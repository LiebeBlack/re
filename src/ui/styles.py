"""
Styles - Definición de estilos, temas y utilidades de color para Musik Player

Este módulo centraliza toda la identidad visual de la aplicación:
  * Paletas de colores "ultra modernas" (neón, glass, gradientes).
  * Fuentes tipográficas consistentes.
  * Helpers de color (mezcla, aclarado, oscurecido) usados por las
    animaciones y por los widgets dinámicos.

Los temas antiguos (dark_premium, dark_blue, dark_purple, light) se
conservan para mantener compatibilidad con configuraciones guardadas,
y se añaden nuevos temas: ocean, aurora, sunset y emerald.
"""

import customtkinter as ctk
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Utilidades de color (usadas por animaciones y widgets dinámicos)
# ---------------------------------------------------------------------------

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """
    Convierte un color '#rrggbb' (o '#rgb') a tupla (r, g, b).

    Args:
        hex_color: Color en formato hexadecimal.

    Returns:
        Tupla con componentes (r, g, b) de 0 a 255.

    Raises:
        ValueError: Si el formato no es válido.
    """
    color = hex_color.strip().lstrip('#')
    if len(color) == 3:
        color = ''.join(ch * 2 for ch in color)
    if len(color) != 6:
        raise ValueError(f"Formato de color inválido: {hex_color}")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """
    Convierte componentes RGB (0-255) a formato '#rrggbb'.

    Args:
        r: Componente roja (0-255).
        g: Componente verde (0-255).
        b: Componente azul (0-255).

    Returns:
        Color en formato hexadecimal.
    """
    return f"#{int(max(0, min(255, r))):02x}{int(max(0, min(255, g))):02x}{int(max(0, min(255, b))):02x}"


def blend_colors(color_a: str, color_b: str, t: float) -> str:
    """
    Mezcla dos colores linealmente.

    Args:
        color_a: Color inicial '#rrggbb'.
        color_b: Color final '#rrggbb'.
        t: Proporción de mezcla (0.0 = color_a, 1.0 = color_b).

    Returns:
        Color mezclado en formato hexadecimal.
    """
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = hex_to_rgb(color_a)
    r2, g2, b2 = hex_to_rgb(color_b)
    return rgb_to_hex(
        r1 + (r2 - r1) * t,
        g1 + (g2 - g1) * t,
        b1 + (b2 - b1) * t,
    )


def lighten(color: str, amount: float = 0.15) -> str:
    """Aclara un color mezclándolo con blanco."""
    return blend_colors(color, "#ffffff", max(0.0, min(1.0, amount)))


def darken(color: str, amount: float = 0.15) -> str:
    """Oscurece un color mezclándolo con negro."""
    return blend_colors(color, "#000000", max(0.0, min(1.0, amount)))


# ---------------------------------------------------------------------------
# Temas
# ---------------------------------------------------------------------------

class Theme:
    """Clase que define los temas de la aplicación."""

    # --- Tema insignia: Midnight Neon (dark_premium) -----------------------
    # Negro azulado profundo + violeta eléctrico → cian (look neón moderno).
    DARK_PREMIUM = {
        "name": "dark_premium",
        "primary": "#0a0e1a",        # Fondo principal (casi negro azulado)
        "secondary": "#101728",      # Fondo secundario
        "card": "#151d33",           # Superficies / tarjetas elevadas
        "accent": "#8b5cf6",         # Violeta eléctrico (acento principal)
        "accent_hover": "#a78bfa",   # Acento al hacer hover
        "glow": "#22d3ee",           # Cian neón (resplandor / gradiente)
        "gradient_a": "#8b5cf6",     # Inicio del gradiente
        "gradient_b": "#22d3ee",     # Fin del gradiente
        "text": "#f1f5f9",
        "text_secondary": "#8b93a7",
        "button": "#1e2a45",
        "button_hover": "#2a3a5f",
        "progress": "#8b5cf6",
        "progress_bg": "#1e2a45",
        "border": "#263252",         # Bordes sutiles (glass)
        "success": "#10b981",
        "warning": "#f59e0b",
        "error": "#ef4444",
    }

    # --- Deep Ocean ---------------------------------------------------------
    DARK_BLUE = {
        "name": "dark_blue",
        "primary": "#081226",
        "secondary": "#0d1f3c",
        "card": "#10264a",
        "accent": "#38bdf8",
        "accent_hover": "#7dd3fc",
        "glow": "#22d3ee",
        "gradient_a": "#0ea5e9",
        "gradient_b": "#22d3ee",
        "text": "#e8f1fb",
        "text_secondary": "#8aa5c4",
        "button": "#123257",
        "button_hover": "#1b4475",
        "progress": "#38bdf8",
        "progress_bg": "#123257",
        "border": "#1d3a63",
        "success": "#10b981",
        "warning": "#f59e0b",
        "error": "#ef4444",
    }

    # --- Aurora (teal / violeta) -------------------------------------------
    DARK_PURPLE = {
        "name": "dark_purple",
        "primary": "#120b24",
        "secondary": "#1c1236",
        "card": "#241743",
        "accent": "#a78bfa",
        "accent_hover": "#c4b5fd",
        "glow": "#34d399",
        "gradient_a": "#8b5cf6",
        "gradient_b": "#34d399",
        "text": "#f5f3ff",
        "text_secondary": "#b8a7e0",
        "button": "#2e1f52",
        "button_hover": "#3d2a6b",
        "progress": "#a78bfa",
        "progress_bg": "#2e1f52",
        "border": "#3b2a63",
        "success": "#34d399",
        "warning": "#fbbf24",
        "error": "#f87171",
    }

    # --- Sunset (rosa / naranja cálido) -------------------------------------
    SUNSET = {
        "name": "sunset",
        "primary": "#1c0f24",
        "secondary": "#291232",
        "card": "#33183f",
        "accent": "#fb7185",
        "accent_hover": "#fda4af",
        "glow": "#fb923c",
        "gradient_a": "#f43f5e",
        "gradient_b": "#fb923c",
        "text": "#fff1f2",
        "text_secondary": "#d6a3b0",
        "button": "#3f1f4d",
        "button_hover": "#542a66",
        "progress": "#fb7185",
        "progress_bg": "#3f1f4d",
        "border": "#51285f",
        "success": "#34d399",
        "warning": "#fbbf24",
        "error": "#f87171",
    }

    # --- Emerald (verde esmeralda oscuro) -----------------------------------
    EMERALD = {
        "name": "emerald",
        "primary": "#05130e",
        "secondary": "#0a1f16",
        "card": "#0e2a1e",
        "accent": "#34d399",
        "accent_hover": "#6ee7b7",
        "glow": "#a3e635",
        "gradient_a": "#10b981",
        "gradient_b": "#a3e635",
        "text": "#ecfdf5",
        "text_secondary": "#8fb8a8",
        "button": "#123527",
        "button_hover": "#1a4a37",
        "progress": "#34d399",
        "progress_bg": "#123527",
        "border": "#1a4a37",
        "success": "#34d399",
        "warning": "#fbbf24",
        "error": "#f87171",
    }

    # --- Slate (grafito frío, minimal) ----------------------------------------
    SLATE = {
        "name": "slate",
        "primary": "#0b0f14",
        "secondary": "#131a22",
        "card": "#18212b",
        "accent": "#38bdf8",
        "accent_hover": "#7dd3fc",
        "glow": "#a5b4fc",
        "gradient_a": "#0ea5e9",
        "gradient_b": "#a5b4fc",
        "text": "#e2e8f0",
        "text_secondary": "#8ea0b4",
        "button": "#1e2a38",
        "button_hover": "#2a3a4e",
        "progress": "#38bdf8",
        "progress_bg": "#1e2a38",
        "border": "#243140",
        "success": "#34d399",
        "warning": "#fbbf24",
        "error": "#f87171",
    }

    # --- Ruby (carmesí profundo) ----------------------------------------------
    RUBY = {
        "name": "ruby",
        "primary": "#170a0e",
        "secondary": "#241016",
        "card": "#2e1520",
        "accent": "#f43f5e",
        "accent_hover": "#fb7185",
        "glow": "#f59e0b",
        "gradient_a": "#e11d48",
        "gradient_b": "#f97316",
        "text": "#fff1f2",
        "text_secondary": "#d3a0ac",
        "button": "#3b1b26",
        "button_hover": "#4f2432",
        "progress": "#f43f5e",
        "progress_bg": "#3b1b26",
        "border": "#4c2230",
        "success": "#34d399",
        "warning": "#fbbf24",
        "error": "#f87171",
    }

    # --- Light (claro, minimalista) ------------------------------------------
    LIGHT = {
        "name": "light",
        "primary": "#f4f6fb",
        "secondary": "#e9edf5",
        "card": "#ffffff",
        "accent": "#6366f1",
        "accent_hover": "#818cf8",
        "glow": "#0ea5e9",
        "gradient_a": "#6366f1",
        "gradient_b": "#0ea5e9",
        "text": "#16181f",
        "text_secondary": "#6b7280",
        "button": "#e5e9f2",
        "button_hover": "#d3d9e6",
        "progress": "#6366f1",
        "progress_bg": "#dbe1ec",
        "border": "#d4dae6",
        "success": "#10b981",
        "warning": "#f59e0b",
        "error": "#ef4444",
    }

    # Alias del tema insignia (nombre moderno, misma paleta)
    MIDNIGHT = DARK_PREMIUM
    OCEAN = DARK_BLUE

    # Nombre visible → clave del tema (para el selector de la UI)
    DISPLAY_NAMES: Dict[str, str] = {
        "🌙 Midnight Neon": "dark_premium",
        "🌊 Deep Ocean": "dark_blue",
        "🌌 Aurora": "dark_purple",
        "🌅 Sunset": "sunset",
        "🍀 Emerald": "emerald",
        "🪨 Slate": "slate",
        "💎 Ruby": "ruby",
        "☀️ Light": "light",
    }

    @classmethod
    def get_theme(cls, theme_name: str) -> Dict[str, str]:
        """
        Obtiene un tema por nombre.

        Args:
            theme_name: Nombre del tema.

        Returns:
            Diccionario con los colores del tema (default: dark_premium).
        """
        themes = {
            "dark_premium": cls.DARK_PREMIUM,
            "dark_blue": cls.DARK_BLUE,
            "dark_purple": cls.DARK_PURPLE,
            "sunset": cls.SUNSET,
            "emerald": cls.EMERALD,
            "slate": cls.SLATE,
            "ruby": cls.RUBY,
            "light": cls.LIGHT,
        }
        return themes.get(theme_name, cls.DARK_PREMIUM)

    @classmethod
    def get_available_themes(cls) -> List[str]:
        """Retorna la lista de claves de temas disponibles."""
        return list(cls.DISPLAY_NAMES.values())

    @classmethod
    def get_display_names(cls) -> Dict[str, str]:
        """Retorna el mapeo nombre visible → clave de tema."""
        return dict(cls.DISPLAY_NAMES)

    @classmethod
    def is_dark(cls, theme_name: str) -> bool:
        """Retorna True si el tema es oscuro (para appearance mode)."""
        return theme_name != "light"


# ---------------------------------------------------------------------------
# Estilos de la aplicación
# ---------------------------------------------------------------------------

class Styles:
    """Clase que define los estilos y colores de la aplicación."""

    # Tema actual
    _current_theme: Dict[str, str] = Theme.DARK_PREMIUM

    # Colores (se actualizan según el tema)
    PRIMARY_COLOR = _current_theme["primary"]
    SECONDARY_COLOR = _current_theme["secondary"]
    CARD_COLOR = _current_theme["card"]
    ACCENT_COLOR = _current_theme["accent"]
    ACCENT_HOVER = _current_theme["accent_hover"]
    GLOW_COLOR = _current_theme["glow"]
    GRADIENT_A = _current_theme["gradient_a"]
    GRADIENT_B = _current_theme["gradient_b"]
    TEXT_COLOR = _current_theme["text"]
    TEXT_SECONDARY = _current_theme["text_secondary"]
    BUTTON_COLOR = _current_theme["button"]
    BUTTON_HOVER = _current_theme["button_hover"]
    PROGRESS_COLOR = _current_theme["progress"]
    PROGRESS_BG = _current_theme["progress_bg"]
    BORDER_COLOR = _current_theme["border"]
    SUCCESS_COLOR = _current_theme["success"]
    WARNING_COLOR = _current_theme["warning"]
    ERROR_COLOR = _current_theme["error"]

    # Dimensiones
    WINDOW_WIDTH = 980
    WINDOW_HEIGHT = 720
    MIN_WIDTH = 720
    MIN_HEIGHT = 560

    # Fuentes (diseño compacto ~13%: menos cuerpo, más aire)
    FONT_FAMILY = "Segoe UI"
    TITLE_FONT = (FONT_FAMILY, 22, "bold")
    SUBTITLE_FONT = (FONT_FAMILY, 15, "bold")
    NORMAL_FONT = (FONT_FAMILY, 12)
    SMALL_FONT = (FONT_FAMILY, 10)
    MONO_FONT = ("Consolas", 11, "bold")

    @classmethod
    def set_theme(cls, theme_name: str) -> None:
        """
        Establece el tema actual y refresca todos los colores derivados.

        Args:
            theme_name: Nombre del tema a usar.
        """
        theme = Theme.get_theme(theme_name)
        cls._current_theme = theme

        cls.PRIMARY_COLOR = theme["primary"]
        cls.SECONDARY_COLOR = theme["secondary"]
        cls.CARD_COLOR = theme["card"]
        cls.ACCENT_COLOR = theme["accent"]
        cls.ACCENT_HOVER = theme["accent_hover"]
        cls.GLOW_COLOR = theme["glow"]
        cls.GRADIENT_A = theme["gradient_a"]
        cls.GRADIENT_B = theme["gradient_b"]
        cls.TEXT_COLOR = theme["text"]
        cls.TEXT_SECONDARY = theme["text_secondary"]
        cls.BUTTON_COLOR = theme["button"]
        cls.BUTTON_HOVER = theme["button_hover"]
        cls.PROGRESS_COLOR = theme["progress"]
        cls.PROGRESS_BG = theme["progress_bg"]
        cls.BORDER_COLOR = theme["border"]
        cls.SUCCESS_COLOR = theme["success"]
        cls.WARNING_COLOR = theme["warning"]
        cls.ERROR_COLOR = theme["error"]

    @classmethod
    def get_current_theme(cls) -> str:
        """Retorna el nombre del tema actual."""
        return cls._current_theme["name"]

    @classmethod
    def get_current_theme_dict(cls) -> Dict[str, str]:
        """Retorna el diccionario completo del tema actual."""
        return dict(cls._current_theme)

    @staticmethod
    def setup_theme(theme_name: str = "dark_premium") -> None:
        """
        Configura el tema de CustomTkinter y de la aplicación.

        Args:
            theme_name: Nombre del tema a usar.
        """
        Styles.set_theme(theme_name)

        if Theme.is_dark(theme_name):
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("dark-blue")
        else:
            ctk.set_appearance_mode("light")
            ctk.set_default_color_theme("blue")

    # ------------------------------------------------------------------
    # Estilos de componentes
    # ------------------------------------------------------------------

    @classmethod
    def get_button_style(cls, style_type: str = "primary") -> dict:
        """
        Retorna el estilo para botones.

        Args:
            style_type: Tipo de botón (primary, accent, secondary, success,
                        warning, error).

        Returns:
            Diccionario con estilos del botón.
        """
        styles = {
            "primary": {
                "fg_color": cls.BUTTON_COLOR,
                "hover_color": cls.BUTTON_HOVER,
                "text_color": cls.TEXT_COLOR,
                "corner_radius": 10,
                "font": cls.NORMAL_FONT,
            },
            "accent": {
                "fg_color": cls.ACCENT_COLOR,
                "hover_color": cls.ACCENT_HOVER,
                "text_color": "#ffffff",
                "corner_radius": 10,
                "font": cls.NORMAL_FONT,
            },
            "secondary": {
                "fg_color": cls.SECONDARY_COLOR,
                "hover_color": cls.BUTTON_COLOR,
                "text_color": cls.TEXT_COLOR,
                "corner_radius": 10,
                "font": cls.NORMAL_FONT,
            },
            "success": {
                "fg_color": cls.SUCCESS_COLOR,
                "hover_color": lighten(cls.SUCCESS_COLOR, 0.1),
                "text_color": "#ffffff",
                "corner_radius": 10,
                "font": cls.NORMAL_FONT,
            },
            "warning": {
                "fg_color": cls.WARNING_COLOR,
                "hover_color": lighten(cls.WARNING_COLOR, 0.1),
                "text_color": "#ffffff",
                "corner_radius": 10,
                "font": cls.NORMAL_FONT,
            },
            "error": {
                "fg_color": cls.ERROR_COLOR,
                "hover_color": lighten(cls.ERROR_COLOR, 0.1),
                "text_color": "#ffffff",
                "corner_radius": 10,
                "font": cls.NORMAL_FONT,
            },
        }
        return styles.get(style_type, styles["primary"])

    @classmethod
    def get_progress_style(cls) -> dict:
        """Retorna el estilo para barras de progreso."""
        return {
            "progress_color": cls.PROGRESS_COLOR,
            "fg_color": cls.PROGRESS_BG,
            "button_color": cls.ACCENT_COLOR,
            "button_hover_color": cls.ACCENT_HOVER,
        }

    @classmethod
    def get_frame_style(cls, style_type: str = "primary") -> dict:
        """
        Retorna el estilo para frames.

        Args:
            style_type: Tipo de frame (primary, secondary, card, transparent).

        Returns:
            Diccionario con estilos del frame.
        """
        styles = {
            "primary": {"fg_color": cls.PRIMARY_COLOR, "corner_radius": 12},
            "secondary": {"fg_color": cls.SECONDARY_COLOR, "corner_radius": 12},
            "card": {
                "fg_color": cls.CARD_COLOR,
                "corner_radius": 14,
                "border_width": 1,
                "border_color": cls.BORDER_COLOR,
            },
            "transparent": {"fg_color": "transparent"},
        }
        return styles.get(style_type, styles["primary"])

    @classmethod
    def get_label_style(cls, style_type: str = "normal") -> dict:
        """
        Retorna el estilo para labels.

        Args:
            style_type: Tipo de label (title, subtitle, normal, small,
                        secondary, accent, glow).

        Returns:
            Diccionario con estilos del label.
        """
        styles = {
            "title": {"font": cls.TITLE_FONT, "text_color": cls.TEXT_COLOR},
            "subtitle": {"font": cls.SUBTITLE_FONT, "text_color": cls.TEXT_COLOR},
            "normal": {"font": cls.NORMAL_FONT, "text_color": cls.TEXT_COLOR},
            "small": {"font": cls.SMALL_FONT, "text_color": cls.TEXT_COLOR},
            "secondary": {"font": cls.NORMAL_FONT, "text_color": cls.TEXT_SECONDARY},
            "accent": {"font": cls.NORMAL_FONT, "text_color": cls.ACCENT_COLOR},
            "glow": {"font": cls.SMALL_FONT, "text_color": cls.GLOW_COLOR},
        }
        return styles.get(style_type, styles["normal"])