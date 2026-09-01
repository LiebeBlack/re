# Instrucciones de Instalación - Musik Player

## Requisitos Previos

Antes de instalar Musik Player, necesitas tener Python instalado en tu sistema.

### Verificar si Python está instalado

Abre una terminal o símbolo del sistema y ejecuta:

```bash
python --version
```

O alternativamente:

```bash
python3 --version
```

Si ves un número de versión (como Python 3.10.0 o superior), ya tienes Python instalado.

### Instalar Python (si no está instalado)

#### Windows
1. Descarga Python desde [python.org](https://www.python.org/downloads/)
2. Ejecuta el instalador
3. **IMPORTANTE**: Marca la casilla "Add Python to PATH" durante la instalación
4. Completa la instalación

#### macOS
Usa Homebrew:
```bash
brew install python
```

O descarga desde [python.org](https://www.python.org/downloads/)

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3 python3-pip
```

## Instalación de Musik Player

### Paso 1: Navegar al directorio del proyecto

```bash
cd C:\Users\L\Desktop\musik
```

### Paso 2: Crear un entorno virtual (recomendado)

Esto crea un entorno aislado para el proyecto:

```bash
python -m venv venv
```

### Paso 3: Activar el entorno virtual

#### Windows
```bash
venv\Scripts\activate
```

#### macOS/Linux
```bash
source venv/bin/activate
```

Verás que el prompt cambia para indicar que el entorno virtual está activo.

### Paso 4: Instalar las dependencias

```bash
pip install -r requirements.txt
```

Esto instalará:
- customtkinter: Interfaz gráfica moderna
- pygame: Motor de audio
- mutagen: Gestión de metadatos de audio

### Paso 5: Ejecutar Musik Player

```bash
python src/main.py
```

## Solución de Problemas

### Error: "python no se reconoce como comando"

**Solución**: Asegúrate de haber marcado "Add Python to PATH" durante la instalación de Python. Si no lo hiciste:

1. Reinstala Python y marca esa opción
2. O agrega Python manualmente a las variables de entorno

### Error: "No se puede importar customtkinter"

**Solución**: Asegúrate de haber instalado las dependencias:
```bash
pip install -r requirements.txt
```

### Error: "No module named 'pygame'"

**Solución**: Instala pygame específicamente:
```bash
pip install pygame
```

### Error: "Error al inicializar pygame mixer"

**Solución**: Esto puede ocurrir si no hay dispositivo de audio disponible. Asegúrate de:
- Tener altavoces o auriculares conectados
- Que ningún otro programa esté bloqueando el dispositivo de audio

### El audio no se reproduce

**Solución**:
1. Verifica que el volumen no esté en 0
2. Asegúrate de que el formato del archivo sea soportado (MP3, WAV, OGG, FLAC)
3. Verifica la configuración de audio de tu sistema

## Desinstalación

Para desinstalar Musik Player:

1. Desactiva el entorno virtual (si está activo):
   ```bash
   deactivate
   ```

2. Elimina el directorio del proyecto:
   ```bash
   rm -rf musik
   ```

3. Opcionalmente, elimina el entorno virtual:
   ```bash
   rm -rf venv
   ```

## Actualización

Para actualizar las dependencias a las últimas versiones:

```bash
pip install --upgrade -r requirements.txt
```

## Soporte de Formatos

Musik Player soporta los siguientes formatos de audio:
- **MP3**: Formato más común, buena calidad/compresión
- **WAV**: Sin compresión, alta calidad
- **OGG**: Formato abierto, buena compresión
- **FLAC**: Sin pérdidas, alta calidad

## Requisitos del Sistema

- **Python**: 3.10 o superior
- **Sistema Operativo**: Windows 10/11, macOS, o Linux
- **RAM**: 4GB mínimo
- **Espacio en disco**: 100MB mínimo
- **Audio**: Dispositivo de audio funcional

## Próximos Pasos

Una vez instalado, consulta el [README.md](README.md) para aprender a usar Musik Player.

Para detalles técnicos sobre la arquitectura del proyecto, consulta [GUIA_DEL_PROYECTO.md](GUIA_DEL_PROYECTO.md).
