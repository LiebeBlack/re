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
    private const uint MonitorDefaultToNearest = 2;

    /// <summary>Rectangulo Win32 en coordenadas fisicas de pantalla.</summary>
    [StructLayout(LayoutKind.Sequential)]
    internal struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct MONITORINFO
    {
        public uint cbSize;
        public RECT rcMonitor;
        public RECT rcWork;
        public uint dwFlags;
    }

    /// <summary>True cuando la ventana esta minimizada (iconica).</summary>
    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static partial bool IsIconic(nint hWnd);

    /// <summary>Puntos por pulgada efectivos de la ventana: la base del escalado de tamano.</summary>
    [LibraryImport("user32.dll")]
    internal static partial uint GetDpiForWindow(nint hWnd);

    [LibraryImport("user32.dll")]
    private static partial nint MonitorFromWindow(nint hWnd, uint dwFlags);

    [LibraryImport("user32.dll", EntryPoint = "GetMonitorInfoW", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GetMonitorInfoW(nint hMonitor, ref MONITORINFO lpmi);

    [LibraryImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool SystemParametersInfoW(uint action, uint param, ref RECT rect, uint initialization);

    /// <summary>Area de trabajo del monitor donde se ubica la ventana, o del primario si no se indica ventana.</summary>
    internal static bool TryGetWorkArea(out RECT area, nint hWnd = 0)
    {
        if (hWnd != 0)
        {
            nint monitor = MonitorFromWindow(hWnd, MonitorDefaultToNearest);
            if (monitor != 0)
            {
                MONITORINFO info = default;
                info.cbSize = (uint)Marshal.SizeOf<MONITORINFO>();
                if (GetMonitorInfoW(monitor, ref info))
                {
                    area = info.rcWork;
                    return true;
                }
            }
        }

        area = default;
        return SystemParametersInfoW(SpiGetWorkArea, 0, ref area, 0);
    }

    /// <summary>
    /// Centra una ventana secundaria sobre su propietaria, acotada al area de trabajo de su monitor.
    /// </summary>
    internal static void CenterOverOwner(Window owner, Window child)
    {
        nint ownerHandle = WinRT.Interop.WindowNative.GetWindowHandle(owner);
        if (!TryGetWorkArea(out RECT area, ownerHandle))
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
