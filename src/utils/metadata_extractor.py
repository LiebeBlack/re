"""
MetadataExtractor - Extracción de metadatos de archivos de audio
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

# Configurar logging
logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Clase para extraer metadatos de archivos de audio"""
    
    @staticmethod
    def extract_metadata(file_path: str) -> Dict[str, Any]:
        """
        Extrae metadatos de un archivo de audio
        
        Args:
            file_path: Ruta del archivo de audio
            
        Returns:
            Diccionario con metadatos (title, artist, album, duration, etc.)
        """
        metadata = {
            "title": None,
            "artist": None,
            "album": None,
            "duration": None,
            "year": None,
            "genre": None
        }
        
        try:
            # Intentar usar mutagen si está disponible
            try:
                from mutagen import File
                from mutagen.mp3 import MP3
                from mutagen.flac import FLAC
                from mutagen.oggvorbis import OggVorbis
                from mutagen.wave import WAVE
                
                audio_file = File(file_path)
                
                if audio_file:
                    # Extraer metadatos según el formato
                    if isinstance(audio_file, MP3):
                        metadata.update(MetadataExtractor._extract_mp3_metadata(audio_file))
                    elif isinstance(audio_file, FLAC):
                        metadata.update(MetadataExtractor._extract_flac_metadata(audio_file))
                    elif isinstance(audio_file, OggVorbis):
                        metadata.update(MetadataExtractor._extract_ogg_metadata(audio_file))
                    elif isinstance(audio_file, WAVE):
                        metadata.update(MetadataExtractor._extract_wav_metadata(audio_file))
                    
                    # Duración
                    if hasattr(audio_file, 'info') and hasattr(audio_file.info, 'length'):
                        metadata["duration"] = audio_file.info.length
                    
                    logger.debug(f"Metadatos extraídos con mutagen: {file_path}")
                    
            except ImportError:
                logger.debug("Mutagen no disponible, usando método básico")
                metadata.update(MetadataExtractor._extract_basic_metadata(file_path))
            
        except Exception as e:
            logger.warning(f"Error al extraer metadatos de {file_path}: {e}")
            metadata.update(MetadataExtractor._extract_basic_metadata(file_path))
        
        # Normalizar metadatos
        return MetadataExtractor._normalize_metadata(metadata, file_path)
    
    @staticmethod
    def _extract_mp3_metadata(audio_file) -> Dict[str, Any]:
        """Extrae metadatos de archivos MP3"""
        metadata = {}
        
        if audio_file.tags:
            tags = audio_file.tags
            
            # Mapear etiquetas comunes
            tag_map = {
                'TIT2': 'title',
                'TPE1': 'artist',
                'TALB': 'album',
                'TDRC': 'year',
                'TCON': 'genre'
            }
            
            for tag, key in tag_map.items():
                if tag in tags:
                    value = tags[tag]
                    if value:
                        metadata[key] = str(value[0]) if isinstance(value, list) else str(value)
        
        return metadata
    
    @staticmethod
    def _extract_flac_metadata(audio_file) -> Dict[str, Any]:
        """Extrae metadatos de archivos FLAC"""
        metadata = {}
        
        if audio_file:
            # FLAC usa diccionario directo
            if 'TITLE' in audio_file:
                metadata['title'] = str(audio_file['TITLE'][0])
            if 'ARTIST' in audio_file:
                metadata['artist'] = str(audio_file['ARTIST'][0])
            if 'ALBUM' in audio_file:
                metadata['album'] = str(audio_file['ALBUM'][0])
            if 'DATE' in audio_file:
                metadata['year'] = str(audio_file['DATE'][0])
            if 'GENRE' in audio_file:
                metadata['genre'] = str(audio_file['GENRE'][0])
        
        return metadata
    
    @staticmethod
    def _extract_ogg_metadata(audio_file) -> Dict[str, Any]:
        """Extrae metadatos de archivos OGG"""
        metadata = {}
        
        if audio_file:
            # OGG Vorbis usa diccionario directo
            if 'TITLE' in audio_file:
                metadata['title'] = str(audio_file['TITLE'][0])
            if 'ARTIST' in audio_file:
                metadata['artist'] = str(audio_file['ARTIST'][0])
            if 'ALBUM' in audio_file:
                metadata['album'] = str(audio_file['ALBUM'][0])
            if 'DATE' in audio_file:
                metadata['year'] = str(audio_file['DATE'][0])
            if 'GENRE' in audio_file:
                metadata['genre'] = str(audio_file['GENRE'][0])
        
        return metadata
    
    @staticmethod
    def _extract_wav_metadata(audio_file) -> Dict[str, Any]:
        """Extrae metadatos de archivos WAV"""
        # WAV no tiene metadatos estándar, devuelve vacío
        return {}
    
    @staticmethod
    def _extract_basic_metadata(file_path: str) -> Dict[str, Any]:
        """Extrae metadatos básicos usando el nombre del archivo"""
        return {
            "title": Path(file_path).stem,
            "artist": "Unknown",
            "album": None,
            "duration": None,
            "year": None,
            "genre": None
        }
    
    @staticmethod
    def _normalize_metadata(metadata: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """
        Normaliza los metadatos asegurando que todos los campos tengan valores
        
        Args:
            metadata: Diccionario de metadatos
            file_path: Ruta del archivo (para fallback)
            
        Returns:
            Diccionario de metadatos normalizado
        """
        # Fallbacks
        if not metadata.get("title"):
            metadata["title"] = Path(file_path).stem
        
        if not metadata.get("artist"):
            metadata["artist"] = "Unknown"
        
        if not metadata.get("album"):
            metadata["album"] = ""
        
        if not metadata.get("year"):
            metadata["year"] = ""
        
        if not metadata.get("genre"):
            metadata["genre"] = ""
        
        return metadata
    
    @staticmethod
    def get_duration(file_path: str) -> Optional[float]:
        """
        Obtiene la duración de un archivo de audio
        
        Args:
            file_path: Ruta del archivo
            
        Returns:
            Duración en segundos, None si no se puede obtener
        """
        try:
            # Intentar con mutagen
            try:
                from mutagen import File
                audio_file = File(file_path)
                if audio_file and hasattr(audio_file, 'info') and hasattr(audio_file.info, 'length'):
                    return audio_file.info.length
            except ImportError:
                pass
            
            # Fallback a pygame
            try:
                import pygame
                sound = pygame.mixer.Sound(file_path)
                return sound.get_length()
            except:
                pass
            
        except Exception as e:
            logger.warning(f"Error al obtener duración de {file_path}: {e}")
        
        return None
