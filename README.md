# psdata

Typed Python library for reading PicoScope 6 `.psdata` and `.pssettings` files.

Language versions:
- English: this file
- Ukrainian: `README.uk.md`

Format specification:
- English: `docs/FORMAT.en.md`
- Ukrainian: `docs/FORMAT.uk.md`

API reference:
- English: `docs/API.en.md`
- Ukrainian: `docs/API.uk.md`

## Features

- Parses PS6 container header and metadata blocks.
- Decodes `settings.xml` for `binaryversion=0` and `binaryversion=2`.
- Provides typed models for windows, channels, settings, samples, and math channels.
- Supports stream iteration over samples (`iter_channel_samples`, `samples`).
- Supports precomputed NumPy APIs (`samples_np`, `channels_np`, `math_np`, `fft_np`).
- Exports decoded artifacts and CSV summaries (`psdata-export` CLI).
- Keeps full XML access (`ElementTree` roots + dictionary conversion).

## Installation

### With `uv` (recommended)

```bash
uv sync
uv sync --extra numpy
```

### With `pip`

```bash
pip install .
pip install .[numpy]
```

## Quick Start

```python
from psdata import PsData

ps = PsData.open("1.psdata")
print(ps.windows_count())

for ch in ps.channels(window_index=0):
    print(ch.channel_index, ch.name, ch.enabled, ch.unit_type)

cfg = ps.channel_settings(channel=0, window_index=0)
print(cfg.sample_rate_hz, cfg.coupling)

for s in ps.samples(channel=0, window_index=0, step=10):
    print(s.sample_index, s.time_seconds, s.adc_raw)
    break
```

## NumPy API

Requires `numpy` (`pip install .[numpy]`).

```python
from psdata import PsData

ps = PsData.open("1.psdata")

ch = ps.samples_np(channel=0, window_index=0, buffer_index=0, value_mode="scaled")
print(ch.values.shape, ch.values.dtype)

all_channels = ps.channels_np(window_index=0, buffer_index=0, value_mode="scaled")
print(list(all_channels.keys()))

m = ps.math_np(index=0, window_index=0, buffer_index=0)
print(m.formula, m.values.shape)

spec = ps.fft_np(channel=0, window_index=0, buffer_index=0, window_fn="hann", detrend="mean")
print(spec.sample_rate_hz, spec.frequency_hz.shape, spec.magnitude.shape)
```

## Examples

Standalone examples are in `examples/`:
- `basic_usage.py`
- `numpy_usage.py`
- `export_usage.py`

Run from repository root:

```bash
uv run python examples/basic_usage.py 1.psdata
uv run python examples/numpy_usage.py 1.psdata --step 500
uv run python examples/export_usage.py 1.psdata --out 1.psdata.decoded.example
```

## CLI

After installation:

```bash
psdata-export 1.psdata --out 1.psdata.decoded
```

## Build and Packaging

Build sdist + wheel:

```bash
uv build
```

Build outputs:
- `dist/*.tar.gz`
- `dist/*.whl`

Optional checks:

```bash
uv run python -m pip install twine
uv run python -m twine check dist/*
```

## Implemented

- Core `.psdata/.pssettings` container parsing.
- `kq` metadata block decoding.
- Binary payload decoding (`none`, `gzip`, `binaryversion=2` transform).
- Channel sample extraction with time axis reconstruction.
- Approximate scaled value computation from channel configuration.
- Math channels metadata and scalar formula evaluation for supported expressions.
- NumPy precomputed API including FFT on channel or computed math data.

## Not Implemented Yet

- Native execution of `FFT(...)` directly inside `mathsformula`.
- Full parity with every PicoScope internal formula/function type.
- Advanced spectral modes (averaging modes, PSD units, vendor-specific FFT normalization).
- Guaranteed support for unknown future `binaryversion` and compression variants.

## Pitfalls and Caveats

- `approx_scaled_value` is a linear conversion based on XML ranges and may not exactly match PicoScope UI values in all probe/device modes.
- `channel_settings().sample_rate_hz` is inferred from timing metadata (per-channel timechunk first, then samplingconfig fallback).
- Sample timelines can differ across channels; cross-channel operations are aligned by common `sample_index`.
- `fft_np()` infers sample rate from the median positive `dt`; irregular timing may change spectral interpretation.
- Large captures can consume significant memory in `*_np` methods.

## Public API

Primary exports from `psdata`:
- `PsData`, `PsDataDocument`, `PsDataError`
- `Header`, `MetadataInfo`, `ParsedContainer`, `KnownChunk`, `BinaryDescriptor`
- `ChannelInfo`, `ChannelSettings`, `ChannelSample`, `WindowInfo`
- `MathChannelInfo`, `MathChannelSample`
- `ValueMode`, `ChannelArray`, `MathChannelArray`, `SpectrumArray`
- `samples_np`, `channels_np`, `math_np`, `fft_np`
- `open_psdata`, `read_known_chunks`, `element_to_dict`
- `export_settings_csvs`, `export_channel_data`, `run`

## License

WTFPL (see `LICENSE`).
