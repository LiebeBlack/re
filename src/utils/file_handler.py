"""
FileHandler - Manejo de archivos y directorios para Musik Player
"""

import os
import logging
from pathlib import Path
from typing import List, Optional

# Configurar logging
logger = logging.getLogger(__name__)


class FileHandler:
    """Clase para manejar operaciones de archivos y directorios"""
    
    # Formatos admitidos: los decodifican pygame/SDL, soundfile o mutagen
    SUPPORTED_FORMATS = {
        '.mp3', '.wav', '.ogg', '.flac',          # básicos / lossless
        '.m4a', '.mp4', '.aac',                   # AAC / ALAC (contenedor MP4)
        '.opus', '.aif', '.aiff',                 # Opus / AIFF
    }

    # Etiquetas para los diálogos de archivo
    FILE_DIALOG_PATTERNS = [
        ("Archivos de audio", "*.mp3 *.wav *.ogg *.flac *.m4a *.mp4 *.aac *.opus *.aif *.aiff"),
        ("Audio sin pérdida", "*.flac *.wav *.m4a *.aif *.aiff"),
        ("MP3", "*.mp3"), ("WAV", "*.wav"), ("FLAC", "*.flac"),
        ("OGG", "*.ogg"), ("AAC / M4A", "*.m4a *.mp4 *.aac"), ("OPUS", "*.opus"),
        ("Todos los archivos", "*.*"),
    ]
    
    @staticmethod
    def is_audio_file(file_path: str) -> bool:
        """
        Verifica si un archivo es un formato de audio soportado
        
        Args:
            file_path: Ruta del archivo a verificar
            
        Returns:
            True si el formato es soportado, False en caso contrario
        """
        if not file_path or not isinstance(file_path, str):
            return False
        
        try:
            return Path(file_path).suffix.lower() in FileHandler.SUPPORTED_FORMATS
        except Exception as e:
            logger.warning(f"Error al verificar formato de archivo: {e}")
            return False
    
    @staticmethod
    def get_audio_files(directory: str) -> List[str]:
        """
        Obtiene todos los archivos de audio de un directorio
        
        Args:
            directory: Ruta del directorio a escanear
            
        Returns:
            Lista de rutas de archivos de audio encontrados
        """
        if not directory or not isinstance(directory, str):
            logger.warning("Directorio inválido")
            return []
        
        audio_files = []
        path = Path(directory)
        
        if not path.exists():
            logger.warning(f"Directorio no existe: {directory}")
            return []
        
        if not path.is_dir():
            logger.warning(f"La ruta no es un directorio: {directory}")
            return []
        
        try:
            for file in path.iterdir():
                if file.is_file() and FileHandler.is_audio_file(str(file)):
                    audio_files.append(str(file))
        except PermissionError as e:
            logger.error(f"Permiso denegado al leer directorio: {e}")
        except Exception as e:
            logger.error(f"Error al escanear directorio: {e}")
        
        return sorted(audio_files)
    
    @staticmethod
    def file_exists(file_path: str) -> bool:
        """
        Verifica si un archivo existe
        
        Args:
            file_path: Ruta del archivo a verificar
            
        Returns:
            True si el archivo existe, False en caso contrario
        """
        if not file_path or not isinstance(file_path, str):
            return False
        
        try:
            return Path(file_path).exists()
        except Exception as e:
            logger.warning(f"Error al verificar existencia de archivo: {e}")
            return False
    
    @staticmethod
    def get_file_name(file_path: str) -> str:
        """
        Obtiene el nombre del archivo sin extensión
        
        Args:
            file_path: Ruta del archivo
            
        Returns:
            Nombre del archivo sin extensión
        """
        return Path(file_path).stem
    
    @staticmethod
    def get_file_extension(file_path: str) -> str:
        """
        Obtiene la extensión del archivo
        
        Args:
            file_path: Ruta del archivo
            
        Returns:
            Extensión del archivo (incluyendo el punto)
        """
        return Path(file_path).suffix.lower()
    
    @staticmethod
    def ensure_directory(directory: str) -> None:
        """
        Asegura que un directorio existe, creándolo si es necesario
        
        Args:
            directory: Ruta del directorio
        """
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def get_file_size(file_path: str) -> int:
        """
        Obtiene el tamaño de un archivo en bytes
        
        Args:
            file_path: Ruta del archivo
            
        Returns:
            Tamaño del archivo en bytes, 0 si no existe
        """
        try:
            return Path(file_path).stat().st_size
        except (OSError, FileNotFoundError):
            return 0
