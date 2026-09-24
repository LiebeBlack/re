using System.Runtime.InteropServices;
using Microsoft.UI.Xaml;

namespace Hidra.Shell;

/// <summary>
/// Preguntas de estado de ventana que WinUI no expone y que la ventana adaptativa y el
/// renderizado inteligente necesitan. No hay superficie Win32 mas alla de estas: cada
/// declaration extra es una dependencia que mantener.
/// </summary>
internal static partial class NativeWindowMethods
{
    private const uint SpiGetWorkArea = 0x0048;

    /// <summary>Rectangulo Win32 en coordenadas fisicas de pantalla.</summary>
    [StructLayout(LayoutKind.Sequential)]
    internal struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    /// <summary>True cuando la ventana esta minimizada (iconica).</summary>
    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static partial bool IsIconic(nint hWnd);

    /// <summary>Puntos por pulgada efectivos de la ventana: la base del escalado de tamano.</summary>
    [LibraryImport("user32.dll")]
    internal static partial uint GetDpiForWindow(nint hWnd);

    [LibraryImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool SystemParametersInfoW(uint action, uint param, ref RECT rect, uint initialization);

    /// <summary>Area de trabajo del monitor primario, sin barra de tareas.</summary>
    /// <remarks>
    /// El parametro se inicializa a default antes de la llamada: el analizador de
    /// asignacion definida no ve a traves del P/Invoke que la funcion nativa lo llena,
    /// y sin eso CS0269 corta la compilacion.
    /// </remarks>
    internal static bool TryGetWorkArea(out RECT area)
    {
        area = default;
        return SystemParametersInfoW(SpiGetWorkArea, 0, ref area, 0);
    }

    /// <summary>
    /// Centra una ventana secundaria sobre su propietaria, acotada al area de trabajo.
    /// </summary>
    /// <remarks>
    /// El centro sobre la propietaria es el comportamiento que el usuario espera de una
    /// herramienta abierta desde una ventana concreta; el acotado evita que en un monitor
    /// pequeno la secundaria quede medio fuera de la pantalla.
    /// </remarks>
    internal static void CenterOverOwner(Window owner, Window child)
    {
        if (!TryGetWorkArea(out RECT area))
        {
            return;
        }

        Windows.Graphics.PointInt32 ownerPosition = owner.AppWindow.Position;
        Windows.Graphics.SizeInt32 ownerSize = owner.AppWindow.Size;
        Windows.Graphics.SizeInt32 childSize = child.AppWindow.Size;

        int x = ownerPosition.X + ((ownerSize.Width - childSize.Width) / 2);
        int y = ownerPosition.Y + ((ownerSize.Height - childSize.Height) / 2);

        child.AppWindow.Move(new Windows.Graphics.PointInt32(
            Math.Clamp(x, area.Left, Math.Max(area.Left, area.Right - childSize.Width)),
            Math.Clamp(y, area.Top, Math.Max(area.Top, area.Bottom - childSize.Height))));
    }
}
