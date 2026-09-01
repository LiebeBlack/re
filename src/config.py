"""
Configuración global de directorios y rutas para Musik Player
"""

import os
import sys
import logging
import tempfile
from pathlib import Path

# Evitar múltiples configuraciones de logging
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)

# Configurar ubicación de datos del usuario (AppData)
if os.name == 'nt':  # Windows
    APP_DATA = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / 'MusikPlayer'
else:  # macOS/Linux
    APP_DATA = Path(os.path.expanduser('~')) / '.musikplayer'

# Crear directorio si no existe con manejo robusto de errores
for _ in range(3):  # Intentar 3 veces
    try:
        APP_DATA.mkdir(parents=True, exist_ok=True)
        logger.info(f"Directorio de datos creado: {APP_DATA}")
        break
    except PermissionError as e:
        logger.warning(f"Permiso denegado para {APP_DATA}: {e}")
        # Fallback a directorio temporal
        APP_DATA = Path(tempfile.gettempdir()) / 'MusikPlayer'
        logger.info(f"Usando directorio temporal: {APP_DATA}")
    except Exception as e:
        logger.error(f"Error creando directorio: {e}")
        if _ == 2:  # Último intento, usar directorio local
            APP_DATA = Path.cwd() / 'musik_data'
            logger.info(f"Usando directorio local: {APP_DATA}")

# Rutas de archivos
LOG_FILE = APP_DATA / 'musik.log'
CONFIG_FILE = APP_DATA / 'musik_config.json'
PLAYLIST_FILE = APP_DATA / 'musik_playlist.json'

logger.info(f"Configuración de rutas:")
logger.info(f"  LOG_FILE: {LOG_FILE}")
logger.info(f"  CONFIG_FILE: {CONFIG_FILE}")
logger.info(f"  PLAYLIST_FILE: {PLAYLIST_FILE}")
