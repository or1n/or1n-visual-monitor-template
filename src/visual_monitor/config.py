DEFAULT_HOTKEY = "f12"
CHECK_INTERVAL = 0.1
MATCH_THRESHOLD = 0.82
CONFIG_FILE = "config.json"
DEFAULT_REFERENCE_DIR = "reference_samples"

DEFAULT_CONFIG = {
    "hotkey": DEFAULT_HOTKEY,
    "target_window_title": "",
    "target_window_hwnd": None,
    "overlay_x": None,
    "overlay_y": None,
    "overlay_width": 900,
    "overlay_height": 220,
    "font_family": "Segoe UI",
    "font_weight": "bold",
    "font_color": "#ff3333",
    "font_size": 28,
    "record_duration_sec": 2.0,
    "record_fps": 12,
    "skills": [
        {
            "name": "Status 1",
            "reference_dir": "",
            "box": {"top": 40, "left": 2450, "width": 40, "height": 40},
            "alert_text": "⚠️ STATUS MISSING! ⚠️",
            "font_size": 28,
            "record_hotkey": DEFAULT_HOTKEY,
        }
    ],
}
