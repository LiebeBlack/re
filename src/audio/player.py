"""
AudioPlayer - Motor de reproducción de audio usando pygame.

Correcciones y mejoras de calidad incluidas:
  * Mixer con buffer más grande (2048) para evitar cortes/parpadeos.
  * Duración real del archivo vía mutagen (o hint de metadatos) en vez de
    cargar la pista completa en memoria con pygame.mixer.Sound.
  * Seek corregido: pygame.mixer.music.get_pos() cuenta desde 0 tras
    play(start=...), por lo que se usa un offset base (self._seek_base)
    para que la barra de progreso refleje la posición real.
  * Detección de fin de pista robusta con get_busy() (funciona aunque la
    duración sea desconocida) + verificación por duración.
  * replay() para el modo Repeat One (reproducir de nuevo desde 0).
  * Hilo de posición sin unirse a sí mismo (evita RuntimeError).
"""

import threading
import time
import logging
from typing import Optional, Callable
from enum import Enum
from pathlib import Path

import pygame


class PlayerState(Enum):
    """Estados del reproductor de audio."""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    LOADING = "loading"
    ERROR = "error"


logger = logging.getLogger(__name__)

# Configuración de calidad del mixer (CD quality: 44.1kHz / 16-bit / estéreo)
# Buffer de 2048 en vez de 512: menor riesgo de subdesbordamientos (stutter).
MIXER_FREQUENCY = 44100
MIXER_SIZE = -16      # 16-bit signed
MIXER_CHANNELS = 2    # Estéreo
MIXER_BUFFER = 2048

# Ticks consecutivos (a 50 ms) sin get_busy() para declarar fin de pista.
# 8 ticks = 400 ms: suficiente margen para no confundir un seek (stop+play)
# con el fin real de la canción.
END_IDLE_TICKS = 8
POSITION_MIN_FOR_END = 0.5  # No declarar fin si la pista casi no empezó


class AudioPlayer:
    """Clase principal para manejar la reproducción de audio."""

    def __init__(self):
        """Inicializa el reproductor de audio."""
        self._current_file: Optional[str] = None
        self._state = PlayerState.STOPPED
        self._volume = 0.7
        self._position = 0.0
        self._duration = 0.0
        # Offset para el seek: get_pos() cuenta desde 0 tras play(start=...)
        self._seek_base = 0.0
        self._is_running = False
        self._update_thread: Optional[threading.Thread] = None
        self._on_position_update: Optional[Callable[[float, float], None]] = None
        self._on_track_end: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._lock = threading.Lock()

        # Inicializar pygame mixer con calidad CD y buffer estable.
        # Se prueba la configuración deseada y se degrada con fallbacks
        # por si el dispositivo de audio no la soporta.
        self._init_mixer()

    def _init_mixer(self) -> None:
        """Inicializa el mixer probando configuraciones en cascada."""
        configs = [
            (MIXER_FREQUENCY, MIXER_SIZE, MIXER_CHANNELS, MIXER_BUFFER),
            (MIXER_FREQUENCY, MIXER_SIZE, MIXER_CHANNELS, 1024),
            (44100, -16, 2, 512),   # configuración clásica
            (22050, -16, 2, 512),   # último recurso
        ]
        for freq, size, channels, buffer in configs:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
            try:
                pygame.mixer.init(frequency=freq, size=size, channels=channels, buffer=buffer)
                pygame.mixer.music.set_volume(self._volume)
                logger.info(
                    f"Mixer inicializado: {freq}Hz, {abs(size)}-bit, "
                    f"{channels}ch, buffer={buffer}"
                )
                return
            except pygame.error as e:
                logger.warning(f"Fallo al inicializar mixer {freq}/{buffer}: {e}")
            except Exception as e:
                logger.warning(f"Error inesperado inicializando mixer: {e}")

        self._state = PlayerState.ERROR
        raise RuntimeError("No se pudo inicializar el dispositivo de audio.")

    # ------------------------------------------------------------------
    # Carga
    # ------------------------------------------------------------------

    def load(self, file_path: str, duration_hint: Optional[float] = None) -> bool:
        """
        Carga un archivo de audio.

        Args:
            file_path: Ruta del archivo a cargar.
            duration_hint: Duración conocida (p. ej. desde metadatos) para
                evitar estimaciones costosas.

        Returns:
            True si se cargó exitosamente, False en caso contrario.
        """
        # Validar que la ruta no sea vacía
        if not file_path or not isinstance(file_path, str):
            logger.error("Ruta de archivo inválida")
            return False

        # Validar que el archivo existe
        if not Path(file_path).exists():
            logger.error(f"El archivo no existe: {file_path}")
            return False

        # Validar que sea un archivo
        if not Path(file_path).is_file():
            logger.error(f"La ruta no es un archivo: {file_path}")
            return False

        with self._lock:
            try:
                self._state = PlayerState.LOADING
                logger.info(f"Cargando archivo: {file_path}")

                pygame.mixer.music.load(file_path)
                self._current_file = file_path
                self._position = 0.0
                self._seek_base = 0.0
                # Duración: hint de metadatos > mutagen > Sound (último recurso)
                self._duration = self._estimate_duration(file_path, duration_hint)

                self._state = PlayerState.STOPPED
                logger.info(f"Archivo cargado exitosamente: {file_path} ({self._duration:.1f}s)")
                return True

            except pygame.error as e:
                logger.error(f"Error de pygame al cargar archivo: {e}")
                self._state = PlayerState.ERROR
                if self._on_error:
                    self._on_error(f"Error al cargar archivo: {e}")
                return False
            except Exception as e:
                logger.error(f"Error inesperado al cargar archivo: {e}")
                self._state = PlayerState.ERROR
                if self._on_error:
                    self._on_error(f"Error inesperado: {e}")
                return False

    def _estimate_duration(self, file_path: str, duration_hint: Optional[float] = None) -> float:
        """
        Estima la duración del archivo sin cargarlo entero en memoria.

        Orden de preferencia:
          1. duration_hint (metadatos ya extraídos).
          2. mutagen (lectura ligera de etiquetas).
          3. pygame.mixer.Sound (último recurso; carga el archivo completo).

        Args:
            file_path: Ruta del archivo.
            duration_hint: Duración conocida (opcional).

        Returns:
            Duración en segundos (0.0 si no se pudo determinar).
        """
        # 1) Hint de metadatos
        if duration_hint and duration_hint > 0:
            return float(duration_hint)

        # 2) mutagen: lectura rápida sin decodificar
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(file_path)
            info = getattr(audio, "info", None)
            length = getattr(info, "length", 0) or 0
            if length > 0:
                logger.debug(f"Duración vía mutagen: {length:.1f}s")
                return float(length)
        except Exception as e:
            logger.debug(f"mutagen no disponible para {file_path}: {e}")

        # 3) Último recurso: Sound (carga completa, solo archivos pequeños)
        try:
            sound = pygame.mixer.Sound(file_path)
            length = sound.get_length()
            del sound
            if length > 0:
                logger.debug(f"Duración vía Sound: {length:.1f}s")
                return float(length)
        except Exception as e:
            logger.debug(f"Sound no disponible para {file_path}: {e}")

        logger.warning(f"No se pudo estimar la duración de {file_path}")
        return 0.0

    # ------------------------------------------------------------------
    # Reproducción
    # ------------------------------------------------------------------

    def play(self) -> bool:
        """
        Inicia la reproducción desde el principio (o desde donde quedó
        el seek).

        Returns:
            True si se inició exitosamente, False en caso contrario.
        """
        if not self._current_file:
            logger.warning("Intento de reproducir sin archivo cargado")
            return False

        # No reiniciar la canción si ya está sonando
        if self._state == PlayerState.PLAYING:
            return True

        with self._lock:
            try:
                logger.info("Iniciando reproducción")
                pygame.mixer.music.play()
                pygame.mixer.music.set_volume(self._volume)
                self._position = 0.0
                self._seek_base = 0.0
                self._state = PlayerState.PLAYING
                self._start_update_thread()
                return True
            except pygame.error as e:
                logger.error(f"Error de pygame al reproducir: {e}")
                self._state = PlayerState.ERROR
                if self._on_error:
                    self._on_error(f"Error al reproducir: {e}")
                return False
            except Exception as e:
                logger.error(f"Error inesperado al reproducir: {e}")
                self._state = PlayerState.ERROR
                if self._on_error:
                    self._on_error(f"Error inesperado: {e}")
                return False

    def replay(self) -> bool:
        """
        Reinicia la pista actual desde el principio (modo Repeat One).

        Devuelve True si se reinició correctamente.
        """
        if not self._current_file:
            logger.warning("Intento de replay sin archivo cargado")
            return False

        with self._lock:
            try:
                logger.info("Reiniciando pista (replay)")
                pygame.mixer.music.play()
                pygame.mixer.music.set_volume(self._volume)
                self._position = 0.0
                self._seek_base = 0.0
                self._state = PlayerState.PLAYING
                self._start_update_thread()
                return True
            except pygame.error as e:
                logger.error(f"Error al reiniciar: {e}")
                self._state = PlayerState.ERROR
                if self._on_error:
                    self._on_error(f"Error al reiniciar: {e}")
                return False

    def pause(self) -> bool:
        """
        Pausa la reproducción.

        Returns:
            True si se pausó exitosamente, False en caso contrario.
        """
        if self._state != PlayerState.PLAYING:
            logger.warning("Intento de pausar cuando no está reproduciendo")
            return False

        with self._lock:
            try:
                logger.info("Pausando reproducción")
                pygame.mixer.music.pause()
                self._state = PlayerState.PAUSED
                return True
            except pygame.error as e:
                logger.error(f"Error al pausar: {e}")
                if self._on_error:
                    self._on_error(f"Error al pausar: {e}")
                return False

    def resume(self) -> bool:
        """
        Reanuda la reproducción pausada.

        Returns:
            True si se reanudó exitosamente, False en caso contrario.
        """
        if self._state != PlayerState.PAUSED:
            logger.warning("Intento de reanudar cuando no está pausado")
            return False

        with self._lock:
            try:
                logger.info("Reanudando reproducción")
                pygame.mixer.music.unpause()
                self._state = PlayerState.PLAYING
                # Reiniciar el hilo de posición (salió al pausar)
                self._start_update_thread()
                return True
            except pygame.error as e:
                logger.error(f"Error al reanudar: {e}")
                if self._on_error:
                    self._on_error(f"Error al reanudar: {e}")
                return False

    def stop(self) -> bool:
        """
        Detiene la reproducción.

        Returns:
            True si se detuvo exitosamente, False en caso contrario.
        """
        with self._lock:
            try:
                logger.info("Deteniendo reproducción")
                pygame.mixer.music.stop()
                self._state = PlayerState.STOPPED
                self._position = 0.0
                self._seek_base = 0.0
                self._stop_update_thread()
                return True
            except pygame.error as e:
                logger.error(f"Error al detener: {e}")
                if self._on_error:
                    self._on_error(f"Error al detener: {e}")
                return False

    # ------------------------------------------------------------------
    # Volumen
    # ------------------------------------------------------------------

    def set_volume(self, volume: float) -> None:
        """
        Establece el volumen de reproducción (0.0 - 1.0).

        Args:
            volume: Valor de volumen entre 0.0 y 1.0.
        """
        # Validar el valor
        if not isinstance(volume, (int, float)):
            logger.warning(f"Volumen inválido: {volume}, usando valor por defecto")
            volume = 0.7

        self._volume = max(0.0, min(1.0, float(volume)))
        try:
            pygame.mixer.music.set_volume(self._volume)
            logger.debug(f"Volumen establecido a: {self._volume}")
        except pygame.error as e:
            logger.error(f"Error al establecer volumen: {e}")

    def get_volume(self) -> float:
        """
        Obtiene el volumen actual.

        Returns:
            Valor de volumen entre 0.0 y 1.0.
        """
        return self._volume

    # ------------------------------------------------------------------
    # Estado y posición
    # ------------------------------------------------------------------

    def get_state(self) -> PlayerState:
        """Obtiene el estado actual del reproductor."""
        return self._state

    def get_position(self) -> float:
        """Obtiene la posición actual en segundos."""
        return self._position

    def get_duration(self) -> float:
        """Obtiene la duración total de la canción en segundos."""
        return self._duration

    def seek(self, position: float) -> bool:
        """
        Busca una posición específica en la canción.

        Args:
            position: Posición en segundos.

        Returns:
            True si se realizó exitosamente, False en caso contrario.
        """
        if not self._current_file:
            logger.warning("Intento de seek sin archivo cargado")
            return False

        # Validar posición
        if not isinstance(position, (int, float)):
            logger.warning(f"Posición inválida: {position}")
            return False

        position = float(position)
        if position < 0:
            position = 0
        elif self._duration > 0 and position > self._duration:
            position = self._duration

        with self._lock:
            try:
                logger.debug(f"Buscando posición: {position}s")
                was_playing = self._state == PlayerState.PLAYING
                pygame.mixer.music.stop()
                pygame.mixer.music.play(start=position)
                pygame.mixer.music.set_volume(self._volume)

                # get_pos() cuenta desde 0 tras play(start=...): guardamos
                # el offset para reportar la posición absoluta real.
                self._seek_base = position
                self._position = position

                if was_playing:
                    self._state = PlayerState.PLAYING
                else:
                    # Si no estaba sonando, pausar inmediatamente para
                    # que el estado coincida con la realidad
                    pygame.mixer.music.pause()
                    self._state = PlayerState.PAUSED

                return True
            except pygame.error as e:
                logger.error(f"Error al buscar posición: {e}")
                if self._on_error:
                    self._on_error(f"Error al buscar posición: {e}")
                return False

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def set_position_callback(self, callback: Callable[[float, float], None]) -> None:
        """
        Establece el callback para actualizaciones de posición.

        Args:
            callback: Función que recibe (posición_actual, duración_total).
        """
        self._on_position_update = callback

    def set_track_end_callback(self, callback: Callable[[], None]) -> None:
        """
        Establece el callback cuando termina una canción.

        Args:
            callback: Función a llamar cuando termina la canción.
        """
        self._on_track_end = callback

    def set_error_callback(self, callback: Callable[[str], None]) -> None:
        """
        Establece el callback para errores.

        Args:
            callback: Función a llamar cuando ocurre un error.
        """
        self._on_error = callback

    # ------------------------------------------------------------------
    # Hilo de actualización de posición
    # ------------------------------------------------------------------

    def _start_update_thread(self) -> None:
        """Inicia el hilo de actualización de posición de forma robusta."""
        # Detener un hilo previo que aún esté vivo (evita hilos duplicados).
        # Importante: nunca unirse a sí mismo (evita RuntimeError en replay).
        if (self._update_thread is not None
                and self._update_thread is not threading.current_thread()
                and self._update_thread.is_alive()):
            self._is_running = False
            self._update_thread.join(timeout=0.5)

        self._is_running = True
        self._update_thread = threading.Thread(target=self._update_position, daemon=True)
        self._update_thread.start()

    def _stop_update_thread(self) -> None:
        """Detiene el hilo de actualización de posición."""
        self._is_running = False
        if self._update_thread is not None and self._update_thread.is_alive():
            self._update_thread.join(timeout=1.0)

    def _update_position(self) -> None:
        """
        Actualiza la posición de reproducción en un hilo separado.

        Detecta el fin de pista de dos formas:
          * get_busy() pasa de True a False durante N ticks (400 ms),
            lo que funciona incluso con duración desconocida.
          * posición >= duración conocida.
        """
        last_callback_time = 0.0
        idle_ticks = 0

        while self._is_running and self._state == PlayerState.PLAYING:
            try:
                with self._lock:
                    pos = pygame.mixer.music.get_pos()
                    busy = pygame.mixer.music.get_busy()

                # get_pos() puede devolver -1 si no hay música; en ese caso
                # se conserva la última posición conocida.
                if pos >= 0:
                    self._position = self._seek_base + pos / 1000.0

                # --- Detección de fin de pista -------------------------
                if busy:
                    idle_ticks = 0
                else:
                    idle_ticks += 1

                ended_by_duration = (
                    self._duration > 0 and self._position >= self._duration - 0.05
                )
                ended_by_idle = (
                    idle_ticks >= END_IDLE_TICKS
                    and self._position > POSITION_MIN_FOR_END
                )

                if ended_by_duration or ended_by_idle:
                    # Ajustar la posición final a la duración conocida
                    if ended_by_duration:
                        self._position = self._duration
                    logger.info("Canción terminada")
                    if self._on_track_end:
                        self._on_track_end()
                    break

                # --- Callback de posición (throttled a 10 Hz) ----------
                current_time = time.time()
                if self._on_position_update and (current_time - last_callback_time >= 0.1):
                    self._on_position_update(self._position, self._duration)
                    last_callback_time = current_time

                time.sleep(0.05)
            except pygame.error as e:
                logger.error(f"Error de pygame en actualización de posición: {e}")
                break
            except Exception as e:
                logger.error(f"Error inesperado en actualización de posición: {e}")
                break

    # ------------------------------------------------------------------
    # Limpieza
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Limpia recursos del reproductor."""
        self.stop()
        try:
            pygame.mixer.quit()
        except Exception as e:
            logger.warning(f"Error al cerrar el mixer: {e}")