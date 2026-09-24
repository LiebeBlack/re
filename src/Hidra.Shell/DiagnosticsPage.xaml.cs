using System.Globalization;
using Hidra.Audio;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Hidra.Shell;

/// <summary>
/// Ventana de diagnostico en vivo del motor de audio.
/// </summary>
/// <remarks>
/// <para>
/// Los contadores del motor los escribe el hilo de audio y se leen sin candados: cada
/// valor puede llegar desfasado en un callback y eso es aceptable para un panel. El
/// sondeo vive en su propio temporizador, a dos hercios: mas rapido no aporta nada y
/// menos deja de parecer vivo.
/// </para>
/// <para>
/// La traza de negociacion no se vuelve a leer: se congela al abrir la ventana, porque
/// describe COMO se abrio el dispositivo y ese hecho no cambia mientras la ventana siga
/// abierta; si el motor se rearma, el panel se reconstruye y lee la traza nueva.
/// </para>
/// </remarks>
public sealed partial class DiagnosticsPage : Window, IDisposable
{
    private const int PollMilliseconds = 500;

    private readonly MainWindow _owner;
    private readonly DispatcherTimer _timer;

    /// <summary>Crea la ventana y arranca el sondeo.</summary>
    public DiagnosticsPage(MainWindow owner)
    {
        InitializeComponent();
        _owner = owner;

        Title = "Diagnostico del motor";
        AppWindow.Resize(new Windows.Graphics.SizeInt32(680, 620));

        NegotiationText.Text = owner.Output is { } output
            ? string.Join(Environment.NewLine, output.NegotiationLog)
            : "(sin motor: no hubo negociacion)";

        // El sondeo esconde su coste detras de la visibilidad: con la ventana oculta no hay
        // nadie leyendo los contadores, de modo que el temporizador se detiene en lugar de
        // escribir TextBlocks que nadie ve.
        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(PollMilliseconds) };
        _timer.Tick += (_, _) => RefreshValues();
        _timer.Start();

        Activated += (_, args) =>
        {
            if (args.WindowActivationState == WindowActivationState.Deactivated
                && NativeWindowMethods.IsIconic(WinRT.Interop.WindowNative.GetWindowHandle(this)))
            {
                _timer.Stop();
            }
            else if (!_timer.IsEnabled)
            {
                _timer.Start();
                RefreshValues();
            }
        };

        RefreshValues();
    }

    /// <inheritdoc />
    public void Dispose()
    {
        _timer.Stop();
    }

    private void RefreshValues()
    {
        if (_owner.Output is not { } output)
        {
            ModeValue.Text = "sin motor";
            FormatValue.Text = "—";
            BufferValue.Text = "—";
            MmcssValue.Text = "—";
            CallbacksValue.Text = "—";
            TimeoutsValue.Text = "—";
            UnderrunValue.Text = "—";
            return;
        }

        RenderStatistics statistics = output.Statistics;

        // Cada TextBlock solo se escribe cuando su texto cambia: con el motor parado todos
        // los valores son constantes, y escribir lo mismo 120 veces por minuto invalidaria
        // el panel entero sin cambiar un pixel.
        string mode = statistics.Mode == AudioStreamMode.Exclusive ? "exclusivo" : "compartido";
        if (ModeValue.Text != mode)
        {
            ModeValue.Text = mode;
        }

        string format = output.Format.ToString();
        if (FormatValue.Text != format)
        {
            FormatValue.Text = format;
        }

        string buffer = string.Create(
            CultureInfo.InvariantCulture,
            $"{output.BufferFrames} fotogramas ({statistics.BufferDurationMilliseconds:F1} ms)");
        if (BufferValue.Text != buffer)
        {
            BufferValue.Text = buffer;
        }

        string mmcss = statistics.UsingMultimediaClass ? "registrado" : "no disponible";
        if (MmcssValue.Text != mmcss)
        {
            MmcssValue.Text = mmcss;
        }

        string callbacks = statistics.Callbacks.ToString("N0", CultureInfo.InvariantCulture);
        if (CallbacksValue.Text != callbacks)
        {
            CallbacksValue.Text = callbacks;
        }

        string timeouts = statistics.WaitTimeouts.ToString("N0", CultureInfo.InvariantCulture);
        if (TimeoutsValue.Text != timeouts)
        {
            TimeoutsValue.Text = timeouts;
        }

        long milliseconds = statistics.SampleRate > 0
            ? _owner.Pipeline.UnderrunSamples / Math.Max(1, output.Format.Channels) * 1000L / statistics.SampleRate
            : 0;

        string underrun = string.Create(
            CultureInfo.InvariantCulture,
            $"{milliseconds} ms ({_owner.Pipeline.UnderrunSamples} muestras)");
        if (UnderrunValue.Text != underrun)
        {
            UnderrunValue.Text = underrun;
        }

        string decoderError = _owner.Pipeline.LastError?.Message ?? "ninguno";
        if (DecoderErrorValue.Text != decoderError)
        {
            DecoderErrorValue.Text = decoderError;
        }
    }
}
