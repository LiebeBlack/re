"""
AudioPlayer - Motor de reproducción de audio de alta calidad.

Arquitectura de doble backend, elegido por pista según la configuración:

  * BACKEND STREAM (pygame.mixer.music): streaming ligero para cualquier
    formato que soporte SDL_mixer (MP3, OGG, FLAC, WAV, OPUS...). Bajo
    consumo de memoria, ideal por defecto.

  * BACKEND HQ/DSP (soundfile + numpy + pygame Channel): decodifica la
    pista completa en un hilo secundario a float32 y aplica la cadena de
    máxima calidad: normalización (ReplayGain / Peak Gain), filtro
    paso-alto subsónico y ecualizador gráfico de 10 bandas (filtros
    biquad en cascada), antes de convertir a int16 para pygame.
    Se activa con el motor HQ; el EQ real solo aplica en este backend.

Garantías de calidad y recursos:
  * La interfaz nunca se congela: decode/procesado en hilo secundario.
  * Búfer y driver de salida configurables (WASAPI/DirectSound/ALSA/Pulse).
  * Los buffers (Sound), canales y arrays numpy se liberan al cambiar de
    pista o cerrar la app (sin fugas de memoria).
  * Detección de fin de pista robusta en ambos backends.
"""

import logging
import math
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Optional

import pygame

from src.audio import dsp

logger = logging.getLogger(__name__)

# Valores por defecto del motor
DEFAULT_SETTINGS = {
    "audio_driver": "auto",
    "sample_rate": 48000,
    "buffer_size": 2048,
    "output_depth": 16,       # 16 (CD) o 32 (float)
    "hq_engine": False,
    "eq_enabled": False,
    "eq_preamp": 0.0,
    "eq_gains": [0.0] * 10,
    "eq_hp_filter": False,
    "normalization": "off",   # off | replaygain | peak
}

# Límites de seguridad del backend HQ (evita consumir toda la RAM)
MAX_HQ_SECONDS = 900          # 15 minutos como máximo en modo HQ
MAX_HQ_SAMPLES = 900 * 96000  # aprox. 350 MB float32 a 96 kHz estéreo

# Ticks sin get_busy() (a 50 ms) para declarar fin de pista en stream
END_IDLE_TICKS = 8
POSITION_MIN_FOR_END = 0.5


class PlayerState(Enum):
    """Estados del reproductor de audio."""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    LOADING = "loading"
    ERROR = "error"


class _Backend(Enum):
    """Backends de reproducción disponibles."""
    NONE = "none"
    STREAM = "stream"   # pygame.mixer.music
    DSP = "dsp"         # soundfile + numpy + Channel


class AudioPlayer:
    """Motor de reproducción con backend STREAM y HQ/DSP."""

    def __init__(self, settings: Optional[Dict] = None):
        """
        Args:
            settings: Overrides de configuración de audio (driver, buffer,
                sample rate, HQ, EQ...). Ver DEFAULT_SETTINGS.
        """
        self._settings = dict(DEFAULT_SETTINGS)
        if settings:
            self._settings.update({k: v for k, v in settings.items() if k in self._settings})

        self._current_file: Optional[str] = None
        self._state = PlayerState.STOPPED
        self._volume = 0.7
        self._position = 0.0
        self._duration = 0.0
        self._seek_base = 0.0
        self._is_running = False
        self._update_thread: Optional[threading.Thread] = None

        self._backend = _Backend.NONE

        # Estado del backend HQ/DSP
        self._dsp_int16: Optional[object] = None      # numpy int16 (N, ch)
        self._dsp_rate: int = 0
        self._dsp_sound: Optional[pygame.mixer.Sound] = None
        self._dsp_channel: Optional[pygame.mixer.Channel] = None
        self._dsp_anchor: float = 0.0                 # time.monotonic al reproducir
        self._dsp_offset: float = 0.0                 # segundos desde donde suena
        self._dsp_gain_db: float = 0.0
        self._dsp_analysis: Optional[Dict] = None   # onda/espectro para UI
        self._decode_thread: Optional[threading.Thread] = None
        self._pending_decode: Optional[str] = None    # archivo en decode
        self._play_pending = False                    # play solicitado durante decode
        self._seek_after_ready: Optional[float] = None  # posición al estar listo

        # Callbacks
        self._on_position_update: Optional[Callable[[float, float], None]] = None
        self._on_track_end: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._on_track_ready: Optional[Callable[[], None]] = None  # decode HQ listo

        self._lock = threading.Lock()

        self._init_mixer()

    # ==================================================================
    # Mixer / configuración de salida
    # ==================================================================

    def _init_mixer(self) -> None:
        """Inicializa el mixer según la configuración, con fallbacks."""
        driver = self._settings.get("audio_driver", "auto")
        rate = int(self._settings.get("sample_rate", 48000))
        size = -16 if self._settings.get("output_depth", 16) == 16 else 32
        buffer = int(self._settings.get("buffer_size", 2048))

        # Seleccionar driver de salida (WASAPI / DirectSound / ALSA / Pulse)
        if driver and driver != "auto":
            import os
            os.environ["SDL_AUDIODRIVER"] = driver

        # Quitar cualquier mixer previo (re-init limpio)
        try:
            pygame.mixer.quit()
        except Exception:
            pass

        configs = [
            (rate, size, 2, buffer),
            (rate, -16, 2, buffer),
            (44100, -16, 2, 2048),
            (44100, -16, 2, 512),
            (22050, -16, 2, 512),
        ]
        for freq, sz, channels, buf in configs:
            try:
                pygame.mixer.init(frequency=freq, size=sz, channels=channels, buffer=buf)
                if channels > 2:
                    pygame.mixer.set_num_channels(channels)
                logger.info(
                    f"Mixer OK: {freq} Hz, {abs(sz)}-bit, driver={driver or 'default'}, "
                    f"buffer={buf}"
                )
                return
            except (pygame.error, Exception) as e:
                logger.warning(f"Falló init mixer {freq}/{sz}/{buf}: {e}")

        self._state = PlayerState.ERROR
        raise RuntimeError("No se pudo inicializar el dispositivo de audio.")

    def apply_audio_settings(self, settings: Dict) -> None:
        """
        Aplica configuración de salida (driver, buffer, sample rate, HQ...).

        Detiene la reproducción actual y reinicia el mixer.

        Args:
            settings: Diccionario parcial con las claves de DEFAULT_SETTINGS.
        """
        was_playing = self._state == PlayerState.PLAYING
        position = self._position
        self._settings.update({k: v for k, v in settings.items() if k in self._settings})
        self._stop_all()
        self._init_mixer()
        # Reanudar donde estaba si había algo cargado
        if self._current_file and (was_playing or self._state == PlayerState.STOPPED):
            self.load(self._current_file, duration_hint=self._duration or None)
            if was_playing and self._state != PlayerState.ERROR:
                self.play()
                self.seek(position)

    def _stop_all(self) -> None:
        """Detiene cualquier reproducción y libera recursos de ambos backends."""
        self._is_running = False
        if self._decode_thread is not None and self._decode_thread.is_alive():
            self._pending_decode = None
            self._decode_thread.join(timeout=0.5)
        self._decode_thread = None
        self._release_dsp()
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self._state = PlayerState.STOPPED
        self._position = 0.0
        self._seek_base = 0.0

    # ==================================================================
    # Carga
    # ==================================================================

    def load(self, file_path: str, duration_hint: Optional[float] = None) -> bool:
        """
        Carga un archivo de audio eligiendo el backend adecuado.

        Si el motor HQ está activo y el archivo puede decodificarse con
        soundfile dentro de los límites de memoria, la carga es asíncrona
        (hilo de decode) y la UI recibe el evento "track_ready".

        Args:
            file_path: Ruta del archivo a cargar.
            duration_hint: Duración conocida (metadatos) en segundos.

        Returns:
            True si la carga se inició con éxito.
        """
        if not file_path or not isinstance(file_path, str):
            logger.error("Ruta de archivo inválida")
            return False
        if not Path(file_path).exists() or not Path(file_path).is_file():
            logger.error(f"El archivo no existe: {file_path}")
            return False

        with self._lock:
            self._release_dsp()  # liberar pista anterior
            self._state = PlayerState.LOADING

            use_hq = bool(self._settings.get("hq_engine"))
            if use_hq:
                ok = self._start_hq_decode(file_path, duration_hint)
                if ok:
                    return True
                # Si el decode HQ no es posible, caer a streaming
                logger.info("HQ no disponible, usando backend STREAM")

            return self._load_stream(file_path, duration_hint)

    def _load_stream(self, file_path: str, duration_hint: Optional[float]) -> bool:
        """Carga vía pygame.mixer.music (backend STREAM)."""
        try:
            pygame.mixer.music.load(file_path)
            self._current_file = file_path
            self._backend = _Backend.STREAM
            self._position = 0.0
            self._seek_base = 0.0
            self._duration = self._estimate_duration(file_path, duration_hint)
            self._state = PlayerState.STOPPED
            logger.info(f"STREAM cargado: {file_path} ({self._duration:.1f}s)")
            return True
        except pygame.error as e:
            logger.error(f"Error de pygame al cargar: {e}")
            self._state = PlayerState.ERROR
            self._notify_error(f"Error al cargar archivo: {e}")
            return False
        except Exception as e:
            logger.error(f"Error inesperado al cargar: {e}")
            self._state = PlayerState.ERROR
            self._notify_error(f"Error inesperado: {e}")
            return False

    # ------------------------------------------------------------------
    # Backend HQ (decode + DSP en hilo secundario)
    # ------------------------------------------------------------------

    def _start_hq_decode(self, file_path: str, duration_hint: Optional[float]) -> bool:
        """
        Inicia el decode HQ en un hilo secundario.

        Returns:
            True si el decode es viable y arrancó, False si debe usarse
            streaming (formato no decodificable o pista demasiado larga).
        """
        try:
            import soundfile as sf
            info = sf.info(file_path)
            duration = float(info.duration)
            if duration <= 0 or duration > MAX_HQ_SECONDS:
                logger.info(f"Pista de {duration:.0f}s fuera del límite HQ ({MAX_HQ_SECONDS}s)")
                return False
            if duration * info.samplerate * info.channels > MAX_HQ_SAMPLES:
                logger.info("Pista demasiado grande para HQ; streaming")
                return False
        except Exception:
            return False  # soundfile no puede: streaming

        self._backend = _Backend.DSP
        self._current_file = file_path
        self._pending_decode = file_path
        if duration_hint and duration_hint > 0:
            self._duration = float(duration_hint)
        else:
            self._duration = 0.0
        self._state = PlayerState.LOADING

        self._decode_thread = threading.Thread(
            target=self._decode_and_process, args=(file_path,), daemon=True
        )
        self._decode_thread.start()
        logger.info(f"HQ decode iniciado (hilo): {file_path}")
        return True

    def _decode_and_process(self, file_path: str) -> None:
        """Hilo secundario: leer -> normalizar -> EQ -> int16 (sin tocar Tk)."""
        try:
            info = dsp.read_track(file_path)
            if info is None:
                self._notify_error("No se pudo decodificar el archivo para el modo HQ.")
                return
            samples = info["samples"]
            fs = info["rate"]

            # --- Normalización de volumen -----------------------------
            gain_db = 0.0
            norm = self._settings.get("normalization", "off")
            if norm == "replaygain":
                gain_db = dsp.replaygain_db(file_path) or 0.0
            elif norm == "peak":
                gain_db = dsp.peak_gain_db(samples)
            self._dsp_gain_db = gain_db
            if gain_db:
                samples = samples * dsp.db_to_linear(gain_db)

            # --- EQ (solo si está activado) ---------------------------
            if self._settings.get("eq_enabled"):
                samples = dsp.apply_eq(
                    samples, fs,
                    self._settings.get("eq_gains", [0.0] * 10),
                    preamp_db=self._settings.get("eq_preamp", 0.0),
                    hp_filter=bool(self._settings.get("eq_hp_filter")),
                )

            # --- Análisis visual (onda + perfil espectral) -------------
            wave_width = 600
            mins, maxs = dsp.compute_waveform_peaks(samples, wave_width)
            spectrum = dsp.compute_spectrum_profile(samples, fs)
            analysis = {
                "wave_mins": mins.tolist(),
                "wave_maxs": maxs.tolist(),
                "spectrum": spectrum.tolist(),
            }

            # --- Convertir a int16 y publicar -------------------------
            int16 = dsp.to_int16(samples)

            # Publicación atómica: si mientras tanto se cargó otra pista,
            # este decode es obsoleto y se descarta (evita clobbering).
            with self._lock:
                if self._pending_decode != file_path:
                    logger.debug(f"Decode obsoleto descartado: {file_path}")
                    return
                self._dsp_int16 = int16
                self._dsp_rate = fs
                self._duration = info["duration"]
                self._dsp_analysis = analysis
                self._pending_decode = None
            if self._on_track_ready:
                # Notifica al hilo principal (vía cola en la UI)
                self._on_track_ready()
            logger.info(f"HQ decode completado: {file_path} ({info['duration']:.1f}s)")
        except Exception as e:
            logger.error(f"Error en decode HQ de {file_path}: {e}")
            self._notify_error(f"Error procesando audio: {e}")

    def accept_hq_buffer(self) -> bool:
        """
        Construye el Sound de pygame con el buffer HQ ya decodificado.

        Debe llamarse desde el hilo principal (tras el evento track_ready).

        Returns:
            True si el buffer se aceptó.
        """
        with self._lock:
            data = self._dsp_int16
            if data is None:
                return False
            try:
                sound = pygame.sndarray.make_sound(data)
                self._dsp_sound = sound
                # Reservar un canal dedicado para la reproducción HQ
                if self._dsp_channel is None:
                    pygame.mixer.set_reserved(1)
                    self._dsp_channel = pygame.mixer.Channel(0)
                self._backend = _Backend.DSP
                self._position = 0.0
                self._seek_base = 0.0
                self._state = PlayerState.STOPPED

                # Si el usuario ya pulsó play durante el decode, arrancar
                was_pending = self._play_pending
                self._play_pending = False
                if was_pending:
                    self._state = PlayerState.PLAYING
                    self._start_backend_play(0.0)
                    self._start_update_thread()
                    if self._seek_after_ready is not None:
                        pos = self._seek_after_ready
                        self._seek_after_ready = None
                        self.seek(pos)
                else:
                    self._seek_after_ready = None
                return True
            except Exception as e:
                logger.error(f"Error creando Sound HQ: {e}")
                self._notify_error(f"Error preparando audio HQ: {e}")
                self._release_dsp()
                return False

    def hq_buffer_ready(self) -> bool:
        """Retorna True si hay un buffer HQ decodificado pendiente de aceptar."""
        return self._dsp_int16 is not None

    def _release_dsp(self) -> None:
        """Libera buffers/canal/stream del backend HQ (sin fugas)."""
        try:
            if self._dsp_channel is not None:
                self._dsp_channel.stop()
        except Exception:
            pass
        self._dsp_channel = None
        self._dsp_sound = None
        self._dsp_int16 = None
        self._dsp_rate = 0
        self._dsp_gain_db = 0.0
        self._dsp_analysis = None
        self._dsp_offset = 0.0
        self._dsp_anchor = 0.0
        self._play_pending = False
        self._seek_after_ready = None
        if self._backend == _Backend.DSP:
            self._backend = _Backend.NONE

    def get_analysis(self) -> Optional[Dict]:
        """
        Devuelve el análisis visual de la pista HQ decodificada.

        Returns:
            Dict con 'wave_mins', 'wave_maxs' y 'spectrum', o None.
        """
        with self._lock:
            return self._dsp_analysis

    def update_dsp_settings(self, settings: Dict) -> None:
        """
        Actualiza parámetros DSP (EQ, normalización, HQ on/off) y vuelve a
        procesar la pista actual si estaba en modo HQ.

        No reinicia el mixer (a diferencia de apply_audio_settings).

        Args:
            settings: Parcial con claves de DEFAULT_SETTINGS.
        """
        self._settings.update({k: v for k, v in settings.items() if k in self._settings})
        was_playing = self._state == PlayerState.PLAYING
        position = self._position
        if self._backend == _Backend.DSP and self._current_file:
            # Reprocesar la pista actual con los nuevos ajustes
            self._release_dsp()
            self._state = PlayerState.LOADING
            self._seek_after_ready = position if (was_playing and position > 0.5) else None
            self._play_pending = was_playing
            self._start_hq_decode(self._current_file, self._duration or None)
        elif not self._settings.get("hq_engine") and self._backend == _Backend.DSP:
            # Salir de modo HQ: volver a streaming
            self._stop_all()
            if self._current_file:
                self.load(self._current_file, duration_hint=self._duration or None)
                if was_playing:
                    self.play()
                    if position > 0.5:
                        self.seek(position)
        elif self._settings.get("hq_engine") and self._backend == _Backend.STREAM:
            # Entrar en modo HQ con pista ya cargada en streaming
            self._stop_all()
            if self._current_file:
                self.load(self._current_file, duration_hint=self._duration or None)
                self._play_pending = was_playing
                if was_playing:
                    self.play()

    # ==================================================================
    # Reproducción
    # ==================================================================

    def _start_backend_play(self, start_seconds: float = 0.0) -> bool:
        """Arranca la reproducción en el backend activo desde start_seconds."""
        if self._backend == _Backend.DSP:
            if self._dsp_sound is None or self._dsp_channel is None:
                return False
            if start_seconds > 0 and self._dsp_int16 is not None:
                # Slice del buffer para el seek
                start = int(start_seconds * self._dsp_rate)
                chunk = self._dsp_int16[start:]
                if chunk.shape[0] == 0:
                    return False
                sound = pygame.sndarray.make_sound(chunk)
            else:
                sound = self._dsp_sound
            self._dsp_channel.play(sound)
            self._dsp_channel.set_volume(self._volume)
            self._dsp_offset = start_seconds
            self._dsp_anchor = time.monotonic()
            self._position = start_seconds
            return True

        # Backend STREAM
        pygame.mixer.music.play(start=start_seconds)
        pygame.mixer.music.set_volume(self._effective_volume())
        self._seek_base = start_seconds
        self._position = start_seconds
        return True

    def _effective_volume(self) -> float:
        """Volumen final aplicado (volumen usuario x ganancia normalización)."""
        gain = 0.0
        if self._backend == _Backend.STREAM:
            gain = getattr(self, "_stream_gain_db", 0.0) or 0.0
        elif self._backend == _Backend.DSP:
            gain = self._dsp_gain_db
        factor = dsp.db_to_linear(gain) if gain else 1.0
        return max(0.0, min(1.0, self._volume * factor))

    def play(self) -> bool:
        """Inicia/reanuda la reproducción desde donde corresponde."""
        if not self._current_file:
            logger.warning("Intento de reproducir sin archivo cargado")
            return False
        if self._state == PlayerState.PLAYING:
            return True
        if self._state == PlayerState.LOADING and self._backend == _Backend.DSP:
            # El decode HQ aún no termina: reproducir en cuanto esté listo
            self._play_pending = True
            logger.info("Play solicitado durante decode HQ; pendiente de 'ready'")
            return True
        if self._backend == _Backend.NONE and self._dsp_int16 is None:
            return False

        with self._lock:
            try:
                if self._state == PlayerState.PAUSED:
                    return self.resume()
                ok = self._start_backend_play(0.0)
                if ok:
                    self._state = PlayerState.PLAYING
                    self._start_update_thread()
                return ok
            except (pygame.error, Exception) as e:
                logger.error(f"Error al reproducir: {e}")
                self._state = PlayerState.ERROR
                self._notify_error(f"Error al reproducir: {e}")
                return False

    def replay(self) -> bool:
        """Reinicia la pista actual desde el principio (Repeat One)."""
        if not self._current_file:
            return False
        with self._lock:
            try:
                if self._backend == _Backend.DSP:
                    if self._dsp_sound is None:
                        return False
                    self._dsp_channel.play(self._dsp_sound)
                    self._dsp_channel.set_volume(self._volume)
                    self._dsp_offset = 0.0
                    self._dsp_anchor = time.monotonic()
                else:
                    pygame.mixer.music.play()
                    pygame.mixer.music.set_volume(self._effective_volume())
                    self._seek_base = 0.0
                self._position = 0.0
                self._state = PlayerState.PLAYING
                self._start_update_thread()
                return True
            except (pygame.error, Exception) as e:
                logger.error(f"Error al reiniciar: {e}")
                self._state = PlayerState.ERROR
                self._notify_error(f"Error al reiniciar: {e}")
                return False

    def pause(self) -> bool:
        """Pausa la reproducción."""
        if self._state != PlayerState.PLAYING:
            return False
        with self._lock:
            try:
                if self._backend == _Backend.DSP:
                    self._dsp_offset += time.monotonic() - self._dsp_anchor
                    self._dsp_channel.pause()
                else:
                    pygame.mixer.music.pause()
                self._state = PlayerState.PAUSED
                return True
            except (pygame.error, Exception) as e:
                logger.error(f"Error al pausar: {e}")
                self._notify_error(f"Error al pausar: {e}")
                return False

    def resume(self) -> bool:
        """Reanuda la reproducción pausada."""
        if self._state != PlayerState.PAUSED:
            return False
        with self._lock:
            try:
                if self._backend == _Backend.DSP:
                    self._dsp_channel.unpause()
                    self._dsp_anchor = time.monotonic()
                else:
                    pygame.mixer.music.unpause()
                self._state = PlayerState.PLAYING
                self._start_update_thread()
                return True
            except (pygame.error, Exception) as e:
                logger.error(f"Error al reanudar: {e}")
                self._notify_error(f"Error al reanudar: {e}")
                return False

    def stop(self) -> bool:
        """Detiene la reproducción y libera el backend DSP."""
        with self._lock:
            try:
                self._is_running = False
                if self._backend == _Backend.DSP:
                    if self._dsp_channel is not None:
                        self._dsp_channel.stop()
                else:
                    pygame.mixer.music.stop()
                self._state = PlayerState.STOPPED
                self._position = 0.0
                self._seek_base = 0.0
                self._stop_update_thread()
                return True
            except (pygame.error, Exception) as e:
                logger.error(f"Error al detener: {e}")
                return False

    def seek(self, position: float) -> bool:
        """Busca una posición en segundos (ambos backends)."""
        if not self._current_file:
            return False
        position = float(position)
        if position < 0:
            position = 0
        if self._duration > 0 and position > self._duration:
            position = self._duration

        with self._lock:
            try:
                was_playing = self._state == PlayerState.PLAYING
                if self._backend == _Backend.DSP:
                    if self._dsp_channel is None or self._dsp_sound is None:
                        return False
                    self._dsp_channel.stop()
                    ok = self._start_backend_play(position)
                    if not ok:
                        return False
                    if not was_playing:
                        self._dsp_channel.pause()
                        self._dsp_offset = position
                        self._state = PlayerState.PAUSED
                    self._position = position
                    return True

                # STREAM
                was_playing = self._state == PlayerState.PLAYING
                pygame.mixer.music.stop()
                pygame.mixer.music.play(start=position)
                pygame.mixer.music.set_volume(self._effective_volume())
                self._seek_base = position
                self._position = position
                if was_playing:
                    self._state = PlayerState.PLAYING
                else:
                    pygame.mixer.music.pause()
                    self._state = PlayerState.PAUSED
                return True
            except (pygame.error, Exception) as e:
                logger.error(f"Error al buscar: {e}")
                self._notify_error(f"Error al buscar posición: {e}")
                return False

    # ==================================================================
    # Volumen
    # ==================================================================

    def set_volume(self, volume: float) -> None:
        """Establece el volumen del usuario (0..1), respetando la ganancia."""
        if not isinstance(volume, (int, float)):
            volume = 0.7
        self._volume = max(0.0, min(1.0, float(volume)))
        try:
            if self._backend == _Backend.DSP and self._dsp_channel is not None:
                self._dsp_channel.set_volume(self._volume)
            else:
                pygame.mixer.music.set_volume(self._effective_volume())
        except Exception:
            pass

    def get_volume(self) -> float:
        return self._volume

    # ==================================================================
    # Estado / posición / duración
    # ==================================================================

    def get_state(self) -> PlayerState:
        return self._state

    def get_position(self) -> float:
        return self._position

    def get_duration(self) -> float:
        return self._duration

    def get_backend(self) -> str:
        """Retorna el backend activo ('stream', 'dsp', 'none')."""
        return self._backend.value

    def is_hq(self) -> bool:
        """True si la pista actual usa el backend HQ/DSP."""
        return self._backend == _Backend.DSP

    def get_hq_rate(self) -> int:
        return self._dsp_rate

    # ==================================================================
    # Callbacks
    # ==================================================================

    def set_position_callback(self, callback: Callable[[float, float], None]) -> None:
        self._on_position_update = callback

    def set_track_end_callback(self, callback: Callable[[], None]) -> None:
        self._on_track_end = callback

    def set_error_callback(self, callback: Callable[[str], None]) -> None:
        self._on_error = callback

    def set_track_ready_callback(self, callback: Callable[[], None]) -> None:
        """Callback cuando termina el decode HQ (desde el hilo secundario)."""
        self._on_track_ready = callback

    def _notify_error(self, message: str) -> None:
        logger.error(message)
        if self._on_error:
            try:
                self._on_error(message)
            except Exception:
                pass

    # ==================================================================
    # Hilo de posición
    # ==================================================================

    def _start_update_thread(self) -> None:
        if (self._update_thread is not None
                and self._update_thread is not threading.current_thread()
                and self._update_thread.is_alive()):
            self._is_running = False
            self._update_thread.join(timeout=0.5)
        self._is_running = True
        self._update_thread = threading.Thread(target=self._update_position, daemon=True)
        self._update_thread.start()

    def _stop_update_thread(self) -> None:
        self._is_running = False
        if self._update_thread is not None and self._update_thread.is_alive():
            self._update_thread.join(timeout=1.0)

    def _update_position(self) -> None:
        """Sondea la posición y detecta fin de pista en el backend activo."""
        last_callback_time = 0.0
        idle_ticks = 0

        while self._is_running and self._state == PlayerState.PLAYING:
            try:
                with self._lock:
                    if self._backend == _Backend.DSP:
                        # Posición por reloj propio (Channel no reporta tiempo)
                        if self._state == PlayerState.PLAYING:
                            self._position = self._dsp_offset + (time.monotonic() - self._dsp_anchor)
                        busy = (self._dsp_channel is not None
                                and self._dsp_channel.get_busy())
                        if self._dsp_channel is not None:
                            # Re-sincronizar si el canal se agota por el final
                            if not busy and self._dsp_int16 is not None:
                                idle_ticks += 1
                            else:
                                idle_ticks = 0
                    else:
                        pos = pygame.mixer.music.get_pos()
                        busy = pygame.mixer.music.get_busy()
                        if pos >= 0:
                            self._position = self._seek_base + pos / 1000.0
                        if busy:
                            idle_ticks = 0
                        else:
                            idle_ticks += 1

                ended_by_duration = (
                    self._duration > 0 and self._position >= self._duration - 0.08
                )
                ended_by_idle = idle_ticks >= END_IDLE_TICKS and self._position > POSITION_MIN_FOR_END

                if ended_by_duration or ended_by_idle:
                    if ended_by_duration:
                        self._position = self._duration
                    logger.info("Pista terminada (%s)", self._backend.value)
                    if self._on_track_end:
                        self._on_track_end()
                    break

                current_time = time.time()
                if self._on_position_update and (current_time - last_callback_time >= 0.1):
                    self._on_position_update(self._position, self._duration)
                    last_callback_time = current_time

                time.sleep(0.05)
            except Exception as e:
                logger.error(f"Error en actualización de posición: {e}")
                break

    # ==================================================================
    # Duración / estimación
    # ==================================================================

    def _estimate_duration(self, file_path: str, duration_hint: Optional[float]) -> float:
        """Duración: hint > soundfile > mutagen > Sound (último recurso)."""
        if duration_hint and duration_hint > 0:
            return float(duration_hint)
        try:
            import soundfile as sf
            info = sf.info(file_path)
            if float(info.duration) > 0:
                return float(info.duration)
        except Exception:
            pass
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(file_path)
            length = getattr(getattr(audio, "info", None), "length", 0) or 0
            if length > 0:
                return float(length)
        except Exception:
            pass
        try:
            sound = pygame.mixer.Sound(file_path)
            length = sound.get_length()
            del sound
            if length > 0:
                return float(length)
        except Exception:
            pass
        return 0.0

    # ==================================================================
    # Limpieza
    # ==================================================================

    def cleanup(self) -> None:
        """Libera todos los recursos antes de cerrar la aplicación."""
        self._stop_all()
        try:
            pygame.mixer.quit()
        except Exception:
            pass