"""Numpy-oriented precomputed APIs for channels, maths and FFT."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Optional

from .model import ChannelArray, MathChannelArray, PsDataError, SpectrumArray, ValueMode

if TYPE_CHECKING:
    from .api import PsData


WindowFunction = Literal["none", "hann", "hamming", "blackman"]
DetrendMode = Literal["none", "mean"]


def _require_numpy() -> Any:
    try:
        import numpy as np
    except ModuleNotFoundError as ex:
        raise PsDataError(
            "numpy is required for *_np methods. Install it with: pip install numpy"
        ) from ex
    return np


def _resolve_value(sample: Any, value_mode: ValueMode) -> float | int:
    if value_mode == "raw":
        return int(sample.adc_raw)
    if value_mode == "adjusted":
        return float(sample.adc_adjusted)
    if sample.approx_scaled_value is not None:
        return float(sample.approx_scaled_value)
    return float(sample.adc_adjusted)


def _resolve_dtype(np: Any, *, dtype: Any, default: Any) -> Any:
    if dtype is None:
        return np.dtype(default)
    return np.dtype(dtype)


def _resolve_float_dtype(np: Any, *, dtype: Any, default: Any = "float64") -> Any:
    resolved = _resolve_dtype(np, dtype=dtype, default=default)
    if resolved.kind not in {"f"}:
        raise PsDataError(f"dtype must be floating-point for this method, got {resolved}")
    return resolved


def samples_np(
    ps: "PsData",
    channel: int,
    *,
    window_index: int = 0,
    buffer_index: int = 0,
    value_mode: ValueMode = "scaled",
    step: int = 1,
    dtype: Any = None,
) -> ChannelArray:
    np = _require_numpy()
    samples = list(
        ps.samples(
            channel=channel,
            window_index=window_index,
            buffer_index=buffer_index,
            step=step,
        )
    )
    if not samples:
        raise PsDataError(
            f"No samples for channel={channel}, window_index={window_index}, buffer_index={buffer_index}"
        )

    sample_index = np.fromiter((s.sample_index for s in samples), dtype=np.int64, count=len(samples))
    time_seconds = np.fromiter((s.time_seconds for s in samples), dtype=np.float64, count=len(samples))

    default_dtype = np.int16 if value_mode == "raw" else np.float64
    values_dtype = _resolve_dtype(np, dtype=dtype, default=default_dtype)
    values = np.asarray([_resolve_value(s, value_mode) for s in samples], dtype=values_dtype)

    return ChannelArray(
        window_index=window_index,
        buffer_index=buffer_index,
        channel_index=channel,
        value_mode=value_mode,
        unit_type=samples[0].unit_type,
        sample_index=sample_index,
        time_seconds=time_seconds,
        values=values,
    )


def channels_np(
    ps: "PsData",
    *,
    window_index: int = 0,
    buffer_index: int = 0,
    value_mode: ValueMode = "scaled",
    step: int = 1,
    enabled_only: bool = True,
    dtype: Any = None,
) -> dict[int, ChannelArray]:
    result: dict[int, ChannelArray] = {}
    for channel in ps.channels(window_index=window_index, enabled_only=enabled_only):
        try:
            series = samples_np(
                ps,
                channel=channel.channel_index,
                window_index=window_index,
                buffer_index=buffer_index,
                value_mode=value_mode,
                step=step,
                dtype=dtype,
            )
            result[channel.channel_index] = series
        except PsDataError as ex:
            if "No samples for channel=" in str(ex):
                continue
            raise
    return result


def math_np(
    ps: "PsData",
    index: int,
    *,
    window_index: int = 0,
    buffer_index: int = 0,
    step: int = 1,
    dtype: Any = None,
) -> MathChannelArray:
    np = _require_numpy()
    samples = list(
        ps.eval_math_channel(
            index=index,
            window_index=window_index,
            buffer_index=buffer_index,
            step=step,
        )
    )
    if not samples:
        raise PsDataError(
            f"No math samples for index={index}, window_index={window_index}, buffer_index={buffer_index}"
        )

    sample_index = np.fromiter((s.sample_index for s in samples), dtype=np.int64, count=len(samples))
    time_seconds = np.fromiter((s.time_seconds for s in samples), dtype=np.float64, count=len(samples))
    values_dtype = _resolve_float_dtype(np, dtype=dtype)
    values = np.asarray([s.value for s in samples], dtype=values_dtype)

    head = samples[0]
    return MathChannelArray(
        window_index=window_index,
        buffer_index=buffer_index,
        list_index=head.list_index,
        channel_index=head.channel_index,
        value_mode="scaled",
        unit_type=head.unit_type,
        formula_name=head.formula_name,
        formula=head.formula,
        sample_index=sample_index,
        time_seconds=time_seconds,
        values=values,
    )


def _window_vector(np: Any, size: int, window_fn: WindowFunction) -> Any:
    if window_fn == "none":
        return np.ones(size, dtype=np.float64)
    if window_fn == "hann":
        return np.hanning(size)
    if window_fn == "hamming":
        return np.hamming(size)
    if window_fn == "blackman":
        return np.blackman(size)
    raise PsDataError(f"Unsupported window function: {window_fn}")


def fft_np(
    ps: "PsData",
    *,
    channel: Optional[int] = None,
    math_index: Optional[int] = None,
    window_index: int = 0,
    buffer_index: int = 0,
    value_mode: ValueMode = "scaled",
    step: int = 1,
    window_fn: WindowFunction = "hann",
    detrend: DetrendMode = "mean",
    nfft: Optional[int] = None,
    dtype: Any = None,
) -> SpectrumArray:
    np = _require_numpy()

    if (channel is None) == (math_index is None):
        raise PsDataError("Provide exactly one source: channel=<int> or math_index=<int>")

    if channel is not None:
        series = samples_np(
            ps,
            channel=channel,
            window_index=window_index,
            buffer_index=buffer_index,
            value_mode=value_mode,
            step=step,
            dtype=np.float64,
        )
        source_kind: Literal["channel", "math"] = "channel"
        source_index = channel
        time_axis = series.time_seconds
        values = series.values.astype(np.float64, copy=False)
    else:
        math_series = math_np(
            ps,
            index=int(math_index),
            window_index=window_index,
            buffer_index=buffer_index,
            step=step,
            dtype=np.float64,
        )
        source_kind = "math"
        source_index = int(math_index)
        time_axis = math_series.time_seconds
        values = math_series.values.astype(np.float64, copy=False)

    if values.size < 2:
        raise PsDataError("At least 2 points are required for FFT")

    diffs = np.diff(time_axis.astype(np.float64, copy=False))
    positive_diffs = diffs[diffs > 0]
    if positive_diffs.size == 0:
        raise PsDataError("Cannot infer sample rate: non-increasing time axis")

    dt = float(np.median(positive_diffs))
    sample_rate_hz = 1.0 / dt

    if detrend == "mean":
        values = values - float(np.mean(values))
    elif detrend != "none":
        raise PsDataError(f"Unsupported detrend mode: {detrend}")

    window_vec = _window_vector(np, values.size, window_fn)
    windowed = values * window_vec

    n = int(nfft) if nfft is not None else int(values.size)
    if n < 2:
        raise PsDataError("nfft must be >= 2")

    fft_out = np.fft.rfft(windowed, n=n)
    freq = np.fft.rfftfreq(n, d=dt)
    magnitude = np.abs(fft_out)

    # Basic amplitude normalization by window coherent gain.
    coherent_gain = float(np.sum(window_vec)) / float(values.size)
    if coherent_gain > 0:
        magnitude = magnitude / (float(values.size) * coherent_gain)

    out_dtype = _resolve_float_dtype(np, dtype=dtype, default="float64")
    return SpectrumArray(
        source_kind=source_kind,
        source_index=source_index,
        window_index=window_index,
        buffer_index=buffer_index,
        sample_rate_hz=sample_rate_hz,
        value_mode=value_mode,
        frequency_hz=freq.astype(out_dtype, copy=False),
        magnitude=magnitude.astype(out_dtype, copy=False),
    )
