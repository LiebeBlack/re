using System.ComponentModel;
using System.Runtime.InteropServices;

namespace Hidra.Kernel.Interop;

/// <summary>
/// Envoltorio de un objeto de evento del kernel. Es la primitiva sobre la que se apoya el
/// callback de WASAPI en modo exclusivo: el driver senaliza y el hilo de audio espera.
/// </summary>
internal sealed class WaitEvent : IDisposable
{
    private nint _handle;
    private bool _disposed;

    /// <summary>Crea el evento del kernel.</summary>
    /// <param name="manualReset">True para un evento de reinicio manual.</param>
    /// <param name="initialState">True para arrancar senalizado.</param>
    public WaitEvent(bool manualReset, bool initialState)
    {
        _handle = Kernel32.CreateEvent(0, manualReset, initialState, null);
        if (_handle == 0)
        {
            throw new Win32Exception(Marshal.GetLastPInvokeError(), "CreateEventW fallo.");
        }
    }

    /// <summary>Handle nativo, para pasarlo a las APIs de audio.</summary>
    public nint Handle => _handle;

    /// <summary>True mientras el handle siga siendo valido.</summary>
    public bool IsValid => _handle != 0;

    /// <summary>
    /// True si el evento esta senalizado en este instante.
    /// </summary>
    /// <remarks>
    /// Solo es significativo para eventos de reinicio manual: consultar uno automatico
    /// consumiria la senal, que es justo lo contrario de lo que espera quien pregunta.
    /// </remarks>
    public bool IsSet => _handle != 0 && Kernel32.WaitForSingleObject(_handle, 0) == Kernel32.WaitObject0;

    /// <summary>Senaliza el evento.</summary>
    public void Set()
    {
        if (_handle != 0)
        {
            Kernel32.SetEvent(_handle);
        }
    }

    /// <summary>Pone el evento a no senalizado.</summary>
    public void Reset()
    {
        if (_handle != 0)
        {
            Kernel32.ResetEvent(_handle);
        }
    }

    /// <summary>Espera el evento. Devuelve false si expira el plazo.</summary>
    public bool Wait(uint milliseconds) =>
        Kernel32.WaitForSingleObject(_handle, milliseconds) == Kernel32.WaitObject0;

    /// <inheritdoc />
    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;

        if (_handle != 0)
        {
            Kernel32.CloseHandle(_handle);
            _handle = 0;
        }

        GC.SuppressFinalize(this);
    }
}
