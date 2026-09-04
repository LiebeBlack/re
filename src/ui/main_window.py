"""
MainWindow - Ventana principal del reproductor de audio avanzado.

Integra:
  * Motor dual (streaming / HQ-DSP) con decode en hilo secundario.
  * Carátula de álbum real (embebida) con fallback a inicial con gradiente.
  * Chips de metadatos técnicos (formato, bitrate, kHz, canales, bits).
  * Forma de onda de la pista en modo HQ + cabezal de reproducción.
  * Panel de ecualizador de 10 bandas (desplegable, compacto).
  * Configuración de salida (driver WASAPI/ALSA/Pulse, buffer, rate, HQ).
  * Layout responsivo compacto, temas en vivo, barra de estado.
"""

import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, Optional

import customtkinter as ctk

from src.audio.player import AudioPlayer, PlayerState
from src.audio.playlist_manager import PlaylistManager, Track
from src.ui.audio_panel import AudioSettingsPopup, EqPanel, MetaChips
from src.ui.player_controls import PlayerControls
from src.ui.playlist_view import PlaylistView
from src.ui.styles import Styles, Theme
from src.ui.widgets import AlbumArt, EllipsisLabel, Tooltip, Visualizer, WaveformView
from src.utils.config_manager import ConfigManager
from src.utils.file_handler import FileHandler
from src.utils.metadata_extractor import MetadataExtractor

logger = logging.getLogger(__name__)

# Umbral de ancho para el modo compacto (responsividad)
COMPACT_WIDTH = 860


class MainWindow(ctk.CTk):
    """Ventana principal del reproductor."""

    def __init__(self):
        super().__init__()

        # Configurar tema guardado antes de crear widgets
        self._config_manager = ConfigManager()
        Styles.setup_theme(self._config_manager.get_theme())

        self.title("Musik Player — Hi-Res Audio")
        self.configure(fg_color=Styles.PRIMARY_COLOR)

        # Crear el motor con la configuración guardada
        cfg = self._config_manager
        self._audio_player = AudioPlayer(settings=self._player_settings_from_config())
        self._playlist_manager = PlaylistManager()
        self._playlist_manager.set_shuffle(cfg.get_shuffle())
        self._playlist_manager.set_repeat_mode(cfg.get_repeat_mode())

        width, height, x, y = cfg.get_window_geometry()
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(Styles.MIN_WIDTH, Styles.MIN_HEIGHT)

        self._previous_volume = cfg.get_volume()
        self._audio_player.set_volume(self._previous_volume)

        # Callbacks del motor
        self._audio_player.set_position_callback(self._on_position_update)
        self._audio_player.set_track_end_callback(self._on_track_end)
        self._audio_player.set_error_callback(self._on_audio_error)
        self._audio_player.set_track_ready_callback(self._on_hq_track_ready)

        # Estado de UI
        self._current_position = 0.0
        self._total_duration = 0.0
        self._is_seeking = False
        self._is_shuffle = cfg.get_shuffle()
        self._repeat_mode = cfg.get_repeat_mode()
        self._volume_save_job: Optional[str] = None
        self._compact = False
        self._last_progress_ui_time = 0.0
        self._progress_ui_interval = 0.15

        # Cachés de metadatos/carátulas/análisis por ruta
        self._meta_cache: Dict[str, dict] = {}
        self._art_cache: Dict[str, Optional[str]] = {}
        self._analysis: Optional[dict] = None
        self._current_meta: dict = {}

        # Cola thread-safe hilo de audio -> UI
        self._ui_queue = queue.Queue()
        self.after(50, self._poll_ui_queue)

        self._build_ui()
        self._setup_callbacks()
        self._setup_keyboard_shortcuts()
        self.bind("<Configure>", self._on_window_resize)

        self._load_saved_playlist()

        self._player_controls.set_volume(self._audio_player.get_volume())
        self._player_controls.set_shuffle_state(self._is_shuffle)
        self._player_controls.set_repeat_state(self._repeat_mode)
        self._sync_eq_panel_from_config()
        self._update_ui_state()

        logger.info("Ventana principal inicializada")

    # ------------------------------------------------------------------
    # Configuración del motor
    # ------------------------------------------------------------------

    def _player_settings_from_config(self) -> Dict:
        cfg = self._config_manager
        return {
            "audio_driver": cfg.get_audio_driver(),
            "sample_rate": cfg.get_sample_rate(),
            "buffer_size": cfg.get_buffer_size(),
            "output_depth": cfg.get_output_depth(),
            "hq_engine": cfg.get_hq_engine(),
            "eq_enabled": cfg.get_eq_enabled(),
            "eq_preamp": cfg.get_eq_preamp(),
            "eq_gains": cfg.get_eq_gains(),
            "eq_hp_filter": cfg.get_eq_hp_filter(),
            "normalization": cfg.get_normalization(),
        }

    # ------------------------------------------------------------------
    # Construcción UI (layout compacto)
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """(Re)construye la interfaz. Usado al iniciar y al cambiar de tema."""
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
        self._main_frame.grid_columnconfigure(0, weight=1)
        self._main_frame.grid_rowconfigure(6, weight=1)  # playlist expande

        self._build_header()        # fila 0
        self._build_now_playing()   # fila 1
        self._build_progress()      # fila 2
        self._build_controls()      # fila 3
        self._build_eq_panel()      # fila 4 (oculto por defecto)
        self._build_actions()       # fila 5
        self._build_playlist()      # fila 6 (expandible)
        self._build_status_bar()    # fila 7

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 2))

        brand = ctk.CTkLabel(header, text="🎵 Musik Player", font=Styles.TITLE_FONT,
                             text_color=Styles.TEXT_COLOR)
        brand.pack(side="left")

        # Selector de tema
        display_names = list(Theme.get_display_names().keys())
        self._theme_menu = ctk.CTkOptionMenu(
            header, values=display_names, command=self._on_theme_change,
            width=150, font=Styles.SMALL_FONT, height=26,
            fg_color=Styles.BUTTON_COLOR, button_color=Styles.ACCENT_COLOR,
            button_hover_color=Styles.ACCENT_HOVER, text_color=Styles.TEXT_COLOR,
            dropdown_fg_color=Styles.SECONDARY_COLOR,
            dropdown_hover_color=Styles.BUTTON_COLOR,
            dropdown_text_color=Styles.TEXT_COLOR, corner_radius=8)
        self._theme_menu.pack(side="right")
        Tooltip(self._theme_menu, "Cambiar tema  (T)")
        self._theme_menu.set(self._display_name_for_theme(Styles.get_current_theme()))

        self._eq_toggle_btn = ctk.CTkButton(
            header, text="🎛 EQ", width=46, height=26, font=Styles.SMALL_FONT,
            fg_color=Styles.BUTTON_COLOR, hover_color=Styles.BUTTON_HOVER,
            text_color=Styles.TEXT_COLOR, corner_radius=8, command=self._toggle_eq_panel)
        self._eq_toggle_btn.pack(side="right", padx=(0, 6))
        Tooltip(self._eq_toggle_btn, "Mostrar / ocultar ecualizador")

        self._settings_btn = ctk.CTkButton(
            header, text="⚙ Audio", width=58, height=26, font=Styles.SMALL_FONT,
            fg_color=Styles.BUTTON_COLOR, hover_color=Styles.BUTTON_HOVER,
            text_color=Styles.TEXT_COLOR, corner_radius=8,
            command=self._open_audio_settings)
        self._settings_btn.pack(side="right", padx=(0, 2))
        Tooltip(self._settings_btn, "Configuración de salida y calidad")

    def _build_now_playing(self) -> None:
        card = ctk.CTkFrame(self._main_frame, **Styles.get_frame_style("card"))
        card.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 6))
        card.grid_columnconfigure(1, weight=1)

        # Portada (carátula real o inicial)
        self._album_art = AlbumArt(card, size=64)
        self._album_art.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=10)

        # Info + chips
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", pady=(8, 0), padx=(0, 8))

        self._song_title_label = EllipsisLabel(
            info, text="No track loaded", font=Styles.SUBTITLE_FONT,
            text_color=Styles.TEXT_COLOR)
        self._song_title_label.pack(fill="x")

        self._artist_label = EllipsisLabel(
            info, text="-", font=Styles.NORMAL_FONT,
            text_color=Styles.TEXT_SECONDARY)
        self._artist_label.pack(fill="x")

        self._meta_chips = MetaChips(info)
        self._meta_chips.pack(fill="x", pady=(3, 0))

        # Tiempos
        time_col = ctk.CTkFrame(card, fg_color="transparent")
        time_col.grid(row=0, column=2, rowspan=2, padx=10, sticky="e")

        self._time_label = ctk.CTkLabel(
            time_col, text="00:00", font=("Consolas", 20, "bold"),
            text_color=Styles.ACCENT_COLOR)
        self._time_label.pack(anchor="e")
        self._total_time_label = ctk.CTkLabel(
            time_col, text="/ 00:00", font=Styles.MONO_FONT,
            text_color=Styles.TEXT_SECONDARY)
        self._total_time_label.pack(anchor="e")

        # Zona visual: barras animadas (default) u onda HQ (encima)
        viz_frame = ctk.CTkFrame(card, fg_color="transparent")
        viz_frame.grid(row=1, column=1, columnspan=2, sticky="ew",
                       padx=(12, 14), pady=(2, 10))
        viz_frame.grid_columnconfigure(0, weight=1)

        self._visualizer = Visualizer(viz_frame, bars=18, height=30, bg=Styles.CARD_COLOR)
        self._visualizer.grid(row=0, column=0, sticky="ew")

        self._waveform = WaveformView(viz_frame, height=30, bg=Styles.CARD_COLOR)
        self._waveform.grid(row=0, column=0, sticky="ew")

    def _build_progress(self) -> None:
        frame = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        frame.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 0))

        self._progress_slider = ctk.CTkSlider(
            frame, from_=0, to=100, number_of_steps=1000, height=12,
            **Styles.get_progress_style())
        self._progress_slider.pack(fill="x", pady=1)
        self._progress_slider.configure(command=self._on_progress_change)
        self._progress_slider.bind("<ButtonPress-1>", self._on_progress_press)
        self._progress_slider.bind("<ButtonRelease-1>", self._on_progress_release)
        Tooltip(self._progress_slider, "Arrastrar y soltar para buscar  (Ctrl+←/→)")

    def _build_controls(self) -> None:
        self._player_controls = PlayerControls(self._main_frame)
        self._player_controls.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 0))

    def _build_eq_panel(self) -> None:
        """Panel EQ colapsable (oculto hasta pulsar el botón EQ)."""
        self._eq_panel = EqPanel(
            self._main_frame,
            presets=self._config_manager.get_eq_presets(),
            on_change=self._on_eq_change,
        )
        self._eq_panel.grid(row=4, column=0, sticky="ew", padx=14, pady=(2, 4))
        self._eq_panel.grid_remove()

    def _build_actions(self) -> None:
        actions = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        actions.grid(row=5, column=0, sticky="ew", padx=14, pady=4)
        for col in range(3):
            actions.grid_columnconfigure(col, weight=1)

        self._action_buttons = []
        specs = [
            ("📁 Cargar Audio", "📁 Cargar", self._on_load_files, "accent", "Agregar archivos  (L)"),
            ("🗑 Limpiar", "🗑", self._on_clear_playlist, "secondary", "Vaciar playlist"),
            ("📤 Exportar M3U", "📤 M3U", self._on_export_m3u, "secondary", "Exportar playlist"),
        ]
        for i, (text, compact, cmd, style, tip) in enumerate(specs):
            btn = ctk.CTkButton(
                actions, text=text, height=30,
                **Styles.get_button_style(style))
            btn.grid(row=0, column=i, padx=(3 if i else 0, 3), sticky="ew")
            btn.configure(command=cmd)
            Tooltip(btn, tip)
            self._action_buttons.append((btn, text, compact))

    def _build_playlist(self) -> None:
        self._playlist_view = PlaylistView(self._main_frame)
        self._playlist_view.grid(row=6, column=0, sticky="nsew", padx=14, pady=(2, 4))

    def _build_status_bar(self) -> None:
        status = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        status.grid(row=7, column=0, sticky="ew", padx=14, pady=(0, 8))

        left = ctk.CTkFrame(status, fg_color="transparent")
        left.pack(side="left")

        self._state_dot = ctk.CTkLabel(left, text="●", font=Styles.SMALL_FONT,
                                       text_color=Styles.TEXT_SECONDARY)
        self._state_dot.pack(side="left", padx=(2, 4))
        self._state_label = ctk.CTkLabel(left, text="Detenido", font=Styles.SMALL_FONT,
                                         text_color=Styles.TEXT_SECONDARY)
        self._state_label.pack(side="left")

        right = ctk.CTkFrame(status, fg_color="transparent")
        right.pack(side="right")

        self._backend_label = ctk.CTkLabel(right, text="", font=Styles.SMALL_FONT,
                                           text_color=Styles.ACCENT_COLOR)
        self._backend_label.pack(side="right", padx=(8, 0))

        self._total_duration_label = ctk.CTkLabel(
            right, text="Total 00:00", font=Styles.SMALL_FONT,
            text_color=Styles.TEXT_SECONDARY)
        self._total_duration_label.pack(side="right", padx=(10, 0))

        self._track_count_label = ctk.CTkLabel(
            right, text="0 pistas", font=Styles.SMALL_FONT,
            text_color=Styles.ACCENT_COLOR)
        self._track_count_label.pack(side="right")

    def _setup_callbacks(self) -> None:
        self._player_controls.set_play_callback(self._on_play)
        self._player_controls.set_pause_callback(self._on_pause)
        self._player_controls.set_next_callback(self._on_next)
        self._player_controls.set_previous_callback(self._on_previous)
        self._player_controls.set_volume_callback(self._on_volume_change)
        self._player_controls.set_shuffle_callback(self._on_shuffle)
        self._player_controls.set_repeat_callback(self._on_repeat)
        self._playlist_view.set_track_select_callback(self._on_track_select)
        self._playlist_view.set_remove_track_callback(self._on_remove_track)

    # ------------------------------------------------------------------
    # EQ / settings
    # ------------------------------------------------------------------

    def _sync_eq_panel_from_config(self) -> None:
        cfg = self._config_manager
        self._eq_panel.set_gains(
            cfg.get_eq_gains(), preset=cfg.get_eq_preset(),
            preamp=cfg.get_eq_preamp(), enabled=cfg.get_eq_enabled(),
            hp_filter=cfg.get_eq_hp_filter())

    def _toggle_eq_panel(self) -> None:
        if self._eq_panel.winfo_ismapped():
            self._eq_panel.grid_remove()
            self._eq_toggle_btn.configure(fg_color=Styles.BUTTON_COLOR,
                                          hover_color=Styles.BUTTON_HOVER)
        else:
            self._eq_panel.grid()
            self._eq_toggle_btn.configure(fg_color=Styles.ACCENT_COLOR,
                                          hover_color=Styles.ACCENT_HOVER,
                                          text_color="#ffffff")

    def _on_eq_change(self, state: Dict) -> None:
        """Cambios del panel EQ -> configuración + reprocesar pista."""
        cfg = self._config_manager
        cfg.set_eq_enabled(state["eq_enabled"], save=False)
        cfg.set_eq_gains(state["eq_gains"], save=False)
        cfg.set_eq_preamp(state["eq_preamp"], save=False)
        cfg.set_eq_hp_filter(state["eq_hp_filter"], save=False)
        cfg.set_eq_preset(state["eq_preset"], save=False)
        cfg.save()

        settings = {
            "eq_enabled": state["eq_enabled"],
            "eq_gains": state["eq_gains"],
            "eq_preamp": state["eq_preamp"],
            "eq_hp_filter": state["eq_hp_filter"],
        }
        # El EQ real requiere el motor HQ: activarlo siempre que el EQ lo
        # pida (aunque HQ ya estuviera encendido por otra vía).
        hq_engine = self._config_manager.get_hq_engine() or bool(state["eq_enabled"])
        self._config_manager.set_hq_engine(hq_engine, save=False)
        settings["hq_engine"] = hq_engine
        if hq_engine:
            logger.info("Motor HQ activo para el ecualizador")
        self._audio_player.update_dsp_settings(settings)
        self._update_backend_indicator()

    def _open_audio_settings(self) -> None:
        AudioSettingsPopup(
            self,
            current=self._player_settings_from_config(),
            on_apply=self._on_audio_settings_applied,
        )

    def _on_audio_settings_applied(self, settings: Dict) -> None:
        cfg = self._config_manager
        for key in ("audio_driver", "sample_rate", "buffer_size", "output_depth",
                    "normalization"):
            if key in settings:
                getattr(cfg, f"set_{key}")(settings[key], save=False)
        cfg.set_hq_engine(bool(settings.get("hq_engine", cfg.get_hq_engine())), save=False)
        cfg.save()

        self._audio_player.apply_audio_settings(self._player_settings_from_config())
        self._update_backend_indicator()
        if self._playlist_manager.get_current_track() is not None:
            self._refresh_playlist_view()
            self._update_ui_state()
        logger.info("Configuración de audio aplicada: %s", settings)

    def _update_backend_indicator(self) -> None:
        """Muestra el backend activo en la barra de estado."""
        try:
            if self._audio_player.is_hq():
                self._backend_label.configure(text="● HQ Engine")
            else:
                backend = self._audio_player.get_backend()
                if backend == "dsp":
                    text = "● HQ…"
                elif backend == "stream":
                    text = ""
                else:
                    text = ""
                self._backend_label.configure(text=text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Temas
    # ------------------------------------------------------------------

    @staticmethod
    def _display_name_for_theme(theme_key: str) -> str:
        for display, key in Theme.get_display_names().items():
            if key == theme_key:
                return display
        return list(Theme.get_display_names().keys())[0]

    def _on_theme_change(self, display_name: str) -> None:
        theme_key = Theme.get_display_names().get(display_name, "dark_premium")
        if theme_key == Styles.get_current_theme():
            return
        self._config_manager.set_theme(theme_key)
        Styles.setup_theme(theme_key)
        self.configure(fg_color=Styles.PRIMARY_COLOR)
        self._rebuild_ui()
        logger.info("Tema cambiado a: %s", theme_key)

    def _rebuild_ui(self) -> None:
        was_playing = self._audio_player.get_state() == PlayerState.PLAYING

        self._build_ui()
        self._setup_callbacks()

        self._player_controls.set_volume(self._audio_player.get_volume())
        self._player_controls.set_shuffle_state(self._is_shuffle)
        self._player_controls.set_repeat_state(self._repeat_mode)
        self._sync_eq_panel_from_config()

        self._refresh_playlist_view()
        self._update_track_info_display()
        self._update_progress_ui()
        self._update_analysis_ui()
        self._update_ui_state()
        self._update_backend_indicator()

        if was_playing:
            self._visualizer.set_playing(True)

    # ------------------------------------------------------------------
    # Carga de archivos y playlist
    # ------------------------------------------------------------------

    def _on_load_files(self) -> None:
        patterns = FileHandler.FILE_DIALOG_PATTERNS
        filetypes = [(label, pat) for label, pat in patterns]
        file_paths = filedialog.askopenfilenames(title="Seleccionar archivos de audio",
                                                 filetypes=filetypes)
        if file_paths:
            self._add_files_to_playlist(file_paths)

    def _add_files_to_playlist(self, file_paths: tuple) -> None:
        start_time = time.time()
        new_tracks = []
        for file_path in file_paths:
            if not self._playlist_manager.has_track(file_path):
                try:
                    metadata = self._meta_for(file_path)
                    track = Track(
                        file_path=file_path,
                        title=metadata.get("title") or FileHandler.get_file_name(file_path),
                        artist=metadata.get("artist") or "Unknown",
                        duration=metadata.get("duration") or 0.0,
                    )
                    new_tracks.append(track)
                except Exception as e:
                    logger.warning(f"Error procesando {file_path}: {e}")

        for track in new_tracks:
            self._playlist_manager.add_track(track)

        if new_tracks:
            self._refresh_playlist_view()
            if self._playlist_manager.get_current_index() == -1 and not self._playlist_manager.is_empty():
                self._playlist_manager.set_current_index(0)
                self._load_current_track()
            self.after(1000, self._playlist_manager.save_playlist)

        logger.info("Agregados %d tracks en %.2fs", len(new_tracks), time.time() - start_time)

    def _meta_for(self, file_path: str) -> dict:
        """Metadatos en caché (extrae una sola vez por ruta)."""
        if file_path not in self._meta_cache:
            self._meta_cache[file_path] = MetadataExtractor.extract_metadata(file_path)
        return self._meta_cache[file_path]

    def _load_saved_playlist(self) -> None:
        if self._playlist_manager.load_playlist():
            self._refresh_playlist_view()
            if not self._playlist_manager.is_empty() and self._playlist_manager.get_current_index() >= 0:
                self._load_current_track()
            logger.info("Playlist guardada cargada")

    def _refresh_playlist_view(self) -> None:
        self._playlist_view.clear()
        tracks = self._playlist_manager.get_all_tracks()
        current_index = self._playlist_manager.get_current_index()
        for i, track in enumerate(tracks):
            self._playlist_view.add_track(
                title=track.title, artist=track.artist, duration=track.duration,
                index=i, is_current=(i == current_index))
        self._playlist_view.update_count(len(tracks))
        self._playlist_view.refresh_search()
        self._playlist_view.set_playing_state(
            self._audio_player.get_state() == PlayerState.PLAYING)
        self._update_status_bar()

    # ------------------------------------------------------------------
    # Reproducción
    # ------------------------------------------------------------------

    def _load_current_track(self) -> bool:
        track = self._playlist_manager.get_current_track()
        if not track:
            return False

        if self._audio_player.load(track.file_path, duration_hint=track.duration or None):
            self._update_track_info(track)
            self._total_duration = track.duration
            self._update_progress_ui()
            return True
        return False

    def _update_track_info(self, track: Track) -> None:
        self._song_title_label.set_full_text(track.title)
        self._artist_label.set_full_text(track.artist)

        meta = self._meta_for(track.file_path)
        self._current_meta = meta
        self._meta_chips.set_metadata(meta, hq=self._audio_player.is_hq())

        # Carátula: en caché o extraer en hilo (no bloquear la UI)
        self._album_art.set_art(None, (track.title or "♪").strip()[:1] or "♪")
        if track.file_path in self._art_cache:
            self._album_art.set_art(self._art_cache[track.file_path],
                                    (track.title or "♪").strip()[:1] or "♪")
        else:
            threading.Thread(
                target=self._art_worker, args=(track.file_path,), daemon=True).start()

        # Onda: reset hasta que llegue el análisis HQ
        self._analysis = None
        self._set_visualizer_mode(have_waveform=False)
        self._update_backend_indicator()

    def _art_worker(self, file_path: str) -> None:
        """Extrae la carátula en un hilo y la encola para la UI."""
        try:
            art = MetadataExtractor.extract_album_art(file_path)
        except Exception as e:
            logger.warning(f"Error extrayendo carátula: {e}")
            art = None
        self._art_cache[file_path] = art
        self._enqueue_ui("art", file_path)

    def _update_track_info_display(self) -> None:
        track = self._playlist_manager.get_current_track()
        if track:
            self._update_track_info(track)
        else:
            self._song_title_label.set_full_text("No track loaded")
            self._artist_label.set_full_text("-")
            self._album_art.set_art(None, "♪")
            self._meta_chips.set_metadata({})
            self._current_meta = {}
            self._waveform.clear()

    def _on_play(self) -> None:
        state = self._audio_player.get_state()
        if state == PlayerState.PAUSED:
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
        self._audio_player.pause()
        self._update_ui_state()

    def _on_next(self) -> None:
        if self._playlist_manager.next():
            was_playing = self._audio_player.get_state() == PlayerState.PLAYING
            self._load_current_track()
            if was_playing:
                self._audio_player.play()
            self._refresh_playlist_view()
        else:
            self._audio_player.stop()
            self._update_progress_ui()
        self._update_ui_state()

    def _on_previous(self) -> None:
        if self._playlist_manager.previous():
            was_playing = self._audio_player.get_state() == PlayerState.PLAYING
            self._load_current_track()
            if was_playing:
                self._audio_player.play()
            self._refresh_playlist_view()
            self._update_ui_state()

    def _on_track_select(self, index: int) -> None:
        if self._playlist_manager.set_current_index(index):
            was_playing = self._audio_player.get_state() == PlayerState.PLAYING
            self._load_current_track()
            if was_playing:
                self._audio_player.play()
            self._refresh_playlist_view()
            self._update_ui_state()

    def _on_remove_track(self, index: int) -> None:
        was_current = index == self._playlist_manager.get_current_index()
        if self._playlist_manager.remove_track(index):
            if was_current:
                self._audio_player.stop()
                self._update_track_info_display()
                self._current_position = 0.0
                self._total_duration = 0.0
                self._update_progress_ui()
            self._refresh_playlist_view()
            self._update_ui_state()
            self._playlist_manager.save_playlist()

    def _on_clear_playlist(self) -> None:
        if self._playlist_manager.is_empty():
            return
        if not messagebox.askyesno("Limpiar playlist", "¿Eliminar todas las pistas?"):
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

    def _on_export_m3u(self) -> None:
        if self._playlist_manager.is_empty():
            messagebox.showinfo("Exportar", "La playlist está vacía.")
            return
        file_path = filedialog.asksaveasfilename(
            title="Exportar playlist M3U", defaultextension=".m3u",
            filetypes=[("M3U Playlist", "*.m3u"), ("All Files", "*.*")])
        if file_path:
            if self._playlist_manager.create_m3u_playlist(file_path):
                messagebox.showinfo("Exportar", f"Playlist exportada a:\n{file_path}")
            else:
                messagebox.showerror("Exportar", "No se pudo exportar la playlist.")

    def _on_volume_change(self, volume: float) -> None:
        self._audio_player.set_volume(volume)
        self._config_manager.set_volume(volume, save=False)
        if self._volume_save_job is not None:
            try:
                self.after_cancel(self._volume_save_job)
            except Exception:
                pass
        self._volume_save_job = self.after(500, self._save_volume_config)

    def _save_volume_config(self) -> None:
        self._volume_save_job = None
        self._config_manager.save()

    # ------------------------------------------------------------------
    # Progreso
    # ------------------------------------------------------------------

    def _on_progress_press(self, event=None) -> None:
        self._is_seeking = True

    def _on_progress_release(self, event=None) -> None:
        self._is_seeking = False
        if self._total_duration > 0:
            position = (self._progress_slider.get() / 100.0) * self._total_duration
            self._audio_player.seek(position)
            self._current_position = position
            self._update_progress_ui(force=True)

    def _on_progress_change(self, value: float) -> None:
        if self._total_duration > 0:
            self._is_seeking = True
            preview = (value / 100.0) * self._total_duration
            self._time_label.configure(text=self._format_time(preview))

    def _update_progress_ui(self, force: bool = False) -> None:
        if self._is_seeking:
            return
        now = time.time()
        if not force and now - self._last_progress_ui_time < self._progress_ui_interval:
            return
        self._last_progress_ui_time = now

        if self._total_duration > 0:
            progress = (self._current_position / self._total_duration) * 100
            self._progress_slider.set(progress)
            self._time_label.configure(text=self._format_time(self._current_position))
            self._total_time_label.configure(text=f"/ {self._format_time(self._total_duration)}")
            # Cabezal de la forma de onda (si hay análisis HQ)
            if self._analysis:
                self._waveform.set_playhead(self._current_position / self._total_duration)
        else:
            self._progress_slider.set(0)
            self._time_label.configure(text="00:00")
            self._total_time_label.configure(text="/ 00:00")

    # ------------------------------------------------------------------
    # Cola hilo de audio -> UI
    # ------------------------------------------------------------------

    def _enqueue_ui(self, event: str, *args) -> None:
        self._ui_queue.put((event, args))

    def _poll_ui_queue(self) -> None:
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
            elif event == "replay":
                if self._audio_player.replay():
                    self._update_ui_state()
            elif event == "hq_ready":
                self._on_hq_ready_main_thread()
            elif event == "art":
                file_path = args[0]
                track = self._playlist_manager.get_current_track()
                if track and track.file_path == file_path:
                    self._album_art.set_art(
                        self._art_cache.get(file_path),
                        (track.title or "♪").strip()[:1] or "♪")
            elif event == "error":
                messagebox.showerror("Audio", f"Ocurrió un error de audio:\n{args[0]}")

        if events:
            self._update_progress_ui()

        self.after(50, self._poll_ui_queue)

    def _on_position_update(self, position: float, duration: float) -> None:
        self._enqueue_ui("pos", position, duration)

    def _on_track_end(self) -> None:
        if self._playlist_manager.get_repeat_mode() == 2:  # Repeat one
            self._enqueue_ui("replay")
        else:
            self._enqueue_ui("end")

    def _on_hq_track_ready(self) -> None:
        """Callback del hilo de decode HQ -> encola para el hilo principal."""
        self._enqueue_ui("hq_ready")

    def _on_hq_ready_main_thread(self) -> None:
        """Acepta el buffer HQ y actualiza la onda + backend en la UI."""
        if self._audio_player.accept_hq_buffer():
            self._update_analysis_ui()
            self._update_backend_indicator()
            # Chips con insignia HQ
            track = self._playlist_manager.get_current_track()
            if track and track.file_path in self._meta_cache:
                self._meta_chips.set_metadata(self._meta_cache[track.file_path], hq=True)
            self._update_ui_state()

    def _update_analysis_ui(self) -> None:
        """Muestra la forma de onda si hay análisis HQ disponible."""
        analysis = self._audio_player.get_analysis()
        self._analysis = analysis
        have_wave = bool(analysis and analysis.get("wave_mins") and analysis.get("wave_maxs"))
        if have_wave:
            self._waveform.set_waveform(analysis["wave_mins"], analysis["wave_maxs"])
            self._waveform.set_playhead(0.0)
        else:
            self._waveform.clear()
        self._set_visualizer_mode(have_waveform=have_wave)

    def _set_visualizer_mode(self, have_waveform: bool) -> None:
        """Alterna entre el ecualizador de barras y la forma de onda HQ."""
        try:
            if have_waveform:
                self._visualizer.set_playing(False)
                self._visualizer.grid_remove()
                self._waveform.grid()
            else:
                self._waveform.grid_remove()
                self._visualizer.grid()
                self._visualizer.set_playing(
                    self._audio_player.get_state() == PlayerState.PLAYING)
        except tk.TclError:
            pass

    def _on_audio_error(self, error_message: str) -> None:
        logger.error("Error de audio: %s", error_message)
        self._enqueue_ui("error", error_message)

    # ------------------------------------------------------------------
    # Estado de la UI
    # ------------------------------------------------------------------

    def _update_ui_state(self) -> None:
        state = self._audio_player.get_state()
        is_playing = state == PlayerState.PLAYING
        is_loading = state == PlayerState.LOADING

        self._player_controls.set_playing_state(is_playing)
        self._playlist_view.set_playing_state(is_playing)
        self._visualizer.set_playing(is_playing)

        has_track = self._playlist_manager.get_current_track() is not None
        self._player_controls.set_enabled(has_track)
        self._update_status_bar(is_loading)
        self._update_backend_indicator()

    def _update_status_bar(self, loading: bool = False) -> None:
        state = self._audio_player.get_state()
        if state == PlayerState.PLAYING:
            color, text = Styles.SUCCESS_COLOR, "Reproduciendo"
        elif state == PlayerState.PAUSED:
            color, text = Styles.WARNING_COLOR, "Pausado"
        elif loading:
            color, text = Styles.ACCENT_COLOR, "Procesando HQ…"
        else:
            color, text = Styles.TEXT_SECONDARY, "Detenido"

        self._state_dot.configure(text_color=color)
        self._state_label.configure(text=text)

        tracks = self._playlist_manager.get_all_tracks()
        total = sum((t.duration or 0) for t in tracks)
        self._track_count_label.configure(
            text=f"{len(tracks)} pista{'s' if len(tracks) != 1 else ''}")
        self._total_duration_label.configure(text=f"Total {self._format_time(total)}")

    @staticmethod
    def _format_time(seconds: float) -> str:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    # ------------------------------------------------------------------
    # Responsividad
    # ------------------------------------------------------------------

    def _on_window_resize(self, event) -> None:
        if event.widget is not self:
            return
        compact = event.width < COMPACT_WIDTH
        if compact != self._compact:
            self._compact = compact
            self.after_idle(self._apply_compact)

    def _apply_compact(self) -> None:
        for btn, normal_text, compact_text in self._action_buttons:
            try:
                btn.configure(text=compact_text if self._compact else normal_text)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Atajos de teclado
    # ------------------------------------------------------------------

    def _guard_shortcut(self, func):
        def _wrapper(event=None):
            widget = self.focus_get()
            if isinstance(widget, (ctk.CTkEntry, tk.Entry, tk.Text)):
                return
            return func()
        return _wrapper

    def _setup_keyboard_shortcuts(self) -> None:
        self.bind("<space>", self._guard_shortcut(self._toggle_play_pause))
        self.bind("<Left>", self._guard_shortcut(self._on_previous))
        self.bind("<Control-Left>", self._guard_shortcut(self._seek_backward))
        self.bind("<Right>", self._guard_shortcut(self._on_next))
        self.bind("<Control-Right>", self._guard_shortcut(self._seek_forward))
        self.bind("<Up>", self._guard_shortcut(self._volume_up))
        self.bind("<Down>", self._guard_shortcut(self._volume_down))
        self.bind("<m>", self._guard_shortcut(self._toggle_mute))
        self.bind("<s>", self._guard_shortcut(self._on_shuffle))
        self.bind("<r>", self._guard_shortcut(self._on_repeat))
        self.bind("<l>", self._guard_shortcut(self._on_load_files))
        self.bind("<t>", self._guard_shortcut(self._cycle_theme))
        self.bind("<q>", self._guard_shortcut(self._on_close))
        self.bind("<f>", self._guard_shortcut(self._toggle_fullscreen))
        self.bind("<Escape>", lambda e: self._exit_fullscreen())
        logger.info("Atajos de teclado configurados")

    def _cycle_theme(self) -> None:
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

    def _toggle_play_pause(self) -> None:
        state = self._audio_player.get_state()
        if state == PlayerState.PLAYING:
            self._on_pause()
        else:
            self._on_play()

    def _seek_backward(self) -> None:
        new_pos = max(0, self._audio_player.get_position() - 10)
        self._audio_player.seek(new_pos)
        self._current_position = new_pos
        self._update_progress_ui(force=True)

    def _seek_forward(self) -> None:
        duration = self._audio_player.get_duration()
        new_pos = min(duration, self._audio_player.get_position() + 10)
        self._audio_player.seek(new_pos)
        self._current_position = new_pos
        self._update_progress_ui(force=True)

    def _volume_up(self) -> None:
        new_vol = min(1.0, self._audio_player.get_volume() + 0.1)
        self._on_volume_change(new_vol)
        self._player_controls.set_volume(new_vol)

    def _volume_down(self) -> None:
        new_vol = max(0.0, self._audio_player.get_volume() - 0.1)
        self._on_volume_change(new_vol)
        self._player_controls.set_volume(new_vol)

    def _toggle_mute(self) -> None:
        current_vol = self._audio_player.get_volume()
        if current_vol > 0:
            self._previous_volume = current_vol
            self._on_volume_change(0.0)
            self._player_controls.set_volume(0.0)
        else:
            self._on_volume_change(getattr(self, "_previous_volume", 0.7))
            self._player_controls.set_volume(getattr(self, "_previous_volume", 0.7))

    def _toggle_shuffle(self) -> None:
        new_shuffle = not self._playlist_manager.get_shuffle()
        self._playlist_manager.set_shuffle(new_shuffle)
        self._config_manager.set_shuffle(new_shuffle)
        self._is_shuffle = new_shuffle
        self._player_controls.set_shuffle_state(new_shuffle)

    def _toggle_repeat(self) -> None:
        new_mode = (self._playlist_manager.get_repeat_mode() + 1) % 3
        self._playlist_manager.set_repeat_mode(new_mode)
        self._config_manager.set_repeat_mode(new_mode)
        self._repeat_mode = new_mode
        self._player_controls.set_repeat_state(new_mode)

    def _on_shuffle(self) -> None:
        self._toggle_shuffle()

    def _on_repeat(self) -> None:
        self._toggle_repeat()

    def _toggle_fullscreen(self) -> None:
        current = self.attributes("-fullscreen")
        self.attributes("-fullscreen", not current)

    def _exit_fullscreen(self) -> None:
        self.attributes("-fullscreen", False)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        try:
            self._player_controls.stop_animations()
        except Exception:
            pass
        self._audio_player.cleanup()

    def run(self) -> None:
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.mainloop()
        except Exception as e:
            logger.error(f"Error en mainloop: {e}")
        finally:
            logger.info("Aplicación finalizada")

    def _on_close(self) -> None:
        try:
            self.update_idletasks()
            geometry = self.geometry()
            parts = geometry.split('+')
            if len(parts) >= 3:
                size = parts[0].split('x')
                if len(size) == 2:
                    self._config_manager.set_window_geometry(
                        int(size[0]), int(size[1]), int(parts[1]), int(parts[2]))
            self._config_manager.set_volume(self._audio_player.get_volume())
            self._config_manager.set_shuffle(self._playlist_manager.get_shuffle())
            self._config_manager.set_repeat_mode(self._playlist_manager.get_repeat_mode())
            self._playlist_manager.save_playlist()
            self._config_manager.save()
            logger.info("Configuración guardada")
        except Exception as e:
            logger.error(f"Error guardando configuración: {e}")
        finally:
            self.cleanup()
            self.destroy()
            logger.info("Aplicación cerrada")