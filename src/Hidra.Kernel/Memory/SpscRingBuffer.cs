using System.Numerics;
using System.Runtime.CompilerServices;

namespace Hidra.Kernel.Memory;

/// <summary>
/// Cola circular sin bloqueo para un productor y un consumidor (SPSC).
/// </summary>
/// <typeparam name="T">Tipo no administrado.</typeparam>
/// <remarks>
/// Productor y consumidor son hilos distintos, cada uno con su propio indice, y el otro
/// indice se lee con semantica de adquisicion/liberacion. No hace falta ningun
/// candado porque ningun hilo escribe el indice del otro: es el patron clasico de
/// publicacion por indice y no requiere instrucciones de barrera adicionales.
/// Capacidad utilizable = <see cref="Capacity"/> (no se desperdicia una ranura) porque
/// los indices son monotonos de 64 bits, no residuos modulo la capacidad.
/// </remarks>
internal sealed unsafe class SpscRingBuffer<T> : IDisposable
    where T : unmanaged
{
    private readonly AlignedBuffer<T> _buffer;
    private readonly int _mask;
    private long _head;
    private long _tail;
    private bool _disposed;

    /// <summary>Crea la cola con la capacidad indicada, que debe ser potencia de dos.</summary>
    public SpscRingBuffer(int capacity)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(capacity, 2);

        if (!BitOperations.IsPow2(capacity))
        {
            throw new ArgumentOutOfRangeException(nameof(capacity), capacity, "La capacidad debe ser potencia de 2.");
        }

        _buffer = new AlignedBuffer<T>(capacity);
        _mask = capacity - 1;
    }

    /// <summary>Numero total de elementos que caben.</summary>
    public int Capacity => _buffer.Length;

    /// <summary>Elementos listos para leer.</summary>
    public int Count
    {
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        get
        {
            long head = Volatile.Read(ref _head);
            long tail = Volatile.Read(ref _tail);
            return (int)(tail - head);
        }
    }

    /// <summary>Huecos libres para escribir.</summary>
    public int Free
    {
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        get
        {
            long head = Volatile.Read(ref _head);
            long tail = Volatile.Read(ref _tail);
            return _buffer.Length - (int)(tail - head);
        }
    }

    /// <summary>
    /// Copia lo que quepa. Devuelve el numero de elementos escritos, que puede ser menor
    /// que el origen si la cola esta llena. Nunca reserva memoria.
    /// </summary>
    public int Write(ReadOnlySpan<T> source)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        if (source.IsEmpty)
        {
            return 0;
        }

        long tail = _tail;
        long head = Volatile.Read(ref _head);
        int free = _buffer.Length - (int)(tail - head);
        int count = Math.Min(free, source.Length);
        if (count == 0)
        {
            return 0;
        }

        int index = (int)(tail & _mask);
        int first = Math.Min(count, _buffer.Length - index);
        T* destination = _buffer.TypedPointer;

        fixed (T* sourcePointer = source)
        {
            Buffer.MemoryCopy(
                sourcePointer,
                destination + index,
                (long)(_buffer.Length - index) * sizeof(T),
                (long)first * sizeof(T));

            if (count > first)
            {
                Buffer.MemoryCopy(
                    sourcePointer + first,
                    destination,
                    (long)index * sizeof(T),
                    (long)(count - first) * sizeof(T));
            }
        }

        Volatile.Write(ref _tail, tail + count);
        return count;
    }

    /// <summary>
    /// Copia lo que haya disponible. Devuelve el numero de elementos leidos.
    /// Nunca reserva memoria.
    /// </summary>
    public int Read(Span<T> destination)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        if (destination.IsEmpty)
        {
            return 0;
        }

        long head = _head;
        long tail = Volatile.Read(ref _tail);
        int available = (int)(tail - head);
        int count = Math.Min(available, destination.Length);
        if (count == 0)
        {
            return 0;
        }

        int index = (int)(head & _mask);
        int first = Math.Min(count, _buffer.Length - index);
        T* source = _buffer.TypedPointer;

        fixed (T* destinationPointer = destination)
        {
            Buffer.MemoryCopy(
                source + index,
                destinationPointer,
                (long)destination.Length * sizeof(T),
                (long)first * sizeof(T));

            if (count > first)
            {
                Buffer.MemoryCopy(
                    source,
                    destinationPointer + first,
                    (long)(destination.Length - first) * sizeof(T),
                    (long)(count - first) * sizeof(T));
            }
        }

        Volatile.Write(ref _head, head + count);
        return count;
    }

    /// <summary>Vacia la cola. Solo puede llamarse con ambos hilos detenidos.</summary>
    public void Reset()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        Volatile.Write(ref _tail, 0);
        Volatile.Write(ref _head, 0);
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _buffer.Dispose();
    }
}
