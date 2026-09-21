using System.Runtime.InteropServices;
using System.Runtime.Intrinsics.Arm;
using System.Runtime.Intrinsics.X86;

namespace Hidra.Kernel.Simd;

/// <summary>
/// Nivel de SIMD disponible, de menor a mayor ancho.
/// </summary>
internal enum SimdTier
{
    /// <summary>Sin vectorizacion. No deberia ocurrir en x64 ni en Arm64.</summary>
    Scalar = 0,

    /// <summary>128 bits garantizados en x64.</summary>
    Sse2 = 1,

    /// <summary>128 bits, suelo exigido por el diseno.</summary>
    Sse42 = 2,

    /// <summary>128 bits en Arm64.</summary>
    AdvSimd = 3,

    /// <summary>256 bits.</summary>
    Avx2 = 4,

    /// <summary>512 bits.</summary>
    Avx512 = 5,
}

/// <summary>
/// Deteccion de hardware resuelta una sola vez en el arranque y congelada en propiedades
/// estaticas de solo lectura. Ningun camino caliente vuelve a consultar <c>IsSupported</c>.
/// </summary>
internal static class SimdCaps
{
    /// <summary>Nivel detectado. Inmutable durante toda la vida del proceso.</summary>
    public static SimdTier Tier { get; } = Detect();

    /// <summary>Nombre legible del nivel, para diagnostico y logs de arranque.</summary>
    public static string TierName { get; } = Tier.ToString();

    /// <summary>Ancho del registro vectorial mas ancho utilizable, en bytes.</summary>
    public static int VectorBytes { get; } = Tier switch
    {
        SimdTier.Avx512 => 64,
        SimdTier.Avx2 => 32,
        _ => 16,
    };

    /// <summary>True cuando la ruta de 256/512 bits esta disponible.</summary>
    public static bool HasAvx => Tier is SimdTier.Avx2 or SimdTier.Avx512;

    /// <summary>True cuando el hardware es Arm64 con AdvSIMD.</summary>
    public static bool IsAdvSimd => Tier == SimdTier.AdvSimd;

    /// <summary>True cuando SSE4.2 o superior esta disponible en x86/x64.</summary>
    public static bool HasSse42 => Tier is SimdTier.Sse42 or SimdTier.Avx2 or SimdTier.Avx512;

    private static SimdTier Detect()
    {
        // En Arm64 el conjunto es fijo: AdvSIMD siempre presente en Armv8-A.
        if (RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
        {
            return AdvSimd.IsSupported ? SimdTier.AdvSimd : SimdTier.Scalar;
        }

        // Orden descendente: se elige la ruta mas ancha que el JIT pueda sostener.
        if (Avx512F.IsSupported && Avx512BW.IsSupported)
        {
            return SimdTier.Avx512;
        }

        if (Avx2.IsSupported && Fma.IsSupported)
        {
            return SimdTier.Avx2;
        }

        if (Sse42.IsSupported)
        {
            return SimdTier.Sse42;
        }

        // x64 garantiza SSE2; un x86 antiguo puede quedarse en el camino escalar.
        return Sse2.IsSupported ? SimdTier.Sse2 : SimdTier.Scalar;
    }
}
