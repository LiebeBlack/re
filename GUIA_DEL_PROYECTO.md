# Guía del Proyecto - Musik Player

## 1. Visión General

**Musik Player** es un reproductor de música offline de escritorio desarrollado en Python con interfaz gráfica moderna y elegante. El objetivo es proporcionar una experiencia de usuario premium con controles intuitivos y soporte para múltiples formatos de audio.

### 1.1 Objetivos Principales

- Interfaz gráfica moderna estilo dark/premium usando CustomTkinter
- Reproducción offline sin necesidad de conexión a internet
- Soporte para formatos: MP3, WAV, OGG, FLAC
- Controles completos: Play/Pause, Siguiente, Anterior, Volumen
- Gestión de lista de reproducción (playlist)
- Rendimiento ligero y optimizado
- Código limpio, modular y mantenible

### 1.2 Stack Tecnológico

- **Lenguaje**: Python 3.10+
- **Interfaz Gráfica**: CustomTkinter (interfaz moderna sobre Tkinter)
- **Motor de Audio**: pygame (mixer)
- **Gestión de Metadatos**: mutagen (opcional, para información de canciones)
- **Gestor de Paquetes**: pip

## 2. Arquitectura del Sistema

### 2.1 Estructura de Directorios

```
musik/
├── src/
│   ├── __init__.py
│   ├── main.py              # Punto de entrada principal
│   ├── ui/                  # Módulos de interfaz gráfica
│   │   ├── __init__.py
│   │   ├── main_window.py   # Ventana principal (layout, temas, estado)
│   │   ├── player_controls.py  # Controles de reproducción
│   │   ├── playlist_view.py    # Vista de lista de reproducción
│   │   ├── styles.py          # Temas, colores y helpers de color
│   │   ├── animations.py      # Motor de animaciones (tweens, pulso, hover)
│   │   └── widgets.py         # Widgets reutilizables (tooltip, visualizador)
│   ├── audio/                # Módulos de audio
│   │   ├── __init__.py
│   │   ├── player.py         # Motor de reproducción
│   │   └── playlist_manager.py # Gestión de playlist
│   └── utils/                # Utilidades
│       ├── __init__.py
│       └── file_handler.py   # Manejo de archivos
├── requirements.txt          # Dependencias
├── README.md                # Documentación
└── GUIA_DEL_PROYECTO.md     # Este documento
```

### 2.2 Módulos Principales

#### 2.2.1 Módulo de Interfaz Gráfica (UI)

**Responsabilidades:**
- Renderizar la interfaz gráfica
- Manejar eventos de usuario
- Mostrar estado del reproductor
- Actualizar visualizaciones

**Componentes:**
- `main_window.py`: Ventana principal contenedora
- `player_controls.py`: Botones de control (play, pause, next, prev, volume)
- `playlist_view.py`: Lista de canciones con scroll
- `styles.py`: Definición de colores, fuentes y estilos globales

#### 2.2.2 Módulo de Audio

**Responsabilidades:**
- Cargar y reproducir archivos de audio
- Controlar volumen
- Manejar estados de reproducción
- Soportar múltiples formatos

**Componentes:**
- `player.py`: Lógica principal de reproducción usando pygame
- `playlist_manager.py`: Gestión de cola de reproducción

#### 2.2.3 Módulo de Utilidades

**Responsabilidades:**
- Manejo de archivos y directorios
- Validación de formatos
- Rutas de archivo

**Componentes:**
- `file_handler.py`: Operaciones de archivo y directorio

## 3. Especificaciones Técnicas

### 3.1 Requisitos de Sistema

- Python 3.10 o superior (compatible hasta 3.13+)
- Windows 10/11, macOS, o Linux
- 4GB RAM mínimo
- 100MB espacio en disco

### 3.2 Dependencias

```
customtkinter>=5.2.0
pygame>=2.5.0
mutagen>=1.46.0  # Opcional, para metadatos
```

### 3.3 Formatos de Audio Soportados

- **MP3**: MPEG Audio Layer III
- **WAV**: Waveform Audio File Format
- **OGG**: Ogg Vorbis
- **FLAC**: Free Lossless Audio Codec

## 4. Diseño de Interfaz

### 4.1 Esquema de Colores (Tema Midnight Neon / dark_premium)

```python
PRIMARY_COLOR = "#0a0e1a"      # Fondo principal (casi negro azulado)
SECONDARY_COLOR = "#101728"    # Fondo secundario
CARD_COLOR = "#151d33"         # Superficies / tarjetas elevadas
ACCENT_COLOR = "#8b5cf6"       # Violeta eléctrico (acento principal)
ACCENT_HOVER = "#a78bfa"       # Acento en hover
GLOW_COLOR = "#22d3ee"         # Cian neón (resplandor / gradiente)
GRADIENT_A = "#8b5cf6"         # Inicio del gradiente (portada)
GRADIENT_B = "#22d3ee"         # Fin del gradiente (portada)
TEXT_COLOR = "#f1f5f9"         # Texto principal
TEXT_SECONDARY = "#8b93a7"     # Texto secundario
BUTTON_COLOR = "#1e2a45"       # Botones
BUTTON_HOVER = "#2a3a5f"       # Hover en botones
BORDER_COLOR = "#263252"       # Bordes sutiles (efecto glass)
```

**Temas disponibles** (cambio en vivo desde el header o con la tecla `T`):

| Tema | Clave | Acento | Glow |
|---|---|---|---|
| 🌙 Midnight Neon | `dark_premium` | `#8b5cf6` | `#22d3ee` |
| 🌊 Deep Ocean | `dark_blue` | `#38bdf8` | `#22d3ee` |
| 🌌 Aurora | `dark_purple` | `#a78bfa` | `#34d399` |
| 🌅 Sunset | `sunset` | `#fb7185` | `#fb923c` |
| 🍀 Emerald | `emerald` | `#34d399` | `#a3e635` |
| ☀️ Light | `light` | `#6366f1` | `#0ea5e9` |

### 4.2 Layout de la Ventana Principal

```
┌─────────────────────────────────────────────┐
│  Musik Player                    [Temas ▾] [Min][Max][X]│
├────────────────────────────────────────────────────────┤
│  ┌─ Now Playing ─────────────────────────────────────┐ │
│  │ (◉)  Song Title (elipsis)            00:00 / 03:45 │ │
│  │      Artist Name                      [00:00/03:45] │ │
│  │      ▮▮▮▮▮▮▮▮▮▮▮▮ (ecualizador animado)              │ │
│  └────────────────────────────────────────────────────┘ │
│      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░  [barra de progreso]       │
│   [◀◀]      [▶/⏸]      [▶▶]     🔊 [slider] 70%        │
│          [🔀 Shuffle]    [🔁 Repeat]                    │
│   [📁 Cargar Audio] [🗑 Limpiar] [📤 Exportar M3U]       │
├────────────────────────────────────────────────────────┤
│  Playlist                            [3 tracks ▾]      │
│  ┌──────────────────────────────────────────────────┐  │
│  │ ▮▮▮▮ Song Title - Artist                  [3:45] │  │
│  │ 2.  Another Song - Artist                [4:20] │  │
│  │ 3.  Third Song - Artist                  [2:55] │  │
│  └──────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────┤
│  ● Reproduciendo           3 pistas   Total 11:00      │
└────────────────────────────────────────────────────────┘
```

### 4.3 Componentes UI

#### 4.3.1 Barra de Progreso
- Slider interactivo para navegar en la canción
- Indicador de tiempo actual y total
- Actualización en tiempo real

#### 4.3.2 Controles de Reproducción
- Botón Anterior (◀◀): Canción anterior en playlist
- Botón Play/Pause (▶/⏸): Toggle reproducción
- Botón Siguiente (▶▶): Siguiente canción en playlist
- Barra de Volumen: Slider vertical u horizontal

#### 4.3.3 Lista de Reproducción
- Scrollable listbox o custom widget
- Indicador de canción actual
- Duración de cada canción
- Selección múltiple (opcional)

## 5. Flujo de Funcionalidad

### 5.1 Inicialización

1. Iniciar aplicación
2. Inicializar pygame mixer
3. Crear ventana principal
4. Cargar configuración (si existe)
5. Mostrar interfaz

### 5.2 Cargar Canción

1. Usuario selecciona archivo(s)
2. Validar formato de audio
3. Extraer metadatos (opcional)
4. Agregar a playlist
5. Actualizar UI

### 5.3 Reproducción

1. Usuario hace clic en Play
2. Cargar archivo en pygame mixer
3. Iniciar reproducción
4. Iniciar timer de actualización
5. Actualizar barra de progreso
6. Manejar eventos (pause, stop, next, prev)

### 5.4 Control de Volumen

1. Usuario ajusta slider de volumen
2. Actualizar volumen de pygame mixer
3. Guardar configuración (opcional)

## 6. Manejo de Errores

### 6.1 Errores Comunes

- **Archivo no encontrado**: Mostrar mensaje amigable
- **Formato no soportado**: Filtrar archivos válidos
- **Error de carga**: Reintentar o mostrar error
- **Dispositivo de audio ocupado**: Informar al usuario

### 6.2 Estrategia de Logging

- Log de errores en archivo `musik.log`
- Niveles: DEBUG, INFO, WARNING, ERROR
- Timestamp en cada entrada

## 7. Optimización y Rendimiento

### 7.1 Prácticas de Optimización

- Cargar archivos bajo demanda
- Buffer de audio optimizado
- Threading para actualización de UI
- Evitar bloqueos en interfaz

### 7.2 Gestión de Memoria

- Liberar recursos al cambiar de canción
- Limpiar playlist cuando sea necesario
- Manejo adecuado de referencias

## 8. Plan de Implementación

### Fase 1: Configuración Inicial
- [x] Crear estructura de directorios
- [ ] Configurar requirements.txt
- [ ] Crear módulos base con __init__.py
- [ ] Configurar logging

### Fase 2: Motor de Audio
- [ ] Implementar AudioPlayer con pygame
- [ ] Implementar soporte de formatos
- [ ] Implementar control de volumen
- [ ] Implementar estados de reproducción

### Fase 3: Interfaz Gráfica
- [ ] Implementar ventana principal
- [ ] Implementar estilos y colores
- [ ] Implementar controles de reproducción
- [ ] Implementar barra de progreso
- [ ] Implementar lista de reproducción

### Fase 4: Integración
- [ ] Conectar UI con motor de audio
- [ ] Implementar carga de archivos
- [ ] Implementar navegación de playlist
- [ ] Implementar persistencia (opcional)

### Fase 5: Pruebas y Optimización
- [ ] Pruebas unitarias de módulos
- [ ] Pruebas de integración
- [ ] Pruebas de rendimiento
- [ ] Corrección de bugs
- [ ] Optimización de código

## 9. Buenas Prácticas de Código

### 9.1 Estilo de Código

- Seguir PEP 8
- Nombres descriptivos en inglés
- Docstrings para funciones y clases
- Type hints donde sea apropiado
- Comentarios para lógica compleja

### 9.2 Principios SOLID

- **Single Responsibility**: Cada clase tiene una responsabilidad única
- **Open/Closed**: Abierto para extensión, cerrado para modificación
- **Liskov Substitution**: Subtipos deben ser sustituibles
- **Interface Segregation**: Interfaces específicas
- **Dependency Inversion**: Depender de abstracciones

### 9.3 Patrones de Diseño

- **Observer**: Para notificaciones de estado
- **Singleton**: Para instancia única del reproductor
- **Factory**: Para creación de componentes UI
- **Strategy**: Para diferentes estrategias de carga

## 10. Documentación

### 10.1 Documentación de Código

- Docstrings estilo Google o NumPy
- Ejemplos de uso en funciones complejas
- Diagramas de flujo para lógica compleja

### 10.2 Documentación de Usuario

- README.md con instrucciones de instalación
- Guía de uso básico
- Solución de problemas comunes

## 11. Futuras Mejoras

### 11.1 Características Potenciales

- Visualizador de audio (waveform)
- Ecualizador
- Atajos de teclado
- Temas personalizables
- Mínimizar a system tray
- Soporte de listas de reproducción guardadas
- Búsqueda en playlist
- Reproducción aleatoria (shuffle)
- Repetición de canción/playlist

### 11.2 Mejoras de Rendimiento

- Caching de metadatos
- Pre-buffering de audio
- Optimización de renderizado UI

## 12. Licencia y Distribución

- Licencia: MIT (recomendada)
- Distribución vía PyPI (opcional)
- Código abierto en GitHub (opcional)

---

**Versión del Documento**: 1.0  
**Fecha de Creación**: 2026-09-01  
**Autor**: Devin AI Assistant  
**Estado**: Borrador Inicial
