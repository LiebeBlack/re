"""
MainWindow - Ventana principal de Musik Player
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional
import logging
import queue
import time

from src.ui.styles import Styles
from src.ui.player_controls import PlayerControls
from src.ui.playlist_view import PlaylistView
from src.audio.player import AudioPlayer, PlayerState
from src.audio.playlist_manager import PlaylistManager, Track
from src.utils.file_handler import FileHandler
from src.utils.config_manager import ConfigManager
from src.utils.metadata_extractor import MetadataExtractor

logger = logging.getLogger(__name__)


class MainWindow(ctk.CTk):
    """Ventana principal del reproductor de música"""

    def __init__(self):
        """Inicializa la ventana principal"""
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
        # Cola thread-safe para comunicar eventos del hilo de audio a la UI.
        # El sondeo se programa una sola vez aquí (hilo principal) y se
        # re-programa a sí mismo, de modo que el hilo de audio nunca toca Tk.
        self._ui_queue = queue.Queue()
        self.after(50, self._poll_ui_queue)

        # Configurar interfaz (antes de cargar la playlist para que la vista exista)
        self._setup_ui()
        self._setup_callbacks()
        self._setup_keyboard_shortcuts()

        # Cargar playlist guardada
        self._load_saved_playlist()

        # Estado inicial
        self._player_controls.set_volume(self._audio_player.get_volume())
        self._update_ui_state()
        self._player_controls.set_shuffle_state(self._is_shuffle)
        self._player_controls.set_repeat_state(self._repeat_mode)

        logger.info("Ventana principal inicializada")

    def _setup_ui(self) -> None:
        """Configura la interfaz gráfica"""
        # Frame principal
        main_frame = ctk.CTkFrame(self, fg_color=Styles.PRIMARY_COLOR)
        main_frame.pack(fill="both", expand=True)

        # Header
        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=15)

        title_label = ctk.CTkLabel(
            header_frame,
            text="🎵 Musik Player",
            font=Styles.TITLE_FONT,
            text_color=Styles.TEXT_COLOR
        )
        title_label.pack()

        # Frame de información
        info_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        info_frame.pack(fill="x", padx=20, pady=(0, 8))

        self._song_title_label = ctk.CTkLabel(
            info_frame,
            text="No track loaded",
            font=Styles.SUBTITLE_FONT,
            text_color=Styles.TEXT_COLOR
        )
        self._song_title_label.pack()

        self._artist_label = ctk.CTkLabel(
            info_frame,
            text="-",
            font=Styles.NORMAL_FONT,
            text_color=Styles.TEXT_SECONDARY
        )
        self._artist_label.pack()

        # Barra de progreso
        progress_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        progress_frame.pack(fill="x", padx=20, pady=8)

        self._time_label = ctk.CTkLabel(
            progress_frame,
            text="00:00 / 00:00",
            font=Styles.SMALL_FONT,
            text_color=Styles.TEXT_SECONDARY
        )
        self._time_label.pack(anchor="w")

        self._progress_slider = ctk.CTkSlider(
            progress_frame,
            from_=0,
            to=100,
            number_of_steps=1000,
            **Styles.get_progress_style()
        )
        self._progress_slider.pack(fill="x", pady=4)
        self._progress_slider.configure(command=self._on_progress_change)
        # Buscar solo al soltar el slider para evitar cortes de audio
        self._progress_slider.bind("<ButtonPress-1>", self._on_progress_press)
        self._progress_slider.bind("<ButtonRelease-1>", self._on_progress_release)

        # Controles de reproducción
        self._player_controls = PlayerControls(main_frame)
        self._player_controls.pack(fill="x", padx=20, pady=8)

        # Frame de acciones (cargar, limpiar, exportar)
        load_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        load_frame.pack(fill="x", padx=20, pady=8)
        load_frame.grid_columnconfigure(0, weight=1)
        load_frame.grid_columnconfigure(1, weight=1)
        load_frame.grid_columnconfigure(2, weight=1)

        load_btn = ctk.CTkButton(
            load_frame,
            text="📁 Load Audio Files",
            height=35,
            **Styles.get_button_style()
        )
        load_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        load_btn.configure(command=self._on_load_files)

        clear_btn = ctk.CTkButton(
            load_frame,
            text="🗑 Clear Playlist",
            height=35,
            **Styles.get_button_style("secondary")
        )
        clear_btn.grid(row=0, column=1, padx=5, sticky="ew")
        clear_btn.configure(command=self._on_clear_playlist)

        export_btn = ctk.CTkButton(
            load_frame,
            text="📤 Export M3U",
            height=35,
            **Styles.get_button_style("secondary")
        )
        export_btn.grid(row=0, column=2, padx=(5, 0), sticky="ew")
        export_btn.configure(command=self._on_export_m3u)

        # Vista de playlist
        self._playlist_view = PlaylistView(main_frame)
        self._playlist_view.pack(fill="both", expand=True, padx=20, pady=(8, 15))

    def _setup_callbacks(self) -> None:
        """Configura los callbacks de los componentes"""
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

    def _on_load_files(self) -> None:
        """Maneja la carga de archivos de audio"""
        file_paths = filedialog.askopenfilenames(
            title="Select Audio Files",
            filetypes=[
                ("Audio Files", "*.mp3 *.wav *.ogg *.flac"),
                ("MP3 Files", "*.mp3"),
                ("WAV Files", "*.wav"),
                ("OGG Files", "*.ogg"),
                ("FLAC Files", "*.flac"),
                ("All Files", "*.*")
            ]
        )

        if file_paths:
            self._add_files_to_playlist(file_paths)

    def _add_files_to_playlist(self, file_paths: tuple) -> None:
        """
        Agrega archivos a la playlist procesando en lote

        Args:
            file_paths: Tupla de rutas de archivos
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
                        duration=metadata.get("duration") or 0.0
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
        """Carga la playlist guardada al iniciar"""
        if self._playlist_manager.load_playlist():
            self._refresh_playlist_view()

            # Cargar la pista actual si existe
            if not self._playlist_manager.is_empty() and self._playlist_manager.get_current_index() >= 0:
                self._load_current_track()

            logger.info("Playlist guardada cargada exitosamente")

    def _refresh_playlist_view(self) -> None:
        """Actualiza la vista de la playlist"""
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
                is_current=is_current
            )

        self._playlist_view.update_count(len(tracks))
        self._playlist_view.refresh_search()

    def _load_current_track(self) -> bool:
        """
        Carga la pista actual en el reproductor

        Returns:
            True si se cargó exitosamente, False en caso contrario
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
        Actualiza la información de la pista en la UI

        Args:
            track: Pista actual
        """
        self._song_title_label.configure(text=track.title)
        self._artist_label.configure(text=track.artist)

    def _on_play(self) -> None:
        """Maneja el evento de play"""
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
        """Maneja el evento de pause"""
        self._audio_player.pause()
        self._update_ui_state()

    def _on_next(self) -> None:
        """Maneja el evento de siguiente pista"""
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
        """Maneja el evento de pista anterior"""
        if self._playlist_manager.previous():
            was_playing = self._audio_player.get_state() == PlayerState.PLAYING
            self._load_current_track()
            if was_playing:
                self._audio_player.play()
            self._refresh_playlist_view()
            self._update_ui_state()

    def _on_volume_change(self, volume: float) -> None:
        """
        Maneja el cambio de volumen (con guardado diferido)

        Args:
            volume: Nuevo volumen (0.0 - 1.0)
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
        """Guarda la configuración de volumen"""
        self._volume_save_job = None
        self._config_manager.save()

    def _on_progress_press(self, event=None) -> None:
        """Marca el inicio de un arrastre en la barra de progreso"""
        self._is_seeking = True

    def _on_progress_release(self, event=None) -> None:
        """Maneja la liberación de la barra de progreso (busca la posición)"""
        self._is_seeking = False
        if self._total_duration > 0:
            position = (self._progress_slider.get() / 100.0) * self._total_duration
            self._audio_player.seek(position)
            self._current_position = position
            self._update_progress_ui()

    def _on_progress_change(self, value: float) -> None:
        """
        Maneja el arrastre en la barra de progreso (solo vista previa)

        Args:
            value: Nuevo valor del slider (0-100)
        """
        if self._total_duration > 0:
            self._is_seeking = True
            preview_position = (value / 100.0) * self._total_duration
            self._time_label.configure(
                text=f"{self._format_time(preview_position)} / {self._format_time(self._total_duration)}"
            )

    def _enqueue_ui(self, event: str, *args) -> None:
        """
        Encola un evento del hilo de audio para procesarlo en el hilo principal
        
        Args:
            event: Tipo de evento (pos, end, error)
            *args: Argumentos del evento
        """
        self._ui_queue.put((event, args))

    def _poll_ui_queue(self) -> None:
        """Procesa los eventos encolados por el hilo de audio (hilo principal)"""
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
        Callback de posición (hilo de audio): solo encola la actualización
        
        Args:
            position: Posición actual en segundos
            duration: Duración total en segundos
        """
        self._enqueue_ui("pos", position, duration)

    def _on_track_end(self) -> None:
        """Callback cuando termina una pista (hilo de audio)"""
        if self._playlist_manager.get_repeat_mode() == 2:  # Repeat one
            # Repetir la misma canción (llamada segura de pygame)
            self._audio_player.play()
        else:
            # Avanzar a la siguiente canción en el hilo principal
            self._enqueue_ui("end")

    def _on_track_select(self, index: int) -> None:
        """
        Maneja la selección de una pista en la playlist

        Args:
            index: Índice de la pista seleccionada
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
        Maneja la remoción de una pista

        Args:
            index: Índice de la pista a remover
        """
        was_current = (index == self._playlist_manager.get_current_index())

        if self._playlist_manager.remove_track(index):
            if was_current:
                self._audio_player.stop()
                self._song_title_label.configure(text="No track loaded")
                self._artist_label.configure(text="-")
                self._current_position = 0.0
                self._total_duration = 0.0
                self._update_progress_ui()

            self._refresh_playlist_view()
            self._update_ui_state()

            # Guardar playlist automáticamente
            self._playlist_manager.save_playlist()

    def _on_clear_playlist(self) -> None:
        """Vacía la playlist completa"""
        if self._playlist_manager.is_empty():
            return

        if not messagebox.askyesno("Clear Playlist", "¿Eliminar todas las pistas de la playlist?"):
            return

        self._playlist_manager.clear()
        self._audio_player.stop()
        self._current_position = 0.0
        self._total_duration = 0.0
        self._song_title_label.configure(text="No track loaded")
        self._artist_label.configure(text="-")

        self._refresh_playlist_view()
        self._update_progress_ui()
        self._update_ui_state()
        self._playlist_manager.save_playlist()
        logger.info("Playlist vaciada")

    def _on_export_m3u(self) -> None:
        """Exporta la playlist actual a un archivo M3U"""
        if self._playlist_manager.is_empty():
            messagebox.showinfo("Export M3U", "La playlist está vacía.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Export Playlist as M3U",
            defaultextension=".m3u",
            filetypes=[("M3U Playlist", "*.m3u"), ("All Files", "*.*")]
        )

        if file_path:
            if self._playlist_manager.create_m3u_playlist(file_path):
                messagebox.showinfo("Export M3U", f"Playlist exportada a:\n{file_path}")
            else:
                messagebox.showerror("Export M3U", "No se pudo exportar la playlist.")

    def _update_progress_ui(self) -> None:
        """Actualiza la UI de la barra de progreso"""
        if self._is_seeking:
            return

        if self._total_duration > 0:
            progress = (self._current_position / self._total_duration) * 100
            self._progress_slider.set(progress)

            current_time = self._format_time(self._current_position)
            total_time = self._format_time(self._total_duration)
            self._time_label.configure(text=f"{current_time} / {total_time}")
        else:
            self._progress_slider.set(0)
            self._time_label.configure(text="00:00 / 00:00")

    def _update_ui_state(self) -> None:
        """Actualiza el estado de la UI según el estado del reproductor"""
        state = self._audio_player.get_state()
        is_playing = (state == PlayerState.PLAYING)

        self._player_controls.set_playing_state(is_playing)

        has_track = self._playlist_manager.get_current_track() is not None
        self._player_controls.set_enabled(has_track)

    def _format_time(self, seconds: float) -> str:
        """
        Formatea tiempo en minutos:segundos

        Args:
            seconds: Tiempo en segundos

        Returns:
            Tiempo formateado (MM:SS)
        """
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def _on_audio_error(self, error_message: str) -> None:
        """
        Maneja errores del reproductor de audio (hilo de audio)
        
        Args:
            error_message: Mensaje de error
        """
        logger.error(f"Error de audio: {error_message}")
        self._enqueue_ui("error", error_message)

    def _guard_shortcut(self, func):
        """
        Evita que los atajos de teclado se disparen mientras se escribe en un campo de texto

        Args:
            func: Función a ejecutar si el foco no está en un entry

        Returns:
            Wrapper que verifica el foco antes de ejecutar
        """
        def _wrapper(event=None):
            widget = self.focus_get()
            if isinstance(widget, (ctk.CTkEntry, tk.Entry, tk.Text)):
                return
            return func()
        return _wrapper

    def _setup_keyboard_shortcuts(self) -> None:
        """Configura los atajos de teclado"""
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

        # Q: Quit
        self.bind("<q>", self._guard_shortcut(self._on_close))

        # F: Toggle fullscreen
        self.bind("<f>", self._guard_shortcut(self._toggle_fullscreen))

        # Escape: Exit fullscreen
        self.bind("<Escape>", lambda e: self._exit_fullscreen())

        logger.info("Atajos de teclado configurados")

    def _toggle_play_pause(self) -> None:
        """Alterna entre play y pause"""
        state = self._audio_player.get_state()
        if state == PlayerState.PLAYING:
            self._on_pause()
        else:
            self._on_play()

    def _seek_backward(self) -> None:
        """Retrocede 10 segundos"""
        current_pos = self._audio_player.get_position()
        new_pos = max(0, current_pos - 10)
        self._audio_player.seek(new_pos)
        logger.info(f"Retrocediendo a {new_pos}s")

    def _seek_forward(self) -> None:
        """Avanza 10 segundos"""
        current_pos = self._audio_player.get_position()
        duration = self._audio_player.get_duration()
        new_pos = min(duration, current_pos + 10)
        self._audio_player.seek(new_pos)
        logger.info(f"Avanzando a {new_pos}s")

    def _volume_up(self) -> None:
        """Sube el volumen un 10%"""
        current_vol = self._audio_player.get_volume()
        new_vol = min(1.0, current_vol + 0.1)
        self._on_volume_change(new_vol)
        self._player_controls.set_volume(new_vol)
        logger.info(f"Volumen: {int(new_vol * 100)}%")

    def _volume_down(self) -> None:
        """Baja el volumen un 10%"""
        current_vol = self._audio_player.get_volume()
        new_vol = max(0.0, current_vol - 0.1)
        self._on_volume_change(new_vol)
        self._player_controls.set_volume(new_vol)
        logger.info(f"Volumen: {int(new_vol * 100)}%")

    def _toggle_mute(self) -> None:
        """Alterna entre mute y unmute"""
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
        """Alterna el modo shuffle"""
        current_shuffle = self._playlist_manager.get_shuffle()
        new_shuffle = not current_shuffle
        self._playlist_manager.set_shuffle(new_shuffle)
        self._config_manager.set_shuffle(new_shuffle)
        self._is_shuffle = new_shuffle
        self._player_controls.set_shuffle_state(new_shuffle)
        logger.info(f"Shuffle: {'Activado' if new_shuffle else 'Desactivado'}")

    def _toggle_repeat(self) -> None:
        """Alterna el modo repeat"""
        current_mode = self._playlist_manager.get_repeat_mode()
        new_mode = (current_mode + 1) % 3
        self._playlist_manager.set_repeat_mode(new_mode)
        self._config_manager.set_repeat_mode(new_mode)
        self._repeat_mode = new_mode
        self._player_controls.set_repeat_state(new_mode)
        modes = ["Off", "Repeat All", "Repeat One"]
        logger.info(f"Repeat: {modes[new_mode]}")

    def _on_shuffle(self) -> None:
        """Maneja el clic en el botón shuffle"""
        self._toggle_shuffle()

    def _on_repeat(self) -> None:
        """Maneja el clic en el botón repeat"""
        self._toggle_repeat()

    def _toggle_fullscreen(self) -> None:
        """Alterna el modo pantalla completa"""
        current_state = self.attributes("-fullscreen")
        self.attributes("-fullscreen", not current_state)
        logger.info(f"Fullscreen: {'Activado' if not current_state else 'Desactivado'}")

    def _exit_fullscreen(self) -> None:
        """Sale del modo pantalla completa"""
        self.attributes("-fullscreen", False)
        logger.info("Fullscreen desactivado")

    def cleanup(self) -> None:
        """Limpia recursos antes de cerrar"""
        self._audio_player.cleanup()

    def run(self) -> None:
        """Inicia el bucle principal de la aplicación"""
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.mainloop()
        except Exception as e:
            logger.error(f"Error en mainloop: {e}")
        finally:
            logger.info("Aplicación finalizada")

    def _on_close(self) -> None:
        """Maneja el cierre de la ventana"""
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