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

El arnés ejecuta **más de 300 comprobaciones deterministas**, entre ellas:

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

## CI y release continuo

`.github/workflows/build.yml` ejecuta en cada *push* y en cada *pull request*, sobre `windows-2022`: restauración, compilación con advertencias como errores, arnés completo, publicación estándar, una comprobación de completitud de la publicación (los trece archivos sin los que la aplicación arranca mal o no arranca) y subida del artefacto.

`.github/workflows/release.yml` convierte cada push **integrado a `main`** en un Release de GitHub con instalador firmado. Se dispara al concluir con éxito el workflow `build` (mediante `workflow_run`), descarga el artefacto YA VERIFICADO de esa ejecución — no recompila nada, lo que publica es exactamente lo que pasó el arnés —, y firma con **Authenticode** cada binario ejecutable y biblioteca del paquete (`signtool` con digest SHA256 y sellado de tiempo RFC 3161, que mantiene la firma válida tras la expiración del certificado). El certificado llega como secret `PFX_BASE64` (Base64, con la cadena completa de cuatro entidades dentro del PFX) y su contraseña como `PFX_PASSWORD`; la clave privada se importa al almacén del runner, el fichero PFX se destruye con relleno a cero **antes** de seguir, y la contraseña nunca aparece en una línea de comandos. Después compila el **instalador Inno Setup** (tema oscuro, asociación de extensiones de audio vía `OpenWithProgids`, detección de runtimes, desinstalación limpia), firma también el instalador, destruye el certificado del almacén y publica el Release etiquetado `v0.0.0-<sha-corto>` con el instalador firmado y su checksum SHA256. La marca es el commit: un commit, un release; re-ejecutar CI actualiza el release del mismo commit en lugar de duplicarlo. Las *pull requests* nunca publican.

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
- **La cola SPSC reconoce su propio estado roto.** El contrato de `Reset` exige ambos hilos detenidos, pero buscar o descargar un archivo con el callback de audio en marcha lo viola de facto: los índices se cruzan durante una ventana y el recuento declarado sale negativo o por encima de la capacidad. `Read` y `Write` tratan ese estado como «todavía no hay nada coherente» y devuelven cero en lugar de copiar con índices sin sentido; la lectura se recoge en la vuelta siguiente, ya con los índices reasentados.
- **El remuestreador verifica en tiempo de ejecución que un solo hilo lo usa.** La instancia no es segura para hilos a propósito, y una invocación cruzada no produce un error visible sino un flujo con la fase corrompida, de los defectos más caros de diagnosticar a oído. `Process` comprueba que quien entra es el mismo hilo que ya está dentro y lanza en caso contrario.
- **Cada hilo desinicializa solo el apartamento COM que inicializó.** `CoInitializeEx` devuelve `S_FALSE` cuando el hilo ya lo tenía: el recuento pertenece al llamador previo, y revertarlo ajeno deja un hilo sin apartamento para el siguiente componente que lo necesite. El hilo de audio aplica el mismo criterio que el de apertura.
- **Una apertura fallida limpia sus recursos parciales en el constructor.** Si la negociación con el dispositivo falla, la instancia nunca llega a escapar y nadie llamará a `Dispose`: los eventos de kernel, el bloque de formato y el apartamento COM se liberan en la ruta de fallo, porque duplicar esa lógica en dos sitios es como se introducen fugas.
- **Rearmar el motor no debe cortar el sonido.** Desde el menú, los ajustes del motor reconstruyen el dispositivo conservando archivo y posición: el motor nuevo se abre ANTES de liberar el viejo, de modo que si el dispositivo rechaza la combinación elegida la reproducción sigue con los ajustes anteriores y el fallo queda reducido a un aviso.
- **El despacho SIMD se decide por etapa, no en tiempo de compilación.** La FFT pregunta el CPUID real del procesador en cada etapa y toma el camino más ancho que el hardware sostiene: 512 bits (AVX-512, 16 mariposas), 256 (AVX2, 8) o 128 (SSE4.2/AdvSIMD, 4). Todos los caminos aplican la misma secuencia escalar por carril — multiplicar, restar, sumar, sin FMA ni sumas horizontales — de modo que la paridad bit a bit entre caminos que verifica el arnés se conserva: el ancho cambia cuántas muestras van por instrucción, nunca cómo se combina cada muestra.
- **El tramado TPDF es determinista y conmutable.** El PRNG es xorshift32 de semilla fija: la misma señal produce exactamente el mismo ruido en cada ejecución, lo que hace comparables las verificaciones. La conversión a 16/24 bits lo aplica antes del redondeo con recorte final; a 32 bits no se aplica (el escalón ya es inaudible) y la propiedad `EnableDither` lo apaga para escuchas de siseo cero. Sin dither, la conversión es exacta: 0.5 entra, 16384 sale.
- **El recorte duro se sustituye por un limitador de rodilla suave.** Por debajo de −0.1 dBFS la señal pasa bit a bit; por encima, la compresión es tangente hiperbólica con pendiente unitaria en la rodilla y techo exacto 1.0. Con remuestreo activo, la cadena reserva además −0.2 dBFS de margen: los picos inter-muestra que la interpolación sinc genera entre muestras ya no llegan al DAC como distorsión.
- **El modo bit-perfecto se declara y se defiende.** Cuando frecuencia, canales y volumen coinciden con el endpoint, la cadena declara `IsBitPerfectPassthrough` y la salida omite limitador y recorte: el DAC recibe el flujo decodificado sin tocar un bit. Cualquier alteración (volumen distinto de uno, mezcla, remuestreo) invalida el estado y las protecciones vuelven.
- **FTZ/DAZ se activan en el hilo de audio.** Los denormales que producen los fades y las colas del filtro cuestan cerca de cien ciclos cada uno en microcódigo; con los bits de MXCSR puestos el hardware los flusha en un ciclo, a −149 dBFS, inaudible por construcción. El registro previo se restaura al salir del hilo.
- **El tramado TPDF entra antes del redondeo y se recorta después.** Convertir a 16/24 bits sin tramado produce distorsión de cuantización correlacionada con la señal; el ruido triangular (resta de dos uniformes, ±1 LSB) la sustituye por un siseo plano de -93 dBFS. La amplitud exacta importa: ±2 LSB aplanan igual pero elevan el suelo de ruido 3 dB sin necesidad, y los extremos a escala plena se recortan para que el propio tramado nunca envuelva la muestra al signo opuesto. A 32 bits el escalón ya es inaudible y el tramado no se aplica.
- **La ventana se adapta al espacio y deja de pintar cuando no hay nada que ver.** La colocación se recuerda en el perfil del usuario y se re-acota al monitor actual (DPI incluido); por debajo de 760 píxeles el layout se compacta con el disparador adaptativo del marcado. El temporizador de dibujo corre a 30 fps activa, 4 fps desactivada y cero minimizada, y el espectro se congela tras doce fotogramas asentado en silencio: invalidar un lienzo para pintar el mismo polígono es trabajo puro.
- **Un decodificador muerto no puede seguir «reproduciendo».** Ante un archivo corrupto el hilo decodificador registra el error y apaga el estado de render, no solo el bombeo: si no, la interfaz mostraría «reproduciendo» para siempre sobre silencio y el botón de pausa no pausaría nada.

## Estado

- Compilación con `TreatWarningsAsErrors` + analizadores de AOT/recorte activos como disciplina: **0 advertencias, 0 errores**.
- Cadena de reproducción validada contra hardware real: 24 576 fotogramas en 50 *callbacks* sin una sola espera agotada.
- MMCSS se trata como mejora, no como requisito: si el servicio no está disponible, el hilo cae a prioridad elevada normal y la reproducción sigue.
