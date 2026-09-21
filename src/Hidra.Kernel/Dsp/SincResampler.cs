using System.Numerics;
using Hidra.Kernel.Memory;

namespace Hidra.Kernel.Dsp;

/// <summary>
/// Remuestreador polifasico de interpolacion sinc con ventana de Kaiser.
/// </summary>
/// <remarks>
/// <para>
/// Esta pieza no es opcional en el diseno: WASAPI en modo exclusivo acepta UNICAMENTE el
/// formato nativo del dispositivo, asi que reproducir material a 44.1 kHz sobre un DAC que
/// trabaja a 48 kHz es imposible sin convertir la frecuencia de muestreo. Una conversion
/// por interpolacion lineal, que es lo que hace un remuestreador ingenuo, mete distorsion
/// de intermodulacion audible; de ahi el kernel sinc con ventana.
/// </para>
/// <para>
/// La tabla de fases se normaliza a ganancia unitaria en continua, fase a fase. Eso hace
/// que una senal de continua salga exactamente como entro, con independencia de la fase
/// fraccionaria, y elimina el rizado periodico que aparece cuando se normaliza la tabla
/// entera en vez de cada fase.
/// </para>
/// <para>
/// El filtro es simetrico y por tanto no causal: la salida va retrasada
/// <see cref="LatencyInInputSamples"/> muestras respecto a la entrada. Quien consume debe
/// aportar ese margen por delante.
/// </para>
/// </remarks>
internal sealed unsafe class SincResampler : IDisposable
{
    /// <summary>Numero de subfases de la tabla polifasica.</summary>
    public const int PhaseCount = 512;

    /// <summary>Coeficientes por fase.</summary>
    public const int TapsPerPhase = 64;

    private const int Lag = (TapsPerPhase / 2) - 1;

    private readonly AlignedBuffer<float> _table;
    private readonly double _ratio;
    private double _nextPosition;
    private bool _disposed;

    /// <summary>Construye el remuestreador y precalcula la tabla de fases.</summary>
    /// <param name="inputRate">Frecuencia de muestreo de origen, en Hz.</param>
    /// <param name="outputRate">Frecuencia de muestreo de destino, en Hz.</param>
    /// <param name="transitionRatio">Fraccion de la banda de paso utilizable. Por debajo de 1 deja margen para la transicion del filtro.</param>
    /// <param name="kaiserBeta">Parametro beta de la ventana de Kaiser: a mayor valor, mas atenuacion de lobulo lateral y transicion mas ancha.</param>
    public SincResampler(int inputRate, int outputRate, double transitionRatio = 0.92, double kaiserBeta = 8.5)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(inputRate);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(outputRate);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(transitionRatio);

        _ratio = (double)inputRate / outputRate;
        _table = new AlignedBuffer<float>(PhaseCount * TapsPerPhase);
        BuildTable(transitionRatio, kaiserBeta);
        _nextPosition = Lag;
    }

    /// <summary>Relacion de conversion, entrada dividida por salida.</summary>
    public double Ratio => _ratio;

    /// <summary>
    /// Retraso en muestras de entrada. La salida 0 corresponde a la posicion
    /// <see cref="LatencyInInputSamples"/> del flujo de entrada. Es una propiedad del
    /// diseno del filtro, no de la instancia, de ahi que sea estatica.
    /// </summary>
    public static int LatencyInInputSamples => Lag;

    /// <summary>Posicion absoluta del flujo de entrada que producira la proxima muestra de salida.</summary>
    public double NextPosition => _nextPosition;

    /// <summary>Reinicia la posicion del flujo.</summary>
    public void Reset() => _nextPosition = Lag;

    /// <summary>
    /// Convierte lo que permita el bloque de entrada disponible. Devuelve el numero de
    /// muestras producidas, que es menor que <paramref name="output"/> cuando al bloque le
    /// falta el margen de anticipacion del filtro; el llamante debe aportar mas entrada y
    /// volver a invocar con un indice de origen mayor.
    /// </summary>
    /// <param name="input">Muestras de entrada de un solo canal.</param>
    /// <param name="inputStartIndex">Indice absoluto del flujo al que corresponde <c>input[0]</c>.</param>
    /// <param name="output">Destino de las muestras convertidas.</param>
    /// <returns>Muestras escritas en <paramref name="output"/>.</returns>
    public int Process(ReadOnlySpan<float> input, long inputStartIndex, Span<float> output)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        if (input.IsEmpty || output.IsEmpty)
        {
            return 0;
        }

        long inputEnd = inputStartIndex + input.Length;
        int produced = 0;

        fixed (float* source = input)
        fixed (float* destination = output)
        {
            while (produced < output.Length)
            {
                double position = _nextPosition;
                long center = (long)Math.Floor(position);
                long first = center - Lag;

                if (first < inputStartIndex || first + TapsPerPhase > inputEnd)
                {
                    break;
                }

                int phase = (int)(((position - center) * PhaseCount) + 0.5);
                if (phase >= PhaseCount)
                {
                    phase = PhaseCount - 1;
                }

                float* kernel = _table.TypedPointer + (phase * TapsPerPhase);
                float* samples = source + (int)(first - inputStartIndex);

                destination[produced] = Dot(samples, kernel, TapsPerPhase);
                produced++;
                _nextPosition += _ratio;
            }
        }

        return produced;
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _table.Dispose();
    }

    /// <summary>
    /// Producto escalar vectorizado. El ancho lo elige el JIT. La suma por lanes reasocia
    /// respecto al camino escalar, por lo que la equivalencia con una referencia escalar se
    /// verifica con tolerancia, no bit a bit.
    /// </summary>
    private static float Dot(float* samples, float* kernel, int count)
    {
        int width = Vector<float>.Count;
        int i = 0;

        Vector<float> accumulator = Vector<float>.Zero;
        for (; i + width <= count; i += width)
        {
            accumulator += Vector.Load(samples + i) * Vector.Load(kernel + i);
        }

        float total = Vector.Sum(accumulator);
        for (; i < count; i++)
        {
            total += samples[i] * kernel[i];
        }

        return total;
    }

    private void BuildTable(double transitionRatio, double kaiserBeta)
    {
        // Al reducir la frecuencia de muestreo hay que cortar por debajo del Nyquist de
        // destino; al aumentarla no hace falta cortar nada, la banda de paso ya cabe entera.
        double scale = transitionRatio * Math.Min(1.0, 1.0 / _ratio);
        double halfWidth = TapsPerPhase / 2.0;
        double betaNormalizer = BesselI0(kaiserBeta);
        float* table = _table.TypedPointer;

        // Fuera del bucle: stackalloc dentro de una iteracion reservaria en cada vuelta y
        // es exactamente lo que no se quiere en un bucle caliente.
        Span<double> weights = stackalloc double[TapsPerPhase];

        for (int phase = 0; phase < PhaseCount; phase++)
        {
            double fraction = (double)phase / PhaseCount;
            double sum = 0.0;

            for (int tap = 0; tap < TapsPerPhase; tap++)
            {
                // Distancia desde el centro del kernel hasta la muestra, en unidades de entrada.
                double distance = ((tap - Lag) - fraction);
                double argument = scale * distance;

                double sinc = argument == 0.0
                    ? 1.0
                    : Math.Sin(Math.PI * argument) / (Math.PI * argument);

                double normalized = distance / halfWidth;
                double window = Math.Abs(normalized) >= 1.0
                    ? 0.0
                    : BesselI0(kaiserBeta * Math.Sqrt(1.0 - (normalized * normalized))) / betaNormalizer;

                double weight = scale * sinc * window;
                weights[tap] = weight;
                sum += weight;
            }

            // Ganancia unitaria en continua por fase: es lo que evita el rizado periodico.
            double inverse = sum != 0.0 ? 1.0 / sum : 0.0;
            float* destination = table + (phase * TapsPerPhase);
            for (int tap = 0; tap < TapsPerPhase; tap++)
            {
                destination[tap] = (float)(weights[tap] * inverse);
            }
        }
    }

    /// <summary>
    /// Funcion de Bessel modificada de primera especie y orden cero, por su serie de
    /// potencias. Converge en pocos terminos para los beta que se usan aqui.
    /// </summary>
    private static double BesselI0(double value)
    {
        double half = value / 2.0;
        double halfSquared = half * half;
        double term = 1.0;
        double sum = 1.0;

        for (int k = 1; k < 64; k++)
        {
            term *= halfSquared / (k * k);
            sum += term;
            if (term < 1e-18 * sum)
            {
                break;
            }
        }

        return sum;
    }
}
