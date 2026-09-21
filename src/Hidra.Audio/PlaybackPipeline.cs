using Hidra.Kernel.Dsp;
using Hidra.Kernel.Interop;
using Hidra.Kernel.Memory;

namespace Hidra.Audio;

/// <summary>
/// Cadena de reproduccion: decodifica en un hilo aparte, convierte al formato del dispositivo
/// y entrega las muestras al hilo de audio sin reservar memoria.
/// </summary>
/// <remarks>
/// <para>
/// Hay exactamente dos hilos y cada uno tiene una responsabilidad distinta. El hilo de audio
/// <b>solo</b> vacia una cola circular ya llena; el trabajo pesado, que es leer y descomprimir
/// el archivo, ocurre en el hilo decodificador. Esa separacion es obligatoria: una lectura de
/// Media Foundation puede tardar milisegundos y tocar el monton, y hacerlo dentro del callback
/// del dispositivo produce un silencio audible cada vez.
/// </para>
/// <para>
/// La comunicacion entre ambos es una cola de un productor y un consumidor, sin bloqueo, que
/// no reserva memoria ni toma candados. Si el decodificador se retrasa, el hilo de audio
/// rellena con silencio y lo contabiliza en lugar de esperar.
/// </para>
/// <para>
/// Las reservas de los buffers de trabajo se hacen al cargar el archivo, en el hilo de la
/// interfaz, y se reutilizan bloque a bloque. El hilo de audio, por tanto, no reserva nunca.
/// </para>
/// <para>
/// Un detalle que no es evidente y que arruina la reproduccion si se pasa por alto: el
/// remuestreador es un filtro no causal, necesita mirar por delante de la muestra que produce.
/// Al final de cada bloque sobra una cola que todavia no se puede convertir, y esa cola hay
/// que <b>arrastrarla</b> al bloque siguiente. Si en lugar de eso se avanza el bloque entero,
/// la siguiente llamada pide una ventana que empieza despues de la posicion de lectura del
/// filtro, el filtro no encuentra sus muestras y devuelve cero salida, para siempre.
/// </para>
/// </remarks>
internal sealed class PlaybackPipeline : ISampleProvider, IDisposable
{
    /// <summary>Capacidad de la cola en muestras. 262 144 muestras son unos 2,7 s en estereo a 48 kHz.</summary>
    private const int RingSamples = 1 << 18;

    /// <summary>Fotogramas que se piden al decodificador en cada vuelta.</summary>
    private const int DecodeBlockFrames = 4096;

    /// <summary>Fotogramas que se retienen para el analisis de espectro.</summary>
    private const int ScopeFrames = 1 << 13;

    private const int ScopeMask = ScopeFrames - 1;

    /// <summary>
    /// Margen que se suma a cada bloque para alojar la cola que arrastra el remuestreador.
    /// </summary>
    /// <remarks>
    /// El margen tiene que ser al menos la ventana del filtro, no su retardo. El filtro no
    /// puede producir la ultima muestra hasta que la ventana completa cae dentro del bloque,
    /// de modo que lo que sobra al final de cada vuelta es del orden de un numero de
    /// coeficientes, no del retardo del centro. Confundir ambos deja el indice fuera del
    /// arreglo en cuanto el residuo supera el margen.
    /// </remarks>
    private const int CarryMargin = SincResampler.TapsPerPhase + 8;

    private readonly SpscRingBuffer<float> _ring = new(RingSamples);
    private readonly WaitEvent _stopRequested = new(manualReset: true, initialState: false);
    private readonly WaitEvent _playRequested = new(manualReset: true, initialState: false);
    private readonly Lock _stateGate = new();
    private readonly float[] _scope = new float[ScopeFrames];

    private long _scopeWrite;
    private long _renderedFrames;
    private long _underrunSamples;
    private float _currentGain = 1.0f;
    private float _targetGain = 1.0f;
    private int _deviceSampleRate;
    private int _deviceChannels;
    private bool _disposed;

    // Estado de busqueda. La version hace de epoca: cada peticion incrementa el contador y el
    // hilo decodificador ejecuta la ultima que haya visto, de modo que dos peticiones seguidas
    // se consolidan en una sola aplicacion sin candados ni señales adicionales.
    private long _seekVersion;
    private long _executedSeekVersion;
    private long _seekTargetTicks;
    private bool _resumeAfterSeek;

    // Estado de render en el dispositivo, separado a proposito del evento de bombeo. El evento
    // _playRequested gobierna el hilo decodificador y se apaga al llegar al fin de archivo, pero
    // entonces todavia queda material en cola que DEBE seguir sonando; una pausa real, en
    // cambio, tiene que silenciar la salida sin vaciar la cola. Son dos cosas distintas y por
    // eso tienen dos interruptores.
    private bool _renderActive;

    private MediaFoundationDecoder? _decoder;
    private Thread? _decodeThread;
    private string? _sourcePath;

    // Buffers de trabajo, reservados al cargar el archivo y reutilizados en cada bloque.
    private float[] _decodeScratch = [];
    private float[][] _channelScratch = [];
    private float[][] _convertedScratch = [];
    private float[] _outputScratch = [];
    private SincResampler?[] _resamplers = [];
    private int _fileChannels;
    private int _fileSampleRate;
    private int _outputChannels;
    private int _carryFrames;


    /// <summary>Indice absoluto del flujo de origen al que corresponde la primera muestra del buffer de trabajo.</summary>
    private long _convertBase;

    /// <summary>Ruta del archivo cargado, o null si no hay ninguno.</summary>
    public string? SourcePath => _sourcePath;

    /// <summary>Formato del archivo cargado.</summary>
    public AudioFormat SourceFormat { get; private set; }

    /// <summary>True cuando el archivo se ha consumido por completo.</summary>
    public bool EndOfStream { get; private set; }

    /// <summary>Error que detuvo el decodificador, si lo hubo.</summary>
    public Exception? LastError { get; private set; }

    /// <summary>True mientras la reproduccion avanza.</summary>
    public bool IsPlaying => _playRequested.IsSet;

    /// <summary>
    /// True mientras el dispositivo deba estar emitiendo lo que hay en cola.
    /// </summary>
    /// <remarks>
    /// No es lo mismo que <see cref="IsPlaying"/>: ese evento gobierna el hilo decodificador
    /// y se apaga al llegar al fin de archivo, pero entonces todavia queda material en cola
    /// saliendo por el dispositivo. Este estado es el que responde a la pregunta audible de
    /// si hay sonido o silencio, y es el que la busqueda apaga y reenciende.
    /// </remarks>
    public bool IsRendering => Volatile.Read(ref _renderActive);

    /// <summary>Fotogramas ya entregados al dispositivo.</summary>
    public long RenderedFrames => Interlocked.Read(ref _renderedFrames);

    /// <summary>Muestras de silencio insertadas por falta de datos.</summary>
    public long UnderrunSamples => Interlocked.Read(ref _underrunSamples);

    /// <summary>Muestras disponibles en la cola.</summary>
    public int BufferedSamples => _ring.Count;

    /// <summary>
    /// Posicion dentro del archivo del material entregado al dispositivo.
    /// </summary>
    /// <remarks>
    /// Avanza con la reproduccion, se congela en pausa y salta a la posicion pedida cuando se
    /// busca: es exactamente lo que un cursor de busqueda necesita mostrar. El hilo
    /// decodificador reescribe el acumulador al aplicar la busqueda, mientras el hilo de audio
    /// esta en silencio, y a partir de ahi Render lo avanza con el material de la nueva
    /// posicion; no hay un momento en el que ambos escriban a la vez.
    /// </remarks>
    public TimeSpan Position => _deviceSampleRate > 0
        ? TimeSpan.FromSeconds((double)RenderedFrames / _deviceSampleRate)
        : TimeSpan.Zero;

    /// <summary>Duracion declarada por el archivo cargado, si la fuente la informa.</summary>
    public TimeSpan? Duration => _decoder?.Duration;

    /// <summary>
    /// Ajusta la cadena al formato que el dispositivo ha concedido.
    /// </summary>
    /// <remarks>
    /// Debe llamarse antes de cargar cualquier archivo: el motor de salida solo conoce el
    /// formato despues de negociarlo, y la conversion depende de el.
    /// </remarks>
    public void Configure(int sampleRate, int channels)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(sampleRate);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(channels);

        lock (_stateGate)
        {
            Volatile.Write(ref _deviceSampleRate, sampleRate);
            Volatile.Write(ref _deviceChannels, channels);
        }
    }

    /// <summary>
    /// Volumen de salida, de 0 a 1.
    /// </summary>
    /// <remarks>
    /// Se aplica con una rampa a lo largo del bloque. Un cambio instantaneo de ganancia
    /// produce un escalon en la forma de onda y eso se oye como un chasquido, no como un
    /// cambio de volumen.
    /// </remarks>
    public double Volume
    {
        get => Volatile.Read(ref _targetGain);
        set => Volatile.Write(ref _targetGain, (float)Math.Clamp(value, 0.0, 1.0));
    }

    /// <summary>Abre un archivo y lo deja listo en pausa.</summary>
    public void Load(string path)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        ArgumentException.ThrowIfNullOrWhiteSpace(path);

        int deviceRate = Volatile.Read(ref _deviceSampleRate);
        int deviceChannels = Volatile.Read(ref _deviceChannels);

        if (deviceRate == 0)
        {
            throw new InvalidOperationException(
                "Hay que llamar a Configure con el formato del dispositivo antes de cargar un archivo.");
        }

        Unload();
        LastError = null;

        MediaFoundationDecoder decoder = MediaFoundationDecoder.Open(path);
        bool succeeded = false;

        try
        {
            int fileRate = decoder.Format.SampleRate;
            int fileChannels = decoder.Format.Channels;
            int outputChannels = MapChannels(fileChannels, deviceChannels, path);

            int workFrames = DecodeBlockFrames + CarryMargin;

            // Al convertir hacia arriba salen mas muestras de las que entran, con la relacion
            // de salida sobre entrada, que es la inversa de la del remuestreador.
            double expansion = (double)deviceRate / fileRate;
            int convertedCapacity = (int)Math.Ceiling(workFrames * expansion) + CarryMargin;

            _decodeScratch = new float[DecodeBlockFrames * fileChannels];
            _channelScratch = new float[fileChannels][];
            _convertedScratch = new float[outputChannels][];
            _resamplers = new SincResampler?[fileChannels];
            _outputScratch = new float[convertedCapacity * outputChannels];

            for (int channel = 0; channel < fileChannels; channel++)
            {
                _channelScratch[channel] = new float[workFrames];
                _resamplers[channel] = fileRate == deviceRate
                    ? null
                    : new SincResampler(fileRate, deviceRate);
            }

            for (int channel = 0; channel < outputChannels; channel++)
            {
                _convertedScratch[channel] = new float[convertedCapacity];
            }

            _fileChannels = fileChannels;
            _fileSampleRate = fileRate;
            _outputChannels = outputChannels;
            _carryFrames = 0;
            _convertBase = 0;

            // Una epoca nueva nace ya ejecutada: el hilo decodificador arranca despues de
            // esta linea, de modo que no hay peticion anterior que pueda colarse.
            long epoch = Volatile.Read(ref _seekVersion);
            _executedSeekVersion = epoch;
            _resumeAfterSeek = false;
            Volatile.Write(ref _renderActive, false);
            _decoder = decoder;
            _sourcePath = path;
            SourceFormat = decoder.Format;
            EndOfStream = false;

            _ring.Reset();
            Interlocked.Exchange(ref _renderedFrames, 0);
            Interlocked.Exchange(ref _underrunSamples, 0);
            Volatile.Write(ref _scopeWrite, 0);

            _playRequested.Reset();
            _stopRequested.Reset();

            _decodeThread = new Thread(DecodeLoop)
            {
                IsBackground = true,
                Name = "Hidra.Audio.Decode",
                // Prioridad normal: el trabajo pesado no debe competir con el hilo de audio,
                // que va por encima precisamente para no ceder nunca.
                Priority = ThreadPriority.Normal,
            };

            _decodeThread.Start();
            succeeded = true;
        }
        finally
        {
            if (!succeeded)
            {
                decoder.Dispose();
                Unload();
            }
        }
    }

    /// <summary>Descarga el archivo actual y detiene el hilo decodificador.</summary>
    public void Unload()
    {
        _stopRequested.Set();
        _playRequested.Reset();

        Thread? thread = _decodeThread;
        _decodeThread = null;

        if (thread is not null && thread.IsAlive && thread != Thread.CurrentThread)
        {
            _ = thread.Join(TimeSpan.FromSeconds(2));
        }

        _decoder?.Dispose();
        _decoder = null;

        foreach (SincResampler? resampler in _resamplers)
        {
            resampler?.Dispose();
        }

        _resamplers = [];
        _convertedScratch = [];
        _channelScratch = [];
        _decodeScratch = [];
        _outputScratch = [];
        _sourcePath = null;
        _carryFrames = 0;
        _resumeAfterSeek = false;
        Volatile.Write(ref _renderActive, false);
        EndOfStream = false;

        _ring.Reset();
        _stopRequested.Reset();
    }

    /// <summary>Arranca o reanuda la reproduccion.</summary>
    public void Play()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        if (_decoder is null)
        {
            throw new InvalidOperationException("No hay ningun archivo cargado.");
        }

        // Un archivo terminado que vuelve a reproducirse empieza de cero: reanudarlo dejaria
        // el boton de reproducir sin efecto visible.
        if (EndOfStream)
        {
            Restart();
            return;
        }

        Volatile.Write(ref _renderActive, true);
        _playRequested.Set();
    }

    /// <summary>Detiene la reproduccion conservando la posicion.</summary>
    public void Pause()
    {
        Volatile.Write(ref _renderActive, false);
        _playRequested.Reset();
    }

    /// <summary>Detiene la reproduccion y vuelve al principio del archivo.</summary>
    public void Stop()
    {
        _playRequested.Reset();

        if (_sourcePath is not null)
        {
            Restart();
        }
    }

    /// <summary>
    /// Mueve la reproduccion a la posicion indicada del archivo cargado.
    /// </summary>
    /// <remarks>
    /// <para>
    /// La peticion se ejecuta en el hilo decodificador, que es el unico dueño del lector de
    /// origen: el lector no es seguro para hilos y el hilo de audio jamas lo toca.
    /// </para>
    /// <para>
    /// Mientras se aplica, la señal de reproduccion permanece baja y el hilo de audio emite
    /// silencio sin tocar la cola: estaria consumiendo material de la posicion anterior o
    /// indices a medio publicar. Si estaba sonando, el material nuevo entra en cola y la
    /// reproduccion se reanuda sola; buscar en pausa no arranca la reproduccion por su cuenta.
    /// </para>
    /// </remarks>
    /// <param name="position">Posicion de destino dentro del archivo.</param>
    public void Seek(TimeSpan position)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        if (_decoder is null)
        {
            throw new InvalidOperationException("No hay ningun archivo cargado.");
        }

        if (position < TimeSpan.Zero)
        {
            position = TimeSpan.Zero;
        }

        // El estado de render, no el evento de bombeo, decide si tras la busqueda se sigue
        // sonando: el evento se apaga solo al llegar al fin de archivo y un salto sobre un
        // archivo ya terminado debe poder reanudarse igualmente.
        bool wasPlaying = Volatile.Read(ref _renderActive);
        Volatile.Write(ref _renderActive, false);
        _playRequested.Reset();

        Volatile.Write(ref _resumeAfterSeek, wasPlaying);
        Volatile.Write(ref _seekTargetTicks, position.Ticks);
        Volatile.Write(ref _seekVersion, Volatile.Read(ref _seekVersion) + 1);
    }

    /// <inheritdoc />
    public void Render(Span<float> destination, int channels)
    {
        int expectedChannels = Volatile.Read(ref _deviceChannels);

        if (expectedChannels == 0 || channels != expectedChannels)
        {
            destination.Clear();
            return;
        }

        // En pausa el hilo de audio emite silencio y NO toca la cola: ni la lee ni avanza
        // contadores. Es lo que hace seguro vaciarla y rellenarla durante una busqueda sin
        // candados, y de paso evita que una pausa consuma el material en cola. La señal es el
        // estado de render, no el evento de bombeo: al llegar al fin de archivo el evento se
        // apaga pero lo que queda en cola debe seguir saliendo.
        if (!Volatile.Read(ref _renderActive))
        {
            destination.Clear();
            return;
        }

        int read = _ring.Read(destination);

        if (read < destination.Length)
        {
            destination[read..].Clear();
            Interlocked.Add(ref _underrunSamples, destination.Length - read);
        }

        ApplyGain(destination, channels);
        CaptureScope(destination, channels);
        Interlocked.Add(ref _renderedFrames, destination.Length / channels);
    }

    /// <summary>
    /// Copia las muestras mas recientes ya reproducidas, mezcladas a mono, para el analizador.
    /// </summary>
    /// <remarks>
    /// La lectura no toma candados ni bloquea al hilo de audio. Puede capturar una ventana
    /// ligeramente rasgada si el hilo de audio escribe justo durante la copia; en un indicador
    /// de espectro eso es visualmente irrelevante, y a cambio el audio nunca espera.
    /// </remarks>
    public void CopyScope(Span<float> destination)
    {
        long write = Volatile.Read(ref _scopeWrite);
        int count = Math.Min(destination.Length, ScopeFrames);

        if (write < count)
        {
            destination.Clear();
            return;
        }

        long start = write - count;

        for (int i = 0; i < count; i++)
        {
            destination[i] = _scope[(int)((start + i) & ScopeMask)];
        }
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        Unload();
        _stopRequested.Dispose();
        _playRequested.Dispose();
        _ring.Dispose();
        GC.SuppressFinalize(this);
    }

    /// <summary>
    /// Decide a cuantos canales hay que entregar el material.
    /// </summary>
    /// <remarks>
    /// Solo se admiten las correspondencias directas, mono a estereo y su mezcla, porque son
    /// las que no alteran el contenido. Cualquier otra combinacion exigiria una matriz de
    /// canales, que es una decision de mezcla y no una conversion de formato.
    /// </remarks>
    private static int MapChannels(int fileChannels, int deviceChannels, string path)
    {
        if (fileChannels == deviceChannels)
        {
            return deviceChannels;
        }

        if (fileChannels == 1 && deviceChannels == 2)
        {
            return 2;
        }

        if (fileChannels == 2 && deviceChannels == 1)
        {
            return 1;
        }

        throw new NotSupportedException(
            $"El archivo '{Path.GetFileName(path)}' tiene {fileChannels} canales y el dispositivo "
            + $"esta configurado para {deviceChannels}. No hay una correspondencia directa entre ambos.");
    }

    private void Restart()
    {
        string? path = _sourcePath;

        if (path is not null)
        {
            Load(path);
        }
    }

    private void DecodeLoop()
    {
        while (!_stopRequested.Wait(0))
        {
            try
            {
                // La busqueda se atiende ANTES de mirar la señal de reproduccion: debe
                // aplicarse igual con el archivo detenido que sonando. El plazo corto de la
                // espera existe para que una busqueda recibida en pausa no espere a que
                // alguien de a play.
                if (ConsumePendingSeek())
                {
                    continue;
                }

                if (!_playRequested.Wait(50))
                {
                    continue;
                }

                // Otra pasada por si llego una busqueda mientras se esperaba: evita
                // decodificar un bloque de la posicion antigua antes de aplicar el salto.
                if (ConsumePendingSeek())
                {
                    continue;
                }

                if (!PumpOnce())
                {
                    // El lector agoto el archivo, o entrego un hueco de flujo. El fin de
                    // flujo, para quien escucha, llega cuando ADEMAS se agota lo que quedaba
                    // en cola: la decodificacion es mucho mas rapida que el tiempo real y
                    // declarar el final al agotarse el archivo dejaria medio bloque de audio
                    // por sonar y un estado "terminado" prematuro. Con un hueco sin fin de
                    // archivo, en cambio, solo toca esperar el siguiente bloque.
                    bool decoderExhausted = _decoder is null || _decoder.EndOfStream;

                    if (decoderExhausted && _ring.Count == 0)
                    {
                        EndOfStream = true;
                        Volatile.Write(ref _renderActive, false);
                        _playRequested.Reset();
                        _ = _stopRequested.Wait(50);
                    }
                    else
                    {
                        _ = _stopRequested.Wait(10);
                    }
                }
            }
            catch (Exception exception) when (exception is not OutOfMemoryException)
            {
                // El hilo decodificador no puede propagar la excepcion: dejarla escapar
                // tumbaria el proceso. Se registra y se detiene el flujo, que es lo que un
                // reproductor debe hacer ante un archivo corrupto.
                LastError = exception;
                EndOfStream = true;
                _playRequested.Reset();
            }
        }
    }

    /// <summary>
    /// Aplica la peticion de busqueda pendiente, si la hay.
    /// </summary>
    /// <remarks>
    /// Devuelve true cuando hay trabajo hecho y toca volver al bucle, lo que evita que la
    /// vuelta siguiente decodifique con la referencia de posicion todavia sin actualizar. La
    /// version que se lee es la que se ejecuta: si llego otra peticion mientras esta se
    /// aplicaba, la vuelta siguiente la recoge, y las intermedias se consolidan solas.
    /// </remarks>
    private bool ConsumePendingSeek()
    {
        long version = Volatile.Read(ref _seekVersion);

        if (version == Volatile.Read(ref _executedSeekVersion))
        {
            return false;
        }

        TimeSpan target = new(Volatile.Read(ref _seekTargetTicks));
        bool resume = Volatile.Read(ref _resumeAfterSeek);

        ApplySeek(target);
        Volatile.Write(ref _executedSeekVersion, version);

        if (resume)
        {
            // Reanudar significa reactivar las dos señales: la de bombeo para que el hilo
            // decodificador siga llenando la cola, y la de render para que el dispositivo
            // deje de emitir silencio.
            Volatile.Write(ref _renderActive, true);
            _playRequested.Set();
        }

        return true;
    }

    /// <summary>
    /// Ejecuta una busqueda: vacia la cola, reposiciona el lector y deja material nuevo
    /// delante del consumidor.
    /// </summary>
    /// <remarks>
    /// Se ejecuta SIEMPRE en el hilo decodificador, unico dueño del lector de origen. La
    /// señal de reproduccion esta baja durante toda la operacion, de modo que el hilo de
    /// audio emite silencio y no toca la cola mientras se vacia y se rellena: es lo que
    /// permite hacerlo sin candados.
    /// </remarks>
    private void ApplySeek(TimeSpan position)
    {
        _ring.Reset();
        _carryFrames = 0;
        _convertBase = 0;
        Volatile.Write(ref _scopeWrite, 0);
        EndOfStream = false;

        // El remuestreador reinicia su posicion interna; la referencia de origen de la cadena
        // de conversion vuelve a cero porque el flujo de entrada empieza en la nueva posicion.
        foreach (SincResampler? resampler in _resamplers)
        {
            resampler?.Reset();
        }

        MediaFoundationDecoder? decoder = _decoder;

        if (decoder is not null)
        {
            decoder.Seek(position);
            FillAfterSeek(position);

            // El acumulador vuelve a ser la posicion dentro del archivo: a partir de aqui,
            // Render lo avanza con el material de la nueva posicion. Durante toda la
            // operacion la señal de reproduccion esta baja, de modo que el hilo de audio no
            // entregaba material y la reescritura no compite con su avance.
            int rate = Volatile.Read(ref _deviceSampleRate);

            if (rate > 0)
            {
                Interlocked.Exchange(ref _renderedFrames, (long)(position.TotalSeconds * rate));
            }
        }
    }

    /// <summary>
    /// Rellena la cola con material de la nueva posicion antes de reanudar el render.
    /// </summary>
    /// <remarks>
    /// Sin este pre-llenado, el primer callback despues de la busqueda encontraria la cola
    /// vacia y el usuario oiria un silencio de arranque alli donde pidió continuar. El tope
    /// de fotogramas y el plazo acotan el caso de una fuente que responda con huecos de
    /// flujo indefinidamente.
    /// </remarks>
    private void FillAfterSeek(TimeSpan position)
    {
        MediaFoundationDecoder decoder = _decoder!;

        int rate = Volatile.Read(ref _deviceSampleRate);
        int channels = Volatile.Read(ref _deviceChannels);

        if (rate <= 0 || channels <= 0)
        {
            return;
        }

        int targetSamples = Math.Min(RingSamples / 2, rate * channels / 2);
        const long FrameCap = 1 << 17;
        long pumpedFrames = 0;
        long deadline = Environment.TickCount64 + 2000;

        while (pumpedFrames < FrameCap
            && _ring.Count < targetSamples
            && !_stopRequested.Wait(0)
            && Environment.TickCount64 < deadline)
        {
            int freeFrames = _ring.Free / channels;

            if (freeFrames < 64)
            {
                _ = _stopRequested.Wait(5);
                continue;
            }

            int read = decoder.Read(_decodeScratch);

            if (read < _fileChannels)
            {
                if (decoder.EndOfStream)
                {
                    break;
                }

                // Un bloque nulo sin fin de archivo es un hueco del flujo, no un error:
                // se reintenta con el siguiente bloque.
                continue;
            }

            ConvertBlock(read / _fileChannels);
            pumpedFrames += read / _fileChannels;
        }
    }

    /// <summary>Decodifica y entrega un bloque. Devuelve false cuando el archivo se acabo.</summary>
    private bool PumpOnce()
    {
        MediaFoundationDecoder decoder = _decoder!;

        // Si la cola esta llena no se decodifica nada: se espera. Escribir a medias
        // desincronizaria el entrelazado de canales.
        if (_ring.Free < _fileChannels * 64)
        {
            _ = _stopRequested.Wait(5);
            return true;
        }

        int read = decoder.Read(_decodeScratch);

        if (read < _fileChannels)
        {
            return false;
        }

        ConvertBlock(read / _fileChannels);
        return true;
    }

    /// <summary>
    /// Convierte un bloque entrelazado de origen al formato del dispositivo y lo deja en
    /// <see cref="_outputScratch"/>, tambien entrelazado.
    /// </summary>
    private void ConvertBlock(int newFrames)
    {
        int total = _carryFrames + newFrames;

        // Separar en canales, colocando el material nuevo detras de la cola arrastrada.
        for (int channel = 0; channel < _fileChannels; channel++)
        {
            float[] plane = _channelScratch[channel];

            for (int frame = 0; frame < newFrames; frame++)
            {
                plane[_carryFrames + frame] = _decodeScratch[(frame * _fileChannels) + channel];
            }
        }

        bool sameRate = _resamplers[0] is null;
        int converted;

        if (sameRate)
        {
            for (int channel = 0; channel < _fileChannels; channel++)
            {
                _channelScratch[channel].AsSpan(0, total).CopyTo(_convertedScratch[channel]);
            }

            converted = total;
            _carryFrames = 0;
        }
        else
        {
            // Todos los canales comparten la misma secuencia de posiciones, porque la relacion
            // de conversion y la posicion inicial son identicas. La cantidad consumida se
            // calcula una sola vez, con el primer canal, y se aplica a todos.
            converted = _resamplers[0]!.Process(
                _channelScratch[0].AsSpan(0, total),
                _convertBase,
                _convertedScratch[0]);

            for (int channel = 1; channel < _fileChannels; channel++)
            {
                _ = _resamplers[channel]!.Process(
                    _channelScratch[channel].AsSpan(0, total),
                    _convertBase,
                    _convertedScratch[channel]);
            }

            SincResampler first = _resamplers[0]!;
            long nextFirst = (long)Math.Floor(first.NextPosition) - SincResampler.LatencyInInputSamples;
            long consumed = Math.Clamp(nextFirst - _convertBase, 0, total);
            int carry = total - (int)consumed;

            for (int channel = 0; channel < _fileChannels; channel++)
            {
                float[] plane = _channelScratch[channel];
                Array.Copy(plane, (int)consumed, plane, 0, carry);
            }

            _convertBase += consumed;
            _carryFrames = carry;
        }

        Interleave(converted);
        WriteAll(_outputScratch.AsSpan(0, converted * _outputChannels));
    }

    /// <summary>Entrelaza los canales convertidos aplicando la correspondencia decidida.</summary>
    private void Interleave(int frames)
    {
        if (_fileChannels == _outputChannels)
        {
            for (int channel = 0; channel < _outputChannels; channel++)
            {
                float[] plane = _convertedScratch[channel];

                for (int frame = 0; frame < frames; frame++)
                {
                    _outputScratch[(frame * _outputChannels) + channel] = plane[frame];
                }
            }

            return;
        }

        if (_fileChannels == 1)
        {
            // Mono a estereo: la misma muestra a los dos canales.
            float[] mono = _convertedScratch[0];

            for (int frame = 0; frame < frames; frame++)
            {
                float value = mono[frame];
                _outputScratch[frame * 2] = value;
                _outputScratch[(frame * 2) + 1] = value;
            }

            return;
        }

        // Estereo a mono: media aritmetica. La suma directa recortaria el nivel.
        float[] left = _convertedScratch[0];
        float[] right = _convertedScratch[1];

        for (int frame = 0; frame < frames; frame++)
        {
            _outputScratch[frame] = (left[frame] + right[frame]) * 0.5f;
        }
    }

    /// <summary>Vuelca en la cola todo el bloque, esperando si esta llena.</summary>
    /// <remarks>
    /// Si la cola esta llena y hay una busqueda pendiente, el resto del bloque se descarta en
    /// el acto: la cola se va a vaciar de todos modos, y quedarse aqui esperando hueco haria
    /// que el hilo decodificador jamas volviera al inicio del bucle para ver la peticion. Ese
    /// estacionamiento es exactamente el bloqueo que aparece al buscar con la pausa activa y
    /// la cola llena, porque en pausa nadie consume y el hueco no llega nunca.
    /// </remarks>
    private void WriteAll(ReadOnlySpan<float> samples)
    {
        int offset = 0;

        while (offset < samples.Length)
        {
            int written = _ring.Write(samples[offset..]);

            if (written == 0)
            {
                if (Volatile.Read(ref _seekVersion) != Volatile.Read(ref _executedSeekVersion))
                {
                    return;
                }

                _ = _stopRequested.Wait(5);
                continue;
            }

            offset += written;
        }
    }

    private void ApplyGain(Span<float> destination, int channels)
    {
        float target = Volatile.Read(ref _targetGain);
        float current = _currentGain;
        int frames = destination.Length / channels;

        if (frames == 0)
        {
            return;
        }

        float step = (target - current) / frames;

        for (int frame = 0; frame < frames; frame++)
        {
            current += step;
            int offset = frame * channels;

            for (int channel = 0; channel < channels; channel++)
            {
                destination[offset + channel] *= current;
            }
        }

        _currentGain = target;
    }

    private void CaptureScope(Span<float> destination, int channels)
    {
        int frames = destination.Length / channels;
        long write = _scopeWrite;

        for (int frame = 0; frame < frames; frame++)
        {
            int offset = frame * channels;
            float sum = 0.0f;

            for (int channel = 0; channel < channels; channel++)
            {
                sum += destination[offset + channel];
            }

            _scope[(int)(write & ScopeMask)] = sum / channels;
            write++;
        }

        Volatile.Write(ref _scopeWrite, write);
    }
}
