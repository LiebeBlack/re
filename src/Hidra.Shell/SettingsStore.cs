using System.Text.Json;
using System.Text.Json.Serialization;

namespace Hidra.Shell;

/// <summary>
/// Preferencias persistidas de la aplicacion, en un JSON plano sobre el perfil del usuario.
/// </summary>
/// <remarks>
/// <para>
/// Se guarda en <c>%LOCALAPPDATA%\Hidra\settings.json</c>: es el lugar canonico para datos
/// que pertenecen al usuario y no al programa, sobrevive a actualizaciones y no requiere
/// ningun almacén del sistema (Registro, ApplicationData de WinRT) que exija identidad de
/// paquete, que es justamente lo que esta aplicacion no tiene al ser sin empaquetar.
/// </para>
/// <para>
/// La escritura es ATOMICA por construccion: se escribe un archivo temporal junto al
/// destino y se renombra encima. Un corte de luz a mitad de guardar deja a lo sumo un
/// temporal huerfano, nunca un JSON partido que impida arrancar. La lectura tolera el
/// archivo ausente, corrupto o de una version anterior: devuelve el valor por defecto
/// campo a campo, porque un ajuste roto no puede tumbar el arranque del reproductor.
/// </para>
/// </remarks>
internal sealed class SettingsStore
{
    /// <summary>Colocacion y tamano recordados de la ventana principal.</summary>
    internal sealed record WindowPlacement(int X, int Y, int Width, int Height);

    private static readonly string DirectoryPath =
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Hidra");

    private static readonly string FilePath = Path.Combine(DirectoryPath, "settings.json");

    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    // Valores por defecto compartidos entre lectura fallida y primera ejecucion.
    private const double DefaultLatencyMilliseconds = 20.0;
    private const int DefaultMode = 0; // AudioStreamMode.Exclusive
    private const bool DefaultAllowSharedFallback = true;
    private const int DefaultWidth = 1120;
    private const int DefaultHeight = 800;

    /// <summary>Latencia de buffer pedida al motor, en milisegundos.</summary>
    public double LatencyMilliseconds { get; set; } = DefaultLatencyMilliseconds;

    /// <summary>Regimen del motor. 0 = exclusivo, 1 = compartido (enum de la capa de audio).</summary>
    /// <remarks>Se guarda como entero para que el JSON no dependa del nombre del enum.</remarks>
    public int EngineMode { get; set; } = DefaultMode;

    /// <summary>True para degradar a compartido si el exclusivo es rechazado.</summary>
    public bool AllowSharedFallback { get; set; } = DefaultAllowSharedFallback;

    /// <summary>Colocacion recordada de la ventana principal, o null para centrar.</summary>
    public WindowPlacement? Placement { get; set; }

    /// <summary>Lee las preferencias del disco, tolerando cualquier estado del archivo.</summary>
    public static SettingsStore Load()
    {
        try
        {
            if (!File.Exists(FilePath))
            {
                return new SettingsStore();
            }

            string json = File.ReadAllText(FilePath);
            SettingsStore? loaded = JsonSerializer.Deserialize<SettingsStore>(json, SerializerOptions);

            return loaded ?? new SettingsStore();
        }
        catch (Exception exception) when (
            exception is IOException or JsonException or UnauthorizedAccessException)
        {
            // Un ajuste ilegible no puede impedir arrancar: se siguen los valores por defecto
            // y el archivo se reescribira entero en el primer guardado.
            return new SettingsStore();
        }
    }

    /// <summary>Escribe las preferencias de forma atomica.</summary>
    public void Save()
    {
        try
        {
            Directory.CreateDirectory(DirectoryPath);

            string temporary = $"{FilePath}.tmp";
            string json = JsonSerializer.Serialize(this, SerializerOptions);

            File.WriteAllText(temporary, json);

            // El renombrado sobre un destino existente es atomico en NTFS: nadie ve nunca un
            // archivo a medio escribir, ni un corte de luz deja el JSON partido.
            File.Move(temporary, FilePath, overwrite: true);
        }
        catch (Exception exception) when (
            exception is IOException or UnauthorizedAccessException)
        {
            // Sin permiso o con el disco lleno la sesion sigue: los ajustes simplemente no
            // se recordaron. Es preferible a tumbar el cierre de la ventana por esto.
        }
    }
}
