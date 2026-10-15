import copy
import ctypes
import json
import os
import re
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

from .capture import best_template_match
from .config import CHECK_INTERVAL, CONFIG_FILE, DEFAULT_CONFIG, DEFAULT_HOTKEY, MATCH_THRESHOLD
from .geometry import (
    build_font_spec,
    clamp_box_to_screen,
    get_centered_box_for_screen,
    get_lower_right_box_for_screen,
    normalize_color,
    normalize_font_size,
    normalize_overlay_box_for_screen,
)


def set_window_min_size(win):
    try:
        win.update_idletasks()
        win.minsize(win.winfo_reqwidth() + 20, win.winfo_reqheight() + 20)
    except Exception:
        pass


class RegionSelector:
    def __init__(self, parent_root, callback, title_text="Select the active region"):
        self.callback = callback
        self.selector_win = tk.Toplevel(parent_root)
        self.selector_win.transient(parent_root)
        self.selector_win.grab_set()
        self.selector_win.attributes("-alpha", 0.3)
        self.selector_win.attributes("-fullscreen", True)
        self.selector_win.attributes("-topmost", True)
        self.selector_win.title(title_text)

        self.canvas = tk.Canvas(self.selector_win, cursor="cross", bg="grey")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.start_x = None
        self.start_y = None
        self.rect = None

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline="#0078d4", width=2)

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        left = min(self.start_x, event.x)
        top = min(self.start_y, event.y)
        width = abs(event.x - self.start_x)
        height = abs(event.y - self.start_y)
        box = {"top": top, "left": left, "width": width, "height": height}
        self.selector_win.destroy()
        if self.callback:
            self.callback(box)


class CaptureSettingsWindow:
    def __init__(self, parent_root, callback, default_duration="2.0", default_fps="12"):
        self.callback = callback
        self.win = tk.Toplevel(parent_root)
        self.win.title("Record active animation")
        self.win.configure(bg="#202020")
        self.win.attributes("-topmost", True)
        self.win.transient(parent_root)
        self.win.grab_set()

        tk.Label(self.win, text="Capture Duration (seconds)", fg="#ffffff", bg="#202020", font=("Segoe UI", 10, "bold")).pack(pady=(14, 6))
        self.duration_var = tk.StringVar(value=default_duration)
        tk.Entry(self.win, textvariable=self.duration_var, width=12, font=("Segoe UI", 10), justify="center").pack()

        tk.Label(self.win, text="Frames per second", fg="#ffffff", bg="#202020", font=("Segoe UI", 10, "bold")).pack(pady=(12, 6))
        self.fps_var = tk.StringVar(value=default_fps)
        tk.Entry(self.win, textvariable=self.fps_var, width=12, font=("Segoe UI", 10), justify="center").pack()

        self.status_label = tk.Label(self.win, text="", fg="#ffd166", bg="#202020", font=("Segoe UI", 9))
        self.status_label.pack(pady=(12, 0))

        tk.Button(self.win, text="Start Recording", command=self.apply, bg="#107c10", fg="#ffffff", font=("Segoe UI", 10, "bold"), width=20).pack(pady=(18, 8))
        set_window_min_size(self.win)

    def apply(self):
        try:
            duration = float(self.duration_var.get())
            fps = int(self.fps_var.get())
        except ValueError:
            self.status_label.config(text="Use a number like 2.0 and an integer like 12.")
            return
        duration = max(0.2, duration)
        fps = max(1, min(30, fps))
        self.win.destroy()
        if self.callback:
            self.callback(duration, fps)


class TextDesignerWindow:
    def __init__(self, parent_root, current_config, save_callback):
        self.save_callback = save_callback
        self.config = current_config
        self.skill_entries = current_config.get("skills", []) if isinstance(current_config, dict) and "skills" in current_config else [current_config]

        self.win = tk.Toplevel(parent_root)
        self.win.title("Live Overlay Layout")
        self.win.attributes("-topmost", True)
        self.win.attributes("-fullscreen", True)
        self.win.overrideredirect(True)
        self.win.attributes("-transparentcolor", "black")
        self.win.attributes("-alpha", 1.0)
        self.win.configure(bg="black")
        self.win.bind("<Escape>", lambda _event: self.win.destroy())

        self.stage = tk.Frame(self.win, bg="black")
        self.stage.place(x=0, y=0, relwidth=1, relheight=1)

        self.panel = tk.Frame(self.win, bg="#0f172a", padx=10, pady=10, highlightthickness=1, highlightbackground="#7fe8ff")
        self.panel.configure(width=340)
        self.panel.pack_propagate(False)
        self.panel.grid_columnconfigure(0, weight=1)
        self.panel.place(relx=1.0, rely=1.0, anchor="se", x=-18, y=-18)

        self.canvas = tk.Canvas(self.stage, bg="black", highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel_resize)
        self.stage.bind("<MouseWheel>", self.on_mouse_wheel_resize)

        tk.Label(self.panel, text="Overlay Layout", fg="#eaf7ff", bg="#0f172a", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(self.panel, text="Drag the outlined box to move it. Wheel = resize text.", fg="#d3e3f6", bg="#0f172a", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(4, 12))

        tk.Label(self.panel, text="Item", fg="#b8d5ef", bg="#0f172a", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w")
        self.skill_names = [str((skill.get("name") or f"Item {idx + 1}")).strip() or f"Item {idx + 1}" for idx, skill in enumerate(self.skill_entries)]
        self.skill_var = tk.StringVar()
        self.skill_combo = ttk.Combobox(self.panel, textvariable=self.skill_var, values=self.skill_names, state="readonly", width=30)
        self.skill_combo.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self.skill_combo.bind("<<ComboboxSelected>>", self.on_skill_changed)

        tk.Label(self.panel, text="Text", fg="#b8d5ef", bg="#0f172a", font=("Segoe UI", 9, "bold")).grid(row=4, column=0, sticky="w")
        self.text_var = tk.StringVar()
        self.text_entry = tk.Entry(self.panel, textvariable=self.text_var, width=28, font=("Segoe UI", 9), bg="#1e293b", fg="#ffffff", insertbackground="white")
        self.text_entry.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        self.text_entry.bind("<KeyRelease>", self.on_live_editor_change)

        tk.Label(self.panel, text="Font", fg="#b8d5ef", bg="#0f172a", font=("Segoe UI", 9, "bold")).grid(row=6, column=0, sticky="w")
        self.font_var = tk.StringVar()
        self.font_combo = ttk.Combobox(self.panel, textvariable=self.font_var, values=self.get_font_choices(), state="readonly", width=30)
        self.font_combo.grid(row=7, column=0, sticky="ew", pady=(0, 10))
        self.font_combo.bind("<<ComboboxSelected>>", self.on_live_editor_change)

        tk.Label(self.panel, text="Size", fg="#b8d5ef", bg="#0f172a", font=("Segoe UI", 9, "bold")).grid(row=8, column=0, sticky="w")
        self.size_var = tk.IntVar()
        self.size_slider = tk.Scale(self.panel, from_=10, to_=96, orient="horizontal", variable=self.size_var, bg="#0f172a", fg="#ffffff", highlightthickness=0, sliderrelief="flat")
        self.size_slider.grid(row=9, column=0, sticky="ew", pady=(0, 10))
        self.size_slider.configure(command=self.on_live_editor_change)

        tk.Label(self.panel, text="Color", fg="#b8d5ef", bg="#0f172a", font=("Segoe UI", 9, "bold")).grid(row=10, column=0, sticky="w")
        color_row = tk.Frame(self.panel, bg="#0f172a")
        color_row.grid(row=11, column=0, sticky="ew", pady=(0, 12))
        self.color_value = tk.StringVar(value="#ff3333")
        self.color_display = tk.Label(color_row, text="  ", bg="#ff3333", width=6, relief="solid", borderwidth=1)
        self.color_display.pack(side="left")
        self.color_entry = tk.Entry(color_row, textvariable=self.color_value, width=10, font=("Segoe UI", 9), bg="#1e293b", fg="#ffffff", insertbackground="white")
        self.color_entry.pack(side="left", padx=(8, 0))
        self.color_entry.bind("<Return>", lambda _event: self.set_selected_color(self.color_value.get()))
        self.color_entry.bind("<FocusOut>", lambda _event: self.set_selected_color(self.color_value.get()))

        palette_row = tk.Frame(self.panel, bg="#0f172a")
        palette_row.grid(row=12, column=0, sticky="ew", pady=(0, 12))
        for color in ["#ff3333", "#ffd166", "#00d1b2", "#3b82f6", "#8b5cf6", "#f472b6", "#ffffff", "#000000"]:
            tk.Button(palette_row, bg=color, activebackground=color, command=lambda chosen=color: self.set_selected_color(chosen), width=3, height=1, relief="solid", bd=1).pack(side="left", padx=2)

        button_row = tk.Frame(self.panel, bg="#0f172a")
        button_row.grid(row=13, column=0, sticky="ew", pady=(8, 0))
        tk.Button(button_row, text="Center", command=self.center_selected_box, bg="#2563eb", fg="#ffffff", font=("Segoe UI", 9, "bold"), bd=0, padx=10).pack(side="left")
        tk.Button(button_row, text="Accept", command=self.apply_changes, bg="#107c10", fg="#ffffff", font=("Segoe UI", 9, "bold"), bd=0, padx=10).pack(side="left", padx=(8, 0))
        tk.Button(button_row, text="Close", command=self.win.destroy, bg="#4a4a4a", fg="#ffffff", font=("Segoe UI", 9, "bold"), bd=0, padx=10).pack(side="right")

        self.drag_item = None
        self.drag_offset = (0, 0)
        self.selected_skill_idx = 0 if self.skill_entries else -1
        self._ensure_centered_layout()
        self.refresh_controls()
        self.refresh_preview()

    def get_font_choices(self):
        preferred = ["Segoe UI", "Arial", "Tahoma", "Verdana", "Calibri", "Consolas", "Microsoft Sans Serif", "Times New Roman"]
        fonts = []
        seen = set()
        try:
            import tkinter.font as tkfont
            available = list(tkfont.families())
        except Exception:
            available = []
        for family in preferred + available:
            if family and family not in seen:
                fonts.append(family)
                seen.add(family)
        return fonts

    def _skill_box(self, item, idx):
        raw = item.get("overlay_box") or {"x": item.get("overlay_x"), "y": item.get("overlay_y"), "w": item.get("overlay_width", 420), "h": item.get("overlay_height", 120)}
        width = max(180, int(raw.get("w", 420)))
        height = max(60, int(raw.get("h", 120)))
        box = normalize_overlay_box_for_screen(raw.get("x"), raw.get("y"), width, height, self.win.winfo_screenwidth(), self.win.winfo_screenheight(), idx=idx)
        item["overlay_box"] = box
        item["overlay_x"] = box["x"]
        item["overlay_y"] = box["y"]
        item["overlay_width"] = box["w"]
        item["overlay_height"] = box["h"]
        return box

    def _ensure_centered_layout(self):
        for idx, item in enumerate(self.skill_entries):
            box = self._skill_box(item, idx)
            screen_w = self.win.winfo_screenwidth()
            screen_h = self.win.winfo_screenheight()
            if box["x"] < 30 or box["y"] < 30 or box["x"] + box["w"] > screen_w - 30 or box["y"] + box["h"] > screen_h - 30:
                default_box = get_lower_right_box_for_screen(screen_w, screen_h, width=box["w"], height=box["h"], idx=idx)
                self._sync_box_to_item(item, default_box)

    def _sync_box_to_item(self, item, box):
        item["overlay_box"] = box
        item["overlay_x"] = int(box["x"])
        item["overlay_y"] = int(box["y"])
        item["overlay_width"] = int(box["w"])
        item["overlay_height"] = int(box["h"])

    def on_skill_changed(self, event=None):
        if not self.skill_entries:
            return
        value = self.skill_var.get()
        for idx, skill in enumerate(self.skill_entries):
            name = str((skill.get("name") or f"Item {idx + 1}")).strip() or f"Item {idx + 1}"
            if name == value:
                self.selected_skill_idx = idx
                self.refresh_controls()
                return

    def center_selected_box(self):
        if self.selected_skill_idx < 0 or not self.skill_entries:
            return
        skill = self.skill_entries[self.selected_skill_idx]
        width = max(180, int(skill.get("overlay_width", self.config.get("overlay_width", 420))))
        height = max(60, int(skill.get("overlay_height", self.config.get("overlay_height", 120))))
        centered = get_centered_box_for_screen(self.win.winfo_screenwidth(), self.win.winfo_screenheight(), width=width, height=height, idx=self.selected_skill_idx)
        self._sync_box_to_item(skill, centered)
        self.refresh_preview()

    def set_selected_color(self, color_value):
        if self.selected_skill_idx < 0:
            return
        try:
            color = normalize_color(color_value)
        except Exception:
            return
        self.color_value.set(color)
        self.color_entry.delete(0, tk.END)
        self.color_entry.insert(0, color)
        self.color_display.configure(bg=color)
        self.apply_selected_skill_editor()
        self.refresh_preview()

    def refresh_controls(self):
        if not self.skill_entries:
            return
        if self.selected_skill_idx < 0:
            self.selected_skill_idx = 0
        skill = self.skill_entries[self.selected_skill_idx]
        self.skill_var.set(str((skill.get("name") or f"Item {self.selected_skill_idx + 1}")).strip() or f"Item {self.selected_skill_idx + 1}")
        self.text_var.set(skill.get("alert_text") or "")
        self.font_var.set(skill.get("font_family") or self.config.get("font_family", "Segoe UI"))
        self.size_var.set(normalize_font_size(skill.get("font_size", self.config.get("font_size", 28))))
        hex_color = normalize_color(skill.get("font_color", self.config.get("font_color", "#ff3333")))
        self.color_value.set(hex_color)
        if hasattr(self, "color_entry"):
            self.color_entry.delete(0, tk.END)
            self.color_entry.insert(0, hex_color)
        self.color_display.configure(bg=hex_color)

    def apply_selected_skill_editor(self):
        if self.selected_skill_idx < 0 or not self.skill_entries:
            return
        skill = self.skill_entries[self.selected_skill_idx]
        skill["alert_text"] = self.text_var.get().strip() or (skill.get("name") or "STATUS MISSING")
        skill["font_family"] = self.font_var.get() or self.config.get("font_family", "Segoe UI")
        skill["font_size"] = normalize_font_size(self.size_var.get())
        skill["font_color"] = normalize_color(self.color_value.get())
        if skill.get("font_weight") is None:
            skill["font_weight"] = self.config.get("font_weight", "bold")

    def on_live_editor_change(self, event=None, *args):
        self.apply_selected_skill_editor()
        self.refresh_preview()

    def on_mouse_wheel_resize(self, event):
        if self.selected_skill_idx < 0 or not self.skill_entries:
            return
        skill = self.skill_entries[self.selected_skill_idx]
        current_size = normalize_font_size(skill.get("font_size", self.config.get("font_size", 28)))
        delta = 1 if getattr(event, "delta", 0) > 0 else -1
        new_size = max(10, min(96, current_size + delta * 2))
        self.size_var.set(new_size)
        self.apply_selected_skill_editor()
        self.refresh_preview()

    def on_press(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        for idx, item in enumerate(self.skill_entries):
            box = self._skill_box(item, idx)
            if box["x"] <= x <= box["x"] + box["w"] and box["y"] <= y <= box["y"] + box["h"]:
                self.selected_skill_idx = idx
                self.refresh_controls()
                self.drag_item = idx
                self.drag_offset = (x - box["x"], y - box["y"])
                return

    def on_drag(self, event):
        if self.drag_item is None:
            return
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        item = self.skill_entries[self.drag_item]
        box = self._skill_box(item, self.drag_item)
        proposed = {"x": x - self.drag_offset[0], "y": y - self.drag_offset[1], "w": box["w"], "h": box["h"]}
        clamped = clamp_box_to_screen(proposed["x"], proposed["y"], proposed["w"], proposed["h"], self.win.winfo_screenwidth(), self.win.winfo_screenheight())
        self._sync_box_to_item(item, clamped)
        self.refresh_preview()

    def on_release(self, event):
        self.drag_item = None

    def refresh_preview(self):
        self.canvas.delete("all")
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        self.canvas.create_rectangle(30, 30, screen_w - 30, screen_h - 30, outline="#8ce6ff", width=2, dash=(7, 7), fill="")
        for idx, item in enumerate(self.skill_entries):
            box = self._skill_box(item, idx)
            x, y, w, h = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
            text = (item.get("alert_text") or item.get("name") or f"Item {idx + 1}").strip() or "STATUS MISSING"
            font_family = item.get("font_family", self.config.get("font_family", "Segoe UI"))
            font_size = normalize_font_size(item.get("font_size", self.config.get("font_size", 28)))
            font_weight = item.get("font_weight", self.config.get("font_weight", "bold"))
            font = build_font_spec(font_family, font_size, font_weight)
            is_active = idx == self.selected_skill_idx
            outline = "#7fe8ff" if is_active else "#5bc1ff"
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=outline, fill="", width=4)
            self.canvas.create_text(x + w / 2, y + h / 2, text=text, fill=normalize_color(item.get("font_color", self.config.get("font_color", "#ff3333"))), font=font, justify="center", anchor="center")
            self.canvas.create_rectangle(x + w - 18, y + h - 18, x + w + 12, y + h + 12, fill="#7fe8ff", outline="#ffffff", width=1)

    def apply_changes(self):
        self.apply_selected_skill_editor()
        for idx, item in enumerate(self.skill_entries):
            box = self._skill_box(item, idx)
            item["overlay_x"] = int(box["x"])
            item["overlay_y"] = int(box["y"])
            item["overlay_width"] = int(box["w"])
            item["overlay_height"] = int(box["h"])
            item["overlay_box"] = box
        self.config["skills"] = list(self.skill_entries)
        self.config["overlay_x"] = int(self.skill_entries[0].get("overlay_x", self.config.get("overlay_x", 200))) if self.skill_entries else int(self.config.get("overlay_x", 200))
        self.config["overlay_y"] = int(self.skill_entries[0].get("overlay_y", self.config.get("overlay_y", 180))) if self.skill_entries else int(self.config.get("overlay_y", 180))
        self.config["overlay_width"] = max(200, int(self.skill_entries[0].get("overlay_width", self.config.get("overlay_width", 900)))) if self.skill_entries else max(200, int(self.config.get("overlay_width", 900)))
        self.config["overlay_height"] = max(80, int(self.skill_entries[0].get("overlay_height", self.config.get("overlay_height", 220)))) if self.skill_entries else max(80, int(self.config.get("overlay_height", 220)))
        self.save_callback(self.config)
        self.win.destroy()


class VisualMonitorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Visual Monitor Template")
        self.root.geometry("1100x700")
        self.root.configure(bg="#202020")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.resizable(True, True)
        self.root.attributes("-topmost", False)

        self.config = self.load_config()
        self.previous_hotkey = self.config.get("hotkey", DEFAULT_HOTKEY)
        self.is_monitoring = False
        self.skills_ui = []
        self.screen_capture = None
        self.target_window_title = self.config.get("target_window_title", "")
        self.target_window_hwnd = self.config.get("target_window_hwnd")

        self.ensure_runtime_dependencies()
        self.setup_styles()
        self.setup_control_panel()
        self.setup_overlay()
        self.populate_skills()

    def ensure_runtime_dependencies(self):
        try:
            import keyboard
            import mss
            import numpy as np
            import cv2
        except ImportError as exc:  # pragma: no cover - runtime dependency guard
            raise RuntimeError(
                "Missing runtime dependencies. Install with: python -m pip install -e ."
            ) from exc
        self.keyboard = keyboard
        self.mss_mod = mss
        self.cv2 = cv2
        self.np = np
        self.screen_capture = mss.MSS()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as handle:
                    loaded = json.load(handle)
                    merged = copy.deepcopy(DEFAULT_CONFIG)
                    merged.update(loaded)
                    if isinstance(loaded.get("skills"), list):
                        merged["skills"] = loaded["skills"]
                    return merged
            except Exception:
                pass
        return copy.deepcopy(DEFAULT_CONFIG)

    def save_config(self, updated_cfg=None):
        if updated_cfg is not None:
            self.config = updated_cfg

        self.config["font_color"] = normalize_color(self.config.get("font_color", "#ff3333"))
        self.config["font_size"] = normalize_font_size(self.config.get("font_size", 28))
        self.config["font_family"] = self.config.get("font_family", "Segoe UI")
        self.config["font_weight"] = (self.config.get("font_weight", "bold") or "bold").lower()
        self.config["overlay_x"] = int(self.config.get("overlay_x", 200))
        self.config["overlay_y"] = int(self.config.get("overlay_y", 180))
        self.config["overlay_width"] = max(200, int(self.config.get("overlay_width", 900)))
        self.config["overlay_height"] = max(80, int(self.config.get("overlay_height", 220)))
        self.config["hotkey"] = self.config.get("hotkey", DEFAULT_HOTKEY)
        self.config["target_window_title"] = self.target_window_title
        self.config["target_window_hwnd"] = self.target_window_hwnd

        try:
            with open(CONFIG_FILE, "w") as handle:
                json.dump(self.config, handle, indent=4)
        except Exception as exc:
            print(f"[Error saving config]: {exc}")

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TScrollbar", background="#2d2d2d", troughcolor="#202020", bordercolor="#202020", arrowcolor="#ffffff")

    def setup_control_panel(self):
        self.root.geometry("1280x760")
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        top_bar = tk.Frame(self.root, bg="#2d2d2d", padx=15, pady=12)
        top_bar.grid(row=0, column=0, sticky="ew")

        self.hotkey_var = tk.StringVar(value=self.config.get("hotkey", DEFAULT_HOTKEY))
        hotkey_frame = tk.Frame(top_bar, bg="#2d2d2d")
        hotkey_frame.pack(side="left")
        tk.Label(hotkey_frame, text="Hotkey:", fg="#0078d4", bg="#2d2d2d", font=("Segoe UI", 10, "bold")).pack(side="left")
        hotkey_entry = tk.Entry(hotkey_frame, textvariable=self.hotkey_var, width=10, font=("Segoe UI", 10, "bold"), bg="#333333", fg="#ffffff", insertbackground="white")
        hotkey_entry.pack(side="left", padx=6)
        tk.Button(hotkey_frame, text="Apply", command=self.apply_hotkey, bg="#333333", fg="#ffffff", font=("Segoe UI", 9, "bold")).pack(side="left")

        self.target_window_var = tk.StringVar(value=self.target_window_title or "No target window selected")
        target_frame = tk.Frame(top_bar, bg="#2d2d2d")
        target_frame.pack(side="left", padx=(18, 10))
        tk.Label(target_frame, text="Target:", fg="#0078d4", bg="#2d2d2d", font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(target_frame, textvariable=self.target_window_var, fg="#ffffff", bg="#2d2d2d", font=("Segoe UI", 9), width=28, anchor="w").pack(side="left", padx=6)
        tk.Button(target_frame, text="Select Window", command=self.select_target_window, bg="#333333", fg="#ffffff", font=("Segoe UI", 9, "bold")).pack(side="left")

        self.status_label = tk.Label(top_bar, text="Status: STOPPED", fg="#ff4343", bg="#2d2d2d", font=("Segoe UI", 10, "bold"))
        self.status_label.pack(side="right", padx=10)

        action_bar = tk.Frame(self.root, bg="#202020", padx=15, pady=10)
        action_bar.grid(row=1, column=0, sticky="ew")

        tk.Button(action_bar, text="＋ Add Item", command=self.add_skill_row, bg="#2c2c2c", fg="#ffffff", font=("Segoe UI", 9, "bold"), bd=0, padx=10, relief="flat").pack(side="left", padx=2)
        tk.Button(action_bar, text="Layout Overlay", command=self.open_text_designer, bg="#2c2c2c", fg="#ffffff", font=("Segoe UI", 9, "bold"), bd=0, padx=10).pack(side="left", padx=10)
        self.toggle_btn = tk.Button(action_bar, text="Start Monitoring", command=self.toggle_monitoring, bg="#107c10", fg="#ffffff", font=("Segoe UI", 9, "bold"), bd=0, width=18)
        self.toggle_btn.pack(side="right", padx=2)
        tk.Button(action_bar, text="Hide App", command=self.hide_main_window, bg="#3a3a3a", fg="#ffffff", font=("Segoe UI", 9, "bold"), bd=0, width=11).pack(side="right", padx=6)

        container = tk.Frame(self.root, bg="#202020")
        container.grid(row=2, column=0, sticky="nsew")
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.skills_frame = tk.Frame(container, bg="#202020")
        self.skills_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.skills_frame.grid_columnconfigure(0, weight=1)
        self.skills_frame.grid_columnconfigure(1, weight=1)

        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth() + 20, self.root.winfo_reqheight() + 20)

    def setup_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-transparentcolor", "black")
        self.overlay.attributes("-topmost", True)
        self.overlay.attributes("-alpha", 1.0)
        self.overlay.configure(bg="black")
        self.update_overlay_geometry()

        self.alert_label = tk.Label(
            self.overlay,
            text="",
            font=("Segoe UI", 24, "bold"),
            fg=self.config.get("font_color", "#ff3333"),
            bg="black",
            justify="center",
            compound="center",
        )
        self.alert_label.pack(expand=True, fill="both")

    def _list_windows(self):
        windows = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def callback(hwnd, _):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
                    title = buffer.value.strip()
                    if title:
                        windows.append((hwnd, title))
            return True

        ctypes.windll.user32.EnumWindows(callback, None)
        return windows

    def select_target_window(self):
        windows = self._list_windows()
        if not windows:
            return

        win = tk.Toplevel(self.root)
        win.title("Select target window")
        win.transient(self.root)
        win.grab_set()
        win.geometry("420x360")
        win.minsize(320, 220)

        tk.Label(win, text="Pick the application or game window to monitor.", font=("Segoe UI", 10, "bold")).pack(padx=12, pady=(12, 8))
        listbox = tk.Listbox(win, height=16, exportselection=False, font=("Segoe UI", 9))
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        for _, title in windows:
            listbox.insert(tk.END, title)

        def apply_selected():
            idx = listbox.curselection()
            if not idx:
                win.destroy()
                return
            hwnd, title = windows[idx[0]]
            self.target_window_hwnd = hwnd
            self.target_window_title = title
            self.target_window_var.set(title[:36] + ("..." if len(title) > 36 else ""))
            self.config["target_window_title"] = title
            self.config["target_window_hwnd"] = hwnd
            self.save_config()
            win.destroy()

        tk.Button(win, text="Use Selected Window", command=apply_selected, bg="#107c10", fg="#ffffff", font=("Segoe UI", 9, "bold")).pack(pady=(0, 12))

    def focus_target_window(self):
        if not self.target_window_hwnd:
            return
        try:
            ctypes.windll.user32.ShowWindow(self.target_window_hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(self.target_window_hwnd)
            ctypes.windll.user32.BringWindowToTop(self.target_window_hwnd)
        except Exception:
            pass

    def hide_main_window(self):
        self.root.withdraw()

    def show_main_window(self):
        self.root.deiconify()
        self.root.focus_force()

    def sync_runtime_overlay_from_settings(self):
        if isinstance(self.config.get("skills"), list) and self.config["skills"]:
            source = self.config["skills"][0]
        elif self.skills_ui:
            source = self.skills_ui[0]
        else:
            source = self.config

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        overlay_x = int(source.get("overlay_x", self.config.get("overlay_x", 200)))
        overlay_y = int(source.get("overlay_y", self.config.get("overlay_y", 180)))
        overlay_width = max(200, int(source.get("overlay_width", self.config.get("overlay_width", 900))))
        overlay_height = max(80, int(source.get("overlay_height", self.config.get("overlay_height", 220))))
        clamped = normalize_overlay_box_for_screen(overlay_x, overlay_y, overlay_width, overlay_height, screen_w, screen_h, idx=0)

        overlay_x = clamped["x"]
        overlay_y = clamped["y"]
        overlay_width = clamped["w"]
        overlay_height = clamped["h"]

        font_color = normalize_color(source.get("font_color", self.config.get("font_color", "#ff3333")))
        font_size = normalize_font_size(source.get("font_size", self.config.get("font_size", 28)))
        font_family = source.get("font_family", self.config.get("font_family", "Segoe UI"))
        font_weight = (source.get("font_weight", self.config.get("font_weight", "bold")) or "bold").lower()

        self.config["overlay_x"] = overlay_x
        self.config["overlay_y"] = overlay_y
        self.config["overlay_width"] = overlay_width
        self.config["overlay_height"] = overlay_height
        self.config["font_color"] = font_color
        self.config["font_size"] = font_size
        self.config["font_family"] = font_family
        self.config["font_weight"] = font_weight

        if self.skills_ui:
            for skill in self.skills_ui:
                skill["overlay_x"] = overlay_x
                skill["overlay_y"] = overlay_y
                skill["overlay_width"] = overlay_width
                skill["overlay_height"] = overlay_height
                skill["font_color"] = font_color
                skill["font_size"] = font_size
                skill["font_family"] = font_family
                skill["font_weight"] = font_weight

        if hasattr(self, "overlay"):
            self.update_overlay_geometry()
        if hasattr(self, "alert_label"):
            self.alert_label.config(
                fg=font_color,
                font=build_font_spec(font_family, font_size, font_weight),
                wraplength=max(200, overlay_width - 40),
            )

    def update_overlay_geometry(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = max(200, int(self.config.get("overlay_width", 900)))
        h = max(80, int(self.config.get("overlay_height", 220)))

        x = self.config.get("overlay_x")
        y = self.config.get("overlay_y")
        if x is None or y is None:
            box = get_lower_right_box_for_screen(sw, sh, width=w, height=h, idx=0)
            x = box["x"]
            y = box["y"]
        else:
            box = normalize_overlay_box_for_screen(x, y, w, h, sw, sh, idx=0)
            x = box["x"]
            y = box["y"]

        self.overlay.geometry(f"{w}x{h}+{int(x)}+{int(y)}")
        try:
            self.overlay.attributes("-fullscreen", False)
        except Exception:
            pass

    def populate_skills(self):
        for widget in self.skills_frame.winfo_children():
            widget.destroy()
        self.skills_ui.clear()

        skills = self.config.get("skills", [])
        if not skills:
            skills = DEFAULT_CONFIG["skills"]

        for skill_data in skills:
            self.add_skill_row(skill_data)

    def add_skill_row(self, data=None):
        row_frame = tk.Frame(self.skills_frame, bg="#2b2b2b", padx=12, pady=10, bd=1, relief="flat")
        row_frame.grid(row=(len(self.skills_ui) // 2), column=(len(self.skills_ui) % 2), sticky="nsew", padx=8, pady=8)
        row_frame.grid_columnconfigure(1, weight=1)
        row_frame.grid_columnconfigure(3, weight=1)

        box_data = data.get("box") if data else {"top": 40, "left": 2450, "width": 40, "height": 40}
        reference_dir_var = tk.StringVar(value=data.get("reference_dir", "") if data else "")
        skill_dict = {
            "name_entry": None,
            "box": box_data,
            "text_entry": None,
            "record_hotkey_entry": None,
            "reference_dir_var": reference_dir_var,
            "frame": row_frame,
            "reference_dir": data.get("reference_dir", "") if data else "",
            "overlay_x": int(data.get("overlay_x", self.config.get("overlay_x", 200))) if data else int(self.config.get("overlay_x", 200)),
            "overlay_y": int(data.get("overlay_y", self.config.get("overlay_y", 180))) if data else int(self.config.get("overlay_y", 180)),
            "overlay_width": max(200, int(data.get("overlay_width", self.config.get("overlay_width", 900)))) if data else max(200, int(self.config.get("overlay_width", 900))),
            "overlay_height": max(80, int(data.get("overlay_height", self.config.get("overlay_height", 220)))) if data else max(80, int(self.config.get("overlay_height", 220))),
            "font_color": normalize_color(data.get("font_color", self.config.get("font_color", "#ff3333"))) if data else normalize_color(self.config.get("font_color", "#ff3333")),
            "font_family": data.get("font_family", self.config.get("font_family", "Segoe UI")) if data else self.config.get("font_family", "Segoe UI"),
            "font_weight": (data.get("font_weight", self.config.get("font_weight", "bold")) or "bold").lower() if data else (self.config.get("font_weight", "bold") or "bold").lower(),
            "font_size": normalize_font_size(data.get("font_size", self.config.get("font_size", 28))) if data else normalize_font_size(self.config.get("font_size", 28)),
        }

        tk.Label(row_frame, text="Name", fg="#cfe4ff", bg="#2b2b2b", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        name_entry = tk.Entry(row_frame, width=14, font=("Segoe UI", 9), bg="#1f1f1f", fg="#ffffff", insertbackground="white", bd=1)
        name_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        name_entry.insert(0, data["name"] if data else f"Item {len(self.skills_ui)+1}")
        skill_dict["name_entry"] = name_entry

        tk.Label(row_frame, text="Folder", fg="#cfe4ff", bg="#2b2b2b", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=(6, 0), padx=(0, 8))
        ref_entry = tk.Entry(row_frame, textvariable=reference_dir_var, width=22, font=("Segoe UI", 9), bg="#1f1f1f", fg="#ffffff", insertbackground="white", bd=1)
        ref_entry.grid(row=1, column=1, sticky="ew", pady=(6, 0), padx=(0, 8))
        tk.Button(row_frame, text="…", command=lambda: self.browse_reference_folder(reference_dir_var), bg="#3a3a3a", fg="#ffffff", bd=0, width=3).grid(row=1, column=2, padx=4, pady=(6, 0))

        tk.Label(row_frame, text="Alert", fg="#cfe4ff", bg="#2b2b2b", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=(8, 0), padx=(0, 8))
        text_entry = tk.Entry(row_frame, width=22, font=("Segoe UI", 9), bg="#1f1f1f", fg="#ffffff", insertbackground="white", bd=1)
        text_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(8, 0), padx=(0, 8))
        text_entry.insert(0, data["alert_text"] if data else "⚠️ STATUS MISSING! ⚠️")
        skill_dict["text_entry"] = text_entry

        rec_btn = tk.Button(row_frame, text="Record", command=lambda: self.record_skill_reference(skill_dict), bg="#0a7d4a", fg="#ffffff", font=("Segoe UI", 9), bd=0, padx=8)
        rec_btn.grid(row=3, column=0, sticky="w", pady=(10, 0), padx=(0, 4))
        box_btn = tk.Button(row_frame, text="Region", command=lambda: self.select_box(skill_dict), bg="#0078d4", fg="#ffffff", font=("Segoe UI", 9), bd=0, padx=6)
        box_btn.grid(row=3, column=1, sticky="w", pady=(10, 0), padx=(0, 4))
        del_btn = tk.Button(row_frame, text="Remove", command=lambda: self.remove_skill_row(skill_dict, row_frame), bg="#c42b1c", fg="#ffffff", font=("Segoe UI", 9, "bold"), bd=0, padx=8)
        del_btn.grid(row=3, column=2, sticky="e", pady=(10, 0), padx=(0, 4))

        tk.Label(row_frame, text="Hotkey", fg="#cfe4ff", bg="#2b2b2b", font=("Segoe UI", 9, "bold")).grid(row=4, column=0, sticky="w", pady=(10, 0), padx=(0, 8))
        record_hotkey_var = tk.StringVar(value=(data.get("record_hotkey", DEFAULT_HOTKEY) if data else DEFAULT_HOTKEY))
        record_hotkey_entry = tk.Entry(row_frame, textvariable=record_hotkey_var, width=10, font=("Segoe UI", 9), bg="#1f1f1f", fg="#ffffff", insertbackground="white", bd=1)
        record_hotkey_entry.grid(row=4, column=1, sticky="w", pady=(10, 0), padx=(0, 10))
        skill_dict["record_hotkey_entry"] = record_hotkey_entry

        status_var = tk.StringVar(value="NO")
        status_label = tk.Label(row_frame, textvariable=status_var, fg="#ff4343", bg="#2b2b2b", font=("Segoe UI", 9, "bold"))
        status_label.grid(row=4, column=2, sticky="e", pady=(10, 0), padx=(10, 0))
        skill_dict["status_var"] = status_var
        skill_dict["status_label"] = status_label

        self.skills_ui.append(skill_dict)
        self.save_config()
        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth() + 60, self.root.winfo_reqheight() + 60)

    def remove_skill_row(self, skill_dict, row_frame):
        if len(self.skills_ui) <= 1:
            return
        row_frame.destroy()
        if skill_dict in self.skills_ui:
            self.skills_ui.remove(skill_dict)
        self.save_config()

    def browse_reference_folder(self, ref_var):
        folder = filedialog.askdirectory(title="Select Capture Folder")
        if folder:
            ref_var.set(folder)
            self.save_config()

    def update_skill_status(self, skill_dict, is_active):
        status_var = skill_dict.get("status_var")
        status_label = skill_dict.get("status_label")
        if status_var is None or status_label is None:
            return
        status_var.set("YES" if is_active else "NO")
        status_label.config(fg="#6ccb5f" if is_active else "#ff4343")

    def record_skill_reference(self, skill_dict):
        if not self.target_window_hwnd:
            self.select_target_window()
            if not self.target_window_hwnd:
                return

        def finalize_recording(selected_box, duration, fps):
            if not selected_box or selected_box.get("width", 0) <= 0 or selected_box.get("height", 0) <= 0:
                return

            trigger_key = ""
            if skill_dict.get("record_hotkey_entry") is not None:
                trigger_key = skill_dict["record_hotkey_entry"].get().strip() or DEFAULT_HOTKEY
            else:
                trigger_key = skill_dict.get("record_hotkey", DEFAULT_HOTKEY)

            base_dir = os.path.join(os.getcwd(), "reference_samples")
            os.makedirs(base_dir, exist_ok=True)
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", skill_dict["name_entry"].get().strip() or "item")
            ref_dir = os.path.join(base_dir, safe_name + "_" + str(int(time.time())))
            os.makedirs(ref_dir, exist_ok=True)

            self.focus_target_window()
            time.sleep(0.05)

            try:
                self.keyboard.press_and_release(trigger_key)
            except Exception:
                pass

            interval = 1.0 / max(1, fps)
            frames = []
            unique_frames = []
            start = time.time()
            with self.mss_mod.MSS() as sct:
                while time.time() - start < duration:
                    frame = self.np.array(sct.grab(selected_box))[:, :, :3]
                    frame_path = os.path.join(ref_dir, f"frame_{len(frames):03d}.png")
                    self.cv2.imwrite(frame_path, frame)
                    frames.append(frame_path)

                    if not unique_frames:
                        unique_frames.append(frame)
                    else:
                        previous = unique_frames[-1]
                        diff = self.cv2.norm(frame.astype(self.np.float32), previous.astype(self.np.float32), self.cv2.NORM_L2)
                        if diff > 25.0:
                            unique_frames.append(frame)
                    time.sleep(interval)

            if unique_frames:
                unique_dir = os.path.join(ref_dir, "unique")
                os.makedirs(unique_dir, exist_ok=True)
                for idx, frame in enumerate(unique_frames):
                    self.cv2.imwrite(os.path.join(unique_dir, f"frame_{idx:03d}.png"), frame)
                final_dir = unique_dir
            else:
                final_dir = ref_dir

            skill_dict["box"] = selected_box
            skill_dict["reference_dir"] = final_dir
            if skill_dict.get("reference_dir_var") is not None:
                skill_dict["reference_dir_var"].set(final_dir)
            skill_dict["record_duration_sec"] = duration
            skill_dict["record_fps"] = fps
            if skill_dict.get("record_hotkey_entry") is not None:
                skill_dict["record_hotkey"] = skill_dict["record_hotkey_entry"].get().strip() or DEFAULT_HOTKEY
            self.save_config()

        def pick_region_then_capture():
            def callback(new_box):
                skill_dict["box"] = new_box
                self.save_config()
                CaptureSettingsWindow(
                    self.root,
                    lambda duration, fps: finalize_recording(new_box, duration, fps),
                    default_duration=str(self.config.get("record_duration_sec", 2.0)),
                    default_fps=str(self.config.get("record_fps", 12)),
                )

            RegionSelector(self.root, callback, "Select the active region to record").selector_win.focus_force()

        pick_region_then_capture()

    def select_box(self, skill_dict):
        def callback(new_box):
            skill_dict["box"] = new_box
            skill_dict["overlay_x"] = skill_dict.get("overlay_x", self.config.get("overlay_x", 200))
            skill_dict["overlay_y"] = skill_dict.get("overlay_y", self.config.get("overlay_y", 180))
            skill_dict["overlay_width"] = max(200, int(skill_dict.get("overlay_width", self.config.get("overlay_width", 900))))
            skill_dict["overlay_height"] = max(80, int(skill_dict.get("overlay_height", self.config.get("overlay_height", 220))))
            self.save_config()
        RegionSelector(self.root, callback).selector_win.focus_force()

    def open_text_designer(self, skill_dict=None):
        target = skill_dict if skill_dict is not None else self.config
        TextDesignerWindow(self.root, target, lambda new_cfg: self.on_config_updated(new_cfg, skill_dict))

    def apply_hotkey(self):
        new_key = self.hotkey_var.get().strip() or DEFAULT_HOTKEY
        old_key = self.previous_hotkey
        self.config["hotkey"] = new_key
        self.save_config()
        try:
            self.keyboard.remove_hotkey(old_key)
        except Exception:
            pass
        self.keyboard.add_hotkey(new_key, handle_hotkey)
        self.previous_hotkey = new_key

    def on_config_updated(self, new_cfg, skill_dict=None):
        new_cfg["_designer_dirty"] = True
        if skill_dict is not None:
            skill_dict.update({
                "name": new_cfg.get("name", skill_dict.get("name", "Item")),
                "alert_text": new_cfg.get("alert_text", skill_dict.get("alert_text", "STATUS MISSING")),
                "font_color": normalize_color(new_cfg.get("font_color", skill_dict.get("font_color", "#ff3333"))),
                "font_size": normalize_font_size(new_cfg.get("font_size", skill_dict.get("font_size", 28))),
                "font_family": new_cfg.get("font_family", skill_dict.get("font_family", "Segoe UI")),
                "font_weight": (new_cfg.get("font_weight", skill_dict.get("font_weight", "bold")) or "bold").lower(),
                "overlay_x": int(new_cfg.get("overlay_x", skill_dict.get("overlay_x", 200))),
                "overlay_y": int(new_cfg.get("overlay_y", skill_dict.get("overlay_y", 180))),
                "overlay_width": max(200, int(new_cfg.get("overlay_width", skill_dict.get("overlay_width", 900)))),
                "overlay_height": max(80, int(new_cfg.get("overlay_height", skill_dict.get("overlay_height", 220)))),
            })
            for ui_skill in self.skills_ui:
                if ui_skill is skill_dict or ui_skill.get("name") == skill_dict.get("name"):
                    ui_skill.update(skill_dict)
                    if "text_entry" in ui_skill and hasattr(ui_skill["text_entry"], "delete"):
                        ui_skill["text_entry"].delete(0, tk.END)
                        ui_skill["text_entry"].insert(0, skill_dict.get("alert_text", "STATUS MISSING"))
            self.config["skills"] = [s if s is not skill_dict else skill_dict for s in self.config.get("skills", [])]
            if self.config.get("skills") and skill_dict not in self.config["skills"]:
                self.config["skills"].append(skill_dict)
        else:
            self.config = new_cfg
            self.config["font_color"] = normalize_color(self.config.get("font_color", "#ff3333"))
            self.config["font_size"] = normalize_font_size(self.config.get("font_size", 28))
            self.config["font_family"] = self.config.get("font_family", "Segoe UI")
            self.config["font_weight"] = (self.config.get("font_weight", "bold") or "bold").lower()
            self.config["overlay_width"] = max(200, int(self.config.get("overlay_width", 900)))
            self.config["overlay_height"] = max(80, int(self.config.get("overlay_height", 220)))

        self.sync_runtime_overlay_from_settings()
        self.save_config()

    def toggle_monitoring(self):
        if not self.is_monitoring and not self.target_window_hwnd:
            self.select_target_window()
            if not self.target_window_hwnd:
                return
            self.focus_target_window()

        self.is_monitoring = not self.is_monitoring
        if self.is_monitoring:
            self.focus_target_window()
            self.status_label.config(text="Status: RUNNING", fg="#6ccb5f")
            self.toggle_btn.config(text="Stop Monitoring", bg="#c42b1c")
        else:
            self.status_label.config(text="Status: STOPPED", fg="#ff4343")
            self.toggle_btn.config(text="Start Monitoring", bg="#107c10")
            self.alert_label.config(text="")
            for skill in self.skills_ui:
                status_var = skill.get("status_var")
                if status_var is not None:
                    status_var.set("NO")
                    skill["status_label"].config(fg="#ff4343")
        self.save_config()

    def update_alerts(self, missing_alerts):
        if not self.is_monitoring:
            self.alert_label.config(text="")
            return

        if missing_alerts:
            combined_text = "\n".join(item["text"] for item in missing_alerts)
            first_item = missing_alerts[0]
            try:
                f_size = int(first_item.get("size", self.config.get("font_size", 28)))
            except (TypeError, ValueError):
                f_size = self.config.get("font_size", 28)

            font_family = self.config.get("font_family", "Segoe UI")
            font_weight = self.config.get("font_weight", "bold")
            if first_item.get("font_family"):
                font_family = first_item["font_family"]
            if first_item.get("font_weight"):
                font_weight = first_item["font_weight"]

            overlay_x = int(first_item.get("overlay_x", self.config.get("overlay_x", 200)))
            overlay_y = int(first_item.get("overlay_y", self.config.get("overlay_y", 180)))
            overlay_w = max(200, int(first_item.get("overlay_width", self.config.get("overlay_width", 900))))
            overlay_h = max(80, int(first_item.get("overlay_height", self.config.get("overlay_height", 220))))
            self.overlay.geometry(f"{overlay_w}x{overlay_h}+{overlay_x}+{overlay_y}")
            self.alert_label.config(
                text=combined_text,
                fg=normalize_color(first_item.get("font_color", self.config.get("font_color", "#ff3333"))),
                font=build_font_spec(font_family, normalize_font_size(f_size), font_weight),
                justify="center",
                wraplength=max(200, overlay_w - 40),
            )
        else:
            self.alert_label.config(text="")

    def on_close(self):
        global is_running
        is_running = False
        try:
            self.screen_capture.close()
        except Exception:
            pass
        self.save_config()
        self.root.destroy()


app = None
is_running = True


def handle_hotkey():
    if app is not None and hasattr(app, "root"):
        app.root.after(0, app.toggle_monitoring)


def background_monitor_worker():
    global is_running
    screen = app.screen_capture if app is not None else None
    while is_running:
        if app is None or not app.is_monitoring or screen is None:
            time.sleep(0.2)
            continue

        missing_alerts = []

        for skill in app.skills_ui:
            box = skill["box"]
            if box.get("width", 0) <= 0 or box.get("height", 0) <= 0:
                continue

            reference_templates = []
            reference_dir = skill.get("reference_dir", "")
            if reference_dir and os.path.isdir(reference_dir):
                for file_name in sorted(os.listdir(reference_dir)):
                    if file_name.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                        frame = app.cv2.imread(os.path.join(reference_dir, file_name), app.cv2.IMREAD_COLOR)
                        if frame is not None:
                            reference_templates.append(frame)

            if not reference_templates:
                app.root.after(0, lambda s=skill: app.update_skill_status(s, False))
                continue

            try:
                img_bgra = screen.grab(box)
                img_bgr = app.np.array(img_bgra)[:, :, :3]

                best_match = best_template_match(img_bgr, reference_templates)
                active = best_match >= MATCH_THRESHOLD

                app.root.after(0, lambda s=skill, is_active=active: app.update_skill_status(s, is_active))
                if not active:
                    missing_alerts.append({
                        "text": (skill["text_entry"].get() or skill["name_entry"].get()).strip() or "STATUS MISSING",
                        "size": skill.get("font_size", app.config.get("font_size", 28)),
                        "font_color": skill.get("font_color", app.config.get("font_color", "#ff3333")),
                        "font_family": skill.get("font_family", app.config.get("font_family", "Segoe UI")),
                        "font_weight": skill.get("font_weight", app.config.get("font_weight", "bold")),
                        "overlay_x": skill.get("overlay_x", app.config.get("overlay_x", 200)),
                        "overlay_y": skill.get("overlay_y", app.config.get("overlay_y", 180)),
                        "overlay_width": skill.get("overlay_width", app.config.get("overlay_width", 900)),
                        "overlay_height": skill.get("overlay_height", app.config.get("overlay_height", 220)),
                    })
            except Exception:
                app.root.after(0, lambda s=skill: app.update_skill_status(s, False))
                continue

        app.root.after(0, lambda alerts=missing_alerts: app.update_alerts(alerts))
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    app = VisualMonitorApp()
    is_running = True

    monitor_thread = threading.Thread(target=background_monitor_worker, daemon=True)
    monitor_thread.start()

    hotkey = app.config.get("hotkey", DEFAULT_HOTKEY).strip() or DEFAULT_HOTKEY
    app.hotkey_var.set(hotkey)
    app.previous_hotkey = hotkey
    app.keyboard.add_hotkey(hotkey, handle_hotkey)
    app.config["hotkey"] = hotkey
    app.save_config()

    try:
        app.root.mainloop()
    except KeyboardInterrupt:
        is_running = False
    finally:
        is_running = False
        try:
            app.keyboard.unhook_all()
        except Exception:
            pass
