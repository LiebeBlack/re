"""
Styles - Definición de estilos y colores para Musik Player
"""

import customtkinter as ctk
from typing import Dict


class Theme:
    """Clase que define los temas de la aplicación"""
    
    DARK_PREMIUM = {
        "name": "dark_premium",
        "primary": "#1a1a2e",
        "secondary": "#16213e",
        "accent": "#e94560",
        "text": "#ffffff",
        "text_secondary": "#a0a0a0",
        "button": "#0f3460",
        "button_hover": "#1a1a2e",
        "progress": "#e94560",
        "progress_bg": "#0f3460",
        "success": "#00d9a5",
        "warning": "#ffb347",
        "error": "#ff6b6b"
    }
    
    DARK_BLUE = {
        "name": "dark_blue",
        "primary": "#0d1b2a",
        "secondary": "#1b263b",
        "accent": "#415a77",
        "text": "#e0e1dd",
        "text_secondary": "#778da9",
        "button": "#1b263b",
        "button_hover": "#0d1b2a",
        "progress": "#415a77",
        "progress_bg": "#1b263b",
        "success": "#00d9a5",
        "warning": "#ffb347",
        "error": "#ff6b6b"
    }
    
    DARK_PURPLE = {
        "name": "dark_purple",
        "primary": "#2d1b69",
        "secondary": "#430d4b",
        "accent": "#9b4dca",
        "text": "#ffffff",
        "text_secondary": "#d4a5e8",
        "button": "#430d4b",
        "button_hover": "#2d1b69",
        "progress": "#9b4dca",
        "progress_bg": "#430d4b",
        "success": "#00d9a5",
        "warning": "#ffb347",
        "error": "#ff6b6b"
    }
    
    LIGHT = {
        "name": "light",
        "primary": "#f8f9fa",
        "secondary": "#e9ecef",
        "accent": "#007bff",
        "text": "#212529",
        "text_secondary": "#6c757d",
        "button": "#007bff",
        "button_hover": "#0056b3",
        "progress": "#007bff",
        "progress_bg": "#e9ecef",
        "success": "#28a745",
        "warning": "#ffc107",
        "error": "#dc3545"
    }
    
    @classmethod
    def get_theme(cls, theme_name: str) -> Dict[str, str]:
        """
        Obtiene un tema por nombre
        
        Args:
            theme_name: Nombre del tema
            
        Returns:
            Diccionario con colores del tema
        """
        themes = {
            "dark_premium": cls.DARK_PREMIUM,
            "dark_blue": cls.DARK_BLUE,
            "dark_purple": cls.DARK_PURPLE,
            "light": cls.LIGHT
        }
        return themes.get(theme_name, cls.DARK_PREMIUM)
    
    @classmethod
    def get_available_themes(cls) -> list:
        """Retorna lista de temas disponibles"""
        return ["dark_premium", "dark_blue", "dark_purple", "light"]


class Styles:
    """Clase que define los estilos y colores de la aplicación"""
    
    # Tema actual
    _current_theme = Theme.DARK_PREMIUM
    
    # Colores (se actualizan según el tema)
    PRIMARY_COLOR = _current_theme["primary"]
    SECONDARY_COLOR = _current_theme["secondary"]
    ACCENT_COLOR = _current_theme["accent"]
    TEXT_COLOR = _current_theme["text"]
    TEXT_SECONDARY = _current_theme["text_secondary"]
    BUTTON_COLOR = _current_theme["button"]
    BUTTON_HOVER = _current_theme["button_hover"]
    PROGRESS_COLOR = _current_theme["progress"]
    PROGRESS_BG = _current_theme["progress_bg"]
    SUCCESS_COLOR = _current_theme["success"]
    WARNING_COLOR = _current_theme["warning"]
    ERROR_COLOR = _current_theme["error"]
    
    # Dimensiones
    WINDOW_WIDTH = 900
    WINDOW_HEIGHT = 700
    MIN_WIDTH = 600
    MIN_HEIGHT = 500
    
    # Fuentes
    TITLE_FONT = ("Segoe UI", 24, "bold")
    SUBTITLE_FONT = ("Segoe UI", 16)
    NORMAL_FONT = ("Segoe UI", 12)
    SMALL_FONT = ("Segoe UI", 10)
    MONO_FONT = ("Consolas", 10)
    
    @classmethod
    def set_theme(cls, theme_name: str) -> None:
        """
        Establece el tema actual
        
        Args:
            theme_name: Nombre del tema a usar
        """
        theme = Theme.get_theme(theme_name)
        cls._current_theme = theme
        
        # Actualizar colores
        cls.PRIMARY_COLOR = theme["primary"]
        cls.SECONDARY_COLOR = theme["secondary"]
        cls.ACCENT_COLOR = theme["accent"]
        cls.TEXT_COLOR = theme["text"]
        cls.TEXT_SECONDARY = theme["text_secondary"]
        cls.BUTTON_COLOR = theme["button"]
        cls.BUTTON_HOVER = theme["button_hover"]
        cls.PROGRESS_COLOR = theme["progress"]
        cls.PROGRESS_BG = theme["progress_bg"]
        cls.SUCCESS_COLOR = theme["success"]
        cls.WARNING_COLOR = theme["warning"]
        cls.ERROR_COLOR = theme["error"]
    
    @classmethod
    def get_current_theme(cls) -> str:
        """Retorna el nombre del tema actual"""
        return cls._current_theme["name"]
    
    @staticmethod
    def setup_theme(theme_name: str = "dark_premium"):
        """
        Configura el tema de CustomTkinter
        
        Args:
            theme_name: Nombre del tema a usar
        """
        Styles.set_theme(theme_name)
        
        if theme_name == "light":
            ctk.set_appearance_mode("light")
            ctk.set_default_color_theme("blue")
        else:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
    
    @classmethod
    def get_button_style(cls, style_type: str = "primary") -> dict:
        """
        Retorna el estilo para botones
        
        Args:
            style_type: Tipo de botón (primary, secondary, success, warning, error)
            
        Returns:
            Diccionario con estilos del botón
        """
        styles = {
            "primary": {
                "fg_color": cls.BUTTON_COLOR,
                "hover_color": cls.BUTTON_HOVER,
                "text_color": cls.TEXT_COLOR,
                "corner_radius": 8,
                "font": cls.NORMAL_FONT
            },
            "secondary": {
                "fg_color": cls.SECONDARY_COLOR,
                "hover_color": cls.PRIMARY_COLOR,
                "text_color": cls.TEXT_COLOR,
                "corner_radius": 8,
                "font": cls.NORMAL_FONT
            },
            "accent": {
                "fg_color": cls.ACCENT_COLOR,
                "hover_color": cls.PROGRESS_COLOR,
                "text_color": cls.TEXT_COLOR,
                "corner_radius": 8,
                "font": cls.NORMAL_FONT
            },
            "success": {
                "fg_color": cls.SUCCESS_COLOR,
                "hover_color": "#00b894",
                "text_color": "#ffffff",
                "corner_radius": 8,
                "font": cls.NORMAL_FONT
            },
            "warning": {
                "fg_color": cls.WARNING_COLOR,
                "hover_color": "#ff9f43",
                "text_color": "#ffffff",
                "corner_radius": 8,
                "font": cls.NORMAL_FONT
            },
            "error": {
                "fg_color": cls.ERROR_COLOR,
                "hover_color": "#ee5a5a",
                "text_color": "#ffffff",
                "corner_radius": 8,
                "font": cls.NORMAL_FONT
            }
        }
        return styles.get(style_type, styles["primary"])
    
    @classmethod
    def get_progress_style(cls) -> dict:
        """Retorna el estilo para barras de progreso"""
        return {
            "progress_color": cls.PROGRESS_COLOR,
            "fg_color": cls.PROGRESS_BG,
            "button_color": cls.ACCENT_COLOR,
            "button_hover_color": cls.ACCENT_COLOR
        }
    
    @classmethod
    def get_frame_style(cls, style_type: str = "primary") -> dict:
        """
        Retorna el estilo para frames
        
        Args:
            style_type: Tipo de frame (primary, secondary, transparent)
            
        Returns:
            Diccionario con estilos del frame
        """
        styles = {
            "primary": {
                "fg_color": cls.PRIMARY_COLOR,
                "corner_radius": 10
            },
            "secondary": {
                "fg_color": cls.SECONDARY_COLOR,
                "corner_radius": 10
            },
            "transparent": {
                "fg_color": "transparent"
            }
        }
        return styles.get(style_type, styles["primary"])
    
    @classmethod
    def get_label_style(cls, style_type: str = "normal") -> dict:
        """
        Retorna el estilo para labels
        
        Args:
            style_type: Tipo de label (title, subtitle, normal, small, secondary)
            
        Returns:
            Diccionario con estilos del label
        """
        styles = {
            "title": {
                "font": cls.TITLE_FONT,
                "text_color": cls.TEXT_COLOR
            },
            "subtitle": {
                "font": cls.SUBTITLE_FONT,
                "text_color": cls.TEXT_COLOR
            },
            "normal": {
                "font": cls.NORMAL_FONT,
                "text_color": cls.TEXT_COLOR
            },
            "small": {
                "font": cls.SMALL_FONT,
                "text_color": cls.TEXT_COLOR
            },
            "secondary": {
                "font": cls.NORMAL_FONT,
                "text_color": cls.TEXT_SECONDARY
            },
            "accent": {
                "font": cls.NORMAL_FONT,
                "text_color": cls.ACCENT_COLOR
            }
        }
        return styles.get(style_type, styles["normal"])
