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
    /// <remarks>
    /// Bajo un <see cref="Reset"/> concurrente los indices pueden cruzarse por una ventana
    /// y la resta sale negativa. Un recuento negativo no significa nada: se devuelve cero
    /// en lugar de propagar un valor que quien llama interpretaria como datos disponibles.
    /// </remarks>
    public int Count
    {
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        get
        {
            long head = Volatile.Read(ref _head);
            long tail = Volatile.Read(ref _tail);
            long count = tail - head;
            return count > 0 ? (int)Math.Min(count, _buffer.Length) : 0;
        }
    }

    /// <summary>Huecos libres para escribir.</summary>
    /// <remarks>
    /// Mismo tratamiento que <see cref="Count"/>: tras un reinicio concurrente el hueco
    /// declarado puede superar la capacidad, y confiar en el haria que el productor
    /// escribiese mas alla de lo que la cola puede sostener.
    /// </remarks>
    public int Free
    {
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        get
        {
            long head = Volatile.Read(ref _head);
            long tail = Volatile.Read(ref _tail);
            long free = (long)_buffer.Length - (tail - head);
            return free > 0 ? (int)Math.Min(free, _buffer.Length) : 0;
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
        long free = (long)_buffer.Length - (tail - head);

        // El mismo cuidado que en Read: un Reset concurrente (descargar un archivo mientras
        // el hilo de audio esta en pleno callback, o vaciar la cola al buscar) puede dejar
        // el hueco declarado por encima de la capacidad durante una ventana. Recortar al
        // tamano del arreglo mantiene la copia dentro de la memoria reservada incluso en
        // ese caso, a costa de perder el bloque, que es lo que ya haria una cola llena.
        int count = (int)Math.Min(Math.Min(free, (long)source.Length), (long)_buffer.Length);
        if (count <= 0)
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

        long head = Volatile.Read(ref _head);
        long tail = Volatile.Read(ref _tail);
        long available = tail - head;

        // Bajo un Reset concurrente los indices pueden cruzarse por una ventana y la resta
        // sale negativa, o el recuento declarado supera la capacidad. Ninguno de los dos
        // estados puede interpretarse: se ignora la lectura y ya se recoge en la vuelta
        // siguiente, cuando los indices vuelvan a ser coherentes. Es lo que mantiene la
        // cola segura aunque el llamante reinicie con un consumidor a medio callback.
        if (available <= 0)
        {
            return 0;
        }

        int count = (int)Math.Min(available, (long)destination.Length);
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

    /// <summary>
    /// Vacia la cola. El contrato estricto es llamarla con ambos hilos detenidos; si un
    /// consumidor o productor esta a medio operacion, las guardas de <see cref="Read"/> y
    /// <see cref="Write"/> reconocen el estado transitorio y devuelven cero en lugar de
    /// copiar con indices sin sentido.
    /// </summary>
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
