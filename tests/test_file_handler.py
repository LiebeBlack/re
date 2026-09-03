"""
Tests unitarios para src/utils/file_handler.py
"""

import unittest
import tempfile
from pathlib import Path

from src.utils.file_handler import FileHandler


class TestFileHandler(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_file(self, name, content=b"data"):
        path = self.tmp_dir / name
        path.write_bytes(content)
        return str(path)

    def test_is_audio_file_supported_formats(self):
        for ext in (".mp3", ".wav", ".ogg", ".flac", ".MP3", ".Wav"):
            self.assertTrue(FileHandler.is_audio_file(f"cancion{ext}"))

    def test_is_audio_file_unsupported(self):
        self.assertFalse(FileHandler.is_audio_file("nota.txt"))
        self.assertFalse(FileHandler.is_audio_file("imagen.png"))

    def test_is_audio_file_invalid_input(self):
        self.assertFalse(FileHandler.is_audio_file(""))
        self.assertFalse(FileHandler.is_audio_file(None))
        self.assertFalse(FileHandler.is_audio_file(123))

    def test_get_audio_files_filters(self):
        self._make_file("a.mp3")
        self._make_file("b.flac")
        self._make_file("c.wav")
        self._make_file("nota.txt")
        self._make_file("imagen.png")

        files = FileHandler.get_audio_files(str(self.tmp_dir))
        self.assertEqual(len(files), 3)
        self.assertTrue(all(f.endswith((".mp3", ".flac", ".wav")) for f in files))

    def test_get_audio_files_invalid_dir(self):
        self.assertEqual(FileHandler.get_audio_files(str(self.tmp_dir / "no_existe")), [])
        self.assertEqual(FileHandler.get_audio_files(""), [])
        self.assertEqual(FileHandler.get_audio_files(None), [])

    def test_get_audio_files_ignores_directories(self):
        (self.tmp_dir / "subdir").mkdir()
        (self.tmp_dir / "subdir" / "inner.mp3").write_bytes(b"x")
        self._make_file("outer.mp3")
        files = FileHandler.get_audio_files(str(self.tmp_dir))
        self.assertEqual(len(files), 1)

    def test_get_file_name(self):
        self.assertEqual(FileHandler.get_file_name("/a/b/cancion.mp3"), "cancion")

    def test_get_file_extension(self):
        self.assertEqual(FileHandler.get_file_extension("/a/b/cancion.MP3"), ".mp3")

    def test_file_exists(self):
        path = self._make_file("exists.mp3")
        self.assertTrue(FileHandler.file_exists(path))
        self.assertFalse(FileHandler.file_exists(str(self.tmp_dir / "no.mp3")))

    def test_get_file_size(self):
        path = self._make_file("size.mp3", b"0123456789")
        self.assertEqual(FileHandler.get_file_size(path), 10)
        self.assertEqual(FileHandler.get_file_size(str(self.tmp_dir / "no.mp3")), 0)

    def test_ensure_directory(self):
        new_dir = self.tmp_dir / "nuevo" / "sub"
        FileHandler.ensure_directory(str(new_dir))
        self.assertTrue(new_dir.exists())


if __name__ == "__main__":
    unittest.main()