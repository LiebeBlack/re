# Hidra

Reproductor de audio para Windows 10/11 construido directamente sobre WASAPI, Media Foundation y WinUI 3, sin middleware de audio ni dependencias de códecs externas.

## El proyecto en una frase

Una cadena de señal completa —decodificación, remuestreo, mezcla y salida— cuyo hilo de tiempo real no reserva memoria, entregada como aplicación de escritorio de despliegue estándar: un ejecutable, sus bibliotecas y las dependencias del sistema.

## Arquitectura

```
┌────────────────────────────────────────────────────────────────────┐
│  [04] Hidra.Shell        Interfaz WinUI 3                          │
│       Ventana sin empaquetar, espectro en Canvas, barra de        │
│       búsqueda, transporte y diagnóstico en vivo. Atajos:         │
│       espacio, flechas. No toca audio: pinta contadores.          │
├────────────────────────────────────────────────────────────────────┤
│  [03] Hidra.Audio        Motores de hardware                       │
│       WasapiExclusiveOutput  → negociación y render por evento     │
│       MediaFoundationDecoder → FLAC/MP3/AAC/WAV/WMA sin NuGet      │
│       PlaybackPipeline       → hilo decodificador + cola + DSP     │
├────────────────────────────────────────────────────────────────────┤
│  [02] Hidra.Kernel       Núcleo sin asignaciones                   │
│       DSP SIMD (FFT radix-2, sinc-Kaiser, ventanas, bandas)        │
│       memoria alineada a 64 B, cola SPSC sin bloqueo               │
│       interop kernel32 + MMCSS (Avrt) vía LibraryImport            │
├────────────────────────────────────────────────────────────────────┤
│  [03] Hidra.Interop      CsWin32                                   │
│       Superficie Win32/WASAPI/MF generada desde metadatos          │
│       oficiales de Windows, no transcrita a mano.                  │
└────────────────────────────────────────────────────────────────────┘
```

El hilo de audio solo vacía una cola ya llena. La decodificación ocurre en un hilo aparte y se comunica con el de audio por una cola de un productor y un consumidor sin candados; si el decodificador se retrasa, el hilo de audio rellena con silencio y lo contabiliza en lugar de esperar. El análisis de espectro vive en el temporizador de la interfaz, nunca dentro del callback del dispositivo.

## Despliegue estándar, no autocontenido

El ejecutable se publica apoyado en el runtime de .NET ya instalado en el equipo:

```
dotnet publish src/Hidra.Shell/Hidra.Shell.csproj -c Release -o artifacts/publish
```

El resultado es un `Hidra.Shell.exe` acompañado de `Hidra.Kernel.dll`, `Hidra.Audio.dll`, `Hidra.Interop.dll`, el marcado compilado (`.xbf`), el índice de recursos (`.pri`) y las dependencias externas (`Microsoft.Windows.SDK.NET.dll`, `WinRT.Runtime.dll`). No hay copia del runtime incrustada ni empaquetado MSIX.

Dos particularidades que el pipeline cubre de forma explícita:

- El publicador de aplicaciones sin empaquetar omite `.xbf` y `.pri`; el proyecto los copia en un destino posterior a `Publish`, y la CI verifica su presencia porque sin ellos el ejecutable no arranca y no avisa del motivo.
- No hace falta el conjunto de herramientas de C++ de Visual Studio, que era el único paso del proceso que lo exigía.

Requisito de ejecución: **Windows 10 1809** o superior con el runtime de .NET 10 y el runtime de Windows App SDK instalados.

## Verificación

```
dotnet build Hidra.slnx -c Release
dotnet run --project tests/Hidra.Verify -c Release
```

El arnés ejecuta **280 comprobaciones deterministas**, entre ellas:

- FFT contrastada contra una DFT directa, y **paridad bit a bit** entre el camino vectorial SIMD y el escalar.
- Paridad de canal completo de extremo a extremo: tonos a 44,1 k y 48 k remuestreados en ambas direcciones y mezclados de mono a estéreo, verificando pico exacto y frecuencia dominante.
- Cola SPSC sin bloqueo estresada con dos hilos reales cruzando el final del arreglo.
- Conversión de muestras incluyendo el caso en que `(float)int.MaxValue` desborda a `int.MinValue`, que era una inversión de escala audible.
- Guardas de cero asignaciones en las rutas de tiempo real.
- Búsqueda de extremo a extremo en tres escenarios: con el archivo detenido (sin arrancar la reproducción), al centro mientras suena y hacia atrás; en cada caso se verifica que la posición quede reflejada, que la salida no sea silencio y que el tono dominante se conserve tras el salto.

Las dos sondas que tocan hardware real (abrir el dispositivo de audio y emitir sonido) son manuales a propósito:

```
dotnet run --project tests/Hidra.Verify -c Release -- --probe-audio
```

## CI

`.github/workflows/build.yml` ejecuta en cada *push*, sobre `windows-2022`: restauración, compilación con advertencias como errores, arnés completo, publicación estándar, una comprobación de completitud de la publicación (los diez archivos sin los que la aplicación arranca mal o no arranca) y subida del artefacto.

## Decisiones de diseño que no son obvias

- **El fin de flujo llega cuando se agota la cola, no el archivo.** La decodificación es mucho más rápida que el tiempo real: declarar el final al agotarse el lector dejaría medio bloque de audio por sonar y un estado "terminado" prematuro.
- **Buscar pausa el render, no el bombeo.** Son dos interruptores distintos: mientras la búsqueda vacía y rellena la cola, el dispositivo emite silencio sin tocar la cola (así no hace falta ningún candado), y el bombeo solo se reanuda con el material nuevo ya delante del consumidor.

- **`GetMixFormat` no es el formato del hardware.** Devuelve el formato del mezclador del sistema. La negociación conserva frecuencia y canales del dispositivo y sondea las codificaciones que el endpoint acepta de verdad; en las máquinas de desarrollo encontró 24 bits enteros donde el mezclador declaraba flotante.
- **El rechazo de `AUDCLNT_STREAMOPTIONS_RAW` llega en `Initialize`.** No al solicitarlo. La estrategia reintenta sin RAW antes de rendirse.
- **`AUDCLNT_E_BUFFER_SIZE_NOT_ALIGNED`** se maneja re-consultando el período alineado y reinicializando el cliente, como exige la documentación de modo exclusivo.
- **Las interfaces de servicio de WASAPI se obtienen con `GetService`**, no con `QueryInterface`; las *derivadas* (`IAudioClient2`), al contrario. La misma idea funciona en un sitio y falla en otro.
- **La ganancia se aplica con rampa** a lo largo del bloque: un cambio instantáneo de volumen es un escalón en la forma de onda, que se oye como un chasquido.
- **El escalado entero va en doble precisión**, porque en simple `(float)int.MaxValue` es 2 147 483 648 y la muestra más fuerte posible se convierte en la más débil.
- **Si el modo exclusivo no está disponible se degrada a compartido**, porque un reproductor que falla entero por no poder tomar el dispositivo es peor que uno que suena.

## Estado

- Compilación con `TreatWarningsAsErrors` + analizadores de AOT/recorte activos como disciplina: **0 advertencias, 0 errores**.
- Cadena de reproducción validada contra hardware real: 24 576 fotogramas en 50 *callbacks* sin una sola espera agotada.
- MMCSS se trata como mejora, no como requisito: si el servicio no está disponible, el hilo cae a prioridad elevada normal y la reproducción sigue.
