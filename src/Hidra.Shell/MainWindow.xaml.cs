using System.Globalization;
using System.Runtime.InteropServices;
using Hidra.Audio;
using Hidra.Kernel.Dsp;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.ApplicationModel.DataTransfer;
using Windows.Foundation;
using Windows.Storage;
using Windows.Storage.Pickers;
using Windows.UI;

namespace Hidra.Shell;

/// <summary>Ventana principal del reproductor.</summary>
/// <remarks>
/// <para>
/// La interfaz no hace trabajo de audio. El motor corre en su propio hilo y la cadena de
/// decodificacion en otro; aqui solo se leen contadores ya publicados y se pinta. El
/// temporizador de dibujo va a unos treinta fotogramas por segundo, que es de sobra para un
/// espectro y deja el procesador libre.
/// </para>
/// <para>
/// El analizador tambien vive aqui y no en el hilo de audio. Es una decision deliberada: una
/// transformada de Fourier de dos mil cuarenta y ocho puntos dentro del callback del
/// dispositivo se nota en la latencia. En lugar de eso el hilo de audio deja una copia de lo
/// ultimo reproducido en un anillo pequeno, y es este temporizador quien la analiza.
/// </para>
/// </remarks>
public sealed partial class MainWindow : Window, IDisposable
{
    private readonly PlaybackPipeline _pipeline = new();

    /// <summary>Tamano de la transformada del analizador.</summary>
    private const int FftSize = 2048;

    /// <summary>Numero de bandas que se dibujan.</summary>
    private const int BandCount = 48;

    /// <summary>Tamano del anillo de captura, en muestras.</summary>
    private const int ScopeSamples = FftSize;

    private const int GridLineCount = 4;

    /// <summary>Cadena de reproduccion y motor de salida; los consumen las ventanas auxiliares.</summary>
    internal PlaybackPipeline Pipeline => _pipeline;

    /// <summary>Motor de salida actual, o null si no se pudo abrir el dispositivo.</summary>
    internal WasapiExclusiveOutput? Output => _output;

    /// <summary>Preferencias persistidas; las leen y escriben las ventanas auxiliares.</summary>
    internal SettingsStore Settings => _settings;

    private readonly float[] _scope = new float[ScopeSamples];
    private readonly float[] _bands = new float[BandCount];
    private readonly Line[] _gridLines = new Line[GridLineCount];
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromMilliseconds(33) };

    private readonly SettingsStore _settings;

    private WasapiExclusiveOutput? _output;
    private SpectrumAnalyzer? _analyzer;
    private Polygon? _spectrum;
    private bool? _lastPlaying;
    private string? _lastState;
    private bool _disposed;

    /// <summary>True mientras el render de pantalla aporte algo: ventana visible y algo que dibujar.</summary>
    private bool _renderWanted;

    /// <summary>Fotogramas de espectro congelado: evita reescrituras cuando nada cambia.</summary>
    private int _frozenFrames;

    /// <summary>Ultima posicion del cursor de busqueda escrita en el control, para no reescribir.</summary>
    private double _lastSliderWritten = -1;

    // Estado de la barra de busqueda. La peticion queda pendiente hasta que la posicion de la
    // cola coincide con el destino; mientras tanto el cursor muestra lo que el usuario pidio
    // y no lo que la cola todavia contiene.
    private long _pendingSeekTicks = -1;
    private long _lastDurationTicks = -1;
    private bool _sliderDragging;

    /// <summary>Crea la ventana, arranca el motor y empieza a dibujar.</summary>
    public MainWindow()
    {
        InitializeComponent();

        Title = "Hidra";
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(TitleBar);

        _settings = SettingsStore.Load();
        ApplyRememberedPlacement();

        BuildSpectrum();
        StartEngine();

        _pipeline.Volume = VolumeSlider.Value / 100.0;

        // Los eventos de puntero del control de busqueda se capturan en la fase de tunel:
        // la plantilla del deslizador los marca como manejados y sin esto el arrastre no
        // llega nunca al codigo de la ventana.
        SeekSlider.AddHandler(UIElement.PointerPressedEvent, new PointerEventHandler(OnSeekPointerPressed), handledEventsToo: true);
        SeekSlider.AddHandler(UIElement.PointerReleasedEvent, new PointerEventHandler(OnSeekPointerReleased), handledEventsToo: true);
        SeekSlider.AddHandler(UIElement.PointerCaptureLostEvent, new PointerEventHandler(OnSeekCaptureLost), handledEventsToo: true);
        SeekSlider.KeyDown += OnSeekKeyDown;

        _timer.Tick += OnTick;

        // El render de pantalla empieza ENCENDIDO pero su cadencia depende de la visibilidad:
        // la primera activacion dispara el arranque, y Visibility lo pausa y reanuda. Un
        // temporizador que sigue corriendo con la ventana minimizada es CPU quemada sin un
        // solo pixel a cambio.
        Activated += OnWindowActivated;
        _timer.Start();

        // La liberacion va atada al cierre de la ventana y no al recolector. El motor de audio
        // tiene un hilo propio y un flujo abierto sobre el dispositivo: dejarlos a merced del
        // recolector mantendria el dispositivo tomado y el hilo vivo mas tiempo del debido.
        Closed += OnClosed;

        UpdateTransportVisuals();
    }

    /// <summary>
    /// Restaura la colocacion recordada, re-acotada al area de trabajo actual.
    /// </summary>
    /// <remarks>
    /// El tamano guardado esta en pixeles fisicos y WinUI trabaja en efectivos, de modo que
    /// la conversion pasa por el DPI real de la ventana una vez creada. Si la colocacion no
    /// existe, o cayo fuera del monitor actual (desenchufar un segundo monitor, cambiar de
    /// docking), la ventana se centra en el area de trabajo con el tamano por defecto:
    /// siempre visible, nunca media ventana fuera de pantalla.
    /// </remarks>
    private void ApplyRememberedPlacement()
    {
        const int defaultWidth = 1120;
        const int defaultHeight = 800;
        const int minimumWidth = 640;
        const int minimumHeight = 520;

        nint handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        uint dpi = NativeWindowMethods.GetDpiForWindow(handle);
        double scale = dpi / 96.0;

        if (!NativeWindowMethods.TryGetWorkArea(out var area, handle))
        {
            AppWindow.Resize(new Windows.Graphics.SizeInt32(defaultWidth, defaultHeight));
            return;
        }

        int workWidth = area.Right - area.Left;
        int workHeight = area.Bottom - area.Top;

        SettingsStore.WindowPlacement? placement = _settings.Placement;

        int requestedWidth = placement is null
            ? defaultWidth
            : (int)Math.Round(placement.Width / scale);
        int requestedHeight = placement is null
            ? defaultHeight
            : (int)Math.Round(placement.Height / scale);

        // Tamano acotado: nunca por debajo de lo que el layout compacto necesita, nunca
        // por encima de lo que el monitor puede mostrar.
        int width = Math.Clamp(requestedWidth, minimumWidth, Math.Max(minimumWidth, (int)(workWidth / scale)));
        int height = Math.Clamp(requestedHeight, minimumHeight, Math.Max(minimumHeight, (int)(workHeight / scale)));

        AppWindow.Resize(new Windows.Graphics.SizeInt32(width, height));

        if (placement is null)
        {
            AppWindow.Move(new Windows.Graphics.PointInt32(
                area.Left + Math.Max(0, ((workWidth - (int)(width * scale)) / 2)),
                area.Top + Math.Max(0, ((workHeight - (int)(height * scale)) / 2))));
            return;
        }

        int x = (int)Math.Round(placement.X / scale);
        int y = (int)Math.Round(placement.Y / scale);

        // La colocacion guardada puede referirse a un monitor que ya no esta: si el
        // rectangulo recordado no toca el area de trabajo actual, se centra en lugar de
        // aparecer inaccesible.
        bool visible = x < area.Right && (x + (width * scale)) > area.Left
            && y < area.Bottom && (y + (height * scale)) > area.Top;

        AppWindow.Move(visible
            ? new Windows.Graphics.PointInt32(
                Math.Clamp(x, area.Left, Math.Max(area.Left, area.Right - (int)(width * scale))),
                Math.Clamp(y, area.Top, Math.Max(area.Top, area.Bottom - (int)(height * scale))))
            : new Windows.Graphics.PointInt32(
                area.Left + Math.Max(0, ((workWidth - (int)(width * scale)) / 2)),
                area.Top + Math.Max(0, ((workHeight - (int)(height * scale)) / 2))));
    }

    private void OnWindowActivated(object sender, WindowActivatedEventArgs args)
    {
        bool active = args.WindowActivationState != WindowActivationState.Deactivated;

        // La cadencia se gestiona ahi donde se sabe: activa a treinta hercios, desactivada
        // a cuatro (la posicion y el estado siguen avanzando por el audio, pero el ojo no
        // esta mirando), minimizada/oculta a cero. Al volver la activacion, la primera
        // pasada reencuentra todo el estado sin trabajo de recuperacion especial.
        if (active)
        {
            _timer.Interval = TimeSpan.FromMilliseconds(33);
            _renderWanted = true;
        }
        else if (NativeWindowMethods.IsIconic(WinRT.Interop.WindowNative.GetWindowHandle(this)))
        {
            _timer.Stop();
            _renderWanted = false;
        }
        else
        {
            _timer.Interval = TimeSpan.FromMilliseconds(250);
            _renderWanted = true;
        }
    }

    /// <inheritdoc />
    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;

        _timer.Stop();
        _timer.Tick -= OnTick;

        // El orden importa: el motor consume la cadena, de modo que hay que parar al
        // consumidor antes de liberar la fuente.
        _output?.Dispose();
        _analyzer?.Dispose();
        _pipeline.Dispose();

        GC.SuppressFinalize(this);
    }

    private void OnClosed(object sender, WindowEventArgs args)
    {
        // La colocacion se guarda ANTES de soltar nada: AppWindow sigue siendo valida aqui.
        Windows.Graphics.PointInt32 position = AppWindow.Position;
        Windows.Graphics.SizeInt32 size = AppWindow.Size;
        _settings.Placement = new SettingsStore.WindowPlacement(position.X, position.Y, size.Width, size.Height);
        _settings.Save();

        // Las ventanas auxiliares deben cerrarse antes de soltar el motor: su sondeo lee
        // contadores de un objeto que va a dejar de existir.
        _settingsPage?.Dispose();
        _diagnosticsPage?.Dispose();
        _aboutPage = null;

        Dispose();
    }

    /// <summary>Abre la ventana de ajustes del motor, o la trae al frente si ya lo esta.</summary>
    private void OnEngineSettingsClicked(object sender, RoutedEventArgs e)
    {
        if (_output is null)
        {
            ShowStatus("Sin motor de audio en marcha no hay ajustes que cambiar.", InfoBarSeverity.Informational);
            return;
        }

        if (_settingsPage is null)
        {
            _settingsPage = new EngineSettingsPage(this);
            _settingsPage.Closed += (_, _) => _settingsPage = null;
            _settingsPage.Activate();
        }
        else
        {
            _settingsPage.Activate();
        }

        NativeWindowMethods.CenterOverOwner(this, _settingsPage);
    }

    // Cualquier Window de WinUI expone Closed y Activate: esta especificacion existe solo
    // para dejar claro que las ventanas auxiliares participan del mismo ciclo de vida.

    /// <summary>Abre la ventana de diagnostico, o la trae al frente si ya lo esta.</summary>
    private void OnDiagnosticsClicked(object sender, RoutedEventArgs e)
    {
        if (_diagnosticsPage is null)
        {
            _diagnosticsPage = new DiagnosticsPage(this);
            _diagnosticsPage.Closed += (_, _) => _diagnosticsPage = null;
            _diagnosticsPage.Activate();
        }
        else
        {
            _diagnosticsPage.Activate();
        }

        NativeWindowMethods.CenterOverOwner(this, _diagnosticsPage);
    }

    /// <summary>Abre la ventana de identidad, o la trae al frente si ya lo esta.</summary>
    private void OnAboutClicked(object sender, RoutedEventArgs e)
    {
        if (_aboutPage is null)
        {
            _aboutPage = new AboutPage(this);
            _aboutPage.Closed += (_, _) => _aboutPage = null;
            _aboutPage.Activate();
        }
        else
        {
            _aboutPage.Activate();
        }

        NativeWindowMethods.CenterOverOwner(this, _aboutPage);
    }

    /// <summary>
    /// Reconstruye el motor con los ajustes pedidos, conservando archivo y posicion.
    /// </summary>
    /// <remarks>
    /// <para>
    /// El orden es el que evita quedarse sin sonido: el motor nuevo se abre ANTES de
    /// liberar el viejo. Si el dispositivo rechaza la combinacion elegida, el viejo sigue
    /// en marcha y el fallo queda reducido a un aviso; la UI no necesita estado de
    /// "motor a medio cambiar" porque la sustitucion es atomica desde su punto de vista.
    /// </para>
    /// <para>
    /// Se ejecuta en el hilo de la interfaz: StartEngine toca controles (textos de
    /// diagnostico) y el pipeline exige que su ciclo de vida se gestione desde un unico
    /// hilo, que es el mismo que responde a los botones de transporte.
    /// </para>
    /// </remarks>
    /// <param name="mode">Regimen pedido para el nuevo motor.</param>
    /// <param name="latency">Latencia de buffer pedida.</param>
    /// <param name="allowSharedFallback">True para degradar a compartido si el exclusivo falla.</param>
    internal async Task ApplyEngineSettingsAsync(AudioStreamMode mode, TimeSpan latency, bool allowSharedFallback)
    {
        if (_output is null)
        {
            return;
        }

        TimeSpan resumePosition = _pipeline.Position;
        string? path = _pipeline.SourcePath;

        WasapiExclusiveOutput old = _output;
        AudioStreamMode previousMode = (AudioStreamMode)_settings.EngineMode;
        TimeSpan previousLatency = _targetLatency;
        bool previousFallback = _settings.AllowSharedFallback;

        // Liberar el motor anterior antes de abrir el nuevo: en modo exclusivo WASAPI
        // rechaza una segunda apertura sobre el mismo endpoint con AUDCLNT_E_DEVICE_IN_USE,
        // lo que forzaria una caida a compartido no deseada.
        old.Dispose();
        _output = null;

        WasapiExclusiveOutput? replacement = null;

        try
        {
            replacement = WasapiExclusiveOutput.Open(_pipeline, latency, mode, allowSharedFallback);
            _pipeline.RestartEngine(replacement.Format.SampleRate, replacement.Format.Channels, resumePosition);
        }
        catch (Exception exception) when (exception is WasapiException or NotSupportedException or COMException)
        {
            replacement?.Dispose();

            // Si los nuevos ajustes fallan en el hardware, restaurar la configuracion anterior.
            try
            {
                replacement = WasapiExclusiveOutput.Open(_pipeline, previousLatency, previousMode, previousFallback);
                _pipeline.RestartEngine(replacement.Format.SampleRate, replacement.Format.Channels, resumePosition);
                _output = replacement;
                ShowStatus($"El motor no admitio los nuevos ajustes ({exception.Message}); se restauraron los anteriores.", InfoBarSeverity.Warning);
            }
            catch (Exception restoreException)
            {
                ReportEngineFailure($"Fallo al restaurar el motor de audio: {restoreException.Message}");
                return;
            }
            return;
        }

        _output = replacement;
        _targetLatency = latency;

        // Los ajustes que el dispositivo acepto son la nueva referencia: si el usuario no
        // toco nada, el proximo arranque pide exactamente lo que ya funciono.
        _settings.LatencyMilliseconds = latency.TotalMilliseconds;
        _settings.EngineMode = (int)mode;
        _settings.AllowSharedFallback = allowSharedFallback;
        _settings.ResamplerQuality = (int)_pipeline.ResamplerQuality;
        _settings.Save();

        _analyzer?.Dispose();
        _analyzer = new SpectrumAnalyzer(FftSize, replacement.Format.SampleRate, BandCount);
        DeviceFormatText.Text = replacement.Format.ToString();
        ModeText.Text = DescribeMode(replacement);
        LatencyText.Text = string.Create(
            CultureInfo.InvariantCulture,
            $"{replacement.Statistics.BufferDurationMilliseconds:F1} ms / {replacement.BufferFrames} fotogramas");

        await Task.CompletedTask;
    }

    /// <summary>
    /// Abre el dispositivo y deja la cadena lista.
    /// </summary>
    /// <remarks>
    /// Un fallo aqui no puede impedir arrancar: si no hay dispositivo de audio, o esta tomado,
    /// la aplicacion sigue siendo util como explorador de archivos y el motivo real del fallo
    /// se muestra en pantalla. Abortar el arranque por eso obligaria al usuario a adivinar por
    /// que no abre.
    /// </remarks>
    private void StartEngine()
    {
        try
        {
            // La latencia y el regimen preferidos vienen de la sesion anterior: si el
            // dispositivo los acepta, la primera apertura ya es la configuracion deseada.
            _targetLatency = TimeSpan.FromMilliseconds(Math.Clamp(
                _settings.LatencyMilliseconds, 2.0, 200.0));

            _output = WasapiExclusiveOutput.Open(
                _pipeline,
                _targetLatency,
                (AudioStreamMode)_settings.EngineMode,
                _settings.AllowSharedFallback);
            _pipeline.ResamplerQuality = (SincResampler.ResamplerQuality)_settings.ResamplerQuality;
            _pipeline.Configure(_output.Format.SampleRate, _output.Format.Channels);
            _analyzer = new SpectrumAnalyzer(FftSize, _output.Format.SampleRate, BandCount);

            DeviceFormatText.Text = _output.Format.ToString();
            ModeText.Text = DescribeMode(_output);
            LatencyText.Text = string.Create(
                CultureInfo.InvariantCulture,
                $"{_output.Statistics.BufferDurationMilliseconds:F1} ms / {_output.BufferFrames} fotogramas");
        }
        catch (WasapiException exception)
        {
            ReportEngineFailure(exception.Message);
        }
        catch (NotSupportedException exception)
        {
            ReportEngineFailure(exception.Message);
        }
        catch (COMException exception)
        {
            ReportEngineFailure($"El sistema de audio rechazo la operacion: {exception.Message}");
        }
    }

    private void ReportEngineFailure(string message)
    {
        DeviceFormatText.Text = "no disponible";
        ModeText.Text = "sin motor";
        LatencyText.Text = "—";
        HealthText.Text = "sin audio";

        _openError = message;
        ShowStatus($"No se pudo abrir el dispositivo de audio. {message}", InfoBarSeverity.Error);
    }

    private static string DescribeMode(WasapiExclusiveOutput output)
    {
        RenderStatistics statistics = output.Statistics;
        string mode = statistics.Mode == AudioStreamMode.Exclusive ? "exclusivo" : "compartido";

        if (statistics.UsingRawStream)
        {
            mode += " + crudo";
        }

        if (statistics.RealignedBuffer)
        {
            mode += " (buffer realineado)";
        }

        return mode;
    }

    /// <summary>Crea el poligono del espectro y sus lineas de referencia.</summary>
    private void BuildSpectrum()
    {
        LinearGradientBrush fill = new()
        {
            StartPoint = new Point(0, 0),
            EndPoint = new Point(0, 1),
        };

        fill.GradientStops.Add(new GradientStop { Offset = 0.0, Color = Color.FromArgb(255, 61, 220, 151) });
        fill.GradientStops.Add(new GradientStop { Offset = 0.55, Color = Color.FromArgb(140, 61, 220, 151) });
        fill.GradientStops.Add(new GradientStop { Offset = 1.0, Color = Color.FromArgb(16, 61, 220, 151) });

        _spectrum = new Polygon
        {
            Stretch = Stretch.None,
            Fill = fill,
            Stroke = new SolidColorBrush(Color.FromArgb(220, 61, 220, 151)),
            StrokeThickness = 1.5,
        };

        // Un punto por banda mas dos que cierran la figura por la base. El numero de puntos
        // queda fijo de por vida: reasignar la coleccion en cada fotograma invalidaria el
        // elemento entero en vez de solo la geometria.
        for (int index = 0; index < BandCount + 2; index++)
        {
            _spectrum.Points.Add(new Point(0, 0));
        }

        SpectrumCanvas.Children.Add(_spectrum);

        // Las lineas de referencia se anaden DESPUES del poligono para que queden por encima:
        // el relleno del espectro es translucido en su mitad inferior y sin esto las lineas se
        // perderian justo donde mas falta hacen.
        SolidColorBrush gridBrush = (SolidColorBrush)Application.Current.Resources["HidraGridLine"];

        for (int index = 0; index < GridLineCount; index++)
        {
            Line line = new() { Stroke = gridBrush, StrokeThickness = 1 };
            _gridLines[index] = line;
            SpectrumCanvas.Children.Add(line);
        }
    }

    private void OnSpectrumSizeChanged(object sender, SizeChangedEventArgs e)
    {
        // Un lienzo no propone tamano propio, asi que hay que darselo de forma explicita o se
        // queda en cero y no dibuja nada.
        SpectrumCanvas.Width = e.NewSize.Width;
        SpectrumCanvas.Height = e.NewSize.Height;

        for (int index = 0; index < GridLineCount; index++)
        {
            double y = Math.Round(e.NewSize.Height * (index + 1) / (GridLineCount + 1)) + 0.5;
            Line line = _gridLines[index];
            line.X1 = 0;
            line.X2 = e.NewSize.Width;
            line.Y1 = y;
            line.Y2 = y;
        }
    }

    private void OnTick(object? sender, object e)
    {
        UpdateDiagnostics();

        if (_renderWanted)
        {
            DrawSpectrum();
        }
    }

    private void DrawSpectrum()
    {
        if (_analyzer is null || _spectrum is null)
        {
            return;
        }

        double width = SpectrumCanvas.ActualWidth;
        double height = SpectrumCanvas.ActualHeight;

        if (width <= 1 || height <= 1)
        {
            return;
        }

        _pipeline.CopyScope(_scope);
        _analyzer.Process(_scope, _bands);

        // Congelacion del espectro: si todas las bandas llevan varios fotogramas clavadas
        // en el suelo de la escala, la ventana FFT esta viendo silencio y cualquier pasada
        // adicional produce exactamente el mismo poligono. Se salta el redibujo (que en
        // WinUI invalida y repinta el lienzo entero) hasta que el material vuelva; el
        // contador se reinicia en cuanto una banda se mueve.
        const int freezeAfterFrames = 12;
        bool settled = true;

        for (int band = 0; band < BandCount; band++)
        {
            if (_bands[band] > _analyzer.MinDecibels + 1f)
            {
                settled = false;
                break;
            }
        }

        if (settled && _frozenFrames >= freezeAfterFrames)
        {
            return;
        }

        _frozenFrames = settled ? _frozenFrames + 1 : 0;

        double range = _analyzer.MaxDecibels - _analyzer.MinDecibels;
        double usable = height - 10;
        PointCollection points = _spectrum.Points;

        for (int band = 0; band < BandCount; band++)
        {
            double normalized = Math.Clamp((_bands[band] - _analyzer.MinDecibels) / range, 0.0, 1.0);
            double x = (band + 0.5) * width / BandCount;
            double y = height - 5 - (normalized * usable);
            points[band] = new Point(x, y);
        }

        points[BandCount] = new Point(width, height);
        points[BandCount + 1] = new Point(0, height);

        if (SpectrumPlaceholder.Visibility == Visibility.Visible)
        {
            SpectrumPlaceholder.Visibility = Visibility.Collapsed;
        }
    }

    private void UpdateDiagnostics()
    {
        // La posicion que manda es la de la cola: avanza con la reproduccion y salta al
        // buscar. El acumulador historico del motor no sirve para un cursor, porque una
        // busqueda hacia atras no lo hace retroceder.
        TimeSpan ring = _pipeline.Position;

        if (_pendingSeekTicks >= 0 && !_pipeline.IsSeekPending)
        {
            // La busqueda ya se aplico en el hilo decodificador y el material nuevo entra en
            // cola: el cursor vuelve a seguir la posicion del audio de forma determinista.
            _pendingSeekTicks = -1;
        }

        TimeSpan position = _pendingSeekTicks >= 0 ? new TimeSpan(_pendingSeekTicks) : ring;

        PositionText.Text = FormatClock(position);
        TotalText.Text = _pipeline.Duration is TimeSpan total ? FormatClock(total) : "--:--";
        UpdateSeekSlider(position);

        if (_output is not null)
        {
            RenderStatistics statistics = _output.Statistics;

            // El contador de underruns lleva MUESTRAS entrelazadas: un fotograma de silencio
            // estereo son dos muestras, de modo que hay que repartir entre canales antes de
            // pasar a milisegundos, o el panel duplicaria el silencio real en estereo.
            int channels = Math.Max(1, _output.Format.Channels);
            long underrunMilliseconds = _output.Format.SampleRate > 0
                ? _pipeline.UnderrunSamples / channels * 1000L / _output.Format.SampleRate
                : 0;

            string health;

            if (statistics.DeviceInvalidated)
            {
                health = "dispositivo perdido";
            }
            else if (_pipeline.LastError is not null)
            {
                health = "error de decodificacion";
            }
            else
            {
                health = string.Create(
                    CultureInfo.InvariantCulture,
                    $"{statistics.Callbacks} bloques, {underrunMilliseconds} ms de silencio");

                if (statistics.UsingMultimediaClass)
                {
                    health += ", mmcss";
                }
            }

            HealthText.Text = health;
        }

        UpdateTransportVisuals();
    }

    /// <summary>
    /// Mueve el cursor de la barra cuando la posicion cambia por reproduccion o por busqueda.
    /// </summary>
    /// <remarks>
    /// El valor del control solo se escribe cuando cambia de verdad: asignar el mismo valor en
    /// cada tick provocaria eventos innecesarios y, con el pulgar agarrado, una pelea entre el
    /// usuario y el temporizador. Durante el arrastre el cursor lo lleva el usuario y el tick
    /// no lo toca.
    /// </remarks>
    private void UpdateSeekSlider(TimeSpan position)
    {
        if (_sliderDragging)
        {
            return;
        }

        long duration = _pipeline.Duration?.Ticks ?? -1;

        if (duration != _lastDurationTicks)
        {
            _lastDurationTicks = duration;
            SeekSlider.Maximum = duration > 0 ? duration : 1;
            SeekSlider.IsEnabled = duration > 0;
        }

        double value = Math.Clamp(position.Ticks, 0, SeekSlider.Maximum);

        // La escritura es condicional tambien por igualdad exacta con lo ya escrito: asignar
        // el mismo valor invalida el control igualmente en WinUI, y con el valor congelado
        // (pausa, archivo terminado) esto evita un re-render por tick sin motivo.
        if (Math.Abs(value - _lastSliderWritten) > 0.5)
        {
            SeekSlider.Value = value;
            _lastSliderWritten = value;
        }
    }

    /// <summary>Formatea un tiempo como mm:ss, u h:mm:ss cuando supera la hora.</summary>
    private static string FormatClock(TimeSpan value)
    {
        int hours = (int)value.TotalHours;

        return hours > 0
            ? string.Create(CultureInfo.InvariantCulture, $"{hours}:{value.Minutes:00}:{value.Seconds:00}")
            : string.Create(CultureInfo.InvariantCulture, $"{value.Minutes:00}:{value.Seconds:00}");
    }

    /// <summary>
    /// Suelta el cursor y convierte la posicion en una peticion de busqueda.
    /// </summary>
    /// <remarks>
    /// La busqueda se aplica en el hilo decodificador, no aqui: el lector de origen no es
    /// seguro para hilos y este hilo jamas lo toca. Solo se registra el destino.
    /// </remarks>
    private void CommitSeek()
    {
        if (_pipeline.SourcePath is null)
        {
            return;
        }

        TimeSpan? duration = _pipeline.Duration;

        if (duration is null || duration <= TimeSpan.Zero)
        {
            return;
        }

        double fraction = Math.Clamp(SeekSlider.Value / SeekSlider.Maximum, 0.0, 1.0);
        TimeSpan target = TimeSpan.FromTicks((long)(duration.Value.Ticks * fraction));

        _pendingSeekTicks = target.Ticks;
        _pipeline.Seek(target);
    }

    private void OnSeekPointerPressed(object sender, PointerRoutedEventArgs e) => _sliderDragging = true;

    private void OnSeekPointerReleased(object sender, PointerRoutedEventArgs e)
    {
        _sliderDragging = false;
        CommitSeek();
    }

    private void OnSeekCaptureLost(object sender, PointerRoutedEventArgs e)
    {
        // La captura se pierde cuando el puntero sale de la ventana con el boton apretado:
        // hay que soltar el cursor igualmente, o la barra quedaria bloqueada para el tick.
        _sliderDragging = false;
        CommitSeek();
    }

    private void OnSeekKeyDown(object sender, KeyRoutedEventArgs e)
    {
        // El propio control moveria el valor tecla a tecla, pero eso no avisaria al motor:
        // el commit ocurre al soltar el puntero, y las teclas no sueltan punteros. Se toma el
        // control de las teclas de paso y se busca de forma explicita.
        bool handled = true;

        switch (e.Key)
        {
            case Windows.System.VirtualKey.Left:
                StepSeek(-1);
                break;
            case Windows.System.VirtualKey.Right:
                StepSeek(1);
                break;
            default:
                handled = false;
                break;
        }

        e.Handled = handled;
    }

    /// <summary>Mueve la posicion un segundo por pulsacion, acotado a la duracion.</summary>
    private void StepSeek(int direction)
    {
        if (_pipeline.SourcePath is null)
        {
            return;
        }

        TimeSpan? duration = _pipeline.Duration;

        if (duration is null || duration <= TimeSpan.Zero)
        {
            return;
        }

        TimeSpan current = _pendingSeekTicks >= 0 ? new TimeSpan(_pendingSeekTicks) : _pipeline.Position;
        TimeSpan target = current + TimeSpan.FromSeconds(direction);
        target = TimeSpan.FromTicks(Math.Clamp(target.Ticks, 0, duration.Value.Ticks));

        _pendingSeekTicks = target.Ticks;
        _pipeline.Seek(target);
    }

    /// <summary>
    /// Atajos de teclado globales de la ventana.
    /// </summary>
    /// <remarks>
    /// La barra de busqueda y el volumen retienen el foco al usarlos, y si esta ventana no
    /// capturara las teclas el espacio activaria el control enfocado en lugar del transporte.
    /// Es el comportamiento estandar que se espera de cualquier reproductor.
    /// </remarks>
    private void OnRootKeyDown(object sender, KeyRoutedEventArgs e)
    {
        switch (e.Key)
        {
            case Windows.System.VirtualKey.Space:
                OnPlayPauseClicked(this, new RoutedEventArgs());
                e.Handled = true;
                break;
            case Windows.System.VirtualKey.Left:
                StepSeek(-1);
                e.Handled = true;
                break;
            case Windows.System.VirtualKey.Right:
                StepSeek(1);
                e.Handled = true;
                break;
            case Windows.System.VirtualKey.Up:
                NudgeVolume(+5);
                e.Handled = true;
                break;
            case Windows.System.VirtualKey.Down:
                NudgeVolume(-5);
                e.Handled = true;
                break;
        }
    }

    private void NudgeVolume(int delta)
    {
        double value = Math.Clamp(VolumeSlider.Value + delta, VolumeSlider.Minimum, VolumeSlider.Maximum);

        if (value != VolumeSlider.Value)
        {
            VolumeSlider.Value = value;
        }
    }

    private void UpdateTransportVisuals()
    {
        // Lo que el icono y el texto deben reflejar es si hay sonido, no si el decodificador
        // esta bombeando: al agotarse el archivo queda material en cola saliendo todavia.
        bool playing = _pipeline.IsRendering;

        if (_lastPlaying != playing)
        {
            _lastPlaying = playing;
            PlayIcon.Glyph = playing ? "\uE769" : "\uE768";
            ToolTipService.SetToolTip(PlayButton, playing ? "Pausar" : "Reproducir");
        }

        string state = _pipeline.SourcePath is null
            ? "en espera"
            : playing
                ? "reproduciendo"
                : _pipeline.EndOfStream
                    ? "terminado"
                    : "en pausa";

        if (_lastState != state)
        {
            _lastState = state;
            StateText.Text = state;
        }
    }

    private async void OnOpenClicked(object sender, RoutedEventArgs e)
    {
        FileOpenPicker picker = new();
        picker.FileTypeFilter.Add(".wav");
        picker.FileTypeFilter.Add(".mp3");
        picker.FileTypeFilter.Add(".flac");
        picker.FileTypeFilter.Add(".m4a");
        picker.FileTypeFilter.Add(".aac");
        picker.FileTypeFilter.Add(".wma");
        picker.FileTypeFilter.Add("*");

        // La aplicacion no esta empaquetada, de modo que el selector no tiene ventana propia y
        // hay que decirle cual es la nuestra. Sin esto lanza al invocarlo.
        nint handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, handle);

        try
        {
            StorageFile? file = await picker.PickSingleFileAsync();

            if (file is not null)
            {
                LoadFile(file.Path);
            }
        }
        catch (COMException exception)
        {
            ShowStatus($"No se pudo abrir el selector de archivos: {exception.Message}", InfoBarSeverity.Error);
        }
    }

    private void OnPlayPauseClicked(object sender, RoutedEventArgs e)
    {
        if (_pipeline.SourcePath is null)
        {
            ShowStatus("Todavia no hay ningun archivo cargado.", InfoBarSeverity.Informational);
            return;
        }

        // La decision se toma por el estado de render, no por el de bombeo: mientras la cola
        // drena al final de un archivo el audio sigue sonando con el bombeo ya apagado, y
        // pulsar pausa entonces tiene que pausar de verdad.
        if (_pipeline.IsRendering)
        {
            _pipeline.Pause();
        }
        else
        {
            _pipeline.Play();
        }

        UpdateTransportVisuals();
    }

    private void OnStopClicked(object sender, RoutedEventArgs e)
    {
        if (_pipeline.SourcePath is null)
        {
            return;
        }

        _pipeline.Stop();
        UpdateTransportVisuals();
    }

    private void OnVolumeChanged(object sender, RangeBaseValueChangedEventArgs e)
    {
        _pipeline.Volume = e.NewValue / 100.0;

        if (VolumeText is not null)
        {
            VolumeText.Text = string.Create(CultureInfo.InvariantCulture, $"{(int)e.NewValue} %");
        }
    }

    private void OnRootDragOver(object sender, DragEventArgs e)
    {
        e.AcceptedOperation = DataPackageOperation.Copy;
        e.DragUIOverride.Caption = "Reproducir en Hidra";
        e.DragUIOverride.IsCaptionVisible = true;
        e.DragUIOverride.IsGlyphVisible = false;
    }

    private async void OnRootDrop(object sender, DragEventArgs e)
    {
        if (!e.DataView.Contains(StandardDataFormats.StorageItems))
        {
            return;
        }

        try
        {
            IReadOnlyList<IStorageItem> items = await e.DataView.GetStorageItemsAsync();

            if (items.Count > 0 && items[0] is StorageFile file)
            {
                LoadFile(file.Path);
            }
        }
        catch (COMException exception)
        {
            ShowStatus($"No se pudo leer el archivo soltado: {exception.Message}", InfoBarSeverity.Error);
        }
    }

    /// <summary>Carga un archivo, lo pone en reproduccion y actualiza la cabecera.</summary>
    private void LoadFile(string path)
    {
        if (_output is null)
        {
            ShowStatus(_openError ?? "No hay dispositivo de audio disponible.", InfoBarSeverity.Error);
            return;
        }

        try
        {
            _pipeline.ResamplerQuality = (SincResampler.ResamplerQuality)_settings.ResamplerQuality;
            _pipeline.Load(path);
            _analyzer?.Reset();

            // La barra de busqueda queda lista con el total del archivo recien cargado. Una
            // fuente sin duracion la desactiva en lugar de fingir un total inventado.
            _pendingSeekTicks = -1;
            _lastDurationTicks = -1;
            SeekSlider.IsEnabled = _pipeline.Duration is not null;
            SeekSlider.Value = 0;
            SeekSlider.Maximum = _pipeline.Duration?.Ticks ?? 1;
            TotalText.Text = _pipeline.Duration is TimeSpan duration ? FormatClock(duration) : "--:--";

            // System.IO.Path se cualifica porque Microsoft.UI.Xaml.Shapes.Path, que entra con
            // el espacio de nombres de las figuras, tiene el mismo nombre y sin esto la
            // referencia es ambigua.
            TrackTitle.Text = System.IO.Path.GetFileName(path);
            TrackDetail.Text = string.Create(
                CultureInfo.InvariantCulture,
                $"{_pipeline.SourceFormat}  ·  {System.IO.Path.GetDirectoryName(path)}");

            SpectrumPlaceholder.Visibility = Visibility.Visible;
            _pipeline.Play();
            UpdateTransportVisuals();
        }
        catch (NotSupportedException exception)
        {
            ShowStatus(exception.Message, InfoBarSeverity.Warning);
        }
        catch (InvalidOperationException exception)
        {
            ShowStatus(exception.Message, InfoBarSeverity.Error);
        }
        catch (IOException exception)
        {
            ShowStatus($"No se pudo leer el archivo: {exception.Message}", InfoBarSeverity.Error);
        }
        catch (COMException exception)
        {
            ShowStatus($"El decodificador rechazo el archivo: {exception.Message}", InfoBarSeverity.Error);
        }
    }

    /// <summary>Error de apertura del motor, que se muestra mientras no haya otro aviso.</summary>
    private string? _openError;

    /// <summary>Ventana de ajustes del motor actualmente abierta, si la hay.</summary>
    private EngineSettingsPage? _settingsPage;

    /// <summary>Ventana de diagnostico actualmente abierta, si la hay.</summary>
    private DiagnosticsPage? _diagnosticsPage;

    /// <summary>Ventana de identidad actualmente abierta, si la hay.</summary>
    private AboutPage? _aboutPage;

    /// <summary>Latencia pedida al motor en el arranque; la reusa el reinicio.</summary>
    private TimeSpan _targetLatency = TimeSpan.FromMilliseconds(20);

    /// <summary>
    /// Muestra un aviso al usuario.
    /// </summary>
    /// <remarks>
    /// Se usa la barra de avisos del sistema en lugar de un dialogo modal porque ninguno de
    /// estos mensajes requiere una decision: son hechos que el usuario necesita leer, y un
    /// modal por cada archivo ilegible seria insufrible.
    /// </remarks>
    private void ShowStatus(string message, InfoBarSeverity severity)
    {
        StatusBar.Severity = severity;
        StatusBar.Message = message;
        StatusBar.IsOpen = true;
    }
}
