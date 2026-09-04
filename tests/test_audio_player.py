"""
Tests funcionales para src/audio/player.py y regresiones de la playlist.

Genera WAVs pequeños (sine) y verifica comportamiento real de pygame:
  * Seek con posición correcta (offset de get_pos()).
  * Detección de fin de pista (por duración y por get_busy()).
  * replay() para Repeat One.
  * Pausa/reanudación y volumen.
  * Shuffle tras agregar/remover pistas (sin IndexError).
"""

import math
import os
import struct
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path

# Usar driver de audio "dummy" si no hay dispositivo de audio (CI/headless)
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from src.audio.player import AudioPlayer, PlayerState
from src.audio.playlist_manager import PlaylistManager, Track


def make_wav(path: Path, seconds: float = 1.0, frequency: int = 440, rate: int = 44100) -> None:
    """Genera un WAV mono de N segundos con un tono senoidal."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            v = int(20000 * math.sin(2 * math.pi * frequency * i / rate))
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))


class TestAudioPlayer(unittest.TestCase):
    """Pruebas funcionales del motor de audio (con WAV reales)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp_dir = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._player = AudioPlayer()

    def tearDown(self):
        try:
            self._player.cleanup()
        except Exception:
            pass

    def _load(self, seconds: float = 2.0, hint: bool = True) -> str:
        path = self.tmp_dir / f"tone_{int(time.time() * 1000)}.wav"
        make_wav(path, seconds=seconds)
        duration_hint = seconds if hint else None
        self.assertTrue(self._player.load(str(path), duration_hint=duration_hint))
        return str(path)

    # ------------------------------------------------------------------

    def test_load_sets_duration_from_hint(self):
        """La duración debe tomarse del hint de metadatos."""
        self._load(seconds=3.0, hint=True)
        self.assertAlmostEqual(self._player.get_duration(), 3.0, delta=0.2)

    def test_load_estimates_duration_without_hint(self):
        """Sin hint, la duración debe estimarse (mutagen) y ser > 0."""
        self._load(seconds=2.5, hint=False)
        self.assertGreater(self._player.get_duration(), 2.0)

    def test_load_rejects_missing_file(self):
        self.assertFalse(self._player.load(str(self.tmp_dir / "no_existe.wav")))

    def test_play_and_state(self):
        self._load()
        self.assertTrue(self._player.play())
        self.assertEqual(self._player.get_state(), PlayerState.PLAYING)
        time.sleep(0.4)
        self.assertGreater(self._player.get_position(), 0.2)
        self.assertTrue(self._player.pause())
        self.assertEqual(self._player.get_state(), PlayerState.PAUSED)
        self.assertTrue(self._player.resume())
        self.assertEqual(self._player.get_state(), PlayerState.PLAYING)

    def test_seek_position_includes_offset(self):
        """Regresión: tras seek, la posición debe reflejar el offset real.

        pygame.mixer.music.get_pos() cuenta desde 0 después de
        play(start=...); el reproductor debe sumar la base del seek.
        """
        self._load(seconds=5.0)
        self._player.play()
        time.sleep(0.3)

        self.assertTrue(self._player.seek(2.0))
        time.sleep(0.5)

        # Debe estar cerca de 2.0 + 0.5 (no saltar de vuelta a ~0.5)
        pos = self._player.get_position()
        self.assertGreaterEqual(pos, 2.0, f"Posición tras seek incorrecta: {pos:.2f}")
        self.assertLess(pos, 3.0, f"Posición tras seek demasiado alta: {pos:.2f}")

    def test_seek_while_paused_stays_paused(self):
        self._load(seconds=4.0)
        self._player.play()
        time.sleep(0.2)
        self._player.pause()
        self.assertTrue(self._player.seek(1.0))
        self.assertEqual(self._player.get_state(), PlayerState.PAUSED)
        self.assertAlmostEqual(self._player.get_position(), 1.0, delta=0.1)

    def test_track_end_detected(self):
        """Al terminar la pista debe dispararse el callback de fin."""
        self._load(seconds=0.5)
        ended = threading.Event()

        def _on_end():
            ended.set()

        self._player.set_track_end_callback(_on_end)
        self._player.play()
        self.assertTrue(ended.wait(timeout=4.0), "El callback de fin no se disparó")

    def test_track_end_detected_without_duration(self):
        """Fin detectado por get_busy() aunque la duración sea desconocida."""
        self._load(seconds=0.6, hint=False)
        ended = threading.Event()

        def _on_end():
            ended.set()

        self._player.set_track_end_callback(_on_end)
        self._player.play()
        self.assertTrue(ended.wait(timeout=4.0), "El fin por get_busy() no se detectó")

    def test_track_end_not_fired_during_seek(self):
        """Un seek (stop + play) no debe disparar el fin de pista."""
        self._load(seconds=6.0)
        fired = []

        def _on_end():
            fired.append(True)

        self._player.set_track_end_callback(_on_end)
        self._player.play()
        time.sleep(0.3)
        for target in (1.0, 2.0, 3.0, 4.0):
            self._player.seek(target)
            time.sleep(0.25)
        self.assertEqual(fired, [], "El seek disparó el fin de pista por error")

    def test_replay_restarts_track(self):
        """replay() debe reiniciar la pista desde 0 y mantener PLAYING."""
        self._load(seconds=4.0)
        self._player.play()
        time.sleep(0.5)
        self._player.seek(3.0)
        time.sleep(0.3)
        self.assertGreaterEqual(self._player.get_position(), 3.0)

        self.assertTrue(self._player.replay())
        self.assertEqual(self._player.get_state(), PlayerState.PLAYING)
        time.sleep(0.3)
        self.assertLess(self._player.get_position(), 1.0,
                        "replay() no reinició la posición")

    def test_volume_clamped(self):
        self._player.set_volume(2.0)
        self.assertAlmostEqual(self._player.get_volume(), 1.0)
        self._player.set_volume(-1.0)
        self.assertAlmostEqual(self._player.get_volume(), 0.0)
        self._player.set_volume(0.35)
        self.assertAlmostEqual(self._player.get_volume(), 0.35)


class TestPlaylistShuffleRegressions(unittest.TestCase):
    """Regresiones de shuffle con pistas agregadas/removidas."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.pm = PlaylistManager(playlist_dir=str(self.tmp_dir))

    def tearDown(self):
        self._tmp.cleanup()

    def _add(self, name: str) -> Track:
        path = self.tmp_dir / name
        path.write_bytes(b"audio data")
        track = Track(file_path=str(path), title=name, duration=10)
        self.pm.add_track(track)
        return track

    def test_shuffle_after_add_includes_new_track(self):
        """Agregar una pista con shuffle activo debe incluirla en la rotación."""
        for i in range(3):
            self._add(f"t{i}.mp3")
        self.pm.set_current_index(0)
        self.pm.set_shuffle(True)

        # Agotar el orden actual
        for _ in range(2):
            self.assertIsNotNone(self.pm.next())
        self.assertIsNone(self.pm.next())

        # Agregar una pista nueva: regenera el orden y ya no debe agotarse
        new_track = self._add("nueva.mp3")
        # La pista nueva debe aparecer en algún momento de la rotación
        found = False
        for _ in range(6):
            t = self.pm.next()
            if t is None:
                break
            if t.file_path == new_track.file_path:
                found = True
                break
        self.assertTrue(found, "La pista nueva no entró en la rotación shuffle")

    def test_remove_track_with_shuffle_no_crash(self):
        """Remover pistas con shuffle activo no debe producir IndexError."""
        for i in range(5):
            self._add(f"t{i}.mp3")
        self.pm.set_current_index(0)
        self.pm.set_shuffle(True)
        self.pm.next()
        self.pm.next()

        self.assertTrue(self.pm.remove_track(2))
        self.pm.set_repeat_mode(1)  # Repeat all
        for _ in range(20):
            self.assertIsNotNone(self.pm.next())  # no IndexError

    def test_remove_all_in_shuffle(self):
        """Vaciar la playlist con shuffle activo debe quedar consistente."""
        for i in range(3):
            self._add(f"t{i}.mp3")
        self.pm.set_current_index(0)
        self.pm.set_shuffle(True)
        self.pm.remove_track(0)
        self.pm.remove_track(0)
        self.pm.remove_track(0)
        self.assertTrue(self.pm.is_empty())
        self.assertIsNone(self.pm.next())


if __name__ == "__main__":
    unittest.main()