using System.Runtime.InteropServices;

namespace Hidra.Kernel.Interop;

/// <summary>
/// Clase de servicio MMCSS. Eleva el hilo de callback al planificador multimedia para que
/// el sistema le garantice una cuota de CPU del 80-90 por ciento y no lo desaloje ante
/// trabajo de prioridad normal. Sin esto, WASAPI Exclusive Mode acumula glitches bajo carga.
/// </summary>
internal static partial class Avrt
{
    /// <summary>
    /// Nombre de tarea de la clase multimedia. "Pro Audio" es la clase que usa el propio
    /// motor de audio de Windows para el hilo de mezcla exclusiva.
    /// </summary>
    internal const string ProAudioTask = "Pro Audio";

    [LibraryImport("avrt.dll", EntryPoint = "AvSetMmThreadCharacteristicsW", SetLastError = true, StringMarshalling = StringMarshalling.Utf16)]
    internal static partial nint AvSetMmThreadCharacteristics(string taskName, out uint taskIndex);

    [LibraryImport("avrt.dll", EntryPoint = "AvSetMmThreadPriority", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static partial bool AvSetMmThreadPriority(nint avrtHandle, AvrtPriority priority);

    [LibraryImport("avrt.dll", EntryPoint = "AvRevertMmThreadCharacteristics", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static partial bool AvRevertMmThreadCharacteristics(nint avrtHandle);
}

/// <summary>Prioridad relativa dentro de la clase multimedia.</summary>
internal enum AvrtPriority
{
    /// <summary>Por debajo de la clase.</summary>
    Low = -1,

    /// <summary>Prioridad normal de la clase.</summary>
    Normal = 0,

    /// <summary>Por encima de la clase.</summary>
    High = 1,

    /// <summary>Maxima prioridad de la clase. Es la que corresponde al hilo de audio.</summary>
    Critical = 2,
}
