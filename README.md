# Musik Player

Reproductor de música offline de escritorio con interfaz gráfica moderna y elegante.

## Características

- Interfaz gráfica moderna estilo dark/premium usando CustomTkinter
- Reproducción offline sin necesidad de conexión a internet
- Soporte para múltiples formatos: MP3, WAV, OGG, FLAC
- Controles completos: Play/Pause, Siguiente, Anterior, Volumen
- Gestión de lista de reproducción (playlist)
- Diseño ligero y optimizado

## Requisitos del Sistema

- Python 3.10 o superior
- Windows 10/11, macOS, o Linux
- 4GB RAM mínimo
- 100MB espacio en disco

## Instalación

1. Clonar o descargar el repositorio:
```bash
cd musik
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

- **Play/Pause**: Reproducir o pausar la canción actual
- **Siguiente (▶▶)**: Saltar a la siguiente canción en la playlist
- **Anterior (◀◀)**: Volver a la canción anterior
- **Barra de Volumen**: Ajustar el volumen de reproducción
- **Barra de Progreso**: Navegar dentro de la canción actual
- **Cargar Archivos**: Agregar archivos de audio a la playlist

## Formatos Soportados

- MP3 (MPEG Audio Layer III)
- WAV (Waveform Audio File Format)
- OGG (Ogg Vorbis)
- FLAC (Free Lossless Audio Codec)

## Estructura del Proyecto

```
musik/
├── src/
│   ├── main.py              # Punto de entrada principal
│   ├── ui/                  # Módulos de interfaz gráfica
│   ├── audio/               # Módulos de audio
│   └── utils/               # Utilidades
├── requirements.txt          # Dependencias
├── README.md                # Este archivo
└── GUIA_DEL_PROYECTO.md     # Documentación técnica
```

## Desarrollo

Para más detalles sobre la arquitectura y plan de implementación, consulte el documento [GUIA_DEL_PROYECTO.md](GUIA_DEL_PROYECTO.md).

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

## Licencia

MIT License

## Autor

Desarrollado con Devin AI Assistant
