import unittest

import visual_monitor


class TestGenericVisualMonitor(unittest.TestCase):
    def test_hex_to_rgb_round_trip(self):
        self.assertEqual(visual_monitor.hex_to_rgb("#ff3333"), (255, 51, 51))
        self.assertEqual(visual_monitor.rgb_to_hex((255, 51, 51)), "#ff3333")

    def test_font_spec_builds_weighted_font(self):
        spec = visual_monitor.build_font_spec("Segoe UI", 36, "bold")
        self.assertEqual(spec[0], "Segoe UI")
        self.assertEqual(spec[1], 36)
        self.assertEqual(spec[2], "bold")

    def test_default_config_is_generic(self):
        self.assertIn("skills", visual_monitor.DEFAULT_CONFIG)
        self.assertNotIn("Maple", str(visual_monitor.DEFAULT_CONFIG))
        self.assertNotIn("buff", str(visual_monitor.DEFAULT_CONFIG).lower())

    def test_stale_screen_coordinates_fall_back_to_lower_right_box(self):
        box = visual_monitor.normalize_overlay_box_for_screen(5000, -100, 300, 120, 1920, 1080, idx=0)
        self.assertEqual(box["x"], 1590)
        self.assertEqual(box["y"], 930)
        self.assertEqual(box["w"], 300)
        self.assertEqual(box["h"], 120)


if __name__ == "__main__":
    unittest.main()
