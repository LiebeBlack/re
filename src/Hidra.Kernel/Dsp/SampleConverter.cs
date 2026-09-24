using System.Numerics;
using System.Runtime.InteropServices;

namespace Hidra.Kernel.Dsp;

/// <summary>Codificacion de las muestras de un flujo.</summary>
internal enum SampleEncoding
{
    /// <summary>Enteros con signo de 16 bits.</summary>
    Pcm16 = 0,

    /// <summary>Enteros con signo de 24 bits empaquetados en 3 bytes.</summary>
    Pcm24 = 1,

    /// <summary>Enteros con signo de 32 bits.</summary>
    Pcm32 = 2,

    /// <summary>Coma flotante de 32 bits, en el rango [-1, 1].</summary>
    Float32 = 3,
}

/// <summary>
/// Conversion de muestras de coma flotante al formato entero del dispositivo.
/// </summary>
/// <remarks>
/// <para>
/// Hace falta porque el motor en modo exclusivo entrega al dispositivo EXACTAMENTE el
/// formato que el dispositivo declara. Un DAC que trabaja a 24 bits enteros no acepta
/// flotantes, y convertir en el momento de escribir el buffer es la unica forma de no
/// meter una etapa de resampleo o un formato intermedio por software.
/// </para>
/// <para>
/// El recorte a [-1, 1] se vectoriza porque es la parte que recorre todas las muestras con
/// dos comparaciones. La conversion a entero se mantiene escalar: en .NET las conversiones
/// vectoriales de float a entero exigen controlar el modo de redondeo y acabarian
/// dependiendo de la ruta de hardware que el JIT elija, que es justo lo que no se quiere en
/// una ruta cuyo resultado se oye.
/// </para>
/// <para>
/// El escalado se hace en doble precision aunque las muestras sean de simple. No es
/// capricho: el entero mas grande de 32 bits con signo, 2147483647, NO es representable en
/// coma flotante simple y se redondea a 2147483648. Multiplicar ahi por la muestra positiva
/// mas alta da un valor fuera del rango de entero, y la conversion resultante es el minimo
/// negativo: la muestra mas fuerte posible se convierte en la mas debil. Es una inversion de
/// escala completa y se oye como un chasquido, no como un error de redondeo. En doble los
/// 2147483647 son exactos y la saturacion cae del lado correcto.
/// </para>
/// <para>
/// No se aplica tramado SOLO en la conversion a 32 bits enteros: el escalon de cuantizado
/// de 24 bits en punto fijo esta a -168 dBFS respecto a la escala completa, ciento de
/// decibelios por debajo del umbral auditivo en cualquier escucha razonable, y el coste
/// del tramado ahi es puro gasto. A 16 y 24 bits, en cambio, SI se aplica: convertir a
/// 16 bits sin tramado produce distorsion de cuantizacion CORRELACIONADA con la senal
/// (armónicos que no estaban en el original); el tramado triangular TPDF la sustituye
/// por un ruido blanco a -93 dBFS que el oido trata como un fondo siseante y no como
/// un artefacto, y con senal debil la diferencia es audible, no teorica.
/// </para>
/// <para>
/// El generador de aleatorios del tramado no reserva memoria y se consume en el hilo de
/// audio: dos uniformes por muestra a 16 bits son unas 200 000 llamadas por segundo en
/// estereo, que no miden nada frente al resto del bloque. La distribucion TPDF
/// (triangular, resta de dos uniformes) es la que aplanza exactamente el error de
/// cuantizado; un uniforme simple dejaria ruido modulado por la senal.
/// </para>
/// </remarks>
internal static class SampleConverter
{
    /// <summary>Control global del tramado. Desactivarlo deja la conversion determinista pura.</summary>
    /// <remarks>
    /// El dither TPDF a 16 bits se oye como un siseo de fondo a unos -93 dBFS; en una cadena
    /// de escucha silenciosa hay quien lo prefiere ausente, y la propiedad existe para eso.
    /// El valor por defecto es activado: sin tramado la distorsion de cuantizacion correla-
    /// cionada con la senal es objetivamente peor que el siseo.
    /// </remarks>
    public static bool EnableDither { get; set; } = true;

    /// <summary>
    /// Generador congruente xorshift32, determinista y sin asignaciones.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Tres desplazamientos y tres XOR por numero, un ciclo completo de 2^32-1, y nada de
    /// estado global: el estado viaja por referencia y pertenece a la cadena de conversion
    /// que este generando el dither. Ser determinista NO es un capricho: la misma sesion
    /// debe producir exactamente el mismo ruido en cada ejecucion, porque un dither que
    /// cambia entre pasadas rompe la comparabilidad de las verificaciones y, con material
    /// conocido, un ingeniero nota la variacion.
    /// </para>
    /// <para>
    /// La semilla inicial es arbitraria pero fija; el unico requisito es que no sea cero
    /// (con estado cero el xorshift se queda en cero para siempre).
    /// </para>
    /// </remarks>
    /// <param name="state">Estado del generador, actualizado in situ.</param>
    /// <returns>Uniforme en [0, 1) con resolucion de 24 bits.</returns>
    private static double NextUniform(ref uint state)
    {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;

        // Se toman los 24 bits altos: suficientes para un dither subaudible y baratos de
        // normalizar con una sola multiplicacion.
        return (state >> 8) * (1.0 / 16777216.0);
    }

    /// <summary>
    /// Reinicia el estado de los generadores de dither a la semilla fija de arranque.
    /// </summary>
    /// <remarks>
    /// Existe para las verificaciones: la misma senal convertida despues de reiniciar debe
    /// producir exactamente los mismos bytes, que es la propiedad que garantiza que el
    /// dither es determinista. La reproduccion en marcha no tiene motivo para llamarla.
    /// </remarks>
    public static void ResetDitherState()
    {
        _ditherState16 = 0x9E3779B9u;
        _ditherState24 = 0x853C49E7u;
    }

    /// <summary>Ruido TPDF: dos uniformes restados, distribucion triangular en (-1, +1).</summary>
    /// <remarks>
    /// La definicion estandar de TPDF es DOS escalones LSB PICO A PICO, es decir +-1 LSB
    /// alrededor del valor ideal. Un multiplicador mayor aplanza el error igualmente pero
    /// eleva el suelo de ruido tres decibelios mas de lo necesario.
    /// </remarks>
    private static double NextTpdf(ref uint state) =>
        NextUniform(ref state) - NextUniform(ref state);
    /// <summary>
    /// Limitador de pico verdadero de rodilla suave: lineal por debajo del umbral, tangente
    /// hiperbolica por encima.
    /// </summary>
    /// <remarks>
    /// <para>
    /// El recorte duro produce armónicos de orden alto que no estaban en la senal y se oyen
    /// como crujido. La curva tanh comprime SOLO lo que sobresale del umbral, con derivada
    /// continua en la rodilla, y por debajo de el la senal pasa matematicamente intacta.
    /// Con el umbral a -0.1 dBFS el margen comprimido es inaudible y el techo queda garantizado.
    /// </para>
    /// <para>
    /// La forma de la rodilla: para |x| &gt; knee, y = tanh((|x| - knee) / w) * a + knee,
    /// con w elegido para que la pendiente en la rodilla sea 1 (continuidad de derivada) y
    /// a ajustado para que el limite asintotico sea exactamente 1.0. La aplicacion es
    /// simetrica y no introduce componente continua.
    /// </para>
    /// </remarks>
    /// <param name="source">Muestras de entrada, normalmente dentro de [-1, 1].</param>
    /// <param name="destination">Destino, recorrible in situ (puede ser la misma memoria).</param>
    public static unsafe void SoftLimit(ReadOnlySpan<float> source, Span<float> destination)
    {
        // -0.1 dBFS en lineal: el punto a partir del cual la curva empieza a comprimir.
        const float knee = 0.988553f;
        // Con width = amplitude = 1 - knee, la curva y = (1-knee)*tanh((x-knee)/(1-knee)) +
        // knee cumple las dos condiciones exactamente: pendiente unitaria en la rodilla
        // (sech^2(0) = 1) y techo asintotico 1.0 (1-knee+knee). No hay ajuste a ojo.
        const float width = 1f - knee;
        const float amplitude = 1f - knee;

        int count = Math.Min(source.Length, destination.Length);
        if (count == 0)
        {
            return;
        }

        fixed (float* sourcePointer = source)
        fixed (float* destinationPointer = destination)
        {
            for (int i = 0; i < count; i++)
            {
                float x = sourcePointer[i];
                float magnitude = MathF.Abs(x);

                float limited;
                if (magnitude <= knee)
                {
                    limited = x;
                }
                else
                {
                    float compressed = MathF.Tanh((magnitude - knee) / width) * amplitude + knee;
                    limited = MathF.CopySign(compressed, x);
                }

                destinationPointer[i] = limited;
            }
        }
    }

    /// <summary>Recorta <paramref name="source"/> a [-1, 1] dentro de <paramref name="destination"/>.</summary>
    public static unsafe void Clamp(ReadOnlySpan<float> source, Span<float> destination)
    {
        int count = Math.Min(source.Length, destination.Length);
        if (count == 0)
        {
            return;
        }

        int width = Vector<float>.Count;
        int i = 0;

        Vector<float> lower = new(-1f);
        Vector<float> upper = new(1f);

        fixed (float* sourcePointer = source)
        fixed (float* destinationPointer = destination)
        {
            for (; i + width <= count; i += width)
            {
                Vector<float> value = Vector.Load(sourcePointer + i);
                Vector<float> clamped = Vector.Min(Vector.Max(value, lower), upper);
                Vector.Store(clamped, destinationPointer + i);
            }

            for (; i < count; i++)
            {
                destinationPointer[i] = Math.Clamp(sourcePointer[i], -1f, 1f);
            }
        }
    }

    /// <summary>
    /// Convierte muestras flotantes ya recortadas al formato entero indicado.
    /// </summary>
    /// <param name="source">Muestras en [-1, 1].</param>
    /// <param name="destination">Destino con el numero de bytes exacto del formato.</param>
    /// <param name="encoding">Formato de destino.</param>
    public static void FromClampedFloat(ReadOnlySpan<float> source, Span<byte> destination, SampleEncoding encoding)
    {
        switch (encoding)
        {
            case SampleEncoding.Float32:
                CastAndCopy(source, destination);
                break;

            case SampleEncoding.Pcm16:
                WritePcm16(source, destination);
                break;

            case SampleEncoding.Pcm24:
                WritePcm24(source, destination);
                break;

            case SampleEncoding.Pcm32:
                WritePcm32(source, destination);
                break;

            default:
                throw new ArgumentOutOfRangeException(nameof(encoding), encoding, "Codificacion no soportada.");
        }
    }

    /// <summary>Numero de bytes que ocupan <paramref name="sampleCount"/> muestras.</summary>
    public static int BytesFor(int sampleCount, SampleEncoding encoding) => encoding switch
    {
        SampleEncoding.Pcm16 => sampleCount * 2,
        SampleEncoding.Pcm24 => sampleCount * 3,
        SampleEncoding.Pcm32 => sampleCount * 4,
        SampleEncoding.Float32 => sampleCount * 4,
        _ => throw new ArgumentOutOfRangeException(nameof(encoding), encoding, "Codificacion no soportada."),
    };

    private static void CastAndCopy(ReadOnlySpan<float> source, Span<byte> destination)
    {
        Span<float> target = MemoryMarshal.Cast<byte, float>(destination);
        int count = Math.Min(source.Length, target.Length);
        source[..count].CopyTo(target);
    }

    /// <summary>Estado del generador de dither para PCM16, compartido por todas las llamadas.</summary>
    /// <remarks>
    /// Un unico estado por proceso es suficiente: el dither no necesita ser independiente
    /// entre canales, solo entre muestras consecutivas. Ser estatico evita que la interfaz
    /// de conversion (que ya existe y consumen varios puntos de la cadena) cambie de firma.
    /// </remarks>
    private static uint _ditherState16 = 0x9E3779B9u;

    /// <summary>Estado del generador de dither para PCM24.</summary>
    private static uint _ditherState24 = 0x853C49E7u;

    private static void WritePcm16(ReadOnlySpan<float> source, Span<byte> destination)
    {
        Span<short> target = MemoryMarshal.Cast<byte, short>(destination);
        int count = Math.Min(source.Length, target.Length);

        if (!EnableDither)
        {
            // Sin tramado la conversion es pura: mismo redondeo, mismo recorte, cero ruido.
            for (int i = 0; i < count; i++)
            {
                double scaled = (double)source[i] * 32767.0;
                target[i] = (short)Math.Clamp(Math.Round(scaled, MidpointRounding.AwayFromZero), -32767, 32767);
            }

            return;
        }

        for (int i = 0; i < count; i++)
        {
            // El tramado entra ANTES del redondeo: es el ruido el que rompe la correlacion
            // entre la senal y el error de cuantizado, no un ajuste posterior. El recorte
            // final evita que el propio tramado envuelva una muestra de escala plena al
            // signo opuesto por complemento a dos.
            double dithered = ((double)source[i] * 32767.0) + NextTpdf(ref _ditherState16);
            target[i] = (short)Math.Clamp(Math.Round(dithered, MidpointRounding.AwayFromZero), -32767, 32767);
        }
    }

    private static void WritePcm24(ReadOnlySpan<float> source, Span<byte> destination)
    {
        int count = Math.Min(source.Length, destination.Length / 3);

        if (!EnableDither)
        {
            for (int i = 0; i < count; i++)
            {
                int sample = (int)Math.Clamp(
                    Math.Round((double)source[i] * 8388607.0, MidpointRounding.AwayFromZero),
                    -8388607,
                    8388607);
                int offset = i * 3;

                destination[offset] = (byte)sample;
                destination[offset + 1] = (byte)(sample >> 8);
                destination[offset + 2] = (byte)(sample >> 16);
            }

            return;
        }

        for (int i = 0; i < count; i++)
        {
            // A 24 bits el tramado es una poliza: el escalon cae a -144 dBFS y la dis-
            // torsion correlacionada ya no sobresale del ruido del propio material. Se
            // conserva por uniformidad de criterio en las dos profundidades donde aplica,
            // con el mismo recorte final de seguridad.
            int sample = (int)Math.Clamp(
                Math.Round(((double)source[i] * 8388607.0) + (NextTpdf(ref _ditherState24) / 256.0), MidpointRounding.AwayFromZero),
                -8388607,
                8388607);
            int offset = i * 3;

            // Complemento a dos en little endian: los bytes bajos de un entero negativo ya
            // son su representacion correcta, no hace falta tratarlos aparte.
            destination[offset] = (byte)sample;
            destination[offset + 1] = (byte)(sample >> 8);
            destination[offset + 2] = (byte)(sample >> 16);
        }
    }

    private static void WritePcm32(ReadOnlySpan<float> source, Span<byte> destination)
    {
        Span<int> target = MemoryMarshal.Cast<byte, int>(destination);
        int count = Math.Min(source.Length, target.Length);

        for (int i = 0; i < count; i++)
        {
            target[i] = (int)Math.Round((double)source[i] * 2147483647.0, MidpointRounding.AwayFromZero);
        }
    }
}
