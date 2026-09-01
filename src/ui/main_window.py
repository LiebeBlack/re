"""
MainWindow - Ventana principal de Musik Player
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional
import logging
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
    """Ventana principal del reproductor de música optimizada"""
    
    def __init__(self):
        """Inicializa la ventana principal"""
        super().__init__()
        
        # Configurar ventana
        self.title("Musik Player")
        self.configure(fg_color=Styles.PRIMARY_COLOR)
        
        # Inicializar componentes con lazy loading
        self._config_manager = None
        self._audio_player = None
        self._playlist_manager = None
        self._player_controls = None
        self._playlist_view = None
        
        # Variables de UI optimizadas
        self._current_position = 0.0
        self._total_duration = 0.0
        self._is_seeking = False
        self._update_pending = False  # Flag para debouncing de UI
        self._last_update_time = 0
        
        # Cache de UI para evitar reconstrucciones
        self._ui_cache = {}
        
        # Inicializar componentes de forma diferida
        self.after(100, self._lazy_init_components)
    
    def _lazy_init_components(self) -> None:
        """Inicializa componentes de forma diferida para inicio rápido"""
        try:
            self._config_manager = ConfigManager()
            self._audio_player = AudioPlayer()
            self._playlist_manager = PlaylistManager()
            
            # Cargar configuración
            self._playlist_manager.set_shuffle(self._config_manager.get_shuffle())
            self._playlist_manager.set_repeat_mode(self._config_manager.get_repeat_mode())
            
            # Cargar geometría
            width, height, x, y = self._config_manager.get_window_geometry()
            self.geometry(f"{width}x{height}+{x}+{y}")
            self.minsize(Styles.MIN_WIDTH, Styles.MIN_HEIGHT)
            
            # Cargar volumen
            saved_volume = self._config_manager.get_volume()
            self._audio_player.set_volume(saved_volume)
            
            # Configurar callbacks
            self._audio_player.set_position_callback(self._on_position_update)
            self._audio_player.set_track_end_callback(self._on_track_end)
            self._audio_player.set_error_callback(self._on_audio_error)
            
            # Cargar playlist guardada
            self._load_saved_playlist()
            
            # Configurar interfaz
            self._setup_ui()
            self._setup_callbacks()
            self._setup_keyboard_shortcuts()
            
            # Estado inicial
            self._update_ui_state()
            
            logger.info("Componentes inicializados exitosamente")
        except Exception as e:
            logger.error(f"Error inicializando componentes: {e}")
            messagebox.showerror("Error", f"Error al inicializar: {e}")
            self.destroy()


class MainWindow(ctk.CTk):
    """Ventana principal del reproductor de música"""
    
    def __init__(self):
        """Inicializa la ventana principal"""
        super().__init__()
        
        # Configurar ventana
        self.title("Musik Player")
        
        # Inicializar componentes
        self._config_manager = ConfigManager()
        self._audio_player = AudioPlayer()
        self._playlist_manager = PlaylistManager()
        
        # Cargar configuración de shuffle/repeat
        self._playlist_manager.set_shuffle(self._config_manager.get_shuffle())
        self._playlist_manager.set_repeat_mode(self._config_manager.get_repeat_mode())
        
        # Cargar playlist guardada
        self._load_saved_playlist()
        
        # Cargar geometría desde configuración
        width, height, x, y = self._config_manager.get_window_geometry()
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(Styles.MIN_WIDTH, Styles.MIN_HEIGHT)
        
        # Cargar volumen desde configuración
        saved_volume = self._config_manager.get_volume()
        self._audio_player.set_volume(saved_volume)
        
        # Configurar callbacks del reproductor
        self._audio_player.set_position_callback(self._on_position_update)
        self._audio_player.set_track_end_callback(self._on_track_end)
        self._audio_player.set_error_callback(self._on_audio_error)
        
        # Variables de UI
        self._current_position = 0.0
        self._total_duration = 0.0
        self._is_seeking = False
        self._is_shuffle = self._config_manager.get_shuffle()
        self._is_repeat = False
        self._repeat_mode = self._config_manager.get_repeat_mode()  # 0: off, 1: all, 2: one
        
        # Configurar interfaz
        self._setup_ui()
        self._setup_callbacks()
        self._setup_keyboard_shortcuts()
        
        # Estado inicial
        self._update_ui_state()
        self._player_controls.set_shuffle_state(self._is_shuffle)
        self._player_controls.set_repeat_state(self._repeat_mode)
    
    def _setup_ui(self) -> None:
        """Configura la interfaz gráfica optimizada"""
        # Frame principal con caching
        if 'main_frame' not in self._ui_cache:
            self._ui_cache['main_frame'] = ctk.CTkFrame(self, fg_color=Styles.PRIMARY_COLOR)
        main_frame = self._ui_cache['main_frame']
        main_frame.pack(fill="both", expand=True)
        
        # Header optimizado
        if 'header_frame' not in self._ui_cache:
            self._ui_cache['header_frame'] = ctk.CTkFrame(main_frame, fg_color="transparent")
            header_frame = self._ui_cache['header_frame']
            header_frame.pack(fill="x", padx=20, pady=15)
            
            title_label = ctk.CTkLabel(
                header_frame,
                text="🎵 Musik Player",
                font=Styles.TITLE_FONT,
                text_color=Styles.TEXT_COLOR
            )
            title_label.pack()
        
        # Frame de información
        if 'info_frame' not in self._ui_cache:
            self._ui_cache['info_frame'] = ctk.CTkFrame(main_frame, fg_color="transparent")
            self._info_frame = self._ui_cache['info_frame']
            self._info_frame.pack(fill="x", padx=20, pady=(0, 8))
            
            self._song_title_label = ctk.CTkLabel(
                self._info_frame,
                text="No track loaded",
                font=Styles.SUBTITLE_FONT,
                text_color=Styles.TEXT_COLOR
            )
            self._song_title_label.pack()
            
            self._artist_label = ctk.CTkLabel(
                self._info_frame,
                text="-",
                font=Styles.NORMAL_FONT,
                text_color=Styles.TEXT_SECONDARY
            )
            self._artist_label.pack()
        
        # Barra de progreso optimizada
        if 'progress_frame' not in self._ui_cache:
            self._ui_cache['progress_frame'] = ctk.CTkFrame(main_frame, fg_color="transparent")
            progress_frame = self._ui_cache['progress_frame']
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
        
        # Controles de reproducción
        if 'player_controls' not in self._ui_cache:
            self._player_controls = PlayerControls(main_frame)
            self._ui_cache['player_controls'] = self._player_controls
            self._player_controls.pack(fill="x", padx=20, pady=8)
        
        # Frame de carga de archivos
        if 'load_frame' not in self._ui_cache:
            self._ui_cache['load_frame'] = ctk.CTkFrame(main_frame, fg_color="transparent")
            load_frame = self._ui_cache['load_frame']
            load_frame.pack(fill="x", padx=20, pady=8)
            
            load_btn = ctk.CTkButton(
                load_frame,
                text="📁 Load Audio Files",
                height=35,
                font=Styles.NORMAL_FONT,
                **Styles.get_button_style()
            )
            load_btn.pack(fill="x")
            load_btn.configure(command=self._on_load_files)
        
        # Vista de playlist
        if 'playlist_view' not in self._ui_cache:
            self._playlist_view = PlaylistView(main_frame)
            self._ui_cache['playlist_view'] = self._playlist_view
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
        Agrega archivos a la playlist optimizado con procesamiento por lotes
        
        Args:
            file_paths: Tupla de rutas de archivos
        """
        import time
        start_time = time.time()
        
        # Procesar archivos en lote
        new_tracks = []
        for file_path in file_paths:
            if not self._playlist_manager.has_track(file_path):
                try:
                    # Extraer metadatos con timeout
                    metadata = MetadataExtractor.extract_metadata(file_path)
                    
                    # Crear track
                    track = Track(
                        file_path=file_path,
                        title=metadata.get("title", FileHandler.get_file_name(file_path)),
                        artist=metadata.get("artist", "Unknown"),
                        duration=metadata.get("duration", 0.0)
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
        """Actualiza la vista de la playlist optimizada con lazy rendering"""
        # Limpiar vista solo si está visible
        if self._playlist_view.winfo_ismapped():
            self._playlist_view.clear()
            
            tracks = self._playlist_manager.get_all_tracks()
            current_index = self._playlist_manager.get_current_index()
            
            # Renderizar tracks en lote
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
            self._load_current_track()
            if self._audio_player.get_state() == PlayerState.PLAYING:
                self._audio_player.play()
            self._refresh_playlist_view()
            self._update_ui_state()
    
    def _on_previous(self) -> None:
        """Maneja el evento de pista anterior"""
        if self._playlist_manager.previous():
            self._load_current_track()
            if self._audio_player.get_state() == PlayerState.PLAYING:
                self._audio_player.play()
            self._refresh_playlist_view()
            self._update_ui_state()
    
    def _on_volume_change(self, volume: float) -> None:
        """
        Maneja el cambio de volumen
        
        Args:
            volume: Nuevo volumen (0.0 - 1.0)
        """
        self._audio_player.set_volume(volume)
    
    def _on_progress_change(self, value: float) -> None:
        """
        Maneja el cambio en la barra de progreso
        
        Args:
            value: Nuevo valor del slider (0-100)
        """
        if self._total_duration > 0:
            position = (value / 100.0) * self._total_duration
            self._audio_player.seek(position)
    
    def _on_position_update(self, position: float, duration: float) -> None:
        """
        Callback para actualizaciones de posición con debouncing
        
        Args:
            position: Posición actual en segundos
            duration: Duración total en segundos
        """
        import time
        current_time = time.time()
        
        # Debouncing: actualizar UI solo cada 100ms
        if current_time - self._last_update_time < 0.1:
            if not self._update_pending:
                self._update_pending = True
                self.after(100, self._debounced_update)
            return
        
        self._current_position = position
        self._total_duration = duration
        self._last_update_time = current_time
        
        # Actualizar UI en el hilo principal
        self.after(0, self._update_progress_ui)
    
    def _debounced_update(self) -> None:
        """Actualización debounced de la UI"""
        self._update_pending = False
        self._update_progress_ui()
    
    def _on_track_end(self) -> None:
        """Callback cuando termina una pista con thread-safe UI update"""
        repeat_mode = self._playlist_manager.get_repeat_mode()
        
        if repeat_mode == 2:  # Repeat one
            # Repetir la misma canción
            self._audio_player.play()
        else:
            # Avanzar a la siguiente canción en el hilo principal
            self.after(0, self._on_next)
    
    def _on_track_select(self, index: int) -> None:
        """
        Maneja la selección de una pista en la playlist
        
        Args:
            index: Índice de la pista seleccionada
        """
        if self._playlist_manager.set_current_index(index):
            self._load_current_track()
            if self._audio_player.get_state() == PlayerState.PLAYING:
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
            
            self._refresh_playlist_view()
            self._update_ui_state()
            
            # Guardar playlist automáticamente
            self._playlist_manager.save_playlist()
    
    def _update_progress_ui(self) -> None:
        """Actualiza la UI de la barra de progreso"""
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
        Maneja errores del reproductor de audio con thread-safe UI update
        
        Args:
            error_message: Mensaje de error
        """
        logger.error(f"Error de audio: {error_message}")
        self.after(0, lambda: messagebox.showerror(
            "Audio Error",
            f"Ocurrió un error de audio:\n{error_message}"
        ))
    
    def _setup_keyboard_shortcuts(self) -> None:
        """Configura los atajos de teclado optimizados"""
        from functools import partial
        
        # Espacio: Play/Pause
        self.bind("<space>", lambda e: self._toggle_play_pause())
        
        # Flecha izquierda: Anterior (con Ctrl para retroceder 10s)
        self.bind("<Left>", lambda e: self._on_previous())
        self.bind("<Control-Left>", lambda e: self._seek_backward())
        
        # Flecha derecha: Siguiente (con Ctrl para avanzar 10s)
        self.bind("<Right>", lambda e: self._on_next())
        self.bind("<Control-Right>", lambda e: self._seek_forward())
        
        # Flecha arriba: Subir volumen
        self.bind("<Up>", lambda e: self._volume_up())
        
        # Flecha abajo: Bajar volumen
        self.bind("<Down>", lambda e: self._volume_down())
        
        # M: Mute/Unmute
        self.bind("<m>", lambda e: self._toggle_mute())
        
        # S: Toggle Shuffle
        self.bind("<s>", lambda e: self._on_shuffle())
        
        # R: Toggle Repeat
        self.bind("<r>", lambda e: self._on_repeat())
        
        # L: Load files
        self.bind("<l>", lambda e: self._on_load_files())
        
        # Q: Quit
        self.bind("<q>", lambda e: self._on_close())
        
        # F: Toggle fullscreen
        self.bind("<f>", lambda e: self._toggle_fullscreen())
        
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
        self._audio_player.set_volume(new_vol)
        self._player_controls.set_volume(new_vol)
        logger.info(f"Volumen: {int(new_vol * 100)}%")
    
    def _volume_down(self) -> None:
        """Baja el volumen un 10%"""
        current_vol = self._audio_player.get_volume()
        new_vol = max(0.0, current_vol - 0.1)
        self._audio_player.set_volume(new_vol)
        self._player_controls.set_volume(new_vol)
        logger.info(f"Volumen: {int(new_vol * 100)}%")
    
    def _toggle_mute(self) -> None:
        """Alterna entre mute y unmute"""
        current_vol = self._audio_player.get_volume()
        if current_vol > 0:
            self._previous_volume = current_vol
            self._audio_player.set_volume(0.0)
            self._player_controls.set_volume(0.0)
            logger.info("Volumen silenciado")
        else:
            new_vol = getattr(self, '_previous_volume', 0.7)
            self._audio_player.set_volume(new_vol)
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
        """Inicia el bucle principal de la aplicación optimizado"""
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.mainloop()
        except Exception as e:
            logger.error(f"Error en mainloop: {e}")
        finally:
            logger.info("Aplicación finalizada")
    
    def _on_close(self) -> None:
        """Maneja el cierre de la ventana optimizado"""
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
