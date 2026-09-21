namespace Hidra.Verify;

/// <summary>
/// Generadores de senal deterministas. Se usa un generador congruencial lineal en lugar de
/// <c>Random</c> para que la misma semilla produzca exactamente la misma secuencia en
/// cualquier runtime y cualquier plataforma: una verificacion que cambia de resultado segun
/// la version del runtime no verifica nada.
/// </summary>
internal static class Signals
{
    /// <summary>Mezcla de dos tonos mas ruido de banda ancha, con energia en todo el espectro.</summary>
    public static void Mixed(Span<float> destination)
    {
        uint state = 0x12345678u;
        int n = destination.Length;

        for (int i = 0; i < n; i++)
        {
            state = (state * 1664525u) + 1013904223u;
            float noise = (((state >> 8) & 0xFFFF) / 65536f) - 0.5f;

            double tone1 = 0.60 * Math.Sin(2.0 * Math.PI * 3.0 * i / n);
            double tone2 = 0.30 * Math.Sin(2.0 * Math.PI * 11.0 * i / n);
            destination[i] = (float)(tone1 + tone2) + (noise * 0.05f);
        }
    }

    /// <summary>Senoide pura de amplitud unitaria.</summary>
    public static void Sine(Span<float> destination, double frequencyHz, int sampleRate, double amplitude = 1.0)
    {
        for (int i = 0; i < destination.Length; i++)
        {
            destination[i] = (float)(amplitude * Math.Sin(2.0 * Math.PI * frequencyHz * i / sampleRate));
        }
    }

    /// <summary>Continua pura. Sirve para medir la ganancia en continua de un filtro.</summary>
    public static void Constant(Span<float> destination, float value) => destination.Fill(value);
}
