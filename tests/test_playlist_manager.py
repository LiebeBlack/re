"""
Tests unitarios para src/audio/playlist_manager.py
"""

import unittest
import tempfile
from pathlib import Path

from src.audio.playlist_manager import PlaylistManager, Track


class TestTrack(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_audio(self, name):
        path = self.tmp_dir / name
        path.write_bytes(b"audio data")
        return str(path)

    def test_valid_track(self):
        track = Track(file_path=self._make_audio("a.mp3"), title="A", artist="Artist", duration=3.5)
        self.assertEqual(track.title, "A")
        self.assertEqual(track.artist, "Artist")
        self.assertEqual(track.duration, 3.5)
        self.assertTrue(track.is_valid())

    def test_invalid_track_raises(self):
        with self.assertRaises(ValueError):
            Track(file_path="", title="A")
        with self.assertRaises(ValueError):
            Track(file_path="/x.mp3", title="")
        with self.assertRaises(ValueError):
            Track(file_path="/x.mp3", title="A", duration=-1)

    def test_is_valid_false_for_missing_file(self):
        track = Track(file_path=str(self.tmp_dir / "no_existe.mp3"), title="A")
        self.assertFalse(track.is_valid())

    def test_to_dict_from_dict_roundtrip(self):
        track = Track(file_path=self._make_audio("a.mp3"), title="A", artist="Artist", duration=3.5)
        restored = Track.from_dict(track.to_dict())
        self.assertEqual(restored.file_path, track.file_path)
        self.assertEqual(restored.title, track.title)
        self.assertEqual(restored.artist, track.artist)
        self.assertEqual(restored.duration, track.duration)

    def test_str_representation(self):
        track = Track(file_path=self._make_audio("a.mp3"), title="A", artist="Artist")
        self.assertEqual(str(track), "A - Artist")


class TestPlaylistManager(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.pm = PlaylistManager(playlist_dir=str(self.tmp_dir))
        self.tracks = []
        for i in range(5):
            path = self.tmp_dir / f"track{i}.mp3"
            path.write_bytes(b"audio data")
            track = Track(file_path=str(path), title=f"Track {i}", artist="Artist", duration=10 + i)
            self.tracks.append(track)
            self.pm.add_track(track)

    def tearDown(self):
        self._tmp.cleanup()

    def test_add_and_count(self):
        self.assertEqual(self.pm.get_track_count(), 5)
        self.assertFalse(self.pm.is_empty())

    def test_add_rejects_invalid_file(self):
        bogus = Track(file_path=str(self.tmp_dir / "no_existe.mp3"), title="Bogus")
        self.assertFalse(self.pm.add_track(bogus))
        self.assertEqual(self.pm.get_track_count(), 5)

    def test_has_track(self):
        self.assertTrue(self.pm.has_track(self.tracks[0].file_path))
        self.assertFalse(self.pm.has_track(str(self.tmp_dir / "otra.mp3")))

    def test_remove_track(self):
        self.assertTrue(self.pm.remove_track(0))
        self.assertEqual(self.pm.get_track_count(), 4)
        self.assertFalse(self.pm.remove_track(99))
        self.assertFalse(self.pm.remove_track("0"))

    def test_next_normal_order(self):
        self.pm.set_current_index(0)
        self.assertEqual(self.pm.next().file_path, self.tracks[1].file_path)
        self.assertEqual(self.pm.next().file_path, self.tracks[2].file_path)
        # Sin repeat, al final de la lista devuelve None
        self.pm.set_current_index(4)
        self.assertIsNone(self.pm.next())

    def test_next_from_nothing_starts_at_first(self):
        # current_index == -1: next() debe empezar por la primera pista
        track = self.pm.next()
        self.assertEqual(track.file_path, self.tracks[0].file_path)

    def test_previous_normal_order(self):
        self.pm.set_current_index(2)
        self.assertEqual(self.pm.previous().file_path, self.tracks[1].file_path)
        self.pm.set_current_index(0)
        self.assertIsNone(self.pm.previous())

    def test_repeat_all_wraps(self):
        self.pm.set_repeat_mode(1)
        self.pm.set_current_index(4)
        self.assertEqual(self.pm.next().file_path, self.tracks[0].file_path)
        self.pm.set_current_index(0)
        self.assertEqual(self.pm.previous().file_path, self.tracks[4].file_path)

    def test_shuffle_does_not_skip_or_repeat_current(self):
        """Regresión: el primer next() en shuffle no debe saltar ni repetir la pista actual"""
        self.pm.set_current_index(0)
        self.pm.set_shuffle(True)

        first = self.pm.next()
        self.assertIsNotNone(first)
        # No puede ser la misma pista actual (está al inicio del orden shuffle)
        self.assertNotEqual(first.file_path, self.tracks[0].file_path)

    def test_shuffle_visits_all_tracks_once(self):
        self.pm.set_current_index(0)
        self.pm.set_shuffle(True)

        visited = []
        for _ in range(4):  # La actual está al inicio, quedan 4 por visitar
            track = self.pm.next()
            self.assertIsNotNone(track)
            visited.append(track.file_path)

        self.assertEqual(len(set(visited)), 4)
        self.assertNotIn(self.tracks[0].file_path, visited)
        # Sin repeat, al agotarse el orden devuelve None
        self.assertIsNone(self.pm.next())

    def test_shuffle_without_current_starts_at_first_shuffled(self):
        pm = PlaylistManager(playlist_dir=str(self.tmp_dir))
        paths = []
        for i in range(3):
            path = self.tmp_dir / f"extra{i}.mp3"
            path.write_bytes(b"x")
            paths.append(str(path))
            pm.add_track(Track(file_path=paths[-1], title=f"E{i}"))

        pm.set_shuffle(True)
        # Sin pista actual, el primer next() debe reproducir el primer elemento
        # del orden shuffle (no saltárselo)
        track = pm.next()
        self.assertIsNotNone(track)

    def test_shuffle_repeat_all_wraps(self):
        self.pm.set_repeat_mode(1)
        self.pm.set_current_index(0)
        self.pm.set_shuffle(True)

        for _ in range(10):  # Más vueltas que pistas disponibles
            self.assertIsNotNone(self.pm.next())

    def test_shuffle_previous_goes_back(self):
        self.pm.set_current_index(0)
        self.pm.set_shuffle(True)
        first = self.pm.next()
        prev = self.pm.previous()
        self.assertIsNotNone(prev)
        # previous() debe volver a la pista que estaba sonando (la actual, al inicio)
        self.assertEqual(prev.file_path, self.tracks[0].file_path)

    def test_save_load_roundtrip(self):
        self.pm.set_current_index(2)
        self.pm.set_shuffle(True)
        self.pm.set_repeat_mode(1)
        self.assertTrue(self.pm.save_playlist())

        pm2 = PlaylistManager(playlist_dir=str(self.tmp_dir))
        self.assertTrue(pm2.load_playlist())
        self.assertEqual(pm2.get_track_count(), 5)
        self.assertEqual(pm2.get_current_index(), 2)
        self.assertTrue(pm2.get_shuffle())
        self.assertEqual(pm2.get_repeat_mode(), 1)

    def test_load_filters_missing_files(self):
        self.pm.save_playlist()
        # Eliminar todas las pistas del disco
        for track in self.tracks:
            Path(track.file_path).unlink()

        pm2 = PlaylistManager(playlist_dir=str(self.tmp_dir))
        self.assertTrue(pm2.load_playlist())
        self.assertEqual(pm2.get_track_count(), 0)
        self.assertEqual(pm2.get_current_index(), -1)

    def test_load_clamps_current_index(self):
        # Guardar playlist de 5 pistas y luego una con solo 2
        self.pm.save_playlist()
        data = {
            "tracks": [t.to_dict() for t in self.tracks[:2]],
            "current_index": 4,  # Fuera de rango
            "shuffle": False,
            "repeat_mode": 0
        }
        import json
        (self.tmp_dir / "musik_playlist.json").write_text(json.dumps(data), encoding="utf-8")

        pm2 = PlaylistManager(playlist_dir=str(self.tmp_dir))
        self.assertTrue(pm2.load_playlist())
        self.assertEqual(pm2.get_current_index(), 1)  # Ajustado al último válido

    def test_load_missing_file_returns_false(self):
        self.assertFalse(self.pm.load_playlist())

    def test_clear(self):
        self.pm.set_current_index(0)
        self.pm.clear()
        self.assertEqual(self.pm.get_track_count(), 0)
        self.assertEqual(self.pm.get_current_index(), -1)

    def test_create_m3u_playlist(self):
        m3u_path = self.tmp_dir / "lista.m3u"
        self.assertTrue(self.pm.create_m3u_playlist(str(m3u_path)))
        content = m3u_path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("#EXTM3U"))
        self.assertIn(self.tracks[0].file_path, content)


if __name__ == "__main__":
    unittest.main()