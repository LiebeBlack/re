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

    /// <summary>Bits FTZ (bit 15) y DAZ (bit 6) del registro de control MXCSR.</summary>
    internal const uint MxCsrFtz = 1u << 15;
    internal const uint MxCsrDaz = 1u << 6;

    /// <summary>
    /// Activa FTZ/DAZ en el hilo actual y devuelve el MXCSR previo para restaurarlo.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Los numeros denormales aparecen solos en una cadena de audio (fades de volumen,
    /// colas del remuestreador, silencios del limitador) y cada operacion con uno cuesta
    /// cerca de cien ciclos de microcodigo. FTZ convierte cualquier resultado denormal en
    /// cero y DAZ trata las entradas denormales como cero, ambos en un ciclo; la perdida
    /// numerica esta a -149 dBFS, muy por debajo de cualquier consideracion auditable.
    /// </para>
    /// <para>
    /// En x86/x64 el registro es MXCSR (instrucciones SSE stmxcsr/ldmxcsr). La llamada
    /// esta escrita en C# directo (no LibraryImport) porque no hay funcion de sistema que
    /// la envuelva: es una instruccion del procesador. En Arm64 el manejo de denormales
    /// es por registro FPCR y hoy no se toca: el hardware AdvSIMD ya los flusha por
    /// defecto en las rutas que usa el JIT.
    /// </para>
    /// </remarks>
    /// <returns>El valor MXCSR anterior del hilo, para <see cref="RestoreControlWord"/>.</returns>
    internal static unsafe uint EnableFtzDaz()
    {
        uint current;

        // stmxcsr [rsp]: guarda el MXCSR del hilo en la pila.
        __stmxcsr(&current);

        uint modified = current | MxCsrFtz | MxCsrDaz;

        // Solo se escribe si cambia: evita el coste de ldmxcsr (que serializa) cuando el
        // hilo ya tenia los bits puestos por un componente anterior.
        if (modified != current)
        {
            __ldmxcsr(modified);
        }

        return current;
    }

    /// <summary>Restaura un MXCSR previamente devuelto por <see cref="EnableFtzDaz"/>.</summary>
    internal static unsafe void RestoreControlWord(uint controlWord)
    {
        __ldmxcsr(controlWord);
    }

    [DllImport("msvcrt.dll", EntryPoint = "_stmxcsr", SetLastError = false, CallingConvention = CallingConvention.Cdecl)]
    private static extern unsafe void __stmxcsr(uint* controlWord);

    [DllImport("msvcrt.dll", EntryPoint = "_ldmxcsr", SetLastError = false, CallingConvention = CallingConvention.Cdecl)]
    private static extern unsafe void __ldmxcsr(uint controlWord);
}
