"""
PlaylistView - Vista de lista de reproducción ultra moderna.

Incluye:
  * Filas tipo tarjeta (card) con esquinas redondeadas.
  * Resaltado al pasar el ratón (hover) en filas y búsqueda en vivo.
  * Indicador animado (mini ecualizador) en la pista en reproducción.
  * Títulos con elipsis automática para anchos pequeños (responsividad).
  * Contador en forma de píldora con resultado de búsqueda.
"""

from functools import partial
from typing import Callable, List, Optional

import customtkinter as ctk

from src.ui.styles import Styles, lighten
from src.ui.widgets import Visualizer, EllipsisLabel, Tooltip


class PlaylistView(ctk.CTkFrame):
    """Frame que muestra la lista de reproducción."""

    def __init__(self, master, **kwargs):
        """
        Args:
            master: Widget padre.
            **kwargs: Argumentos adicionales para CTkFrame.
        """
        super().__init__(master, **kwargs)

        self._on_track_select: Optional[Callable[[int], None]] = None
        self._on_remove_track: Optional[Callable[[int], None]] = None

        # Widgets de las filas (paralelo a _track_frames para actualizar estilos)
        self._track_frames: List[ctk.CTkFrame] = []
        self._row_data: List[dict] = []
        # Pistas actuales (filtradas o todas)
        self._current_tracks: List[dict] = []
        # Indicador animado de la pista en reproducción
        self._current_viz: Optional[Visualizer] = None
        self._playing_state = False

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Configura la interfaz de la playlist."""
        self.configure(fg_color="transparent")

        # Header: título + contador (píldora)
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=6, pady=(4, 6))

        title_label = ctk.CTkLabel(
            header_frame,
            text="Playlist",
            font=Styles.SUBTITLE_FONT,
            text_color=Styles.TEXT_COLOR,
        )
        title_label.pack(side="left")

        self._count_label = ctk.CTkLabel(
            header_frame,
            text="0 tracks",
            font=Styles.SMALL_FONT,
            text_color=Styles.TEXT_SECONDARY,
            fg_color=Styles.SECONDARY_COLOR,
            corner_radius=10,
        )
        self._count_label.pack(side="right", padx=(6, 0), pady=2)

        # Búsqueda en vivo
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=6, pady=(0, 6))

        self._search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="🔍 Buscar por título o artista...",
            height=32,
            font=Styles.NORMAL_FONT,
            fg_color=Styles.SECONDARY_COLOR,
            border_color=Styles.BORDER_COLOR,
            border_width=1,
            corner_radius=10,
        )
        self._search_entry.pack(fill="x")
        self._search_entry.bind("<KeyRelease>", lambda e: self._on_search())

        # Lista con scroll
        self._scrollable_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            label_text="",
        )
        self._scrollable_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))

    # ------------------------------------------------------------------
    # Poblado de la vista
    # ------------------------------------------------------------------

    def add_track(self, title: str, artist: str, duration: float, index: int,
                  is_current: bool = False) -> None:
        """
        Agrega una pista a la vista.

        Args:
            title: Título de la canción.
            artist: Artista de la canción.
            duration: Duración en segundos.
            index: Índice de la pista.
            is_current: True si es la pista actual.
        """
        track_data = {
            "title": title,
            "artist": artist,
            "duration": duration,
            "index": index,
            "is_current": is_current,
        }
        self._current_tracks.append(track_data)

        # Solo mostrar si coincide con la búsqueda activa
        search_text = self._search_entry.get().lower()
        if not search_text or search_text in title.lower() or search_text in artist.lower():
            self._display_track(track_data)

    def _display_track(self, track_data: dict) -> None:
        """
        Muestra una pista en la vista (crea la fila tarjeta).

        Args:
            track_data: Diccionario con la información de la pista.
        """
        title = track_data["title"]
        artist = track_data["artist"]
        duration = track_data["duration"]
        index = track_data["index"]
        is_current = track_data["is_current"]

        base_bg = Styles.CARD_COLOR if is_current else "transparent"
        hover_bg = lighten(Styles.CARD_COLOR, 0.06) if is_current else Styles.BUTTON_COLOR

        # Fila tarjeta
        row = ctk.CTkFrame(
            self._scrollable_frame,
            fg_color=base_bg,
            corner_radius=10,
        )
        row.pack(fill="x", pady=2)
        row.grid_columnconfigure(1, weight=1)  # info expande

        # Columna 0: indicador de reproducción o número de pista
        if is_current:
            viz = Visualizer(row, bars=6, height=22, bg=Styles.CARD_COLOR, bar_width=4)
            viz.grid(row=0, column=0, padx=(10, 4), pady=10)
            viz.set_playing(self._playing_state)
            self._current_viz = viz
            indicator = viz
        else:
            index_label = ctk.CTkLabel(
                row,
                text=f"{index + 1}",
                font=Styles.MONO_FONT,
                text_color=Styles.TEXT_SECONDARY,
                width=34,
            )
            index_label.grid(row=0, column=0, padx=(10, 2), pady=10)
            indicator = index_label

        # Columna 1: título + artista (con elipsis responsiva)
        info_frame = ctk.CTkFrame(row, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="w", padx=6, pady=8)

        title_label = EllipsisLabel(
            info_frame,
            text=title,
            font=Styles.NORMAL_FONT,
            text_color=Styles.ACCENT_COLOR if is_current else Styles.TEXT_COLOR,
        )
        title_label.pack(fill="x")

        artist_label = EllipsisLabel(
            info_frame,
            text=artist,
            font=Styles.SMALL_FONT,
            text_color=Styles.TEXT_SECONDARY,
        )
        artist_label.pack(fill="x")

        # Columna 2: duración
        duration_label = ctk.CTkLabel(
            row,
            text=self._format_duration(duration),
            font=Styles.MONO_FONT,
            text_color=Styles.TEXT_SECONDARY,
            width=50,
        )
        duration_label.grid(row=0, column=2, padx=6, pady=10)

        # Columna 3: botón remover
        remove_btn = ctk.CTkButton(
            row,
            text="✕",
            width=28,
            height=28,
            font=("Segoe UI", 11),
            fg_color=Styles.BUTTON_COLOR,
            hover_color=Styles.ERROR_COLOR,
            text_color=Styles.TEXT_COLOR,
            corner_radius=8,
        )
        remove_btn.grid(row=0, column=3, padx=(2, 8), pady=10)
        Tooltip(remove_btn, "Quitar de la playlist")

        # Clic en la fila (y en sus hijos) selecciona la pista
        track_idx = index
        click = partial(self._on_track_click, track_idx)
        for widget in (row, indicator, info_frame, title_label, artist_label, duration_label):
            widget.bind("<Button-1>", click, add="+")

        remove_btn.configure(command=partial(self._on_remove_click, track_idx))

        # Hover: resaltar la fila
        self._bind_row_hover(row, hover_bg, base_bg)

        # Guardar referencias para clear() / update_track()
        self._track_frames.append(row)
        self._row_data.append({
            "index": index,
            "frame": row,
            "title_label": title_label,
            "indicator": indicator,
        })

    def _bind_row_hover(self, row: ctk.CTkFrame, hover_bg: str, normal_bg: str) -> None:
        """
        Aplica resaltado al pasar el ratón sobre la fila.

        Args:
            row: Frame de la fila.
            hover_bg: Color de fondo en hover.
            normal_bg: Color de fondo en reposo.
        """
        def _hover(event=None) -> None:
            try:
                row.configure(fg_color=hover_bg)
            except Exception:
                pass

        def _leave(event=None) -> None:
            try:
                row.configure(fg_color=normal_bg)
            except Exception:
                pass

        row.bind("<Enter>", _hover, add="+")
        row.bind("<Leave>", _leave, add="+")
        # Los hijos no tienen su propio fondo, pero el Enter/Leave de cada
        # uno dispara el resaltado sin parpadeos.
        for child in self._all_children(row):
            child.bind("<Enter>", _hover, add="+")
            child.bind("<Leave>", _leave, add="+")

    @staticmethod
    def _all_children(widget) -> List:
        """Retorna todos los descendientes de un widget (recursivo)."""
        children = list(widget.winfo_children())
        for child in list(children):
            children.extend(PlaylistView._all_children(child))
        return children

    # ------------------------------------------------------------------
    # Estado de reproducción
    # ------------------------------------------------------------------

    def set_playing_state(self, is_playing: bool) -> None:
        """
        Sincroniza el mini ecualizador de la pista actual.

        Args:
            is_playing: True si el reproductor está sonando.
        """
        self._playing_state = is_playing
        if self._current_viz is not None:
            try:
                self._current_viz.set_playing(is_playing)
            except Exception:
                pass

    def clear(self) -> None:
        """Limpia la vista de playlist."""
        for frame in self._track_frames:
            frame.destroy()
        self._track_frames.clear()
        self._row_data.clear()
        self._current_tracks.clear()
        self._current_viz = None
        self._update_count(0)

    def update_track(self, index: int, is_current: bool) -> None:
        """
        Actualiza el estilo de una pista sin reconstruir la lista.

        Args:
            index: Índice de la pista a actualizar.
            is_current: True si ahora es la pista actual.
        """
        for row_info in self._row_data:
            if row_info["index"] != index:
                continue
            row = row_info["frame"]
            title_label = row_info["title_label"]
            try:
                if is_current:
                    row.configure(fg_color=Styles.CARD_COLOR)
                    title_label.configure(text_color=Styles.ACCENT_COLOR)
                else:
                    row.configure(fg_color="transparent")
                    title_label.configure(text_color=Styles.TEXT_COLOR)
            except Exception:
                pass
            return

    def update_count(self, count: int) -> None:
        """Actualiza el contador de pistas."""
        self._update_count(count)

    def _update_count(self, count: int) -> None:
        """Actualiza el label de conteo."""
        self._count_label.configure(text=f"{count} track{'s' if count != 1 else ''}")

    # ------------------------------------------------------------------
    # Formato
    # ------------------------------------------------------------------

    @staticmethod
    def _format_duration(duration: float) -> str:
        """
        Formatea la duración en minutos:segundos.

        Args:
            duration: Duración en segundos.

        Returns:
            Duración formateada (MM:SS).
        """
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        return f"{minutes:02d}:{seconds:02d}"

    # ------------------------------------------------------------------
    # Búsqueda
    # ------------------------------------------------------------------

    def refresh_search(self) -> None:
        """Re-aplica el filtro de búsqueda activo tras refrescar la lista."""
        if self._search_entry.get():
            self._on_search()

    def _on_search(self) -> None:
        """Maneja la búsqueda en la playlist (filtrado en vivo)."""
        search_text = self._search_entry.get().lower()

        # Limpiar vista actual
        for frame in self._track_frames:
            frame.destroy()
        self._track_frames.clear()
        self._row_data.clear()
        self._current_viz = None

        # Filtrar y mostrar pistas
        for track_data in self._current_tracks:
            title = track_data["title"].lower()
            artist = track_data["artist"].lower()
            if not search_text or search_text in title or search_text in artist:
                self._display_track(track_data)

        # Actualizar contador (visible/total cuando hay búsqueda)
        visible_count = len(self._track_frames)
        total_count = len(self._current_tracks)
        if search_text:
            self._count_label.configure(text=f"{visible_count}/{total_count} tracks")
        else:
            self._count_label.configure(text=f"{total_count} tracks")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_track_click(self, index: int) -> None:
        """Maneja el clic en una pista."""
        if self._on_track_select:
            self._on_track_select(index)

    def _on_remove_click(self, index: int) -> None:
        """Maneja el clic en el botón remover."""
        if self._on_remove_track:
            self._on_remove_track(index)

    def set_track_select_callback(self, callback: Callable[[int], None]) -> None:
        """Establece el callback para selección de pista."""
        self._on_track_select = callback

    def set_remove_track_callback(self, callback: Callable[[int], None]) -> None:
        """Establece el callback para remover pista."""
        self._on_remove_track = callback