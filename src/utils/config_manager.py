"""
ConfigManager - Gestión de configuración y persistencia
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

# Configurar logging
logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    """Configuración de la aplicación"""
    volume: float = 0.7
    window_width: int = 900
    window_height: int = 700
    window_x: int = 100
    window_y: int = 100
    shuffle: bool = False
    repeat_mode: int = 0  # 0: off, 1: all, 2: one
    theme: str = "dark"
    last_playlist: Optional[str] = None
    auto_play: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la configuración a diccionario"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """Crea configuración desde diccionario"""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class ConfigManager:
    """Gestor de configuración de la aplicación"""
    
    CONFIG_FILE = "musik_config.json"
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Inicializa el gestor de configuración
        
        Args:
            config_dir: Directorio para guardar la configuración (default: directorio actual)
        """
        if config_dir:
            self._config_path = Path(config_dir) / self.CONFIG_FILE
        else:
            self._config_path = Path.cwd() / self.CONFIG_FILE
        
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
        Guarda la configuración en archivo
        
        Returns:
            True si se guardó exitosamente, False en caso contrario
        """
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config.to_dict(), f, indent=4)
            logger.info("Configuración guardada exitosamente")
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
