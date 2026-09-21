using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace Hidra.Kernel.Memory;

/// <summary>
/// Bloque de memoria nativa alineado a linea de cache, con liberacion determinista.
/// </summary>
/// <typeparam name="T">Tipo no administrado almacenado.</typeparam>
/// <remarks>
/// Deliberadamente SIN finalizador. Un finalizador aqui solo aportaria jitter: la
/// liberacion tiene que ser determinista y nunca puede caer dentro de una recoleccion
/// que compita con el hilo de callback de audio. Si un buffer se filtra, es un error de
/// construccion que el arnes debe detectar, no algo que el GC deba parchear.
/// La alineacion a 64 bytes evita cruces de linea de cache en los accesos vectoriales.
/// </remarks>
internal sealed unsafe class AlignedBuffer<T> : IDisposable
    where T : unmanaged
{
    /// <summary>Alineacion por defecto: una linea de cache completa.</summary>
    public const nuint Alignment = 64;

    private void* _pointer;
    private int _length;
    private bool _disposed;

    /// <summary>Reserva <paramref name="length"/> elementos puestos a cero.</summary>
    public AlignedBuffer(int length)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(length);

        _length = length;
        if (length == 0)
        {
            return;
        }

        nuint bytes = (nuint)length * (nuint)sizeof(T);
        _pointer = NativeMemory.AlignedAlloc(bytes, Alignment);
        NativeMemory.Clear(_pointer, bytes);
    }

    /// <summary>Numero de elementos.</summary>
    public int Length => _length;

    /// <summary>True cuando hay memoria reservada.</summary>
    public bool IsAllocated => _pointer is not null;

    /// <summary>Puntero crudo al primer elemento, o null si la longitud es cero.</summary>
    public void* Pointer
    {
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        get => _pointer;
    }

    /// <summary>Puntero tipado al primer elemento, o null si la longitud es cero.</summary>
    public T* TypedPointer
    {
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        get => (T*)_pointer;
    }

    /// <summary>Vista <see cref="Span{T}"/> sobre la memoria nativa.</summary>
    public Span<T> Span
    {
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        get => _pointer is null ? default : new Span<T>(_pointer, _length);
    }

    /// <summary>Acceso por referencia, sin comprobacion de limites.</summary>
    public ref T this[int index]
    {
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        get => ref Unsafe.Add(ref Unsafe.AsRef<T>(_pointer), (nint)index);
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;

        if (_pointer is not null)
        {
            NativeMemory.AlignedFree(_pointer);
            _pointer = null;
        }

        _length = 0;
    }
}
