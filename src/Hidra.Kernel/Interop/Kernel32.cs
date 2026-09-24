using System.Runtime.InteropServices;

namespace Hidra.Kernel.Interop;

/// <summary>
/// P/Invoke de kernel32 via <c>LibraryImport</c>: el generador de codigo fuente emite el
/// thunk en tiempo de compilacion, sin reflexion ni marshalling dinamico, de modo que
/// sobrevive al recorte y al AOT.
/// </summary>
internal static partial class Kernel32
{
    internal const uint Infinite = 0xFFFFFFFF;
    internal const uint WaitObject0 = 0x00000000;
    internal const uint WaitTimeout = 0x00000102;
    internal const uint WaitAbandoned = 0x00000080;

    [LibraryImport("kernel32.dll", EntryPoint = "CreateEventW", SetLastError = true, StringMarshalling = StringMarshalling.Utf16)]
    internal static partial nint CreateEvent(
        nint eventAttributes,
        [MarshalAs(UnmanagedType.Bool)] bool manualReset,
        [MarshalAs(UnmanagedType.Bool)] bool initialState,
        string? name);

    [LibraryImport("kernel32.dll", EntryPoint = "SetEvent", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static partial bool SetEvent(nint handle);

    [LibraryImport("kernel32.dll", EntryPoint = "ResetEvent", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static partial bool ResetEvent(nint handle);

    [LibraryImport("kernel32.dll", EntryPoint = "WaitForSingleObject", SetLastError = true)]
    internal static partial uint WaitForSingleObject(nint handle, uint milliseconds);

    [LibraryImport("kernel32.dll", EntryPoint = "WaitForMultipleObjects", SetLastError = true)]
    internal static unsafe partial uint WaitForMultipleObjects(
        uint count,
        nint* handles,
        [MarshalAs(UnmanagedType.Bool)] bool waitAll,
        uint milliseconds);

    [LibraryImport("kernel32.dll", EntryPoint = "CloseHandle", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static partial bool CloseHandle(nint handle);

    [LibraryImport("kernel32.dll", EntryPoint = "GetCurrentThreadId")]
    internal static partial uint GetCurrentThreadId();

    [LibraryImport("kernel32.dll", EntryPoint = "SetThreadAffinityMask", SetLastError = true)]
    internal static partial nuint SetThreadAffinityMask(nint thread, nuint affinityMask);

    [LibraryImport("kernel32.dll", EntryPoint = "GetCurrentThread")]
    internal static partial nint GetCurrentThread();

    [LibraryImport("kernel32.dll", EntryPoint = "QueryPerformanceCounter", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static partial bool QueryPerformanceCounter(out long counter);

    [LibraryImport("kernel32.dll", EntryPoint = "QueryPerformanceFrequency", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static partial bool QueryPerformanceFrequency(out long frequency);

    /// <summary>Mascara de control de denormales de <c>_controlfp_s</c> (<c>_MCW_DN</c>).</summary>
    internal const uint ControlWordDenormalMask = 0x03000000u;

    /// <summary>Modo de aplanado de denormales (<c>_DN_FLUSH</c>): en x64 fija FTZ y DAZ en el MXCSR.</summary>
    internal const uint DenormalFlush = 0x01000000u;

    /// <summary>Valor centinela de fallo: <see cref="RestoreControlWord"/> lo ignora.</summary>
    internal const uint ControlWordFailed = uint.MaxValue;

    /// <summary>
    /// Activa el aplanado de denormales (FTZ/DAZ) en el hilo actual y devuelve el modo
    /// previo para restaurarlo.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Los denormales aparecen solos en una cadena de audio (fades de volumen, colas del
    /// remuestreador, silencios del limitador) y cada operacion con uno cuesta cerca de
    /// cien ciclos de microcodigo. Con el aplanado activo el hardware los convierte en
    /// cero en un ciclo; la perdida numerica esta a -149 dBFS, muy por debajo de cualquier
    /// consideracion auditable.
    /// </para>
    /// <para>
    /// La via es <c>_controlfp_s</c> del CRT y no un acceso directo al MXCSR: en x64,
    /// <c>_DN_FLUSH</c> sobre <c>_MCW_DN</c> fija a la vez los bits FTZ y DAZ del registro,
    /// y la funcion existe en msvcrt.dll y ucrtbase.dll en todas las versiones soportadas,
    /// mientras que los simbolos <c>_stmxcsr</c>/<c>_ldmxcsr</c> NO estan exportados por
    /// ningun CRT de Windows y enlazar a ellos revienta el hilo con
    /// EntryPointNotFoundException. La llamada es por hilo: cada hilo de audio la aplica
    /// en su arranque y la revierte en su salida.
    /// </para>
    /// </remarks>
    /// <returns>El modo de denormales previo, o <see cref="ControlWordFailed"/> si el CRT rechazo la peticion.</returns>
    internal static uint EnableFtzDaz()
    {
        int result = _controlfp_s(out uint current, DenormalFlush, ControlWordDenormalMask);

        return result == 0 ? current : ControlWordFailed;
    }

    /// <summary>Restaura el modo de denormales devuelto por <see cref="EnableFtzDaz"/>.</summary>
    internal static void RestoreControlWord(uint controlWord)
    {
        if (controlWord == ControlWordFailed)
        {
            return;
        }

        // Solo se restaura el campo de denormales: el resto del registro de control es de
        // quien lo haya tocado, y pisarlo entero seria un efecto secundario invisible.
        _ = _controlfp_s(out _, controlWord & ControlWordDenormalMask, ControlWordDenormalMask);
    }

    /// <summary>
    /// Control del coprocesador de coma flotante del CRT. Se declara con DllImport por ser
    /// una funcion variadica-free del CRT y no de la API de Windows; el generador de
    /// LibraryImport no procesa este modulo.
    /// </summary>
    [DllImport("msvcrt.dll", EntryPoint = "_controlfp_s", SetLastError = false, CallingConvention = CallingConvention.Cdecl)]
    private static extern int _controlfp_s(out uint current, uint newValue, uint mask);
}
