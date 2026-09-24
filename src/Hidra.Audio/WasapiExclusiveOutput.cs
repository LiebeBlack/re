using System.ComponentModel;
using System.Runtime.InteropServices;
using Hidra.Kernel.Dsp;
using Hidra.Kernel.Interop;
using Hidra.Kernel.Memory;
using Windows.Win32;
using Windows.Win32.Foundation;
using Windows.Win32.Media.Audio;
using Windows.Win32.System.Com;

namespace Hidra.Audio;

/// <summary>
/// Motor de salida WASAPI en modo exclusivo con callback por evento.
/// </summary>
/// <remarks>
/// <para>
/// En modo exclusivo la aplicacion toma el dispositivo entero: nadie mas escribe en el, el
/// motor de audio del sistema no mezcla, no remuestrea y no aplica efectos. El precio es que
/// el flujo tiene que estar EXACTAMENTE en el formato nativo del dispositivo, y que el
/// dispositivo no admite dos streams exclusivos a la vez.
/// </para>
/// <para>
/// El modelo es de <b>traccion por evento</b>: el driver senaliza un objeto de evento del
/// kernel y el hilo de audio rellena lo que quede libre. No se sondea el estado ni se duerme
/// un tiempo fijo, que es lo que produce glitches cuando el reloj del dispositivo no coincide
/// exactamente con el del procesador.
/// </para>
/// <para>
/// Los tipos COM proceden de la capa generada desde los metadatos oficiales de Win32. Se
/// consume siempre a traves de punteros crudos y de la vtable, sin envoltorios administrados
/// ni marshalling en tiempo de ejecucion, que es lo que permite que esto sobreviva al AOT.
/// </para>
/// <para>
/// Se usan Identificadores de Interfaz obtenidos de los metadatos generados en lugar de
/// <c>typeof(T).GUID</c>: esa ultima forma lee el atributo Guid por reflexion, y con la
/// reflexion desactivada en la publicacion AOT el resultado no esta garantizado.
/// </para>
/// </remarks>
internal sealed unsafe class WasapiExclusiveOutput : IDisposable
{
    /// <summary>Identificador de clase del enumerador de dispositivos de audio.</summary>
    private static readonly Guid ClsidMmDeviceEnumerator = new("BCDE0395-E52F-467C-8E3D-C4579291692E");

    /// <summary>
    /// Codificaciones que se sondean, en orden de preferencia.
    /// </summary>
    /// <remarks>
    /// 24 bits enteros primero: es la profundidad nativa de la mayoria de DACs dedicados,
    /// de los HDMI de Intel y de los Realtek HDA recientes, y conserva el rango dinamico
    /// completo del material. 32 detras, para los endpoints que lo exigen; despues 16,
    /// el suelo universal; la coma flotante al final porque suele ser una comodidad del
    /// motor por software y no del hardware.
    /// </remarks>
    private static readonly SampleEncoding[] PreferredEncodings =
    [
        SampleEncoding.Pcm24,
        SampleEncoding.Pcm32,
        SampleEncoding.Float32,
        SampleEncoding.Pcm16,
    ];

    /// <summary>Codigo de error de modo de apartamento ya establecido por otro componente.</summary>
    private const int RpcChangedMode = unchecked((int)0x80010106);

    private readonly ISampleProvider _provider;
    private readonly WaitEvent _bufferReady;
    private readonly WaitEvent _stopRequested;
    private readonly Thread _renderThread;
    private readonly AlignedBuffer<float> _scratch;
    private readonly bool _ownsComApartment;
    private readonly bool _allowSharedFallback;

    // No son de solo lectura porque el reintento en modo compartido tiene que sustituir el
    // bloque de formato por el del mezclador del sistema.
    private AlignedBuffer<byte> _formatBlock;
    private AudioFormat _format;
    private AudioStreamMode _mode;

    private readonly List<string> _negotiationLog = [];
    private IAudioClient* _client;
    private IAudioRenderClient* _renderClient;
    private WAVEFORMATEX* _deviceMixFormat;
    private int _bufferFrames;
    private bool _disposed;

    /// <summary>Abre el dispositivo por defecto y arranca la reproduccion.</summary>
    /// <remarks>
    /// Si el constructor lanza, los recursos parciales se liberan aqui y no en el propio
    /// constructor: <see cref="Dispose"/> ya sabe liberar cada pieza de forma condicional,
    /// y duplicar esa logica en dos sitios es como se introducen fugas cuando una de las
    /// dos copias deja de corresponderse con la otra.
    /// </remarks>
    /// <param name="provider">Fuente de muestras.</param>
    /// <param name="targetLatency">Latencia de buffer deseada. El dispositivo puede conceder otra.</param>
    /// <param name="mode">Regimen deseado. Por defecto, exclusivo.</param>
    /// <param name="allowSharedFallback">
    /// True para reintentar en modo compartido cuando el dispositivo rechaza el exclusivo. Un
    /// reproductor que falla en lugar de degradar es peor que uno que suena con algo mas de
    /// procesamiento, de modo que el valor por defecto es reintentar.
    /// </param>
    public static WasapiExclusiveOutput Open(
        ISampleProvider provider,
        TimeSpan targetLatency,
        AudioStreamMode mode = AudioStreamMode.Exclusive,
        bool allowSharedFallback = true)
    {
        WasapiExclusiveOutput output = new(provider, targetLatency, mode, allowSharedFallback);

        // Si el arranque del hilo falla (es lo unico que puede fallar despues del
        // constructor), el objeto ya posee eventos de kernel, un cliente WASAPI y un
        // apartamento COM: hay que liberarlo aunque nunca llegara a devolverse.
        try
        {
            output.StartRenderThread();
            return output;
        }
        catch
        {
            output.Dispose();
            throw;
        }
    }

    /// <summary>Formato nativo del dispositivo, al que se ha ajustado el flujo.</summary>
    public AudioFormat Format => _format;

    /// <summary>Fotogramas del buffer concedido.</summary>
    public int BufferFrames => _bufferFrames;

    /// <summary>Contadores de ejecucion.</summary>
    public RenderStatistics Statistics { get; }

    /// <summary>
    /// Traza de la negociacion de formato, en orden.
    /// </summary>
    /// <remarks>
    /// Se construye una sola vez, durante la apertura, y solo contiene un punado de cadenas.
    /// Existe porque ante un rechazo del dispositivo la unica informacion util es QUE formato
    /// se pidio y que contesto: sin esto, un fallo de negociacion en un equipo ajeno es
    /// indistinguible de un dispositivo ausente.
    /// </remarks>
    public IReadOnlyList<string> NegotiationLog => _negotiationLog;

    /// <summary>Latencia real del buffer.</summary>
    public TimeSpan BufferDuration => TimeSpan.FromSeconds((double)_bufferFrames / _format.SampleRate);

    private WasapiExclusiveOutput(ISampleProvider provider, TimeSpan targetLatency, AudioStreamMode mode, bool allowSharedFallback)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(targetLatency.TotalMilliseconds);

        _provider = provider;
        _mode = mode;
        _allowSharedFallback = allowSharedFallback;
        Statistics = new RenderStatistics { Mode = mode };

        _bufferReady = new WaitEvent(manualReset: false, initialState: false);
        _stopRequested = new WaitEvent(manualReset: true, initialState: false);

        _ownsComApartment = EnterApartment();

        IMMDeviceEnumerator* enumerator = null;
        IMMDevice* device = null;

        try
        {
            try
            {
                enumerator = CreateDeviceEnumerator();
                enumerator->GetDefaultAudioEndpoint(EDataFlow.eRender, ERole.eMultimedia, &device);

                _client = ActivateClient(device);

                (AudioFormat negotiated, AlignedBuffer<byte> block) = NegotiateFormat(_client);
                _format = negotiated;
                _formatBlock = block;

                try
                {
                    ConfigureStream(device, targetLatency);
                }
                catch (COMException) when (_mode == AudioStreamMode.Exclusive && _allowSharedFallback)
                {
                    // El modo exclusivo no siempre esta disponible: otro reproductor puede
                    // tener el dispositivo tomado, o el driver puede no admitirlo. Degradar a
                    // compartido deja la aplicacion sonando en lugar de devolver un error.
                    _negotiationLog.Add("el modo exclusivo no esta disponible: se reintenta en modo compartido");

                    if (_client is not null)
                    {
                        _ = _client->Release();
                        _client = null;
                    }

                    _formatBlock?.Dispose();

                    _mode = AudioStreamMode.Shared;
                    Statistics.Mode = AudioStreamMode.Shared;
                    _client = ActivateClient(device);

                    (AudioFormat sharedFormat, AlignedBuffer<byte> sharedBlock) = NegotiateFormat(_client);
                    _format = sharedFormat;
                    _formatBlock = sharedBlock;

                    ConfigureStream(device, targetLatency);
                }
            }
            catch (COMException exception)
            {
                // Si falla despues de activar el cliente hay que liberarlo: dejarlo vivo
                // mantendria el endpoint bloqueado y el siguente intento fallaria igual.
                ReleaseResourcesAfterFailure();

                // Reempaquetar la excepcion conserva la causa original, que es lo que la
                // capa de interfaz muestra; WasapiException expone el HRESULT sin tocar.
                throw new WasapiException(
                    $"{exception.Message} Traza de negociacion: {string.Join(" | ", _negotiationLog)}",
                    exception.HResult,
                    exception);
            }
            catch
            {
                // Un fallo que no es COMException (la excepcion propia WasapiException de los
                // reintentos agotados, o un formato del mezclador desconocido) tambien deja
                // cliente, bloque de formato y eventos vivos: sin esta clausula escaparian
                // todos y el endpoint quedaria bloqueado hasta cerrar el proceso.
                ReleaseResourcesAfterFailure();
                throw;
            }
            finally
            {
                // Se libera al final del todo porque el reintento en modo compartido necesita
                // volver a leer el bloque del mezclador.
                PInvoke.CoTaskMemFree(_deviceMixFormat);
                _deviceMixFormat = null;
            }
        }
        finally
        {
            if (device is not null)
            {
                _ = device->Release();
            }

            if (enumerator is not null)
            {
                _ = enumerator->Release();
            }
        }

        // En modo flotante no se usa la memoria intermedia: la fuente escribe directo sobre
        // el buffer del dispositivo. El buffer de cero elementos es solo para que Dispose
        // tenga siempre un objeto valido que liberar.
        _scratch = _format.IsFloat ? new AlignedBuffer<float>(0) : new AlignedBuffer<float>(_bufferFrames * _format.Channels);

        Statistics.BufferFrames = _bufferFrames;
        Statistics.SampleRate = _format.SampleRate;

        _renderThread = new Thread(RenderLoop)
        {
            IsBackground = true,
            Name = "Hidra.Audio.Output",
            // Prioridad elevada como red de seguridad: si MMCSS no esta disponible, el hilo
            // todavia tiene que ganarle la CPU al trabajo normal. No se usa Highest porque la
            // clase multimedia ya reparte la cuota y subir mas solo perjudica al resto.
            Priority = ThreadPriority.AboveNormal,
        };
    }

    /// <summary>
    /// Libera todo lo que se haya podido adquirir antes de un fallo de apertura.
    /// </summary>
    /// <remarks>
    /// Solo se invoca desde el constructor: si la apertura falla, la instancia nunca llega
    /// a escapar y nadie mas llamara a <see cref="Dispose"/>, de modo que aqui se libera
    /// TODO, eventos de kernel y apartamento COM incluidos. Desinicializar dos veces el
    /// apartamento de un hilo corrompe el recuento de referencias COM del proceso, y el
    /// unico modo de evitarlo es que exista un solo limpiador por camino.
    /// </remarks>
    private void ReleaseResourcesAfterFailure()
    {
        if (_client is not null)
        {
            _ = _client->Release();
            _client = null;
        }

        // El doble Dispose no existe: los eventos y el bloque de formato son idempotentes,
        // y el campo no se anula porque su declaracion no admite null y estos dos limpiadores
        // nunca se ejecutan sobre la misma instancia.
        _formatBlock?.Dispose();
        _bufferReady.Dispose();
        _stopRequested.Dispose();

        if (_ownsComApartment)
        {
            PInvoke.CoUninitialize();
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

        _stopRequested.Set();
        if (_renderThread.IsAlive)
        {
            _ = _renderThread.Join(TimeSpan.FromSeconds(2));
        }

        if (_client is not null)
        {
            try
            {
                _client->Stop();
            }
            catch (COMException)
            {
                // Detener un flujo cuyo dispositivo desaparecio no es un fallo recuperable ni
                // relevante: la liberacion de abajo es lo que importa.
            }
        }

        if (_renderClient is not null)
        {
            _ = _renderClient->Release();
            _renderClient = null;
        }

        if (_client is not null)
        {
            _ = _client->Release();
            _client = null;
        }

        _bufferReady.Dispose();
        _stopRequested.Dispose();
        _formatBlock.Dispose();
        _scratch.Dispose();

        if (_ownsComApartment)
        {
            PInvoke.CoUninitialize();
        }

        GC.SuppressFinalize(this);
    }

    /// <summary>
    /// Identificador de interfaz tomado de los metadatos generados.
    /// </summary>
    private static ref readonly Guid IidOf<T>()
        where T : unmanaged, IComIID => ref T.Guid;

    private static bool IsHResult(COMException exception, HRESULT expected) =>
        exception.HResult == expected.Value;

    private static bool EnterApartment()
    {
        HRESULT result = PInvoke.CoInitializeEx(null, COINIT.COINIT_MULTITHREADED);

        // S_FALSE significa que el apartamento ya estaba inicializado por este hilo, y es
        // correcto. RPC_E_CHANGED_MODE significa que otro componente lo dejo en apartamento
        // de un solo hilo: se puede seguir usando COM, pero no hay que desinicializarlo.
        return result.Succeeded && result.Value != 1;
    }

    private static IMMDeviceEnumerator* CreateDeviceEnumerator()
    {
        Guid classId = ClsidMmDeviceEnumerator;
        Guid interfaceId = IidOf<IMMDeviceEnumerator>();
        void* instance = null;

        HRESULT result = PInvoke.CoCreateInstance(&classId, null, CLSCTX.CLSCTX_ALL, &interfaceId, &instance);
        result.ThrowOnFailure();

        return (IMMDeviceEnumerator*)instance;
    }

    private static IAudioClient* ActivateClient(IMMDevice* device)
    {
        device->Activate(IidOf<IAudioClient>(), CLSCTX.CLSCTX_ALL, null, out void* instance);
        return (IAudioClient*)instance;
    }

    private WAVEFORMATEX* ReadNativeFormat(IAudioClient* client)
    {
        client->GetMixFormat(out WAVEFORMATEX* format);
        return format;
    }

    /// <summary>
    /// Decide en que formato acepta el dispositivo un flujo en modo exclusivo.
    /// </summary>
    /// <remarks>
    /// <para>
    /// El bloque que devuelve <c>GetMixFormat</c> describe el MEZCLADOR del sistema, no el
    /// hardware. Aporta dos datos que si son del dispositivo, la frecuencia de muestreo y el
    /// numero de canales, pero la codificacion de las muestras la elige el motor de audio para
    /// su propia comodidad, casi siempre coma flotante. En modo exclusivo ese bloque no tiene
    /// ninguna obligacion de ser valido, y de hecho lo habitual es que el dispositivo lo
    /// rechace con <c>AUDCLNT_E_UNSUPPORTED_FORMAT</c>.
    /// </para>
    /// <para>
    /// Por eso se conservan frecuencia y canales y se sondean las codificaciones que el
    /// hardware puede admitir de verdad. El orden empieza por la profundidad de bits mas
    /// habitual en un convertidor dedicado, sigue por la universal de 16 bits y deja la coma
    /// flotante al final, que es justo la que suele requerir un motor de audio por software.
    /// </para>
    /// </remarks>
    private (AudioFormat Format, AlignedBuffer<byte> Block) NegotiateFormat(IAudioClient* client)
    {
        if (_deviceMixFormat is not null)
        {
            PInvoke.CoTaskMemFree(_deviceMixFormat);
            _deviceMixFormat = null;
        }

        _deviceMixFormat = ReadNativeFormat(client);

        _negotiationLog.Add(
            $"mezclador del sistema: etiqueta=0x{_deviceMixFormat->wFormatTag:X4} "
            + $"bits={_deviceMixFormat->wBitsPerSample} canales={_deviceMixFormat->nChannels} "
            + $"frecuencia={_deviceMixFormat->nSamplesPerSec} extension={_deviceMixFormat->cbSize}");

        if (!WaveFormatBridge.TryRead(_deviceMixFormat, out AudioFormat baseFormat))
        {
            throw new NotSupportedException(
                "El dispositivo declara un formato de mezcla que el motor no sabe interpretar.");
        }

        _negotiationLog.Add($"dispositivo interpretado como: {baseFormat}");

        if (_mode == AudioStreamMode.Shared)
        {
            // En modo compartido el formato del mezclador no es una sugerencia: es el unico
            // que el motor acepta, y ademas es el correcto porque el propio motor hace la
            // conversion desde ahi hasta el hardware.
            _negotiationLog.Add("modo compartido: se usa el bloque del mezclador tal cual");

            int sharedSize = WaveFormatBridge.BlockSize(_deviceMixFormat);
            AlignedBuffer<byte> sharedBlock = new(sharedSize);
            Buffer.MemoryCopy(_deviceMixFormat, sharedBlock.Pointer, sharedSize, sharedSize);

            return (baseFormat, sharedBlock);
        }

        foreach (SampleEncoding encoding in PreferredEncodings)
        {
            AudioFormat candidate = new(baseFormat.SampleRate, baseFormat.Channels, encoding, baseFormat.ChannelMask);
            AlignedBuffer<byte> block = BuildFormatBlock(candidate);

            if (IsExclusiveFormatSupported(client, block))
            {
                _negotiationLog.Add($"exclusivo aceptado: {candidate}");
                Statistics.FormatNegotiatedByProbing = candidate != baseFormat;
                return (candidate, block);
            }

            _negotiationLog.Add($"exclusivo rechazado: {candidate}");
            block.Dispose();
        }

        // Ninguna codificacion sondeada fue aceptada. Como ultimo recurso se intenta con el
        // bloque del mezclador tal cual, porque hay motores que solo admiten exactamente ese.
        int size = WaveFormatBridge.BlockSize(_deviceMixFormat);
        AlignedBuffer<byte> fallback = new(size);
        Buffer.MemoryCopy(_deviceMixFormat, fallback.Pointer, size, size);

        _negotiationLog.Add($"ningun candidato aceptado; se usa el bloque del mezclador tal cual ({size} bytes)");
        Statistics.FormatNegotiatedByProbing = false;
        return (baseFormat, fallback);
    }

    private static AlignedBuffer<byte> BuildFormatBlock(in AudioFormat format)
    {
        AlignedBuffer<byte> block = new(sizeof(WAVEFORMATEXTENSIBLE));
        WaveFormatBridge.Write(format, (WAVEFORMATEXTENSIBLE*)block.Pointer);
        return block;
    }

    /// <summary>
    /// Pregunta al dispositivo si admite el formato dado en modo exclusivo.
    /// </summary>
    /// <remarks>
    /// El bloque se pasa por su DIRECCION, no por valor: se entrega un puntero al inicio del
    /// bloque extensible completo. Copiarlo a un <c>WAVEFORMATEX</c> de 18 bytes haria que el
    /// motor leyera los 22 bytes de extension mas alla del final.
    /// </remarks>
    private static bool IsExclusiveFormatSupported(IAudioClient* client, AlignedBuffer<byte> block)
    {
        WAVEFORMATEX* format = (WAVEFORMATEX*)block.Pointer;

        try
        {
            client->IsFormatSupported(AUDCLNT_SHAREMODE.AUDCLNT_SHAREMODE_EXCLUSIVE, *format, out WAVEFORMATEX* closestMatch);

            // En modo exclusivo el metodo no propone alternativas: o acepta el formato pedido
            // o devuelve error. La liberacion es defensiva.
            if (closestMatch is not null)
            {
                PInvoke.CoTaskMemFree(closestMatch);
            }

            return true;
        }
        catch (COMException)
        {
            return false;
        }
    }

    /// <summary>
    /// Obtiene el cliente de render del flujo.
    /// </summary>
    /// <remarks>
    /// Se usa <c>GetService</c> y NO <c>QueryInterface</c>. La diferencia no es cosmetica: las
    /// interfaces de servicio de WASAPI no se anuncian a traves de QueryInterface, de modo que
    /// preguntar por ellas por esa via falla aunque el objeto las implemente. Es un error facil
    /// de cometer porque para las interfaces derivadas, como IAudioClient2, QueryInterface si
    /// es el camino correcto.
    /// </remarks>
    private static IAudioRenderClient* GetRenderClient(IAudioClient* client)
    {
        try
        {
            client->GetService(out IAudioRenderClient* service);
            return service;
        }
        catch (COMException)
        {
            return null;
        }
    }

    /// <summary>
    /// Consulta una interfaz sobre un objeto COM existente.
    /// </summary>
    private static bool TryQueryInterface<T>(void* source, out T* result)
        where T : unmanaged, IComIID
    {
        result = null;

        Guid interfaceId = IidOf<T>();
        void* instance = null;

        // Cualquier objeto COM empieza por IUnknown, de modo que su vtable sirve para
        // preguntar por el resto de interfaces.
        HRESULT call = ((IUnknown*)source)->QueryInterface(&interfaceId, &instance);
        if (call.Failed)
        {
            return false;
        }

        result = (T*)instance;
        return true;
    }

    /// <summary>
    /// Inicializa el flujo y absorbe las dos negociaciones que el dispositivo puede exigir.
    /// </summary>
    /// <remarks>
    /// Son dos rechazos de naturaleza distinta y hay que tratarlos por separado:
    /// <list type="bullet">
    /// <item>La <b>desalineacion de buffer</b> no viene de un formato invalido sino de que el
    /// motor redondea la duracion pedida a su periodo. Se responde pidiendo la duracion que
    /// corresponde al tamano que el dispositivo habria concedido.</item>
    /// <item>El rechazo por <b>flujo sin procesar no soportado</b> tampoco viene del formato:
    /// llega aqui, en la inicializacion, y no al solicitar la opcion. Un driver que no
    /// implementa el modo crudo acepta la peticion y luego rechaza el flujo, de modo que el
    /// unico tratamiento posible es reintentar sin la opcion.</item>
    /// </list>
    /// </remarks>
    private void ConfigureStream(IMMDevice* device, TimeSpan targetLatency)
    {
        // En modo compartido la opcion de flujo sin procesar no existe y pedirla hace fallar
        // la inicializacion.
        bool rawRequested = _mode == AudioStreamMode.Exclusive && ApplyRawStreamOption(_client);
        long duration = ReferenceTime.FromTimeSpan(targetLatency);

        if (_mode == AudioStreamMode.Shared)
        {
            // En modo compartido la duracion no puede quedar por debajo del periodo del
            // dispositivo, y tiene que ser multiplo suyo; el motor redondea el resto y avisa
            // con la desalineacion, que ya se trata mas abajo.
            _client->GetDevicePeriod(out long defaultPeriod, out _);
            duration = Math.Max(duration, defaultPeriod);
            _negotiationLog.Add($"modo compartido: periodo del dispositivo {ReferenceTime.ToMilliseconds(defaultPeriod):F3} ms; se piden {ReferenceTime.ToMilliseconds(duration):F3} ms");
        }

        bool initialized = false;

        for (int attempt = 0; attempt < 4 && !initialized; attempt++)
        {
            try
            {
                InitializeStream(duration);
                initialized = true;
                Statistics.UsingRawStream = rawRequested;
            }
            catch (COMException exception) when (IsHResult(exception, HRESULT.AUDCLNT_E_BUFFER_SIZE_NOT_ALIGNED))
            {
                _client->GetBufferSize(out uint granted);
                duration = ReferenceTime.FromFrames(granted, _format.SampleRate);
                Statistics.RealignedBuffer = true;

                _negotiationLog.Add($"buffer desalineado: se reintenta pidiendo {granted} fotogramas, que equivalen a {ReferenceTime.ToMilliseconds(duration):F3} ms");

                Reactivate(device, rawRequested);
            }
            catch (COMException exception) when (IsHResult(exception, HRESULT.AUDCLNT_E_UNSUPPORTED_FORMAT) && rawRequested)
            {
                rawRequested = false;
                Statistics.UsingRawStream = false;

                _negotiationLog.Add("el driver no admite el flujo sin procesar: se reintenta con el procesamiento normal");

                Reactivate(device, rawRequested: false);
            }
        }

        if (!initialized)
        {
            throw new WasapiException(
                "El dispositivo rechazo el flujo en modo exclusivo tras agotar los reintentos. "
                + $"Traza: {string.Join(" | ", _negotiationLog)}",
                HRESULT.AUDCLNT_E_UNSUPPORTED_FORMAT.Value);
        }

        _negotiationLog.Add($"flujo inicializado: {_format}, buffer de la peticion {ReferenceTime.ToMilliseconds(duration):F3} ms");

        _client->SetEventHandle(new HANDLE(_bufferReady.Handle));
        _client->GetBufferSize(out uint bufferFrames);
        _bufferFrames = (int)bufferFrames;

        _renderClient = GetRenderClient(_client);
        if (_renderClient is null)
        {
            throw new NotSupportedException("El dispositivo no expone la interfaz de cliente de render.");
        }

        _client->Start();
    }

    /// <summary>
    /// Suelta el cliente y activa uno nuevo, que es la unica forma de poder volver a
    /// inicializar.
    /// </summary>
    /// <remarks>
    /// <c>Initialize</c> solo puede invocarse una vez por cliente, incluso cuando falla. La
    /// opcion de flujo sin procesar pertenece al cliente y no al dispositivo, de modo que hay
    /// que volver a aplicarla si se quiere seguir usandola.
    /// </remarks>
    private void Reactivate(IMMDevice* device, bool rawRequested)
    {
        _ = _client->Release();
        _client = ActivateClient(device);

        if (rawRequested)
        {
            _ = ApplyRawStreamOption(_client);
        }
    }

    private void InitializeStream(long duration)
    {
        WAVEFORMATEX* format = (WAVEFORMATEX*)_formatBlock.Pointer;

        // hnsPeriodicity es cero: el motor se queda con la periodicidad del dispositivo.
        _client->Initialize(
            _mode == AudioStreamMode.Exclusive
                ? AUDCLNT_SHAREMODE.AUDCLNT_SHAREMODE_EXCLUSIVE
                : AUDCLNT_SHAREMODE.AUDCLNT_SHAREMODE_SHARED,
            PInvoke.AUDCLNT_STREAMFLAGS_EVENTCALLBACK,
            duration,
            0,
            format,
            null);
    }

    /// <summary>
    /// Pide un flujo sin procesar por el motor de audio.
    /// </summary>
    /// <remarks>
    /// Es una optimizacion, no un requisito: si el dispositivo o el driver no la admiten, la
    /// reproduccion sigue con normalidad y solo se pierde la garantia de que el sistema no
    /// inserte efectos. Que la peticion se acepte aqui NO significa que el flujo vaya a
    /// inicializarse: un driver que no implementa el modo crudo acepta la opcion y rechaza
    /// despues la inicializacion. Por eso esta funcion solo informa de que se pidio, y quien
    /// decide si esta activo es la inicializacion del flujo.
    /// </remarks>
    private static bool ApplyRawStreamOption(IAudioClient* client)
    {
        if (!TryQueryInterface(client, out IAudioClient2* client2))
        {
            return false;
        }

        try
        {
            AudioClientProperties properties = default;
            properties.cbSize = (uint)sizeof(AudioClientProperties);
            properties.bIsOffload = false;
            properties.eCategory = AUDIO_STREAM_CATEGORY.AudioCategory_Media;
            properties.Options = AUDCLNT_STREAMOPTIONS.AUDCLNT_STREAMOPTIONS_RAW;

            client2->SetClientProperties(properties);
            return true;
        }
        catch (COMException)
        {
            return false;
        }
        finally
        {
            _ = client2->Release();
        }
    }

    private void StartRenderThread() => _renderThread.Start();

    private void RenderLoop()
    {
        // El hilo de audio tambien necesita su apartamento COM: los punteros de WASAPI son
        // agiles, pero el apartamento debe declararse antes de usarlos desde otro hilo.
        // S_FALSE significa que ESTE hilo ya lo tenia inicializado: el recuento quedo en
        // el del llamador previo, y revertirlo aqui dejaria el hilo sin apartamento para
        // quien venga despues. RPC_E_CHANGED_MODE significa que otro componente lo dejo en
        // apartamento de un solo hilo: se puede seguir usando COM, pero no es nuestro.
        HRESULT apartment = PInvoke.CoInitializeEx(null, COINIT.COINIT_MULTITHREADED);
        bool ownsApartment = apartment.Succeeded && apartment.Value != 1;

        // FTZ/DAZ antes del primer bloque: los desvanecimientos de volumen y las colas del
        // remuestreador producen denormales con naturalidad, y cada una cuesta cerca de
        // cien ciclos en microcodigo. Con los bits puestos, el hardware las flusha en un
        // ciclo. Se restaura al salir para no contaminar al resto del proceso.
        uint savedControlWord = Kernel32.EnableFtzDaz();

        try
        {
            using (MmcssScope multimedia = MmcssScope.Enter())
            {
                Statistics.UsingMultimediaClass = multimedia.IsActive;

                while (!_stopRequested.Wait(0))
                {
                    // El plazo es una red de seguridad: si el driver deja de senalizar, el
                    // bucle vuelve a comprobar la parada en lugar de quedarse colgado.
                    if (!_bufferReady.Wait(1000))
                    {
                        Statistics.WaitTimeouts++;
                        continue;
                    }

                    try
                    {
                        FillBuffer();
                    }
                    catch (COMException exception) when (IsHResult(exception, HRESULT.AUDCLNT_E_DEVICE_INVALIDATED))
                    {
                        Statistics.DeviceInvalidated = true;
                        break;
                    }
                }
            }
        }
        finally
        {
            // Solo se desinicializa lo que este hilo inicializo: es exactamente el mismo
            // criterio que aplica EnterApartment para el hilo de apertura.
            if (ownsApartment)
            {
                PInvoke.CoUninitialize();
            }

            Kernel32.RestoreControlWord(savedControlWord);
        }
    }

    private void FillBuffer()
    {
        _client->GetCurrentPadding(out uint padding);

        int available = _bufferFrames - (int)padding;
        if (available <= 0)
        {
            Statistics.EmptyCallbacks++;
            return;
        }

        _renderClient->GetBuffer((uint)available, out byte* destination);
        int samples = available * _format.Channels;

        try
        {
            if (_format.IsFloat)
            {
                // El formato del dispositivo es el que usan las fuentes: se escribe directo,
                // sin copia intermedia.
                _provider.Render(new Span<float>(destination, samples), _format.Channels);
            }
            else
            {
                Span<float> scratch = _scratch.Span[..samples];
                _provider.Render(scratch, _format.Channels);

                // Modo transparente: la fuente ya viaja sin alteracion y el volumen esta a
                // la unidad. Ni limitador ni recorte: tocar la muestra aqui romperia la
                // garantia bit a bit que el estado declara. Con volumen distinto de uno la
                // rampa de ganancia altera las muestras y el limitador vuelve a aplicar.
                bool transparent = _provider is PlaybackPipeline { IsBitPerfectPassthrough: true }
                    && ((PlaybackPipeline)_provider).Volume == 1.0;

                if (!transparent)
                {
                    // Limitador de rodilla suave en lugar de recorte duro: los picos entre
                    // muestras se comprimen con tangente hiperbolica por encima de -0.1
                    // dBFS y el resto de la senal pasa intacta.
                    SampleConverter.SoftLimit(scratch, scratch);
                }

                int bytes = SampleConverter.BytesFor(samples, _format.Encoding);
                SampleConverter.FromClampedFloat(scratch, new Span<byte>(destination, bytes), _format.Encoding);
            }
        }
        finally
        {
            _renderClient->ReleaseBuffer((uint)available, 0);
        }

        Statistics.FramesRendered += available;
        Statistics.Callbacks++;
        Statistics.LastAvailableFrames = available;
    }
}
