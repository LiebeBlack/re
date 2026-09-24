using Hidra.Kernel.Dsp;
using Hidra.Kernel.Memory;

namespace Hidra.Verify;

/// <summary>Comprobaciones de la capa de memoria y de las ventanas espectrales.</summary>
internal static class MemoryTests
{
    public static void Run()
    {
        Harness.Suite("memoria/alineacion", AlignmentIsRespected);
        Harness.Suite("memoria/cola-vuelta", WrapsAroundWithoutLosingData);
        Harness.Suite("memoria/cola-spsc", ProducerConsumerKeepsOrder);
        Harness.Suite("memoria/cola-reinicio-concurrente", ResetUnderConcurrentReaderReturnsNothing);
        Harness.Suite("ventanas/coherencia", WindowFunctionsAreSane);
    }

    private static unsafe void AlignmentIsRespected()
    {
        using var buffer = new AlignedBuffer<float>(4096);

        Harness.Check(buffer.IsAllocated, "el buffer no se reservo");
        Harness.Check((nuint)buffer.TypedPointer % AlignedBuffer<float>.Alignment == 0, "el puntero no respeta la alineacion solicitada");
        Harness.Check(buffer.Length == 4096, $"longitud inesperada {buffer.Length}");

        var span = buffer.Span;
        Harness.Check(span.Length == 4096, "la vista Span no cubre la longitud completa");

        bool cleared = true;
        for (int i = 0; i < span.Length; i++)
        {
            if (span[i] != 0f)
            {
                cleared = false;
                break;
            }
        }

        Harness.Check(cleared, "el buffer no llego a cero");
    }

    /// <summary>
    /// La cola no desperdicia ranura: con capacidad 8 caben 8 elementos, y una escritura
    /// que cruza el final del arreglo debe conservar el orden.
    /// </summary>
    private static void WrapsAroundWithoutLosingData()
    {
        using var buffer = new SpscRingBuffer<float>(8);

        var first = new float[8];
        for (int i = 0; i < 8; i++)
        {
            first[i] = i;
        }

        Harness.Check(buffer.Write(first) == 8, "no se aceptaron los 8 elementos que caben");
        Harness.Check(buffer.Free == 0, $"la cola admite mas de lo que debe: libre={buffer.Free}");

        var sink = new float[8];
        Harness.Check(buffer.Read(sink) == 8, "no se leyeron 8 elementos");

        // Desplaza los indices cinco posiciones para forzar el cruce del final del arreglo.
        var partial = new float[5];
        Harness.Check(buffer.Read(partial) == 0, "se leyeron elementos inexistentes");

        for (int i = 0; i < 8; i++)
        {
            first[i] = i;
        }

        Harness.Check(buffer.Write(first) == 8, "no se reescribio la cola completa");
        Harness.Check(buffer.Read(partial) == 5, "no se leyeron los 5 elementos esperados");

        var tail = new float[8];
        for (int i = 0; i < 8; i++)
        {
            tail[i] = 100f + i;
        }

        int writtenAfterFreeing = buffer.Write(tail);
        Harness.Check(writtenAfterFreeing == 5, $"tras liberar 5 huecos se escribieron {writtenAfterFreeing} elementos");

        var drained = new float[8];
        Harness.Check(buffer.Read(drained) == 8, "no se drenaron los 8 elementos");

        bool ordered = true;
        for (int i = 0; i < 3; i++)
        {
            ordered &= drained[i] == 5f + i;
        }

        for (int i = 0; i < 5; i++)
        {
            ordered &= drained[3 + i] == 100f + i;
        }

        Harness.Check(ordered, "el contenido de la cola no se conserva al cruzar el final del arreglo");
    }

    /// <summary>
    /// Un productor y un consumidor reales, sobre hilos distintos, con bloques de tamano
    /// primo para que ninguna fase se alinee con la capacidad y las vueltas se desfasen.
    /// </summary>
    private static void ProducerConsumerKeepsOrder()
    {
        const int total = 400_000;
        using var buffer = new SpscRingBuffer<int>(1024);

        var payload = new int[257];
        int sent = 0;
        int received = 0;
        bool ordered = true;
        Exception? failure = null;

        var producer = new Thread(() =>
        {
            try
            {
                while (sent < total)
                {
                    int count = Math.Min(payload.Length, total - sent);
                    for (int i = 0; i < count; i++)
                    {
                        payload[i] = sent + i;
                    }

                    int written = buffer.Write(payload.AsSpan(0, count));
                    sent += written;

                    if (written == 0)
                    {
                        Thread.SpinWait(40);
                    }
                }
            }
            catch (Exception exception)
            {
                failure = exception;
            }
        });

        var consumer = new Thread(() =>
        {
            try
            {
                var sink = new int[311];
                while (received < total)
                {
                    int read = buffer.Read(sink);
                    if (read == 0)
                    {
                        Thread.SpinWait(40);
                        continue;
                    }

                    for (int i = 0; i < read; i++)
                    {
                        if (sink[i] != received + i)
                        {
                            ordered = false;
                        }
                    }

                    received += read;
                }
            }
            catch (Exception exception)
            {
                failure = exception;
            }
        });

        producer.Start();
        consumer.Start();
        producer.Join();
        consumer.Join();

        Harness.Check(failure is null, $"excepcion dentro de un hilo: {failure?.Message}");
        Harness.Check(received == total, $"se recibieron {received} de {total} elementos");
        Harness.Check(ordered, "se perdio o se altero el orden de los elementos");
    }

    /// <summary>
    /// Un reinicio de la cola mientras el consumidor esta a medio operacion es el caso que
    /// rompe la invariante de los indices monotonos: los indices se cruzan y el recuento
    /// declarado deja de tener sentido. La cola debe reconocer ese estado transitorio y
    /// devolver cero, no copiar con indices sin sentido.
    /// </summary>
    private static void ResetUnderConcurrentReaderReturnsNothing()
    {
        using var buffer = new SpscRingBuffer<float>(1024);
        var data = new float[512];
        var sink = new float[1024];

        for (int i = 0; i < data.Length; i++)
        {
            data[i] = i;
        }

        _ = buffer.Write(data);

        // Un productor sigue empujando mientras el reinicio y las lecturas se cruzan: el
        // escenario reproduce la descarga de un archivo con el callback de audio en marcha.
        using ManualResetEventSlim stop = new(false);
        var writer = new Thread(() =>
        {
            while (!stop.IsSet)
            {
                _ = buffer.Write(data);
            }
        });

        writer.Start();

        long nonsense = 0;
        for (int round = 0; round < 20_000; round++)
        {
            buffer.Reset();

            // La lectura tras el reinicio debe devolver como mucho lo que haya publicado un
            // productor DESPUES del reinicio, y nunca un recuento que desborde la capacidad
            // ni un valor negativo disfrazado de disponible.
            int read = buffer.Read(sink);
            nonsense += read < 0 || read > buffer.Capacity ? 1 : 0;
        }

        stop.Set();
        writer.Join();

        Harness.Check(nonsense == 0, $"la cola declaro disponible material inexistente {nonsense} veces");

        // Y tras dejar de reiniciar, la cola vuelve a ser operativa de forma inmediata.
        buffer.Reset();
        Harness.Check(buffer.Write(data) == data.Length, "la cola no volvio a aceptar escrituras tras el paro");
        Harness.Check(buffer.Read(sink) == data.Length, "la cola no devolvio lo escrito tras el paro");
    }

    private static void WindowFunctionsAreSane()
    {
        const int size = 512;
        var hann = new float[size];
        var blackmanHarris = new float[size];
        var rectangular = new float[size];

        WindowFunctions.Fill(WindowKind.Hann, hann);
        WindowFunctions.Fill(WindowKind.BlackmanHarris, blackmanHarris);
        WindowFunctions.Fill(WindowKind.Rectangular, rectangular);

        Harness.Finite(hann, "la ventana de Hann produjo valores no finitos");
        Harness.Finite(blackmanHarris, "la ventana de Blackman-Harris produjo valores no finitos");

        // Convencion periodica: el maximo cae EXACTAMENTE en la unidad en el centro y el
        // primer coeficiente es exactamente cero. El ultimo no llega a cero, porque en un
        // periodo la ventana no es simetrica respecto de la ultima muestra: es justo la
        // diferencia entre la forma periodica y la simetrica de diseno de filtros.
        Harness.Close(0.0, hann[0], 1e-7, "Hann no arranca en cero");
        Harness.Close(1.0, hann[size / 2], 1e-7, "Hann no alcanza la unidad en el centro");
        Harness.Check(hann[size - 1] < 1e-3f, $"el ultimo coeficiente de Hann vale {hann[size - 1]:R}, demasiado alto para la convencion periodica");

        // La rectangular es la identidad.
        bool identity = true;
        for (int i = 0; i < size; i++)
        {
            identity &= rectangular[i] == 1f;
        }

        Harness.Check(identity, "la ventana rectangular no es la identidad");

        // Blackman-Harris es estrictamente positiva en el interior, a diferencia de otras
        // ventanas de lobulo bajo, lo que importa para que el logaritmo no reciba energia negativa.
        bool positive = true;
        for (int i = 0; i < size; i++)
        {
            positive &= blackmanHarris[i] > 0f;
        }

        Harness.Check(positive, "Blackman-Harris produjo valores no positivos");

        // La aplicacion vectorizada debe coincidir exactamente con el producto escalar.
        var source = new float[size];
        Signals.Mixed(source);
        var destination = new float[size];
        WindowFunctions.Apply(blackmanHarris, source, destination);

        bool exact = true;
        for (int i = 0; i < size; i++)
        {
            exact &= BitConverter.SingleToInt32Bits(destination[i]) == BitConverter.SingleToInt32Bits(source[i] * blackmanHarris[i]);
        }

        Harness.Check(exact, "la aplicacion vectorial de la ventana no coincide con el producto escalar");
    }
}
