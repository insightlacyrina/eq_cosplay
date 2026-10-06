"""A single, side-effect-free response model shared by the stage and data inspector.

The renderer may decimate this model, but readouts and CSV exports always use the
original frequency grid. Simulated response is derived from the selected filter
chain, never from the GUI's historical ``simulated_curve`` cache.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class ResponseData:
    freqs: np.ndarray
    source: np.ndarray
    target: np.ndarray
    simulated: np.ndarray
    residual: np.ndarray
    before_residual: np.ndarray
    filter_response: np.ndarray
    source_available: bool
    target_available: bool
    use_fir: bool
    mode: str
    bands: tuple[dict, ...]
    iir_rmse: float | None
    combined_rmse: float | None
    fir_taps: int | None
    level_offset_db: float | None


def _vector(value) -> np.ndarray:
    if value is None:
        return np.empty(0, dtype=float)
    try:
        return np.asarray(value, dtype=float).reshape(-1).copy()
    except (TypeError, ValueError):
        return np.empty(0, dtype=float)


def _number(value) -> float | None:
    try:
        number = float(value)
        return number if np.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def build_response(correction: dict | None, mode: str = "eq", raw_target: bool = False) -> ResponseData:
    """Normalize list/NumPy inputs without truth-value coercion or mutation.

    ``target_fr`` is the core's level-aligned measurement. Adding its recorded
    alignment offset recovers the original measurement for the raw-target view.
    Residual convention: target minus simulation, in dB.
    """
    corr = correction if isinstance(correction, dict) else {}
    grid = _vector(corr.get("grid_freqs"))
    valid = np.isfinite(grid) & (grid >= 20.0) & (grid <= 20000.0)
    indices = np.flatnonzero(valid)
    if len(indices):
        indices = indices[np.argsort(grid[indices], kind="stable")]
        indices = indices[np.r_[True, np.diff(grid[indices]) > 0]]
    freqs = grid[indices]

    def curve(*keys) -> np.ndarray:
        for key in keys:
            values = _vector(corr.get(key))
            if len(values) == len(grid) and len(grid):
                return values[indices]
        return np.empty(0, dtype=float)

    source = curve("source_fr", "source_curve")
    target = curve("target_fr", "target_curve")
    source_available = len(source) > 0 and bool(np.any(np.isfinite(source)))
    target_available = len(target) > 0 and bool(np.any(np.isfinite(target)))
    use_fir = bool(corr.get("use_fir", False))
    response = curve("combined_resp", "peq_resp") if use_fir else curve("peq_resp", "combined_resp")
    if not len(response):
        response = np.zeros_like(freqs)
    if not source_available:
        source = np.zeros_like(freqs)
    if not target_available:
        target = np.empty(0, dtype=float)
    offset = _number(corr.get("level_offset_db"))
    original_target = curve("target_raw_fr")
    if raw_target and target_available:
        if len(original_target):
            target = original_target
        elif offset is not None:
            target = target + offset
    if mode == "comp":
        if target_available:
            target = target - source
        source = np.zeros_like(freqs)
        simulated = response.copy()
    else:
        mode = "eq"
        simulated = source + response
    residual = target - simulated if target_available else np.empty(0, dtype=float)
    before = target - source if target_available else np.empty(0, dtype=float)
    taps = _number(corr.get("fir_n_taps"))
    arrays = (freqs, source, target, simulated, residual, before, response)
    for array in arrays:
        array.setflags(write=False)
    return ResponseData(
        *arrays, source_available, target_available, use_fir, mode,
        tuple(dict(band) for band in (corr.get("peq") or ()) if isinstance(band, dict)),
        _number(corr.get("peq_rmse")), _number(corr.get("combined_rmse")),
        int(taps) if taps is not None and taps > 0 else None, offset,
    )


def response_at(data: ResponseData, freq: float) -> dict[str, float | None]:
    """Interpolate on log-frequency using the un-decimated grid."""
    out: dict[str, float | None] = {}
    for name in ("source", "target", "simulated", "residual"):
        values = getattr(data, name)
        valid = np.isfinite(values) if len(values) == len(data.freqs) else np.zeros(0, dtype=bool)
        if not len(data.freqs) or not np.any(valid) or not np.isfinite(freq) or freq <= 0:
            out[name] = None
        else:
            out[name] = float(np.interp(np.log10(freq), np.log10(data.freqs[valid]), values[valid]))
    return out


def display_indices(freqs: np.ndarray, width: int, max_points: int = 512) -> np.ndarray:
    """Bound vector geometry to visible pixels; leave the underlying model intact."""
    count = len(freqs)
    budget = min(count, max(24, min(int(max_points), int(width))))
    if count <= budget:
        return np.arange(count, dtype=int)
    return np.unique(np.rint(np.linspace(0, count - 1, budget)).astype(int))


def export_response_csv(path: str | Path, correction: dict, mode: str = "eq", raw_target: bool = False) -> None:
    """Export full-resolution aligned and original measurement columns together."""
    data = build_response(correction, mode, raw_target)
    measured = build_response(correction, "eq", False)
    raw = build_response(correction, "eq", True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("frequency_hz", "source_measured_db", "target_aligned_db", "target_original_db",
                         "filter_response_db", "simulated_db", "display_target_db", "residual_db", "display_mode", "fir_enabled"))
        for i, frequency in enumerate(data.freqs):
            def cell(values):
                return format(float(values[i]), ".12g") if len(values) and np.isfinite(values[i]) else ""
            writer.writerow((format(float(frequency), ".12g"),
                             cell(measured.source) if measured.source_available else "",
                             cell(measured.target), cell(raw.target) if correction.get("target_raw_fr") is not None or measured.level_offset_db is not None else "", cell(data.filter_response),
                             cell(data.simulated), cell(data.target), cell(data.residual), mode, int(data.use_fir)))
