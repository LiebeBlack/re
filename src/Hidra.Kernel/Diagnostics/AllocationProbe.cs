namespace Hidra.Kernel.Diagnostics;

/// <summary>
/// Mide bytes asignados en el monton administrado por el hilo actual.
/// </summary>
/// <remarks>
/// Solo para verificacion. Llamar a esto desde el hilo de audio de produccion seria
/// contraproducente: la lectura del contador de asignacion no es gratis y ademas impide
/// que el JIT optimice el codigo que rodea la medicion.
/// </remarks>
internal readonly struct AllocationProbe
{
    private readonly long _start;

    private AllocationProbe(long start) => _start = start;

    /// <summary>Bytes asignados por este hilo desde el inicio de la sonda.</summary>
    public long AllocatedBytes => GC.GetAllocatedBytesForCurrentThread() - _start;

    /// <summary>Inicia la medicion en el hilo que llama.</summary>
    public static AllocationProbe Begin() => new(GC.GetAllocatedBytesForCurrentThread());
}
