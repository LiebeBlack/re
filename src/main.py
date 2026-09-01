"""
Main - Punto de entrada principal de Musik Player
"""

import sys
import os
import logging
import traceback

# Configurar logging primero (antes de imports que puedan fallar)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Agregar el directorio src al path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Agregar el directorio padre (para cuando se ejecuta como módulo)
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    import customtkinter as ctk
    from src.ui.main_window import MainWindow
    from src.ui.styles import Styles
    from src.config import LOG_FILE, APP_DATA

    # Agregar FileHandler al logging después de cargar config
    try:
        file_handler = logging.FileHandler(str(LOG_FILE), mode='a', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(file_handler)
        logger.info(f"Logging configurado en: {LOG_FILE}")
    except Exception as e:
        logger.warning(f"No se pudo configurar log en archivo: {e}")
        logger.info("Usando solo logging en consola")
except ImportError as e:
    logger.error(f"Error importando dependencias: {e}")
    logger.error(traceback.format_exc())
    print(f"Error: Dependencias faltantes. Ejecuta: pip install -r requirements.txt")
    sys.exit(1)
except Exception as e:
    logger.error(f"Error inesperado al importar: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)


def main():
    """Función principal de la aplicación"""
    try:
        logger.info("Iniciando Musik Player")
        
        # Configurar tema
        Styles.setup_theme()
        logger.info("Tema configurado")
        
        # Crear y ejecutar la ventana principal
        app = MainWindow()
        logger.info("Ventana principal creada")
        
        app.run()
        logger.info("Musik Player cerrado normalmente")
        
    except ImportError as e:
        logger.error(f"Error de importación: {e}")
        print(f"Error: Dependencias faltantes. Ejecuta: pip install -r requirements.txt")
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Error de runtime: {e}")
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)
        print(f"Error inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
