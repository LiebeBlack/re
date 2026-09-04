"""
PlaylistManager - Gestión de lista de reproducción
"""

import logging
import random
import json
import os
from typing import List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

# Configurar ubicación de datos del usuario
if os.name == 'nt':  # Windows
    app_data = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / 'MusikPlayer'
else:  # macOS/Linux
    app_data = Path(os.path.expanduser('~')) / '.musikplayer'

try:
    app_data.mkdir(parents=True, exist_ok=True)
except Exception as e:
    logger.warning(f"No se pudo crear directorio de datos: {e}")
    import tempfile
    app_data = Path(tempfile.gettempdir()) / 'MusikPlayer'
    app_data.mkdir(parents=True, exist_ok=True)

PLAYLIST_FILE = app_data / 'musik_playlist.json'


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
    
    def to_dict(self) -> dict:
        """Convierte la pista a diccionario"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Track':
        """Crea una pista desde un diccionario"""
        return cls(**data)


class PlaylistManager:
    """Clase para gestionar la lista de reproducción"""
    
    def __init__(self, playlist_dir: Optional[str] = None):
        """
        Inicializa el gestor de playlist
        
        Args:
            playlist_dir: Directorio para guardar la playlist (default: usa configuración centralizada)
        """
        if playlist_dir:
            self._playlist_path = Path(playlist_dir) / 'musik_playlist.json'
        else:
            self._playlist_path = PLAYLIST_FILE
        
        self._tracks: List[Track] = []
        self._current_index: int = -1
        self._shuffle = False
        self._repeat_mode = 0  # 0: off, 1: all, 2: one
        self._shuffled_indices: List[int] = []
        self._shuffle_index = 0
        logger.info(f"PlaylistManager inicializado con ruta: {self._playlist_path}")
    
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

        # Si shuffle está activo, regenerar el orden para que la nueva
        # pista quede incluida en la rotación (sin romper el orden actual).
        if self._shuffle and len(self._tracks) > 1:
            self._generate_shuffle_order()

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

            # Con shuffle activo, regenerar el orden para eliminar
            # referencias obsoletas (evita IndexError en next/previous).
            if self._shuffle and len(self._tracks) > 0:
                self._generate_shuffle_order()

            logger.info(f"Pista removida: {track.title}")
            return True
        
        logger.warning(f"Índice fuera de rango: {index}")
        return False
    
    def clear(self) -> None:
        """Limpia la playlist"""
        self._tracks.clear()
        self._current_index = -1
        self._shuffled_indices = []
        self._shuffle_index = 0
    
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
    
    def set_shuffle(self, shuffle: bool) -> None:
        """
        Establece el modo shuffle
        
        Args:
            shuffle: True para activar shuffle, False para desactivar
        """
        self._shuffle = shuffle
        if shuffle and len(self._tracks) > 0:
            self._generate_shuffle_order()
        else:
            self._shuffled_indices = []
            self._shuffle_index = 0
        logger.info(f"Shuffle {'activado' if shuffle else 'desactivado'}")
    
    def get_shuffle(self) -> bool:
        """
        Obtiene el estado de shuffle
        
        Returns:
            True si shuffle está activo, False en caso contrario
        """
        return self._shuffle
    
    def _safe_shuffle_index(self, shuffle_position: int) -> Optional[int]:
        """
        Retorna el índice real de pista para una posición del orden shuffle,
        validando que sea un índice existente (los tracks pueden haberse
        removido y dejar referencias obsoletas).

        Args:
            shuffle_position: Posición dentro de _shuffled_indices.

        Returns:
            Índice de pista válido o None si es obsoleto.
        """
        if not (0 <= shuffle_position < len(self._shuffled_indices)):
            return None
        actual = self._shuffled_indices[shuffle_position]
        if 0 <= actual < len(self._tracks):
            return actual
        return None

    def _generate_shuffle_order(self) -> None:
        """Genera un orden aleatorio de reproducción"""
        indices = list(range(len(self._tracks)))
        random.shuffle(indices)
        
        # Si hay una pista actual, ponerla al inicio del orden para que
        # "next" no la vuelva a repetir inmediatamente.
        if self._current_index >= 0 and self._current_index in indices:
            indices.remove(self._current_index)
            indices.insert(0, self._current_index)
            self._shuffle_index = 0  # La pista actual está en la posición 0
        else:
            self._shuffle_index = -1  # "next" empezará en la posición 0
        
        self._shuffled_indices = indices
        logger.debug("Orden shuffle generado")
    
    def set_repeat_mode(self, mode: int) -> None:
        """
        Establece el modo de repetición
        
        Args:
            mode: 0: off, 1: all, 2: one
        """
        self._repeat_mode = max(0, min(2, mode))
        modes = ["Off", "Repeat All", "Repeat One"]
        logger.info(f"Repeat mode: {modes[self._repeat_mode]}")
    
    def get_repeat_mode(self) -> int:
        """
        Obtiene el modo de repetición
        
        Returns:
            0: off, 1: all, 2: one
        """
        return self._repeat_mode
    
    def next(self) -> Optional[Track]:
        """
        Avanza a la siguiente pista (considerando shuffle y repeat)
        
        Returns:
            Siguiente pista si existe, None en caso contrario
        """
        if not self._tracks:
            return None
        
        if self._shuffle:
            return self._next_shuffle()
        else:
            return self._next_normal()
    
    def _next_normal(self) -> Optional[Track]:
        """Avanza a la siguiente pista en modo normal"""
        if self._current_index < len(self._tracks) - 1:
            self._current_index += 1
            return self._tracks[self._current_index]
        elif self._repeat_mode == 1:  # Repeat all
            self._current_index = 0
            return self._tracks[0]
        return None
    
    def _next_shuffle(self) -> Optional[Track]:
        """Avanza a la siguiente pista en modo shuffle"""
        if not self._shuffled_indices:
            self._generate_shuffle_order()
        
        self._shuffle_index += 1
        
        if self._shuffle_index >= len(self._shuffled_indices):
            if self._repeat_mode == 1:  # Repeat all
                self._shuffle_index = 0
                random.shuffle(self._shuffled_indices)
            else:
                return None
        
        actual_index = self._safe_shuffle_index(self._shuffle_index)
        if actual_index is None:
            # Índice obsoleto (p. ej. tras remover pistas): regenerar
            self._generate_shuffle_order()
            self._shuffle_index = 0
            actual_index = self._safe_shuffle_index(0)
            if actual_index is None:
                return None
        
        self._current_index = actual_index
        return self._tracks[actual_index]
    
    def previous(self) -> Optional[Track]:
        """
        Retrocede a la pista anterior (considerando shuffle y repeat)
        
        Returns:
            Pista anterior si existe, None en caso contrario
        """
        if not self._tracks:
            return None
        
        if self._shuffle:
            return self._previous_shuffle()
        else:
            return self._previous_normal()
    
    def _previous_normal(self) -> Optional[Track]:
        """Retrocede a la pista anterior en modo normal"""
        if self._current_index > 0:
            self._current_index -= 1
            return self._tracks[self._current_index]
        elif self._repeat_mode == 1:  # Repeat all
            self._current_index = len(self._tracks) - 1
            return self._tracks[-1]
        return None
    
    def _previous_shuffle(self) -> Optional[Track]:
        """Retrocede a la pista anterior en modo shuffle"""
        if not self._shuffled_indices:
            self._generate_shuffle_order()
        
        if self._shuffle_index <= 0:
            if self._repeat_mode == 1:  # Repeat all
                self._shuffle_index = len(self._shuffled_indices) - 1
            else:
                self._shuffle_index = 0
        else:
            self._shuffle_index -= 1
        
        actual_index = self._safe_shuffle_index(self._shuffle_index)
        if actual_index is None:
            self._generate_shuffle_order()
            self._shuffle_index = 0
            actual_index = self._safe_shuffle_index(0)
            if actual_index is None:
                return None
        
        self._current_index = actual_index
        return self._tracks[actual_index]
    
    def save_playlist(self, file_path: Optional[str] = None) -> bool:
        """
        Guarda la playlist actual en un archivo JSON
        
        Args:
            file_path: Ruta del archivo (default: usa la ruta por defecto)
            
        Returns:
            True si se guardó exitosamente, False en caso contrario
        """
        try:
            save_path = Path(file_path) if file_path else self._playlist_path
            
            playlist_data = {
                "tracks": [track.to_dict() for track in self._tracks],
                "current_index": self._current_index,
                "shuffle": self._shuffle,
                "repeat_mode": self._repeat_mode
            }
            
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(playlist_data, f, indent=4, ensure_ascii=False)
            
            logger.info(f"Playlist guardada en: {save_path}")
            return True
        except Exception as e:
            logger.error(f"Error al guardar playlist: {e}")
            return False
    
    def load_playlist(self, file_path: Optional[str] = None) -> bool:
        """
        Carga una playlist desde un archivo JSON
        
        Args:
            file_path: Ruta del archivo (default: usa la ruta por defecto)
            
        Returns:
            True si se cargó exitosamente, False en caso contrario
        """
        try:
            load_path = Path(file_path) if file_path else self._playlist_path
            
            if not load_path.exists():
                logger.info(f"No existe archivo de playlist: {load_path}")
                return False
            
            with open(load_path, 'r', encoding='utf-8') as f:
                playlist_data = json.load(f)
            
            # Cargar pistas omitiendo las inválidas o cuyos archivos ya no existen
            tracks = []
            for track_data in playlist_data.get("tracks", []):
                try:
                    track = Track.from_dict(track_data)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Pista inválida en playlist guardada, omitida: {e}")
                    continue
                if track.is_valid():
                    tracks.append(track)
                else:
                    logger.warning(f"Archivo no existe, pista omitida: {track.file_path}")
            self._tracks = tracks
            
            # Cargar configuración
            self._current_index = playlist_data.get("current_index", -1)
            if self._current_index >= len(self._tracks):
                self._current_index = len(self._tracks) - 1 if self._tracks else -1
            self._shuffle = playlist_data.get("shuffle", False)
            self._repeat_mode = playlist_data.get("repeat_mode", 0)
            
            # Regenerar orden shuffle si está activo
            if self._shuffle and len(self._tracks) > 0:
                self._generate_shuffle_order()
            
            logger.info(f"Playlist cargada desde: {load_path}")
            logger.info(f"{len(self._tracks)} pistas cargadas")
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Error al decodificar JSON de playlist: {e}")
            return False
        except Exception as e:
            logger.error(f"Error al cargar playlist: {e}")
            return False
    
    def export_playlist(self, file_path: str) -> bool:
        """
        Exporta la playlist actual a un archivo específico
        
        Args:
            file_path: Ruta del archivo de destino
            
        Returns:
            True si se exportó exitosamente, False en caso contrario
        """
        return self.save_playlist(file_path)
    
    def create_m3u_playlist(self, file_path: str) -> bool:
        """
        Crea un archivo M3U de la playlist actual
        
        Args:
            file_path: Ruta del archivo M3U
            
        Returns:
            True si se creó exitosamente, False en caso contrario
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                for track in self._tracks:
                    f.write(f"#EXTINF:{int(track.duration)},{track.artist} - {track.title}\n")
                    f.write(f"{track.file_path}\n")
            
            logger.info(f"Playlist M3U creada en: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error al crear playlist M3U: {e}")
            return False
