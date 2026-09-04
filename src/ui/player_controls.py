"""
PlayerControls - Controles de reproducción ultra modernos para Musik Player.

Incluye:
  * Botón de play/pause circular con resplandor pulsante mientras suena.
  * Botones con animación de escala al pasar el ratón.
  * Slider de volumen con icono dinámico y porcentaje en vivo.
  * Botones de shuffle/repeat con estados visuales claros.
  * Tooltips en todos los controles.
"""

from typing import Callable, Optional

import customtkinter as ctk

from src.ui.styles import Styles, lighten
from src.ui.animations import Pulse, bind_hover_effect
from src.ui.widgets import Tooltip


class PlayerControls(ctk.CTkFrame):
    """Frame que contiene los controles de reproducción."""

    def __init__(self, master, **kwargs):
        """
        Args:
            master: Widget padre.
            **kwargs: Argumentos adicionales para CTkFrame.
        """
        super().__init__(master, **kwargs)

        # Callbacks configurables desde MainWindow
        self._on_play: Optional[Callable[[], None]] = None
        self._on_pause: Optional[Callable[[], None]] = None
        self._on_next: Optional[Callable[[], None]] = None
        self._on_previous: Optional[Callable[[], None]] = None
        self._on_volume_change: Optional[Callable[[float], None]] = None
        self._on_shuffle: Optional[Callable[[], None]] = None
        self._on_repeat: Optional[Callable[[], None]] = None

        # Pulso del botón de play (solo visible mientras se reproduce)
        self._play_pulse: Optional[Pulse] = None

        self._setup_ui()

    @staticmethod
    def _button_style(style_type: str = "primary", font=None, **overrides) -> dict:
        """
        Retorna el estilo del botón permitiendo sobreescribir fuente,
        esquinas u otros valores (evita kwargs duplicados de CTkButton).

        Args:
            style_type: Tipo de botón (primary, secondary, accent).
            font: Tupla de fuente opcional.
            **overrides: Valores extra que reemplazan a los del estilo.

        Returns:
            Diccionario con estilos del botón.
        """
        style = Styles.get_button_style(style_type)
        if font:
            style["font"] = font
        style.update(overrides)
        return style

    def _setup_ui(self) -> None:
        """Configura la interfaz de los controles."""
        # Grid responsivo: fila 0 = transporte + volumen, fila 1 = modos
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ------------------------------------------------------------
        # Transporte (anterior / play-pause / siguiente)
        # ------------------------------------------------------------
        transport_frame = ctk.CTkFrame(self, fg_color="transparent")
        transport_frame.grid(row=0, column=0, sticky="ew", padx=(10, 5), pady=6)

        transport_center = ctk.CTkFrame(transport_frame, fg_color="transparent")
        transport_center.pack(anchor="center")

        # Botón Anterior
        self._previous_btn = ctk.CTkButton(
            transport_center,
            text="◀◀",
            width=54,
            height=54,
            **self._button_style("secondary", ("Segoe UI", 15), corner_radius=27),
        )
        self._previous_btn.pack(side="left", padx=6)
        self._previous_btn.configure(command=self._on_previous_click)
        bind_hover_effect(self._previous_btn, self)
        Tooltip(self._previous_btn, "Pista anterior  (←)")

        # Botón Play/Pause (circular, con glow pulsante)
        self._play_pause_btn = ctk.CTkButton(
            transport_center,
            text="▶",
            width=76,
            height=76,
            corner_radius=38,
            fg_color=Styles.ACCENT_COLOR,
            hover_color=Styles.ACCENT_COLOR,  # el glow lo controla el Pulse
            text_color="#ffffff",
            font=("Segoe UI", 26),
        )
        self._play_pause_btn.pack(side="left", padx=6)
        self._play_pause_btn.configure(command=self._on_play_pause_click)
        bind_hover_effect(self._play_pause_btn, self, grow=8)
        Tooltip(self._play_pause_btn, "Reproducir / Pausar  (Espacio)")

        # Botón Siguiente
        self._next_btn = ctk.CTkButton(
            transport_center,
            text="▶▶",
            width=54,
            height=54,
            **self._button_style("secondary", ("Segoe UI", 15), corner_radius=27),
        )
        self._next_btn.pack(side="left", padx=6)
        self._next_btn.configure(command=self._on_next_click)
        bind_hover_effect(self._next_btn, self)
        Tooltip(self._next_btn, "Siguiente pista  (→)")

        # ------------------------------------------------------------
        # Volumen (icono + slider + porcentaje)
        # ------------------------------------------------------------
        volume_frame = ctk.CTkFrame(self, fg_color="transparent")
        volume_frame.grid(row=0, column=1, sticky="ew", padx=(5, 15), pady=6)

        volume_header = ctk.CTkFrame(volume_frame, fg_color="transparent")
        volume_header.pack(fill="x")

        self._volume_icon_label = ctk.CTkLabel(
            volume_header,
            text="🔊",
            font=Styles.NORMAL_FONT,
            text_color=Styles.TEXT_SECONDARY,
        )
        self._volume_icon_label.pack(side="left")

        volume_label = ctk.CTkLabel(
            volume_header,
            text="Volume",
            font=Styles.SMALL_FONT,
            text_color=Styles.TEXT_SECONDARY,
        )
        volume_label.pack(side="left", padx=6)

        self._volume_value_label = ctk.CTkLabel(
            volume_header,
            text="70%",
            font=Styles.MONO_FONT,
            text_color=Styles.ACCENT_COLOR,
        )
        self._volume_value_label.pack(side="right")

        self._volume_slider = ctk.CTkSlider(
            volume_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            **Styles.get_progress_style(),
        )
        self._volume_slider.pack(fill="x", pady=5)
        self._volume_slider.set(70)  # 70% por defecto
        self._volume_slider.configure(command=self._on_volume_slider_change)
        Tooltip(self._volume_slider, "Volumen  (↑ / ↓ / M para silenciar)")

        # ------------------------------------------------------------
        # Modos (shuffle / repeat)
        # ------------------------------------------------------------
        modes_frame = ctk.CTkFrame(self, fg_color="transparent")
        modes_frame.grid(row=1, column=0, columnspan=2, pady=(2, 8))

        self._shuffle_btn = ctk.CTkButton(
            modes_frame,
            text="🔀 Shuffle",
            width=120,
            height=34,
            **self._button_style("secondary", ("Segoe UI", 12)),
        )
        self._shuffle_btn.pack(side="left", padx=6)
        self._shuffle_btn.configure(command=self._on_shuffle_click)
        bind_hover_effect(self._shuffle_btn, self, grow=4)
        Tooltip(self._shuffle_btn, "Reproducción aleatoria  (S)")

        self._repeat_btn = ctk.CTkButton(
            modes_frame,
            text="🔁 Repeat",
            width=140,
            height=34,
            **self._button_style("secondary", ("Segoe UI", 12)),
        )
        self._repeat_btn.pack(side="left", padx=6)
        self._repeat_btn.configure(command=self._on_repeat_click)
        bind_hover_effect(self._repeat_btn, self, grow=4)
        Tooltip(self._repeat_btn, "Repetir: Off / Todo / Una  (R)")

    # ------------------------------------------------------------------
    # Handlers internos
    # ------------------------------------------------------------------

    def _on_play_pause_click(self) -> None:
        """Alterna play/pause según el estado visual del botón."""
        if self._on_play and self._on_pause:
            if self._play_pause_btn.cget("text") == "▶":
                self._on_play()
            else:
                self._on_pause()

    def _on_previous_click(self) -> None:
        """Maneja el clic en el botón anterior."""
        if self._on_previous:
            self._on_previous()

    def _on_next_click(self) -> None:
        """Maneja el clic en el botón siguiente."""
        if self._on_next:
            self._on_next()

    def _on_volume_slider_change(self, value: float) -> None:
        """
        Maneja el cambio en el slider de volumen.

        Args:
            value: Nuevo valor del volumen (0-100).
        """
        volume = value / 100.0
        self._update_volume_display(volume)
        if self._on_volume_change:
            self._on_volume_change(volume)

    def _on_shuffle_click(self) -> None:
        """Maneja el clic en el botón shuffle."""
        if self._on_shuffle:
            self._on_shuffle()

    def _on_repeat_click(self) -> None:
        """Maneja el clic en el botón repeat."""
        if self._on_repeat:
            self._on_repeat()

    def _update_volume_display(self, volume: float) -> None:
        """
        Actualiza icono y porcentaje del volumen.

        Args:
            volume: Volumen entre 0.0 y 1.0.
        """
        percent = int(round(volume * 100))
        try:
            self._volume_value_label.configure(text=f"{percent}%")
            if volume <= 0.0:
                icon = "🔇"
            elif volume < 0.5:
                icon = "🔉"
            else:
                icon = "🔊"
            self._volume_icon_label.configure(text=icon)
        except Exception:
            pass  # widget destruido (cierre/rebuild)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def set_play_callback(self, callback: Callable[[], None]) -> None:
        """Establece el callback para el botón play."""
        self._on_play = callback

    def set_pause_callback(self, callback: Callable[[], None]) -> None:
        """Establece el callback para el botón pause."""
        self._on_pause = callback

    def set_next_callback(self, callback: Callable[[], None]) -> None:
        """Establece el callback para el botón siguiente."""
        self._on_next = callback

    def set_previous_callback(self, callback: Callable[[], None]) -> None:
        """Establece el callback para el botón anterior."""
        self._on_previous = callback

    def set_volume_callback(self, callback: Callable[[float], None]) -> None:
        """Establece el callback para el cambio de volumen."""
        self._on_volume_change = callback

    def set_shuffle_callback(self, callback: Callable[[], None]) -> None:
        """Establece el callback para el botón shuffle."""
        self._on_shuffle = callback

    def set_repeat_callback(self, callback: Callable[[], None]) -> None:
        """Establece el callback para el botón repeat."""
        self._on_repeat = callback

    def set_playing_state(self, is_playing: bool) -> None:
        """
        Actualiza el estado del botón play/pause.

        Args:
            is_playing: True si está reproduciendo, False si está pausado.
        """
        if is_playing:
            self._play_pause_btn.configure(text="⏸")
            self._start_play_pulse()
        else:
            self._play_pause_btn.configure(text="▶")
            self._stop_play_pulse()

    def _start_play_pulse(self) -> None:
        """Arranca el resplandor pulsante del botón de play."""
        if self._play_pulse is None:
            self._play_pulse = Pulse(
                self,
                lambda c: self._play_pause_btn.configure(fg_color=c),
                base_color=Styles.ACCENT_COLOR,
                pulse_color=lighten(Styles.ACCENT_COLOR, 0.35),
                period_ms=800,
            )
        else:
            self._play_pulse.set_colors(Styles.ACCENT_COLOR, lighten(Styles.ACCENT_COLOR, 0.35))
        self._play_pulse.start()

    def _stop_play_pulse(self) -> None:
        """Detiene el resplandor y restaura el color base."""
        if self._play_pulse is not None:
            self._play_pulse.stop()

    def stop_animations(self) -> None:
        """Cancela todas las animaciones internas (cierre/rebuild)."""
        self._stop_play_pulse()

    def set_volume(self, volume: float) -> None:
        """
        Establece el volumen del slider y el display.

        Args:
            volume: Valor de volumen entre 0.0 y 1.0.
        """
        self._volume_slider.set(volume * 100)
        self._update_volume_display(volume)

    def set_enabled(self, enabled: bool) -> None:
        """
        Habilita/deshabilita el transporte (play/pause/prev/next).

        El volumen y los modos quedan siempre activos porque tienen
        sentido aunque no haya pista cargada.

        Args:
            enabled: True para habilitar, False para deshabilitar.
        """
        state = "normal" if enabled else "disabled"
        self._previous_btn.configure(state=state)
        self._play_pause_btn.configure(state=state)
        self._next_btn.configure(state=state)

    def set_shuffle_state(self, is_shuffle: bool) -> None:
        """
        Actualiza el estado del botón shuffle.

        Args:
            is_shuffle: True si shuffle está activo.
        """
        if is_shuffle:
            self._shuffle_btn.configure(
                fg_color=Styles.ACCENT_COLOR,
                hover_color=Styles.ACCENT_HOVER,
                text_color="#ffffff",
            )
        else:
            self._shuffle_btn.configure(
                fg_color=Styles.BUTTON_COLOR,
                hover_color=Styles.BUTTON_HOVER,
                text_color=Styles.TEXT_COLOR,
            )

    def set_repeat_state(self, repeat_mode: int) -> None:
        """
        Actualiza el estado del botón repeat.

        Args:
            repeat_mode: 0: off, 1: all, 2: one.
        """
        if repeat_mode == 0:
            text, active = "🔁 Repeat", False
        elif repeat_mode == 1:
            text, active = "🔁 Repeat All", True
        else:
            text, active = "🔂 Repeat One", True

        if active:
            self._repeat_btn.configure(
                text=text,
                fg_color=Styles.ACCENT_COLOR,
                hover_color=Styles.ACCENT_HOVER,
                text_color="#ffffff",
            )
        else:
            self._repeat_btn.configure(
                text=text,
                fg_color=Styles.BUTTON_COLOR,
                hover_color=Styles.BUTTON_HOVER,
                text_color=Styles.TEXT_COLOR,
            )