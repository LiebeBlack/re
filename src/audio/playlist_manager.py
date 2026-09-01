"""
PlaylistManager - Gestión de lista de reproducción
"""

import logging
from typing import List, Optional
from dataclasses import dataclass
from pathlib import Path

# Configurar logging
logger = logging.getLogger(__name__)


@dataclass
class Track:
    """Representa una pista de audio"""
    file_path: str
    title: str
    artist: str = "Unknown"
    duration: float = 0.0
    
    def __post_init__(self):
        """Valida los datos después de la inicialización"""
        if not self.file_path or not isinstance(self.file_path, str):
            raise ValueError("file_path debe ser una cadena no vacía")
        if not self.title or not isinstance(self.title, str):
            raise ValueError("title debe ser una cadena no vacía")
        if not isinstance(self.artist, str):
            raise ValueError("artist debe ser una cadena")
        if not isinstance(self.duration, (int, float)) or self.duration < 0:
            raise ValueError("duration debe ser un número no negativo")
    
    def __str__(self) -> str:
        """Representación en string de la pista"""
        return f"{self.title} - {self.artist}"
    
    def is_valid(self) -> bool:
        """Verifica si la pista es válida (archivo existe)"""
        return Path(self.file_path).exists() and Path(self.file_path).is_file()


class PlaylistManager:
    """Clase para gestionar la lista de reproducción"""
    
    def __init__(self):
        """Inicializa el gestor de playlist"""
        self._tracks: List[Track] = []
        self._current_index: int = -1
        logger.info("PlaylistManager inicializado")
    
    def add_track(self, track: Track) -> bool:
        """
        Agrega una pista a la playlist
        
        Args:
            track: Pista a agregar
            
        Returns:
            True si se agregó exitosamente, False en caso contrario
        """
        if not isinstance(track, Track):
            logger.error("Intento de agregar objeto que no es Track")
            return False
        
        if not track.is_valid():
            logger.warning(f"Archivo no válido: {track.file_path}")
            return False
        
        self._tracks.append(track)
        logger.info(f"Pista agregada: {track.title}")
        return True
    
    def add_tracks(self, tracks: List[Track]) -> int:
        """
        Agrega múltiples pistas a la playlist
        
        Args:
            tracks: Lista de pistas a agregar
            
        Returns:
            Número de pistas agregadas exitosamente
        """
        if not isinstance(tracks, list):
            logger.error("tracks debe ser una lista")
            return 0
        
        added_count = 0
        for track in tracks:
            if self.add_track(track):
                added_count += 1
        
        logger.info(f"{added_count} pistas agregadas de {len(tracks)} intentadas")
        return added_count
    
    def remove_track(self, index: int) -> bool:
        """
        Remueve una pista de la playlist
        
        Args:
            index: Índice de la pista a remover
            
        Returns:
            True si se removió exitosamente, False en caso contrario
        """
        if not isinstance(index, int):
            logger.error("Índice debe ser un entero")
            return False
        
        if 0 <= index < len(self._tracks):
            track = self._tracks[index]
            # Si removemos la pista actual, ajustar el índice
            if index == self._current_index:
                self._current_index = -1
            elif index < self._current_index:
                self._current_index -= 1
            
            self._tracks.pop(index)
            logger.info(f"Pista removida: {track.title}")
            return True
        
        logger.warning(f"Índice fuera de rango: {index}")
        return False
    
    def clear(self) -> None:
        """Limpia la playlist"""
        self._tracks.clear()
        self._current_index = -1
    
    def get_track(self, index: int) -> Optional[Track]:
        """
        Obtiene una pista por su índice
        
        Args:
            index: Índice de la pista
            
        Returns:
            Pista si existe, None en caso contrario
        """
        if 0 <= index < len(self._tracks):
            return self._tracks[index]
        return None
    
    def get_current_track(self) -> Optional[Track]:
        """
        Obtiene la pista actual
        
        Returns:
            Pista actual si existe, None en caso contrario
        """
        if 0 <= self._current_index < len(self._tracks):
            return self._tracks[self._current_index]
        return None
    
    def get_next_track(self) -> Optional[Track]:
        """
        Obtiene la siguiente pista
        
        Returns:
            Siguiente pista si existe, None en caso contrario
        """
        if self._current_index < len(self._tracks) - 1:
            return self._tracks[self._current_index + 1]
        return None
    
    def get_previous_track(self) -> Optional[Track]:
        """
        Obtiene la pista anterior
        
        Returns:
            Pista anterior si existe, None en caso contrario
        """
        if self._current_index > 0:
            return self._tracks[self._current_index - 1]
        return None
    
    def next(self) -> Optional[Track]:
        """
        Avanza a la siguiente pista
        
        Returns:
            Siguiente pista si existe, None en caso contrario
        """
        if self._current_index < len(self._tracks) - 1:
            self._current_index += 1
            return self._tracks[self._current_index]
        return None
    
    def previous(self) -> Optional[Track]:
        """
        Retrocede a la pista anterior
        
        Returns:
            Pista anterior si existe, None en caso contrario
        """
        if self._current_index > 0:
            self._current_index -= 1
            return self._tracks[self._current_index]
        return None
    
    def set_current_index(self, index: int) -> bool:
        """
        Establece el índice de la pista actual
        
        Args:
            index: Índice a establecer
            
        Returns:
            True si se estableció exitosamente, False en caso contrario
        """
        if 0 <= index < len(self._tracks):
            self._current_index = index
            return True
        return False
    
    def get_current_index(self) -> int:
        """
        Obtiene el índice de la pista actual
        
        Returns:
            Índice de la pista actual (-1 si no hay pista actual)
        """
        return self._current_index
    
    def get_all_tracks(self) -> List[Track]:
        """
        Obtiene todas las pistas de la playlist
        
        Returns:
            Lista de todas las pistas
        """
        return self._tracks.copy()
    
    def get_track_count(self) -> int:
        """
        Obtiene el número de pistas en la playlist
        
        Returns:
            Número de pistas
        """
        return len(self._tracks)
    
    def is_empty(self) -> bool:
        """
        Verifica si la playlist está vacía
        
        Returns:
            True si está vacía, False en caso contrario
        """
        return len(self._tracks) == 0
    
    def has_track(self, file_path: str) -> bool:
        """
        Verifica si una pista ya está en la playlist
        
        Args:
            file_path: Ruta del archivo a verificar
            
        Returns:
            True si la pista está en la playlist, False en caso contrario
        """
        return any(track.file_path == file_path for track in self._tracks)
