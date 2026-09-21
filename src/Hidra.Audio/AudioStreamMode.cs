namespace Hidra.Audio;

/// <summary>Regimen de comparticion del dispositivo de audio.</summary>
internal enum AudioStreamMode
{
    /// <summary>
    /// Toma el dispositivo entero. No hay mezcla, ni remuestreo, ni efectos del sistema, y el
    /// formato tiene que ser el nativo del hardware. A cambio, solo puede haber un flujo a la
    /// vez y el dispositivo puede negarse.
    /// </summary>
    Exclusive = 0,

    /// <summary>
    /// Comparte el dispositivo con el resto del sistema a traves del mezclador. Siempre
    /// disponible, pero el flujo pasa por el remuestreador y la cadena de efectos del motor
    /// de audio, de modo que no hay garantia de correspondencia exacta con la fuente.
    /// </summary>
    Shared = 1,
}
