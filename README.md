# Musik Player

Reproductor de música offline de escritorio con interfaz gráfica moderna y elegante.

## Características

- **Interfaz gráfica moderna**: Estilo dark/premium usando CustomTkinter con múltiples temas
- **Reproducción offline**: Sin necesidad de conexión a internet
- **Soporte para múltiples formatos**: MP3, WAV, OGG, FLAC
- **Controles completos**: Play/Pause, Siguiente, Anterior, Volumen, Barra de progreso
- **Gestión de playlist**: Agregar, remover, buscar y organizar pistas
- **Modos de reproducción**: Shuffle y Repeat (Off, All, One)
- **Persistencia**: Guarda automáticamente tu playlist y configuración
- **Extracción de metadatos**: Información de artista, álbum, título, etc.
- **Atajos de teclado**: Control total desde el teclado
- **Búsqueda en playlist**: Filtra rápidamente tus canciones
- **Diseño ligero y optimizado**: Rendimiento eficiente

## Requisitos del Sistema

- Python 3.10 o superior
- Windows 10/11, macOS, o Linux
- 4GB RAM mínimo
- 100MB espacio en disco

## Instalación

1. Clonar o descargar el repositorio:
```bash
git clone https://github.com/tu-usuario/musik-player.git
cd musik-player
```

2. Crear un entorno virtual (recomendado):
```bash
python -m venv venv

# En Windows:
venv\Scripts\activate

# En macOS/Linux:
source venv/bin/activate
```

3. Instalar las dependencias:
```bash
pip install -r requirements.txt
```

## Uso

Ejecutar el reproductor:
```bash
python src/main.py
```

### Controles

#### Botones de la Interfaz
- **Play/Pause (▶/⏸)**: Reproducir o pausar la canción actual
- **Siguiente (▶▶)**: Saltar a la siguiente canción en la playlist
- **Anterior (◀◀)**: Volver a la canción anterior
- **Shuffle (🔀)**: Activar/desactivar reproducción aleatoria
- **Repeat (🔁/🔂)**: Ciclar entre Off, Repeat All, Repeat One
- **Barra de Volumen**: Ajustar el volumen de reproducción
- **Barra de Progreso**: Navegar dentro de la canción actual
- **Cargar Archivos**: Agregar archivos de audio a la playlist
- **Búsqueda**: Filtrar canciones por título o artista

#### Atajos de Teclado
- **Espacio**: Play/Pause
- **Flecha Izquierda**: Canción anterior
- **Ctrl + Flecha Izquierda**: Retroceder 10 segundos
- **Flecha Derecha**: Siguiente canción
- **Ctrl + Flecha Derecha**: Avanzar 10 segundos
- **Flecha Arriba**: Subir volumen 10%
- **Flecha Abajo**: Bajar volumen 10%
- **M**: Mute/Unmute
- **S**: Toggle Shuffle
- **R**: Toggle Repeat
- **L**: Cargar archivos
- **F**: Pantalla completa
- **Escape**: Salir de pantalla completa
- **Q**: Cerrar aplicación

## Formatos Soportados

- MP3 (MPEG Audio Layer III)
- WAV (Waveform Audio File Format)
- OGG (Ogg Vorbis)
- FLAC (Free Lossless Audio Codec)

## Estructura del Proyecto

```
musik-player/
├── src/
│   ├── main.py                   # Punto de entrada principal
│   ├── ui/                       # Módulos de interfaz gráfica
│   │   ├── main_window.py        # Ventana principal
│   │   ├── player_controls.py    # Controles de reproducción
│   │   ├── playlist_view.py      # Vista de playlist
│   │   └── styles.py             # Estilos y temas
│   ├── audio/                    # Módulos de audio
│   │   ├── player.py             # Motor de reproducción
│   │   └── playlist_manager.py   # Gestión de playlist
│   └── utils/                    # Utilidades
│       ├── config_manager.py     # Gestión de configuración
│       ├── file_handler.py       # Manejo de archivos
│       └── metadata_extractor.py # Extracción de metadatos
├── .github/
│   └── workflows/
│       └── build.yml             # GitHub Actions CI/CD
├── requirements.txt              # Dependencias
├── build.py                      # Script de compilación
├── README.md                     # Este archivo
├── GUIA_DEL_PROYECTO.md          # Documentación técnica
└── MEJORAS_REALIZADAS.md        # Registro de mejoras
```

## Compilación

Para crear un ejecutable:

### Windows:
```bash
python build.py
```

### Manual con PyInstaller:
```bash
pip install pyinstaller
pyinstaller --name=MusikPlayer --windowed --onedir --add-data="src;src" --hidden-import=customtkinter --hidden-import=pygame --hidden-import=mutagen --clean src/main.py
```

El ejecutable se generará en la carpeta `dist/MusikPlayer/`.

### Instalador de Windows (NSIS):
```bash
python build.py
makensis installer.nsi
```

Esto genera `MusikPlayer-Setup.exe` con el instalador que incluye accesos directos, asociaciones de archivos (MP3, WAV, OGG, FLAC) y entrada en Agregar/Quitar programas.

## Desarrollo

Para más detalles sobre la arquitectura y plan de implementación, consulte el documento [GUIA_DEL_PROYECTO.md](GUIA_DEL_PROYECTO.md).

## Configuración

La aplicación guarda automáticamente:
- Posición y tamaño de la ventana
- Volumen actual
- Estado de Shuffle y Repeat
- Playlist actual
- Tema seleccionado

Los archivos de configuración se guardan en el directorio de la aplicación:
- `musik_config.json` - Configuración general
- `musik_playlist.json` - Playlist guardada
- `musik.log` - Log de la aplicación

## Troubleshooting

### Error: ModuleNotFoundError

Asegúrese de haber instalado todas las dependencias:
```bash
pip install -r requirements.txt
```

### Error: No se puede reproducir el archivo

Verifique que el formato del archivo sea soportado (MP3, WAV, OGG, FLAC).

### El audio no se escucha

- Verifique que el volumen no esté en 0
- Asegúrese de que ningún otro programa esté usando el dispositivo de audio
- Verifique la configuración de audio de su sistema

### La playlist no se guarda

- Verifique que tenga permisos de escritura en el directorio
- Revisar el archivo `musik.log` para más detalles

## Características Futuras

- [ ] Visualizador de audio (waveform)
- [ ] Ecualizador
- [ ] Soporte de listas de reproducción múltiples
- [ ] Integración con Spotify/Apple Music
- [ ] Sincronización en la nube
- [ ] Soporte de letras
- [ ] Descarga de metadatos de internet

## Contribución

Las contribuciones son bienvenidas! Por favor:
1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## Licencia

MIT License

## Autor

Desarrollado con Devin AI Assistant

## Versión

Versión 1.0.0 - Release inicial
