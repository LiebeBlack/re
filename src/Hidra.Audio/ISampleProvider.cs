namespace Hidra.Audio;

/// <summary>
/// Fuente de muestras del motor de salida.
/// </summary>
/// <remarks>
/// El contrato es un unico metodo que rellena un destino ya reservado, sin devolver nada y
/// sin poder reservar memoria. Es la forma de que el hilo de audio nunca tenga que negociar
/// con el monton: quien implementa escribe directamente donde le dicen. Se usa una interfaz
/// y no un delegado a proposito, porque la llamada queda desvirtualizada al ser el tipo
/// sellado y no hay objeto delegado que invocar.
/// </remarks>
internal interface ISampleProvider
{
    /// <summary>
    /// Rellena <paramref name="destination"/> con muestras entrelazadas.
    /// </summary>
    /// <param name="destination">Destino cuyo tamano es fotogramas por canales.</param>
    /// <param name="channels">Numero de canales entrelazados.</param>
    void Render(Span<float> destination, int channels);
}

/// <summary>
/// Generador de un tono puro. Sirve para ejercitar el motor sin depender de un archivo ni
/// de un decodificador, y es lo que permite probar la cadena completa con un dispositivo real.
/// </summary>
internal sealed class ToneProvider : ISampleProvider
{
    private const double TwoPi = 2.0 * Math.PI;

    private readonly double _increment;
    private readonly float _amplitude;
    private double _phase;
    private double _frames;

    /// <summary>Crea el generador.</summary>
    public ToneProvider(int sampleRate, double frequencyHz, float amplitude = 0.25f)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(sampleRate);

        _increment = TwoPi * frequencyHz / sampleRate;
        _amplitude = amplitude;
    }

    /// <summary>Fotogramas generados hasta ahora.</summary>
    public double FramesGenerated => _frames;

    /// <inheritdoc />
    public void Render(Span<float> destination, int channels)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(channels);

        int frames = destination.Length / channels;

        for (int frame = 0; frame < frames; frame++)
        {
            float value = (float)(Math.Sin(_phase) * _amplitude);
            int offset = frame * channels;

            for (int channel = 0; channel < channels; channel++)
            {
                destination[offset + channel] = value;
            }

            _phase += _increment;
            while (_phase >= TwoPi)
            {
                _phase -= TwoPi;
            }
        }

        _frames += frames;
    }
}
