"""
PlayerControls - Controles de reproducción para Musik Player
"""

import customtkinter as ctk
from typing import Optional, Callable
from ui.styles import Styles


class PlayerControls(ctk.CTkFrame):
    """Frame que contiene los controles de reproducción"""
    
    def __init__(self, master, **kwargs):
        """
        Inicializa los controles de reproducción
        
        Args:
            master: Widget padre
            **kwargs: Argumentos adicionales para CTkFrame
        """
        super().__init__(master, **kwargs)
        
        self._on_play: Optional[Callable[[], None]] = None
        self._on_pause: Optional[Callable[[], None]] = None
        self._on_next: Optional[Callable[[], None]] = None
        self._on_previous: Optional[Callable[[], None]] = None
        self._on_volume_change: Optional[Callable[[float], None]] = None
        self._on_shuffle: Optional[Callable[[], None]] = None
        self._on_repeat: Optional[Callable[[], None]] = None
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Configura la interfaz de los controles"""
        # Frame principal para los botones
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(expand=True, fill="both", padx=20, pady=10)
        
        # Configurar grid
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        button_frame.grid_columnconfigure(2, weight=1)
        button_frame.grid_columnconfigure(3, weight=1)
        button_frame.grid_columnconfigure(4, weight=1)
        
        # Botón Anterior
        self._previous_btn = ctk.CTkButton(
            button_frame,
            text="◀◀",
            width=60,
            height=50,
            font=("Segoe UI", 16),
            **Styles.get_button_style()
        )
        self._previous_btn.grid(row=0, column=0, padx=5)
        self._previous_btn.configure(command=self._on_previous_click)
        
        # Botón Play/Pause
        self._play_pause_btn = ctk.CTkButton(
            button_frame,
            text="▶",
            width=70,
            height=70,
            font=("Segoe UI", 24),
            **Styles.get_button_style()
        )
        self._play_pause_btn.grid(row=0, column=1, padx=5)
        self._play_pause_btn.configure(command=self._on_play_pause_click)
        
        # Botón Siguiente
        self._next_btn = ctk.CTkButton(
            button_frame,
            text="▶▶",
            width=60,
            height=50,
            font=("Segoe UI", 16),
            **Styles.get_button_style()
        )
        self._next_btn.grid(row=0, column=2, padx=5)
        self._next_btn.configure(command=self._on_next_click)
        
        # Frame para volumen
        volume_frame = ctk.CTkFrame(button_frame, fg_color="transparent")
        volume_frame.grid(row=0, column=3, columnspan=2, padx=20, sticky="ew")
        
        # Label de volumen
        volume_label = ctk.CTkLabel(
            volume_frame,
            text="Volume",
            font=Styles.NORMAL_FONT,
            text_color=Styles.TEXT_SECONDARY
        )
        volume_label.pack(anchor="w")
        
        # Slider de volumen
        self._volume_slider = ctk.CTkSlider(
            volume_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            width=200,
            **Styles.get_progress_style()
        )
        self._volume_slider.pack(fill="x", pady=5)
        self._volume_slider.set(70)  # 70% por defecto
        self._volume_slider.configure(command=self._on_volume_slider_change)
        
        # Frame adicional para shuffle y repeat
        mode_frame = ctk.CTkFrame(button_frame, fg_color="transparent")
        mode_frame.grid(row=1, column=0, columnspan=5, pady=10)
        
        # Botón Shuffle
        self._shuffle_btn = ctk.CTkButton(
            mode_frame,
            text="🔀",
            width=50,
            height=35,
            font=("Segoe UI", 14),
            **Styles.get_button_style("secondary")
        )
        self._shuffle_btn.pack(side="left", padx=5)
        self._shuffle_btn.configure(command=self._on_shuffle_click)
        
        # Botón Repeat
        self._repeat_btn = ctk.CTkButton(
            mode_frame,
            text="🔁",
            width=50,
            height=35,
            font=("Segoe UI", 14),
            **Styles.get_button_style("secondary")
        )
        self._repeat_btn.pack(side="left", padx=5)
        self._repeat_btn.configure(command=self._on_repeat_click)
    
    def _on_play_pause_click(self) -> None:
        """Maneja el clic en el botón play/pause"""
        if self._on_play and self._on_pause:
            # Alternar entre play y pause según el estado actual
            if self._play_pause_btn.cget("text") == "▶":
                self._on_play()
            else:
                self._on_pause()
    
    def _on_previous_click(self) -> None:
        """Maneja el clic en el botón anterior"""
        if self._on_previous:
            self._on_previous()
    
    def _on_next_click(self) -> None:
        """Maneja el clic en el botón siguiente"""
        if self._on_next:
            self._on_next()
    
    def _on_volume_slider_change(self, value: float) -> None:
        """
        Maneja el cambio en el slider de volumen
        
        Args:
            value: Nuevo valor del volumen (0-100)
        """
        if self._on_volume_change:
            volume = value / 100.0
            self._on_volume_change(volume)
    
    def _on_shuffle_click(self) -> None:
        """Maneja el clic en el botón shuffle"""
        if self._on_shuffle:
            self._on_shuffle()
        else:
            # Toggle visual state si no hay callback
            current_color = self._shuffle_btn.cget("fg_color")
            if current_color == Styles.ACCENT_COLOR:
                self._shuffle_btn.configure(fg_color=Styles.BUTTON_COLOR)
            else:
                self._shuffle_btn.configure(fg_color=Styles.ACCENT_COLOR)
    
    def _on_repeat_click(self) -> None:
        """Maneja el clic en el botón repeat"""
        if self._on_repeat:
            self._on_repeat()
        else:
            # Toggle visual state si no hay callback
            current_text = self._repeat_btn.cget("text")
            current_color = self._repeat_btn.cget("fg_color")
            if current_text == "🔁":
                if current_color == Styles.ACCENT_COLOR:
                    self._repeat_btn.configure(text="🔁", fg_color=Styles.BUTTON_COLOR)
                else:
                    self._repeat_btn.configure(text="🔁", fg_color=Styles.ACCENT_COLOR)
            else:
                self._repeat_btn.configure(text="🔁", fg_color=Styles.BUTTON_COLOR)
    
    def set_play_callback(self, callback: Callable[[], None]) -> None:
        """
        Establece el callback para el botón play
        
        Args:
            callback: Función a llamar al hacer clic en play
        """
        self._on_play = callback
    
    def set_pause_callback(self, callback: Callable[[], None]) -> None:
        """
        Establece el callback para el botón pause
        
        Args:
            callback: Función a llamar al hacer clic en pause
        """
        self._on_pause = callback
    
    def set_next_callback(self, callback: Callable[[], None]) -> None:
        """
        Establece el callback para el botón siguiente
        
        Args:
            callback: Función a llamar al hacer clic en siguiente
        """
        self._on_next = callback
    
    def set_previous_callback(self, callback: Callable[[], None]) -> None:
        """
        Establece el callback para el botón anterior
        
        Args:
            callback: Función a llamar al hacer clic en anterior
        """
        self._on_previous = callback
    
    def set_volume_callback(self, callback: Callable[[float], None]) -> None:
        """
        Establece el callback para el cambio de volumen
        
        Args:
            callback: Función a llamar cuando cambia el volumen
        """
        self._on_volume_change = callback
    
    def set_shuffle_callback(self, callback: Callable[[], None]) -> None:
        """
        Establece el callback para el botón shuffle
        
        Args:
            callback: Función a llamar al hacer clic en shuffle
        """
        self._on_shuffle = callback
    
    def set_repeat_callback(self, callback: Callable[[], None]) -> None:
        """
        Establece el callback para el botón repeat
        
        Args:
            callback: Función a llamar al hacer clic en repeat
        """
        self._on_repeat = callback
    
    def set_playing_state(self, is_playing: bool) -> None:
        """
        Actualiza el estado del botón play/pause
        
        Args:
            is_playing: True si está reproduciendo, False si está pausado
        """
        if is_playing:
            self._play_pause_btn.configure(text="⏸")
        else:
            self._play_pause_btn.configure(text="▶")
    
    def set_volume(self, volume: float) -> None:
        """
        Establece el volumen del slider
        
        Args:
            volume: Valor de volumen entre 0.0 y 1.0
        """
        self._volume_slider.set(volume * 100)
    
    def set_enabled(self, enabled: bool) -> None:
        """
        Habilita o deshabilita los controles
        
        Args:
            enabled: True para habilitar, False para deshabilitar
        """
        state = "normal" if enabled else "disabled"
        self._previous_btn.configure(state=state)
        self._play_pause_btn.configure(state=state)
        self._next_btn.configure(state=state)
        self._volume_slider.configure(state=state)
        self._shuffle_btn.configure(state=state)
        self._repeat_btn.configure(state=state)
    
    def set_shuffle_state(self, is_shuffle: bool) -> None:
        """
        Actualiza el estado del botón shuffle
        
        Args:
            is_shuffle: True si shuffle está activo
        """
        if is_shuffle:
            self._shuffle_btn.configure(fg_color=Styles.ACCENT_COLOR)
        else:
            self._shuffle_btn.configure(fg_color=Styles.BUTTON_COLOR)
    
    def set_repeat_state(self, repeat_mode: int) -> None:
        """
        Actualiza el estado del botón repeat
        
        Args:
            repeat_mode: 0: off, 1: all, 2: one
        """
        if repeat_mode == 0:
            self._repeat_btn.configure(text="🔁", fg_color=Styles.BUTTON_COLOR)
        elif repeat_mode == 1:
            self._repeat_btn.configure(text="🔁", fg_color=Styles.ACCENT_COLOR)
        elif repeat_mode == 2:
            self._repeat_btn.configure(text="🔂", fg_color=Styles.ACCENT_COLOR)
