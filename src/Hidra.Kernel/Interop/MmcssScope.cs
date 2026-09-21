namespace Hidra.Kernel.Interop;

/// <summary>
/// Registra el hilo actual en MMCSS y lo revierte al salir del ambito.
/// </summary>
/// <remarks>
/// Es un <c>ref struct</c> logico de un solo uso: no se copia a heap y nunca se boxea.
/// Si MMCSS no esta disponible (algun Windows Server sin el servicio, o una sesion sin
/// planificador multimedia) la entrada queda inactiva y el motor sigue funcionando con la
/// prioridad de hilo normal, sin fallar.
/// </remarks>
internal readonly struct MmcssScope : IDisposable
{
    private readonly nint _handle;

    private MmcssScope(nint handle) => _handle = handle;

    /// <summary>True cuando el hilo quedo efectivamente registrado en MMCSS.</summary>
    public bool IsActive => _handle != 0;

    /// <summary>
    /// Entra en la clase multimedia. Devuelve un ambito inactivo si el servicio rechaza
    /// la peticion, en lugar de lanzar: un equipo sin MMCSS debe poder reproducir audio.
    /// </summary>
    public static MmcssScope Enter(
        string taskName = Avrt.ProAudioTask,
        AvrtPriority priority = AvrtPriority.Critical)
    {
        nint handle = Avrt.AvSetMmThreadCharacteristics(taskName, out _);
        if (handle == 0)
        {
            return default;
        }

        if (!Avrt.AvSetMmThreadPriority(handle, priority))
        {
            _ = Avrt.AvRevertMmThreadCharacteristics(handle);
            return default;
        }

        return new MmcssScope(handle);
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (_handle != 0)
        {
            _ = Avrt.AvRevertMmThreadCharacteristics(_handle);
        }
    }
}
