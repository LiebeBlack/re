"""
PlaylistView - Vista de lista de reproducción para Musik Player
"""

import customtkinter as ctk
from typing import Optional, Callable, List
from functools import partial
from src.ui.styles import Styles


class PlaylistView(ctk.CTkFrame):
    """Frame que muestra la lista de reproducción"""
    
    def __init__(self, master, **kwargs):
        """
        Inicializa la vista de playlist
        
        Args:
            master: Widget padre
            **kwargs: Argumentos adicionales para CTkFrame
        """
        super().__init__(master, **kwargs)
        
        self._on_track_select: Optional[Callable[[int], None]] = None
        self._on_remove_track: Optional[Callable[[int], None]] = None
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Configura la interfaz de la playlist"""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        title_label = ctk.CTkLabel(
            header_frame,
            text="Playlist",
            font=Styles.SUBTITLE_FONT,
            text_color=Styles.TEXT_COLOR
        )
        title_label.pack(side="left")
        
        # Label de conteo
        self._count_label = ctk.CTkLabel(
            header_frame,
            text="0 tracks",
            font=Styles.SMALL_FONT,
            text_color=Styles.TEXT_SECONDARY
        )
        self._count_label.pack(side="right")
        
        # Frame de búsqueda
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=10, pady=(5, 10))
        
        # Entry de búsqueda
        self._search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="🔍 Search playlist...",
            height=30,
            font=Styles.NORMAL_FONT,
            **Styles.get_frame_style("secondary")
        )
        self._search_entry.pack(fill="x")
        # Bind para búsqueda en tiempo real
        self._search_entry.bind("<KeyRelease>", lambda e: self._on_search())
        
        # Scrollable frame para la lista
        self._scrollable_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            label_text=""
        )
        self._scrollable_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Lista para guardar los frames de las pistas
        self._track_frames: List[ctk.CTkFrame] = []
        
        # Lista para guardar las pistas actuales (filtradas o todas)
        self._current_tracks: List[dict] = []
    
    def add_track(self, title: str, artist: str, duration: float, index: int, is_current: bool = False) -> None:
        """
        Agrega una pista a la vista
        
        Args:
            title: Título de la canción
            artist: Artista de la canción
            duration: Duración en segundos
            index: Índice de la pista
            is_current: True si es la pista actual
        """
        # Guardar información de la pista
        track_data = {
            "title": title,
            "artist": artist,
            "duration": duration,
            "index": index,
            "is_current": is_current
        }
        self._current_tracks.append(track_data)
        
        # Solo mostrar si no hay búsqueda activa o si coincide con la búsqueda
        search_text = self._search_entry.get().lower()
        if not search_text or search_text in title.lower() or search_text in artist.lower():
            self._display_track(track_data)
    
    def _display_track(self, track_data: dict) -> None:
        """
        Muestra una pista en la vista
        
        Args:
            track_data: Diccionario con información de la pista
        """
        title = track_data["title"]
        artist = track_data["artist"]
        duration = track_data["duration"]
        index = track_data["index"]
        is_current = track_data["is_current"]
        
        # Frame de la pista
        track_frame = ctk.CTkFrame(
            self._scrollable_frame,
            fg_color=Styles.SECONDARY_COLOR if is_current else "transparent",
            corner_radius=5
        )
        track_frame.pack(fill="x", pady=2)
        
        # Configurar grid
        track_frame.grid_columnconfigure(0, weight=0)  # Índice
        track_frame.grid_columnconfigure(1, weight=1)  # Info
        track_frame.grid_columnconfigure(2, weight=0)  # Duración
        track_frame.grid_columnconfigure(3, weight=0)  # Botón remover
        
        # Índice
        index_label = ctk.CTkLabel(
            track_frame,
            text=f"{index + 1}.",
            font=Styles.SMALL_FONT,
            text_color=Styles.ACCENT_COLOR if is_current else Styles.TEXT_SECONDARY,
            width=30
        )
        index_label.grid(row=0, column=0, padx=5, pady=8)
        
        # Info (título y artista)
        info_frame = ctk.CTkFrame(track_frame, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="w", padx=5)
        
        title_label = ctk.CTkLabel(
            info_frame,
            text=title,
            font=Styles.NORMAL_FONT,
            text_color=Styles.ACCENT_COLOR if is_current else Styles.TEXT_COLOR,
            anchor="w"
        )
        title_label.pack(fill="x")
        
        artist_label = ctk.CTkLabel(
            info_frame,
            text=artist,
            font=Styles.SMALL_FONT,
            text_color=Styles.TEXT_SECONDARY,
            anchor="w"
        )
        artist_label.pack(fill="x")
        
        # Duración
        duration_str = self._format_duration(duration)
        duration_label = ctk.CTkLabel(
            track_frame,
            text=duration_str,
            font=Styles.SMALL_FONT,
            text_color=Styles.TEXT_SECONDARY,
            width=50
        )
        duration_label.grid(row=0, column=2, padx=5, pady=8)
        
        # Botón remover
        remove_btn = ctk.CTkButton(
            track_frame,
            text="✕",
            width=30,
            height=30,
            font=("Segoe UI", 12),
            fg_color=Styles.BUTTON_COLOR,
            hover_color=Styles.ACCENT_COLOR,
            text_color=Styles.TEXT_COLOR,
            corner_radius=5
        )
        remove_btn.grid(row=0, column=3, padx=5, pady=8)
        
        # Configurar comandos con closures correctos
        track_idx = index
        track_frame.configure(cursor="hand2")
        
        # Usar functools.partial para evitar problemas de closure
        track_frame.bind("<Button-1>", partial(self._on_track_click, track_idx))
        remove_btn.configure(command=partial(self._on_remove_click, track_idx))
        
        # Guardar referencia
        self._track_frames.append(track_frame)
    
    def clear(self) -> None:
        """Limpia la vista de playlist"""
        for frame in self._track_frames:
            frame.destroy()
        self._track_frames.clear()
        self._current_tracks.clear()
        self._update_count(0)
    
    def update_track(self, index: int, is_current: bool) -> None:
        """
        Actualiza el estado de una pista
        
        Args:
            index: Índice de la pista a actualizar
            is_current: True si es la pista actual
        """
        if 0 <= index < len(self._track_frames):
            frame = self._track_frames[index]
            if is_current:
                frame.configure(fg_color=Styles.SECONDARY_COLOR)
                # Actualizar colores de labels
                for widget in frame.winfo_children():
                    if isinstance(widget, ctk.CTkLabel):
                        if widget.cget("text").endswith("."):
                            widget.configure(text_color=Styles.ACCENT_COLOR)
            else:
                frame.configure(fg_color="transparent")
                # Restaurar colores
                for widget in frame.winfo_children():
                    if isinstance(widget, ctk.CTkLabel):
                        if widget.cget("text").endswith("."):
                            widget.configure(text_color=Styles.TEXT_SECONDARY)
    
    def update_count(self, count: int) -> None:
        """
        Actualiza el contador de pistas
        
        Args:
            count: Número de pistas
        """
        self._update_count(count)
    
    def _update_count(self, count: int) -> None:
        """Actualiza el label de conteo"""
        self._count_label.configure(text=f"{count} track{'s' if count != 1 else ''}")
    
    def _format_duration(self, duration: float) -> str:
        """
        Formatea la duración en minutos:segundos
        
        Args:
            duration: Duración en segundos
            
        Returns:
            Duración formateada (MM:SS)
        """
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def _on_track_click(self, index: int) -> None:
        """
        Maneja el clic en una pista
        
        Args:
            index: Índice de la pista seleccionada
        """
        if self._on_track_select:
            self._on_track_select(index)
    
    def _on_remove_click(self, index: int) -> None:
        """
        Maneja el clic en el botón remover
        
        Args:
            index: Índice de la pista a remover
        """
        if self._on_remove_track:
            self._on_remove_track(index)
    
    def set_track_select_callback(self, callback: Callable[[int], None]) -> None:
        """
        Establece el callback para selección de pista
        
        Args:
            callback: Función a llamar al seleccionar una pista
        """
        self._on_track_select = callback
    
    def set_remove_track_callback(self, callback: Callable[[int], None]) -> None:
        """
        Establece el callback para remover pista
        
        Args:
            callback: Función a llamar al remover una pista
        """
        self._on_remove_track = callback
    
    def refresh_search(self) -> None:
        """Re-aplica el filtro de búsqueda activo tras refrescar la lista"""
        if self._search_entry.get():
            self._on_search()

    def _on_search(self) -> None:
        """Maneja la búsqueda en la playlist"""
        search_text = self._search_entry.get().lower()
        
        # Limpiar vista actual
        for frame in self._track_frames:
            frame.destroy()
        self._track_frames.clear()
        
        # Filtrar y mostrar pistas
        for track_data in self._current_tracks:
            title = track_data["title"].lower()
            artist = track_data["artist"].lower()
            
            if not search_text or search_text in title or search_text in artist:
                self._display_track(track_data)
        
        # Actualizar contador
        visible_count = len(self._track_frames)
        total_count = len(self._current_tracks)
        
        if search_text:
            self._count_label.configure(text=f"{visible_count}/{total_count} tracks")
        else:
            self._count_label.configure(text=f"{total_count} tracks")
