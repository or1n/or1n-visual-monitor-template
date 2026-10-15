# or1n-visual-monitor-template

Status: Active template / public-ready starting point

Quick thing: a reusable screen-monitoring and overlay toolkit for visual state checks, alerting, and hotkey-driven automation.

## Short description

This project started as a targeted visual alert helper but has been generalized into a professional template for other screen-based monitoring workflows. The code is organized so the capture logic, overlay rendering, and hotkey controls stay isolated from the UI and can be reused for different products, tools, and monitoring tasks without rewriting the core behavior.

## Features

### Current features
- Window-aware screen capture and reference-image matching
- Hotkey-driven monitoring toggles
- Overlay alert text and layout controls
- Per-skill or per-check configuration entries
- Screen-safe fallback placement for overlays
- Config persistence through JSON files
- Light modular structure with UI separated from matching logic

### Not yet implemented
- YAML configuration export/import
- Advanced fuzzy matching and heuristics for complex visual detection
- Full plugin architecture for custom alert actions

## Requirements

- Python 3.10+
- Windows desktop environment for the current hotkey and screen capture implementation
- `numpy`
- `opencv-python`
- `mss`
- `keyboard`

## Installation and workflow

1. Clone this repository.
2. Create a virtual environment.
3. Install the package in editable mode:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .
```

4. Copy the example config if needed and edit your local runtime values.
5. Launch the app:

```bash
python -m visual_monitor
```

## Usage

This repository is meant to be a template for public-facing automation tools. You can use it as-is for visual checks, or adjust the configuration to match other launch windows and monitoring rules. The main focus is keeping the UI independent from the detection and overlay engine so you can redesign the interface without breaking the automation flow.

## Building from the command line

```bash
python -m pip install -e .
python -m unittest
```

## Versioning

This project uses timestamp-based versioning for simplicity and reproducibility:

Format: v{YYYY}.{MM}.{DD}.{HH}.{mm}.{ss}.{fff}

Example:

```text
v2026.10.15.14.30.00.000
```

## Example

```python
from visual_monitor import normalize_color, normalize_overlay_box_for_screen

box = normalize_overlay_box_for_screen(5000, -100, 300, 120, 1920, 1080, idx=0)
print(box)
```

## Benefits

- Reusable beyond a single game or niche workflow
- Keeps runtime capture logic separate from UI code
- Easier to open source, share, and extend
- Suitable for public repository templates and not just personal scripts
- More maintainable and easier to test

## Current version

v2026.10.15.14.30.00.000

## Accessibility

The interface aims to remain readable and adjustable for accessibility-minded users, with high-contrast defaults, configurable text sizes, and predictable overlay positioning. Additional UI theme and color customization can be added without changing the underlying detection engine.

## License

This project is licensed under the MIT License.

---

Repository name pattern: `or1n-*` with hyphenated, public-friendly names.
