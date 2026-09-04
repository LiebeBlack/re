"""
Widgets - Componentes UI modernos y reutilizables.

Incluye:
  * Tooltip: ayuda contextual flotante al pasar el ratón.
  * Visualizer: ecualizador animado (canvas) que reacciona a play/pause.
  * CoverBadge: portada circular con la inicial de la pista y gradiente.
  * EllipsisLabel: label que trunca el texto con "…" según su ancho real.
"""

import math
import random
import tkinter as tk
import tkinter.font as tkfont
from typing import List, Optional

import customtkinter as ctk

from src.ui.styles import Styles, blend_colors


# ---------------------------------------------------------------------------
# Tooltip
# ---------------------------------------------------------------------------

class Tooltip:
    """
    Muestra un pequeño globo de ayuda al mantener el ratón sobre un widget.

    El globo aparece tras un breve retardo y se posiciona justo debajo
    del widget. Se destruye al salir o al hacer clic.
    """

    def __init__(self, widget: tk.Misc, text: str, delay: int = 500):
        """
        Args:
            widget: Widget al que asociar el tooltip.
            text: Texto del tooltip.
            delay: Retardo en ms antes de mostrarse.
        """
        self._widget = widget
        self._text = text
        self._delay = delay
        self._after_id: Optional[str] = None
        self._tip: Optional[tk.Toplevel] = None

        # add="+" conserva otros bindings del widget
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event=None) -> None:
        """Programa la aparición del tooltip tras el retardo."""
        self._on_leave()
        try:
            self._after_id = self._widget.after(self._delay, self._show)
        except tk.TclError:
            pass

    def _show(self) -> None:
        """Crea y posiciona la ventana del tooltip."""
        try:
            if not self._widget.winfo_exists():
                return
            x = self._widget.winfo_rootx()
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6

            tip = tk.Toplevel(self._widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tip.attributes("-topmost", True)

            frame = ctk.CTkFrame(
                tip,
                fg_color=Styles.SECONDARY_COLOR,
                corner_radius=8,
                border_width=1,
                border_color=Styles.BORDER_COLOR,
            )
            frame.pack()

            label = ctk.CTkLabel(
                frame,
                text=self._text,
                font=Styles.SMALL_FONT,
                text_color=Styles.TEXT_COLOR,
            )
            label.pack(padx=9, pady=5)

            self._tip = tip
        except tk.TclError:
            self._tip = None

    def _on_leave(self, event=None) -> None:
        """Cancela el retardo y destruye el tooltip si estaba visible."""
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


# ---------------------------------------------------------------------------
# Visualizer (ecualizador animado)
# ---------------------------------------------------------------------------

class Visualizer(tk.Canvas):
    """
    Ecualizador de barras dibujado en un Canvas.

    Cuando está reproduciendo, las barras bailan con una onda
    pseudoaleatoria suave (~25 fps). En pausa/stop quedan en un nivel
    bajo estático. Los colores de las barras usan el tema actual.
    """

    # Periodo de animación: 60 ms (~16 fps) es suave y barato para la UI
    ANIM_STEP_MS = 60

    def __init__(
        self,
        master,
        bars: int = 22,
        height: int = 40,
        bg: Optional[str] = None,
        bar_width: Optional[int] = None,
        **kwargs,
    ):
        """
        Args:
            master: Widget padre.
            bars: Número de barras del ecualizador.
            height: Altura del canvas.
            bg: Color de fondo (default: Styles.SECONDARY_COLOR).
            bar_width: Ancho fijo de barra (default: automático).
            **kwargs: Argumentos extra para tk.Canvas.
        """
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("height", height)
        super().__init__(master, bg=bg or Styles.SECONDARY_COLOR, **kwargs)

        self._bar_count = max(4, bars)
        self._fixed_bar_width = bar_width
        self._playing = False
        self._phase = random.uniform(0, 1000)
        self._after_id: Optional[str] = None
        self._destroyed = False

        # Re-dibujar al cambiar de tamaño (responsividad)
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Destroy>", self._on_destroy)

    # -- Estado -----------------------------------------------------------

    def set_playing(self, playing: bool) -> None:
        """
        Activa/desactiva la animación.

        Args:
            playing: True para animar las barras, False para dejarlas bajas.
        """
        if playing == self._playing:
            return
        self._playing = playing
        if playing:
            self._start_loop()
        else:
            self._stop_loop()
            self._redraw()

    def is_playing(self) -> bool:
        """Retorna True si la animación está activa."""
        return self._playing

    # -- Ciclo de animación ------------------------------------------------

    def _start_loop(self) -> None:
        if self._after_id is None:
            self._tick()

    def _stop_loop(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _on_destroy(self, event=None) -> None:
        """Limpia el after pendiente al destruir el widget."""
        self._destroyed = True
        self._stop_loop()

    def _tick(self) -> None:
        if self._destroyed or not self._playing:
            self._after_id = None
            return
        self._phase += 1
        self._redraw()
        try:
            self._after_id = self.after(self.ANIM_STEP_MS, self._tick)
        except tk.TclError:
            self._after_id = None

    # -- Dibujo ------------------------------------------------------------

    def _bar_height(self, i: int) -> float:
        """
        Calcula la altura normalizada (0..1) de la barra i.

        Reproduciendo: suma de senos con frecuencias distintas + ruido
        determinista, que se ve natural sin coste.
        Pausa/stop: nivel bajo casi constante con mínima variación.
        """
        if self._playing:
            t = self._phase * 0.22
            wave = (
                0.5 * math.sin(t + i * 0.85)
                + 0.3 * math.sin(t * 1.7 + i * 1.6)
                + 0.2 * math.sin(t * 3.1 + i * 0.4)
            )
            noise = 0.25 * math.sin(i * 12.9898 * 0.1 + self._phase * 0.05)
            h = 0.28 + 0.72 * max(0.0, min(1.0, (wave + 1.0) / 2.0 + noise * 0.3))
        else:
            h = 0.10 + 0.05 * math.sin(i * 2.3 + self._phase * 0.2)
        return max(0.06, min(1.0, h))

    def _redraw(self) -> None:
        """Redibuja todas las barras según el tamaño actual del canvas."""
        try:
            self.delete("all")
        except tk.TclError:
            return

        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 2 or height <= 2:
            return

        n = self._bar_count
        gap = 3
        if self._fixed_bar_width:
            bar_w = self._fixed_bar_width
        else:
            bar_w = max(2, (width - gap * (n - 1)) // n)

        accent = Styles.ACCENT_COLOR
        glow = Styles.GLOW_COLOR
        bg = self.cget("bg")

        for i in range(n):
            h = self._bar_height(i)
            bar_h = max(3, int(height * h))
            x1 = i * (bar_w + gap)
            y1 = height - bar_h
            x2 = x1 + bar_w

            # Gradiente vertical de color por barra (acento → glow)
            t = i / max(1, n - 1)
            color = blend_colors(accent, glow, t)
            color = blend_colors(bg, color, 0.55 + 0.45 * h)

            # Barra con extremo superior redondeado (rectángulo + óvalo)
            radius = min(bar_w, bar_h) / 2.0
            if bar_h > radius * 2:
                self.create_rectangle(x1, y1 + radius, x2, height, fill=color, outline="")
                self.create_oval(x1, y1, x2, y1 + radius * 2, fill=color, outline="")
            else:
                self.create_oval(x1, y1, x2, height, fill=color, outline="")


# ---------------------------------------------------------------------------
# CoverBadge (portada de la pista)
# ---------------------------------------------------------------------------

class CoverBadge(tk.Canvas):
    """
    Cuadro redondeado con la inicial de la pista y gradiente de tema.

    Simula la portada de álbum cuando no hay carátula real.
    """

    def __init__(self, master, size: int = 76, text: str = "♪", **kwargs):
        """
        Args:
            master: Widget padre.
            size: Lado del canvas (cuadrado).
            text: Inicial/texto a mostrar (normalmente la inicial del título).
            **kwargs: Argumentos extra para tk.Canvas.
        """
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        super().__init__(master, **kwargs)

        self._size = size
        self._text = text or "♪"
        self._draw()

    def set_text(self, text: str) -> None:
        """Actualiza la inicial mostrada y redibuja."""
        self._text = (text or "♪").strip()[:2]
        self._draw()

    def _draw(self) -> None:
        """Dibuja el fondo con gradiente (simulado por franjas) y el texto."""
        try:
            self.delete("all")
        except tk.TclError:
            return

        s = self._size
        radius = int(s * 0.24)
        color_a = Styles.GRADIENT_A
        color_b = Styles.GRADIENT_B

        # Gradiente vertical simulado con franjas horizontales redondeadas
        stripes = 12
        stripe_h = s / stripes
        for i in range(stripes):
            t = i / (stripes - 1)
            color = blend_colors(color_a, color_b, t)
            y0 = i * stripe_h
            y1 = y0 + stripe_h + 1
            if y0 < s:
                self._rounded_rect(self, 0, y0, s, min(y1, s), radius, fill=color, outline="")

        # Inicial centrada en grande
        try:
            font = tkfont.Font(family=Styles.FONT_FAMILY, size=int(s * 0.34), weight="bold")
        except tk.TclError:
            font = None
        self.create_text(
            s // 2,
            s // 2 + 1,
            text=self._text.upper(),
            fill="#ffffff",
            font=font,
        )

    @staticmethod
    def _rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs) -> None:
        """
        Dibuja un rectángulo redondeado en el canvas.

        Usa dos rectángulos + cuatro óvalos para simular esquinas suaves.
        """
        r = min(radius, (y2 - y1) / 2, (x2 - x1) / 2)
        canvas.create_rectangle(x1, y1 + r, x2, y2 - r, **kwargs)
        canvas.create_rectangle(x1 + r, y1, x2 - r, y2, **kwargs)
        canvas.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, **kwargs)
        canvas.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, **kwargs)
        canvas.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, **kwargs)
        canvas.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, **kwargs)


# ---------------------------------------------------------------------------
# AlbumArt (carátula real o inicial con gradiente)
# ---------------------------------------------------------------------------

class AlbumArt(tk.Canvas):
    """
    Portada del álbum: muestra la carátula embebida (PNG/JPEG vía Pillow)
    o, si no existe, la inicial con gradiente del tema (CoverBadge).
    """

    def __init__(self, master, size: int = 76, **kwargs):
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
        super().__init__(master, **kwargs)
        self._size = size
        self._art_path: Optional[str] = None
        self._photo = None
        # Badge de respaldo (widget embebido en el canvas). Se muestra o
        # se oculta según haya carátula real (los widgets embebidos de un
        # canvas siempre se dibujan encima de los items, por eso se ocultan).
        self._badge = CoverBadge(self, size=size, text="♪")
        self._badge.place(x=0, y=0)

    def set_art(self, image_path: Optional[str], fallback_text: str = "♪") -> None:
        """
        Muestra la carátula real o vuelve al badge con la inicial.

        Args:
            image_path: Ruta de imagen (PNG/JPEG) o None.
            fallback_text: Texto del badge cuando no hay carátula.
        """
        self._art_path = image_path
        try:
            self.delete("art")
        except tk.TclError:
            pass
        self._photo = None

        if not image_path:
            self._badge.set_text(fallback_text or "♪")
            self._badge.place(x=0, y=0)
            return

        try:
            from PIL import Image, ImageTk
            with Image.open(image_path) as img:
                img = img.convert("RGB")
                img.thumbnail((self._size, self._size), Image.LANCZOS)
                self._photo = ImageTk.PhotoImage(img)
            self._badge.place_forget()
            self.create_image(self._size // 2, self._size // 2,
                              image=self._photo, anchor="center", tags="art")
        except Exception:
            # Imagen inválida: volver al badge
            self._badge.set_text(fallback_text or "♪")
            self._badge.place(x=0, y=0)

    def get_art_path(self) -> Optional[str]:
        return self._art_path


# ---------------------------------------------------------------------------
# WaveformView (forma de onda de la pista + cabezal de reproducción)
# ---------------------------------------------------------------------------

class WaveformView(tk.Canvas):
    """
    Dibuja la envolvente (picos min/max) de la pista decodificada en modo HQ
    con un gradiente del tema y un cabezal de reproducción en vivo.
    Todo se dibuja con un único polígono + línea (muy barato en la GPU).
    """

    def __init__(self, master, height: int = 40, bg: Optional[str] = None, **kwargs):
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("height", height)
        super().__init__(master, bg=bg or Styles.SECONDARY_COLOR, **kwargs)
        self._mins: Optional[list] = None
        self._maxs: Optional[list] = None
        self._playhead = -1.0  # fracción 0..1 (o -1 sin cabezal)
        self.bind("<Configure>", lambda e: self.redraw())

    def set_waveform(self, mins, maxs) -> None:
        """
        Define los picos de la forma de onda (arrays/lista del mismo tamaño).

        Args:
            mins: Valores negativos de envolvente (0..-1).
            maxs: Valores positivos de envolvente (0..1).
        """
        self._mins = list(mins)
        self._maxs = list(maxs)
        self.redraw()

    def set_playhead(self, fraction: float) -> None:
        """
        Mueve el cabezal de reproducción.

        Args:
            fraction: Posición relativa 0..1 (o -1 para ocultarlo).
        """
        fraction = max(-1.0, min(1.0, fraction))
        if abs(fraction - self._playhead) < 0.004:
            return
        self._playhead = fraction
        self.redraw()

    def clear(self) -> None:
        """Vacía la forma de onda."""
        self._mins = None
        self._maxs = None
        self._playhead = -1.0
        self.redraw()

    def redraw(self) -> None:
        """Redibuja la onda y el cabezal al tamaño actual."""
        try:
            self.delete("all")
        except tk.TclError:
            return
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 2 or height <= 2:
            return

        mid = height / 2.0
        amp = max(3.0, mid - 2.0)

        if self._mins is None or self._maxs is None:
            # Sin datos: línea base sutil
            self.create_line(0, mid, width, mid, fill=Styles.BORDER_COLOR, width=1)
            return

        n = len(self._maxs)
        if n == 0:
            return

        color_a = Styles.ACCENT_COLOR
        color_b = Styles.GLOW_COLOR

        # Construir el polígono de la envolvente (cima + fondo invertido)
        points = []
        for i in range(n):
            x = width * i / (n - 1)
            y = mid - float(self._maxs[i]) * amp
            points.append((x, y))
        for i in range(n - 1, -1, -1):
            x = width * i / (n - 1)
            y = mid - float(self._mins[i]) * amp
            points.append((x, y))

        flat = [c for pt in points for c in pt]
        # Gradiente simulado: polígono de color + sombra glow inferior
        self.create_polygon(flat, fill=blend_colors(Styles.SECONDARY_COLOR, color_a, 0.35),
                            outline="")
        # Línea de pico superior en gradiente (glow)
        line_pts = []
        for i in range(n):
            x = width * i / (n - 1)
            line_pts.extend((x, mid - float(self._maxs[i]) * amp))
        self.create_line(*line_pts, fill=blend_colors(color_a, color_b, 0.5), width=1.5)

        # Cabezal de reproducción
        if self._playhead >= 0:
            x = self._playhead * width
            self.create_line(x, 2, x, height - 2, fill=Styles.TEXT_COLOR, width=2)


# ---------------------------------------------------------------------------
# EllipsisLabel (texto que se trunca con "…")
# ---------------------------------------------------------------------------

class EllipsisLabel(ctk.CTkLabel):
    """
    Label que muestra el texto completo almacenado y lo trunca con "…"
    según el ancho real del widget (se re-adapta al redimensionar).

    Uso: crear con el texto completo y llamar a set_full_text() para
    cambiarlo. Nunca usar configure(text=...) directamente.
    """

    def __init__(self, master, text: str = "", **kwargs):
        self._full_text = text
        self._font = kwargs.get("font", Styles.NORMAL_FONT)
        kwargs.setdefault("anchor", "w")
        super().__init__(master, text=text, **kwargs)

        # Objeto de fuente cacheado (crear uno por evento Configure es caro)
        self._font_obj = None
        self._last_width = -1

        # Re-trunca al redimensionar (responsividad)
        self.bind("<Configure>", lambda e: self._refresh())

    def set_full_text(self, text: str) -> None:
        """Establece el texto completo y lo trunca según el ancho actual."""
        self._full_text = text or ""
        self._last_width = -1
        self._refresh()

    def _refresh(self) -> None:
        """Recalcula el texto visible para que quepa en el ancho actual."""
        try:
            if not self.winfo_exists():
                return
            width = self.winfo_width()
        except tk.TclError:
            return
        if width <= 1 or not self._full_text:
            return
        if width == self._last_width:
            return  # sin cambios de ancho: nada que recalcular
        self._last_width = width

        try:
            if self._font_obj is None:
                self._font_obj = tkfont.Font(font=self._font)
            font = self._font_obj
            available = max(20, width - 8)  # margen de padding interno
        except tk.TclError:
            return

        shown = self._fit_text(font, available)
        try:
            if self.cget("text") != shown:
                self.configure(text=shown)
        except tk.TclError:
            pass

    def _fit_text(self, font, available: int) -> str:
        """Ajusta el texto con elipsis para que quepa en available px."""
        text = self._full_text
        if font.measure(text) <= available:
            return text

        ellipsis = "…"
        low, high = 0, len(text)
        # Búsqueda binaria del prefijo más largo que cabe con la elipsis
        while low < high:
            mid = (low + high + 1) // 2
            candidate = text[:mid] + ellipsis
            if font.measure(candidate) <= available:
                low = mid
            else:
                high = mid - 1
        return text[:low] + ellipsis if low > 0 else ellipsis