using Hidra.Kernel.Dsp;

namespace Hidra.Verify;

/// <summary>Comprobaciones del analizador de espectro y del remuestreador.</summary>
internal static class DspTests
{
    public static void Run()
    {
        Harness.Suite("espectro/tono-cae-en-su-banda", ToneFallsInItsBand);
        Harness.Suite("espectro/rango-de-salida", OutputStaysInRange);
        Harness.Suite("espectro/reinicio", ResetDiscardsHistory);
        Harness.Suite("remuestreo/ganancia-continua", ConstantIsPreserved);
        Harness.Suite("remuestreo/amplitud-y-frecuencia", AmplitudeAndFrequencySurvive);
        Harness.Suite("remuestreo/aumento", UpsamplingAlsoWorks);
    }

    private static void ToneFallsInItsBand()
    {
        const int fftSize = 2048;
        const int sampleRate = 48000;
        const int bandCount = 64;
        const float minHz = 20f;
        const float maxHz = 20000f;

        using var analyzer = new SpectrumAnalyzer(fftSize, sampleRate, bandCount, minHz, maxHz, WindowKind.BlackmanHarris, riseMilliseconds: 0f, fallMilliseconds: 0f);

        var frame = new float[fftSize];
        var bands = new float[bandCount];
        Signals.Sine(frame, 1000.0, sampleRate);

        // Varias pasadas para que el suavizado converja.
        for (int i = 0; i < 8; i++)
        {
            analyzer.Process(frame, bands);
        }

        Harness.Finite(bands, "el analizador produjo bandas no finitas");

        int loudest = 0;
        for (int i = 1; i < bandCount; i++)
        {
            if (bands[i] > bands[loudest])
            {
                loudest = i;
            }
        }

        int expected = (int)Math.Floor(bandCount * Math.Log(1000.0 / minHz) / Math.Log(maxHz / minHz));
        Harness.Check(Math.Abs(loudest - expected) <= 1, $"la banda dominante fue {loudest} y se esperaba alrededor de {expected}");

        // Un tono grave debe caer muy por debajo del anterior.
        var lowFrame = new float[fftSize];
        Signals.Sine(lowFrame, 50.0, sampleRate);
        for (int i = 0; i < 8; i++)
        {
            analyzer.Process(lowFrame, bands);
        }

        int lowLoudest = 0;
        for (int i = 1; i < bandCount; i++)
        {
            if (bands[i] > bands[lowLoudest])
            {
                lowLoudest = i;
            }
        }

        Harness.Check(lowLoudest < 8, $"un tono de 50 Hz cayo en la banda {lowLoudest}, demasiado alta");
    }

    private static void OutputStaysInRange()
    {
        const int fftSize = 1024;
        const int bandCount = 32;

        using var analyzer = new SpectrumAnalyzer(fftSize, 44100, bandCount);
        var frame = new float[fftSize];
        var bands = new float[bandCount];

        Signals.Mixed(frame);
        analyzer.Process(frame, bands);

        // Una senal por debajo de escala plena no debe superar el techo declarado. Se deja
        // medio decibel de margen porque el pico de banda es un promedio de pocos bins.
        bool inRange = true;
        float highest = float.MinValue;
        for (int i = 0; i < bandCount; i++)
        {
            highest = Math.Max(highest, bands[i]);
            inRange &= bands[i] <= analyzer.MaxDecibels + 0.5f;
        }

        Harness.Check(inRange, $"el nivel de banda se sale del rango declarado: maximo {highest} dB");

        // La escala solo tiene sentido si el techo es alcanzable: un tono a escala plena
        // debe leerse en su banda cerca de cero decibelios, no treinta decibelios mas abajo.
        var tone = new float[fftSize];
        Signals.Sine(tone, 1000.0, 44100, 1.0);
        using (var toneAnalyzer = new SpectrumAnalyzer(fftSize, 44100, bandCount))
        {
            var toneBands = new float[bandCount];
            for (int i = 0; i < 8; i++)
            {
                toneAnalyzer.Process(tone, toneBands);
            }

            float loudest = float.MinValue;
            for (int i = 0; i < bandCount; i++)
            {
                loudest = Math.Max(loudest, toneBands[i]);
            }

            Harness.Check(
                loudest > -12f && loudest <= 0.5f,
                $"un tono a escala plena mide {loudest} dB en su banda");
        }
    }

    private static void ResetDiscardsHistory()
    {
        const int fftSize = 1024;
        const int bandCount = 16;

        using var analyzer = new SpectrumAnalyzer(fftSize, 44100, bandCount, riseMilliseconds: 0f, fallMilliseconds: 0f);
        var frame = new float[fftSize];
        var bands = new float[bandCount];

        Signals.Sine(frame, 1000.0, 44100);
        analyzer.Process(frame, bands);

        analyzer.Reset();

        // Silencio absoluto mas alla del suelo del float: el nivel debe caer en picado.
        Array.Clear(frame);
        analyzer.Process(frame, bands);

        float loudest = float.MinValue;
        for (int i = 0; i < bandCount; i++)
        {
            loudest = Math.Max(loudest, bands[i]);
        }

        Harness.Check(loudest < -100f, $"tras el reinicio el nivel de silencio fue {loudest} dB, demasiado alto");
    }

    private static void ConstantIsPreserved()
    {
        const int inputLength = 16384;

        using var resampler = new SincResampler(48000, 44100);
        var input = new float[inputLength];
        Signals.Constant(input, 1f);

        var output = new float[32768];
        int produced = resampler.Process(input, 0, output);

        Harness.Check(produced > 14000, $"solo se produjeron {produced} muestras de las esperadas");

        // La tabla esta normalizada por fase, asi que la continua debe salir plana: cualquier
        // rizado aqui delataria una normalizacion global en vez de por fase.
        float minimum = float.MaxValue;
        float maximum = float.MinValue;
        for (int i = 0; i < produced; i++)
        {
            minimum = Math.Min(minimum, output[i]);
            maximum = Math.Max(maximum, output[i]);
        }

        Harness.Close(1.0, minimum, 2e-3, "la continua de salida no es la unidad");
        Harness.Close(1.0, maximum, 2e-3, "la continua de salida no es la unidad");
        Harness.Check(maximum - minimum < 1e-3f, $"la continua de salida riza {maximum - minimum:R}");
    }

    private static void AmplitudeAndFrequencySurvive()
    {
        const int inputLength = 16384;
        const double tone = 1000.0;

        using var resampler = new SincResampler(48000, 44100);
        var input = new float[inputLength];
        Signals.Sine(input, tone, 48000);

        var output = new float[32768];
        int produced = resampler.Process(input, 0, output);
        Harness.Check(produced > 14000, $"solo se produjeron {produced} muestras");

        Harness.Finite(output.AsSpan(0, produced), "el remuestreador produjo valores no finitos");

        // Se ignora el primer y el ultimo 10% para no medir el transitorio del filtro.
        int start = produced / 10;
        int end = produced - start;

        float peak = 0f;
        for (int i = start; i < end; i++)
        {
            peak = Math.Max(peak, Math.Abs(output[i]));
        }

        Harness.Close(1.0, peak, 0.01, "la amplitud del tono no se conserva");

        int crossings = 0;
        for (int i = start + 1; i < end; i++)
        {
            if ((output[i - 1] < 0f) != (output[i] < 0f))
            {
                crossings++;
            }
        }

        double expected = 2.0 * tone * (end - start) / 44100.0;
        Harness.Close(expected, crossings, 2.0, "la frecuencia del tono no se conserva");
    }

    private static void UpsamplingAlsoWorks()
    {
        const int inputLength = 12000;

        using var resampler = new SincResampler(44100, 48000);
        var input = new float[inputLength];
        Signals.Constant(input, 0.5f);

        var output = new float[32768];
        int produced = resampler.Process(input, 0, output);

        Harness.Check(produced > 12000, $"solo se produjeron {produced} muestras al aumentar la frecuencia");

        float minimum = float.MaxValue;
        float maximum = float.MinValue;
        for (int i = 0; i < produced; i++)
        {
            minimum = Math.Min(minimum, output[i]);
            maximum = Math.Max(maximum, output[i]);
        }

        Harness.Close(0.5, minimum, 2e-3, "la continua de salida no es la mitad");
        Harness.Close(0.5, maximum, 2e-3, "la continua de salida no es la mitad");
    }
}
