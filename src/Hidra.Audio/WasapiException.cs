namespace Hidra.Audio;

/// <summary>
/// Fallo de la capa de audio, con el codigo <c>HRESULT</c> original.
/// </summary>
/// <remarks>
/// Se usa un tipo propio en lugar de <see cref="System.Runtime.InteropServices.COMException"/>
/// porque esa excepcion esta reservada al tiempo de ejecucion: construirla a mano para anadir
/// contexto es exactamente lo que la regla CA2201 prohibe, y con razon. Aqui se conserva el
/// codigo original para que quien capture pueda distinguir un dispositivo ocupado de un
/// dispositivo ausente, y se anade el contexto del motor en el mensaje.
/// </remarks>
internal sealed class WasapiException : Exception
{
    /// <summary>Crea la excepcion conservando el codigo de error del sistema.</summary>
    public WasapiException(string message, int hresult)
        : base(message) => HResult = hresult;

    /// <summary>Crea la excepcion encadenando la causa original.</summary>
    public WasapiException(string message, int hresult, Exception innerException)
        : base(message, innerException) => HResult = hresult;

    /// <summary>Codigo de error con el que fallo la operacion.</summary>
    public new int HResult { get; }
}
