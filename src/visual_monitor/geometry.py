def normalize_color(value):
    if value is None:
        return "#ff3333"
    color = str(value).strip()
    if not color:
        return "#ff3333"
    if not color.startswith("#"):
        color = f"#{color}"
    if len(color) == 4:
        color = "#" + "".join(ch * 2 for ch in color[1:])
    if len(color) != 7:
        return "#ff3333"
    return color.lower()


def hex_to_rgb(value):
    color = normalize_color(value)
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def rgb_to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, int(channel))):02x}" for channel in rgb)


def normalize_font_size(value, minimum=10, maximum=96):
    try:
        size = int(float(value))
    except (TypeError, ValueError):
        size = 28
    return max(minimum, min(maximum, size))


def build_font_spec(font_family, font_size, font_weight="bold"):
    family = str(font_family or "Segoe UI").strip() or "Segoe UI"
    size = normalize_font_size(font_size)
    weight = str(font_weight or "bold").strip().lower() or "bold"
    if weight in {"heavy", "demibold"}:
        weight = "bold"
    return (family, size, weight)


def get_centered_box_for_screen(screen_width, screen_height, width=420, height=120, idx=0):
    width = max(180, int(width))
    height = max(60, int(height))
    max_x = max(30, int(screen_width) - width - 30)
    max_y = max(30, int(screen_height) - height - 30)
    x = max(30, min(max_x, (int(screen_width) - width) // 2))
    y = max(30, min(max_y, (int(screen_height) - height) // 2 + (idx * 24)))
    return {"x": x, "y": y, "w": width, "h": height}


def get_lower_right_box_for_screen(screen_width, screen_height, width=420, height=120, idx=0, margin=30):
    width = max(180, int(width))
    height = max(60, int(height))
    screen_w = max(1, int(screen_width))
    screen_h = max(1, int(screen_height))
    x = max(margin, screen_w - width - margin)
    y = max(margin, screen_h - height - margin - (idx * 18))
    return {"x": x, "y": y, "w": width, "h": height}


def clamp_box_to_screen(x, y, width, height, screen_width, screen_height, margin=30):
    width = max(180, int(width))
    height = max(60, int(height))
    max_x = max(margin, int(screen_width) - width - margin)
    max_y = max(margin, int(screen_height) - height - margin)
    x = max(margin, min(int(x), max_x))
    y = max(margin, min(int(y), max_y))
    return {"x": x, "y": y, "w": width, "h": height}


def normalize_overlay_box_for_screen(x, y, width, height, screen_width, screen_height, idx=0, margin=30):
    """Use the lower-right safe area when saved overlay coordinates are stale or off-screen."""
    width = max(180, int(width))
    height = max(60, int(height))
    screen_w = max(1, int(screen_width))
    screen_h = max(1, int(screen_height))

    try:
        x_val = int(x) if x is not None else None
        y_val = int(y) if y is not None else None
    except (TypeError, ValueError):
        x_val = None
        y_val = None

    if x_val is None or y_val is None:
        return get_lower_right_box_for_screen(screen_w, screen_h, width=width, height=height, idx=idx, margin=margin)

    stale_outside_screen = (
        x_val < -margin or y_val < -margin or x_val > screen_w + margin or y_val > screen_h + margin
    )
    if stale_outside_screen:
        return get_lower_right_box_for_screen(screen_w, screen_h, width=width, height=height, idx=idx, margin=margin)

    return clamp_box_to_screen(x_val, y_val, width, height, screen_w, screen_h, margin=margin)
