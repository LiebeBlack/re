using Hidra.Kernel.Diagnostics;
using Hidra.Kernel.Dsp;

namespace Hidra.Verify;

/// <summary>
/// Demuestra que los caminos en tiempo real no asignan memoria despues de su construccion.
/// Es la comprobacion que respalda la regla de cero asignaciones: sin medicion, la regla es
/// solo una intencion escrita en un comentario.
/// </summary>
internal static class AllocationTests
{
    public static void Run()
    {
        Harness.Suite("asignaciones/fft", FftAllocatesNothing);
        Harness.Suite("asignaciones/espectro", AnalyzerAllocatesNothing);
        Harness.Suite("asignaciones/remuestreo", ResamplerAllocatesNothing);
    }

    private static void FftAllocatesNothing()
    {
        const int size = 2048;

        using var fft = new FftKernel(size);
        var real = new float[size];
        var imaginary = new float[size];
        var bins = new float[size / 2];
        Signals.Mixed(real);

        for (int i = 0; i < 50; i++)
        {
            fft.Forward(real, imaginary);
            fft.ForwardReal(real, bins, imaginary);
        }

        var probe = AllocationProbe.Begin();
        for (int i = 0; i < 500; i++)
        {
            fft.Forward(real, imaginary);
        }

        long allocated = probe.AllocatedBytes;
        Harness.Check(allocated == 0, $"la FFT compleja asigno {allocated} bytes en 500 transformadas");

        probe = AllocationProbe.Begin();
        for (int i = 0; i < 500; i++)
        {
            fft.ForwardReal(real, bins, imaginary);
        }

        allocated = probe.AllocatedBytes;
        Harness.Check(allocated == 0, $"la FFT real asigno {allocated} bytes en 500 transformadas");
    }

    private static void AnalyzerAllocatesNothing()
    {
        const int fftSize = 2048;
        const int bandCount = 64;

        using var analyzer = new SpectrumAnalyzer(fftSize, 48000, bandCount);
        var frame = new float[fftSize];
        var bands = new float[bandCount];
        Signals.Mixed(frame);

        for (int i = 0; i < 300; i++)
        {
            analyzer.Process(frame, bands);
        }

        var probe = AllocationProbe.Begin();
        for (int i = 0; i < 3000; i++)
        {
            analyzer.Process(frame, bands);
        }

        long allocated = probe.AllocatedBytes;
        Harness.Check(allocated == 0, $"el analizador asigno {allocated} bytes en 3000 fotogramas");
    }

    private static void ResamplerAllocatesNothing()
    {
        const int inputLength = 8192;

        using var resampler = new SincResampler(44100, 48000);
        var input = new float[inputLength];
        var output = new float[16384];
        Signals.Sine(input, 997.0, 44100);

        for (int pass = 0; pass < 50; pass++)
        {
            resampler.Reset();
            resampler.Process(input, 0, output);
        }

        long total = 0;
        for (int pass = 0; pass < 200; pass++)
        {
            resampler.Reset();
            var probe = AllocationProbe.Begin();
            resampler.Process(input, 0, output);
            total += probe.AllocatedBytes;
        }

        Harness.Check(total == 0, $"el remuestreador asigno {total} bytes en 200 pasadas");
    }
}
