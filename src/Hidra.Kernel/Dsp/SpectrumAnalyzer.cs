using Hidra.Kernel.Memory;

namespace Hidra.Kernel.Dsp;

/// <summary>
/// Convierte bloques de audio en un espectro de bandas listo para pintar, sin reservar
/// memoria despues de la construccion.
/// </summary>
/// <remarks>
/// La agregacion por bandas es geometricamente espaciada porque el oido tambien lo es:
/// bandas lineales desperdiciarian casi todas las bandas en el extremo agudo, donde no se
/// distingue nada. La reduccion dentro de cada banda se mantiene escalar a proposito: es
/// una suma de pocos terminos y reordenarla en un acumulador vectorial cambiaria el ultimo
/// bit, rompiendo el determinismo entre ejecuciones y entre equipos.
/// </remarks>
internal sealed unsafe class SpectrumAnalyzer : IDisposable
{
    private readonly FftKernel _fft;
    private readonly int _fftSize;
    private readonly int _binCount;
    private readonly int _bandCount;
    private readonly AlignedBuffer<float> _window;
    private readonly AlignedBuffer<float> _frame;
    private readonly AlignedBuffer<float> _real;
    private readonly AlignedBuffer<float> _imaginary;
    private readonly AlignedBuffer<int> _bandStart;
    private readonly AlignedBuffer<int> _bandEnd;
    private readonly AlignedBuffer<float> _bandDecibels;
    private readonly float _riseCoefficient;
    private readonly float _fallCoefficient;
    private readonly float _minDecibels;
    private readonly float _maxDecibels;
    private readonly float _powerScale;
    private bool _primed;
    private bool _disposed;

    /// <summary>Prepara el analizador con su mapa de bandas.</summary>
    /// <param name="fftSize">Tamano de FFT. Potencia de dos.</param>
    /// <param name="sampleRate">Frecuencia de muestreo del material de entrada.</param>
    /// <param name="bandCount">Numero de bandas de salida.</param>
    /// <param name="minFrequencyHz">Frecuencia central de la primera banda.</param>
    /// <param name="maxFrequencyHz">Frecuencia superior de la ultima banda.</param>
    /// <param name="window">Ventana espectral aplicada antes de la FFT.</param>
    /// <param name="riseMilliseconds">Constante de subida del suavizado.</param>
    /// <param name="fallMilliseconds">Constante de bajada del suavizado.</param>
    public SpectrumAnalyzer(
        int fftSize,
        int sampleRate,
        int bandCount,
        float minFrequencyHz = 20f,
        float maxFrequencyHz = 20000f,
        WindowKind window = WindowKind.BlackmanHarris,
        float riseMilliseconds = 12f,
        float fallMilliseconds = 120f,
        float minDecibels = -100f,
        float maxDecibels = 0f)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(sampleRate);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(bandCount);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(minFrequencyHz);

        _fftSize = fftSize;
        _bandCount = bandCount;
        _minDecibels = minDecibels;
        _maxDecibels = maxDecibels;

        // Escalado que devuelve amplitudes fisicas a la salida de la FFT. El factor 4 sale de
        // que una sinusoide de amplitud A reparte A*gananciaCoherente/2 entre los dos bins
        // conjugados; al quedarnos con los positivos, la amplitud es 2*|X|/gananciaCoherente.
        // Se trabaja en potencia, de modo que A^2 = 4*|X|^2 / gananciaCoherente^2 y no hace
        // falta ninguna raiz cuadrada por bin.
        double coherentGain = WindowFunctions.CoherentGain(window, fftSize);
        _powerScale = coherentGain > 0.0
            ? (float)(4.0 / (coherentGain * coherentGain))
            : 1f;
        _fft = new FftKernel(fftSize);
        _binCount = _fft.BinCount;

        _window = new AlignedBuffer<float>(fftSize);
        WindowFunctions.Fill(window, _window.Span);

        _frame = new AlignedBuffer<float>(fftSize);
        _real = new AlignedBuffer<float>(_binCount);
        _imaginary = new AlignedBuffer<float>(_binCount);
        _bandDecibels = new AlignedBuffer<float>(bandCount);
        _bandStart = new AlignedBuffer<int>(bandCount);
        _bandEnd = new AlignedBuffer<int>(bandCount);

        // Suavizado asimetrico: respuesta rapida al subir, relajada al bajar. Es lo que hace
        // que un golpe de bateria se vea como un golpe y no como un parpadeo.
        _riseCoefficient = TimeConstant(riseMilliseconds, sampleRate, fftSize);
        _fallCoefficient = TimeConstant(fallMilliseconds, sampleRate, fftSize);

        double frequencyRatio = maxFrequencyHz / minFrequencyHz;
        for (int band = 0; band < bandCount; band++)
        {
            double low = minFrequencyHz * Math.Pow(frequencyRatio, (double)band / bandCount);
            double high = minFrequencyHz * Math.Pow(frequencyRatio, (double)(band + 1) / bandCount);

            int start = (int)Math.Round(low * fftSize / sampleRate);
            int end = (int)Math.Round(high * fftSize / sampleRate);

            // El bin 0 es continua pura; aporta un pedestal que ensucia la banda mas grave.
            start = Math.Clamp(start, 1, _binCount - 1);
            end = Math.Clamp(end, start + 1, _binCount);

            _bandStart[band] = start;
            _bandEnd[band] = end;
        }
    }

    /// <summary>Numero de bandas de salida.</summary>
    public int BandCount => _bandCount;

    /// <summary>Tamano de bloque que consume <see cref="Process"/>.</summary>
    public int FrameSize => _fftSize;

    /// <summary>Suelo de la escala de salida, en decibelios.</summary>
    public float MinDecibels => _minDecibels;

    /// <summary>Techo de la escala de salida, en decibelios.</summary>
    public float MaxDecibels => _maxDecibels;

    /// <summary>
    /// Procesa un bloque y escribe el nivel de cada banda en decibelios.
    /// No reserva memoria ni bloquea.
    /// </summary>
    /// <param name="samples">Al menos <see cref="FrameSize"/> muestras.</param>
    /// <param name="decibels">Destino con <see cref="BandCount"/> elementos.</param>
    public void Process(ReadOnlySpan<float> samples, Span<float> decibels)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        if (samples.Length < _fftSize)
        {
            throw new ArgumentException($"El bloque necesita al menos {_fftSize} muestras.", nameof(samples));
        }

        if (decibels.Length < _bandCount)
        {
            throw new ArgumentException($"El destino necesita al menos {_bandCount} elementos.", nameof(decibels));
        }

        WindowFunctions.Apply(_window.Span, samples, _frame.Span);
        _fft.ForwardReal(_frame.Span, _real.Span, _imaginary.Span);

        float* real = _real.TypedPointer;
        float* imaginary = _imaginary.TypedPointer;

        for (int band = 0; band < _bandCount; band++)
        {
            int start = _bandStart[band];
            int end = _bandEnd[band];

            float power = 0f;
            for (int bin = start; bin < end; bin++)
            {
                float binReal = real[bin];
                float binImaginary = imaginary[bin];
                power += (binReal * binReal) + (binImaginary * binImaginary);
            }

            // Se promedia por numero de bins. Sin esto, las bandas agudas, que agrupan
            // decenas de bins, se leerian artificialmente mas fuertes que las graves, que
            // agrupan uno o dos: el espectro tendria una rampa que no esta en la senal.
            int width = end - start;
            float measured = 10f * MathF.Log10((power * _powerScale / width) + 1e-20f);
            float previous = _bandDecibels[band];

            if (!_primed)
            {
                _bandDecibels[band] = measured;
                decibels[band] = measured;
                continue;
            }

            float coefficient = measured > previous ? _riseCoefficient : _fallCoefficient;
            float smoothed = previous + ((measured - previous) * coefficient);
            _bandDecibels[band] = smoothed;
            decibels[band] = smoothed;
        }

        _primed = true;
    }

    /// <summary>
    /// Descarta el estado de suavizado. Necesario al cambiar de fuente para que las bandas
    /// no arrastren el nivel anterior.
    /// </summary>
    public void Reset()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        _primed = false;
        _bandDecibels.Span.Clear();
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _fft.Dispose();
        _window.Dispose();
        _frame.Dispose();
        _real.Dispose();
        _imaginary.Dispose();
        _bandStart.Dispose();
        _bandEnd.Dispose();
        _bandDecibels.Dispose();
    }

    private static float TimeConstant(float milliseconds, int sampleRate, int frameSize)
    {
        if (milliseconds <= 0f)
        {
            return 1f;
        }

        double framesPerMillisecond = (double)sampleRate / (frameSize * 1000.0);
        double frames = milliseconds * framesPerMillisecond;
        return (float)(1.0 - Math.Exp(-1.0 / frames));
    }
}
