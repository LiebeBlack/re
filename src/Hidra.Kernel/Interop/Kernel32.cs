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
}
