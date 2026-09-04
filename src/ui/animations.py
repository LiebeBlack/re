"""
Animations - Motor de animaciones ligero para la UI (basado en after()).

Proporciona:
  * Curvas de easing (ease_out_cubic, ease_in_out_quad).
  * Tween genérico de valores numéricos.
  * Tween de colores (mezcla hexadecimal).
  * Pulse: resplandor continuo (glow) para el botón de play.
  * bind_hover_effect: escala + color al pasar el ratón.

Todo se ejecuta en el hilo principal vía widget.after(), por lo que es
seguro para Tkinter y se cancela automáticamente al destruir los widgets.
"""

import math
import tkinter as tk
from typing import Callable, Optional

from src.ui.styles import blend_colors, lighten, darken


# ---------------------------------------------------------------------------
# Curvas de easing
# ---------------------------------------------------------------------------

def ease_out_cubic(t: float) -> float:
    """Easing suave: arranca rápido y frena al final."""
    return 1 - (1 - t) ** 3


def ease_in_out_quad(t: float) -> float:
    """Easing simétrico: acelera y desacelera."""
    return 2 * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 2) / 2


def ease_out_back(t: float) -> float:
    """Easing con rebote sutil al final (efecto elástico)."""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# ---------------------------------------------------------------------------
# Tween genérico
# ---------------------------------------------------------------------------

class Tween:
    """
    Animación de un valor numérico desde un estado inicial a uno final.

    Uso típico: animar dimensiones, paddings o cualquier propiedad numérica.

    Attributes:
        STEP_MS: Intervalo de refresco por defecto (~60 fps).
    """

    STEP_MS = 16

    def __init__(
        self,
        master: tk.Misc,
        start: float,
        end: float,
        duration: int,
        setter: Callable[[float], None],
        easing: Callable[[float], float] = ease_out_cubic,
        step_ms: Optional[int] = None,
        on_done: Optional[Callable[[], None]] = None,
    ):
        """
        Args:
            master: Widget que programa los after() (hilo principal).
            start: Valor inicial.
            end: Valor final.
            duration: Duración en milisegundos.
            setter: Callable que recibe el valor interpolado en cada paso.
            easing: Función de easing (default: ease_out_cubic).
            step_ms: Intervalo entre pasos (default: STEP_MS).
            on_done: Callable al terminar.
        """
        self._master = master
        self._start = start
        self._end = end
        self._duration = max(1, duration)
        self._setter = setter
        self._easing = easing
        self._step_ms = step_ms or self.STEP_MS
        self._on_done = on_done

        self._elapsed = 0
        self._after_id: Optional[str] = None
        self._finished = False

    def start(self) -> None:
        """Inicia la animación (no-op si ya está en marcha)."""
        if self._after_id is not None:
            return
        self._finished = False
        self._tick()

    def cancel(self) -> None:
        """Cancela la animación sin ejecutar on_done."""
        self._finished = True
        if self._after_id is not None:
            try:
                self._master.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def is_running(self) -> bool:
        """Retorna True si la animación sigue activa."""
        return self._after_id is not None and not self._finished

    def _tick(self) -> None:
        """Avanza un paso de la animación."""
        if self._finished:
            return
        try:
            if not self._master.winfo_exists():
                self._finished = True
                return
        except tk.TclError:
            self._finished = True
            return

        self._elapsed += self._step_ms
        t = min(1.0, self._elapsed / self._duration)

        value = self._start + (self._end - self._start) * self._easing(t)
        try:
            self._setter(value)
        except tk.TclError:
            self._finished = True
            return

        if t >= 1.0:
            self._finished = True
            self._after_id = None
            if self._on_done:
                try:
                    self._on_done()
                except tk.TclError:
                    pass
        else:
            try:
                self._after_id = self._master.after(self._step_ms, self._tick)
            except tk.TclError:
                self._finished = True


def tween_color(
    master: tk.Misc,
    start_color: str,
    end_color: str,
    duration: int,
    setter: Callable[[str], None],
    easing: Callable[[float], float] = ease_out_cubic,
    step_ms: Optional[int] = None,
    on_done: Optional[Callable[[], None]] = None,
) -> Tween:
    """
    Anima un color desde start_color hasta end_color.

    Args:
        master: Widget que programa los after().
        start_color: Color inicial '#rrggbb'.
        end_color: Color final '#rrggbb'.
        duration: Duración en milisegundos.
        setter: Callable que recibe el color interpolado ('#rrggbb').
        easing: Función de easing.
        step_ms: Intervalo entre pasos.
        on_done: Callable al terminar.

    Returns:
        El Tween creado (para poder cancelarlo).
    """
    def _setter(t: float) -> None:
        setter(blend_colors(start_color, end_color, t))

    tween = Tween(
        master, 0.0, 1.0, duration, _setter,
        easing=easing, step_ms=step_ms, on_done=on_done,
    )
    tween.start()
    return tween


# ---------------------------------------------------------------------------
# Pulse (resplandor continuo)
# ---------------------------------------------------------------------------

class Pulse:
    """
    Oscila el color de una propiedad entre dos colores de forma continua.

    Se usa para dar un "glow" pulsante al botón de play mientras suena.
    """

    def __init__(
        self,
        master: tk.Misc,
        setter: Callable[[str], None],
        base_color: str,
        pulse_color: str,
        period_ms: int = 900,
    ):
        """
        Args:
            master: Widget que programa los after().
            setter: Callable que recibe el color interpolado.
            base_color: Color base (reposo).
            pulse_color: Color del pico del resplandor.
            period_ms: Periodo de la oscilación en ms.
        """
        self._master = master
        self._setter = setter
        self._base = base_color
        self._pulse = pulse_color
        self._period = max(100, period_ms)

        self._running = False
        self._after_id: Optional[str] = None
        self._phase = 0.0
        self._last_color: Optional[str] = None

    def start(self) -> None:
        """Comienza el pulso (no-op si ya corre)."""
        if self._running:
            return
        self._running = True
        self._last_color = None
        self._tick()

    def stop(self) -> None:
        """Detiene el pulso y restaura el color base."""
        self._running = False
        if self._after_id is not None:
            try:
                self._master.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        try:
            self._setter(self._base)
        except tk.TclError:
            pass

    def set_colors(self, base_color: str, pulse_color: str) -> None:
        """Actualiza los colores del pulso (útil al cambiar de tema)."""
        self._base = base_color
        self._pulse = pulse_color
        if not self._running:
            try:
                self._setter(self._base)
            except tk.TclError:
                pass

    def is_running(self) -> bool:
        """Retorna True si el pulso está activo."""
        return self._running

    def _tick(self) -> None:
        """Calcula el color actual de la onda senoidal."""
        if not self._running:
            return
        try:
            if not self._master.winfo_exists():
                self._running = False
                return
        except tk.TclError:
            self._running = False
            return

        # Paso de 30 ms (~33 fps): suficiente para un resplandor suave
        # sin saturar la UI (cada configure de CTk redibuja el widget).
        step_ms = 30
        self._phase += 2 * math.pi * step_ms / self._period
        wave = 0.5 * (1 + math.sin(self._phase))

        color = blend_colors(self._base, self._pulse, wave * 0.55)
        # No redibujar si el color apenas cambió (evita trabajo inútil)
        if color == self._last_color:
            pass
        else:
            self._last_color = color
            try:
                self._setter(color)
            except tk.TclError:
                self._running = False
                return

        try:
            self._after_id = self._master.after(step_ms, self._tick)
        except tk.TclError:
            self._running = False


# ---------------------------------------------------------------------------
# Efecto hover (escala + color)
# ---------------------------------------------------------------------------

def bind_hover_effect(
    widget: tk.Misc,
    master: tk.Misc,
    grow: int = 6,
    duration: int = 180,
    hover_color: Optional[str] = None,
    normal_color: Optional[str] = None,
) -> None:
    """
    Añade dinamismo al pasar el ratón: escala el widget y opcionalmente
    anima su color de fondo.

    Args:
        widget: Widget a animar (CTkButton, CTkFrame...).
        master: Widget que programa los after() (normalmente el padre).
        grow: Incremento de tamaño en píxeles al hacer hover.
        duration: Duración de la animación en ms.
        hover_color: Color de fondo al hacer hover (opcional).
        normal_color: Color de fondo en reposo (opcional, solo si hover_color).
    """
    state = {"entered": False, "tween": None}

    def _get_dim() -> tuple:
        try:
            w = int(widget.cget("width"))
            h = int(widget.cget("height"))
        except (tk.TclError, ValueError):
            w = h = 0
        return w, h

    def _get_color(prop: str) -> Optional[str]:
        try:
            color = widget.cget(prop)
            return color if color and color != "default" else None
        except tk.TclError:
            return None

    def _animate_color(end: str) -> None:
        if hover_color is None or normal_color is None:
            return
        start = _get_color("fg_color")
        if not start or start == end:
            return
        try:
            tween_color(master, start, end, duration, lambda c: widget.configure(fg_color=c))
        except tk.TclError:
            pass

    def _on_enter(event=None) -> None:
        if state["entered"]:
            return
        state["entered"] = True
        w, h = _get_dim()
        if w and h:
            if state["tween"] is not None:
                state["tween"].cancel()
            state["tween"] = Tween(
                master, w, w + grow, duration,
                lambda v: widget.configure(width=int(v)),
            )
            state["tween"].start()
        _animate_color(hover_color)  # type: ignore[arg-type]

    def _on_leave(event=None) -> None:
        if not state["entered"]:
            return
        state["entered"] = False
        w, h = _get_dim()
        if w and h:
            if state["tween"] is not None:
                state["tween"].cancel()
            state["tween"] = Tween(
                master, w, w - grow, duration,
                lambda v: widget.configure(width=int(v)),
            )
            state["tween"].start()
        _animate_color(normal_color)  # type: ignore[arg-type]

    widget.bind("<Enter>", _on_enter, add="+")
    widget.bind("<Leave>", _on_leave, add="+")


def pulse_color(color: str, amount: float = 0.15) -> str:
    """Helper: color más brillante para usar como pico de pulso."""
    return lighten(color, amount)


def fade_to(color: str, amount: float = 0.12) -> str:
    """Helper: color más oscuro (fondo de tarjetas elevadas)."""
    return darken(color, amount)