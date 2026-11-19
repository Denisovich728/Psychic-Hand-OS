# Archivo: psychic_hand_os.py
"""Punto de entrada principal de PsychicHandOS: Vision -> Gestos -> Actuador SO."""

import json
import os
import subprocess
import sys
import time

import cv2
import numpy as np
from pynput import keyboard as kb

from gesture_node import GestureNode
from os_actuator_node import OSActuatorNode
from vision_node import VisionNode

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIVE_POSE_PATH = os.path.join(BASE_DIR, "live_pose.json")


class RuntimeState:
    """Estado global de ejecucion controlado por teclas rapidas."""

    def __init__(self):
        self.armed = False
        self.req_reset = False
        self.req_config = False
        self.req_json_dump = False
        self.show_raw = False
        self.running = True


def start_global_hotkeys(state):
    """Registra atajos globales de teclado sin bloquear el hilo de video."""

    def on_press(key):
        if key == kb.Key.f8:
            state.armed = not state.armed
            status = "ARMADO (ON)" if state.armed else "PAUSADO (OFF)"
            print(f"[HOTKEY F8] Control SO: {status}")
        elif key == kb.Key.f9:
            state.req_reset = True
        elif key == kb.Key.f10:
            state.req_config = True
        elif key == kb.Key.f11:
            state.req_json_dump = True
        elif key == kb.Key.f7:
            state.show_raw = not state.show_raw
        elif key == kb.Key.esc:
            state.running = False

    listener = kb.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    return listener


def _format_cmd_label(cmd_tuple):
    action, val = cmd_tuple
    if action == "CUSTOM_ACTION" and isinstance(val, dict):
        return f"CUSTOM: {val.get('name', val.get('action_type', ''))}"
    if isinstance(val, tuple):
        return f"{action} ({val[0]:.2f}, {val[1]:.2f})"
    return f"{action} ({val})" if val is not None else action


def render_hud(frame, topo, cmd_tuple, state):
    """Dibuja la topologia de mano y telemetria sobre fondo negro o camara real."""
    h, w, _ = frame.shape
    canvas = frame.copy() if state.show_raw else np.zeros((h, w, 3), dtype=np.uint8)

    for idx, hand in enumerate(topo.get("hands", [])):
        cx, cy = hand["centroid"]
        r = int(hand["radius"])
        tips = hand.get("tips", [])
        extended = hand.get("extended_fingers", [False] * 5)
        valleys = hand.get("inflections", [])
        chains = hand.get("chains", [])
        mask = hand.get("finger_mask", "00000")
        pinch_idx = hand.get("pinch_index", 0.0)

        if "hull" in hand and hand["hull"] is not None and len(hand["hull"]) >= 3:
            cv2.drawContours(canvas, [hand["hull"]], -1, (0, 120, 0), 1)

        cv2.circle(canvas, (cx, cy), r, (200, 100, 0), 1)
        cv2.circle(canvas, (cx, cy), 6, (255, 120, 0), -1)

        for chain in chains:
            for k in range(len(chain) - 1):
                cv2.line(canvas, chain[k], chain[k + 1], (255, 220, 0), 2)

        for node in valleys:
            cv2.circle(canvas, node, 4, (0, 0, 220), -1)

        for i, tip in enumerate(tips):
            is_ext = extended[i] if i < len(extended) else False
            color = (0, 255, 255) if is_ext else (90, 90, 90)
            radius = 7 if is_ext else 4
            cv2.circle(canvas, tip, radius, color, -1)

        label = (
            f"H{idx+1} [Mask:{mask} | Ext:{hand.get('extended_count', 0)}"
            f" | Pinch:{pinch_idx:.2f} | Aspect:{hand['aspect_ratio']:.2f}]"
        )
        cv2.putText(
            canvas,
            label,
            (max(10, cx - 150), min(h - 28, cy + r + 25)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.44,
            (220, 220, 220),
            1,
        )

    mode_color = (0, 255, 0) if state.armed else (0, 140, 255)
    mode_txt = "ARMED (F8:ON)" if state.armed else "PREVIEW ONLY (F8:OFF)"
    cmd_txt = _format_cmd_label(cmd_tuple)
    cv2.putText(
        canvas,
        f"{mode_txt} | {cmd_txt}",
        (10, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        mode_color,
        2,
    )
    cv2.putText(
        canvas,
        "[F7]Camara [F8]On/Off [F9]Reset [F10]Configurador [F11]JSON [ESC]Salir",
        (10, h - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.41,
        (180, 180, 180),
        1,
    )
    return canvas


def main():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    real_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    real_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[CAMARA HARDWARE] Sensor activo a: {real_w}x{real_h}")

    vision = VisionNode(json_path=os.path.join(BASE_DIR, "psychic_context.json"))
    gesture = GestureNode(config_path=os.path.join(BASE_DIR, "gestures_config.json"))
    actuator = OSActuatorNode()
    state = RuntimeState()
    start_global_hotkeys(state)

    win_name = "PsychicHandOS - Control Gestual"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 960, int(960 * (real_h / max(1, real_w))))

    config_proc = None
    last_live_write = 0.0

    print("=================================================================")
    print("[PsychicHandOS v1.0] INICIADO (F8: OFF)")
    print("  F7  -> Alternar vista (Camara Real / Fondo Negro)")
    print("  F8  -> ACTIVAR / PAUSAR control de Windows")
    print("  F9  -> Reiniciar filtros y estado de gestos")
    print("  F10 -> Abrir Configurador de Gestos")
    print("  F11 -> Exportar telemetria a psychic_context.json")
    print("  ESC -> Salir")
    print("=================================================================")

    try:
        while cap.isOpened() and state.running:
            ret, raw_frame = cap.read()
            if not ret:
                break

            target_h = int(640 * (raw_frame.shape[0] / raw_frame.shape[1]))
            frame = cv2.resize(raw_frame, (640, target_h), interpolation=cv2.INTER_NEAREST)
            frame = cv2.flip(frame, 1)

            if state.req_reset:
                gesture.load_config(force=True)
                state.req_reset = False

            if state.req_config:
                if config_proc is None or config_proc.poll() is not None:
                    config_script = os.path.join(BASE_DIR, "configurator_ui.py")
                    config_proc = subprocess.Popen([sys.executable, config_script])
                state.req_config = False

            if state.req_json_dump:
                vision.export_context_json("hotkey_F11_dump")
                state.req_json_dump = False

            topo = vision.extract_topology(frame)
            cmd_tuple = gesture.evaluate_gesture(topo)

            if config_proc is not None and config_proc.poll() is None:
                now = time.time()
                if (now - last_live_write) >= 0.2 and topo.get("valid"):
                    hand = topo["hands"][-1]
                    with open(LIVE_POSE_PATH, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "finger_mask": hand["finger_mask"],
                                "pinch_index": round(hand["pinch_index"], 3),
                            },
                            f,
                        )
                    last_live_write = now

            if state.armed:
                actuator.execute_command(cmd_tuple)

            hud = render_hud(frame, topo, cmd_tuple, state)
            cv2.imshow(win_name, hud)
            cv2.waitKey(1)
    finally:
        vision.export_context_json("session_exit")
        if os.path.exists(LIVE_POSE_PATH):
            try:
                os.remove(LIVE_POSE_PATH)
            except OSError:
                pass
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
