namespace Hidra.Audio;

/// <summary>
/// Contadores del motor de salida, para diagnostico y para la interfaz.
/// </summary>
/// <remarks>
/// Las escrituras las hace un unico hilo, el de audio, y las lecturas cualquier otro. No hay
/// sincronizacion porque todos los campos son de 32 o 64 bits alineados, de modo que una
/// lectura nunca ve un valor a medias; a lo sumo ve el valor anterior. Para un panel de
/// diagnostico eso es aceptable, y cualquier cerrojo aqui acabaria en el hilo de audio.
/// </remarks>
internal sealed class RenderStatistics
{
    /// <summary>Tamano del buffer concedido por el dispositivo, en fotogramas.</summary>
    public int BufferFrames { get; internal set; }

    /// <summary>Frecuencia de muestreo del flujo, en Hz.</summary>
    public int SampleRate { get; internal set; }

    /// <summary>Fotogramas entregados al dispositivo.</summary>
    public long FramesRendered { get; internal set; }

    /// <summary>Numero de rellenados completados.</summary>
    public long Callbacks { get; internal set; }

    /// <summary>Veces que el callback no encontro hueco que rellenar.</summary>
    public long EmptyCallbacks { get; internal set; }

    /// <summary>Veces que el evento del buffer no llego a tiempo.</summary>
    public long WaitTimeouts { get; internal set; }

    /// <summary>Ultimo numero de fotogramas disponibles en el callback.</summary>
    public int LastAvailableFrames { get; internal set; }

    /// <summary>True cuando el hilo de audio quedo registrado en MMCSS.</summary>
    public bool UsingMultimediaClass { get; internal set; }

    /// <summary>True cuando el dispositivo acepto el flujo sin procesar.</summary>
    public bool UsingRawStream { get; internal set; }

    /// <summary>Regimen con el que quedo abierto el flujo.</summary>
    public AudioStreamMode Mode { get; internal set; }

    /// <summary>True cuando hubo que renegociar el buffer por desalineacion.</summary>
    public bool RealignedBuffer { get; internal set; }

    /// <summary>
    /// True cuando la codificacion se eligio sondeando al dispositivo en lugar de aceptar la
    /// del mezclador del sistema.
    /// </summary>
    public bool FormatNegotiatedByProbing { get; internal set; }

    /// <summary>True cuando el dispositivo desaparecio durante la reproduccion.</summary>
    public bool DeviceInvalidated { get; internal set; }

    /// <summary>Latencia aproximada del buffer, en milisegundos.</summary>
    public double BufferDurationMilliseconds =>
        SampleRate > 0 ? (double)BufferFrames / SampleRate * 1000.0 : 0.0;
}
