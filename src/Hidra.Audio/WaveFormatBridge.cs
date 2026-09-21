using Hidra.Kernel.Dsp;
using Windows.Win32.Media.Audio;

namespace Hidra.Audio;

/// <summary>
/// Convierte entre <see cref="AudioFormat"/> y las estructuras nativas de Win32.
/// </summary>
/// <remarks>
/// Esta capa no toma decisiones: solo traduce. Toda la logica comprobable vive en
/// <see cref="AudioFormat"/> y <see cref="ReferenceTime"/>, que no dependen de Win32.
/// </remarks>
internal static class WaveFormatBridge
{
    private const ushort FormatTagPcm = 1;
    private const ushort FormatTagIeeeFloat = 3;
    private const ushort FormatTagExtensible = 0xFFFE;

    /// <summary>Subtipo de medio para PCM entero.</summary>
    private static readonly Guid SubTypePcm = new("00000001-0000-0010-8000-00AA00389B71");

    /// <summary>Subtipo de medio para coma flotante IEEE.</summary>
    private static readonly Guid SubTypeFloat = new("00000003-0000-0010-8000-00AA00389B71");

    private const uint SpeakerFrontLeft = 0x1;
    private const uint SpeakerFrontRight = 0x2;
    private const uint SpeakerFrontCenter = 0x4;
    private const uint SpeakerLowFrequency = 0x8;
    private const uint SpeakerBackLeft = 0x10;
    private const uint SpeakerBackRight = 0x20;
    private const uint SpeakerBackCenter = 0x100;
    private const uint SpeakerSideLeft = 0x200;
    private const uint SpeakerSideRight = 0x400;

    /// <summary>Interpreta el formato nativo del dispositivo.</summary>
    public static unsafe bool TryRead(WAVEFORMATEX* format, out AudioFormat result)
    {
        result = default;

        if (format is null || format->nChannels == 0 || format->nSamplesPerSec == 0)
        {
            return false;
        }

        ushort tag = format->wFormatTag;
        uint channelMask = 0;

        if (tag == FormatTagExtensible)
        {
            // WAVEFORMATEXTENSIBLE anade 22 bytes a la estructura base; si cbSize no los
            // declara, leer el campo de mascara seria leer fuera del bloque.
            if (format->cbSize < 22)
            {
                return false;
            }

            WAVEFORMATEXTENSIBLE* extensible = (WAVEFORMATEXTENSIBLE*)format;
            channelMask = extensible->dwChannelMask;

            if (extensible->SubFormat == SubTypeFloat)
            {
                tag = FormatTagIeeeFloat;
            }
            else if (extensible->SubFormat == SubTypePcm)
            {
                tag = FormatTagPcm;
            }
            else
            {
                return false;
            }
        }

        SampleEncoding? encoding = (tag, format->wBitsPerSample) switch
        {
            (FormatTagPcm, 16) => SampleEncoding.Pcm16,
            (FormatTagPcm, 24) => SampleEncoding.Pcm24,
            (FormatTagPcm, 32) => SampleEncoding.Pcm32,
            (FormatTagIeeeFloat, 32) => SampleEncoding.Float32,
            _ => null,
        };

        if (encoding is null)
        {
            return false;
        }

        result = new AudioFormat(
            (int)format->nSamplesPerSec,
            format->nChannels,
            encoding.Value,
            channelMask != 0 ? channelMask : DefaultChannelMask(format->nChannels));

        return true;
    }

    /// <summary>
    /// Tamano en bytes del bloque de formato completo, contando la extension declarada.
    /// </summary>
    /// <remarks>
    /// El motor inicializa el flujo con el bloque EXACTO que devolvio el dispositivo en lugar
    /// de reconstruir uno equivalente. Es deliberado: un formato reconstruido con los mismos
    /// campos pero distinto <c>wFormatTag</c> es semanticamente identico y sin embargo algunos
    /// drivers lo rechazan. Copiar el bloque original elimina esa clase de fallo.
    /// </remarks>
    public static unsafe int BlockSize(WAVEFORMATEX* format) => sizeof(WAVEFORMATEX) + format->cbSize;

    /// <summary>
    /// Escribe un formato extensible, que es la unica forma de declarar mas de dos canales o
    /// 24 bits.
    /// </summary>
    public static unsafe void Write(in AudioFormat format, WAVEFORMATEXTENSIBLE* destination)
    {
        *destination = default;

        WAVEFORMATEX* header = &destination->Format;
        header->wFormatTag = FormatTagExtensible;
        header->nChannels = (ushort)format.Channels;
        header->nSamplesPerSec = (uint)format.SampleRate;
        header->nAvgBytesPerSec = (uint)format.AverageBytesPerSecond;
        header->nBlockAlign = (ushort)format.BlockAlign;
        header->wBitsPerSample = (ushort)format.BitsPerSample;
        header->cbSize = 22;

        destination->Samples.wValidBitsPerSample = (ushort)format.BitsPerSample;
        destination->dwChannelMask = format.ChannelMask != 0
            ? format.ChannelMask
            : DefaultChannelMask(format.Channels);

        destination->SubFormat = format.IsFloat ? SubTypeFloat : SubTypePcm;
    }

    /// <summary>
    /// Mascara de canales por defecto para un numero de canales dado.
    /// </summary>
    /// <remarks>
    /// La disposicion de los canales no es un detalle cosmetico: sin mascara, un stream de
    /// mas de dos canales no tiene orden definido y el altavoz central puede acabar sonando
    /// por el subwoofer. Las asignaciones de aqui siguen el orden canonico de Windows.
    /// </remarks>
    public static uint DefaultChannelMask(int channels) => channels switch
    {
        1 => SpeakerFrontCenter,
        2 => SpeakerFrontLeft | SpeakerFrontRight,
        3 => SpeakerFrontLeft | SpeakerFrontRight | SpeakerFrontCenter,
        4 => SpeakerFrontLeft | SpeakerFrontRight | SpeakerBackLeft | SpeakerBackRight,
        5 => SpeakerFrontLeft | SpeakerFrontRight | SpeakerFrontCenter | SpeakerBackLeft | SpeakerBackRight,
        6 => SpeakerFrontLeft | SpeakerFrontRight | SpeakerFrontCenter | SpeakerLowFrequency | SpeakerBackLeft | SpeakerBackRight,
        7 => SpeakerFrontLeft | SpeakerFrontRight | SpeakerFrontCenter | SpeakerLowFrequency | SpeakerBackCenter | SpeakerSideLeft | SpeakerSideRight,
        8 => SpeakerFrontLeft | SpeakerFrontRight | SpeakerFrontCenter | SpeakerLowFrequency
             | SpeakerBackLeft | SpeakerBackRight | SpeakerSideLeft | SpeakerSideRight,
        _ => 0,
    };
}
