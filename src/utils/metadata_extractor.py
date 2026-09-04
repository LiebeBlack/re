"""
MetadataExtractor - Extracción de metadatos técnicos y carátulas.

Ofrece dos niveles de información:
  * Etiquetas (title, artist, album, year, genre...) vía mutagen (opcional).
  * Metadatos técnicos (formato, codec, sample rate, canales, bit depth,
    bitrate, duración) vía mutagen o soundfile.
  * Carátula embebida (APIC / FLAC pictures / MP4 covr) -> PNG en caché.

Sin mutagen ni soundfile instalados, degrada a datos básicos del nombre
de archivo (la app nunca debe fallar por falta de dependencias opcionales).
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Extensiones sin pérdida (para la insignia "Lossless" en la UI)
LOSSLESS_FORMATS = {".flac", ".wav", ".alac", ".m4a", ".aiff", ".aif", ".ape", ".wv", ".wma"}


class MetadataExtractor:
    """Clase para extraer metadatos técnicos y carátulas de audio."""

    _art_cache_dir: Optional[Path] = None

    # ------------------------------------------------------------------
    # Metadatos
    # ------------------------------------------------------------------

    @staticmethod
    def extract_metadata(file_path: str) -> Dict[str, Any]:
        """
        Extrae metadatos (etiquetas + técnicos) de un archivo de audio.

        Args:
            file_path: Ruta del archivo de audio.

        Returns:
            Diccionario con title, artist, album, duration, year, genre,
            format, codec, sample_rate, channels, bit_depth, bitrate,
            lossless y file_size.
        """
        metadata = {
            "title": None, "artist": None, "album": None, "duration": None,
            "year": None, "genre": None, "format": None, "codec": None,
            "sample_rate": None, "channels": None, "bit_depth": None,
            "bitrate": None, "lossless": False, "file_size": 0,
        }

        try:
            metadata["format"] = Path(file_path).suffix.lower().lstrip(".").upper()
            metadata["file_size"] = Path(file_path).stat().st_size
            metadata["lossless"] = Path(file_path).suffix.lower() in LOSSLESS_FORMATS
        except OSError:
            pass

        mutagen_audio = None
        try:
            from mutagen import File as MutagenFile
            mutagen_audio = MutagenFile(file_path)
            if mutagen_audio is not None:
                metadata.update(MetadataExtractor._extract_tags(mutagen_audio, file_path))
        except Exception as e:
            logger.debug(f"mutagen no disponible para {file_path}: {e}")

        # Técnicos: primero info de mutagen, luego soundfile
        if mutagen_audio is not None and getattr(mutagen_audio, "info", None) is not None:
            info = mutagen_audio.info
            if getattr(info, "length", 0):
                metadata["duration"] = float(info.length)
            if getattr(info, "sample_rate", 0):
                metadata["sample_rate"] = int(info.sample_rate)
            channels = getattr(info, "channels", None)
            if channels is not None:
                metadata["channels"] = int(channels)
            bits = getattr(info, "bits_per_sample", None)
            if bits is not None:
                metadata["bit_depth"] = int(bits)
            bitrate = getattr(info, "bitrate", None)
            if bitrate:
                metadata["bitrate"] = int(bitrate)
            metadata["codec"] = MetadataExtractor._codec_name(mutagen_audio)
        else:
            metadata.update(MetadataExtractor._probe_soundfile(file_path))

        # Bitrate calculado si falta (lossless: file_size*8/duration)
        duration = metadata.get("duration") or 0
        if not metadata.get("bitrate") and duration > 0 and metadata.get("file_size"):
            metadata["bitrate"] = int(metadata["file_size"] * 8 / duration)

        return MetadataExtractor._normalize_metadata(metadata, file_path)

    @staticmethod
    def _extract_tags(audio_file, file_path: str) -> Dict[str, Any]:
        """Extrae etiquetas según el tipo de contenedor."""
        meta: Dict[str, Any] = {}
        try:
            # MP4 / M4A (AAC / ALAC): etiquetas estilo dict
            if audio_file.__class__.__name__ in ("MP4", "MP4Tags"):
                tags = audio_file.tags if hasattr(audio_file, "tags") else None
                if tags:
                    def _v(key):
                        val = tags.get(key)
                        if isinstance(val, list) and val:
                            val = val[0]
                        return val

                    map_mp4 = {
                        "\xa9nam": "title", "\xa9ART": "artist", "\xa9alb": "album",
                        "\xa9day": "year", "\xa9gen": "genre",
                    }
                    for key, field in map_mp4.items():
                        val = _v(key)
                        if val is not None:
                            meta[field] = str(val).strip("\x00")
                return meta

            # ID3 (MP3) / APE / etc.: usar frame IDs estándar
            tags = getattr(audio_file, "tags", None)
            if tags is not None and hasattr(tags, "get"):
                id3_map = {"TIT2": "title", "TPE1": "artist", "TALB": "album",
                           "TDRC": "year", "TCON": "genre"}
                for frame_id, field in id3_map.items():
                    if frame_id in tags:
                        meta[field] = str(tags[frame_id])
                return meta

            # Vorbis / FLAC / Ogg / Opus: diccionario directo
            direct_map = {"title": "TITLE", "artist": "ARTIST", "album": "ALBUM",
                          "year": "DATE", "genre": "GENRE"}
            for field, key in direct_map.items():
                val = audio_file.get(key)
                if val:
                    meta[field] = str(val[0] if isinstance(val, list) else val)
        except Exception as e:
            logger.debug(f"Error extrayendo etiquetas de {file_path}: {e}")
        return meta

    @staticmethod
    def _probe_soundfile(file_path: str) -> Dict[str, Any]:
        """Rellena datos técnicos con soundfile (sin mutagen)."""
        meta: Dict[str, Any] = {}
        try:
            import soundfile as sf
            info = sf.info(file_path)
            meta["duration"] = float(info.duration)
            meta["sample_rate"] = int(info.samplerate)
            meta["channels"] = int(info.channels)
            subtype = str(getattr(info, "subtype", "") or "")
            bits = "".join(ch for ch in subtype if ch.isdigit())
            if bits:
                meta["bit_depth"] = int(bits)
            meta["codec"] = str(getattr(info, "format", "") or "").split(" ")[0]
        except Exception as e:
            logger.debug(f"soundfile no pudo leer {file_path}: {e}")
        return meta

    @staticmethod
    def _codec_name(audio_file) -> str:
        """Nombre de codec legible a partir del objeto mutagen."""
        name = audio_file.__class__.__name__
        codec_map = {
            "MP3": "MPEG Layer 3", "FLAC": "FLAC", "WAVE": "PCM",
            "OggVorbis": "Vorbis", "OggOpus": "Opus", "MP4": "AAC/ALAC",
            "AIFF": "PCM", "APE": "Monkey's Audio", "WavPack": "WavPack",
        }
        for cls, label in codec_map.items():
            if cls in name:
                return label
        return name.replace("_", " ")

    @staticmethod
    def _normalize_metadata(metadata: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Completa valores ausentes con fallbacks seguros."""
        if not metadata.get("title"):
            metadata["title"] = Path(file_path).stem
        metadata.setdefault("artist", None)
        if not metadata.get("artist"):
            metadata["artist"] = "Unknown"
        for field in ("album", "year", "genre", "format", "codec"):
            if not metadata.get(field):
                metadata[field] = ""
        if not metadata.get("duration"):
            metadata["duration"] = 0.0
        if metadata.get("bitrate"):
            metadata["bitrate"] = int(metadata["bitrate"])
        return metadata

    # ------------------------------------------------------------------
    # Carátula embebida
    # ------------------------------------------------------------------

    @staticmethod
    def get_art_cache_dir() -> Path:
        """Directorio de caché de carátulas (se crea si no existe)."""
        if MetadataExtractor._art_cache_dir is None:
            base = Path(tempfile.gettempdir()) / "musikplayer_art"
            try:
                base.mkdir(parents=True, exist_ok=True)
                MetadataExtractor._art_cache_dir = base
            except OSError:
                MetadataExtractor._art_cache_dir = base  # tempdir siempre escribe
        return MetadataExtractor._art_cache_dir

    @staticmethod
    def extract_album_art(file_path: str) -> Optional[str]:
        """
        Extrae la carátula embebida del archivo y la guarda como PNG en caché.

        Args:
            file_path: Ruta del archivo de audio.

        Returns:
            Ruta del PNG si existe carátula, None en caso contrario.
        """
        try:
            from mutagen import File as MutagenFile
        except Exception:
            return None

        try:
            audio = MutagenFile(file_path)
            if audio is None:
                return None

            art_data: Optional[bytes] = None

            # FLAC / Ogg: bloques de imagen
            pictures = getattr(audio, "pictures", None)
            if pictures:
                art_data = pictures[0].data

            # ID3 (MP3): frames APIC
            if art_data is None and getattr(audio, "tags", None) is not None:
                tags = audio.tags
                for key in ("APIC:", "APIC"):
                    frame = tags.get(key)
                    if frame is not None:
                        frame_list = frame if isinstance(frame, list) else [frame]
                        for f in frame_list:
                            if getattr(f, "data", None):
                                art_data = bytes(f.data)
                                break
                        if art_data:
                            break

            # MP4 / M4A: covr (datos JPEG/PNG o lista)
            if art_data is None:
                tags = getattr(audio, "tags", None)
                if tags is not None:
                    covr = tags.get("covr")
                    if covr:
                        first = covr[0]
                        art_data = bytes(getattr(first, "imagebytes", None) or first)

            if not art_data:
                return None

            # Normalizar a PNG con Pillow si está disponible
            cache = MetadataExtractor.get_art_cache_dir()
            out_path = cache / f"{Path(file_path).stem.replace(' ', '_')}.png"
            try:
                from PIL import Image
                import io
                with Image.open(io.BytesIO(art_data)) as img:
                    img = img.convert("RGB")
                    # Limitar tamaño para no cargar la UI (máx 512 px)
                    img.thumbnail((512, 512), Image.LANCZOS)
                    img.save(out_path, "PNG")
                return str(out_path)
            except Exception:
                # Guardar crudo con extensión adecuada si no hay Pillow
                if out_path.exists():
                    return str(out_path)
                return None
        except Exception as e:
            logger.debug(f"No se pudo extraer carátula de {file_path}: {e}")
            return None

    # ------------------------------------------------------------------
    # Duración (método público de compatibilidad)
    # ------------------------------------------------------------------

    @staticmethod
    def get_duration(file_path: str) -> Optional[float]:
        """
        Obtiene la duración de un archivo de audio.

        Args:
            file_path: Ruta del archivo.

        Returns:
            Duración en segundos o None.
        """
        try:
            meta = MetadataExtractor.extract_metadata(file_path)
            return meta.get("duration") or None
        except Exception as e:
            logger.warning(f"Error al obtener duración de {file_path}: {e}")
        return None