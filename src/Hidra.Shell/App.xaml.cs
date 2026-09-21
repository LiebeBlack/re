using System.Diagnostics.CodeAnalysis;
using Microsoft.UI.Xaml;

namespace Hidra.Shell;

/// <summary>Punto de entrada de la aplicacion.</summary>
/// <remarks>
/// El arranque de la aplicacion lo genera el compilador de marcado de Windows App SDK, que es
/// quien llama a <see cref="Application.Start"/> y establece el bucle de mensajes. No se
/// sustituye por un <c>Main</c> propio: hacerlo obligaria a replicar a mano la verificacion de
/// requisitos del proceso y la inicializacion del interoperador de COM, que es exactamente
/// donde una copia desactualizada rompe la aplicacion sin que el compilador lo note.
/// </remarks>
[SuppressMessage(
    "Design",
    "CA1001:Types that own disposable fields should be disposable",
    Justification = "El ciclo de vida de Application lo controla el marco del sistema, no el codigo de la aplicacion, y nadie puede invocar Dispose sobre el. La ventana se libera a si misma en su evento de cierre, que es el unico punto donde consta que ya no se va a usar; marcarla como descartable sugeriria un contrato de propiedad que no existe.")]
public partial class App : Application
{
    private MainWindow? _window;

    /// <summary>Crea la aplicacion y carga sus recursos.</summary>
    public App() => InitializeComponent();

    /// <inheritdoc />
    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        // La referencia se conserva a proposito: sin un campo que la mantenga, el objeto
        // administrado de la ventana puede recogerse mientras su ventana nativa sigue viva.
        _window = new MainWindow();
        _window.Activate();
    }
}
