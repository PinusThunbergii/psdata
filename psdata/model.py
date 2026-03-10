"""Typed domain models for psdata package."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional

if TYPE_CHECKING:
    import numpy as np

    NDArray = np.ndarray[Any, Any]
else:
    NDArray = Any


@dataclass(frozen=True)
class Header:
    signature: int
    file_type_marker: int
    header_version: int
    main_payload_length: int
    main_payload_start: int
    main_payload_end: int


@dataclass(frozen=True)
class MetadataInfo:
    app_version: Optional[str]
    file_guid: Optional[str]
    uncompressed_length: Optional[int]
    compressed_length: Optional[int]
    binary_version: Optional[int]


@dataclass(frozen=True)
class ParsedContainer:
    source: Path
    raw_bytes: bytes
    header: Header
    metadata: MetadataInfo
    metadata_xml_bytes: bytes
    settings_xml_bytes: bytes


@dataclass(frozen=True)
class KnownChunk:
    magic: int
    magic_hex: str
    with_length: bool
    default_name: str
    payload: bytes
    size: int


@dataclass(frozen=True)
class BinaryDescriptor:
    guid: Optional[str]
    uncompressed_length: int
    binary_version: int
    relative_offset: int
    compression_type: str
    compressed_length: int

    @classmethod
    def from_xml_values(
        cls,
        *,
        guid: Optional[str],
        uncompressed_length: int,
        binary_version: int,
        relative_offset: int,
        compression_type: str,
        compressed_length: int,
    ) -> "BinaryDescriptor":
        return cls(
            guid=guid,
            uncompressed_length=uncompressed_length,
            binary_version=binary_version,
            relative_offset=relative_offset,
            compression_type=compression_type.lower(),
            compressed_length=compressed_length,
        )


@dataclass(frozen=True)
class ChannelSample:
    window_index: int
    window_type: Optional[str]
    buffer_index: int
    channel_index: int
    sample_index: int
    time_seconds: float
    adc_raw: int
    adc_adjusted: int
    approx_scaled_value: Optional[float]
    unit_type: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_index": self.window_index,
            "window_type": self.window_type,
            "buffer_index": self.buffer_index,
            "channel_index": self.channel_index,
            "sample_index": self.sample_index,
            "time_seconds": self.time_seconds,
            "adc_raw": self.adc_raw,
            "adc_adjusted": self.adc_adjusted,
            "approx_scaled_value": self.approx_scaled_value,
            "unit_type": self.unit_type,
        }


@dataclass(frozen=True)
class ChannelInfo:
    window_index: int
    channel_index: int
    name: str
    enabled: Optional[bool]
    unit_type: Optional[str]
    coupling: Optional[str]
    probe_name: Optional[str]


@dataclass(frozen=True)
class WindowInfo:
    window_index: int
    window_type: Optional[str]
    device_reference_guid: Optional[str]
    notes: Optional[str]
    buffer_count: int
    channels_count: int
    enabled_channels_count: int
    maths_channels_count: int
    download_manager: Optional[str]
    channels: list[ChannelInfo] = field(default_factory=list)


@dataclass(frozen=True)
class ChannelSettings:
    window_index: int
    channel_index: int
    name: str
    enabled: Optional[bool]
    coupling: Optional[str]
    is_autoranging: Optional[bool]
    unit_type: Optional[str]
    probe_name: Optional[str]
    min_adc: Optional[int]
    max_adc: Optional[int]
    adc_zero_offset: Optional[int]
    scaled_min: Optional[float]
    scaled_max: Optional[float]
    input_min: Optional[float]
    input_max: Optional[float]
    bandwidth_limit: Optional[str]
    sample_rate_hz: Optional[float] = None


@dataclass(frozen=True)
class MathChannelInfo:
    window_index: int
    list_index: int
    channel_index: Optional[int]
    formula: Optional[str]
    formula_name: Optional[str]
    formula_colour: Optional[str]
    range_min: Optional[float]
    range_max: Optional[float]
    unit_type: Optional[str]
    full_name: Optional[str]
    short_name: Optional[str]
    si: Optional[str]


@dataclass(frozen=True)
class MathChannelSample:
    window_index: int
    buffer_index: int
    list_index: int
    channel_index: Optional[int]
    sample_index: int
    time_seconds: float
    value: float
    unit_type: Optional[str]
    formula_name: Optional[str]
    formula: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_index": self.window_index,
            "buffer_index": self.buffer_index,
            "list_index": self.list_index,
            "channel_index": self.channel_index,
            "sample_index": self.sample_index,
            "time_seconds": self.time_seconds,
            "value": self.value,
            "unit_type": self.unit_type,
            "formula_name": self.formula_name,
            "formula": self.formula,
        }


ValueMode = Literal["raw", "adjusted", "scaled"]


@dataclass(frozen=True)
class ChannelArray:
    window_index: int
    buffer_index: int
    channel_index: int
    value_mode: ValueMode
    unit_type: Optional[str]
    sample_index: NDArray
    time_seconds: NDArray
    values: NDArray


@dataclass(frozen=True)
class MathChannelArray:
    window_index: int
    buffer_index: int
    list_index: int
    channel_index: Optional[int]
    value_mode: ValueMode
    unit_type: Optional[str]
    formula_name: Optional[str]
    formula: Optional[str]
    sample_index: NDArray
    time_seconds: NDArray
    values: NDArray


@dataclass(frozen=True)
class SpectrumArray:
    source_kind: Literal["channel", "math"]
    source_index: int
    window_index: int
    buffer_index: int
    sample_rate_hz: float
    value_mode: ValueMode
    frequency_hz: NDArray
    magnitude: NDArray


class PsDataError(RuntimeError):
    """Raised when .psdata/.pssettings bytes are invalid or unsupported."""
