"""
Tests unitarios para src/utils/metadata_extractor.py
"""

import unittest
import tempfile
from pathlib import Path

from src.utils.metadata_extractor import MetadataExtractor


class TestMetadataExtractor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_basic_fallback_for_unknown_content(self):
        """Un archivo sin metadatos válidos debe usar el nombre de archivo como título"""
        path = self.tmp_dir / "mi_cancion.mp3"
        path.write_bytes(b"no es audio real")

        metadata = MetadataExtractor.extract_metadata(str(path))
        self.assertEqual(metadata["title"], "mi_cancion")
        self.assertEqual(metadata["artist"], "Unknown")
        self.assertEqual(metadata["album"], "")
        self.assertIn("duration", metadata)  # La clave existe (puede ser None)

    def test_missing_file_does_not_crash(self):
        metadata = MetadataExtractor.extract_metadata(str(self.tmp_dir / "no_existe.mp3"))
        # Debe devolver algo utilizable (normalizado), sin excepción
        self.assertTrue(metadata["title"])

    def test_get_duration_missing_file(self):
        duration = MetadataExtractor.get_duration(str(self.tmp_dir / "no_existe.mp3"))
        self.assertIsNone(duration)

    def test_metadata_keys_present(self):
        path = self.tmp_dir / "x.flac"
        path.write_bytes(b"datos")
        metadata = MetadataExtractor.extract_metadata(str(path))
        for key in ("title", "artist", "album", "duration", "year", "genre"):
            self.assertIn(key, metadata)


if __name__ == "__main__":
    unittest.main()