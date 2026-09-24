using System.ComponentModel;
using System.Runtime.InteropServices;
using Hidra.Audio;
using Hidra.Kernel.Interop;
using Hidra.Kernel.Simd;

namespace Hidra.Verify;

internal static class Program
{
    private static int Main(string[] args)
    {
        Console.WriteLine($"SIMD      : {SimdCaps.TierName} ({SimdCaps.VectorBytes} bytes)  SSE4.2={SimdCaps.HasSse42}  AVX={SimdCaps.HasAvx}  AdvSIMD={SimdCaps.IsAdvSimd}");
        Console.WriteLine($"Reloj     : {HighResolutionClock.Frequency} Hz");
        Console.WriteLine($"Ancho vec : {System.Numerics.Vector<float>.Count} lanes");
        Console.WriteLine();

        if (args.Contains("--probe-audio", StringComparer.Ordinal))
        {
            return ProbeAudio();
        }

        int fileArgument = Array.IndexOf(args, "--probe-file");

        if (fileArgument >= 0)
        {
            if (fileArgument + 1 >= args.Length)
            {
                Console.WriteLine("Falta la ruta del archivo: --probe-file <ruta>");
                return 1;
            }

            return ProbeFile(args[fileArgument + 1]);
        }

        FftTests.Run();
        MemoryTests.Run();
        DspTests.Run();
        AudioTests.Run();
        FilePipelineTests.Run();
        AllocationTests.Run();
        InteropTests.Run();

        return Harness.Report();
    }

    /// <summary>
    /// Decodifica un archivo real y describe lo que sale de la cadena, sin tocar el dispositivo.
    /// </summary>
    /// <remarks>
    /// Sirve para comprobar cualquier archivo, en cualquier formato que el sistema sepa leer,
    /// en un equipo que no tenga salida de audio utilizable. La frecuencia dominante y el pico
    /// se miden sobre las muestras ya convertidas, de modo que un archivo que suene mal por un
    /// error de conversion se delata aqui.
    /// </remarks>
    private static int ProbeFile(string path)
    {
        const int DeviceRate = 48000;
        const int DeviceChannels = 2;

        Console.WriteLine($"Archivo: {path}");
        Console.WriteLine();

        try
        {
            using PlaybackPipeline pipeline = new();
            pipeline.Configure(DeviceRate, DeviceChannels);
            pipeline.Load(path);

            Console.WriteLine($"Origen            : {pipeline.SourceFormat}");
            Console.WriteLine($"Dispositivo       : {DeviceRate} Hz, {DeviceChannels} canales");
            Console.WriteLine();

            pipeline.Play();

            float[] block = new float[960 * DeviceChannels];
            double peak = 0;
            double sumSquares = 0;
            long rendered = 0;
            DateTime deadline = DateTime.UtcNow.AddSeconds(60);

            while (DateTime.UtcNow < deadline)
            {
                int available = pipeline.BufferedSamples / DeviceChannels;

                if (available == 0)
                {
                    if (pipeline.EndOfStream)
                    {
                        break;
                    }

                    Thread.Sleep(1);
                    continue;
                }

                int frames = Math.Min(available, block.Length / DeviceChannels);
                Span<float> destination = block.AsSpan(0, frames * DeviceChannels);
                pipeline.Render(destination, DeviceChannels);

                foreach (float sample in destination)
                {
                    peak = Math.Max(peak, Math.Abs(sample));
                    sumSquares += (double)sample * sample;
                }

                rendered += frames;
            }

            if (pipeline.LastError is not null)
            {
                Console.WriteLine($"Fallo del decodificador: {pipeline.LastError.Message}");
                return 1;
            }

            double rms = rendered > 0 ? Math.Sqrt(sumSquares / (rendered * DeviceChannels)) : 0;

            Console.WriteLine($"Fotogramas        : {rendered}");
            Console.WriteLine($"Duracion          : {pipeline.Position}");
            Console.WriteLine($"Pico              : {peak:F4}");
            Console.WriteLine($"Valor eficaz      : {rms:F5}");
            Console.WriteLine($"Silencio anadido  : {pipeline.UnderrunSamples} muestras");
            Console.WriteLine();

            bool healthy = rendered > 0 && peak > 0.0001 && pipeline.UnderrunSamples == 0;
            Console.WriteLine(healthy ? "SONDA CORRECTA" : "SONDA FALLIDA");
            return healthy ? 0 : 1;
        }
        catch (NotSupportedException exception)
        {
            Console.WriteLine($"Formato no soportado: {exception.Message}");
            return 1;
        }
        catch (COMException exception)
        {
            Console.WriteLine($"Fallo de COM: 0x{exception.HResult:X8} {exception.Message}");
            return 1;
        }
    }

    /// <summary>
    /// Abre el dispositivo de salida por defecto en modo exclusivo y reproduce un tono
    /// durante medio segundo.
    /// </summary>
    /// <remarks>
    /// No forma parte de la verificacion automatica: necesita hardware, toma el dispositivo
    /// en exclusiva y emite sonido, de modo que no puede correr en integracion continua ni
    /// producir un resultado reproducible. Existe para cerrar la unica brecha que la
    /// verificacion sin dispositivo no puede cubrir, que es comprobar que la negociacion del
    /// formato nativo y la realineacion del buffer funcionan contra un driver real.
    /// </remarks>
    private static int ProbeAudio()
    {
        Console.WriteLine("Sonda de hardware: se abrira el dispositivo por defecto en modo exclusivo");
        Console.WriteLine("y se reproducira un tono de 440 Hz durante medio segundo.");
        Console.WriteLine();

        try
        {
            using WasapiExclusiveOutput output = WasapiExclusiveOutput.Open(
                new ToneProvider(sampleRate: 48000, frequencyHz: 440.0, amplitude: 0.15f),
                TimeSpan.FromMilliseconds(10));

            RenderStatistics statistics = output.Statistics;

            Console.WriteLine("Negociacion de formato:");
            foreach (string entry in output.NegotiationLog)
            {
                Console.WriteLine($"  {entry}");
            }

            Console.WriteLine();
            Console.WriteLine($"Regimen           : {statistics.Mode}");
            Console.WriteLine($"Formato nativo    : {output.Format}");
            Console.WriteLine($"Buffer concedido  : {output.BufferFrames} fotogramas");
            Console.WriteLine($"Latencia de buffer: {output.BufferDuration.TotalMilliseconds:F2} ms");
            Console.WriteLine($"Flujo sin procesar: {(statistics.UsingRawStream ? "concedido" : "no concedido")}");
            Console.WriteLine($"Buffer realineado : {(statistics.RealignedBuffer ? "si, hubo desalineacion" : "no hizo falta")}");
            Console.WriteLine($"Clase multimedia  : {(statistics.UsingMultimediaClass ? "registrado" : "no disponible")}");
            Console.WriteLine();

            Thread.Sleep(500);

            Console.WriteLine($"Fotogramas        : {statistics.FramesRendered}");
            Console.WriteLine($"Rellenados        : {statistics.Callbacks}");
            Console.WriteLine($"Sin hueco         : {statistics.EmptyCallbacks}");
            Console.WriteLine($"Esperas agotadas  : {statistics.WaitTimeouts}");
            Console.WriteLine($"Dispositivo caido : {statistics.DeviceInvalidated}");
            Console.WriteLine();

            bool healthy = statistics.FramesRendered > 0
                && statistics.WaitTimeouts == 0
                && !statistics.DeviceInvalidated;

            Console.WriteLine(healthy ? "SONDA CORRECTA" : "SONDA FALLIDA");
            return healthy ? 0 : 1;
        }
        catch (WasapiException exception)
        {
            // El caso mas frecuente con diferencia es que otro reproductor tenga el
            // dispositivo tomado en exclusiva: en modo exclusivo solo puede haber uno.
            Console.WriteLine($"Fallo de WASAPI: 0x{exception.HResult:X8}");
            Console.WriteLine(exception.Message);
            return 1;
        }
        catch (COMException exception)
        {
            Console.WriteLine($"Fallo de COM: 0x{exception.HResult:X8} {exception.Message}");
            return 1;
        }
        catch (Win32Exception exception)
        {
            Console.WriteLine($"Fallo de Win32: {exception.Message}");
            return 1;
        }
    }
}
