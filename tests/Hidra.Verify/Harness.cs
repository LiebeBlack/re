namespace Hidra.Verify;

/// <summary>
/// Arnes minimo sin dependencias externas. Se evita deliberadamente un framework de test
/// con reflexion: ademas de no aportar nada aqui, obligaria a abrir una excepcion en la
/// configuracion de recorte y AOT que es precisamente lo que se quiere demostrar.
/// </summary>
internal static class Harness
{
    private static readonly List<string> Failures = [];
    private static string _suite = "general";
    private static int _checks;

    /// <summary>Numero de comprobaciones ejecutadas.</summary>
    public static int Checks => _checks;

    /// <summary>Ejecuta una suite. Una excepcion no detiene el resto de la verificacion.</summary>
    public static void Suite(string name, Action body)
    {
        _suite = name;
        try
        {
            body();
        }
        catch (Exception exception)
        {
            Failures.Add($"{name}: excepcion no controlada {exception.GetType().Name}: {exception.Message}");
        }
    }

    /// <summary>Comprueba una condicion.</summary>
    public static void Check(bool condition, string message)
    {
        _checks++;
        if (!condition)
        {
            Failures.Add($"{_suite}: {message}");
        }
    }

    /// <summary>Comprueba igualdad exacta de un float.</summary>
    public static void Same(float expected, float actual, string message)
    {
        _checks++;
        if (BitConverter.SingleToInt32Bits(expected) != BitConverter.SingleToInt32Bits(actual))
        {
            Failures.Add($"{_suite}: {message} (esperado {expected:R}, obtenido {actual:R})");
        }
    }

    /// <summary>Comprueba una igualdad con tolerancia absoluta.</summary>
    public static void Close(double expected, double actual, double tolerance, string message)
    {
        _checks++;
        if (double.IsNaN(actual) || double.IsInfinity(actual) || Math.Abs(expected - actual) > tolerance)
        {
            Failures.Add($"{_suite}: {message} (esperado {expected:R} +/- {tolerance:R}, obtenido {actual:R})");
        }
    }

    /// <summary>Comprueba que no hay NaN ni infinitos.</summary>
    public static void Finite(ReadOnlySpan<float> values, string message)
    {
        _checks++;
        for (int i = 0; i < values.Length; i++)
        {
            if (!float.IsFinite(values[i]))
            {
                Failures.Add($"{_suite}: {message} (indice {i} vale {values[i]})");
                return;
            }
        }
    }

    /// <summary>Imprime el resumen y devuelve el codigo de salida del proceso.</summary>
    public static int Report()
    {
        Console.WriteLine();
        Console.WriteLine($"Comprobaciones: {_checks}");
        Console.WriteLine($"Fallos: {Failures.Count}");

        foreach (string failure in Failures)
        {
            Console.WriteLine($"  FALLO {failure}");
        }

        if (Failures.Count == 0)
        {
            Console.WriteLine();
            Console.WriteLine("VERIFICACION CORRECTA");
            return 0;
        }

        Console.WriteLine();
        Console.WriteLine("VERIFICACION FALLIDA");
        return 1;
    }
}
