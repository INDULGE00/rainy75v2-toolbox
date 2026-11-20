# SPDX-License-Identifier: MIT
"""Regression tests for the studio defaults added after v1.3.21."""
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


class FirmwareSyncTest(unittest.TestCase):
    def test_build_output_is_also_copied_next_to_the_app(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            built = root / 'build' / 'ips'
            built.mkdir(parents=True)
            (built / 'rainy75v2-ips.bin').write_bytes(b'firmware')
            (built / 'manifest.json').write_text('{"target":"ips"}', encoding='utf8')
            old_root = studio.ROOT
            try:
                studio.ROOT = root
                copied = studio.sync_firmware_to_app('ips')
            finally:
                studio.ROOT = old_root
            self.assertEqual(copied, ['rainy75v2-ips.bin', 'rainy75v2-ips.manifest.json'])
            self.assertEqual((root / 'rainy75v2-ips.bin').read_bytes(), b'firmware')
            self.assertEqual(json.loads((root / 'rainy75v2-ips.manifest.json').read_text(encoding='utf8')),
                             {'target': 'ips'})
            # build/ stays intact so the wizard's "latest build" source still works.
            self.assertTrue((built / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
