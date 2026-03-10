# psdata API Reference (English)

This page documents the main public functions and classes exported by `psdata`.

## Imports

```python
from psdata import (
    PsData,
    PsDataDocument,
    PsDataError,
    open_psdata,
    samples_np,
    channels_np,
    math_np,
    fft_np,
    run,
    export_settings_csvs,
    export_channel_data,
)
```

## 1) High-Level API (`PsData`)

### `PsData.open(path: str | Path) -> PsData`
Open `.psdata` / `.pssettings` and build a convenient high-level facade.

### `windows_count() -> int`
Return number of capture windows in `settings.xml`.

### `windows_info(include_channels: bool = True) -> list[WindowInfo]`
Return structured window metadata:
- `window_type`, `buffer_count`, `channels_count`
- `enabled_channels_count`, `maths_channels_count`
- optional channel list

### `channels(window_index: int = 0, enabled_only: bool = False) -> list[ChannelInfo]`
Return channel descriptors for a window.

### `channel_settings(channel: int, window_index: int = 0) -> ChannelSettings`
Return detailed channel settings:
- probe/range/ADC info
- `bandwidth_limit`
- `sample_rate_hz` (inferred from time metadata)

### `samples(...) -> Iterator[ChannelSample]`
Stream channel samples with optional filters:
- `channel`
- `window_index`
- `buffer_index`
- `step`

### `samples_map(...) -> dict[int, Iterator[ChannelSample]]`
Map channel index to sample iterator (for selected window).

### Math channels

#### `has_math_channels(window_index: int = 0) -> bool`
Quick check for math channels.

#### `math_channels(window_index: int = 0) -> list[MathChannelInfo]`
Return all math channel definitions from channel repository.

#### `math_channel(index: int, window_index: int = 0) -> MathChannelInfo`
Return one math channel definition by list index.

#### `eval_math_channel(...) -> Iterator[MathChannelSample]`
Evaluate supported scalar formula expressions on aligned sample indices.

Supported expression subset:
- `#N` channel references
- `+ - * / ^`, unary `+/-`, parentheses
- constants `pi`, `e`
- functions: `abs`, `sqrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `exp`, `log`, `log10`, `floor`, `ceil`, `round`, `min`, `max`

Not supported in evaluator:
- `FFT(...)` inside formula text

#### `eval_math_channel_rows(...) -> Iterator[dict[str, Any]]`
Same as above, but dictionary rows.

### NumPy methods on `PsData`

#### `samples_np(...) -> ChannelArray`
Precomputed arrays for one channel.

#### `channels_np(...) -> dict[int, ChannelArray]`
Precomputed arrays for multiple channels.

#### `math_np(...) -> MathChannelArray`
Precomputed arrays for one computed math channel.

#### `fft_np(...) -> SpectrumArray`
FFT spectrum (frequency + magnitude) from either:
- `channel=<int>`
- `math_index=<int>`

Exactly one source must be provided.

## 2) Dot-Path XML Access (`XmlAccessor`)

`PsData.settings` and `PsData.metadata` expose:

### `node(path: str) -> Optional[Element]`
Return XML node by dot path.

### `get(path: str, default: Optional[str] = None, attr: str = "value") -> Optional[str]`
Return attribute (or text) by dot path.

Examples:
- `capturewindows.capturewindow.0.capturewindowtype`
- `capturewindows.0.capturewindowtype`

## 3) Low-Level API (`PsDataDocument`)

Created with:
- `open_psdata(path)`
- or `PsData.open(path).document`

### XML and metadata
- `metadata_xml_text`, `settings_xml_text`
- `metadata_dict()`, `settings_dict()`
- `find_metadata(path)`, `find_settings(path)`
- `get_metadata_value(path, attr="value", default=None)`
- `get_settings_value(path, attr="value", default=None)`

### Binary descriptors and chunks
- `iter_binary_nodes()`
- `iter_binary_descriptors()`
- `decode_binary_node(binary_node)`
- `decode_binary_descriptor(descriptor)`
- `known_chunks()`

### Samples and summary
- `iter_channel_samples(step=1)`
- `iter_channel_rows(step=1)`
- `summary()`

## 4) Module-Level NumPy Functions

These are exported from `psdata` and equivalent to `PsData` methods:
- `samples_np(ps, ...)`
- `channels_np(ps, ...)`
- `math_np(ps, ...)`
- `fft_np(ps, ...)`

Useful when you prefer functional style.

## 5) Export API and CLI

### `run(input_file, out_dir, extract_channel_series=True, channel_step=1) -> dict`
Main export pipeline:
- writes `metadata.xml`, `settings.xml`
- writes CSV summaries
- optionally writes per-sample channel CSV files
- extracts known trailer chunks
- writes `summary.json`

### `export_settings_csvs(settings_xml, out_dir) -> dict`
Write:
- `capture_windows.csv`
- `channels.csv`
- `channel_repository.csv`

### `export_channel_data(settings_xml, data, header, out_dir, step=1) -> dict`
Write per-channel sample CSV files.

### CLI entry point

```bash
psdata-export input.psdata --out input.psdata.decoded
```

## 6) Errors

### `PsDataError`
Raised for unsupported/invalid format cases, including:
- unexpected header/signature values
- unsupported `binaryversion` or compression mode
- out-of-range channel/window/math indices
- unsupported math expression constructs
- missing required source samples for formula evaluation

## 7) Minimal Examples

```python
from psdata import PsData

ps = PsData.open("1.psdata")
print(ps.windows_count())
print(ps.channels(window_index=0))
print(ps.channel_settings(channel=0).sample_rate_hz)
```

```python
from psdata import PsData

ps = PsData.open("1.psdata")
spec = ps.fft_np(channel=0, window_index=0, buffer_index=0, step=500)
print(spec.frequency_hz.shape, spec.magnitude.shape)
```
