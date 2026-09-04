"""
ConfigManager - Gestión de configuración y persistencia
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field

# Configurar logging
logger = logging.getLogger(__name__)

# Configurar ubicación de datos del usuario
if os.name == 'nt':  # Windows
    app_data = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / 'MusikPlayer'
else:  # macOS/Linux
    app_data = Path(os.path.expanduser('~')) / '.musikplayer'

try:
    app_data.mkdir(parents=True, exist_ok=True)
except Exception as e:
    logger.warning(f"No se pudo crear directorio de datos, usando temporal: {e}")
    import tempfile
    app_data = Path(tempfile.gettempdir()) / 'MusikPlayer'
    app_data.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = app_data / 'musik_config.json'


@dataclass
class AppConfig:
    """Configuración de la aplicación"""
    volume: float = 0.7
    window_width: int = 980
    window_height: int = 720
    window_x: int = 100
    window_y: int = 100
    shuffle: bool = False
    repeat_mode: int = 0  # 0: off, 1: all, 2: one
    theme: str = "dark_premium"
    last_playlist: Optional[str] = None
    auto_play: bool = False
    save_playlist: bool = True
    # --- Motor de audio avanzado --------------------------------------
    audio_driver: str = "auto"          # auto | wasapi | directsound | alsa | pulseaudio | dummy
    sample_rate: int = 48000            # frecuencia de salida (44100 / 48000)
    buffer_size: int = 2048             # búfer en muestras (512..4096)
    output_depth: int = 16              # 16 (CD) | 32 (float32)
    hq_engine: bool = False             # motor HQ (decode + EQ) activado
    eq_enabled: bool = False            # ecualizador gráfico activado
    eq_preamp: float = 0.0              # ganancia previa en dB (-12..12)
    eq_gains: str = "0,0,0,0,0,0,0,0,0,0"  # 10 bandas en dB (-12..12)
    eq_preset: str = "Flat"            # nombre del preset activo
    eq_hp_filter: bool = False          # filtro paso-alto (rumble) 25 Hz
    normalization: str = "off"          # off | replaygain | peak

    # Presets de ecualizador (nombre -> 10 ganancias en dB)
    EQ_PRESETS: dict = field(default_factory=lambda: {
        "Flat": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "Rock": [4, 3, 1, -1, -1, 1, 2, 3, 4, 4],
        "Pop": [-1, 1, 3, 4, 3, 0, -1, -1, -1, -1],
        "Jazz": [3, 2, 1, 2, -1, -1, 0, 1, 2, 3],
        "Classical": [3, 2, 0, -1, -1, -1, 0, 1, 2, 3],
        "Bass Boost": [6, 5, 3, 1, 0, 0, 0, 0, 0, 0],
        "Vocal": [-2, -1, 0, 2, 3, 3, 2, 1, 0, -1],
        "Electronic": [4, 3, 0, -2, -1, 2, 3, 3, 2, 1],
        "Headphones": [2, 1, 0, -1, -1, 0, 1, 2, 3, 3],
    })
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la configuración a diccionario"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """Crea configuración desde diccionario"""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class ConfigManager:
    """Gestor de configuración de la aplicación"""
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Inicializa el gestor de configuración
        
        Args:
            config_dir: Directorio para guardar la configuración (default: directorio de datos del usuario)
        """
        if config_dir:
            self._config_path = Path(config_dir) / 'musik_config.json'
        else:
            self._config_path = CONFIG_FILE
        
        self._config = AppConfig()
        self._load_config()
        logger.info(f"ConfigManager inicializado con ruta: {self._config_path}")
    
    def _load_config(self) -> None:
        """Carga la configuración desde archivo"""
        try:
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._config = AppConfig.from_dict(data)
                    logger.info("Configuración cargada exitosamente")
            else:
                logger.info("No existe archivo de configuración, usando defaults")
        except json.JSONDecodeError as e:
            logger.error(f"Error al decodificar JSON: {e}")
            self._config = AppConfig()
        except Exception as e:
            logger.error(f"Error al cargar configuración: {e}")
            self._config = AppConfig()
    
    def _save_config(self) -> bool:
        """
        Guarda la configuración en archivo optimizado con escritura atómica
        
        Returns:
            True si se guardó exitosamente, False en caso contrario
        """
        try:
            # Escritura atómica para evitar corrupción
            import tempfile
            import shutil
            
            # Escribir a archivo temporal primero
            temp_path = self._config_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self._config.to_dict(), f, indent=4)
            
            # Mover atómicamente
            shutil.move(str(temp_path), str(self._config_path))
            
            logger.debug("Configuración guardada exitosamente")
            return True
        except Exception as e:
            logger.error(f"Error al guardar configuración: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Obtiene un valor de configuración
        
        Args:
            key: Clave de configuración
            default: Valor por defecto si no existe
            
        Returns:
            Valor de configuración o default
        """
        return getattr(self._config, key, default)
    
    def set(self, key: str, value: Any, save: bool = True) -> None:
        """
        Establece un valor de configuración
        
        Args:
            key: Clave de configuración
            value: Valor a establecer
            save: Si True, guarda inmediatamente en archivo
        """
        if hasattr(self._config, key):
            setattr(self._config, key, value)
            if save:
                self._save_config()
            logger.debug(f"Configuración actualizada: {key} = {value}")
        else:
            logger.warning(f"Clave de configuración inválida: {key}")
    
    def get_volume(self) -> float:
        """Obtiene el volumen"""
        return self._config.volume
    
    def set_volume(self, volume: float, save: bool = True) -> None:
        """Establece el volumen"""
        self.set('volume', max(0.0, min(1.0, volume)), save)
    
    def get_window_geometry(self) -> tuple:
        """Obtiene la geometría de la ventana (width, height, x, y)"""
        return (
            self._config.window_width,
            self._config.window_height,
            self._config.window_x,
            self._config.window_y
        )
    
    def set_window_geometry(self, width: int, height: int, x: int, y: int, save: bool = True) -> None:
        """Establece la geometría de la ventana"""
        self.set('window_width', width, False)
        self.set('window_height', height, False)
        self.set('window_x', x, False)
        self.set('window_y', y, save)
    
    def get_shuffle(self) -> bool:
        """Obtiene el estado de shuffle"""
        return self._config.shuffle
    
    def set_shuffle(self, shuffle: bool, save: bool = True) -> None:
        """Establece el estado de shuffle"""
        self.set('shuffle', shuffle, save)
    
    def get_repeat_mode(self) -> int:
        """Obtiene el modo de repeat"""
        return self._config.repeat_mode
    
    def set_repeat_mode(self, mode: int, save: bool = True) -> None:
        """Establece el modo de repeat"""
        self.set('repeat_mode', max(0, min(2, mode)), save)
    
    def get_theme(self) -> str:
        """Obtiene el tema"""
        return self._config.theme
    
    def set_theme(self, theme: str, save: bool = True) -> None:
        """Establece el tema"""
        self.set('theme', theme, save)

    # ------------------------------------------------------------------
    # Motor de audio avanzado
    # ------------------------------------------------------------------

    def get_audio_driver(self) -> str:
        """Obtiene el driver de salida de audio configurado."""
        return self._config.audio_driver

    def set_audio_driver(self, driver: str, save: bool = True) -> None:
        """Establece el driver de salida (auto, wasapi, directsound, alsa...)."""
        self.set('audio_driver', driver, save)

    def get_sample_rate(self) -> int:
        """Obtiene la frecuencia de muestreo de salida."""
        return self._config.sample_rate

    def set_sample_rate(self, rate: int, save: bool = True) -> None:
        """Establece la frecuencia de muestreo de salida."""
        self.set('sample_rate', rate, save)

    def get_buffer_size(self) -> int:
        """Obtiene el tamaño de búfer (evita stuttering)."""
        return self._config.buffer_size

    def set_buffer_size(self, size: int, save: bool = True) -> None:
        """Establece el tamaño de búfer en muestras."""
        self.set('buffer_size', size, save)

    def get_output_depth(self) -> int:
        """Obtiene la profundidad de salida (16 o 32)."""
        return self._config.output_depth

    def set_output_depth(self, depth: int, save: bool = True) -> None:
        """Establece la profundidad de salida."""
        self.set('output_depth', depth, save)

    def get_hq_engine(self) -> bool:
        """Obtiene si el motor de alta calidad está activo."""
        return self._config.hq_engine

    def set_hq_engine(self, enabled: bool, save: bool = True) -> None:
        """Establece si el motor HQ está activo."""
        self.set('hq_engine', enabled, save)

    def get_eq_enabled(self) -> bool:
        """Obtiene si el ecualizador está activo."""
        return self._config.eq_enabled

    def set_eq_enabled(self, enabled: bool, save: bool = True) -> None:
        """Establece si el ecualizador está activo."""
        self.set('eq_enabled', enabled, save)

    def get_eq_preamp(self) -> float:
        """Obtiene la ganancia previa del EQ en dB."""
        return self._config.eq_preamp

    def set_eq_preamp(self, db: float, save: bool = True) -> None:
        """Establece la ganancia previa del EQ en dB."""
        self.set('eq_preamp', max(-12.0, min(12.0, float(db))), save)

    def get_eq_gains(self) -> list:
        """Obtiene las 10 ganancias del EQ en dB (lista de floats)."""
        try:
            return [float(g) for g in str(self._config.eq_gains).split(",")][:10]
        except (ValueError, TypeError):
            return [0.0] * 10

    def set_eq_gains(self, gains: list, save: bool = True) -> None:
        """Establece las 10 ganancias del EQ en dB."""
        clamped = [max(-12.0, min(12.0, float(g))) for g in gains][:10]
        while len(clamped) < 10:
            clamped.append(0.0)
        self.set('eq_gains', ",".join(f"{g:.1f}" for g in clamped), save)

    def get_eq_preset(self) -> str:
        """Obtiene el nombre del preset de EQ activo."""
        return self._config.eq_preset

    def set_eq_preset(self, name: str, save: bool = True) -> None:
        """Establece el preset de EQ activo."""
        self.set('eq_preset', name, save)

    def get_eq_hp_filter(self) -> bool:
        """Obtiene si el filtro paso-alto (subsónico) está activo."""
        return self._config.eq_hp_filter

    def set_eq_hp_filter(self, enabled: bool, save: bool = True) -> None:
        """Establece el filtro paso-alto subsónico."""
        self.set('eq_hp_filter', enabled, save)

    def get_normalization(self) -> str:
        """Obtiene el modo de normalización (off | replaygain | peak)."""
        return self._config.normalization

    def set_normalization(self, mode: str, save: bool = True) -> None:
        """Establece el modo de normalización de volumen."""
        self.set('normalization', mode if mode in ("off", "replaygain", "peak") else "off", save)

    def get_eq_presets(self) -> dict:
        """Obtiene los presets de EQ disponibles."""
        return dict(self._config.EQ_PRESETS)
    
    def get_last_playlist(self) -> Optional[str]:
        """Obtiene la última playlist"""
        return self._config.last_playlist
    
    def set_last_playlist(self, playlist_path: Optional[str], save: bool = True) -> None:
        """Establece la última playlist"""
        self.set('last_playlist', playlist_path, save)
    
    def get_auto_play(self) -> bool:
        """Obtiene el estado de auto-play"""
        return self._config.auto_play
    
    def set_auto_play(self, auto_play: bool, save: bool = True) -> None:
        """Establece el estado de auto-play"""
        self.set('auto_play', auto_play, save)
    
    def save(self) -> bool:
        """Guarda la configuración actual"""
        return self._save_config()
    
    def reset_to_defaults(self) -> None:
        """Restablece la configuración a valores por defecto"""
        self._config = AppConfig()
        self._save_config()
        logger.info("Configuración restablecida a valores por defecto")
    
    def export_config(self, file_path: str) -> bool:
        """
        Exporta la configuración a un archivo específico
        
        Args:
            file_path: Ruta del archivo de destino
            
        Returns:
            True si se exportó exitosamente, False en caso contrario
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self._config.to_dict(), f, indent=4)
            logger.info(f"Configuración exportada a: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error al exportar configuración: {e}")
            return False
    
    def import_config(self, file_path: str) -> bool:
        """
        Importa configuración desde un archivo
        
        Args:
            file_path: Ruta del archivo de configuración
            
        Returns:
            True si se importó exitosamente, False en caso contrario
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._config = AppConfig.from_dict(data)
                self._save_config()
            logger.info(f"Configuración importada desde: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error al importar configuración: {e}")
            return False
