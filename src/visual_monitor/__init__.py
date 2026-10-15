from .config import (
    CHECK_INTERVAL,
    CONFIG_FILE,
    DEFAULT_CONFIG,
    DEFAULT_HOTKEY,
    DEFAULT_REFERENCE_DIR,
    MATCH_THRESHOLD,
)
from .geometry import (
    build_font_spec,
    clamp_box_to_screen,
    get_centered_box_for_screen,
    get_lower_right_box_for_screen,
    hex_to_rgb,
    normalize_color,
    normalize_font_size,
    normalize_overlay_box_for_screen,
    rgb_to_hex,
)
from .capture import best_template_match
from .app import VisualMonitorApp

__version__ = "v2026.10.15.14.30.00.000"

__all__ = [
    "CHECK_INTERVAL",
    "CONFIG_FILE",
    "DEFAULT_CONFIG",
    "DEFAULT_HOTKEY",
    "DEFAULT_REFERENCE_DIR",
    "MATCH_THRESHOLD",
    "VisualMonitorApp",
    "__version__",
    "best_template_match",
    "build_font_spec",
    "clamp_box_to_screen",
    "get_centered_box_for_screen",
    "get_lower_right_box_for_screen",
    "hex_to_rgb",
    "normalize_color",
    "normalize_font_size",
    "normalize_overlay_box_for_screen",
    "rgb_to_hex",
]
