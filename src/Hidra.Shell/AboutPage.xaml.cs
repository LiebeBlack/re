using System.Reflection;
using Hidra.Kernel.Simd;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Hidra.Shell;

/// <summary>
/// Ventana de identidad de la aplicacion, con el entorno real de ejecucion.
/// </summary>
/// <remarks>
/// Todo lo que aqui se muestra se lee una vez en la construccion: la version es la del
/// ensamblado, el runtime y el ancho vectorial son propiedades del proceso, y el formato
/// del dispositivo lo publica el motor. Nada cambia durante la sesion, de modo que no
/// hay temporizador ni sondeo.
/// </remarks>
public sealed partial class AboutPage : Window
{
    /// <summary>Crea la ventana y rellena sus datos.</summary>
    public AboutPage(MainWindow owner)
    {
        InitializeComponent();

        Title = "Acerca de Hidra";
        AppWindow.Resize(new Windows.Graphics.SizeInt32(520, 460));

        Assembly assembly = typeof(AboutPage).Assembly;
        string version = assembly.GetName().Version?.ToString(3) ?? "0.0.0";

        SubtitleText.Text = $"Reproductor de audio sobre WASAPI  ·  version {version}";
        RuntimeText.Text = $".NET {Environment.Version}  ·  {System.Runtime.InteropServices.RuntimeInformation.OSDescription}";

        SimdText.Text = $"SIMD: {SimdCaps.TierName}  ·  registro de {SimdCaps.VectorBytes} bytes";
        VectorText.Text = $"Vector<float>: {System.Numerics.Vector<float>.Count} lanes";

        DeviceText.Text = owner.Output is { } output
            ? $"Dispositivo: {output.Format}"
            : "Dispositivo: sin motor de audio";
    }
}
