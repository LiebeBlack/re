"""
dsp - Procesado digital de señal (DSP) para máxima calidad de audio.

Proporciona, sobre buffers float32 (numpy):
  * Lectura de pistas con soundfile (WAV / FLAC hasta 24-bit / MP3 / OGG...).
  * Ecualizador gráfico de 10 bandas (31 Hz - 16 kHz) con filtros biquad
    peaking (RBJ cookbook) aplicados en cascada vía scipy.signal.
  * Filtro paso-alto subsónico (rumble) de 25 Hz.
  * Normalización: ReplayGain (etiquetas) y ganancia de pico (Peak Gain).
  * Conversión float32 -> int16 lista para pygame.sndarray.
  * Análisis visual: picos de forma de onda y perfil espectral promedio.

scipy es un requisito opcional: si no está disponible, el EQ se omite
(se registra una advertencia) y el resto de funciones sigue funcionando.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np

# Frecuencias centrales de las 10 bandas (estándar ISO)
BAND_FREQS: List[float] = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

# Frecuencia del filtro paso-alto subsónico (Hz)
HP_FILTER_FREQ = 25.0
HP_FILTER_Q = 0.707

_MAX_INT16 = 32767.0

try:  # scipy es opcional (solo necesario para el EQ)
    from scipy import signal as _scipy_signal
    _HAS_SCIPY = True
except Exception:  # pragma: no cover - depende del entorno
    _scipy_signal = None
    _HAS_SCIPY = False


# ---------------------------------------------------------------------------
# Utilidades de ganancia
# ---------------------------------------------------------------------------

def db_to_linear(db: float) -> float:
    """Convierte dB a factor lineal (1.0 = 0 dB)."""
    return float(10.0 ** (db / 20.0))


def linear_to_db(value: float) -> float:
    """Convierte factor lineal a dB."""
    value = max(abs(value), 1e-9)
    return float(20.0 * np.log10(value))


# ---------------------------------------------------------------------------
# Coeficientes de filtros (RBJ Audio EQ Cookbook)
# ---------------------------------------------------------------------------

def _peaking_coeffs(fs: int, f0: float, gain_db: float, q: float = 1.0) -> List[float]:
    """
    Coeficientes de un filtro peaking (campana) biquad.

    Args:
        fs: Frecuencia de muestreo.
        f0: Frecuencia central.
        gain_db: Ganancia en dB (positiva = realce, negativa = corte).
        q: Factor de calidad.

    Returns:
        Lista [b0, b1, b2, a1, a2] ya normalizada por a0.
    """
    a = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / fs
    cw = np.cos(w0)
    alpha = np.sin(w0) / (2.0 * q)

    b0 = 1.0 + alpha * a
    b1 = -2.0 * cw
    b2 = 1.0 - alpha * a
    a0 = 1.0 + alpha / a
    a1 = -2.0 * cw
    a2 = 1.0 - alpha / a
    return [b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0]


def _highpass_coeffs(fs: int, f0: float, q: float = 0.707) -> List[float]:
    """
    Coeficientes de un filtro paso-alto biquad (Butterworth por defecto).

    Args:
        fs: Frecuencia de muestreo.
        f0: Frecuencia de corte.
        q: Factor de calidad.

    Returns:
        Lista [b0, b1, b2, a1, a2].
    """
    w0 = 2.0 * np.pi * f0 / fs
    cw = np.cos(w0)
    sw = np.sin(w0)
    alpha = sw / (2.0 * q)

    b0 = (1.0 + cw) / 2.0
    b1 = -(1.0 + cw)
    b2 = (1.0 + cw) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cw
    a2 = 1.0 - alpha
    return [b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0]


def has_scipy() -> bool:
    """Retorna True si scipy está disponible (necesario para el EQ)."""
    return _HAS_SCIPY


# ---------------------------------------------------------------------------
# Aplicación del EQ
# ---------------------------------------------------------------------------

def apply_eq(
    samples: np.ndarray,
    fs: int,
    gains_db: List[float],
    preamp_db: float = 0.0,
    hp_filter: bool = False,
) -> np.ndarray:
    """
    Aplica la cadena de audio: preamp -> paso-alto (opcional) -> 10 bandas.

    Args:
        samples: Buffer float32 de forma (N, canales).
        fs: Frecuencia de muestreo.
        gains_db: 10 ganancias en dB (se trunca/rellena a 10).
        preamp_db: Ganancia previa en dB.
        hp_filter: True para activar el filtro paso-alto subsónico.

    Returns:
        Buffer procesado (misma forma). Sin scipy devuelve copia sin EQ.
    """
    if samples.size == 0:
        return samples

    out = samples.astype(np.float32, copy=True)

    if not _HAS_SCIPY:
        # Sin scipy no hay filtros; solo se aplica el preamp (lineal).
        out *= db_to_linear(preamp_db)
        return out

    # Ganancia previa (evita recortes al sumar el realce de bandas)
    if preamp_db:
        out = out * db_to_linear(preamp_db)

    # Normalizar la lista de ganancias a 10 bandas
    gains = [float(g) for g in gains_db][: len(BAND_FREQS)]
    while len(gains) < len(BAND_FREQS):
        gains.append(0.0)

    sections = []
    if hp_filter:
        sections.append(_highpass_coeffs(fs, HP_FILTER_FREQ, HP_FILTER_Q))
    for freq, gain in zip(BAND_FREQS, gains):
        if abs(gain) < 0.05:  # banda plana: saltar (ahorra CPU)
            continue
        sections.append(_peaking_coeffs(fs, freq, gain))

    if not sections:
        return out

    sos = np.asarray(sections, dtype=np.float64)
    try:
        out = _scipy_signal.sosfilt(sos, out, axis=0).astype(np.float32)
    except Exception:
        # Fallback: aplicar cada sección por separado
        for b0, b1, b2, a1, a2 in sections:
            out = _scipy_signal.lfilter([b0, b1, b2], [1.0, a1, a2], out, axis=0).astype(np.float32)
    return out


# ---------------------------------------------------------------------------
# Lectura y análisis
# ---------------------------------------------------------------------------

def read_track(file_path: str) -> Optional[Dict]:
    """
    Lee una pista a float32 con soundfile.

    Args:
        file_path: Ruta del archivo.

    Returns:
        Dict con {'samples': np.ndarray float32 (N, ch), 'rate': int,
        'duration': float} o None si no se pudo decodificar.
    """
    try:
        import soundfile as sf
        data, rate = sf.read(file_path, dtype="float32", always_2d=True)
        if data.size == 0:
            return None
        return {
            "samples": np.ascontiguousarray(data),
            "rate": int(rate),
            "duration": float(data.shape[0]) / rate,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"No se pudo leer {file_path} con soundfile: {e}")
        return None


def replaygain_db(file_path: str) -> Optional[float]:
    """
    Lee la etiqueta ReplayGain de la pista (track gain) si existe.

    Args:
        file_path: Ruta del archivo.

    Returns:
        Ganancia en dB o None si no hay etiqueta.
    """
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(file_path)
        if audio is None:
            return None
        tags = audio.tags or {}
        candidates = []

        if hasattr(audio, "tags") and audio.tags:
            for key in ("replaygain_track_gain", "TXXX:REPLAYGAIN_TRACK_GAIN"):
                value = tags.get(key)
                if value:
                    candidates.append(str(value))

        # Vorbis/ID3: recorrer todas las claves por si el formato difiere
        if not candidates:
            for key, value in tags.items():
                text = str(value)
                if "replaygain_track_gain" in key.lower():
                    candidates.append(text)
        if not candidates:
            return None

        raw = candidates[0].strip().lower().replace(" db", "")
        raw = raw.split()[0] if raw.split() else raw
        return float(raw)
    except Exception:
        return None


def peak_gain_db(samples: np.ndarray, target_db: float = -1.0) -> float:
    """
    Calcula la ganancia de pico para alcanzar target_db sin recortar.

    Args:
        samples: Buffer float32.
        target_db: Nivel objetivo en dBFS (default -1 dB).

    Returns:
        Ganancia a aplicar en dB.
    """
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak <= 1e-6:
        return 0.0
    current_db = linear_to_db(peak)
    return float(target_db - current_db)


def to_int16(samples: np.ndarray) -> np.ndarray:
    """
    Convierte float32 (rango -1..1) a int16 con saturación y contiguidad.

    Args:
        samples: Buffer float32.

    Returns:
        Buffer int16 de la misma forma.
    """
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * _MAX_INT16).astype(np.int16)


def compute_waveform_peaks(samples: np.ndarray, width: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calcula picos (min/max) de envolvente para dibujar la forma de onda.

    Args:
        samples: Buffer float32 (N, ch) o (N,).
        width: Número de columnas de píxeles.

    Returns:
        Tupla (mins, maxs) de numpy arrays de longitud `width`.
    """
    mono = samples
    if mono.ndim == 2:
        mono = np.mean(mono, axis=1)
    mono = np.abs(mono)
    n = mono.shape[0]
    if n == 0:
        return np.zeros(width), np.zeros(width)
    if n <= width:
        # Rellenar si la pista es más corta que el ancho
        idx = np.linspace(0, n - 1, width).astype(int)
        vals = mono[idx]
        return -vals, vals

    # Particionar en `width` segmentos y tomar el pico de cada uno
    seg = n // width
    trimmed = mono[: seg * width]
    chunks = trimmed.reshape(width, seg)
    peaks = np.max(chunks, axis=1)
    # Suavizado ligero
    if width > 8:
        kernel = np.ones(5, dtype=np.float32) / 5.0
        peaks = np.convolve(peaks, kernel, mode="same")
    return -peaks, peaks


def compute_spectrum_profile(samples: np.ndarray, fs: int,
                             bands: Optional[List[float]] = None,
                             max_windows: int = 400) -> np.ndarray:
    """
    Perfil espectral promedio por bandas (para visualización decorativa).

    Args:
        samples: Buffer float32 (N, ch).
        fs: Frecuencia de muestreo.
        bands: Frecuencias centrales de las bandas.
        max_windows: Número máximo de ventanas FFT a promediar.

    Returns:
        Array normalizado 0..1 con la energía de cada banda.
    """
    if samples.ndim == 2:
        mono = np.mean(samples, axis=1)
    else:
        mono = samples
    mono = mono.astype(np.float32)
    if mono.size == 0:
        return np.zeros(len(bands or BAND_FREQS))

    nfft = 4096
    hop = nfft // 2
    window = np.hanning(nfft).astype(np.float32)

    total_windows = max(1, (mono.shape[0] - nfft) // hop)
    step = max(1, total_windows // max_windows)

    band_centers = bands or BAND_FREQS
    freqs = np.fft.rfftfreq(nfft, d=1.0 / fs)
    acc = np.zeros(len(band_centers), dtype=np.float64)

    count = 0
    start = 0
    while start + nfft <= mono.shape[0] and count < max_windows:
        seg = mono[start:start + nfft] * window
        mag = np.abs(np.fft.rfft(seg)) ** 2
        for i, f0 in enumerate(band_centers):
            # Sumar energía en una octava alrededor de la banda
            lo = max(0, np.searchsorted(freqs, f0 / np.sqrt(2.0)))
            hi = np.searchsorted(freqs, f0 * np.sqrt(2.0))
            acc[i] += float(np.sum(mag[lo:hi]))
        count += 1
        start += hop * step

    if count == 0:
        return np.zeros(len(band_centers))

    acc /= count
    peak_energy = float(np.max(acc)) if acc.size else 0.0
    if peak_energy > 0:
        # Escala logarítmica suavizada para que se vea bien en la UI
        levels = np.log10(acc + 1e-9)
        levels -= float(np.max(levels))
        levels = 1.0 + levels / 12.0  # ~60 dB de rango dinámico
        levels = np.clip(levels, 0.0, 1.0)
    else:
        levels = np.zeros(len(band_centers))
    return levels.astype(np.float32)
