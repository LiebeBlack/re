using Hidra.Kernel.Dsp;

namespace Hidra.Audio;

/// <summary>
/// Descripcion del formato de un flujo, independiente de las estructuras de Win32.
/// </summary>
/// <remarks>
/// Se mantiene aparte de <c>WAVEFORMATEX</c> a proposito: la aritmetica de duraciones y la
/// validacion de formatos son logica pura que debe poder verificarse sin dispositivo de audio,
/// sin COM y sin Windows de por medio. La conversion a las estructuras nativas vive en una
/// capa aparte que no contiene ninguna decision.
/// </remarks>
internal readonly struct AudioFormat : IEquatable<AudioFormat>
{
    /// <summary>Crea una descripcion de formato validando sus invariantes.</summary>
    public AudioFormat(int sampleRate, int channels, SampleEncoding encoding, uint channelMask = 0)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(sampleRate);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(channels);

        SampleRate = sampleRate;
        Channels = channels;
        Encoding = encoding;
        ChannelMask = channelMask;
        BitsPerSample = encoding switch
        {
            SampleEncoding.Pcm16 => 16,
            SampleEncoding.Pcm24 => 24,
            SampleEncoding.Pcm32 => 32,
            SampleEncoding.Float32 => 32,
            _ => throw new ArgumentOutOfRangeException(nameof(encoding), encoding, "Codificacion no soportada."),
        };
    }

    /// <summary>Muestras por segundo.</summary>
    public int SampleRate { get; }

    /// <summary>Numero de canales del flujo entrelazado.</summary>
    public int Channels { get; }

    /// <summary>Codificacion de cada muestra.</summary>
    public SampleEncoding Encoding { get; }

    /// <summary>Mascara de canales, o cero cuando el formato es PCM clasico.</summary>
    public uint ChannelMask { get; }

    /// <summary>Bits por muestra del contenedor.</summary>
    public int BitsPerSample { get; }

    /// <summary>Bytes de un fotograma completo, todos los canales incluidos.</summary>
    public int BlockAlign => Channels * (BitsPerSample / 8);

    /// <summary>Bytes por segundo del flujo.</summary>
    public int AverageBytesPerSecond => SampleRate * BlockAlign;

    /// <summary>True cuando las muestras son de coma flotante.</summary>
    public bool IsFloat => Encoding == SampleEncoding.Float32;

    /// <summary>Fotogramas que ocupan <paramref name="duration"/> a la frecuencia del formato.</summary>
    public long FramesFor(TimeSpan duration) =>
        (long)Math.Ceiling(duration.TotalSeconds * SampleRate);

    /// <inheritdoc />
    public bool Equals(AudioFormat other) =>
        SampleRate == other.SampleRate
        && Channels == other.Channels
        && Encoding == other.Encoding
        && ChannelMask == other.ChannelMask;

    /// <inheritdoc />
    public override bool Equals(object? obj) => obj is AudioFormat other && Equals(other);

    /// <inheritdoc />
    public override int GetHashCode() => HashCode.Combine(SampleRate, Channels, Encoding, ChannelMask);

    /// <summary>Compara dos formatos.</summary>
    public static bool operator ==(AudioFormat left, AudioFormat right) => left.Equals(right);

    /// <summary>Compara dos formatos.</summary>
    public static bool operator !=(AudioFormat left, AudioFormat right) => !left.Equals(right);

    /// <inheritdoc />
    public override string ToString() =>
        $"{SampleRate} Hz, {Channels} canales, {BitsPerSample} bits {(IsFloat ? "float" : "int")}";
}

/// <summary>
/// Aritmetica de duraciones del motor de audio.
/// </summary>
/// <remarks>
/// Una unidad de <c>REFERENCE_TIME</c> es de 100 nanosegundos, de donde salen los diez
/// millones por segundo. Toda esta aritmetica es pura y verificable.
/// </remarks>
internal static class ReferenceTime
{
    /// <summary>Unidades de 100 nanosegundos en un segundo.</summary>
    public const long PerSecond = 10_000_000;

    /// <summary>Convierte una duracion a unidades de referencia, redondeando al alza.</summary>
    public static long FromTimeSpan(TimeSpan duration)
    {
        double units = duration.TotalSeconds * PerSecond;
        return (long)Math.Ceiling(units);
    }

    /// <summary>
    /// Duracion de buffer que corresponde a un numero de fotogramas ya concedido por el
    /// dispositivo.
    /// </summary>
    /// <remarks>
    /// Este calculo es el nucleo del manejo de <c>AUDCLNT_E_BUFFER_SIZE_NOT_ALIGNED</c>.
    /// En modo exclusivo el motor redondea la duracion solicitada al periodo del dispositivo
    /// y devuelve ese error si el redondeo cambio el valor. La respuesta correcta no es
    /// reintentar con el mismo numero: hay que preguntar al cliente por el tamano de buffer
    /// que realmente concedio, convertirlo a duracion y volver a inicializar con ESE valor,
    /// que ya esta alineado por construccion. Pedir un tamano arbitrario en modo exclusivo
    /// falla en unos drivers y en otros da una latencia muy distinta de la esperada.
    /// </remarks>
    public static long FromFrames(long frames, int sampleRate)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(sampleRate);
        ArgumentOutOfRangeException.ThrowIfNegative(frames);

        return (long)((double)PerSecond * frames / sampleRate);
    }

    /// <summary>Convierte unidades de referencia a milisegundos.</summary>
    public static double ToMilliseconds(long units) => (double)units / PerSecond * 1000.0;

    /// <summary>Convierte unidades de referencia a fotogramas, redondeando al alza.</summary>
    public static long ToFrames(long units, int sampleRate) =>
        (long)Math.Ceiling((double)units * sampleRate / PerSecond);
}
