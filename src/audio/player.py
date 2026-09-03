"""
AudioPlayer - Motor de reproducción de audio usando pygame
"""

import pygame
import threading
import time
import logging
from typing import Optional, Callable
from enum import Enum
from pathlib import Path


class PlayerState(Enum):
    """Estados del reproductor de audio"""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    LOADING = "loading"
    ERROR = "error"


logger = logging.getLogger(__name__)


class AudioPlayer:
    """Clase principal para manejar la reproducción de audio"""
    
    def __init__(self):
        """Inicializa el reproductor de audio"""
        self._current_file: Optional[str] = None
        self._state = PlayerState.STOPPED
        self._volume = 0.7
        self._position = 0.0
        self._duration = 0.0
        self._is_running = False
        self._update_thread: Optional[threading.Thread] = None
        self._on_position_update: Optional[Callable[[float, float], None]] = None
        self._on_track_end: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._lock = threading.Lock()
        
        # Inicializar pygame mixer
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.music.set_volume(self._volume)
            logger.info("AudioPlayer inicializado correctamente")
        except pygame.error as e:
            logger.error(f"Error al inicializar pygame mixer: {e}")
            self._state = PlayerState.ERROR
            raise RuntimeError(f"Error al inicializar pygame mixer: {e}")
        except Exception as e:
            logger.error(f"Error inesperado al inicializar: {e}")
            self._state = PlayerState.ERROR
            raise RuntimeError(f"Error inesperado al inicializar: {e}")
    
    def load(self, file_path: str) -> bool:
        """
        Carga un archivo de audio
        
        Args:
            file_path: Ruta del archivo a cargar
            
        Returns:
            True si se cargó exitosamente, False en caso contrario
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
                self._duration = self._estimate_duration(file_path)
                
                self._state = PlayerState.STOPPED
                logger.info(f"Archivo cargado exitosamente: {file_path}")
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
    
    def play(self) -> bool:
        """
        Inicia la reproducción
        
        Returns:
            True si se inició exitosamente, False en caso contrario
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
    
    def pause(self) -> bool:
        """
        Pausa la reproducción
        
        Returns:
            True si se pausó exitosamente, False en caso contrario
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
        Reanuda la reproducción pausada
        
        Returns:
            True si se reanudó exitosamente, False en caso contrario
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
        Detiene la reproducción
        
        Returns:
            True si se detuvo exitosamente, False en caso contrario
        """
        with self._lock:
            try:
                logger.info("Deteniendo reproducción")
                pygame.mixer.music.stop()
                self._state = PlayerState.STOPPED
                self._position = 0.0
                self._stop_update_thread()
                return True
            except pygame.error as e:
                logger.error(f"Error al detener: {e}")
                if self._on_error:
                    self._on_error(f"Error al detener: {e}")
                return False
    
    def set_volume(self, volume: float) -> None:
        """
        Establece el volumen de reproducción
        
        Args:
            volume: Valor de volumen entre 0.0 y 1.0
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
        Obtiene el volumen actual
        
        Returns:
            Valor de volumen entre 0.0 y 1.0
        """
        return self._volume
    
    def get_state(self) -> PlayerState:
        """
        Obtiene el estado actual del reproductor
        
        Returns:
            Estado actual del reproductor
        """
        return self._state
    
    def get_position(self) -> float:
        """
        Obtiene la posición actual en segundos
        
        Returns:
            Posición actual en segundos
        """
        return self._position
    
    def get_duration(self) -> float:
        """
        Obtiene la duración total de la canción en segundos
        
        Returns:
            Duración total en segundos
        """
        return self._duration
    
    def seek(self, position: float) -> bool:
        """
        Busca una posición específica en la canción
        
        Args:
            position: Posición en segundos
            
        Returns:
            True si se realizó exitosamente, False en caso contrario
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
    
    def set_position_callback(self, callback: Callable[[float, float], None]) -> None:
        """
        Establece el callback para actualizaciones de posición
        
        Args:
            callback: Función que recibe (posición_actual, duración_total)
        """
        self._on_position_update = callback
    
    def set_track_end_callback(self, callback: Callable[[], None]) -> None:
        """
        Establece el callback cuando termina una canción
        
        Args:
            callback: Función a llamar cuando termina la canción
        """
        self._on_track_end = callback
    
    def set_error_callback(self, callback: Callable[[str], None]) -> None:
        """
        Establece el callback para errores
        
        Args:
            callback: Función a llamar cuando ocurre un error
        """
        self._on_error = callback
    
    def _start_update_thread(self) -> None:
        """Inicia el hilo de actualización de posición de forma robusta"""
        # Detener un hilo previo que aún esté vivo para evitar hilos duplicados
        if self._update_thread and self._update_thread.is_alive():
            self._is_running = False
            self._update_thread.join(timeout=0.5)
        
        self._is_running = True
        self._update_thread = threading.Thread(target=self._update_position, daemon=True)
        self._update_thread.start()
    
    def _stop_update_thread(self) -> None:
        """Detiene el hilo de actualización de posición"""
        self._is_running = False
        if self._update_thread:
            self._update_thread.join(timeout=1.0)
    
    def _update_position(self) -> None:
        """Actualiza la posición de reproducción en un hilo separado optimizado"""
        import time
        last_callback_time = 0
        
        while self._is_running and self._state == PlayerState.PLAYING:
            try:
                with self._lock:
                    pos = pygame.mixer.music.get_pos()
                    if pos >= 0:
                        self._position = pos / 1000.0
                    else:
                        self._position = 0
                
                # Callback con throttling (máximo 10 veces por segundo)
                current_time = time.time()
                if self._on_position_update and (current_time - last_callback_time >= 0.1):
                    self._on_position_update(self._position, self._duration)
                    last_callback_time = current_time
                
                # Verificar si la canción terminó
                if self._duration > 0 and self._position >= self._duration:
                    logger.info("Canción terminada")
                    if self._on_track_end:
                        self._on_track_end()
                    break
                
                time.sleep(0.05)  # Reducido para mejor rendimiento
            except pygame.error as e:
                logger.error(f"Error de pygame en actualización de posición: {e}")
                break
            except Exception as e:
                logger.error(f"Error inesperado en actualización de posición: {e}")
                break
    
    def _estimate_duration(self, file_path: str) -> float:
        """
        Estima la duración del archivo de audio
        
        Args:
            file_path: Ruta del archivo
            
        Returns:
            Duración estimada en segundos
        """
        try:
            # Intentar obtener la duración usando pygame
            sound = pygame.mixer.Sound(file_path)
            duration = sound.get_length()
            logger.debug(f"Duración estimada para {file_path}: {duration}s")
            return duration
        except pygame.error as e:
            logger.warning(f"No se pudo estimar duración con pygame: {e}")
            # Si falla, retornar 0 (se actualizará durante la reproducción)
            return 0.0
        except Exception as e:
            logger.warning(f"Error inesperado al estimar duración: {e}")
            return 0.0
    
    def cleanup(self) -> None:
        """Limpia recursos del reproductor"""
        self.stop()
        pygame.mixer.quit()
