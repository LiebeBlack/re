using System.Runtime.InteropServices;
using Hidra.Kernel.Dsp;
using Windows.Win32;
using Windows.Win32.Foundation;
using Windows.Win32.Media.MediaFoundation;
using Windows.Win32.System.Com.StructuredStorage;
using Windows.Win32.System.Variant;

namespace Hidra.Audio;

/// <summary>
/// Decodificador de audio apoyado en el lector de origen de Media Foundation.
/// </summary>
/// <remarks>
/// <para>
/// Se usa Media Foundation en lugar de un decodificador propio porque aporta, sin ninguna
/// dependencia adicional, todos los formatos que el sistema ya sabe leer: PCM, MP3, AAC, WMA y,
/// desde Windows 10, tambien FLAC. Escribir esos decodificadores a mano no aportaria nada al
/// problema que se esta resolviendo.
/// </para>
/// <para>
/// La conversion a coma flotante la hace el propio sistema: se le pide al lector que entregue
/// muestras de 32 bits en coma flotante y el se encarga de convertir desde el formato del
/// archivo. Asi el resto de la cadena solo trata un formato, y el tramado y la conversion a
/// enteros quedan en un unico sitio: la salida.
/// </para>
/// <para>
/// Este tipo NO es seguro para el hilo de audio: reserva y libera memoria al pedir buffers.
/// Su consumidor natural es un hilo decodificador que alimente una cola.
/// </para>
/// </remarks>
internal sealed unsafe class MediaFoundationDecoder : IDisposable
{
    private static readonly Lock StartupGate = new();
    private static int _activeDecoders;

    private readonly IMFSourceReader* _reader;
    private IMFMediaBuffer* _buffer;
    private byte* _bufferData;
    private int _bufferLength;
    private int _bufferOffset;
    private bool _endOfStream;
    private bool _disposed;

    private MediaFoundationDecoder(IMFSourceReader* reader, AudioFormat format, TimeSpan? duration)
    {
        _reader = reader;
        Format = format;
        Duration = duration;
    }

    /// <summary>Formato de las muestras que entrega el decodificador.</summary>
    public AudioFormat Format { get; }

    /// <summary>True cuando ya no queda material por leer.</summary>
    public bool EndOfStream => _endOfStream;

    /// <summary>
    /// Duracion total declarada por la fuente, o null cuando el origen no la informa.
    /// </summary>
    public TimeSpan? Duration { get; private set; }

    /// <summary>Abre un archivo de audio y prepara la entrega en coma flotante.</summary>
    /// <param name="path">Ruta del archivo.</param>
    public static MediaFoundationDecoder Open(string path)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);

        if (!File.Exists(path))
        {
            throw new FileNotFoundException("No se encontro el archivo de audio.", path);
        }

        EnterStartup();

        IMFSourceReader* reader = null;

        try
        {
            // El segundo parametro son atributos opcionales del lector; ninguno hace falta.
            PInvoke.MFCreateSourceReaderFromURL(path, null, &reader).ThrowOnFailure();

            RequestFloatOutput(reader);

            AudioFormat format = ReadFormat(reader);
            TimeSpan? duration = TryReadDuration(reader);

            return new MediaFoundationDecoder(reader, format, duration);
        }
        catch
        {
            if (reader is not null)
            {
                _ = reader->Release();
            }

            ExitStartup();
            throw;
        }
    }

    /// <summary>
    /// Lee hasta llenar el destino. Devuelve el numero de MUESTRAS escritas, que puede ser menor
    /// al pedido cuando el archivo se acaba.
    /// </summary>
    public int Read(Span<float> destination)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        if (destination.IsEmpty)
        {
            return 0;
        }

        int written = 0;

        fixed (float* target = destination)
        {
            while (written < destination.Length)
            {
                if (_bufferOffset >= _bufferLength && !FillBuffer())
                {
                    break;
                }

                int available = _bufferLength - _bufferOffset;
                int take = Math.Min(available, destination.Length - written);

                // El puntero base es de bytes, porque es lo que devuelve Lock, pero el
                // desplazamiento esta en MUESTRAS. Hay que convertirlo antes de sumarlo: si se
                // suma tal cual, el avance es de un byte por muestra y la lectura devuelve una
                // vista desplazada del bloque que ademas se sale de el en cuanto el
                // desplazamiento acumulado supera su tamano.
                Buffer.MemoryCopy(
                    ((float*)_bufferData) + _bufferOffset,
                    target + written,
                    (long)take * sizeof(float),
                    (long)take * sizeof(float));

                _bufferOffset += take;
                written += take;
            }
        }

        return written;
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        ReleaseBuffer();

        if (_reader is not null)
        {
            _ = _reader->Release();
        }

        ExitStartup();
        GC.SuppressFinalize(this);
    }

    private static void EnterStartup()
    {
        lock (StartupGate)
        {
            if (_activeDecoders == 0)
            {
                PInvoke.MFStartup(PInvoke.MF_VERSION, 0).ThrowOnFailure();
            }

            _activeDecoders++;
        }
    }

    private static void ExitStartup()
    {
        lock (StartupGate)
        {
            _activeDecoders--;

            if (_activeDecoders == 0)
            {
                _ = PInvoke.MFShutdown();
            }
        }
    }

    /// <summary>
    /// Pide al lector que entregue coma flotante de 32 bits en lugar del formato del archivo.
    /// </summary>
    private static void RequestFloatOutput(IMFSourceReader* reader)
    {
        IMFMediaType* target = null;

        try
        {
            PInvoke.MFCreateMediaType(&target).ThrowOnFailure();

            target->SetGUID(PInvoke.MF_MT_MAJOR_TYPE, PInvoke.MFMediaType_Audio);
            target->SetGUID(PInvoke.MF_MT_SUBTYPE, PInvoke.MFAudioFormat_Float);

            // El segundo parametro es reservado y debe ir a null; el tercero es el tipo deseado.
            reader->SetCurrentMediaType(
                unchecked((uint)MF_SOURCE_READER_CONSTANTS.MF_SOURCE_READER_FIRST_AUDIO_STREAM),
                null,
                target);
        }
        finally
        {
            if (target is not null)
            {
                _ = target->Release();
            }
        }
    }

    private static AudioFormat ReadFormat(IMFSourceReader* reader)
    {
        IMFMediaType* current = null;

        try
        {
            uint streamIndex = unchecked((uint)MF_SOURCE_READER_CONSTANTS.MF_SOURCE_READER_FIRST_AUDIO_STREAM);
            reader->GetCurrentMediaType(streamIndex, &current);

            current->GetUINT32(PInvoke.MF_MT_AUDIO_NUM_CHANNELS, out uint channels);
            current->GetUINT32(PInvoke.MF_MT_AUDIO_SAMPLES_PER_SECOND, out uint sampleRate);

            if (channels == 0 || sampleRate == 0)
            {
                throw new NotSupportedException("El archivo no declara un formato de audio utilizable.");
            }

            // El lector ya convierte a coma flotante, de modo que la profundidad de bits es la
            // del contenedor que se pidio, no la del archivo original.
            return new AudioFormat((int)sampleRate, (int)channels, SampleEncoding.Float32);
        }
        finally
        {
            if (current is not null)
            {
                _ = current->Release();
            }
        }
    }

    /// <summary>
    /// Pregunta a la fuente por su duracion.
    /// </summary>
    /// <remarks>
    /// Es un atributo OPCIONAL: algunos originales no lo implementan y la consulta falla, de
    /// modo que una ausencia no es un error del decodificador sino una caracteristica del
    /// origen. Por eso la consulta se hace por el origen de medios y no por el flujo: la
    /// duracion es una propiedad del archivo entero, no de una pista concreta.
    /// </remarks>
    private static TimeSpan? TryReadDuration(IMFSourceReader* reader)
    {
        try
        {
            uint mediaSource = unchecked((uint)MF_SOURCE_READER_CONSTANTS.MF_SOURCE_READER_MEDIASOURCE);
            reader->GetPresentationAttribute(mediaSource, PInvoke.MF_PD_DURATION, out PROPVARIANT value);

            try
            {
                if (value.vt == VARENUM.VT_I8)
                {
                    // Media Foundation y TimeSpan miden en unidades de cien nanosegundos.
                    long ticks = value.hVal;
                    return ticks > 0 ? TimeSpan.FromTicks(ticks) : null;
                }
            }
            finally
            {
                _ = PInvoke.PropVariantClear(ref value);
            }
        }
        catch (COMException)
        {
            // La fuente no declara duracion.
        }

        return null;
    }

    /// <summary>
    /// Mueve la posicion de lectura del flujo.
    /// </summary>
    /// <remarks>
    /// <para>
    /// El flujo se vacia ANTES de pedir la nueva posicion: una busqueda sobre un lector con
    /// material en cola no invalida los bloques ya entregados, y sin el vaciado el primer
    /// bloque despues de la busqueda seguiria siendo material del punto anterior.
    /// </para>
    /// <para>
    /// La posicion se expresa en unidades de cien nanosegundos con el formato de tiempo
    /// GUID_NULL, que es el que todas las fuentes de audio aceptan sin negociacion. El
    /// PROPVARIANT se limpia SIEMPRE: un variant de tipo entero no reserva memoria, pero el
    /// contrato de la funcion exige liberarlo y saltarse la limpieza con tipos que si la
    /// necesitan es una fuga garantizada.
    /// </para>
    /// </remarks>
    public void Seek(TimeSpan position)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        uint streamIndex = unchecked((uint)MF_SOURCE_READER_CONSTANTS.MF_SOURCE_READER_FIRST_AUDIO_STREAM);

        ReleaseBuffer();
        _reader->Flush(streamIndex);

        PROPVARIANT target = default;
        target.vt = VARENUM.VT_I8;
        target.hVal = position.Ticks;

        try
        {
            _reader->SetCurrentPosition(Guid.Empty, in target);
        }
        finally
        {
            _ = PInvoke.PropVariantClear(ref target);
        }

        _endOfStream = false;
    }

    /// <summary>Pide el siguiente bloque al lector y lo deja listo para copiar.</summary>
    /// <returns>True cuando hay datos nuevos disponibles.</returns>
    private bool FillBuffer()
    {
        ReleaseBuffer();

        if (_endOfStream)
        {
            return false;
        }

        IMFSample* sample = null;

        try
        {
            uint streamIndex = unchecked((uint)MF_SOURCE_READER_CONSTANTS.MF_SOURCE_READER_FIRST_AUDIO_STREAM);

            _reader->ReadSample(
                streamIndex,
                0,
                out uint _,
                out uint rawFlags,
                out long _,
                &sample);

            // El valor de fin de flujo es 0x2, no 0x1. Confundirlos hace que el reproductor
            // trate el final del archivo como un error y se detenga un bloque antes, que es
            // exactamente el tipo de detalle que no se nota hasta que se nota.
            if ((rawFlags & (uint)MF_SOURCE_READER_FLAG.MF_SOURCE_READERF_ENDOFSTREAM) != 0)
            {
                _endOfStream = true;
                return false;
            }

            if ((rawFlags & (uint)MF_SOURCE_READER_FLAG.MF_SOURCE_READERF_ERROR) != 0)
            {
                _endOfStream = true;
                return false;
            }

            // Un bloque nulo sin fin de archivo es un hueco del flujo, no un error: se descarta.
            if (sample is null)
            {
                return false;
            }

            IMFMediaBuffer* buffer = null;
            sample->ConvertToContiguousBuffer(&buffer);

            try
            {
                // El bloque de Media Foundation se bloquea para leerlo y hay que soltarlo
                // antes de liberar el objeto; de ahi que el puntero de datos y el objeto se
                // guarden juntos y se liberen juntos en ReleaseBuffer.
                buffer->Lock(out byte* data, out uint _, out uint currentLength);
                _buffer = buffer;
                _bufferData = data;

                // La longitud que devuelve Lock esta en BYTES, no en muestras. Tratarla como
                // numero de muestras hace que la lectura avance cuatro veces mas de lo que el
                // bloque contiene en cada vuelta: se lee memoria ajena al bloque, aparecen
                // valores basura en la senal y el recuento de muestras sale cuatro veces
                // mayor de lo real. Al final del archivo eso es leer fuera del bloque, que en
                // el mejor caso ensucia el audio y en el peor provoca una violacion de acceso.
                _bufferLength = (int)(currentLength / sizeof(float));
                _bufferOffset = 0;
            }
            catch
            {
                _ = buffer->Release();
                throw;
            }

            return _bufferLength > 0;
        }
        finally
        {
            if (sample is not null)
            {
                _ = sample->Release();
            }
        }
    }

    private void ReleaseBuffer()
    {
        if (_buffer is not null)
        {
            // Desbloquear y liberar, en ese orden y sin excepcion: el orden inverso dejaria
            // una vista del bloque de memoria viva sobre un objeto ya destruido.
            _buffer->Unlock();
            _ = _buffer->Release();
            _buffer = null;
        }

        _bufferData = null;
        _bufferLength = 0;
        _bufferOffset = 0;
    }
}
