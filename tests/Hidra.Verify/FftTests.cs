using Hidra.Kernel.Dsp;

namespace Hidra.Verify;

/// <summary>
/// Contraste de la FFT contra una DFT directa y contra su propio camino escalar.
/// </summary>
internal static class FftTests
{
    public static void Run()
    {
        Harness.Suite("fft/compleja-frente-a-dft", ComplexMatchesNaiveDft);
        Harness.Suite("fft/vectorial-frente-a-escalar", VectorPathIsBitExact);
        Harness.Suite("fft/real-frente-a-dft", RealMatchesNaiveDft);
        Harness.Suite("fft/tono-conocido", KnownToneLandsInItsBin);
    }

    /// <summary>
    /// La FFT compleja debe coincidir con la definicion directa. Es la comprobacion que
    /// valida de una vez la permutacion bit-reversa, las tablas de twiddles por etapa y el
    /// orden de las mariposas.
    /// </summary>
    private static void ComplexMatchesNaiveDft()
    {
        const int size = 256;

        using var fft = new FftKernel(size);
        var real = new float[size];
        var imaginary = new float[size];
        Mixed(real, size);
        Mixed(imaginary, 97);

        var expectedReal = new float[size];
        var expectedImaginary = new float[size];
        NaiveComplexDft(real, imaginary, expectedReal, expectedImaginary);

        fft.Forward(real, imaginary);

        double reference = 0.0;
        for (int i = 0; i < size; i++)
        {
            reference = Math.Max(reference, Math.Max(Math.Abs(expectedReal[i]), Math.Abs(expectedImaginary[i])));
        }

        double tolerance = Math.Max(1e-6, reference * 1e-4);
        double worst = 0.0;
        for (int i = 0; i < size; i++)
        {
            worst = Math.Max(worst, Math.Abs(expectedReal[i] - real[i]));
            worst = Math.Max(worst, Math.Abs(expectedImaginary[i] - imaginary[i]));
        }

        Harness.Check(worst <= tolerance, $"desviacion maxima {worst:R} por encima de la tolerancia {tolerance:R}");
    }

    /// <summary>
    /// El camino vectorial y el escalar deben dar el MISMO bit. Si algun dia alguien deja
    /// que el JIT fusione una multiplicacion y una suma en un FMA dentro del camino
    /// vectorial, esta comprobacion se rompe y avisa de que ya no hay paridad.
    /// </summary>
    private static void VectorPathIsBitExact()
    {
        int[] sizes = [64, 256, 1024];

        foreach (int size in sizes)
        {
            using var fft = new FftKernel(size);
            var vectorReal = new float[size];
            var vectorImaginary = new float[size];
            Mixed(vectorReal, size);
            Mixed(vectorImaginary, 131);

            var scalarReal = new float[size];
            var scalarImaginary = new float[size];
            vectorReal.CopyTo(scalarReal, 0);
            vectorImaginary.CopyTo(scalarImaginary, 0);

            fft.Forward(vectorReal, vectorImaginary, vectorized: true);
            fft.Forward(scalarReal, scalarImaginary, vectorized: false);

            int worstIndex = -1;
            for (int i = 0; i < size; i++)
            {
                if (BitConverter.SingleToInt32Bits(vectorReal[i]) != BitConverter.SingleToInt32Bits(scalarReal[i]) ||
                    BitConverter.SingleToInt32Bits(vectorImaginary[i]) != BitConverter.SingleToInt32Bits(scalarImaginary[i]))
                {
                    worstIndex = i;
                    break;
                }
            }

            Harness.Check(worstIndex < 0, $"sin paridad bit a bit para n={size} (primer indice divergente {worstIndex})");
        }
    }

    /// <summary>La FFT real empaquetada debe dar los mismos bins que la DFT directa.</summary>
    private static void RealMatchesNaiveDft()
    {
        const int size = 256;
        int bins = size / 2;

        using var fft = new FftKernel(size);
        var signal = new float[size];
        Mixed(signal, size);

        var expectedReal = new float[bins];
        var expectedImaginary = new float[bins];
        NaiveRealDft(signal, expectedReal, expectedImaginary);

        var real = new float[bins];
        var imaginary = new float[bins];
        fft.ForwardReal(signal, real, imaginary);

        double reference = 0.0;
        for (int i = 0; i < bins; i++)
        {
            reference = Math.Max(reference, Math.Max(Math.Abs(expectedReal[i]), Math.Abs(expectedImaginary[i])));
        }

        double tolerance = Math.Max(1e-6, reference * 1e-4);
        double worst = 0.0;
        for (int i = 0; i < bins; i++)
        {
            worst = Math.Max(worst, Math.Abs(expectedReal[i] - real[i]));
            worst = Math.Max(worst, Math.Abs(expectedImaginary[i] - imaginary[i]));
        }

        Harness.Check(worst <= tolerance, $"desviacion maxima {worst:R} por encima de la tolerancia {tolerance:R}");
    }

    /// <summary>
    /// Una sinusoide en un bin exacto debe concentrar toda su energia ahi. Verifica la
    /// convencion de signos y el orden de bins, que una comparacion de magnitudes por si
    /// sola no detectaria: un espectro espejado tambien cuadra en magnitud.
    /// </summary>
    private static void KnownToneLandsInItsBin()
    {
        const int size = 1024;
        const int toneBin = 64;
        int bins = size / 2;

        using var fft = new FftKernel(size);
        var signal = new float[size];
        for (int i = 0; i < size; i++)
        {
            signal[i] = (float)Math.Cos(2.0 * Math.PI * toneBin * i / size);
        }

        var real = new float[bins];
        var imaginary = new float[bins];
        fft.ForwardReal(signal, real, imaginary);

        double peak = 0.0;
        int peakBin = -1;
        for (int i = 0; i < bins; i++)
        {
            double magnitude = Math.Sqrt((real[i] * real[i]) + (imaginary[i] * imaginary[i]));
            if (magnitude > peak)
            {
                peak = magnitude;
                peakBin = i;
            }
        }

        Harness.Check(peakBin == toneBin, $"el pico cayo en el bin {peakBin} en vez de {toneBin}");
        Harness.Close(size / 2.0, peak, size * 1e-3, "la magnitud del pico no corresponde a media longitud de bloque");
    }

    private static void Mixed(Span<float> destination, int seed)
    {
        uint state = (uint)seed * 2654435761u;

        for (int i = 0; i < destination.Length; i++)
        {
            state = (state * 1664525u) + 1013904223u;
            destination[i] = (((state >> 9) & 0x3FFF) / 16384f) - 0.5f;
        }
    }

    private static void NaiveComplexDft(
        ReadOnlySpan<float> real,
        ReadOnlySpan<float> imaginary,
        Span<float> expectedReal,
        Span<float> expectedImaginary)
    {
        int n = real.Length;

        for (int k = 0; k < n; k++)
        {
            double sumReal = 0.0;
            double sumImaginary = 0.0;

            for (int t = 0; t < n; t++)
            {
                double angle = -2.0 * Math.PI * k * t / n;
                double cosine = Math.Cos(angle);
                double sine = Math.Sin(angle);
                sumReal += (real[t] * cosine) - (imaginary[t] * sine);
                sumImaginary += (real[t] * sine) + (imaginary[t] * cosine);
            }

            expectedReal[k] = (float)sumReal;
            expectedImaginary[k] = (float)sumImaginary;
        }
    }

    private static void NaiveRealDft(ReadOnlySpan<float> signal, Span<float> expectedReal, Span<float> expectedImaginary)
    {
        int n = signal.Length;
        int bins = n / 2;

        for (int k = 0; k < bins; k++)
        {
            double sumReal = 0.0;
            double sumImaginary = 0.0;

            for (int t = 0; t < n; t++)
            {
                double angle = -2.0 * Math.PI * k * t / n;
                sumReal += signal[t] * Math.Cos(angle);
                sumImaginary += signal[t] * Math.Sin(angle);
            }

            expectedReal[k] = (float)sumReal;
            expectedImaginary[k] = (float)sumImaginary;
        }
    }
}
