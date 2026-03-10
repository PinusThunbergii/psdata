# PSDATA Format (English)

This document describes the `.psdata/.pssettings` format as implemented by this library and inferred from reverse-engineering of PicoScope 6 binaries.

## 1. Container Header

At file start:
1. `uint32` signature: `0x4457574A`
2. `uint32` file type marker:
   - data: `0x049BA5E3`
   - settings: `0x9EB3687E`
3. `int32` header version (commonly `1`)
4. `int64` main payload length
5. `64 bytes` reserved area (`8 * int64`)

Derived fields:
- `main_payload_start = 84`
- `main_payload_end = main_payload_start + main_payload_length`

## 2. Core Metadata Block

Immediately after `main_payload_end`:
1. `uint32 CORE_MARKER = 0x45E3F55B`
2. `int64` metadata XML length
3. `kq` block payload (metadata XML bytes)

Metadata XML usually contains:
- `applicationversion`
- `fileguid`
- `uncompressedlength`
- `compressedlength`
- `binaryversion`

## 3. `kq` Block Layout

`kq` encoded block:
1. `int32 isCompressed` (`0` or `1`)
2. `int64 uncompressedLength`
3. `64 bytes` reserved
4. payload:
   - gzip bytes when `isCompressed=1`
   - raw bytes when `isCompressed=0`

## 4. `settings.xml` Decoding

### `binaryversion=0`
- settings content is already available from metadata path.

### `binaryversion=2`
- compressed settings blob is stored near the end of main payload.
- decoding pipeline:
1. read `compressedlength` bytes from
   `main_payload_start + main_payload_length - compressedlength`
2. apply Pico transform (`er_transform`) with seed:
   `(Int64LE(fileguid[0:8]) XOR absolute_offset XOR uncompressedlength) & 0xFFFFFFFF`
3. `gzip.decompress(...)`
4. clean trailing zero bytes / BOM artifacts

## 5. Binary Data Descriptors (`<binary>`)

Inside `settings.xml`, value chunks reference binary data by descriptor fields:
- `guid`
- `uncompressedlength`
- `binaryversion`
- `offset` (relative to `main_payload_start`)
- `compressiontype` (`none` or `gzip`)
- `compressedlength`

Absolute data offset:
- `absolute_start = main_payload_start + offset`

## 6. Samples Storage

Channel samples are represented in:
- `capturewindows/capturewindow/circularBuffer/buffers/buffer/enabledchannels/enabled`

Per enabled channel:
- `collectiontimearray/timechunk[]` (time axis info)
- `values/valuechunk[]` (binary chunks)

Decoded valuechunk payload:
- little-endian signed `int16[]`

If payload size is odd, the last byte is ignored.

## 7. Time Axis Reconstruction

For each chunk `k`:
- use `timechunk[k]` if available:
  - `start`
  - `interval`
  - `count`

Sample timestamp:
- `time_seconds = start + i * interval`

Global per-channel sample index is accumulated over chunks:
- `sample_index = chunk_sample_offset + i`

## 8. ADC and Scaling

Raw sample:
- `adc_raw` from decoded `int16`

Adjusted sample:
- `adc_adjusted = adc_raw - adccountszerooffset`

Approximate scaled value:
- linear mapping using `minadccounts/maxadccounts` and channel `scaledrange min/max`.
- this is approximate and may not match UI exactly for all probe/device modes.

## 9. Channel and Window Structures

Key nodes:
- `capturewindows/capturewindow`
- `.../devicesettings/channelconfig/channels/channel`
- `.../channelrepository/mathsChannelCollection/mathsChannel`
- `.../filtermanager/channels/channel`

Window contains:
- capture type, notes, device reference, buffer list, channel repository.

Channel config contains:
- enable state, coupling, units, probe info, ADC limits, zero offset, ranges, bandwidth limit.

## 10. Math Channels

Stored under:
- `.../channelrepository/mathsChannelCollection/mathsChannel/mathsformula`

Fields:
- `formula`, `formulaname`, `formulacolour`
- `rangemin`, `rangemax`
- `unittype`, `fullname`, `shortname`, `si`

Current evaluator supports:
- channel refs `#0`, `#1`, ...
- `+ - * / ^`, unary `+/-`, parentheses
- constants `pi`, `e`
- functions: `abs`, `sqrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `exp`, `log`, `log10`, `floor`, `ceil`, `round`, `min`, `max`

Not supported:
- direct `FFT(...)` execution inside formula evaluator.

## 11. Trailer Chunks

After main parts, optional known chunks can exist:
- `preview_small.png`
- `preview_large.png`
- `reference_waveforms.bin`
- `automotive_details.xml`

They are parsed from the file tail by marker/offset rules.

## 12. Current Limits

- Only known compression types (`none`, `gzip`) are implemented.
- Unknown future `binaryversion` values raise `PsDataError`.
- Some vendor-specific UI semantics are inferred, not guaranteed.
