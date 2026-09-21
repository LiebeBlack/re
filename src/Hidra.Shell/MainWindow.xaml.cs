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
    /// <summary>Tamano de la transformada del analizador.</summary>
    private const int FftSize = 2048;

    /// <summary>Numero de bandas que se dibujan.</summary>
    private const int BandCount = 48;

    /// <summary>Tamano del anillo de captura, en muestras.</summary>
    private const int ScopeSamples = FftSize;

    private const int GridLineCount = 4;

    private readonly PlaybackPipeline _pipeline = new();
    private readonly float[] _scope = new float[ScopeSamples];
    private readonly float[] _bands = new float[BandCount];
    private readonly Line[] _gridLines = new Line[GridLineCount];
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromMilliseconds(33) };

    private WasapiExclusiveOutput? _output;
    private SpectrumAnalyzer? _analyzer;
    private Polygon? _spectrum;
    private bool? _lastPlaying;
    private string? _lastState;
    private bool _disposed;

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
        AppWindow.Resize(new Windows.Graphics.SizeInt32(1120, 800));

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
        _timer.Start();

        // La liberacion va atada al cierre de la ventana y no al recolector. El motor de audio
        // tiene un hilo propio y un flujo abierto sobre el dispositivo: dejarlos a merced del
        // recolector mantendria el dispositivo tomado y el hilo vivo mas tiempo del debido.
        Closed += OnClosed;

        UpdateTransportVisuals();
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

    private void OnClosed(object sender, WindowEventArgs args) => Dispose();

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
            _output = WasapiExclusiveOutput.Open(_pipeline, TimeSpan.FromMilliseconds(20));
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
        DrawSpectrum();
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

        if (_pendingSeekTicks >= 0 && Math.Abs(ring.Ticks - _pendingSeekTicks) <= 200_000)
        {
            // La busqueda ya se aplico y el material nuevo entra en cola: el cursor vuelve a
            // seguir el audio. El margen de veinte milisegundos tolera la granularidad del
            // primer bloque convertido.
            _pendingSeekTicks = -1;
        }

        TimeSpan position = _pendingSeekTicks >= 0 ? new TimeSpan(_pendingSeekTicks) : ring;

        PositionText.Text = FormatClock(position);
        TotalText.Text = _pipeline.Duration is TimeSpan total ? FormatClock(total) : "--:--";
        UpdateSeekSlider(position);

        if (_output is not null)
        {
            RenderStatistics statistics = _output.Statistics;
            long underrunMilliseconds = _output.Format.SampleRate > 0
                ? _pipeline.UnderrunSamples * 1000L / _output.Format.SampleRate
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

        if (Math.Abs(SeekSlider.Value - value) > 0.5)
        {
            SeekSlider.Value = value;
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
