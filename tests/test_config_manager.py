"""
Tests unitarios para src/utils/config_manager.py
"""

import unittest
import tempfile
from pathlib import Path

from src.utils.config_manager import ConfigManager, AppConfig


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_defaults(self):
        cm = ConfigManager(config_dir=str(self.tmp_dir))
        self.assertEqual(cm.get_volume(), 0.7)
        self.assertEqual(cm.get_theme(), "dark_premium")
        self.assertFalse(cm.get_shuffle())
        self.assertEqual(cm.get_repeat_mode(), 0)
        self.assertFalse(cm.get_auto_play())

    def test_set_get(self):
        cm = ConfigManager(config_dir=str(self.tmp_dir))
        cm.set("theme", "dark_blue")
        self.assertEqual(cm.get("theme"), "dark_blue")
        self.assertIsNone(cm.get("clave_inexistente"))
        self.assertEqual(cm.get("clave_inexistente", "default"), "default")

    def test_set_invalid_key_warns_but_does_not_crash(self):
        cm = ConfigManager(config_dir=str(self.tmp_dir))
        cm.set("no_existe", 123)  # No debe lanzar excepción

    def test_persistence_roundtrip(self):
        cm = ConfigManager(config_dir=str(self.tmp_dir))
        cm.set_volume(0.42)
        cm.set_shuffle(True)
        cm.set_repeat_mode(2)
        cm.set_theme("dark_purple")

        cm2 = ConfigManager(config_dir=str(self.tmp_dir))
        self.assertAlmostEqual(cm2.get_volume(), 0.42)
        self.assertTrue(cm2.get_shuffle())
        self.assertEqual(cm2.get_repeat_mode(), 2)
        self.assertEqual(cm2.get_theme(), "dark_purple")

    def test_volume_clamped(self):
        cm = ConfigManager(config_dir=str(self.tmp_dir))
        cm.set_volume(1.5)
        self.assertEqual(cm.get_volume(), 1.0)
        cm.set_volume(-0.5)
        self.assertEqual(cm.get_volume(), 0.0)

    def test_repeat_mode_clamped(self):
        cm = ConfigManager(config_dir=str(self.tmp_dir))
        cm.set_repeat_mode(99)
        self.assertEqual(cm.get_repeat_mode(), 2)
        cm.set_repeat_mode(-5)
        self.assertEqual(cm.get_repeat_mode(), 0)

    def test_window_geometry(self):
        cm = ConfigManager(config_dir=str(self.tmp_dir))
        cm.set_window_geometry(1024, 768, 50, 60)
        w, h, x, y = cm.get_window_geometry()
        self.assertEqual((w, h, x, y), (1024, 768, 50, 60))

    def test_reset_to_defaults(self):
        cm = ConfigManager(config_dir=str(self.tmp_dir))
        cm.set_volume(0.2)
        cm.reset_to_defaults()
        self.assertEqual(cm.get_volume(), 0.7)

    def test_from_dict_ignores_unknown_keys(self):
        cfg = AppConfig.from_dict({"volume": 0.5, "clave_falsa": True, "theme": "light"})
        self.assertEqual(cfg.volume, 0.5)
        self.assertEqual(cfg.theme, "light")
        self.assertFalse(hasattr(cfg, "clave_falsa"))

    def test_corrupted_config_falls_back_to_defaults(self):
        cfg_file = self.tmp_dir / "musik_config.json"
        cfg_file.write_text("{esto no es json valido", encoding="utf-8")
        cm = ConfigManager(config_dir=str(self.tmp_dir))
        self.assertEqual(cm.get_volume(), 0.7)


if __name__ == "__main__":
    unittest.main()