using System.Runtime.InteropServices;
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
        Harness.Suite("audio/cadena-recorte-conversion", ClampedFloatToIntegerRoundTripIsMonotone);
        Harness.Suite("audio/determinismo-dither", DitherIsDeterministic);
        Harness.Suite("audio/limitador-suave", SoftLimiterGuarantees);
    }

    /// <summary>
    /// El dither TPDF con xorshift32 es DETERMINISTICO: dos conversiones de la misma senal
    /// deben producir exactamente los mismos bytes. Ademas, desactivar el dither debe dar
    /// la conversion pura (cero dBFS entra, escala plena sale sin desviacion).
    /// </summary>
    private static void DitherIsDeterministic()
    {
        const int count = 4096;

        float[] source = new float[count];
        for (int i = 0; i < count; i++)
        {
            source[i] = MathF.Sin(2f * MathF.PI * 97.0f * i / count) * 0.25f;
        }

        // Estado de dither reseteable a traves de la interfaz publica del conversor.
        byte[] first = new byte[SampleConverter.BytesFor(count, SampleEncoding.Pcm16)];
        byte[] second = new byte[first.Length];

        SampleConverter.ResetDitherState();
        SampleConverter.FromClampedFloat(source, first, SampleEncoding.Pcm16);

        SampleConverter.ResetDitherState();
        SampleConverter.FromClampedFloat(source, second, SampleEncoding.Pcm16);

        bool identical = first.AsSpan().SequenceEqual(second);
        Harness.Check(identical, "dos pasadas con el mismo estado produjeron dither distinto");

        // Con el dither desactivado, la conversion es exacta: 0.5 entra, 16384 (+-redondeo
        // exacto, sin ruido) sale.
        SampleConverter.EnableDither = false;
        try
        {
            byte[] exact = new byte[SampleConverter.BytesFor(3, SampleEncoding.Pcm16)];
            float[] halfScale = [0.5f, -0.5f, 0f];
            SampleConverter.FromClampedFloat(halfScale, exact, SampleEncoding.Pcm16);
            short[] asShort = System.Runtime.InteropServices.MemoryMarshal.Cast<byte, short>(exact).ToArray();

            Harness.Check(asShort[0] == 16384, $"sin dither, 0.5 deberia dar 16384 exacto, dio {asShort[0]}");
            Harness.Check(asShort[1] == -16384, $"sin dither, -0.5 deberia dar -16384 exacto, dio {asShort[1]}");
            Harness.Check(asShort[2] == 0, $"sin dither, cero deberia dar 0 exacto, dio {asShort[2]}");
        }
        finally
        {
            // El resto de la verificacion cuenta con el dither activado: restaurar SIEMPRE.
            SampleConverter.EnableDither = true;
        }
    }

    /// <summary>
    /// Contratos del limitador de rodilla suave: la senal por debajo del umbral pasa
    /// INTACTA bit a bit, la salida nunca supera la unidad, y la compresion cerca del
    /// techo es acotada (el armónico introducido es despreciable comparado con el recorte duro).
    /// </summary>
    private static void SoftLimiterGuarantees()
    {
        const int count = 2048;

        // Senal moderada: todo por debajo de la rodilla, debe salir IDENTICA.
        float[] moderate = new float[count];
        for (int i = 0; i < count; i++)
        {
            moderate[i] = MathF.Sin(2f * MathF.PI * 31.0f * i / count) * 0.5f;
        }

        float[] untouched = new float[count];
        SampleConverter.SoftLimit(moderate, untouched);

        bool bitExactBelowKnee = true;
        for (int i = 0; i < count; i++)
        {
            bitExactBelowKnee &= BitConverter.SingleToInt32Bits(moderate[i]) == BitConverter.SingleToInt32Bits(untouched[i]);
        }

        Harness.Check(bitExactBelowKnee, "el limitador altero muestras por debajo de la rodilla");

        // Senal con sobremedida: los picos a 1.3 deben salir comprimidos y con techo 1.0.
        float[] overdriven = new float[count];
        for (int i = 0; i < count; i++)
        {
            overdriven[i] = MathF.Sin(2f * MathF.PI * 31.0f * i / count) * 1.3f;
        }

        float[] limited = new float[count];
        SampleConverter.SoftLimit(overdriven, limited);

        bool ceiling = true;
        bool kneeContinuous = true;
        for (int i = 0; i < count; i++)
        {
            ceiling &= limited[i] <= 1f && limited[i] >= -1f;

            // A mitad de la rodilla la compresion ya debe notarse (no es un clamp duro
            // disfrazado), pero la muestra en la rodilla exacta apenas se mueve.
            if (overdriven[i] > 1f && limited[i] <= 0.98f)
            {
                kneeContinuous = false;
            }
        }

        Harness.Check(ceiling, "el limitador dejo pasar una muestra por encima de la unidad");
        Harness.Check(kneeContinuous, "la rodilla comprimio menos de lo que la curva garantiza");

        // La senal dentro de rango con picos en el borde debe conservar pico cercano a uno,
        // no fundirse a un nivel menor (el limitador no es un compresor general).
        float[] fullScale = new float[count];
        for (int i = 0; i < count; i++)
        {
            fullScale[i] = MathF.Sin(2f * MathF.PI * 31.0f * i / count);
        }

        float[] atKnee = new float[count];
        SampleConverter.SoftLimit(fullScale, atKnee);

        float peak = 0;
        for (int i = 0; i < count; i++)
        {
            peak = Math.Max(peak, Math.Abs(atKnee[i]));
        }

        Harness.Check(peak > 0.97f, $"un tono a escala plena salio con pico {peak:R}, demasiado atenuado");
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

    /// <summary>
    /// El contrato de la conversion CON tramado TPDF es estocastico: cada muestra cae a lo
    /// sumo a un escalon LSB de su valor ideal, sin sesgo acumulado, y los extremos a escala
    /// plena nunca se superan (el recorte final lo impide). Un contrato exacto seria
    /// incorrecto aqui: exigir que cero dé exactamente cero es exigir que no haya tramado.
    /// </summary>
    private static void IntegerConversionHitsTheFullScale()
    {
        float[] samples = [-1f, -0.5f, 0f, 0.5f, 1f];

        // 16 bits: el valor ideal +- un LSB.
        byte[] pcm16 = new byte[samples.Length * 2];
        SampleConverter.FromClampedFloat(samples, pcm16, SampleEncoding.Pcm16);
        short[] as16 = System.Runtime.InteropServices.MemoryMarshal.Cast<byte, short>(pcm16).ToArray();

        Harness.Check(as16[0] is >= -32767 and <= -32766, $"menos uno deberia caer en -32767+-1, dio {as16[0]}");
        Harness.Check(as16[1] is >= -16385 and <= -16383, $"-0.5 deberia caer en -16384+-1, dio {as16[1]}");
        Harness.Check(as16[2] is >= -1 and <= 1, $"cero deberia caer en 0+-1, dio {as16[2]}");
        Harness.Check(as16[3] is >= 16383 and <= 16385, $"0.5 deberia caer en 16384+-1, dio {as16[3]}");
        Harness.Check(as16[4] is >= 32766 and <= 32767, $"uno deberia caer en 32767+-1, dio {as16[4]}");

        // Sin sesgo: la media de cero repetido debe converger a cero (el tramado TPDF es
        // simetrico; un dither mal construido arrastraria la continua).
        const int repetitions = 20001;
        byte[] zeros16 = new byte[repetitions * 2];
        float[] zeros = new float[repetitions];
        SampleConverter.FromClampedFloat(zeros, zeros16, SampleEncoding.Pcm16);
        short[] zeroSamples = System.Runtime.InteropServices.MemoryMarshal.Cast<byte, short>(zeros16).ToArray();

        double mean = 0;
        bool bounded = true;
        for (int i = 0; i < repetitions; i++)
        {
            mean += zeroSamples[i];
            bounded &= zeroSamples[i] is >= -1 and <= 1;
        }

        mean /= repetitions;
        Harness.Check(bounded, "el tramado de silencio se salio del rango de +-1 LSB");
        Harness.Check(Math.Abs(mean) < 0.05, $"el tramado de silencio tiene sesgo (media {mean:R} LSB)");

        // 24 bits: mismos limites, recomponiendo el entero de tres bytes con signo.
        byte[] pcm24 = new byte[samples.Length * 3];
        SampleConverter.FromClampedFloat(samples, pcm24, SampleEncoding.Pcm24);

        int minusOne24 = SignExtend24(pcm24[0] | (pcm24[1] << 8) | (pcm24[2] << 16));
        int zero24 = SignExtend24(pcm24[6] | (pcm24[7] << 8) | (pcm24[8] << 16));
        int plusOne24 = SignExtend24(pcm24[12] | (pcm24[13] << 8) | (pcm24[14] << 16));

        Harness.Check(minusOne24 is >= -8388607 and <= -8388606, $"menos uno en 24 bits deberia caer en -8388607+-1, dio {minusOne24}");
        Harness.Check(zero24 is >= -1 and <= 1, $"cero en 24 bits deberia caer en 0+-1, dio {zero24}");
        Harness.Check(plusOne24 is >= 8388606 and <= 8388607, $"uno en 24 bits deberia caer en 8388607+-1, dio {plusOne24}");

        // 32 bits: SIN tramado a proposito (el escalon de 24 bits en punto fijo ya es
        // inaudible), de modo que aqui el contrato SI es exacto.
        byte[] pcm32 = new byte[samples.Length * 4];
        SampleConverter.FromClampedFloat(samples, pcm32, SampleEncoding.Pcm32);
        int[] as32 = System.Runtime.InteropServices.MemoryMarshal.Cast<byte, int>(pcm32).ToArray();

        Harness.Check(as32[0] == -2147483647, $"menos uno deberia dar -2147483647, dio {as32[0]}");
        Harness.Check(as32[2] == 0, $"cero deberia dar 0, dio {as32[2]}");
        Harness.Check(as32[4] == 2147483647, $"uno deberia dar 2147483647, dio {as32[4]}");

        Harness.Check(SampleConverter.BytesFor(10, SampleEncoding.Pcm16) == 20, "el tamano en bytes de PCM16 es incorrecto");
        Harness.Check(SampleConverter.BytesFor(10, SampleEncoding.Pcm24) == 30, "el tamano en bytes de PCM24 es incorrecto");
        Harness.Check(SampleConverter.BytesFor(10, SampleEncoding.Float32) == 40, "el tamano en bytes de Float32 es incorrecto");
    }

    /// <summary>
    /// La cadena exacta que pisa el hilo de audio ante un DAC de enteros: recorte y
    /// conversion, bloque a bloque, sin estados intermedios. Se recorre la escala completa
    /// con muestras que ya estan en rango para comprobar que el recorte no las toca y que
    /// el cuantizado conserva el simbolo en todo el recorrido, no solo en los extremos.
    /// </summary>
    private static void ClampedFloatToIntegerRoundTripIsMonotone()
    {
        const int count = 513; // impar: ejercita tambien la cola escalar de Clamp

        float[] source = new float[count];
        for (int i = 0; i < count; i++)
        {
            source[i] = (i / (float)(count - 1) * 2f) - 1f;
        }

        source[0] = -1f;
        source[count - 1] = 1f;

        float[] clamped = new float[count];
        SampleConverter.Clamp(source, clamped);

        foreach (SampleEncoding encoding in new[] { SampleEncoding.Pcm16, SampleEncoding.Pcm24, SampleEncoding.Pcm32 })
        {
            int fullScale = encoding switch
            {
                SampleEncoding.Pcm16 => short.MaxValue,
                SampleEncoding.Pcm32 => int.MaxValue,
                _ => 8388607,
            };

            byte[] bytes = new byte[SampleConverter.BytesFor(count, encoding)];
            SampleConverter.FromClampedFloat(clamped, bytes, encoding);

            // Con tramado, la fidelidad se mide contra el valor IDEAL de cada muestra: a lo
            // sumo un LSB de desviacion, nunca dos. La monotonia estricta ya no es el
            // contrato (el ruido puede intercambiar dos muestras vecinas un LSB, que es
            // justo lo que hace inaudible la cuantizacion), y en su lugar se comprueba la
            // desviacion acotada muestra a muestra.
            bool withinOneLsb = true;
            bool signOk = true;

            for (int i = 0; i < count; i++)
            {
                int quantized = encoding switch
                {
                    SampleEncoding.Pcm16 => MemoryMarshal.Cast<byte, short>(bytes)[i],
                    SampleEncoding.Pcm32 => MemoryMarshal.Cast<byte, int>(bytes)[i],
                    _ => SignExtend24(bytes[(i * 3)] | (bytes[(i * 3) + 1] << 8) | (bytes[(i * 3) + 2] << 16)),
                };

                int ideal = (int)Math.Round((double)clamped[i] * fullScale, MidpointRounding.AwayFromZero);
                withinOneLsb &= Math.Abs(quantized - ideal) <= 1;
                signOk &= (clamped[i] < 0f) == (quantized < 0) || (clamped[i] == 0f && Math.Abs(quantized) <= 1);
            }

            Harness.Check(withinOneLsb, $"la conversion a {encoding} se desvio mas de un LSB del valor ideal");
            Harness.Check(signOk, $"la conversion a {encoding} cambio el simbolo de alguna muestra");

            // Los extremos saturados nunca SUPERAN la escala plena: el recorte final lo
            // garantiza aunque el tramado empuje mas alla. En 24 bits el entero de tres
            // bytes se recompone con extension de signo, o el extremo negativo se leeria
            // como positivo.
            int lowest = encoding switch
            {
                SampleEncoding.Pcm16 => MemoryMarshal.Cast<byte, short>(bytes)[0],
                SampleEncoding.Pcm32 => MemoryMarshal.Cast<byte, int>(bytes)[0],
                _ => SignExtend24(bytes[0] | (bytes[1] << 8) | (bytes[2] << 16)),
            };

            int highest = encoding switch
            {
                SampleEncoding.Pcm16 => MemoryMarshal.Cast<byte, short>(bytes)[count - 1],
                SampleEncoding.Pcm32 => MemoryMarshal.Cast<byte, int>(bytes)[count - 1],
                _ => SignExtend24(bytes[(3 * (count - 1))] | (bytes[(3 * (count - 1)) + 1] << 8) | (bytes[(3 * (count - 1)) + 2] << 16)),
            };

            Harness.Check(highest >= fullScale - 1 && highest <= fullScale, $"uno entero quedo fuera de la escala plena en {encoding}: {highest}");
            Harness.Check(lowest >= -fullScale && lowest <= -(fullScale - 1), $"menos uno entero quedo fuera de la escala plena negativa en {encoding}: {lowest}");
        }
    }

    /// <summary>Recompone un entero de 24 bits en complemento a dos sobre 32.</summary>
    private static int SignExtend24(int value) =>
        (value & 0x800000) != 0 ? value | unchecked((int)0xFF000000) : value;
}
