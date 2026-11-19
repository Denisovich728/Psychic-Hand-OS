# Archivo: os_actuator_node.py
"""Actuador de sistema operativo (raton, teclado y atajos) para PsychicHandOS."""

import ctypes
from pynput.keyboard import Controller as KeyController, Key
from pynput.mouse import Button, Controller as MouseController


KEY_ALIASES = {
    "ctrl": Key.ctrl_l,
    "control": Key.ctrl_l,
    "alt": Key.alt_l,
    "shift": Key.shift_l,
    "win": Key.cmd,
    "cmd": Key.cmd,
    "super": Key.cmd,
    "tab": Key.tab,
    "enter": Key.enter,
    "return": Key.enter,
    "esc": Key.esc,
    "escape": Key.esc,
    "space": Key.space,
    "backspace": Key.backspace,
    "delete": Key.delete,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "home": Key.home,
    "end": Key.end,
    "page_up": Key.page_up,
    "page_down": Key.page_down,
    "f1": Key.f1,
    "f2": Key.f2,
    "f3": Key.f3,
    "f4": Key.f4,
    "f5": Key.f5,
    "f6": Key.f6,
    "f7": Key.f7,
    "f8": Key.f8,
    "f9": Key.f9,
    "f10": Key.f10,
    "f11": Key.f11,
    "f12": Key.f12,
}


class OSActuatorNode:
    """Ejecuta comandos de cursor, clic, scroll y atajos de teclado en Windows."""

    def __init__(self):
        self.mouse = MouseController()
        self.keyboard = KeyController()
        user32 = ctypes.windll.user32
        self.screen_w = user32.GetSystemMetrics(0)
        self.screen_h = user32.GetSystemMetrics(1)

    def _move_norm(self, val):
        norm_x, norm_y = val
        x = max(0, min(self.screen_w - 1, int(norm_x * self.screen_w)))
        y = max(0, min(self.screen_h - 1, int(norm_y * self.screen_h)))
        self.mouse.position = (x, y)

    def _parse_key(self, token):
        clean = token.strip().lower()
        if clean in KEY_ALIASES:
            return KEY_ALIASES[clean]
        if len(clean) == 1:
            return clean
        return getattr(Key, clean, None)

    def execute_hotkey(self, combo_str):
        """Ejecuta una combinacion tipo 'ctrl+c' o 'win+d'."""
        if not combo_str:
            return
        parts = [p for p in combo_str.split("+") if p.strip()]
        keys = [self._parse_key(p) for p in parts]
        keys = [k for k in keys if k is not None]
        if not keys:
            return

        if len(keys) == 1:
            self.keyboard.tap(keys[0])
            return

        modifiers = keys[:-1]
        target = keys[-1]
        for mod in modifiers:
            self.keyboard.press(mod)
        try:
            self.keyboard.tap(target)
        finally:
            for mod in reversed(modifiers):
                self.keyboard.release(mod)

    def _execute_custom(self, payload):
        atype = payload.get("action_type", "")
        aval = payload.get("action_value", "")

        if atype == "hotkey":
            self.execute_hotkey(aval)
        elif atype == "mouse_click":
            self.mouse.click(Button.left, 1)
        elif atype == "mouse_double_click":
            self.mouse.click(Button.left, 2)
        elif atype == "mouse_right_click":
            self.mouse.click(Button.right, 1)
        elif atype == "scroll_up":
            self.mouse.scroll(0, 3)
        elif atype == "scroll_down":
            self.mouse.scroll(0, -3)
        elif atype == "minimize_current":
            self.execute_hotkey("win+down")
        elif atype == "minimize_all":
            self.execute_hotkey("win+d")
        elif atype == "alt_tab":
            self.execute_hotkey("alt+tab")
        elif atype == "media_play_pause":
            self.keyboard.tap(Key.media_play_pause)
        elif atype == "media_next":
            self.keyboard.tap(Key.media_next)
        elif atype == "media_prev":
            self.keyboard.tap(Key.media_previous)
        elif atype == "volume_up":
            self.keyboard.tap(Key.media_volume_up)
        elif atype == "volume_down":
            self.keyboard.tap(Key.media_volume_down)

    def execute_command(self, command_tuple):
        """Despacha la tupla (accion, valor) hacia el sistema operativo."""
        action, val = command_tuple

        if action == "MOVE_CURSOR":
            self._move_norm(val)
        elif action == "MOUSE_DOWN":
            self._move_norm(val)
            self.mouse.press(Button.left)
        elif action == "MOUSE_UP":
            self.mouse.release(Button.left)
        elif action == "LEFT_CLICK":
            self.mouse.click(Button.left, 1)
        elif action == "DOUBLE_CLICK":
            self.mouse.click(Button.left, 2)
        elif action == "SCROLL":
            self.mouse.scroll(0, int(val))
        elif action == "CUSTOM_ACTION":
            self._execute_custom(val)
