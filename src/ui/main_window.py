"""
MainWindow - Ventana principal ultra moderna de Musik Player.

Características del rediseño:
  * Layout responsivo por grid (la playlist se expande, todo se adapta).
  * Header con selector de temas (cambio en vivo sin reiniciar).
  * Tarjeta "Now Playing" con portada (CoverBadge), visualizador animado
    y tiempos grandes en tipografía mono.
  * Barra de estado con estado de reproducción, conteo y duración total.
  * Modo compacto automático al reducir la ventana (responsividad).
  * Atajo T para ciclar entre temas.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional
import logging
import queue
import time

from src.ui.styles import Styles, Theme
from src.ui.player_controls import PlayerControls
from src.ui.playlist_view import PlaylistView
from src.ui.widgets import Visualizer, CoverBadge, EllipsisLabel, Tooltip
from src.audio.player import AudioPlayer, PlayerState
from src.audio.playlist_manager import PlaylistManager, Track
from src.utils.file_handler import FileHandler
from src.utils.config_manager import ConfigManager
from src.utils.metadata_extractor import MetadataExtractor

logger = logging.getLogger(__name__)

# Umbral de ancho para activar el modo compacto (responsividad)
COMPACT_WIDTH = 840


class MainWindow(ctk.CTk):
    """Ventana principal del reproductor de música."""

    def __init__(self):
        """Inicializa la ventana principal."""
        super().__init__()

        # Configurar tema guardado antes de crear widgets
        self._config_manager = ConfigManager()
        Styles.setup_theme(self._config_manager.get_theme())

        # Configurar ventana
        self.title("Musik Player")
        self.configure(fg_color=Styles.PRIMARY_COLOR)

        # Inicializar componentes
        self._audio_player = AudioPlayer()
        self._playlist_manager = PlaylistManager()

        # Cargar configuración de shuffle/repeat
        self._playlist_manager.set_shuffle(self._config_manager.get_shuffle())
        self._playlist_manager.set_repeat_mode(self._config_manager.get_repeat_mode())

        # Cargar geometría desde configuración
        width, height, x, y = self._config_manager.get_window_geometry()
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(Styles.MIN_WIDTH, Styles.MIN_HEIGHT)

        # Cargar volumen desde configuración
        self._previous_volume = self._config_manager.get_volume()
        self._audio_player.set_volume(self._previous_volume)

        # Configurar callbacks del reproductor
        self._audio_player.set_position_callback(self._on_position_update)
        self._audio_player.set_track_end_callback(self._on_track_end)
        self._audio_player.set_error_callback(self._on_audio_error)

        # Variables de UI
        self._current_position = 0.0
        self._total_duration = 0.0
        self._is_seeking = False
        self._is_shuffle = self._config_manager.get_shuffle()
        self._repeat_mode = self._config_manager.get_repeat_mode()  # 0: off, 1: all, 2: one
        self._volume_save_job: Optional[str] = None
        self._compact = False

        # Cola thread-safe para comunicar eventos del hilo de audio a la UI.
        # El sondeo se programa una sola vez aquí (hilo principal) y se
        # re-programa a sí mismo, de modo que el hilo de audio nunca toca Tk.
        self._ui_queue = queue.Queue()
        self.after(50, self._poll_ui_queue)

        # Construir interfaz (antes de cargar la playlist para que la vista exista)
        self._build_ui()
        self._setup_callbacks()
        self._setup_keyboard_shortcuts()

        # Responsividad: adaptar layout al redimensionar
        self.bind("<Configure>", self._on_window_resize)

        # Cargar playlist guardada
        self._load_saved_playlist()

        # Estado inicial
        self._player_controls.set_volume(self._audio_player.get_volume())
        self._player_controls.set_shuffle_state(self._is_shuffle)
        self._player_controls.set_repeat_state(self._repeat_mode)
        self._update_ui_state()

        logger.info("Ventana principal inicializada")

    # ------------------------------------------------------------------
    # Construcción de la UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """(Re)construye toda la interfaz. Usado al iniciar y al cambiar de tema."""
        # Detener animaciones que referencien widgets viejos antes de destruirlos
        if hasattr(self, "_player_controls"):
            try:
                self._player_controls.stop_animations()
            except Exception:
                pass

        if hasattr(self, "_main_frame"):
            try:
                if self._main_frame.winfo_exists():
                    self._main_frame.destroy()
            except tk.TclError:
                pass

        self._main_frame = ctk.CTkFrame(self, fg_color=Styles.PRIMARY_COLOR)
        self._main_frame.pack(fill="both", expand=True)

        # Grid responsivo: la fila de la playlist (5) se expande
        self._main_frame.grid_columnconfigure(0, weight=1)
        self._main_frame.grid_rowconfigure(5, weight=1)

        self._build_header()
        self._build_now_playing()
        self._build_progress()
        self._build_controls()
        self._build_actions()
        self._build_playlist()
        self._build_status_bar()

    def _build_header(self) -> None:
        """Header: marca + selector de temas."""
        header = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 4))

        brand = ctk.CTkLabel(
            header,
            text="🎵 Musik Player",
            font=Styles.TITLE_FONT,
            text_color=Styles.TEXT_COLOR,
        )
        brand.pack(side="left")

        # Selector de tema (cambio en vivo)
        display_names = list(Theme.get_display_names().keys())
        self._theme_menu = ctk.CTkOptionMenu(
            header,
            values=display_names,
            command=self._on_theme_change,
            width=180,
            font=Styles.SMALL_FONT,
            fg_color=Styles.BUTTON_COLOR,
            button_color=Styles.ACCENT_COLOR,
            button_hover_color=Styles.ACCENT_HOVER,
            text_color=Styles.TEXT_COLOR,
            dropdown_fg_color=Styles.SECONDARY_COLOR,
            dropdown_hover_color=Styles.BUTTON_COLOR,
            dropdown_text_color=Styles.TEXT_COLOR,
            corner_radius=10,
        )
        self._theme_menu.pack(side="right")
        Tooltip(self._theme_menu, "Cambiar tema de la aplicación  (T)")
        self._theme_menu.set(self._display_name_for_theme(Styles.get_current_theme()))

    def _build_now_playing(self) -> None:
        """Tarjeta Now Playing: portada + info + visualizador + tiempo."""
        card = ctk.CTkFrame(self._main_frame, **Styles.get_frame_style("card"))
        card.grid(row=1, column=0, sticky="ew", padx=20, pady=(6, 8))
        card.grid_columnconfigure(1, weight=1)

        # Portada con la inicial de la pista
        self._cover_badge = CoverBadge(card, size=72, text="♪")
        self._cover_badge.grid(row=0, column=0, rowspan=2, padx=(16, 14), pady=12)

        # Columna de información
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", pady=(12, 2), padx=(0, 10))

        self._song_title_label = EllipsisLabel(
            info,
            text="No track loaded",
            font=Styles.SUBTITLE_FONT,
            text_color=Styles.TEXT_COLOR,
        )
        self._song_title_label.pack(fill="x")

        self._artist_label = EllipsisLabel(
            info,
            text="-",
            font=Styles.NORMAL_FONT,
            text_color=Styles.TEXT_SECONDARY,
        )
        self._artist_label.pack(fill="x", pady=(2, 0))

        # Ecualizador animado
        self._visualizer = Visualizer(card, bars=26, height=34, bg=Styles.CARD_COLOR)
        self._visualizer.grid(row=1, column=1, sticky="ew", padx=(14, 16), pady=(2, 12))

        # Tiempos grandes (columna derecha)
        time_col = ctk.CTkFrame(card, fg_color="transparent")
        time_col.grid(row=0, column=2, rowspan=2, padx=14, sticky="e")

        self._time_label = ctk.CTkLabel(
            time_col,
            text="00:00",
            font=("Consolas", 24, "bold"),
            text_color=Styles.ACCENT_COLOR,
        )
        self._time_label.pack(anchor="e")

        self._total_time_label = ctk.CTkLabel(
            time_col,
            text="/ 00:00",
            font=Styles.MONO_FONT,
            text_color=Styles.TEXT_SECONDARY,
        )
        self._total_time_label.pack(anchor="e")

    def _build_progress(self) -> None:
        """Barra de progreso de la pista actual."""
        progress_frame = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        progress_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(2, 2))

        self._progress_slider = ctk.CTkSlider(
            progress_frame,
            from_=0,
            to=100,
            number_of_steps=1000,
            **Styles.get_progress_style(),
        )
        self._progress_slider.pack(fill="x", pady=2)
        self._progress_slider.configure(command=self._on_progress_change)
        # Buscar solo al soltar el slider para evitar cortes de audio
        self._progress_slider.bind("<ButtonPress-1>", self._on_progress_press)
        self._progress_slider.bind("<ButtonRelease-1>", self._on_progress_release)
        Tooltip(self._progress_slider, "Arrastrar y soltar para buscar  (Ctrl+← / Ctrl+→)")

    def _build_controls(self) -> None:
        """Controles de reproducción (play, next, volumen, modos)."""
        self._player_controls = PlayerControls(self._main_frame)
        self._player_controls.grid(row=3, column=0, sticky="ew", padx=20, pady=(2, 2))

    def _build_actions(self) -> None:
        """Filas de acciones: cargar, limpiar, exportar (grid equilibrado)."""
        actions = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=20, pady=6)
        for col in range(3):
            actions.grid_columnconfigure(col, weight=1)

        self._action_buttons = []

        load_btn = ctk.CTkButton(
            actions,
            text="📁 Cargar Audio",
            height=36,
            **Styles.get_button_style("accent"),
        )
        load_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        load_btn.configure(command=self._on_load_files)
        Tooltip(load_btn, "Agregar archivos de audio  (L)")
        self._action_buttons.append((load_btn, "📁 Cargar Audio", "📁 Cargar"))

        clear_btn = ctk.CTkButton(
            actions,
            text="🗑 Limpiar Playlist",
            height=36,
            **Styles.get_button_style("secondary"),
        )
        clear_btn.grid(row=0, column=1, padx=5, sticky="ew")
        clear_btn.configure(command=self._on_clear_playlist)
        Tooltip(clear_btn, "Vaciar toda la playlist")
        self._action_buttons.append((clear_btn, "🗑 Limpiar Playlist", "🗑 Limpiar"))

        export_btn = ctk.CTkButton(
            actions,
            text="📤 Exportar M3U",
            height=36,
            **Styles.get_button_style("secondary"),
        )
        export_btn.grid(row=0, column=2, padx=(5, 0), sticky="ew")
        export_btn.configure(command=self._on_export_m3u)
        Tooltip(export_btn, "Guardar la playlist en formato M3U")
        self._action_buttons.append((export_btn, "📤 Exportar M3U", "📤 Exportar"))

    def _build_playlist(self) -> None:
        """Vista de playlist (se expande con la ventana)."""
        self._playlist_view = PlaylistView(self._main_frame)
        self._playlist_view.grid(row=5, column=0, sticky="nsew", padx=20, pady=(4, 6))

    def _build_status_bar(self) -> None:
        """Barra de estado inferior: estado + conteo + duración total."""
        status = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        status.grid(row=6, column=0, sticky="ew", padx=20, pady=(2, 10))

        left = ctk.CTkFrame(status, fg_color="transparent")
        left.pack(side="left")

        self._state_dot = ctk.CTkLabel(
            left,
            text="●",
            font=Styles.SMALL_FONT,
            text_color=Styles.TEXT_SECONDARY,
        )
        self._state_dot.pack(side="left", padx=(2, 4))

        self._state_label = ctk.CTkLabel(
            left,
            text="Detenido",
            font=Styles.SMALL_FONT,
            text_color=Styles.TEXT_SECONDARY,
        )
        self._state_label.pack(side="left")

        right = ctk.CTkFrame(status, fg_color="transparent")
        right.pack(side="right")

        self._total_duration_label = ctk.CTkLabel(
            right,
            text="Total 00:00",
            font=Styles.SMALL_FONT,
            text_color=Styles.TEXT_SECONDARY,
        )
        self._total_duration_label.pack(side="right", padx=(10, 0))

        self._track_count_label = ctk.CTkLabel(
            right,
            text="0 pistas",
            font=Styles.SMALL_FONT,
            text_color=Styles.ACCENT_COLOR,
        )
        self._track_count_label.pack(side="right")

    # ------------------------------------------------------------------
    # Callbacks de componentes
    # ------------------------------------------------------------------

    def _setup_callbacks(self) -> None:
        """Configura los callbacks de los componentes (tras cada rebuild)."""
        # Callbacks de controles
        self._player_controls.set_play_callback(self._on_play)
        self._player_controls.set_pause_callback(self._on_pause)
        self._player_controls.set_next_callback(self._on_next)
        self._player_controls.set_previous_callback(self._on_previous)
        self._player_controls.set_volume_callback(self._on_volume_change)
        self._player_controls.set_shuffle_callback(self._on_shuffle)
        self._player_controls.set_repeat_callback(self._on_repeat)

        # Callbacks de playlist
        self._playlist_view.set_track_select_callback(self._on_track_select)
        self._playlist_view.set_remove_track_callback(self._on_remove_track)

    # ------------------------------------------------------------------
    # Temas (cambio en vivo)
    # ------------------------------------------------------------------

    @staticmethod
    def _display_name_for_theme(theme_key: str) -> str:
        """Retorna el nombre visible de un tema dado su clave."""
        for display, key in Theme.get_display_names().items():
            if key == theme_key:
                return display
        return "🌙 Midnight Neon"

    def _on_theme_change(self, display_name: str) -> None:
        """
        Aplica un nuevo tema y reconstruye la UI en vivo.

        Args:
            display_name: Nombre visible del tema seleccionado.
        """
        theme_key = Theme.get_display_names().get(display_name, "dark_premium")
        if theme_key == Styles.get_current_theme():
            return

        self._config_manager.set_theme(theme_key)
        Styles.setup_theme(theme_key)
        self.configure(fg_color=Styles.PRIMARY_COLOR)
        self._rebuild_ui()
        logger.info(f"Tema cambiado a: {theme_key}")

    def _rebuild_ui(self) -> None:
        """Reconstruye la UI conservando todo el estado de reproducción."""
        was_playing = self._audio_player.get_state() == PlayerState.PLAYING

        self._build_ui()
        self._setup_callbacks()

        # Re-aplicar estado visual
        self._player_controls.set_volume(self._audio_player.get_volume())
        self._player_controls.set_shuffle_state(self._is_shuffle)
        self._player_controls.set_repeat_state(self._repeat_mode)

        self._refresh_playlist_view()
        self._update_track_info_display()
        self._update_progress_ui()
        self._update_ui_state()

        if was_playing:
            self._visualizer.set_playing(True)

    # ------------------------------------------------------------------
    # Carga de archivos y playlist
    # ------------------------------------------------------------------

    def _on_load_files(self) -> None:
        """Maneja la carga de archivos de audio."""
        file_paths = filedialog.askopenfilenames(
            title="Select Audio Files",
            filetypes=[
                ("Audio Files", "*.mp3 *.wav *.ogg *.flac"),
                ("MP3 Files", "*.mp3"),
                ("WAV Files", "*.wav"),
                ("OGG Files", "*.ogg"),
                ("FLAC Files", "*.flac"),
                ("All Files", "*.*"),
            ],
        )

        if file_paths:
            self._add_files_to_playlist(file_paths)

    def _add_files_to_playlist(self, file_paths: tuple) -> None:
        """
        Agrega archivos a la playlist procesando en lote.

        Args:
            file_paths: Tupla de rutas de archivos.
        """
        start_time = time.time()

        # Procesar archivos en lote
        new_tracks = []
        for file_path in file_paths:
            if not self._playlist_manager.has_track(file_path):
                try:
                    # Extraer metadatos
                    metadata = MetadataExtractor.extract_metadata(file_path)

                    # Crear track (la duración puede ser None si no se pudo obtener)
                    track = Track(
                        file_path=file_path,
                        title=metadata.get("title") or FileHandler.get_file_name(file_path),
                        artist=metadata.get("artist") or "Unknown",
                        duration=metadata.get("duration") or 0.0,
                    )
                    new_tracks.append(track)
                except Exception as e:
                    logger.warning(f"Error procesando {file_path}: {e}")

        # Agregar tracks en lote
        for track in new_tracks:
            self._playlist_manager.add_track(track)

        # Actualizar vista solo si hay cambios
        if new_tracks:
            self._refresh_playlist_view()

            # Si es la primera carga y no hay pista actual, cargar la primera
            if self._playlist_manager.get_current_index() == -1 and not self._playlist_manager.is_empty():
                self._playlist_manager.set_current_index(0)
                self._load_current_track()

            # Guardar playlist automáticamente en background
            self.after(1000, self._playlist_manager.save_playlist)

        elapsed = time.time() - start_time
        logger.info(f"Agregados {len(new_tracks)} tracks en {elapsed:.2f}s")

    def _load_saved_playlist(self) -> None:
        """Carga la playlist guardada al iniciar."""
        if self._playlist_manager.load_playlist():
            self._refresh_playlist_view()

            # Cargar la pista actual si existe
            if not self._playlist_manager.is_empty() and self._playlist_manager.get_current_index() >= 0:
                self._load_current_track()

            logger.info("Playlist guardada cargada exitosamente")

    def _refresh_playlist_view(self) -> None:
        """Actualiza la vista de la playlist."""
        self._playlist_view.clear()

        tracks = self._playlist_manager.get_all_tracks()
        current_index = self._playlist_manager.get_current_index()

        for i, track in enumerate(tracks):
            is_current = (i == current_index)
            self._playlist_view.add_track(
                title=track.title,
                artist=track.artist,
                duration=track.duration,
                index=i,
                is_current=is_current,
            )

        self._playlist_view.update_count(len(tracks))
        self._playlist_view.refresh_search()
        self._playlist_view.set_playing_state(self._audio_player.get_state() == PlayerState.PLAYING)
        self._update_status_bar()

    # ------------------------------------------------------------------
    # Reproducción
    # ------------------------------------------------------------------

    def _load_current_track(self) -> bool:
        """
        Carga la pista actual en el reproductor.

        Returns:
            True si se cargó exitosamente, False en caso contrario.
        """
        track = self._playlist_manager.get_current_track()
        if not track:
            return False

        if self._audio_player.load(track.file_path):
            self._update_track_info(track)
            self._total_duration = track.duration
            self._update_progress_ui()
            return True
        return False

    def _update_track_info(self, track: Track) -> None:
        """
        Actualiza la información de la pista en la UI.

        Args:
            track: Pista actual.
        """
        self._song_title_label.set_full_text(track.title)
        self._artist_label.set_full_text(track.artist)
        # Inicial para la portada (simula carátula de álbum)
        initial = (track.title or "♪").strip()[:1] or "♪"
        self._cover_badge.set_text(initial)

    def _update_track_info_display(self) -> None:
        """Re-aplica la información de la pista actual tras un rebuild."""
        track = self._playlist_manager.get_current_track()
        if track:
            self._update_track_info(track)
        else:
            self._song_title_label.set_full_text("No track loaded")
            self._artist_label.set_full_text("-")
            self._cover_badge.set_text("♪")

    def _on_play(self) -> None:
        """Maneja el evento de play."""
        if self._audio_player.get_state() == PlayerState.PAUSED:
            self._audio_player.resume()
        else:
            if not self._playlist_manager.get_current_track():
                if not self._playlist_manager.is_empty():
                    self._playlist_manager.set_current_index(0)
                    self._load_current_track()

            if self._audio_player.get_state() != PlayerState.PLAYING:
                self._audio_player.play()

        self._update_ui_state()

    def _on_pause(self) -> None:
        """Maneja el evento de pause."""
        self._audio_player.pause()
        self._update_ui_state()

    def _on_next(self) -> None:
        """Maneja el evento de siguiente pista."""
        if self._playlist_manager.next():
            was_playing = self._audio_player.get_state() == PlayerState.PLAYING
            self._load_current_track()
            if was_playing:
                self._audio_player.play()
            self._refresh_playlist_view()
        else:
            # No hay más pistas: detener la reproducción
            self._audio_player.stop()
            self._update_progress_ui()
        self._update_ui_state()

    def _on_previous(self) -> None:
        """Maneja el evento de pista anterior."""
        if self._playlist_manager.previous():
            was_playing = self._audio_player.get_state() == PlayerState.PLAYING
            self._load_current_track()
            if was_playing:
                self._audio_player.play()
            self._refresh_playlist_view()
            self._update_ui_state()

    def _on_volume_change(self, volume: float) -> None:
        """
        Maneja el cambio de volumen (con guardado diferido).

        Args:
            volume: Nuevo volumen (0.0 - 1.0).
        """
        self._audio_player.set_volume(volume)
        self._config_manager.set_volume(volume, save=False)

        # Guardado diferido para no escribir el archivo en cada movimiento del slider
        if self._volume_save_job is not None:
            try:
                self.after_cancel(self._volume_save_job)
            except Exception:
                pass
        self._volume_save_job = self.after(500, self._save_volume_config)

    def _save_volume_config(self) -> None:
        """Guarda la configuración de volumen."""
        self._volume_save_job = None
        self._config_manager.save()

    def _on_track_select(self, index: int) -> None:
        """
        Maneja la selección de una pista en la playlist.

        Args:
            index: Índice de la pista seleccionada.
        """
        if self._playlist_manager.set_current_index(index):
            was_playing = self._audio_player.get_state() == PlayerState.PLAYING
            self._load_current_track()
            if was_playing:
                self._audio_player.play()
            self._refresh_playlist_view()
            self._update_ui_state()

    def _on_remove_track(self, index: int) -> None:
        """
        Maneja la remoción de una pista.

        Args:
            index: Índice de la pista a remover.
        """
        was_current = (index == self._playlist_manager.get_current_index())

        if self._playlist_manager.remove_track(index):
            if was_current:
                self._audio_player.stop()
                self._update_track_info_display()
                self._current_position = 0.0
                self._total_duration = 0.0
                self._update_progress_ui()

            self._refresh_playlist_view()
            self._update_ui_state()

            # Guardar playlist automáticamente
            self._playlist_manager.save_playlist()

    def _on_clear_playlist(self) -> None:
        """Vacía la playlist completa."""
        if self._playlist_manager.is_empty():
            return

        if not messagebox.askyesno("Clear Playlist", "¿Eliminar todas las pistas de la playlist?"):
            return

        self._playlist_manager.clear()
        self._audio_player.stop()
        self._current_position = 0.0
        self._total_duration = 0.0
        self._update_track_info_display()

        self._refresh_playlist_view()
        self._update_progress_ui()
        self._update_ui_state()
        self._playlist_manager.save_playlist()
        logger.info("Playlist vaciada")

    def _on_export_m3u(self) -> None:
        """Exporta la playlist actual a un archivo M3U."""
        if self._playlist_manager.is_empty():
            messagebox.showinfo("Export M3U", "La playlist está vacía.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Export Playlist as M3U",
            defaultextension=".m3u",
            filetypes=[("M3U Playlist", "*.m3u"), ("All Files", "*.*")],
        )

        if file_path:
            if self._playlist_manager.create_m3u_playlist(file_path):
                messagebox.showinfo("Export M3U", f"Playlist exportada a:\n{file_path}")
            else:
                messagebox.showerror("Export M3U", "No se pudo exportar la playlist.")

    # ------------------------------------------------------------------
    # Barra de progreso
    # ------------------------------------------------------------------

    def _on_progress_press(self, event=None) -> None:
        """Marca el inicio de un arrastre en la barra de progreso."""
        self._is_seeking = True

    def _on_progress_release(self, event=None) -> None:
        """Maneja la liberación de la barra de progreso (busca la posición)."""
        self._is_seeking = False
        if self._total_duration > 0:
            position = (self._progress_slider.get() / 100.0) * self._total_duration
            self._audio_player.seek(position)
            self._current_position = position
            self._update_progress_ui()

    def _on_progress_change(self, value: float) -> None:
        """
        Maneja el arrastre en la barra de progreso (solo vista previa).

        Args:
            value: Nuevo valor del slider (0-100).
        """
        if self._total_duration > 0:
            self._is_seeking = True
            preview_position = (value / 100.0) * self._total_duration
            self._time_label.configure(text=self._format_time(preview_position))

    # ------------------------------------------------------------------
    # Hilo de audio → UI (cola thread-safe)
    # ------------------------------------------------------------------

    def _enqueue_ui(self, event: str, *args) -> None:
        """
        Encola un evento del hilo de audio para procesarlo en el hilo principal.

        Args:
            event: Tipo de evento (pos, end, error).
            *args: Argumentos del evento.
        """
        self._ui_queue.put((event, args))

    def _poll_ui_queue(self) -> None:
        """Procesa los eventos encolados por el hilo de audio (hilo principal)."""
        events = []
        try:
            while True:
                events.append(self._ui_queue.get_nowait())
        except queue.Empty:
            pass

        for event, args in events:
            if event == "pos":
                self._current_position = args[0]
                self._total_duration = args[1]
            elif event == "end":
                self._on_next()
            elif event == "error":
                messagebox.showerror("Audio Error", f"Ocurrió un error de audio:\n{args[0]}")

        if events:
            self._update_progress_ui()

        self.after(50, self._poll_ui_queue)

    def _on_position_update(self, position: float, duration: float) -> None:
        """
        Callback de posición (hilo de audio): solo encola la actualización.

        Args:
            position: Posición actual en segundos.
            duration: Duración total en segundos.
        """
        self._enqueue_ui("pos", position, duration)

    def _on_track_end(self) -> None:
        """Callback cuando termina una pista (hilo de audio)."""
        if self._playlist_manager.get_repeat_mode() == 2:  # Repeat one
            # Repetir la misma canción (llamada segura de pygame)
            self._audio_player.play()
        else:
            # Avanzar a la siguiente canción en el hilo principal
            self._enqueue_ui("end")

    def _on_audio_error(self, error_message: str) -> None:
        """
        Maneja errores del reproductor de audio (hilo de audio).

        Args:
            error_message: Mensaje de error.
        """
        logger.error(f"Error de audio: {error_message}")
        self._enqueue_ui("error", error_message)

    # ------------------------------------------------------------------
    # Actualización de la UI
    # ------------------------------------------------------------------

    def _update_progress_ui(self) -> None:
        """Actualiza la UI de la barra de progreso y los tiempos."""
        if self._is_seeking:
            return

        if self._total_duration > 0:
            progress = (self._current_position / self._total_duration) * 100
            self._progress_slider.set(progress)

            current_time = self._format_time(self._current_position)
            total_time = self._format_time(self._total_duration)
            self._time_label.configure(text=current_time)
            self._total_time_label.configure(text=f"/ {total_time}")
        else:
            self._progress_slider.set(0)
            self._time_label.configure(text="00:00")
            self._total_time_label.configure(text="/ 00:00")

    def _update_ui_state(self) -> None:
        """Actualiza el estado de la UI según el estado del reproductor."""
        state = self._audio_player.get_state()
        is_playing = (state == PlayerState.PLAYING)

        self._player_controls.set_playing_state(is_playing)
        self._playlist_view.set_playing_state(is_playing)
        self._visualizer.set_playing(is_playing)

        has_track = self._playlist_manager.get_current_track() is not None
        self._player_controls.set_enabled(has_track)

        self._update_status_bar()

    def _update_status_bar(self) -> None:
        """Actualiza la barra de estado: estado, conteo y duración total."""
        state = self._audio_player.get_state()
        if state == PlayerState.PLAYING:
            color, text = Styles.SUCCESS_COLOR, "Reproduciendo"
        elif state == PlayerState.PAUSED:
            color, text = Styles.WARNING_COLOR, "Pausado"
        else:
            color, text = Styles.TEXT_SECONDARY, "Detenido"

        self._state_dot.configure(text_color=color)
        self._state_label.configure(text=text)

        tracks = self._playlist_manager.get_all_tracks()
        total_seconds = sum(t.duration or 0 for t in tracks)
        self._track_count_label.configure(
            text=f"{len(tracks)} pista{'s' if len(tracks) != 1 else ''}"
        )
        self._total_duration_label.configure(text=f"Total {self._format_time(total_seconds)}")

    @staticmethod
    def _format_time(seconds: float) -> str:
        """
        Formatea tiempo en minutos:segundos.

        Args:
            seconds: Tiempo en segundos.

        Returns:
            Tiempo formateado (MM:SS).
        """
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    # ------------------------------------------------------------------
    # Responsividad
    # ------------------------------------------------------------------

    def _on_window_resize(self, event) -> None:
        """Activa/desactiva el modo compacto según el ancho de la ventana."""
        if event.widget is not self:
            return
        compact = event.width < COMPACT_WIDTH
        if compact != self._compact:
            self._compact = compact
            self.after_idle(self._apply_compact)

    def _apply_compact(self) -> None:
        """Ajusta textos y tamaños para ventanas estrechas."""
        for btn, normal_text, compact_text in self._action_buttons:
            try:
                btn.configure(text=compact_text if self._compact else normal_text)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Atajos de teclado
    # ------------------------------------------------------------------

    def _guard_shortcut(self, func):
        """
        Evita que los atajos de teclado se disparen mientras se escribe
        en un campo de texto.

        Args:
            func: Función a ejecutar si el foco no está en un entry.

        Returns:
            Wrapper que verifica el foco antes de ejecutar.
        """
        def _wrapper(event=None):
            widget = self.focus_get()
            if isinstance(widget, (ctk.CTkEntry, tk.Entry, tk.Text)):
                return
            return func()
        return _wrapper

    def _setup_keyboard_shortcuts(self) -> None:
        """Configura los atajos de teclado."""
        # Espacio: Play/Pause
        self.bind("<space>", self._guard_shortcut(self._toggle_play_pause))

        # Flecha izquierda: Anterior (con Ctrl para retroceder 10s)
        self.bind("<Left>", self._guard_shortcut(self._on_previous))
        self.bind("<Control-Left>", self._guard_shortcut(self._seek_backward))

        # Flecha derecha: Siguiente (con Ctrl para avanzar 10s)
        self.bind("<Right>", self._guard_shortcut(self._on_next))
        self.bind("<Control-Right>", self._guard_shortcut(self._seek_forward))

        # Flecha arriba: Subir volumen
        self.bind("<Up>", self._guard_shortcut(self._volume_up))

        # Flecha abajo: Bajar volumen
        self.bind("<Down>", self._guard_shortcut(self._volume_down))

        # M: Mute/Unmute
        self.bind("<m>", self._guard_shortcut(self._toggle_mute))

        # S: Toggle Shuffle
        self.bind("<s>", self._guard_shortcut(self._on_shuffle))

        # R: Toggle Repeat
        self.bind("<r>", self._guard_shortcut(self._on_repeat))

        # L: Load files
        self.bind("<l>", self._guard_shortcut(self._on_load_files))

        # T: Cycle theme
        self.bind("<t>", self._guard_shortcut(self._cycle_theme))

        # Q: Quit
        self.bind("<q>", self._guard_shortcut(self._on_close))

        # F: Toggle fullscreen
        self.bind("<f>", self._guard_shortcut(self._toggle_fullscreen))

        # Escape: Exit fullscreen
        self.bind("<Escape>", lambda e: self._exit_fullscreen())

        logger.info("Atajos de teclado configurados")

    def _cycle_theme(self) -> None:
        """Cicla entre los temas disponibles (atajo T)."""
        keys = Theme.get_available_themes()
        current = Styles.get_current_theme()
        index = keys.index(current) if current in keys else 0
        next_key = keys[(index + 1) % len(keys)]
        display = self._display_name_for_theme(next_key)
        try:
            self._theme_menu.set(display)
        except Exception:
            pass
        self._on_theme_change(display)

    # ------------------------------------------------------------------
    # Controles auxiliares
    # ------------------------------------------------------------------

    def _toggle_play_pause(self) -> None:
        """Alterna entre play y pause."""
        state = self._audio_player.get_state()
        if state == PlayerState.PLAYING:
            self._on_pause()
        else:
            self._on_play()

    def _seek_backward(self) -> None:
        """Retrocede 10 segundos."""
        current_pos = self._audio_player.get_position()
        new_pos = max(0, current_pos - 10)
        self._audio_player.seek(new_pos)
        logger.info(f"Retrocediendo a {new_pos}s")

    def _seek_forward(self) -> None:
        """Avanza 10 segundos."""
        current_pos = self._audio_player.get_position()
        duration = self._audio_player.get_duration()
        new_pos = min(duration, current_pos + 10)
        self._audio_player.seek(new_pos)
        logger.info(f"Avanzando a {new_pos}s")

    def _volume_up(self) -> None:
        """Sube el volumen un 10%."""
        current_vol = self._audio_player.get_volume()
        new_vol = min(1.0, current_vol + 0.1)
        self._on_volume_change(new_vol)
        self._player_controls.set_volume(new_vol)
        logger.info(f"Volumen: {int(new_vol * 100)}%")

    def _volume_down(self) -> None:
        """Baja el volumen un 10%."""
        current_vol = self._audio_player.get_volume()
        new_vol = max(0.0, current_vol - 0.1)
        self._on_volume_change(new_vol)
        self._player_controls.set_volume(new_vol)
        logger.info(f"Volumen: {int(new_vol * 100)}%")

    def _toggle_mute(self) -> None:
        """Alterna entre mute y unmute."""
        current_vol = self._audio_player.get_volume()
        if current_vol > 0:
            self._previous_volume = current_vol
            self._on_volume_change(0.0)
            self._player_controls.set_volume(0.0)
            logger.info("Volumen silenciado")
        else:
            new_vol = getattr(self, '_previous_volume', 0.7)
            self._on_volume_change(new_vol)
            self._player_controls.set_volume(new_vol)
            logger.info(f"Volumen restaurado: {int(new_vol * 100)}%")

    def _toggle_shuffle(self) -> None:
        """Alterna el modo shuffle."""
        current_shuffle = self._playlist_manager.get_shuffle()
        new_shuffle = not current_shuffle
        self._playlist_manager.set_shuffle(new_shuffle)
        self._config_manager.set_shuffle(new_shuffle)
        self._is_shuffle = new_shuffle
        self._player_controls.set_shuffle_state(new_shuffle)
        logger.info(f"Shuffle: {'Activado' if new_shuffle else 'Desactivado'}")

    def _toggle_repeat(self) -> None:
        """Alterna el modo repeat."""
        current_mode = self._playlist_manager.get_repeat_mode()
        new_mode = (current_mode + 1) % 3
        self._playlist_manager.set_repeat_mode(new_mode)
        self._config_manager.set_repeat_mode(new_mode)
        self._repeat_mode = new_mode
        self._player_controls.set_repeat_state(new_mode)
        modes = ["Off", "Repeat All", "Repeat One"]
        logger.info(f"Repeat: {modes[new_mode]}")

    def _on_shuffle(self) -> None:
        """Maneja el clic en el botón shuffle."""
        self._toggle_shuffle()

    def _on_repeat(self) -> None:
        """Maneja el clic en el botón repeat."""
        self._toggle_repeat()

    def _toggle_fullscreen(self) -> None:
        """Alterna el modo pantalla completa."""
        current_state = self.attributes("-fullscreen")
        self.attributes("-fullscreen", not current_state)
        logger.info(f"Fullscreen: {'Activado' if not current_state else 'Desactivado'}")

    def _exit_fullscreen(self) -> None:
        """Sale del modo pantalla completa."""
        self.attributes("-fullscreen", False)
        logger.info("Fullscreen desactivado")

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Limpia recursos antes de cerrar."""
        try:
            self._player_controls.stop_animations()
        except Exception:
            pass
        self._audio_player.cleanup()

    def run(self) -> None:
        """Inicia el bucle principal de la aplicación."""
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.mainloop()
        except Exception as e:
            logger.error(f"Error en mainloop: {e}")
        finally:
            logger.info("Aplicación finalizada")

    def _on_close(self) -> None:
        """Maneja el cierre de la ventana."""
        try:
            # Guardar geometría de ventana
            self.update_idletasks()
            geometry = self.geometry()
            parts = geometry.split('+')
            if len(parts) >= 3:
                size = parts[0].split('x')
                if len(size) == 2:
                    width = int(size[0])
                    height = int(size[1])
                    x = int(parts[1])
                    y = int(parts[2])
                    self._config_manager.set_window_geometry(width, height, x, y)

            # Guardar volumen actual
            current_volume = self._audio_player.get_volume()
            self._config_manager.set_volume(current_volume)

            # Guardar estado de shuffle/repeat
            self._config_manager.set_shuffle(self._playlist_manager.get_shuffle())
            self._config_manager.set_repeat_mode(self._playlist_manager.get_repeat_mode())

            # Guardar playlist y configuración
            self._playlist_manager.save_playlist()
            self._config_manager.save()

            logger.info("Configuración guardada exitosamente")
        except Exception as e:
            logger.error(f"Error guardando configuración: {e}")
        finally:
            # Limpiar recursos
            self.cleanup()
            self.destroy()
            logger.info("Aplicación cerrada correctamente")