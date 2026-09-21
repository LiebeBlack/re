using System.Numerics;
using System.Runtime.CompilerServices;
using System.Runtime.Intrinsics;
using Hidra.Kernel.Memory;

namespace Hidra.Kernel.Dsp;

/// <summary>
/// FFT compleja radix-2 diezmado en tiempo, in-place, sobre memoria nativa.
/// </summary>
/// <remarks>
/// <para>
/// Las tablas de twiddles se guardan CONTIGUAS por etapa en lugar de usar el truco
/// habitual de una tabla global indexada con paso. La suma de medias longitudes sobre
/// todas las etapas es exactamente n-1 (no n*log2(n)), asi que la tabla completa ocupa
/// 2*(n-1) floats: para n=4096 son 32 KB. A cambio, cada carga vectorial de twiddles es
/// contigua, sin reunir escalares ni permutar registros.
/// </para>
/// <para>
/// La vectorizacion usa <see cref="Vector128{T}"/>, que en x86 emite SSE/SSE4.2 y en
/// Arm64 emite AdvSIMD a partir del MISMO codigo: la ruta de respaldo no es una copia
/// escalar mantenida aparte, es el mismo algoritmo con ancho variable.
/// </para>
/// <para>
/// Paridad numerica: el camino vectorial no reasocia ni fusiona operaciones. Cada muestra
/// se multiplica, se suma y se resta en el mismo orden que en el camino escalar y no se
/// emite FMA, por lo que ambos caminos producen resultados identicos bit a bit. El arnes
/// de verificacion lo comprueba muestra a muestra.
/// </para>
/// </remarks>
internal sealed unsafe class FftKernel : IDisposable
{
    private readonly int _size;
    private readonly int _logSize;
    private readonly AlignedBuffer<float> _twiddleCos;
    private readonly AlignedBuffer<float> _twiddleSin;
    private readonly AlignedBuffer<int> _stageOffset;
    private readonly AlignedBuffer<int> _bitReverse;
    private readonly AlignedBuffer<float> _postCos;
    private readonly AlignedBuffer<float> _postSin;
    private bool _disposed;

    /// <summary>Construye el kernel y precalcula todas sus tablas.</summary>
    /// <param name="size">Tamano de la FFT. Potencia de dos, minimo 4.</param>
    public FftKernel(int size)
    {
        if (size < 4 || !BitOperations.IsPow2(size))
        {
            throw new ArgumentOutOfRangeException(nameof(size), size, "El tamano de la FFT debe ser potencia de 2 y mayor o igual que 4.");
        }

        _size = size;
        _logSize = BitOperations.Log2((uint)size);

        // Desplazamiento de la tabla de twiddles de cada etapa. La suma total es size-1.
        _stageOffset = new AlignedBuffer<int>(_logSize + 1);
        int total = 0;
        for (int stage = 0; stage < _logSize; stage++)
        {
            _stageOffset[stage] = total;
            total += 1 << stage;
        }

        _stageOffset[_logSize] = total;

        _twiddleCos = new AlignedBuffer<float>(total);
        _twiddleSin = new AlignedBuffer<float>(total);

        for (int stage = 0; stage < _logSize; stage++)
        {
            int half = 1 << stage;
            int offset = _stageOffset[stage];

            // w[k] = exp(-2*pi*i*k / (2*half)) no depende de size: la misma tabla sirve para
            // cualquier transformada de longitud menor o igual.
            double step = -Math.PI / half;
            for (int k = 0; k < half; k++)
            {
                double angle = step * k;
                _twiddleCos[offset + k] = (float)Math.Cos(angle);
                _twiddleSin[offset + k] = (float)Math.Sin(angle);
            }
        }

        // Permutacion bit-reversa. Para la subtransformada de longitud size/2 se reutiliza
        // esta misma tabla desplazando un bit: invertir log2(size) bits de un indice menor
        // que size/2 coloca siempre un cero en el bit de mas peso, luego basta con >> 1.
        _bitReverse = new AlignedBuffer<int>(size);
        for (int i = 0; i < size; i++)
        {
            uint value = (uint)i;
            uint reversed = 0;
            for (int bit = 0; bit < _logSize; bit++)
            {
                reversed = (reversed << 1) | (value & 1u);
                value >>= 1;
            }

            _bitReverse[i] = (int)reversed;
        }

        // Twiddles de post-proceso de la FFT real: exp(-2*pi*i*k/size) para k en [0, size/2).
        int bins = size >> 1;
        _postCos = new AlignedBuffer<float>(bins);
        _postSin = new AlignedBuffer<float>(bins);
        for (int k = 0; k < bins; k++)
        {
            double angle = -2.0 * Math.PI * k / size;
            _postCos[k] = (float)Math.Cos(angle);
            _postSin[k] = (float)Math.Sin(angle);
        }
    }

    /// <summary>Tamano de la transformada.</summary>
    public int Size => _size;

    /// <summary>Numero de bins utiles de <see cref="ForwardReal"/>.</summary>
    public int BinCount => _size >> 1;

    /// <summary>FFT compleja in-place totalmente vectorizada.</summary>
    public void Forward(Span<float> real, Span<float> imaginary) => Forward(real, imaginary, vectorized: true);

    /// <summary>
    /// FFT compleja in-place con seleccion explicita del camino. El parametro existe para
    /// que el arnes de verificacion pueda contrastar el camino vectorial contra el escalar.
    /// </summary>
    public void Forward(Span<float> real, Span<float> imaginary, bool vectorized)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        if (real.Length < _size || imaginary.Length < _size)
        {
            throw new ArgumentException($"Las senales necesitan al menos {_size} muestras.", nameof(real));
        }

        Permute(real, imaginary, _size, _bitReverse.TypedPointer, shift: 0);

        fixed (float* realPointer = real)
        fixed (float* imaginaryPointer = imaginary)
        {
            for (int stage = 0; stage < _logSize; stage++)
            {
                int half = 1 << stage;
                if (vectorized && half >= Vector128<float>.Count)
                {
                    StageVector(realPointer, imaginaryPointer, _size, half, _twiddleCos.TypedPointer, _twiddleSin.TypedPointer, _stageOffset[stage]);
                }
                else
                {
                    StageScalar(realPointer, imaginaryPointer, _size, half, _twiddleCos.TypedPointer, _twiddleSin.TypedPointer, _stageOffset[stage]);
                }
            }
        }
    }

    /// <summary>
    /// FFT de una senal real mediante empaquetado: cada par de muestras reales viaja como
    /// una muestra compleja, con lo que la transformada efectiva es de la mitad de tamano
    /// y el coste se reduce aproximadamente a la mitad. El desacoplado posterior recupera
    /// los bins de la senal real.
    /// </summary>
    /// <param name="input">Al menos <see cref="Size"/> muestras reales.</param>
    /// <param name="real">Parte real de los bins. Necesita <see cref="BinCount"/> elementos.</param>
    /// <param name="imaginary">Parte imaginaria de los bins. Necesita <see cref="BinCount"/> elementos.</param>
    public void ForwardReal(ReadOnlySpan<float> input, Span<float> real, Span<float> imaginary)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        int bins = _size >> 1;
        if (input.Length < _size)
        {
            throw new ArgumentException($"La entrada necesita al menos {_size} muestras.", nameof(input));
        }

        if (real.Length < bins || imaginary.Length < bins)
        {
            throw new ArgumentException($"La salida necesita al menos {bins} bins.", nameof(real));
        }

        Span<float> realBins = real[..bins];
        Span<float> imaginaryBins = imaginary[..bins];

        for (int i = 0; i < bins; i++)
        {
            realBins[i] = input[2 * i];
            imaginaryBins[i] = input[(2 * i) + 1];
        }

        ForwardHalf(realBins, imaginaryBins);
        Untangle(realBins, imaginaryBins);
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _twiddleCos.Dispose();
        _twiddleSin.Dispose();
        _stageOffset.Dispose();
        _bitReverse.Dispose();
        _postCos.Dispose();
        _postSin.Dispose();
    }

    /// <summary>Transformada compleja de longitud size/2 reutilizando las tablas completas.</summary>
    private void ForwardHalf(Span<float> real, Span<float> imaginary)
    {
        int length = _size >> 1;
        Permute(real, imaginary, length, _bitReverse.TypedPointer, shift: 1);

        fixed (float* realPointer = real)
        fixed (float* imaginaryPointer = imaginary)
        {
            for (int stage = 0; stage < _logSize - 1; stage++)
            {
                int half = 1 << stage;
                if (half >= Vector128<float>.Count)
                {
                    StageVector(realPointer, imaginaryPointer, length, half, _twiddleCos.TypedPointer, _twiddleSin.TypedPointer, _stageOffset[stage]);
                }
                else
                {
                    StageScalar(realPointer, imaginaryPointer, length, half, _twiddleCos.TypedPointer, _twiddleSin.TypedPointer, _stageOffset[stage]);
                }
            }
        }
    }

    /// <summary>Desacopla la FFT de la senal empaquetada en los bins de la senal real.</summary>
    private void Untangle(Span<float> real, Span<float> imaginary)
    {
        int length = _size >> 1;
        if (length < 2)
        {
            return;
        }

        // X[k] = E[k] + w^k * O[k]  y  X[length-k] = conj(E[k] - w^k * O[k]).
        // Solo se recorren k en [0, length/2]: escribir la mitad baja en k y la alta en
        // length-k no colisiona porque la lectura de esta iteracion siempre cae en indices
        // que las iteraciones anteriores todavia no han tocado.
        int halfCount = length >> 1;
        int mask = length - 1;

        for (int k = 0; k <= halfCount; k++)
        {
            int mirror = (length - k) & mask;

            float aReal = real[k];
            float aImag = imaginary[k];
            float bReal = real[mirror];
            float bImag = -imaginary[mirror];

            float evenReal = 0.5f * (aReal + bReal);
            float evenImag = 0.5f * (aImag + bImag);
            float deltaReal = aReal - bReal;
            float deltaImag = aImag - bImag;

            // O = delta / (2i) = delta * (-i/2)
            float oddReal = 0.5f * deltaImag;
            float oddImag = -0.5f * deltaReal;

            float wReal = _postCos[k];
            float wImag = _postSin[k];
            float rotatedReal = (wReal * oddReal) - (wImag * oddImag);
            float rotatedImag = (wReal * oddImag) + (wImag * oddReal);

            real[k] = evenReal + rotatedReal;
            imaginary[k] = evenImag + rotatedImag;

            if (mirror != k)
            {
                real[mirror] = evenReal - rotatedReal;
                imaginary[mirror] = rotatedImag - evenImag;
            }
        }
    }

    private static void Permute(Span<float> real, Span<float> imaginary, int length, int* bitReverse, int shift)
    {
        for (int i = 0; i < length; i++)
        {
            int j = bitReverse[i] >> shift;
            if (j > i)
            {
                (real[i], real[j]) = (real[j], real[i]);
                (imaginary[i], imaginary[j]) = (imaginary[j], imaginary[i]);
            }
        }
    }

    /// <summary>Camino escalar. Tambien es la referencia de paridad del camino vectorial.</summary>
    private static void StageScalar(
        float* real,
        float* imaginary,
        int length,
        int half,
        float* twiddleCos,
        float* twiddleSin,
        int offset)
    {
        int block = half << 1;

        for (int start = 0; start < length; start += block)
        {
            for (int k = 0; k < half; k++)
            {
                int low = start + k;
                int high = low + half;

                float wReal = twiddleCos[offset + k];
                float wImag = twiddleSin[offset + k];
                float highReal = real[high];
                float highImag = imaginary[high];
                float lowReal = real[low];
                float lowImag = imaginary[low];

                float productReal = (wReal * highReal) - (wImag * highImag);
                float productImag = (wReal * highImag) + (wImag * highReal);

                real[low] = lowReal + productReal;
                imaginary[low] = lowImag + productImag;
                real[high] = lowReal - productReal;
                imaginary[high] = lowImag - productImag;
            }
        }
    }

    /// <summary>
    /// Camino vectorial. Opera cuatro mariposas por iteracion sobre cargas contiguas; la
    /// cola que no llega al ancho del vector cae al camino escalar.
    /// </summary>
    private static void StageVector(
        float* real,
        float* imaginary,
        int length,
        int half,
        float* twiddleCos,
        float* twiddleSin,
        int offset)
    {
        int width = Vector128<float>.Count;
        int block = half << 1;

        for (int start = 0; start < length; start += block)
        {
            int k = 0;

            for (; k + width <= half; k += width)
            {
                int low = start + k;
                int high = low + half;

                Vector128<float> wReal = Vector128.Load(twiddleCos + offset + k);
                Vector128<float> wImag = Vector128.Load(twiddleSin + offset + k);
                Vector128<float> highReal = Vector128.Load(real + high);
                Vector128<float> highImag = Vector128.Load(imaginary + high);
                Vector128<float> lowReal = Vector128.Load(real + low);
                Vector128<float> lowImag = Vector128.Load(imaginary + low);

                Vector128<float> productReal = Vector128.Subtract(
                    Vector128.Multiply(wReal, highReal),
                    Vector128.Multiply(wImag, highImag));

                Vector128<float> productImag = Vector128.Add(
                    Vector128.Multiply(wReal, highImag),
                    Vector128.Multiply(wImag, highReal));

                Vector128.Store<float>(Vector128.Add(lowReal, productReal), real + low);
                Vector128.Store<float>(Vector128.Add(lowImag, productImag), imaginary + low);
                Vector128.Store<float>(Vector128.Subtract(lowReal, productReal), real + high);
                Vector128.Store<float>(Vector128.Subtract(lowImag, productImag), imaginary + high);
            }

            for (; k < half; k++)
            {
                int low = start + k;
                int high = low + half;

                float wReal = twiddleCos[offset + k];
                float wImag = twiddleSin[offset + k];
                float highReal = real[high];
                float highImag = imaginary[high];
                float lowReal = real[low];
                float lowImag = imaginary[low];

                float productReal = (wReal * highReal) - (wImag * highImag);
                float productImag = (wReal * highImag) + (wImag * highReal);

                real[low] = lowReal + productReal;
                imaginary[low] = lowImag + productImag;
                real[high] = lowReal - productReal;
                imaginary[high] = lowImag - productImag;
            }
        }
    }
}
