# SPDX-License-Identifier: MIT
"""Regression tests for the studio defaults added in v1.3.22."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import assets
import studio


class IconPresetTest(unittest.TestCase):
    def test_presets_are_20x14_and_shared_with_firmware(self):
        self.assertEqual(set(assets.ICON_PRESETS), {'rice', 'book', 'blank'})
        for rows in assets.ICON_PRESETS.values():
            self.assertEqual(len(rows), 14)
            self.assertTrue(all(len(row) == 20 for row in rows))
            self.assertTrue(all(set(row) <= {'0', '1'} for row in rows))
        self.assertEqual(assets.RICE_ART, assets._rows_to_art(assets.RICE_ROWS))
        self.assertEqual(assets.BOOK_ART, assets._rows_to_art(assets.BOOK_ROWS))
        self.assertTrue(any('#' in row for row in assets.RICE_ART))
        self.assertTrue(any('#' in row for row in assets.BOOK_ART))
        self.assertEqual(assets.BOOK_ROWS[1], '11111111101111111110')
        self.assertIn('大肥鱼', studio.PRESETS)
        self.assertNotIn('深海蓝', studio.PRESETS)
        claude = studio.PRESETS['克劳德']
        self.assertEqual(claude, {'background': '#f9eae2', 'panel': '#fcf5f1',
                                  'shell': '#e29b7b', 'ink': '#6d4831', 'accent': '#da7e55'})

    def test_blank_custom_icon_does_not_reserve_a_large_mask(self):
        theme = assets.load(assets.ROOT / 'profiles/themes.json')['pink']
        saved = assets.ROOT / 'local' / 'left-icon.json'
        backup = saved.read_bytes() if saved.exists() else None
        old_bar = assets._STATUSBAR_OVERRIDE
        try:
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_text(json.dumps({'w': 20, 'h': 14,
                                         'rows': ['0' * 20] * 14}), encoding='utf8')
            assets._STATUSBAR_OVERRIDE = {'left': {'type': 'rice'}}
            layout = assets.status_layout(theme)
            self.assertIsNotNone(layout['rice'])
            self.assertEqual((layout['rice']['w'], layout['rice']['h']), (1, 1))
            self.assertEqual(bytes(layout['rice']['filled']), b'\x00')
        finally:
            assets._STATUSBAR_OVERRIDE = old_bar
            if backup is None:
                saved.unlink(missing_ok=True)
            else:
                saved.write_bytes(backup)


class ThemeResolutionTest(unittest.TestCase):
    def test_legacy_and_empty_theme_ids_fall_back(self):
        self.assertEqual(studio.resolve_theme_id('ocean'), 'pink')
        self.assertEqual(studio.resolve_theme_id(None, ''), 'pink')
        self.assertEqual(studio.resolve_theme_id('mint'), 'mint')


class StaticCharacterValidationTest(unittest.TestCase):
    def test_static_image_without_source_gif_validates(self):
        """Single-frame GIFs skip the sourceGif path; MAX_FRAMES must stay global."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'local' / 'views').mkdir(parents=True)
            (root / 'local' / 'views' / 'pose.png').write_bytes(b'\x89PNG\r\n\x1a\n')
            old = studio.ROOT
            try:
                studio.ROOT = root
                cfg = studio.validate_character({
                    'files': ['local/views/pose.png'], 'sequence': [0],
                    'box': [188, 42, 300, 154], 'frameCount': 1,
                })
            finally:
                studio.ROOT = old
            self.assertEqual(cfg['frameCount'], 1)
            self.assertNotIn('sourceGif', cfg)


class FirmwareSyncTest(unittest.TestCase):
    def test_build_output_is_also_copied_next_to_the_app(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            built = root / 'build' / 'ips'
            built.mkdir(parents=True)
            (built / 'rainy75v2-ips.bin').write_bytes(b'firmware')
            (built / 'manifest.json').write_text('{"target":"ips"}', encoding='utf8')
            out_dir = root / '新编译固件'
            old_root, old_out = studio.ROOT, studio.APP_FIRMWARE_DIR
            try:
                studio.ROOT = root
                studio.APP_FIRMWARE_DIR = out_dir
                copied = studio.sync_firmware_to_app('ips')
                self.assertEqual(studio.FIRMWARE_TARGETS['app'](), out_dir)
            finally:
                studio.ROOT, studio.APP_FIRMWARE_DIR = old_root, old_out
            self.assertEqual(copied, ['rainy75v2-ips.bin', 'rainy75v2-ips.manifest.json'])
            self.assertEqual((out_dir / 'rainy75v2-ips.bin').read_bytes(), b'firmware')
            self.assertEqual(json.loads((out_dir / 'rainy75v2-ips.manifest.json').read_text(encoding='utf8')),
                             {'target': 'ips'})
            # build/ stays intact so the wizard's "latest build" source still works.
            self.assertTrue((built / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
