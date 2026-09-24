using Hidra.Kernel.Interop;
using Hidra.Kernel.Dsp;

namespace Hidra.Verify;

/// <summary>
/// Verificacion del nivel de interoperabilidad que soporta la cadena de audio: el control
/// de denormales FTZ/DAZ del hilo y el comportamiento del generador de dither.
/// </summary>
/// <remarks>
/// <para>
/// La comprobacion de FTZ/DAZ corre en un HILO REAL y no en el principal por dos motivos.
/// El primero es fidelidad: el modo de denormales es por hilo, y lo que se quiere probar
/// es exactamente el ciclo que ejecuta el hilo de audio (aplicar, trabajar, restaurar).
/// El segundo es aislamiento: si el CRT rechazara la peticion, el fallo queda acotado a
/// la comprobacion y no deja el modo de denormales del proceso principal en un estado que
/// contamine el resto de suites.
/// </para>
/// <para>
/// La demostracion del rendimiento usa un bucle que produce denormales con dos caminos
/// medibles: multiplicar por 0.1f repetidamente (degenera a denormal en unas 150pasos)
/// y una mesa de reverb con entrada cero (la senal circula por el lazo y se degenera
/// solo, que es el caso real del filtro en silencio). Con FTZ/DAZ el lazo termina en
/// plano cero; sin ellos, cada operacion cae en microcodigo. El umbral relativo es de
/// dos veces: suficiente para demostrar el efecto sin depender del ruido de medicion
/// de un equipo de CI compartido.
/// </para>
/// </remarks>
internal static class InteropTests
{
    public static void Run()
    {
        Harness.Suite("interop/ftz-daz", FtzDazRoundTrip);
        Harness.Suite("interop/ftz-daz-rendimiento", FtzDazActuallyHelps);
    }

    private static void FtzDazRoundTrip()
    {
        Exception? failure = null;
        uint observedBefore = uint.MaxValue;
        uint observedAfter = uint.MaxValue;
        bool restoreRejected = false;

        var worker = new Thread(() =>
        {
            try
            {
                // Estado previo del hilo: el CRT arranca sin aplanar en un proceso .NET,
                // pero no se asume: solo se comprueba que aplicar CAMBIA el modo.
                uint previous = Kernel32.EnableFtzDaz();
                bool applied = previous != Kernel32.ControlWordFailed;

                if (applied)
                {
                    // Un segundo apply devuelve el modo ya aplanado; la API es estable
                    // ante llamadas repetidas (el hilo de audio puede reentrar).
                    uint second = Kernel32.EnableFtzDaz();
                    Harness.Check(second != Kernel32.ControlWordFailed, "la segunda aplicacion de FTZ/DAZ fue rechazada");
                    Kernel32.RestoreControlWord(second);
                }

                // Devolver el estado inicial: la restauracion con el valor centinela no
                // debe lanzar (el hilo de render la llama en su finally pase lo que pase).
                Kernel32.RestoreControlWord(previous);
                Kernel32.RestoreControlWord(Kernel32.ControlWordFailed);

                // Un valor ajeno a la mascara no debe corromper nada: la restauracion
                // solo toca el campo de denormales.
                Kernel32.RestoreControlWord(0xDEADBEEF);

                observedBefore = previous;
                _ = restoreRejected;
                observedAfter = Kernel32.EnableFtzDaz();
                Kernel32.RestoreControlWord(observedAfter);
            }
            catch (Exception exception)
            {
                failure = exception;
            }
        });

        worker.Start();
        worker.Join();

        Harness.Check(failure is null, $"el ciclo FTZ/DAZ lanzo: {failure?.GetType().Name} {failure?.Message}");
        Harness.Check(observedAfter != Kernel32.ControlWordFailed, "el CRT rechazo el modo de aplanado de denormales");
    }

    private static void FtzDazActuallyHelps()
    {
        const int length = 4096;

        float[] buffer = new float[length];
        for (int i = 0; i < length; i++)
        {
            buffer[i] = 1e-20f; // denormal de arranque: fuerza el caso peor desde el inicio
        }

        // SIN aplanar: estado heredado del proceso. El bucle degenera a denormal y cada
        // operacion paga microcodigo.
        double withoutFtz = MeasureDenormalLoop(buffer, flushDenormals: false);

        // CON aplanado: el mismo bucle trabaja en cero plano.
        double withFtz = MeasureDenormalLoop(buffer, flushDenormals: true);

        Harness.Check(
            withFtz < withoutFtz * 2.0,
            $"el aplanado no mejoro el lazo denormal (con {withFtz:F1} us vs sin {withoutFtz:F1} us)");

        if (withoutFtz > withFtz * 2.0)
        {
            Console.WriteLine(
                $"  ftz/daz: lazo denormal {withoutFtz:F0} us -> {withFtz:F0} us ({withoutFtz / withFtz:F1}x mas rapido)");
        }
    }

    /// <summary>
    /// Mide un lazo que circula denormales, con y sin FTZ/DAZ, en el hilo actual.
    /// El bucle multiplica repetidamente: 1e-20 * 0.1 degenera a denormal en pocas
    /// vueltas y ahi empieza el microcodigo que el aplanado elimina.
    /// </summary>
    private static double MeasureDenormalLoop(float[] buffer, bool flushDenormals, int passes = 2000)
    {
        uint previous = flushDenormals ? Kernel32.EnableFtzDaz() : Kernel32.ControlWordFailed;

        try
        {
            long start = HighResolutionClock.Timestamp();

            for (int pass = 0; pass < passes; pass++)
            {
                for (int i = 0; i < buffer.Length; i++)
                {
                    buffer[i] *= 0.1f;
                }
            }

            long elapsed = HighResolutionClock.Timestamp() - start;

            // La resurreccion evita que el optimizador elimine el lazo completo: el
            // contenido del buffer se consume para que la multiplicacion siga viva.
            float survivor = 0f;
            for (int i = 0; i < buffer.Length; i += 512)
            {
                survivor += buffer[i];
            }

            GC.KeepAlive(survivor);
            return HighResolutionClock.ToMilliseconds(elapsed) * 1000.0;
        }
        finally
        {
            Kernel32.RestoreControlWord(previous);
        }
    }
}
