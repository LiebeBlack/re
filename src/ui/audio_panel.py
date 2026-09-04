"""
audio_panel - Componentes de interfaz para el motor de audio avanzado.

Incluye:
  * MetaChips: píldoras con los metadatos técnicos (formato, bitrate,
    sample rate, canales, profundidad) + insignia HQ/Lossless.
  * EqPanel: ecualizador gráfico compacto de 10 bandas con preamp,
    filtro subsónico, presets y encendido/apagado.
  * AudioSettingsPopup: configuración de salida (driver WASAPI/ALSA/Pulse,
    buffer, sample rate, profundidad), normalización y motor HQ.
"""

from typing import Callable, Dict, List, Optional

import customtkinter as ctk

from src.ui.styles import Styles, blend_colors
from src.ui.widgets import Tooltip


# ---------------------------------------------------------------------------
# MetaChips (metadatos técnicos en píldoras)
# ---------------------------------------------------------------------------

class MetaChips(ctk.CTkFrame):
    """Fila de píldoras con los metadatos técnicos de la pista."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._chips: List[ctk.CTkLabel] = []

    def set_metadata(self, meta: Dict, hq: bool = False) -> None:
        """
        Actualiza las píldoras con los metadatos.

        Args:
            meta: Diccionario de MetadataExtractor.extract_metadata.
            hq: True si la pista se reproduce con el motor HQ.
        """
        for chip in self._chips:
            chip.destroy()
        self._chips.clear()

        parts: List[tuple] = []

        fmt = (meta.get("format") or "").upper()
        if fmt:
            lossless = bool(meta.get("lossless"))
            parts.append((fmt, Styles.SUCCESS_COLOR if lossless else None))
            if lossless:
                parts.append(("Lossless", Styles.SUCCESS_COLOR))

        codec = meta.get("codec") or ""
        if codec and codec.upper() != fmt:
            parts.append((codec, None))

        bitrate = meta.get("bitrate")
        if bitrate:
            parts.append((f"{int(bitrate) // 1000} kbps", None))

        sr = meta.get("sample_rate")
        if sr:
            khz = int(sr) / 1000.0
            parts.append((f"{khz:g} kHz", None))

        channels = meta.get("channels")
        if channels:
            parts.append((f"{int(channels)} ch", None))

        bits = meta.get("bit_depth")
        if bits:
            parts.append((f"{int(bits)} bit", None))

        if hq:
            parts.append(("HQ EQ", Styles.ACCENT_COLOR))

        for text, color in parts:
            chip = ctk.CTkLabel(
                self,
                text=text,
                font=Styles.SMALL_FONT,
                text_color=color or Styles.TEXT_SECONDARY,
                fg_color=Styles.BUTTON_COLOR if color is None else blend_colors(color, Styles.PRIMARY_COLOR, 0.7),
                corner_radius=8,
            )
            chip.pack(side="left", padx=(0, 4), pady=2)
            self._chips.append(chip)

        if not self._chips:
            empty = ctk.CTkLabel(self, text="—", font=Styles.SMALL_FONT,
                                 text_color=Styles.TEXT_SECONDARY)
            empty.pack(side="left")
            self._chips.append(empty)


# ---------------------------------------------------------------------------
# EqPanel (ecualizador gráfico de 10 bandas)
# ---------------------------------------------------------------------------

EQ_FREQS = ["31", "62", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"]
EQ_MIN, EQ_MAX = -12.0, 12.0


class EqPanel(ctk.CTkFrame):
    """
    Panel compacto de ecualizador: 10 bandas en 2 columnas + preamp y
    filtro subsónico. Emite cambios vía callback on_change().
    """

    def __init__(self, master, on_change: Optional[Callable[[Dict], None]] = None,
                 presets: Optional[Dict[str, list]] = None, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self._on_change = on_change
        self._presets = presets or {"Flat": [0] * 10}
        self._sliders: List[ctk.CTkSlider] = []
        self._value_labels: List[ctk.CTkLabel] = []
        self._gains = [0.0] * 10
        self._enabled = False
        self._hp_filter = False
        self._preamp = 0.0
        self._busy = False  # evita loops al programar presets

        self._build_ui()

    # -- Construcción ----------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        # Cabecera: título, enable, presets
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        title = ctk.CTkLabel(head, text="🎛 Ecualizador", font=Styles.SMALL_FONT,
                             text_color=Styles.TEXT_COLOR)
        title.pack(side="left")

        self._enable_switch = ctk.CTkSwitch(
            head, text="EQ activo", font=Styles.SMALL_FONT,
            progress_color=Styles.ACCENT_COLOR, command=self._on_enable_toggle,
            width=40, height=18)
        self._enable_switch.pack(side="right", padx=(10, 4))

        self._preset_menu = ctk.CTkOptionMenu(
            head, values=list(self._presets.keys()), command=self._on_preset,
            font=Styles.SMALL_FONT, width=130, height=24,
            fg_color=Styles.BUTTON_COLOR, button_color=Styles.ACCENT_COLOR,
            button_hover_color=Styles.ACCENT_HOVER, text_color=Styles.TEXT_COLOR,
            dropdown_fg_color=Styles.SECONDARY_COLOR,
            dropdown_hover_color=Styles.BUTTON_COLOR,
            dropdown_text_color=Styles.TEXT_COLOR, corner_radius=8)
        self._preset_menu.pack(side="right", padx=(0, 6))
        Tooltip(self._preset_menu, "Presets rápidos de ecualización")

        self._reset_btn = ctk.CTkButton(
            head, text="↺", width=24, height=24, font=("Segoe UI", 11),
            fg_color=Styles.BUTTON_COLOR, hover_color=Styles.BUTTON_HOVER,
            text_color=Styles.TEXT_COLOR, corner_radius=8, command=self._on_reset)
        self._reset_btn.pack(side="right", padx=(0, 2))
        Tooltip(self._reset_btn, "Poner todo a 0 dB")

        # 10 bandas en 2 columnas de 5 filas
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="ew")
        for col in range(2):
            grid.grid_columnconfigure(col, weight=1)

        for band in range(10):
            row = band % 5
            col = band // 5
            cell = ctk.CTkFrame(grid, fg_color=Styles.SECONDARY_COLOR, corner_radius=8)
            cell.grid(row=row, column=col, sticky="ew", padx=3, pady=2)

            freq = ctk.CTkLabel(cell, text=EQ_FREQS[band], font=Styles.MONO_FONT,
                                text_color=Styles.TEXT_SECONDARY, width=30)
            freq.pack(side="left", padx=(6, 4), pady=2)

            slider = ctk.CTkSlider(
                cell, from_=EQ_MIN, to=EQ_MAX, number_of_steps=int(EQ_MAX * 2 * 10),
                width=90, height=12,
                progress_color=Styles.ACCENT_COLOR, fg_color=Styles.PROGRESS_BG,
                button_color=Styles.ACCENT_COLOR,
                button_hover_color=Styles.ACCENT_HOVER)
            slider.set(0)
            slider.pack(side="left", fill="x", expand=True, padx=4)
            slider.configure(command=lambda v, b=band: self._on_band_change(b, v))
            self._sliders.append(slider)

            value = ctk.CTkLabel(cell, text="0", font=Styles.MONO_FONT,
                                 text_color=Styles.TEXT_SECONDARY, width=24)
            value.pack(side="right", padx=(0, 6))
            self._value_labels.append(value)

        # Preamp + filtro subsónico
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", pady=(6, 0))

        self._hp_switch = ctk.CTkSwitch(
            bottom, text="Filtro subsónico (25 Hz)", font=Styles.SMALL_FONT,
            progress_color=Styles.ACCENT_COLOR, command=self._on_hp_toggle,
            width=40, height=18)
        self._hp_switch.pack(side="left", padx=4)
        Tooltip(self._hp_switch, "Elimina el retumbar sub-grave (rumble)")

        preamp_frame = ctk.CTkFrame(bottom, fg_color="transparent")
        preamp_frame.pack(side="right")
        ctk.CTkLabel(preamp_frame, text="Preamp", font=Styles.SMALL_FONT,
                     text_color=Styles.TEXT_SECONDARY).pack(side="left", padx=(4, 4))
        self._preamp_slider = ctk.CTkSlider(
            preamp_frame, from_=-12.0, to=12.0, number_of_steps=240,
            width=110, height=12,
            progress_color=Styles.ACCENT_COLOR, fg_color=Styles.PROGRESS_BG,
            button_color=Styles.ACCENT_COLOR, button_hover_color=Styles.ACCENT_HOVER)
        self._preamp_slider.set(0)
        self._preamp_slider.pack(side="left")
        self._preamp_slider.configure(command=self._on_preamp_change)
        self._preamp_label = ctk.CTkLabel(preamp_frame, text="0.0 dB",
                                          font=Styles.MONO_FONT,
                                          text_color=Styles.TEXT_SECONDARY, width=48)
        self._preamp_label.pack(side="left", padx=(4, 2))

    # -- Handlers --------------------------------------------------------

    def _emit(self) -> None:
        """Notifica el cambio de configuración al exterior."""
        if self._busy:
            return
        if self._on_change:
            self._on_change({
                "eq_enabled": self._enabled,
                "eq_gains": list(self._gains),
                "eq_preamp": self._preamp,
                "eq_hp_filter": self._hp_filter,
                "eq_preset": self._preset_menu.get(),
            })

    def _on_band_change(self, band: int, value: float) -> None:
        self._gains[band] = float(value)
        self._value_labels[band].configure(
            text=f"{float(value):+.0f}", text_color=Styles.TEXT_COLOR
            if abs(float(value)) > 0.5 else Styles.TEXT_SECONDARY)
        if self._enabled:
            self._emit()

    def _on_preamp_change(self, value: float) -> None:
        self._preamp = float(value)
        self._preamp_label.configure(text=f"{self._preamp:+.1f} dB")
        if self._enabled:
            self._emit()

    def _on_enable_toggle(self) -> None:
        self._enabled = bool(self._enable_switch.get())
        self._emit()

    def _on_hp_toggle(self) -> None:
        self._hp_filter = bool(self._hp_switch.get())
        if self._enabled:
            self._emit()

    def _on_preset(self, name: str) -> None:
        gains = self._presets.get(name)
        if gains is None:
            return
        self.set_gains(gains, preset=name)
        if self._enabled:
            self._emit()

    def _on_reset(self) -> None:
        self._preset_menu.set("Flat")
        self.set_gains([0.0] * 10, preset="Flat")
        if self._enabled:
            self._emit()

    # -- API pública -----------------------------------------------------

    def set_gains(self, gains: List[float], preset: Optional[str] = None,
                  preamp: Optional[float] = None, enabled: Optional[bool] = None,
                  hp_filter: Optional[bool] = None) -> None:
        """Sincroniza el panel con un estado externo (sin emitir)."""
        self._busy = True
        try:
            for band, slider in enumerate(self._sliders):
                if band < len(gains):
                    g = float(gains[band])
                    self._gains[band] = g
                    slider.set(g)
                    self._value_labels[band].configure(
                        text=f"{g:+.0f}",
                        text_color=Styles.TEXT_COLOR if abs(g) > 0.5 else Styles.TEXT_SECONDARY)
            if preamp is not None:
                self._preamp = float(preamp)
                self._preamp_slider.set(self._preamp)
                self._preamp_label.configure(text=f"{self._preamp:+.1f} dB")
            if enabled is not None:
                self._enabled = bool(enabled)
                self._enable_switch.select() if self._enabled else self._enable_switch.deselect()
            if hp_filter is not None:
                self._hp_filter = bool(hp_filter)
                self._hp_switch.select() if self._hp_filter else self._hp_switch.deselect()
            if preset is not None:
                self._preset_menu.set(preset)
        finally:
            self._busy = False

    def get_state(self) -> Dict:
        """Devuelve el estado actual del panel (sin emitir)."""
        return {
            "eq_enabled": self._enabled,
            "eq_gains": list(self._gains),
            "eq_preamp": self._preamp,
            "eq_hp_filter": self._hp_filter,
            "eq_preset": self._preset_menu.get(),
        }


# ---------------------------------------------------------------------------
# AudioSettingsPopup (configuración de salida y normalización)
# ---------------------------------------------------------------------------

class AudioSettingsPopup(ctk.CTkToplevel):
    """Diálogo compacto de configuración del motor de audio."""

    def __init__(self, master, current: Dict, presets: Optional[Dict] = None,
                 on_apply: Optional[Callable[[Dict], None]] = None):
        super().__init__(master)
        self.title("Configuración de audio")
        self.resizable(False, False)
        self._on_apply = on_apply
        self._presets = presets or {}

        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        container = ctk.CTkFrame(self, fg_color=Styles.SECONDARY_COLOR, corner_radius=12)
        container.pack(padx=12, pady=12, fill="both", expand=True)

        self._build_output_section(container, current)
        self._build_quality_section(container, current)
        self._build_actions(container)

        self.transient(master)
        self.after(50, self._center_on, master)

    # -- Secciones --------------------------------------------------------

    def _build_output_section(self, parent, current: Dict) -> None:
        box = ctk.CTkFrame(parent, fg_color=Styles.PRIMARY_COLOR, corner_radius=10)
        box.pack(fill="x", padx=6, pady=(4, 6))

        ctk.CTkLabel(box, text="🔊 Salida de audio", font=Styles.SUBTITLE_FONT,
                     text_color=Styles.TEXT_COLOR).pack(anchor="w", padx=10, pady=(6, 2))

        row1 = ctk.CTkFrame(box, fg_color="transparent")
        row1.pack(fill="x", padx=10)

        drivers = ["auto", "wasapi", "directsound", "dsound", "winmm", "alsa", "pulseaudio", "dummy"]
        self._driver_menu = self._make_menu(row1, "Driver", drivers, current.get("audio_driver", "auto"), 150)
        self._rate_menu = self._make_menu(row1, "Sample rate", ["44100", "48000"], str(current.get("sample_rate", 48000)), 110)

        row2 = ctk.CTkFrame(box, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(4, 8))
        self._buffer_menu = self._make_menu(row2, "Búfer (anti-cortes)", ["512", "1024", "2048", "4096"], str(current.get("buffer_size", 2048)), 130)
        self._depth_menu = self._make_menu(row2, "Profundidad", ["16", "32"], str(current.get("output_depth", 16)), 100)

    def _build_quality_section(self, parent, current: Dict) -> None:
        box = ctk.CTkFrame(parent, fg_color=Styles.PRIMARY_COLOR, corner_radius=10)
        box.pack(fill="x", padx=6, pady=(0, 6))

        ctk.CTkLabel(box, text="✨ Calidad y normalización", font=Styles.SUBTITLE_FONT,
                     text_color=Styles.TEXT_COLOR).pack(anchor="w", padx=10, pady=(6, 2))

        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 6))

        self._hq_switch = ctk.CTkSwitch(
            row, text="Motor HQ (decode + EQ, FLAC/WAV/MP3)", font=Styles.SMALL_FONT,
            progress_color=Styles.ACCENT_COLOR, width=40, height=18)
        self._hq_switch.select() if current.get("hq_engine") else self._hq_switch.deselect()
        self._hq_switch.pack(side="left")
        Tooltip(self._hq_switch,
                "Decodifica en un hilo aparte y aplica EQ / normalización reales.\n"
                "Requiere numpy + soundfile.")

        self._norm_menu = self._make_menu(
            row, "Normalización",
            ["off", "replaygain", "peak"],
            current.get("normalization", "off"), 120)

    def _build_actions(self, parent) -> None:
        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(2, 8))

        apply_btn = ctk.CTkButton(
            actions, text="Aplicar", height=28,
            fg_color=Styles.ACCENT_COLOR, hover_color=Styles.ACCENT_HOVER,
            text_color="#ffffff", font=Styles.NORMAL_FONT, corner_radius=8,
            command=self._on_apply)
        apply_btn.pack(side="right")

        cancel_btn = ctk.CTkButton(
            actions, text="Cancelar", height=28,
            fg_color=Styles.BUTTON_COLOR, hover_color=Styles.BUTTON_HOVER,
            text_color=Styles.TEXT_COLOR, font=Styles.NORMAL_FONT, corner_radius=8,
            command=self.destroy)
        cancel_btn.pack(side="right", padx=(0, 6))

    # -- Helpers ------------------------------------------------------------

    @staticmethod
    def _make_menu(parent, label: str, values: list, current: str, width: int) -> ctk.CTkOptionMenu:
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(cell, text=label, font=Styles.SMALL_FONT,
                     text_color=Styles.TEXT_SECONDARY).pack(anchor="w")
        menu = ctk.CTkOptionMenu(
            cell, values=values, width=width, height=24, font=Styles.SMALL_FONT,
            fg_color=Styles.BUTTON_COLOR, button_color=Styles.ACCENT_COLOR,
            button_hover_color=Styles.ACCENT_HOVER, text_color=Styles.TEXT_COLOR,
            dropdown_fg_color=Styles.SECONDARY_COLOR,
            dropdown_hover_color=Styles.BUTTON_COLOR,
            dropdown_text_color=Styles.TEXT_COLOR, corner_radius=8)
        if current in values:
            menu.set(current)
        else:
            menu.set(values[0])
        menu.pack(anchor="w", pady=(1, 0))
        return menu

    def _center_on(self, master) -> None:
        try:
            self.update_idletasks()
            x = master.winfo_rootx() + 60
            y = master.winfo_rooty() + 60
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _on_apply(self) -> None:
        settings = {
            "audio_driver": self._driver_menu.get(),
            "sample_rate": int(self._rate_menu.get()),
            "buffer_size": int(self._buffer_menu.get()),
            "output_depth": int(self._depth_menu.get()),
            "hq_engine": bool(self._hq_switch.get()),
            "normalization": self._norm_menu.get(),
        }
        if self._on_apply:
            self._on_apply(settings)
        self.destroy()