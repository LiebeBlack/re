using Hidra.Audio;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;

namespace Hidra.Shell;

/// <summary>
/// Ventana secundaria de ajustes del motor de audio.
/// </summary>
/// <remarks>
/// <para>
/// El flujo completo es: leer el estado del motor en marcha, dejar al usuario elegir
/// regimen y latencia, y al confirmar construir un motor nuevo con esos parametros y
/// rearmar la cadena de reproduccion conservando archivo y posicion. El motor viejo se
/// libera DESPUES de que el nuevo este abierto: si la apertura falla, la reproduccion
/// sigue con el motor anterior y el usuario solo ve un aviso, en lugar de quedarse sin
/// sonido por haber probado una combinacion que su dispositivo rechaza.
/// </para>
/// <para>
/// Es una ventana y no un dialogo de contenido a proposito: se puede dejar abierta
/// mientras se comprueba como queda el sonido, y la principal sigue operable.
/// </para>
/// </remarks>
public sealed partial class EngineSettingsPage : Window, IDisposable
{
    private readonly MainWindow _owner;

    /// <summary>Crea la ventana con el propietario que la abre.</summary>
    public EngineSettingsPage(MainWindow owner)
    {
        InitializeComponent();
        _owner = owner;

        Title = "Ajustes del motor";
        AppWindow.Resize(new Windows.Graphics.SizeInt32(520, 680));

        SettingsStore settings = owner.Settings;

        // La seleccion arranca de lo PERSISTIDO, no del estado del motor: si el usuario
        // eligio compartido y el motor cayo a compartido por degradacion, la ventana
        // muestra compartido en los dos casos, que es lo que hay que saber.
        AudioStreamMode persistedMode = (AudioStreamMode)settings.EngineMode;
        ExclusiveRadio.IsChecked = persistedMode == AudioStreamMode.Exclusive;
        SharedRadio.IsChecked = persistedMode == AudioStreamMode.Shared;
        FallbackCheck.IsChecked = settings.AllowSharedFallback;

        ResamplerStandardRadio.IsChecked = settings.ResamplerQuality == 0;
        ResamplerMaxRadio.IsChecked = settings.ResamplerQuality == 1;

        ExclusiveHint.Text = "Sin mezcla del sistema ni remuestreo: el motor negocia el formato nativo del DAC. Solo un flujo a la vez.";
        SharedHint.Text = "Pasa por el mezclador de Windows: convive con otros reproductores, con algo mas de camino hasta el hardware.";

        // El punto de partida de la latencia es la pedida y persistida, no la concedida: la
        // concedida depende del redondeo del dispositivo y no es lo que el usuario eligio.
        LatencySlider.Value = Math.Clamp(
            settings.LatencyMilliseconds,
            LatencySlider.Minimum,
            LatencySlider.Maximum);
        RefreshLatencyText();
        RefreshModeNotice();
    }

    /// <inheritdoc />
    public void Dispose()
    {
        // Sin recursos propios: los controles los libera la ventana al cerrarse.
    }

    private void OnModeChecked(object sender, RoutedEventArgs e)
    {
        // Durante InitializeComponent el primer RadioButton dispara Checked antes de que
        // exista el resto del arbol: solo se refresca cuando todo esta construido.
        if (ModeNotice is not null)
        {
            RefreshModeNotice();
        }
    }

    private void OnLatencyChanged(object sender, RangeBaseValueChangedEventArgs e)
    {
        // Durante InitializeComponent el deslizador ya dispara este evento: el texto solo
        // puede refrescarse cuando los controles existen de verdad.
        if (LatencyValueText is not null)
        {
            RefreshLatencyText();
        }
    }

    private void RefreshLatencyText()
    {
        LatencyValueText.Text = string.Create(
            System.Globalization.CultureInfo.InvariantCulture,
            $"{LatencySlider.Value:F0} ms");
    }

    private void RefreshModeNotice()
    {
        bool exclusive = ExclusiveRadio.IsChecked == true;

        ModeNotice.Text = exclusive
            ? "Al aplicar, el motor se reinicia: la reproduccion se reanuda en la posicion actual."
            : "Al aplicar, el motor se reinicia en modo compartido y otro programa podra usar el dispositivo a la vez.";
    }

    private void OnCancelClicked(object sender, RoutedEventArgs e)
    {
        Close();
    }

    private async void OnApplyClicked(object sender, RoutedEventArgs e)
    {
        AudioStreamMode mode = ExclusiveRadio.IsChecked == true
            ? AudioStreamMode.Exclusive
            : AudioStreamMode.Shared;
        TimeSpan latency = TimeSpan.FromMilliseconds(LatencySlider.Value);
        bool fallback = FallbackCheck.IsChecked == true;

        int resamplerQuality = ResamplerMaxRadio.IsChecked == true ? 1 : 0;
        _owner.Settings.ResamplerQuality = resamplerQuality;
        _owner.Pipeline.ResamplerQuality = (Kernel.Dsp.SincResampler.ResamplerQuality)resamplerQuality;

        ApplyButton.IsEnabled = false;

        try
        {
            await _owner.ApplyEngineSettingsAsync(mode, latency, fallback);
        }
        finally
        {
            // La aplicacion puede haber cerrado la ventana dentro de la aplicacion de los
            // ajustes: tocar aqui el boton seria tocar un arbol suelto.
            if (ApplyButton is not null)
            {
                ApplyButton.IsEnabled = true;
            }
        }
    }
}
