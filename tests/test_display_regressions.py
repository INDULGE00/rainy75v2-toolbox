# SPDX-License-Identifier: MIT
"""Regression tests for the two v1.3.10 display bugs.

1. Connection icons are packed 24 px -> 3 bytes per row; the firmware used to
   read them as one 32-bit word per row, dropping 2/3 of each icon.
2. A full-screen capture baked into S1 produced a second nested UI. The studio
   must refuse such images instead of merely warning.
"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import assets
from PIL import Image, ImageDraw


class IconPackingTest(unittest.TestCase):
    def test_each_icon_row_is_three_bytes_msb_first(self):
        for art, packed in zip((assets.USB_ART, assets.RF_ART, assets.BT_ART), assets.ICONS):
            self.assertEqual(len(art), 14)
            self.assertTrue(all(len(row) == 24 for row in art))
            self.assertEqual(len(packed), 14 * 3)
            for y, row in enumerate(art):
                for x, cell in enumerate(row):
                    byte = packed[y * 3 + (x >> 3)]
                    bit = bool(byte & (128 >> (x & 7)))
                    self.assertEqual(bit, cell == '#', f'row={y} x={x}')
        # A 32-bit-per-row read (the broken firmware) cannot reproduce the art:
        # it would only see the first 14 of the 42 bytes.
        broken = {(y, x) for y in range(14) for x in range(24)
                  if assets.ICONS[0][y] & (1 << (23 - x))}
        real = {(y, x) for y in range(14) for x in range(24)
                if assets.USB_ART[y][x] == '#'}
        self.assertNotEqual(broken, real)


class ScreenshotDetectionTest(unittest.TestCase):
    @staticmethod
    def _gif(draw, size):
        im = Image.new('RGB', size, '#eef4ff')
        d = ImageDraw.Draw(im)
        draw(d)
        buf = io.BytesIO()
        im.save(buf, format='GIF')
        return buf.getvalue()

    def test_screen_shaped_ui_capture_is_rejected(self):
        from studio import looks_like_ui_capture
        def ui(d):
            # The rounded key-card border that every screen UI has.
            d.rounded_rectangle((10, 20, 180, 150), radius=12, outline='#22418c', width=3)
        capture = self._gif(ui, (904, 483))
        hit, why = looks_like_ui_capture(capture)
        self.assertTrue(hit, why)

    def test_portrait_character_is_accepted(self):
        from studio import looks_like_ui_capture
        def character(d):
            d.ellipse((60, 40, 250, 380), fill='#4466aa')
        clean = self._gif(character, (317, 409))
        hit, why = looks_like_ui_capture(clean)
        self.assertFalse(hit, why)


if __name__ == '__main__':
    unittest.main()


class KeyCountWidgetTest(unittest.TestCase):
    def test_key_widget_icon_is_12x10_and_kind6(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from assets import STATUS_WIDGETS, _sym_keys
        self.assertEqual(STATUS_WIDGETS['keys'], (12, 10, 29, 7, 6))  # 5 digits
        self.assertEqual(_sym_keys().size, (12, 10))

    def test_live_icon_spec_roundtrip(self):
        from studio import preview_icon
        icon = preview_icon('3x2:f00f')
        self.assertEqual(icon.size, (3, 2))
        self.assertEqual([icon.getpixel((x, y)) for y in range(2) for x in range(3)],
                         [1, 1, 1, 1, 0, 0])
        self.assertIsNone(preview_icon('bad-spec'))


class LeftSlotBandTest(unittest.TestCase):
    def test_time_and_text_stay_inside_repaint_band(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from assets import status_layout, load, STATUS_BAND_Y, STATUS_BAND_H, ROOT
        theme = load(ROOT / 'profiles/themes.json')['pink']
        orig = (ROOT / 'profiles/statusbar.json').read_text(encoding='utf8')
        try:
            for kind in ('time', 'rice'):
                cfg = {'left': {'type': kind, 'text': '南柯一梦'},
                       'right': ['conn', 'caps', 'battery']}
                (ROOT / 'profiles/statusbar.json').write_text(
                    json.dumps(cfg, ensure_ascii=False), encoding='utf8')
                lay = status_layout(theme)
                x, y, w, h = lay['regions'][1]
                self.assertEqual(y, STATUS_BAND_Y, kind)
                self.assertLessEqual(y + h, STATUS_BAND_Y + STATUS_BAND_H, kind)
        finally:
            (ROOT / 'profiles/statusbar.json').write_text(orig, encoding='utf8')


class HeaderCompletenessTest(unittest.TestCase):
    def test_icon_mode_emits_array_others_omit_it(self):
        """draw_rice() is compiled only for the icon mode, so time/text builds
        must not carry its table (that headroom is what fits custom text)."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from assets import headers, load, ROOT
        theme = load(ROOT / 'profiles/themes.json')['pink']
        keys = load(ROOT / 'profiles/keys.json')
        orig = (ROOT / 'profiles/statusbar.json').read_text(encoding='utf8')
        try:
            for kind in ('time', 'text', 'rice'):
                cfg = {'left': {'type': kind, 'text': '南柯一梦'},
                       'right': ['conn', 'caps', 'battery']}
                (ROOT / 'profiles/statusbar.json').write_text(
                    json.dumps(cfg, ensure_ascii=False), encoding='utf8')
                with tempfile.TemporaryDirectory() as d:
                    headers(keys, theme, Path(d))
                    src = (Path(d) / 'ui_assets.h').read_text(encoding='utf8')
                    if kind == 'rice':
                        self.assertIn('left_icon_filled[]', src)
                    else:
                        self.assertNotIn('left_icon_filled[]', src, kind)
        finally:
            (ROOT / 'profiles/statusbar.json').write_text(orig, encoding='utf8')

    def test_custom_text_is_baked_into_background(self):
        """Custom text lives in the S1 image, so it must not add a mask region."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from assets import status_layout, load, ROOT
        theme = load(ROOT / 'profiles/themes.json')['pink']
        orig = (ROOT / 'profiles/statusbar.json').read_text(encoding='utf8')
        try:
            (ROOT / 'profiles/statusbar.json').write_text(
                json.dumps({'left': {'type': 'text', 'text': 'Hi 南柯?'},
                            'right': ['conn', 'caps', 'battery']}, ensure_ascii=False),
                encoding='utf8')
            lay = status_layout(theme)
            # key region + conn + caps + battery icon/value = 5; nothing static
            self.assertEqual(len(lay['regions']), 5)
            self.assertEqual(lay['static'], {})
        finally:
            (ROOT / 'profiles/statusbar.json').write_text(orig, encoding='utf8')


class PixelEditorTest(unittest.TestCase):
    def test_default_icon_fits_editor_limit(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from assets import left_icon
        w, h = left_icon().size
        self.assertLessEqual(w, 20)
        self.assertLessEqual(h, 14)

    def test_tight_crop_removes_empty_margins(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from assets import tight_icon
        from PIL import Image, ImageDraw
        im = Image.new('1', (20, 14), 0)
        ImageDraw.Draw(im).rectangle((5, 4, 10, 8), fill=1)
        self.assertEqual(tight_icon(im).size, (6, 5))

    def test_icon_colour_defaults_to_theme_ink(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from assets import left_icon_color
        self.assertEqual(left_icon_color({'ink': '#112233'}), '#112233')
