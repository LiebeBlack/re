using System.Numerics;
using System.Runtime.InteropServices;

namespace Hidra.Kernel.Dsp;

/// <summary>Codificacion de las muestras de un flujo.</summary>
internal enum SampleEncoding
{
    /// <summary>Enteros con signo de 16 bits.</summary>
    Pcm16 = 0,

    /// <summary>Enteros con signo de 24 bits empaquetados en 3 bytes.</summary>
    Pcm24 = 1,

    /// <summary>Enteros con signo de 32 bits.</summary>
    Pcm32 = 2,

    /// <summary>Coma flotante de 32 bits, en el rango [-1, 1].</summary>
    Float32 = 3,
}

/// <summary>
/// Conversion de muestras de coma flotante al formato entero del dispositivo.
/// </summary>
/// <remarks>
/// <para>
/// Hace falta porque el motor en modo exclusivo entrega al dispositivo EXACTAMENTE el
/// formato que el dispositivo declara. Un DAC que trabaja a 24 bits enteros no acepta
/// flotantes, y convertir en el momento de escribir el buffer es la unica forma de no
/// meter una etapa de resampleo o un formato intermedio por software.
/// </para>
/// <para>
/// El recorte a [-1, 1] se vectoriza porque es la parte que recorre todas las muestras con
/// dos comparaciones. La conversion a entero se mantiene escalar: en .NET las conversiones
/// vectoriales de float a entero exigen controlar el modo de redondeo y acabarian
/// dependiendo de la ruta de hardware que el JIT elija, que es justo lo que no se quiere en
/// una ruta cuyo resultado se oye.
/// </para>
/// <para>
/// El escalado se hace en doble precision aunque las muestras sean de simple. No es
/// capricho: el entero mas grande de 32 bits con signo, 2147483647, NO es representable en
/// coma flotante simple y se redondea a 2147483648. Multiplicar ahi por la muestra positiva
/// mas alta da un valor fuera del rango de entero, y la conversion resultante es el minimo
/// negativo: la muestra mas fuerte posible se convierte en la mas debil. Es una inversion de
/// escala completa y se oye como un chasquido, no como un error de redondeo. En doble los
/// 2147483647 son exactos y la saturacion cae del lado correcto.
/// </para>
/// <para>
/// No se aplica tramado. Convertir 32 bits flotantes a 16 bits enteros sin tramado produce
/// distorsion de cuantizacion correlacionada con la senal; el tramado triangular es la
/// mejora natural de esta funcion.
/// </para>
/// </remarks>
internal static class SampleConverter
{
    /// <summary>Recorta <paramref name="source"/> a [-1, 1] dentro de <paramref name="destination"/>.</summary>
    public static unsafe void Clamp(ReadOnlySpan<float> source, Span<float> destination)
    {
        int count = Math.Min(source.Length, destination.Length);
        if (count == 0)
        {
            return;
        }

        int width = Vector<float>.Count;
        int i = 0;

        Vector<float> lower = new(-1f);
        Vector<float> upper = new(1f);

        fixed (float* sourcePointer = source)
        fixed (float* destinationPointer = destination)
        {
            for (; i + width <= count; i += width)
            {
                Vector<float> value = Vector.Load(sourcePointer + i);
                Vector<float> clamped = Vector.Min(Vector.Max(value, lower), upper);
                Vector.Store(clamped, destinationPointer + i);
            }

            for (; i < count; i++)
            {
                destinationPointer[i] = Math.Clamp(sourcePointer[i], -1f, 1f);
            }
        }
    }

    /// <summary>
    /// Convierte muestras flotantes ya recortadas al formato entero indicado.
    /// </summary>
    /// <param name="source">Muestras en [-1, 1].</param>
    /// <param name="destination">Destino con el numero de bytes exacto del formato.</param>
    /// <param name="encoding">Formato de destino.</param>
    public static void FromClampedFloat(ReadOnlySpan<float> source, Span<byte> destination, SampleEncoding encoding)
    {
        switch (encoding)
        {
            case SampleEncoding.Float32:
                CastAndCopy(source, destination);
                break;

            case SampleEncoding.Pcm16:
                WritePcm16(source, destination);
                break;

            case SampleEncoding.Pcm24:
                WritePcm24(source, destination);
                break;

            case SampleEncoding.Pcm32:
                WritePcm32(source, destination);
                break;

            default:
                throw new ArgumentOutOfRangeException(nameof(encoding), encoding, "Codificacion no soportada.");
        }
    }

    /// <summary>Numero de bytes que ocupan <paramref name="sampleCount"/> muestras.</summary>
    public static int BytesFor(int sampleCount, SampleEncoding encoding) => encoding switch
    {
        SampleEncoding.Pcm16 => sampleCount * 2,
        SampleEncoding.Pcm24 => sampleCount * 3,
        SampleEncoding.Pcm32 => sampleCount * 4,
        SampleEncoding.Float32 => sampleCount * 4,
        _ => throw new ArgumentOutOfRangeException(nameof(encoding), encoding, "Codificacion no soportada."),
    };

    private static void CastAndCopy(ReadOnlySpan<float> source, Span<byte> destination)
    {
        Span<float> target = MemoryMarshal.Cast<byte, float>(destination);
        int count = Math.Min(source.Length, target.Length);
        source[..count].CopyTo(target);
    }

    private static void WritePcm16(ReadOnlySpan<float> source, Span<byte> destination)
    {
        Span<short> target = MemoryMarshal.Cast<byte, short>(destination);
        int count = Math.Min(source.Length, target.Length);

        for (int i = 0; i < count; i++)
        {
            target[i] = (short)Math.Round((double)source[i] * 32767.0, MidpointRounding.AwayFromZero);
        }
    }

    private static void WritePcm24(ReadOnlySpan<float> source, Span<byte> destination)
    {
        int count = Math.Min(source.Length, destination.Length / 3);

        for (int i = 0; i < count; i++)
        {
            int sample = (int)Math.Round((double)source[i] * 8388607.0, MidpointRounding.AwayFromZero);
            int offset = i * 3;

            // Complemento a dos en little endian: los bytes bajos de un entero negativo ya
            // son su representacion correcta, no hace falta tratarlos aparte.
            destination[offset] = (byte)sample;
            destination[offset + 1] = (byte)(sample >> 8);
            destination[offset + 2] = (byte)(sample >> 16);
        }
    }

    private static void WritePcm32(ReadOnlySpan<float> source, Span<byte> destination)
    {
        Span<int> target = MemoryMarshal.Cast<byte, int>(destination);
        int count = Math.Min(source.Length, target.Length);

        for (int i = 0; i < count; i++)
        {
            target[i] = (int)Math.Round((double)source[i] * 2147483647.0, MidpointRounding.AwayFromZero);
        }
    }
}
