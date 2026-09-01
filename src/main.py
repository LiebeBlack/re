"""
Main - Punto de entrada principal de Musik Player
"""

import sys
import os
import logging

# Agregar el directorio src al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
from ui.main_window import MainWindow
from ui.styles import Styles

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('musik.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


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
