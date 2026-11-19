# Archivo: configurator_ui.py
"""Configurador grafico (Tkinter) para crear, editar y ajustar gestos de PsychicHandOS."""

import json
import os
import time
import tkinter as tk
from tkinter import messagebox, ttk

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gestures_config.json")
LIVE_POSE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_pose.json")

TRIGGER_TYPES = ("mask", "pinch_index", "pinch_middle", "tilt_side")
ACTION_TYPES = (
    "hotkey",
    "mouse_click",
    "mouse_double_click",
    "mouse_right_click",
    "scroll_up",
    "scroll_down",
    "minimize_current",
    "minimize_all",
    "alt_tab",
    "media_play_pause",
    "media_next",
    "media_prev",
    "volume_up",
    "volume_down",
)
FINGER_NAMES = ("Pulgar", "Indice", "Medio", "Anular", "Menique")


class GestureConfiguratorApp:
    """Interfaz grafica para gestionar gestures_config.json."""

    def __init__(self, root):
        self.root = root
        self.root.title("PsychicHandOS - Configurador de Gestos")
        self.root.geometry("920x620")
        self.root.minsize(840, 560)

        self.config = self._load_config()
        self.selected_index = None
        self.live_mask = None

        self._build_ui()
        self._refresh_tree()
        self._load_cursor_scroll_fields()
        self._poll_live_pose()

    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "app_name": "PsychicHandOS",
            "version": "1.0.0",
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

    def _save_config_file(self):
        self._apply_cursor_scroll_fields()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("Guardado", "Configuracion guardada en gestures_config.json.")

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tab_gestures = ttk.Frame(notebook)
        self.tab_cursor = ttk.Frame(notebook)
        notebook.add(self.tab_gestures, text="Gestos Personalizados")
        notebook.add(self.tab_cursor, text="Cursor y Scroll")

        self._build_gestures_tab()
        self._build_cursor_tab()

        footer = ttk.Frame(self.root)
        footer.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.live_label = ttk.Label(footer, text="Postura en vivo: (sin conexion con camara)")
        self.live_label.pack(side=tk.LEFT)
        ttk.Button(footer, text="Guardar Todo en JSON", command=self._save_config_file).pack(
            side=tk.RIGHT
        )

    def _build_gestures_tab(self):
        paned = ttk.PanedWindow(self.tab_gestures, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Lista izquierda
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=3)

        cols = ("name", "enabled", "trigger", "mask", "action")
        self.tree = ttk.Treeview(left_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("name", text="Nombre")
        self.tree.heading("enabled", text="Activo")
        self.tree.heading("trigger", text="Disparo")
        self.tree.heading("mask", text="Mascara")
        self.tree.heading("action", text="Accion")

        self.tree.column("name", width=180)
        self.tree.column("enabled", width=55, anchor=tk.CENTER)
        self.tree.column("trigger", width=90, anchor=tk.CENTER)
        self.tree.column("mask", width=70, anchor=tk.CENTER)
        self.tree.column("action", width=140)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_gesture)

        btn_bar = ttk.Frame(left_frame)
        btn_bar.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_bar, text="Nuevo", command=self._clear_editor).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="Eliminar", command=self._delete_selected).pack(side=tk.LEFT, padx=2)

        # Editor derecho
        right_frame = ttk.LabelFrame(paned, text="Editor de Gesto", padding=10)
        paned.add(right_frame, weight=2)

        self.var_name = tk.StringVar()
        self.var_enabled = tk.BooleanVar(value=True)
        self.var_trigger = tk.StringVar(value="mask")
        self.var_hold = tk.IntVar(value=6)
        self.var_cooldown = tk.DoubleVar(value=1.0)
        self.var_action_type = tk.StringVar(value="hotkey")
        self.var_action_val = tk.StringVar()
        self.finger_vars = [tk.BooleanVar(value=False) for _ in range(5)]

        row = 0
        ttk.Label(right_frame, text="Nombre:").grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Entry(right_frame, textvariable=self.var_name, width=28).grid(
            row=row, column=1, sticky=tk.EW, pady=4
        )

        row += 1
        ttk.Checkbutton(right_frame, text="Gesto habilitado", variable=self.var_enabled).grid(
            row=row, column=1, sticky=tk.W, pady=4
        )

        row += 1
        ttk.Label(right_frame, text="Tipo de disparo:").grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Combobox(
            right_frame,
            textvariable=self.var_trigger,
            values=TRIGGER_TYPES,
            state="readonly",
        ).grid(row=row, column=1, sticky=tk.EW, pady=4)

        row += 1
        ttk.Label(right_frame, text="Dedos extendidos:").grid(
            row=row, column=0, sticky=tk.NW, pady=4
        )
        fingers_box = ttk.Frame(right_frame)
        fingers_box.grid(row=row, column=1, sticky=tk.W, pady=4)
        for idx, fname in enumerate(FINGER_NAMES):
            ttk.Checkbutton(fingers_box, text=fname, variable=self.finger_vars[idx]).pack(
                anchor=tk.W
            )
        ttk.Button(
            fingers_box, text="Usar postura en vivo", command=self._apply_live_pose
        ).pack(anchor=tk.W, pady=(4, 0))

        row += 1
        ttk.Label(right_frame, text="Hold (frames):").grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Spinbox(right_frame, from_=1, to=30, textvariable=self.var_hold, width=10).grid(
            row=row, column=1, sticky=tk.W, pady=4
        )

        row += 1
        ttk.Label(right_frame, text="Cooldown (seg):").grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Spinbox(
            right_frame, from_=0.2, to=10.0, increment=0.1, textvariable=self.var_cooldown, width=10
        ).grid(row=row, column=1, sticky=tk.W, pady=4)

        row += 1
        ttk.Label(right_frame, text="Accion:").grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Combobox(
            right_frame,
            textvariable=self.var_action_type,
            values=ACTION_TYPES,
            state="readonly",
        ).grid(row=row, column=1, sticky=tk.EW, pady=4)

        row += 1
        ttk.Label(right_frame, text="Atajo / Valor:").grid(row=row, column=0, sticky=tk.W, pady=4)
        ttk.Entry(right_frame, textvariable=self.var_action_val, width=28).grid(
            row=row, column=1, sticky=tk.EW, pady=4
        )

        row += 1
        ttk.Label(
            right_frame,
            text="Ejemplos atajo: ctrl+c, win+d, alt+tab, ctrl+shift+t",
            foreground="#666666",
        ).grid(row=row, column=1, sticky=tk.W)

        row += 1
        ttk.Button(
            right_frame, text="Agregar / Actualizar Gesto", command=self._save_editor_gesture
        ).grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(12, 0))

        right_frame.columnconfigure(1, weight=1)

    def _build_cursor_tab(self):
        frame = ttk.Frame(self.tab_cursor, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        self.var_cur_enabled = tk.BooleanVar()
        self.var_cur_mask = tk.StringVar()
        self.var_pinch_click = tk.BooleanVar()
        self.var_pinch_thresh = tk.DoubleVar()
        self.var_margin_x = tk.DoubleVar()
        self.var_margin_y = tk.DoubleVar()
        self.var_min_cutoff = tk.DoubleVar()
        self.var_beta = tk.DoubleVar()
        self.var_cur_deadzone = tk.DoubleVar()

        self.var_scr_enabled = tk.BooleanVar()
        self.var_scr_mask = tk.StringVar()
        self.var_scr_sens = tk.DoubleVar()

        cur_box = ttk.LabelFrame(frame, text="Control de Cursor", padding=10)
        cur_box.pack(fill=tk.X, pady=(0, 12))

        fields_cur = [
            ("Mascara cursor (5 bits):", self.var_cur_mask),
            ("Umbral pinch clic:", self.var_pinch_thresh),
            ("Margen X (0.0 - 0.4):", self.var_margin_x),
            ("Margen Y (0.0 - 0.4):", self.var_margin_y),
            ("Filtro min_cutoff:", self.var_min_cutoff),
            ("Filtro beta:", self.var_beta),
            ("Zona muerta cursor:", self.var_cur_deadzone),
        ]
        ttk.Checkbutton(cur_box, text="Cursor habilitado", variable=self.var_cur_enabled).grid(
            row=0, column=0, sticky=tk.W, pady=3
        )
        ttk.Checkbutton(
            cur_box, text="Clic y arrastre por pinch pulgar+indice", variable=self.var_pinch_click
        ).grid(row=0, column=1, sticky=tk.W, pady=3)

        for i, (label, var) in enumerate(fields_cur, start=1):
            ttk.Label(cur_box, text=label).grid(row=i, column=0, sticky=tk.W, pady=3)
            ttk.Entry(cur_box, textvariable=var, width=18).grid(row=i, column=1, sticky=tk.W, pady=3)

        scr_box = ttk.LabelFrame(frame, text="Scroll Continuo", padding=10)
        scr_box.pack(fill=tk.X)
        ttk.Checkbutton(scr_box, text="Scroll habilitado", variable=self.var_scr_enabled).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=3
        )
        ttk.Label(scr_box, text="Mascara scroll (5 bits):").grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Entry(scr_box, textvariable=self.var_scr_mask, width=18).grid(
            row=1, column=1, sticky=tk.W, pady=3
        )
        ttk.Label(scr_box, text="Sensibilidad:").grid(row=2, column=0, sticky=tk.W, pady=3)
        ttk.Entry(scr_box, textvariable=self.var_scr_sens, width=18).grid(
            row=2, column=1, sticky=tk.W, pady=3
        )

    def _load_cursor_scroll_fields(self):
        c = self.config.get("cursor", {})
        self.var_cur_enabled.set(bool(c.get("enabled", True)))
        self.var_cur_mask.set(c.get("finger_mask", "01000"))
        self.var_pinch_click.set(bool(c.get("pinch_click", True)))
        self.var_pinch_thresh.set(float(c.get("pinch_threshold", 0.36)))
        self.var_margin_x.set(float(c.get("margin_x", 0.15)))
        self.var_margin_y.set(float(c.get("margin_y", 0.15)))
        self.var_min_cutoff.set(float(c.get("smoothing_min_cutoff", 1.4)))
        self.var_beta.set(float(c.get("smoothing_beta", 0.04)))
        self.var_cur_deadzone.set(float(c.get("deadzone", 0.0025)))

        s = self.config.get("scroll", {})
        self.var_scr_enabled.set(bool(s.get("enabled", True)))
        self.var_scr_mask.set(s.get("finger_mask", "01100"))
        self.var_scr_sens.set(float(s.get("sensitivity", 18.0)))

    def _apply_cursor_scroll_fields(self):
        c = self.config.setdefault("cursor", {})
        c["enabled"] = bool(self.var_cur_enabled.get())
        c["finger_mask"] = self.var_cur_mask.get().strip() or "01000"
        c["pinch_click"] = bool(self.var_pinch_click.get())
        c["pinch_threshold"] = float(self.var_pinch_thresh.get())
        c["margin_x"] = float(self.var_margin_x.get())
        c["margin_y"] = float(self.var_margin_y.get())
        c["smoothing_min_cutoff"] = float(self.var_min_cutoff.get())
        c["smoothing_beta"] = float(self.var_beta.get())
        c["deadzone"] = float(self.var_cur_deadzone.get())

        s = self.config.setdefault("scroll", {})
        s["enabled"] = bool(self.var_scr_enabled.get())
        s["finger_mask"] = self.var_scr_mask.get().strip() or "01100"
        s["sensitivity"] = float(self.var_scr_sens.get())

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, g in enumerate(self.config.get("gestures", [])):
            action_desc = g.get("action_type", "")
            if g.get("action_value"):
                action_desc = f"{action_desc} ({g['action_value']})"
            self.tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    g.get("name", ""),
                    "Si" if g.get("enabled", True) else "No",
                    g.get("trigger_type", "mask"),
                    g.get("finger_mask", ""),
                    action_desc,
                ),
            )

    def _on_select_gesture(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self.selected_index = idx
        g = self.config["gestures"][idx]

        self.var_name.set(g.get("name", ""))
        self.var_enabled.set(bool(g.get("enabled", True)))
        self.var_trigger.set(g.get("trigger_type", "mask"))
        self.var_hold.set(int(g.get("hold_frames", 6)))
        self.var_cooldown.set(float(g.get("cooldown", 1.0)))
        self.var_action_type.set(g.get("action_type", "hotkey"))
        self.var_action_val.set(g.get("action_value", ""))

        mask = g.get("finger_mask", "00000").ljust(5, "0")
        for i in range(5):
            self.finger_vars[i].set(mask[i] == "1")

    def _clear_editor(self):
        self.selected_index = None
        self.tree.selection_remove(self.tree.selection())
        self.var_name.set("")
        self.var_enabled.set(True)
        self.var_trigger.set("mask")
        self.var_hold.set(6)
        self.var_cooldown.set(1.0)
        self.var_action_type.set("hotkey")
        self.var_action_val.set("")
        for var in self.finger_vars:
            var.set(False)

    def _save_editor_gesture(self):
        name = self.var_name.get().strip()
        if not name:
            messagebox.showwarning("Campo requerido", "Ingresa un nombre para el gesto.")
            return

        mask = "".join("1" if v.get() else "0" for v in self.finger_vars)
        ttype = self.var_trigger.get()
        if ttype != "mask" and mask == "00000":
            mask = ""

        gestures = self.config.setdefault("gestures", [])
        gid = (
            gestures[self.selected_index]["id"]
            if self.selected_index is not None
            else f"custom_{int(time.time())}"
        )

        entry = {
            "id": gid,
            "name": name,
            "enabled": bool(self.var_enabled.get()),
            "trigger_type": ttype,
            "finger_mask": mask,
            "hold_frames": int(self.var_hold.get()),
            "cooldown": float(self.var_cooldown.get()),
            "action_type": self.var_action_type.get(),
            "action_value": self.var_action_val.get().strip(),
        }

        if self.selected_index is not None:
            gestures[self.selected_index] = entry
        else:
            gestures.append(entry)

        self._refresh_tree()
        self._clear_editor()

    def _delete_selected(self):
        if self.selected_index is None:
            return
        del self.config["gestures"][self.selected_index]
        self._refresh_tree()
        self._clear_editor()

    def _poll_live_pose(self):
        try:
            if os.path.exists(LIVE_POSE_PATH) and (time.time() - os.path.getmtime(LIVE_POSE_PATH)) < 2.0:
                with open(LIVE_POSE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.live_mask = data.get("finger_mask")
                pinch_i = data.get("pinch_index", 0.0)
                self.live_label.config(
                    text=f"Postura en vivo: mascara={self.live_mask} | pinch_indice={pinch_i:.2f}"
                )
            else:
                self.live_mask = None
                self.live_label.config(text="Postura en vivo: (sin conexion con camara)")
        except Exception:
            pass
        self.root.after(200, self._poll_live_pose)

    def _apply_live_pose(self):
        if not self.live_mask or len(self.live_mask) != 5:
            messagebox.showinfo(
                "Sin postura",
                "Inicia PsychicHandOS y coloca tu mano frente a la camara para capturar.",
            )
            return
        for i in range(5):
            self.finger_vars[i].set(self.live_mask[i] == "1")


def main():
    root = tk.Tk()
    GestureConfiguratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
