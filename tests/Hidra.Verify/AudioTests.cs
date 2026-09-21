using Hidra.Audio;
using Hidra.Kernel.Dsp;
using Windows.Win32.Media.Audio;

namespace Hidra.Verify;

/// <summary>
/// Verificacion de la parte del motor de audio que no necesita dispositivo: la descripcion
/// de formato, la aritmetica de duraciones y la conversion de muestras.
/// </summary>
/// <remarks>
/// El motor en si solo se puede validar contra hardware. Todo lo que se pueda separar de eso
/// se separa y se comprueba aqui, que es la unica forma de que un fallo de aritmetica no se
/// disfrace de fallo de driver.
/// </remarks>
internal static class AudioTests
{
    private static readonly Guid SubTypeFloat = new("00000003-0000-0010-8000-00AA00389B71");

    public static void Run()
    {
        Harness.Suite("audio/descripcion-de-formato", FormatDescriptionIsConsistent);
        Harness.Suite("audio/formato-invalido", InvalidFormatsAreRejected);
        Harness.Suite("audio/duraciones", ReferenceTimesAreExactWhereTheyMustBe);
        Harness.Suite("audio/alineacion-de-buffer", BufferRealignmentNeverAsksForLess);
        Harness.Suite("audio/lectura-de-formato-nativo", NativeFormatsAreReadCorrectly);
        Harness.Suite("audio/mascara-de-canales", ChannelMasksMatchTheLayout);
        Harness.Suite("audio/recorte", ClampingSaturatesEverywhere);
        Harness.Suite("audio/conversion-entera", IntegerConversionHitsTheFullScale);
    }

    private static void FormatDescriptionIsConsistent()
    {
        AudioFormat stereo = new(48000, 2, SampleEncoding.Pcm24);

        Harness.Check(stereo.BlockAlign == 6, $"un fotograma estereo de 24 bits deberia ocupar 6 bytes, ocupa {stereo.BlockAlign}");
        Harness.Check(stereo.AverageBytesPerSecond == 288000, $"el caudal deberia ser 288000, es {stereo.AverageBytesPerSecond}");
        Harness.Check(stereo.BitsPerSample == 24, $"los bits por muestra deberian ser 24, son {stereo.BitsPerSample}");
        Harness.Check(!stereo.IsFloat, "PCM de 24 bits no es coma flotante");

        AudioFormat floatFormat = new(44100, 2, SampleEncoding.Float32);
        Harness.Check(floatFormat.IsFloat, "Float32 deberia reportarse como coma flotante");
        Harness.Check(floatFormat.BlockAlign == 8, $"un fotograma estereo flotante deberia ocupar 8 bytes, ocupa {floatFormat.BlockAlign}");

        Harness.Check(stereo.FramesFor(TimeSpan.FromMilliseconds(10)) == 480, "10 ms a 48 kHz deberian ser 480 fotogramas");
        Harness.Check(stereo == new AudioFormat(48000, 2, SampleEncoding.Pcm24), "dos descripciones iguales no comparan igual");
        Harness.Check(stereo != floatFormat, "descripciones distintas comparan igual");
    }

    private static void InvalidFormatsAreRejected()
    {
        bool rejectedRate = false;
        try
        {
            _ = new AudioFormat(0, 2, SampleEncoding.Pcm16);
        }
        catch (ArgumentOutOfRangeException)
        {
            rejectedRate = true;
        }

        Harness.Check(rejectedRate, "una frecuencia de cero deberia rechazarse");

        bool rejectedChannels = false;
        try
        {
            _ = new AudioFormat(48000, 0, SampleEncoding.Pcm16);
        }
        catch (ArgumentOutOfRangeException)
        {
            rejectedChannels = true;
        }

        Harness.Check(rejectedChannels, "cero canales deberia rechazarse");
    }

    private static void ReferenceTimesAreExactWhereTheyMustBe()
    {
        Harness.Check(ReferenceTime.PerSecond == 10_000_000, "una unidad de referencia es de 100 nanosegundos");
        Harness.Check(ReferenceTime.FromTimeSpan(TimeSpan.FromMilliseconds(10)) == 100_000, "10 ms no son 100000 unidades");
        Harness.Check(ReferenceTime.FromTimeSpan(TimeSpan.FromSeconds(1)) == ReferenceTime.PerSecond, "un segundo no son diez millones de unidades");
        Harness.Check(Math.Abs(ReferenceTime.ToMilliseconds(100_000) - 10.0) < 1e-9, "100000 unidades no son 10 ms");
    }

    /// <summary>
    /// Propiedad clave del manejo de la desalineacion: al convertir el tamano concedido a
    /// duracion y despues de vuelta a fotogramas nunca se pide menos de lo que el dispositivo
    /// concedio. Si se pidiera una fraccion de fotograma menos, el segundo intento volveria a
    /// ser rechazado y el motor entraria en un bucle de reintentos.
    /// </summary>
    private static void BufferRealignmentNeverAsksForLess()
    {
        int[] rates = [44100, 48000, 88200, 96000, 176400, 192000];
        long[] grantedSizes = [256, 441, 480, 512, 1024, 1323, 2048, 4096];

        long requested = ReferenceTime.FromTimeSpan(TimeSpan.FromMilliseconds(10));

        foreach (int rate in rates)
        {
            foreach (long granted in grantedSizes)
            {
                long aligned = ReferenceTime.FromFrames(granted, rate);
                long recovered = ReferenceTime.ToFrames(aligned, rate);

                Harness.Check(
                    recovered >= granted && recovered <= granted + 1,
                    $"a {rate} Hz y {granted} fotogramas concedidos el reintento pide {recovered}");

                // Y el valor ya alineado tiene que ser estable: reconvertirlo no lo mueve.
                Harness.Check(
                    ReferenceTime.FromFrames(granted, rate) == ReferenceTime.FromFrames(recovered, rate),
                    $"la duracion alineada a {rate} Hz no es estable para {granted} fotogramas");
            }
        }

        // El caso documentado por Microsoft: 44100 Hz y 441 fotogramas concedidos equivalen
        // exactamente a los 10 ms pedidos, de ahi que el segundo intento pase.
        Harness.Check(ReferenceTime.FromFrames(441, 44100) == requested, "441 fotogramas a 44100 Hz deberian ser exactamente 10 ms");
        Harness.Check(ReferenceTime.FromFrames(480, 48000) == requested, "480 fotogramas a 48000 Hz deberian ser exactamente 10 ms");
    }

    private static void NativeFormatsAreReadCorrectly()
    {
        // PCM clasico de 16 bits: sin extension, sin mascara de canales.
        WAVEFORMATEX plain = default;
        plain.wFormatTag = 1;
        plain.nChannels = 2;
        plain.nSamplesPerSec = 48000;
        plain.wBitsPerSample = 16;
        plain.nBlockAlign = 4;
        plain.nAvgBytesPerSec = 192000;
        plain.cbSize = 0;

        unsafe
        {
            Harness.Check(WaveFormatBridge.TryRead(&plain, out AudioFormat parsed), "no se pudo leer un formato PCM de 16 bits");
            Harness.Check(parsed.SampleRate == 48000 && parsed.Channels == 2, "se leyeron mal las caracteristicas basicas");
            Harness.Check(parsed.Encoding == SampleEncoding.Pcm16, "la codificacion no es PCM de 16 bits");
            Harness.Check(parsed.ChannelMask == WaveFormatBridge.DefaultChannelMask(2), "no se aplico la mascara estereo por defecto");

            // Extensible flotante a cuatro canales: aqui la mascara la declara el dispositivo.
            WAVEFORMATEXTENSIBLE extensible = default;
            extensible.Format.wFormatTag = 0xFFFE;
            extensible.Format.nChannels = 4;
            extensible.Format.nSamplesPerSec = 96000;
            extensible.Format.wBitsPerSample = 32;
            extensible.Format.nBlockAlign = 16;
            extensible.Format.nAvgBytesPerSec = 1536000;
            extensible.Format.cbSize = 22;
            extensible.dwChannelMask = 0x33;
            extensible.SubFormat = SubTypeFloat;

            Harness.Check(
                WaveFormatBridge.TryRead((WAVEFORMATEX*)&extensible, out AudioFormat wide),
                "no se pudo leer un formato extensible flotante");

            Harness.Check(wide.Encoding == SampleEncoding.Float32, "la codificacion no es coma flotante");
            Harness.Check(wide.Channels == 4, "el numero de canales es incorrecto");
            Harness.Check(wide.ChannelMask == 0x33, "no se respeto la mascara declarada por el dispositivo");

            // Extensible que no declara su extension: leer la mascara seria leer fuera del bloque.
            WAVEFORMATEX truncated = default;
            truncated.wFormatTag = 0xFFFE;
            truncated.nChannels = 2;
            truncated.nSamplesPerSec = 48000;
            truncated.wBitsPerSample = 32;
            truncated.cbSize = 0;

            Harness.Check(!WaveFormatBridge.TryRead(&truncated, out _), "un bloque extensible truncado deberia rechazarse");

            // Formato que el motor no sabe convertir.
            WAVEFORMATEX unsupported = default;
            unsupported.wFormatTag = 1;
            unsupported.nChannels = 2;
            unsupported.nSamplesPerSec = 48000;
            unsupported.wBitsPerSample = 8;
            unsupported.cbSize = 0;

            Harness.Check(!WaveFormatBridge.TryRead(&unsupported, out _), "PCM de 8 bits deberia rechazarse");

            Harness.Check(WaveFormatBridge.BlockSize(&plain) == 18, $"el bloque basico deberia medir 18 bytes, mide {WaveFormatBridge.BlockSize(&plain)}");
            Harness.Check(WaveFormatBridge.BlockSize((WAVEFORMATEX*)&extensible) == 40, $"el bloque extensible deberia medir 40 bytes, mide {WaveFormatBridge.BlockSize((WAVEFORMATEX*)&extensible)}");
        }
    }

    private static void ChannelMasksMatchTheLayout()
    {
        Harness.Check(WaveFormatBridge.DefaultChannelMask(1) == 0x4, "mono deberia ser altavoz central");
        Harness.Check(WaveFormatBridge.DefaultChannelMask(2) == 0x3, "estereo deberia ser izquierdo delante mas derecho delante");
        Harness.Check(WaveFormatBridge.DefaultChannelMask(6) == 0x3F, "5.1 deberia ser 0x3F");
        Harness.Check(WaveFormatBridge.DefaultChannelMask(8) == 0x63F, "7.1 deberia ser 0x63F");
        Harness.Check(WaveFormatBridge.DefaultChannelMask(0) == 0, "cero canales no tiene mascara");
    }

    private static void ClampingSaturatesEverywhere()
    {
        // Longitud impar y valores fuera de rango en varias posiciones: asi se ejercitan
        // tanto el bucle vectorial como la cola escalar.
        float[] source = new float[37];
        for (int i = 0; i < source.Length; i++)
        {
            source[i] = (i - 18) * 0.25f;
        }

        source[0] = -100f;
        source[1] = 100f;
        source[35] = -1.5f;
        source[36] = 1.5f;

        float[] destination = new float[source.Length];
        SampleConverter.Clamp(source, destination);

        bool inRange = true;
        for (int i = 0; i < destination.Length; i++)
        {
            inRange &= destination[i] >= -1f && destination[i] <= 1f;
        }

        Harness.Check(inRange, "el recorte dejo pasar un valor fuera de rango");

        Harness.Close(-1.0, destination[0], 1e-7, "un valor muy negativo deberia saturar a -1");
        Harness.Close(1.0, destination[1], 1e-7, "un valor muy positivo deberia saturar a 1");
        Harness.Close(-1.0, destination[35], 1e-7, "la cola escalar no satura por abajo");
        Harness.Close(1.0, destination[36], 1e-7, "la cola escalar no satura por arriba");

        // Dentro de rango el recorte no debe tocar ni un valor, y fuera de rango debe dejar
        // exactamente el extremo con el signo original. Se recorren todos los indices porque
        // el generador de arriba produce valores dentro y fuera de rango mezclados.
        bool preserved = true;
        bool saturated = true;

        for (int i = 0; i < source.Length; i++)
        {
            if (Math.Abs(source[i]) <= 1f)
            {
                preserved &= Math.Abs(destination[i] - source[i]) < 1e-7f;
            }
            else
            {
                float expected = source[i] > 0f ? 1f : -1f;
                saturated &= Math.Abs(destination[i] - expected) < 1e-7f;
            }
        }

        Harness.Check(preserved, "el recorte altero valores que ya estaban en rango");
        Harness.Check(saturated, "el recorte no llevo al extremo correspondiente un valor fuera de rango");
    }

    private static void IntegerConversionHitsTheFullScale()
    {
        float[] samples = [-1f, -0.5f, 0f, 0.5f, 1f];

        // 16 bits
        byte[] pcm16 = new byte[samples.Length * 2];
        SampleConverter.FromClampedFloat(samples, pcm16, SampleEncoding.Pcm16);
        short[] as16 = System.Runtime.InteropServices.MemoryMarshal.Cast<byte, short>(pcm16).ToArray();

        Harness.Check(as16[0] == -32767, $"menos uno deberia dar -32767, dio {as16[0]}");
        Harness.Check(as16[2] == 0, $"cero deberia dar 0, dio {as16[2]}");
        Harness.Check(as16[4] == 32767, $"uno deberia dar 32767, dio {as16[4]}");

        // 24 bits: se comprueba byte a byte porque no hay tipo nativo de tres bytes.
        byte[] pcm24 = new byte[samples.Length * 3];
        SampleConverter.FromClampedFloat(samples, pcm24, SampleEncoding.Pcm24);

        Harness.Check(pcm24[0] == 0x01 && pcm24[1] == 0x00 && pcm24[2] == 0x80, "menos uno en 24 bits no es 0x800001 en little endian");
        Harness.Check(pcm24[6] == 0x00 && pcm24[7] == 0x00 && pcm24[8] == 0x00, "cero en 24 bits deberia ser todo ceros");
        Harness.Check(pcm24[12] == 0xFF && pcm24[13] == 0xFF && pcm24[14] == 0x7F, "uno en 24 bits no es 0x7FFFFF en little endian");

        // 32 bits
        byte[] pcm32 = new byte[samples.Length * 4];
        SampleConverter.FromClampedFloat(samples, pcm32, SampleEncoding.Pcm32);
        int[] as32 = System.Runtime.InteropServices.MemoryMarshal.Cast<byte, int>(pcm32).ToArray();

        Harness.Check(as32[0] == -2147483647, $"menos uno deberia dar -2147483647, dio {as32[0]}");
        Harness.Check(as32[4] == 2147483647, $"uno deberia dar 2147483647, dio {as32[4]}");

        Harness.Check(SampleConverter.BytesFor(10, SampleEncoding.Pcm16) == 20, "el tamano en bytes de PCM16 es incorrecto");
        Harness.Check(SampleConverter.BytesFor(10, SampleEncoding.Pcm24) == 30, "el tamano en bytes de PCM24 es incorrecto");
        Harness.Check(SampleConverter.BytesFor(10, SampleEncoding.Float32) == 40, "el tamano en bytes de Float32 es incorrecto");
    }
}
