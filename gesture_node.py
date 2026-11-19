# Archivo: gesture_node.py
"""Evaluador de gestos con filtro One-Euro, maquina de estados y reglas JSON."""

import json
import math
import os
import time
from collections import deque


class OneEuroFilter:
    """Filtro adaptativo paso-bajo: elimina temblor en reposo y mantiene baja latencia."""

    def __init__(self, min_cutoff=1.4, beta=0.04, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / max(1e-6, dt))

    def apply(self, x, t=None):
        t = time.time() if t is None else t
        if self.x_prev is None or self.t_prev is None:
            self.x_prev = x
            self.dx_prev = 0.0
            self.t_prev = t
            return x

        dt = max(1e-4, t - self.t_prev)
        dx = (x - self.x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self.x_prev

        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        return x_hat

    def reset(self):
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None


class GestureNode:
    """Traduce la topologia de VisionNode en acciones discretas y continuas."""

    def __init__(self, config_path="gestures_config.json"):
        self.config_path = config_path
        self._config_mtime = 0.0
        self.config = {}

        self.filter_x = OneEuroFilter()
        self.filter_y = OneEuroFilter()
        self.last_cursor_pos = None

        self.mask_history = deque(maxlen=4)
        self.hold_counters = {}
        self.fired_in_hold = set()
        self.last_rule_fire = {}

        # Estado de pinch-click / drag / doble clic
        self.pinching = False
        self.pinch_start_time = 0.0
        self.dragging = False
        self.last_click_time = 0.0

        # Estado de scroll continuo
        self.prev_scroll_y = None

        self.load_config(force=True)

    def load_config(self, force=False):
        """Carga o recarga gestures_config.json si ha cambiado en disco."""
        if not os.path.exists(self.config_path):
            if force:
                self.config = {
                    "cursor": {
                        "enabled": True,
                        "finger_mask": "01000",
                        "pinch_click": True,
                        "pinch_threshold": 0.36,
                        "drag_hold_sec": 0.35,
                        "double_click_window_sec": 0.45,
                        "margin_x": 0.15,
                        "margin_y": 0.15,
                        "smoothing_min_cutoff": 1.4,
                        "smoothing_beta": 0.04,
                        "deadzone": 0.0025,
                    },
                    "scroll": {
                        "enabled": True,
                        "finger_mask": "01100",
                        "sensitivity": 18.0,
                        "deadzone": 0.004,
                    },
                    "gestures": [],
                }
            return

        mtime = os.path.getmtime(self.config_path)
        if not force and mtime <= self._config_mtime:
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self._config_mtime = mtime

        cur_cfg = self.config.get("cursor", {})
        self.filter_x.min_cutoff = float(cur_cfg.get("smoothing_min_cutoff", 1.4))
        self.filter_x.beta = float(cur_cfg.get("smoothing_beta", 0.04))
        self.filter_y.min_cutoff = float(cur_cfg.get("smoothing_min_cutoff", 1.4))
        self.filter_y.beta = float(cur_cfg.get("smoothing_beta", 0.04))

    def _reset_transient_state(self):
        self.filter_x.reset()
        self.filter_y.reset()
        self.last_cursor_pos = None
        self.mask_history.clear()
        self.hold_counters.clear()
        self.fired_in_hold.clear()
        self.prev_scroll_y = None
        if self.dragging:
            self.dragging = False
            self.pinching = False
            return ("MOUSE_UP", None)
        self.pinching = False
        return ("NONE", None)

    def _stable_mask(self, raw_mask):
        self.mask_history.append(raw_mask)
        if len(self.mask_history) < 2:
            return raw_mask
        counts = {}
        for m in self.mask_history:
            counts[m] = counts.get(m, 0) + 1
        return max(counts.items(), key=lambda kv: kv[1])[0]

    @staticmethod
    def _matches_rule(rule, hand, stable_mask):
        ttype = rule.get("trigger_type", "mask")
        req_mask = rule.get("finger_mask", "")
        if ttype == "mask":
            return stable_mask == req_mask
        if ttype == "pinch_index":
            mask_ok = (not req_mask) or (stable_mask == req_mask)
            return mask_ok and hand["pinch_index"] < 0.36
        if ttype == "pinch_middle":
            mask_ok = (not req_mask) or (stable_mask == req_mask)
            return mask_ok and hand["pinch_middle"] < 0.36
        if ttype == "tilt_side":
            return hand["aspect_ratio"] < 0.43
        return False

    def evaluate_gesture(self, topo):
        """Evalua la topologia actual y retorna una tupla (ACCION, VALOR)."""
        self.load_config(force=False)

        if not topo or not topo.get("valid", False):
            return self._reset_transient_state()

        now = time.time()
        w, h = topo["frame_size"]
        hand = topo["hands"][-1]
        raw_mask = hand["finger_mask"]
        stable_mask = self._stable_mask(raw_mask)

        # 1. Evaluar gestos discretos configurados en JSON
        for rule in self.config.get("gestures", []):
            if not rule.get("enabled", True):
                continue
            rid = rule.get("id", rule.get("name", "rule"))
            if self._matches_rule(rule, hand, stable_mask):
                self.hold_counters[rid] = self.hold_counters.get(rid, 0) + 1
                hold_req = max(1, int(rule.get("hold_frames", 6)))
                cooldown = float(rule.get("cooldown", 1.0))
                last_fire = self.last_rule_fire.get(rid, 0.0)

                if (
                    self.hold_counters[rid] >= hold_req
                    and rid not in self.fired_in_hold
                    and (now - last_fire) >= cooldown
                ):
                    self.fired_in_hold.add(rid)
                    self.last_rule_fire[rid] = now
                    self.prev_scroll_y = None
                    return (
                        "CUSTOM_ACTION",
                        {
                            "id": rid,
                            "name": rule.get("name", rid),
                            "action_type": rule.get("action_type", "hotkey"),
                            "action_value": rule.get("action_value", ""),
                        },
                    )
            else:
                self.hold_counters[rid] = 0
                self.fired_in_hold.discard(rid)

        # 2. Modo Scroll Continuo
        scroll_cfg = self.config.get("scroll", {})
        if scroll_cfg.get("enabled", True) and stable_mask == scroll_cfg.get("finger_mask", "01100"):
            idx_tip = hand["tips"][1]
            mid_tip = hand["tips"][2]
            avg_y = ((idx_tip[1] + mid_tip[1]) * 0.5) / max(1.0, h)
            if self.prev_scroll_y is not None:
                dy = avg_y - self.prev_scroll_y
                deadzone = float(scroll_cfg.get("deadzone", 0.004))
                if abs(dy) > deadzone:
                    sens = float(scroll_cfg.get("sensitivity", 18.0))
                    steps = int(round(-dy * sens * 10))
                    self.prev_scroll_y = avg_y
                    if steps != 0:
                        return ("SCROLL", steps)
            else:
                self.prev_scroll_y = avg_y
            return ("SCROLL_READY", stable_mask)
        else:
            self.prev_scroll_y = None

        # 3. Modo Cursor + Pinch Click / Drag / Doble Clic
        cur_cfg = self.config.get("cursor", {})
        cursor_mask = cur_cfg.get("finger_mask", "01000")
        pinch_click_enabled = bool(cur_cfg.get("pinch_click", True))
        # Permitimos el pulgar extendido o semi-extendido durante modo cursor para hacer pinch
        cursor_active = cur_cfg.get("enabled", True) and (
            stable_mask == cursor_mask
            or (pinch_click_enabled and stable_mask == ("1" + cursor_mask[1:]))
        )

        if cursor_active:
            tx, ty = hand["tips"][1]  # Yema del indice
            mx = w * float(cur_cfg.get("margin_x", 0.15))
            my = h * float(cur_cfg.get("margin_y", 0.15))
            norm_x = max(0.0, min(1.0, (tx - mx) / max(1.0, w - 2 * mx)))
            norm_y = max(0.0, min(1.0, (ty - my) / max(1.0, h - 2 * my)))

            sx = self.filter_x.apply(norm_x, now)
            sy = self.filter_y.apply(norm_y, now)

            if self.last_cursor_pos is not None:
                dz = float(cur_cfg.get("deadzone", 0.0025))
                if math.hypot(sx - self.last_cursor_pos[0], sy - self.last_cursor_pos[1]) < dz:
                    sx, sy = self.last_cursor_pos

            pinch_thresh = float(cur_cfg.get("pinch_threshold", 0.36))
            is_pinched = pinch_click_enabled and (hand["pinch_index"] < pinch_thresh)

            if is_pinched:
                if not self.pinching:
                    self.pinching = True
                    self.pinch_start_time = now
                elif not self.dragging and (now - self.pinch_start_time) >= float(
                    cur_cfg.get("drag_hold_sec", 0.35)
                ):
                    self.dragging = True
                    self.last_cursor_pos = (sx, sy)
                    return ("MOUSE_DOWN", (sx, sy))
                elif self.dragging:
                    self.last_cursor_pos = (sx, sy)
                    return ("MOVE_CURSOR", (sx, sy))

                # Congelar ligeramente el cursor mientras se inicia el pinch para clic preciso
                if self.last_cursor_pos is None:
                    self.last_cursor_pos = (sx, sy)
                return ("PINCH_HOLD", self.last_cursor_pos)

            if self.pinching and not is_pinched:
                self.pinching = False
                if self.dragging:
                    self.dragging = False
                    return ("MOUSE_UP", None)

                dbl_win = float(cur_cfg.get("double_click_window_sec", 0.45))
                if (now - self.last_click_time) <= dbl_win:
                    self.last_click_time = 0.0
                    return ("DOUBLE_CLICK", None)
                self.last_click_time = now
                return ("LEFT_CLICK", None)

            self.last_cursor_pos = (sx, sy)
            return ("MOVE_CURSOR", (sx, sy))

        if self.dragging:
            self.dragging = False
            self.pinching = False
            return ("MOUSE_UP", None)
        self.pinching = False
        return ("TRACKING_IDLE", stable_mask)
