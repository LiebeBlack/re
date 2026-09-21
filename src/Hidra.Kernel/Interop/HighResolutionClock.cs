using System.ComponentModel;

namespace Hidra.Kernel.Interop;

/// <summary>
/// Reloj monotono de alta resolucion. Deliberadamente NO se usa
/// <c>DateTime</c> ni <c>Stopwatch</c> para el control de plazos del motor de audio: el
/// contador de rendimiento es monotono, no depende de la hora del sistema y no puede
/// retroceder por un ajuste de NTP en mitad de la reproduccion.
/// </summary>
internal static class HighResolutionClock
{
    private static readonly long TicksPerSecond = QueryFrequency();

    /// <summary>Frecuencia del contador, en Hz.</summary>
    public static long Frequency => TicksPerSecond;

    /// <summary>Lee el contador de rendimiento.</summary>
    public static long Timestamp()
    {
        _ = Kernel32.QueryPerformanceCounter(out long counter);
        return counter;
    }

    /// <summary>Convierte ticks a segundos.</summary>
    public static double ToSeconds(long ticks) => (double)ticks / TicksPerSecond;

    /// <summary>Convierte ticks a milisegundos.</summary>
    public static double ToMilliseconds(long ticks) => (double)ticks * 1000.0 / TicksPerSecond;

    private static long QueryFrequency()
    {
        if (!Kernel32.QueryPerformanceFrequency(out long frequency) || frequency <= 0)
        {
            throw new Win32Exception("QueryPerformanceFrequency no devolvio una frecuencia util.");
        }

        return frequency;
    }
}
