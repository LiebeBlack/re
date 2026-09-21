using System.Globalization;
using System.Text;
using Hidra.Audio;
using Hidra.Kernel.Dsp;
using Hidra.Kernel.Memory;

namespace Hidra.Verify;

/// <summary>
/// Comprueba la cadena completa de lectura de archivos: decodificacion por Media Foundation,
/// conversion de frecuencia, correspondencia de canales y entrega a traves de la cola.
/// </summary>
/// <remarks>
/// <para>
/// Esta suite cubre la parte del motor que si se puede verificar sin hardware. El motor de
/// salida necesita un dispositivo, pero la cadena que produce las muestras no: se puede
/// ejercitar entera construyendo un archivo con contenido conocido y examinando lo que sale.
/// </para>
/// <para>
/// La comprobacion que de verdad importa aqui es la frecuencia dominante de la salida. Medir
/// solo que haya senal no detectaria un error de conversion: un remuestreador mal construido
/// produce una senal perfectamente audible pero con el tono desplazado. Analizar el espectro
/// y exigir que el pico siga en 440 Hz es lo unico que distingue una conversion correcta de
/// una que suena.
/// </para>
/// </remarks>
internal static class FilePipelineTests
{
    private const int DeviceRate = 48000;
    private const int DeviceChannels = 2;
    private const int FftSize = 8192;
    private const int RenderBlockFrames = 480;

    /// <summary>Frecuencia del tono de prueba.</summary>
    private const double ToneHz = 440.0;

    /// <summary>Amplitud del tono de prueba.</summary>
    private const double ToneAmplitude = 0.5;

    /// <summary>Duracion de los archivos de prueba, en segundos.</summary>
    private const double Duration = 1.5;

    /// <summary>Ejecuta la suite completa.</summary>
    public static void Run()
    {
        string directory = Path.Combine(Path.GetTempPath(), "hidra-verify");

        try
        {
            Directory.CreateDirectory(directory);

            string stereo44 = Path.Combine(directory, "tono-44100-est.wav");
            string mono22 = Path.Combine(directory, "tono-22050-mono.wav");
            string stereo48 = Path.Combine(directory, "tono-48000-est.wav");

            WriteWav(stereo44, 44100, 2, ToneHz, ToneAmplitude);
            WriteWav(mono22, 22050, 1, ToneHz, ToneAmplitude);
            WriteWav(stereo48, 48000, 2, ToneHz, ToneAmplitude);

            // Sin conversion: misma frecuencia y mismos canales. Es el camino que debe ser
            // exacto, y sirve de referencia para juzgar los demas.
            Harness.Suite("archivo/directo", () => VerifyResampling(stereo44, 44100, 2, 44100, 2));

            // Conversion hacia arriba: el caso que obliga el modo exclusivo, porque el
            // dispositivo solo admite su frecuencia nativa.
            Harness.Suite("archivo/remuestreo-al-alza", () => VerifyResampling(stereo44, 44100, 2, DeviceRate, DeviceChannels));

            // Conversion hacia abajo, que activa el recorte de banda del filtro. Es la
            // direccion que produce aliasing si la tabla de fases esta mal construida.
            Harness.Suite("archivo/remuestreo-a-la-baja", () => VerifyResampling(stereo48, DeviceRate, 2, 44100, 2));

            // Mono de origen sobre un dispositivo estereo: conversion de frecuencia y de
            // correspondencia de canales a la vez.
            Harness.Suite("archivo/mono-a-estereo", () => VerifyResampling(mono22, 22050, 1, DeviceRate, DeviceChannels));

            Harness.Suite("archivo/inalcanzable", () => VerifyMissingFile());
            Harness.Suite("archivo/canales-incompatibles", () => VerifyChannelMismatch(mono22));

            Harness.Suite("archivo/busqueda/pausa", () => VerifySeekPaused(stereo48));
            Harness.Suite("archivo/busqueda/al-centro", () => VerifySeekWhilePlaying(stereo48, 0.5));
            Harness.Suite("archivo/busqueda/hacia-atras", () => VerifySeekWhilePlaying(stereo48, 0.25));
        }
        finally
        {
            TryDeleteDirectory(directory);
        }
    }

    /// <summary>
    /// Abre un archivo y examina lo que la cadena entrega.
    /// </summary>
    /// <param name="path">Archivo de origen.</param>
    /// <param name="sourceRate">Frecuencia del archivo, segun el contenido escrito.</param>
    /// <param name="sourceChannels">Canales del archivo.</param>
    /// <param name="deviceRate">Frecuencia que se declara para el dispositivo.</param>
    /// <param name="deviceChannels">Canales que se declaran para el dispositivo.</param>
    private static void VerifyResampling(string path, int sourceRate, int sourceChannels, int deviceRate, int deviceChannels)
    {
        using PlaybackPipeline pipeline = new();
        pipeline.Configure(deviceRate, deviceChannels);
        pipeline.Load(path);

        Harness.Check(pipeline.SourceFormat.SampleRate == sourceRate, $"la frecuencia declarada debe ser {sourceRate}");
        Harness.Check(pipeline.SourceFormat.Channels == sourceChannels, $"los canales declarados deben ser {sourceChannels}");
        Harness.Check(!pipeline.IsPlaying, "un archivo recien cargado no debe estar reproduciendose");

        pipeline.Play();
        Harness.Check(pipeline.IsPlaying, "tras pedir reproduccion debe estar activo");

        // El decodificador debe llenar la cola por delante del consumidor. Si esto no ocurre,
        // la reproduccion dependeria del azar de la planificacion y se oirian cortes.
        const int InitialFill = 1 << 16;
        DateTime deadline = DateTime.UtcNow.AddSeconds(10);

        while (pipeline.BufferedSamples < InitialFill && !pipeline.EndOfStream && DateTime.UtcNow < deadline)
        {
            Thread.Sleep(5);
        }

        Harness.Check(
            pipeline.BufferedSamples >= InitialFill || pipeline.EndOfStream,
            $"el decodificador debe adelantarse al consumidor (en cola {pipeline.BufferedSamples} muestras)");
        Harness.Check(pipeline.LastError is null, $"el decodificador no debe fallar ({pipeline.LastError?.Message})");

        // Se consume exactamente lo disponible, nunca mas, para que las muestras de relleno no
        // contaminen las medidas. Lo que se mide es el contenido, no la capacidad de aguantar.
        float[] block = new float[RenderBlockFrames * deviceChannels];
        List<float> produced = new((int)(sourceRate * Duration * 2));
        long rendered = 0;

        while (true)
        {
            int available = pipeline.BufferedSamples / deviceChannels;

            if (available == 0)
            {
                if (pipeline.EndOfStream)
                {
                    break;
                }

                Thread.Sleep(1);
                continue;
            }

            int frames = Math.Min(available, RenderBlockFrames);
            Span<float> destination = block.AsSpan(0, frames * deviceChannels);
            pipeline.Render(destination, deviceChannels);

            foreach (float sample in destination)
            {
                produced.Add(sample);
            }

            rendered += frames;

            if (rendered > deviceRate * Duration * 4)
            {
                break;
            }
        }

        Harness.Check(pipeline.EndOfStream, "el archivo debe agotarse");
        Harness.Check(rendered > 0, "debe entregarse al menos un bloque de audio");
        Harness.Check(pipeline.UnderrunSamples == 0, $"no debe faltar material (faltaron {pipeline.UnderrunSamples} muestras)");

        float[] samples = [.. produced];
        Harness.Finite(samples, "la salida no debe contener NaN ni infinitos");

        double peak = 0;
        double sumSquares = 0;

        foreach (float sample in samples)
        {
            double magnitude = Math.Abs(sample);
            peak = Math.Max(peak, magnitude);
            sumSquares += (double)sample * sample;
        }

        Harness.Check(peak > 0.05, $"la salida no puede ser silencio (pico {peak:F4})");
        Harness.Close(ToneAmplitude, peak, 0.05, "el pico debe corresponder a la amplitud del tono");

        // Relacion entre lo entregado y lo leido. Un error de velocidad de reproduccion, como
        // el que produce un remuestreador mal construido, aparece aqui de inmediato.
        long sourceFrames = (long)(sourceRate * Duration);
        double expectedRatio = (double)deviceRate / sourceRate;
        double measuredRatio = (double)rendered / sourceFrames;

        // El filtro es no causal: las ultimas muestras del archivo no se pueden convertir
        // porque les falta el margen de anticipacion. Es una perdida de decenas de muestras
        // sobre cientos de miles, no un error de velocidad, de ahi la tolerancia relativa.
        Harness.Close(expectedRatio, measuredRatio, expectedRatio * 0.005, "la cantidad entregada debe corresponder a la relacion de conversion");

        double dominant = DominantFrequency(samples, deviceChannels, deviceRate);
        Harness.Close(ToneHz, dominant, 8.0, "el tono dominante debe conservarse pese a la conversion");

        // Con correspondencia mono a estereo los dos canales deben ser identicos: cualquier
        // desviacion significaria que el entrelazado lee mas alla del canal que le toca.
        if (sourceChannels == 1 && deviceChannels == 2)
        {
            bool identical = true;
            for (int i = 0; i + 1 < samples.Length; i += 2)
            {
                if (samples[i] != samples[i + 1])
                {
                    identical = false;
                    break;
                }
            }

            Harness.Check(identical, "los dos canales deben recibir la misma muestra al duplicar mono");
        }

        Console.WriteLine(
            string.Create(
                CultureInfo.InvariantCulture,
                $"  {Path.GetFileName(path)} {sourceRate} Hz/{sourceChannels}ch -> {deviceRate} Hz/{deviceChannels}ch: "
                + $"{rendered} fotogramas, pico {peak:F4}, dominante {dominant:F1} Hz, relacion {measuredRatio:F5}"));
    }

    /// <summary>
    /// Comprobacion compartida: la posicion pedida queda reflejada en el acumulador y el
    /// material que sale despues conserva el tono. La frecuencia dominante es el unico
    /// indicador que distingue un salto bien aplicado de uno que silencia, repite o desplaza
    /// el contenido.
    /// </summary>
    private static void CheckSeekOutcome(PlaybackPipeline pipeline, int deviceRate, int deviceChannels, TimeSpan target)
    {
        // El hilo decodificador aplica la peticion en su proxima vuelta.
        DateTime deadline = DateTime.UtcNow.AddSeconds(5);

        while (Math.Abs(pipeline.Position.Ticks - target.Ticks) > 100_000 && DateTime.UtcNow < deadline)
        {
            Thread.Sleep(5);
        }

        // Tolerancia de un bloque de render: el acumulador solo avanza cuando el hilo de audio
        // entrega material de la nueva posicion, y ese material llega por bloques.
        long tolerance = 200_000; // veinte milisegundos en unidades de cien nanosegundos
        Harness.Check(
            Math.Abs(pipeline.Position.Ticks - target.Ticks) <= tolerance,
            $"la posicion debe reflejar la busqueda (posicion {pipeline.Position.TotalMilliseconds:F1} ms, "
            + $"objetivo {target.TotalMilliseconds:F1} ms)");

        // En regimen: el tono debe seguir siendo el mismo despues del salto.
        pipeline.Play();

        // El analisis espectral lee desde el cuarto central de la senal una ventana entera:
        // con menos de cuatro tercios de la transformada la lectura se sale del arreglo, que
        // es exactamente el fallo que produjo la primera version de esta prueba.
        float[] block = new float[RenderBlockFrames * deviceChannels];
        List<float> produced = new(FftSize * 4);
        deadline = DateTime.UtcNow.AddSeconds(10);

        while (produced.Count < FftSize * 3 && DateTime.UtcNow < deadline)
        {
            int available = pipeline.BufferedSamples / deviceChannels;

            if (available == 0)
            {
                Thread.Sleep(1);
                continue;
            }

            int frames = Math.Min(available, RenderBlockFrames);
            Span<float> destination = block.AsSpan(0, frames * deviceChannels);
            pipeline.Render(destination, deviceChannels);

            for (int i = 0; i < frames * deviceChannels; i++)
            {
                produced.Add(destination[i]);
            }
        }

        float[] samples = [.. produced];
        Harness.Check(samples.Length >= FftSize, "debe haber material suficiente tras la busqueda");
        Harness.Finite(samples, "la salida tras la busqueda no debe contener NaN ni infinitos");

        double peak = 0;

        foreach (float sample in samples)
        {
            peak = Math.Max(peak, Math.Abs(sample));
        }

        Harness.Check(peak > 0.05, $"la salida tras la busqueda no puede ser silencio (pico {peak:F4})");

        double dominant = DominantFrequency(samples, deviceChannels, deviceRate);
        Harness.Close(ToneHz, dominant, 8.0, "el tono debe conservarse tras la busqueda");
    }

    /// <summary>Buscar con el archivo detenido no debe arrancar la reproduccion.</summary>
    private static void VerifySeekPaused(string path)
    {
        using PlaybackPipeline pipeline = new();
        pipeline.Configure(DeviceRate, DeviceChannels);
        pipeline.Load(path);
        pipeline.Seek(TimeSpan.FromSeconds(Duration / 2));

        DateTime deadline = DateTime.UtcNow.AddSeconds(5);

        while (pipeline.Position < TimeSpan.FromSeconds(0.5) && DateTime.UtcNow < deadline)
        {
            Thread.Sleep(5);
        }

        Harness.Check(!pipeline.IsPlaying, "buscar en pausa no debe arrancar la reproduccion");

        // La comprobacion del contenido reproduce por necesidad: el material ya esta en cola
        // por el pre-llenado de la busqueda, y lo que se verifica aqui es que sea el correcto.
        CheckSeekOutcome(pipeline, DeviceRate, DeviceChannels, TimeSpan.FromSeconds(Duration / 2));
    }

    /// <summary>Buscar mientras suena debe reanudar solo, con tono intacto.</summary>
    private static void VerifySeekWhilePlaying(string path, double fraction)
    {
        using PlaybackPipeline pipeline = new();
        pipeline.Configure(DeviceRate, DeviceChannels);
        pipeline.Load(path);
        pipeline.Play();

        // Esperar a que el arranque sea un hecho antes de pedir el salto.
        DateTime deadline = DateTime.UtcNow.AddSeconds(5);

        while (pipeline.BufferedSamples < 1 << 15 && DateTime.UtcNow < deadline)
        {
            Thread.Sleep(5);
        }

        TimeSpan target = TimeSpan.FromSeconds(Duration * fraction);
        pipeline.Seek(target);
        CheckSeekOutcome(pipeline, DeviceRate, DeviceChannels, target);
        Harness.Check(pipeline.IsRendering, "tras buscar durante la reproduccion debe seguir sonando");
    }

    private static void VerifyMissingFile()
    {
        using PlaybackPipeline pipeline = new();
        pipeline.Configure(DeviceRate, DeviceChannels);

        string missing = Path.Combine(Path.GetTempPath(), "hidra-verify", "no-existe-en-absoluto.wav");
        bool threw = false;

        try
        {
            pipeline.Load(missing);
        }
        catch (FileNotFoundException)
        {
            threw = true;
        }

        Harness.Check(threw, "abrir un archivo inexistente debe fallar con un error claro");
        Harness.Check(pipeline.SourcePath is null, "un archivo que no se pudo abrir no debe quedar cargado");
    }

    private static void VerifyChannelMismatch(string path)
    {
        using PlaybackPipeline pipeline = new();

        // Un archivo mono sobre un dispositivo de seis canales no tiene correspondencia
        // directa: debe rechazarse con un motivo explicito en lugar de inventar una mezcla.
        pipeline.Configure(DeviceRate, 6);
        bool threw = false;
        string? message = null;

        try
        {
            pipeline.Load(path);
        }
        catch (NotSupportedException exception)
        {
            threw = true;
            message = exception.Message;
        }

        Harness.Check(threw, "una correspondencia de canales no soportada debe rechazarse");
        Harness.Check(message?.Contains("canales", StringComparison.OrdinalIgnoreCase) == true, "el rechazo debe explicar el motivo");
    }

    /// <summary>
    /// Frecuencia del pico espectral de la salida, medida sobre una ventana en regimen
    /// permanente para no capturar el transitorio inicial.
    /// </summary>
    private static double DominantFrequency(float[] interleaved, int channels, int sampleRate)
    {
        int frameCount = interleaved.Length / channels;

        if (frameCount < FftSize)
        {
            return 0;
        }

        using AlignedBuffer<float> real = new(FftSize / 2);
        using AlignedBuffer<float> imaginary = new(FftSize / 2);
        using AlignedBuffer<float> windowed = new(FftSize);
        using AlignedBuffer<float> window = new(FftSize);
        using FftKernel fft = new(FftSize);

        WindowFunctions.Fill(WindowKind.Hann, window.Span);

        // Mitad de la senal: se evita el arranque y el final, donde el filtro del
        // remuestreador todavia no esta en regimen o ya no tiene material.
        int offset = (frameCount / 4) * channels;
        int index = 0;

        for (int frame = 0; frame < FftSize; frame++)
        {
            windowed.Span[index++] = interleaved[offset + (frame * channels)];
        }

        WindowFunctions.Apply(window.Span, windowed.Span, windowed.Span);
        fft.ForwardReal(windowed.Span, real.Span, imaginary.Span);

        int bestBin = 1;
        double bestPower = 0;

        for (int bin = 1; bin < real.Length; bin++)
        {
            double power = ((double)real.Span[bin] * real.Span[bin]) + ((double)imaginary.Span[bin] * imaginary.Span[bin]);

            if (power > bestPower)
            {
                bestPower = power;
                bestBin = bin;
            }
        }

        return (double)bestBin * sampleRate / FftSize;
    }

    /// <summary>Escribe un archivo PCM de 16 bits con un tono puro.</summary>
    private static void WriteWav(string path, int sampleRate, int channels, double frequency, double amplitude)
    {
        int frames = (int)(sampleRate * Duration);
        int dataBytes = frames * channels * 2;

        using FileStream stream = File.Create(path);
        using BinaryWriter writer = new(stream, Encoding.ASCII, leaveOpen: false);

        writer.Write(Encoding.ASCII.GetBytes("RIFF"));
        writer.Write(36 + dataBytes);
        writer.Write(Encoding.ASCII.GetBytes("WAVE"));
        writer.Write(Encoding.ASCII.GetBytes("fmt "));
        writer.Write(16);
        writer.Write((short)1);
        writer.Write((short)channels);
        writer.Write(sampleRate);
        writer.Write(sampleRate * channels * 2);
        writer.Write((short)(channels * 2));
        writer.Write((short)16);
        writer.Write(Encoding.ASCII.GetBytes("data"));
        writer.Write(dataBytes);

        for (int frame = 0; frame < frames; frame++)
        {
            double phase = 2.0 * Math.PI * frequency * frame / sampleRate;
            short value = (short)Math.Round(Math.Sin(phase) * amplitude * short.MaxValue);

            for (int channel = 0; channel < channels; channel++)
            {
                writer.Write(value);
            }
        }
    }

    private static void TryDeleteDirectory(string directory)
    {
        try
        {
            Directory.Delete(directory, recursive: true);
        }
        catch (IOException)
        {
            // Un archivo temporal que no se puede borrar no invalida la verificacion.
        }
    }
}
