"""Regression for clipped native UIA peers observed in resource-native-06."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from ui_geometry import resource_control_visible


class ResourceViewportTests(unittest.TestCase):
    def setUp(self):
        self.title = {'y': 129, 'height': 27}
        self.summary = {'y': 353}
        self.item = {'type': 'Text', 'y': 318, 'height': 20,
                     'width': 486, 'isOffscreen': False}

    def visible(self, **changes):
        return resource_control_visible(self.title, self.summary,
                                        {**self.item, **changes})

    def test_captured_light_one_pixel_feedback_is_not_visible(self):
        self.assertFalse(self.visible(y=340, height=1))

    def test_captured_dark_one_pixel_feedback_is_not_visible(self):
        self.assertFalse(resource_control_visible(
            {'y': 181, 'height': 27}, {'y': 405},
            {**self.item, 'y': 392, 'height': 1}))

    def test_complete_line_inside_settings(self):
        self.assertTrue(self.visible())

    def test_line_clips_against_fixed_index_row(self):
        self.assertFalse(self.visible(y=328))

    def test_line_clips_against_title(self):
        self.assertFalse(self.visible(y=150))

    def test_offscreen_or_zero_width(self):
        self.assertFalse(self.visible(isOffscreen=True))
        self.assertFalse(self.visible(width=0))

    def test_button_needs_full_native_height_even_if_enabled(self):
        self.assertFalse(self.visible(type='Button', height=1, isEnabled=True))
        self.assertTrue(self.visible(type='Button', y=300, height=32,
                                     isEnabled=False))

    def test_missing_observed_peer(self):
        self.assertFalse(resource_control_visible(None, self.summary, self.item))
        self.assertFalse(resource_control_visible(self.title, None, self.item))
        self.assertFalse(resource_control_visible(self.title, self.summary, None))


if __name__ == '__main__':
    unittest.main()
