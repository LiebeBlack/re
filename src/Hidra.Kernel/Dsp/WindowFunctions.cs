using System.Numerics;
using System.Runtime.InteropServices;

namespace Hidra.Kernel.Dsp;

/// <summary>
/// Funciones de ventana precalculadas. La ventana se aplica por muestra antes de la FFT
/// para reducir la fuga espectral; sin ella una sinusoide pura ensucia decenas de bins.
/// </summary>
internal enum WindowKind
{
    /// <summary>Sin ventana. Solo valida para senales que caben exactas en la FFT.</summary>
    Rectangular = 0,

    /// <summary>Buena resolucion, fuga moderada. La opcion tipica en analizadores musicales.</summary>
    Hann = 1,

    /// <summary>Lobulo lateral bajo, resolucion aceptable.</summary>
    Hamming = 2,

    /// <summary>Mejor rechazo de lobulo lateral que Hann.</summary>
    Blackman = 3,

    /// <summary>Rechazo muy alto (-92 dB). La usada por defecto: el ojo ve el espectro sin pedestales.</summary>
    BlackmanHarris = 4,

    /// <summary>Amplitud casi plana, ideal para medida de nivel, mala para ver picos.</summary>
    FlatTop = 5,
}

/// <summary>Generacion y aplicacion de ventanas espectrales, ambas sin asignaciones.</summary>
internal static class WindowFunctions
{
    /// <summary>
    /// Suma de los coeficientes de una ventana: su ganancia coherente. Es el factor por el
    /// que hay que dividir la salida de la FFT para recuperar la amplitud real de un tono.
    /// </summary>
    public static double CoherentGain(WindowKind kind, int size)
    {
        if (kind == WindowKind.Rectangular)
        {
            return size;
        }

        double total = 0.0;
        double denominator = size;

        for (int i = 0; i < size; i++)
        {
            double t = 2.0 * Math.PI * i / denominator;
            double c1 = Math.Cos(t);
            double c2 = Math.Cos(2.0 * t);

            total += kind switch
            {
                WindowKind.Hann => 0.5 - (0.5 * c1),
                WindowKind.Hamming => 0.54 - (0.46 * c1),
                WindowKind.Blackman => 0.42 - (0.5 * c1) + (0.08 * c2),
                WindowKind.BlackmanHarris => 0.35875 - (0.48829 * c1) + (0.14128 * c2)
                                                    - (0.01168 * Math.Cos(3.0 * t)),
                WindowKind.FlatTop => 1.0 - (1.93 * c1) + (1.29 * c2)
                                           - (0.388 * Math.Cos(3.0 * t))
                                           + (0.032 * Math.Cos(4.0 * t)),
                _ => 1.0,
            };
        }

        return total;
    }
    /// <summary>Rellena <paramref name="destination"/> con la ventana indicada.</summary>
    /// <remarks>
    /// Se usa la convencion PERIODICA (DFT-even), dividiendo por el numero de muestras y no
    /// por n-1. La convencion simetrica (n-1) es la correcta para disenar filtros FIR, pero
    /// aplicada a un analisis por FFT deja de ser periodica y la fuga espectral no cae como
    /// debe. La diferencia es de media muestra, y por eso la simetrica es un error facil de
    /// cometer y dificil de notar: la ventana parece correcta, con su maximo casi en uno,
    /// pero el pico deja de caer exactamente en su bin.
    /// </remarks>
    public static void Fill(WindowKind kind, Span<float> destination)
    {
        int n = destination.Length;
        if (n == 0)
        {
            return;
        }

        if (kind == WindowKind.Rectangular)
        {
            destination.Fill(1f);
            return;
        }

        double denominator = n;

        for (int i = 0; i < n; i++)
        {
            double t = 2.0 * Math.PI * i / denominator;
            double c1 = Math.Cos(t);
            double c2 = Math.Cos(2.0 * t);

            destination[i] = kind switch
            {
                WindowKind.Hann => (float)(0.5 - (0.5 * c1)),
                WindowKind.Hamming => (float)(0.54 - (0.46 * c1)),
                WindowKind.Blackman => (float)(0.42 - (0.5 * c1) + (0.08 * c2)),
                WindowKind.BlackmanHarris => (float)(0.35875 - (0.48829 * c1) + (0.14128 * c2)
                                                     - (0.01168 * Math.Cos(3.0 * t))),
                WindowKind.FlatTop => (float)(1.0 - (1.93 * c1) + (1.29 * c2)
                                                   - (0.388 * Math.Cos(3.0 * t))
                                                   + (0.032 * Math.Cos(4.0 * t))),
                _ => 1f,
            };
        }
    }

    /// <summary>
    /// Multiplica muestra a muestra. El ancho del vector lo elige el JIT, asi que la misma
    /// linea de codigo emite AVX-512, AVX2, SSE4.2 o AdvSIMD segun el equipo.
    /// </summary>
    /// <remarks>
    /// El bucle vectorial no reasocia nada: cada muestra se multiplica una vez, por lo que
    /// el resultado es identico bit a bit al del camino escalar.
    /// </remarks>
    public static unsafe void Apply(ReadOnlySpan<float> window, ReadOnlySpan<float> source, Span<float> destination)
    {
        int length = Math.Min(destination.Length, Math.Min(window.Length, source.Length));
        if (length == 0)
        {
            return;
        }

        int width = Vector<float>.Count;
        int i = 0;

        fixed (float* windowPointer = window)
        fixed (float* sourcePointer = source)
        fixed (float* destinationPointer = destination)
        {
            for (; i + width <= length; i += width)
            {
                Vector<float> w = Vector.Load(windowPointer + i);
                Vector<float> s = Vector.Load(sourcePointer + i);
                Vector.Store(Vector.Multiply(w, s), destinationPointer + i);
            }

            for (; i < length; i++)
            {
                destinationPointer[i] = windowPointer[i] * sourcePointer[i];
            }
        }
    }
}
