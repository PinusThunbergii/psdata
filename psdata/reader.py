"""High-level typed reader API for PicoScope 6 .psdata/.pssettings files."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

from .model import BinaryDescriptor, ChannelSample, Header, KnownChunk, MetadataInfo, ParsedContainer, PsDataError
from .parser import (
    CHUNK_AUTOMOTIVE_DETAILS,
    CHUNK_PREVIEW_LARGE,
    CHUNK_PREVIEW_SMALL,
    CHUNK_REFERENCE_WAVEFORMS,
    CORE_MARKER,
    FILETYPE_DATA,
    FILETYPE_SETTINGS,
    SIGNATURE,
    decode_binary_blob,
    descriptor_from_binary_node,
    marker_name,
    parse_container,
    read_known_chunks,
    to_float,
    to_int,
    xml_value,
)


def element_to_dict(node: ET.Element) -> dict[str, Any]:
    """Convert an XML element into a full-fidelity nested dictionary."""
    text = (node.text or "").strip()
    return {
        "tag": node.tag,
        "attributes": dict(node.attrib),
        "text": text if text else None,
        "children": [element_to_dict(child) for child in list(node)],
    }


@dataclass
class PsDataDocument:
    """Decoded .psdata/.pssettings container with typed accessors."""

    source: Path
    raw_bytes: bytes
    header: Header
    metadata_info: MetadataInfo
    metadata_xml_bytes: bytes
    settings_xml_bytes: bytes
    metadata_root: ET.Element
    settings_root: ET.Element

    @property
    def metadata_xml_text(self) -> str:
        return self.metadata_xml_bytes.decode("utf-8", errors="ignore")

    @property
    def settings_xml_text(self) -> str:
        return self.settings_xml_bytes.decode("utf-8", errors="ignore")

    def metadata_dict(self) -> dict[str, Any]:
        return element_to_dict(self.metadata_root)

    def settings_dict(self) -> dict[str, Any]:
        return element_to_dict(self.settings_root)

    def find_metadata(self, path: str) -> list[ET.Element]:
        return self.metadata_root.findall(path)

    def find_settings(self, path: str) -> list[ET.Element]:
        return self.settings_root.findall(path)

    def get_metadata_value(self, path: str, attr: str = "value", default: Optional[str] = None) -> Optional[str]:
        elem = self.metadata_root.find(path)
        if elem is None:
            return default
        if attr == "text":
            text = (elem.text or "").strip()
            return text or default
        return elem.attrib.get(attr, default)

    def get_settings_value(self, path: str, attr: str = "value", default: Optional[str] = None) -> Optional[str]:
        elem = self.settings_root.find(path)
        if elem is None:
            return default
        if attr == "text":
            text = (elem.text or "").strip()
            return text or default
        return elem.attrib.get(attr, default)

    def iter_binary_nodes(self) -> Iterator[ET.Element]:
        for node in self.settings_root.findall(".//binary"):
            yield node

    def iter_binary_descriptors(self) -> Iterator[BinaryDescriptor]:
        for binary_node in self.iter_binary_nodes():
            yield descriptor_from_binary_node(binary_node)

    def decode_binary_descriptor(self, descriptor: BinaryDescriptor) -> bytes:
        return decode_binary_blob(data=self.raw_bytes, header=self.header, descriptor=descriptor)

    def decode_binary_node(self, binary_node: ET.Element) -> bytes:
        descriptor = descriptor_from_binary_node(binary_node)
        return self.decode_binary_descriptor(descriptor)

    def known_chunks(self) -> list[KnownChunk]:
        return read_known_chunks(self.raw_bytes)

    def iter_channel_samples(self, step: int = 1) -> Iterator[ChannelSample]:
        if step < 1:
            step = 1

        capture_windows = self.settings_root.findall("./capturewindows/capturewindow")
        for window_index, cw in enumerate(capture_windows):
            window_type = xml_value(cw, "capturewindowtype")

            config_by_index: dict[int, dict[str, Optional[float] | Optional[int] | Optional[str]]] = {}
            cfg_channels = cw.findall("./circularBuffer/devicemodeladapters/devicesettings/channelconfig/channels/channel")
            for idx, ch in enumerate(cfg_channels):
                config_by_index[idx] = {
                    "unit_type": xml_value(ch, "unit/unittype"),
                    "min_adc": to_int(xml_value(ch, "minadccounts")),
                    "max_adc": to_int(xml_value(ch, "maxadccounts")),
                    "adc_zero_offset": to_int(xml_value(ch, "adccountszerooffset")) or 0,
                    "scaled_min": to_float(xml_value(ch, "probesettings/range/scaledrange/min/value")),
                    "scaled_max": to_float(xml_value(ch, "probesettings/range/scaledrange/max/value")),
                }

            buffers = cw.findall("./circularBuffer/buffers/buffer")
            for buffer_index, buffer_node in enumerate(buffers):
                enabled_nodes = buffer_node.findall("./enabledchannels/enabled")
                for enabled in enabled_nodes:
                    channel_index = to_int(xml_value(enabled, "channel"))
                    if channel_index is None:
                        continue

                    time_chunks = enabled.findall("./collectiontimearray/timechunk")
                    value_chunks = enabled.findall("./values/valuechunk")
                    if not value_chunks:
                        continue

                    cfg = config_by_index.get(channel_index, {})
                    sample_offset = 0

                    for chunk_idx, value_chunk in enumerate(value_chunks):
                        binary = value_chunk.find("binary")
                        if binary is None:
                            continue

                        raw = self.decode_binary_node(binary)
                        if len(raw) < 2:
                            continue
                        if len(raw) % 2:
                            raw = raw[:-1]
                        values = memoryview(raw).cast("h")

                        start = 0.0
                        interval = 1.0
                        expected_count = len(values)
                        if chunk_idx < len(time_chunks):
                            tc = time_chunks[chunk_idx]
                            start = to_float(xml_value(tc, "start")) or start
                            interval = to_float(xml_value(tc, "interval")) or interval
                            expected_count = to_int(xml_value(tc, "count")) or expected_count

                        count = min(len(values), expected_count)
                        min_adc = cfg.get("min_adc")
                        max_adc = cfg.get("max_adc")
                        adc_zero = int(cfg.get("adc_zero_offset") or 0)
                        scaled_min = cfg.get("scaled_min")
                        scaled_max = cfg.get("scaled_max")
                        unit_type = cfg.get("unit_type")

                        for idx in range(0, count, step):
                            raw_adc = int(values[idx])
                            adjusted_adc = raw_adc - adc_zero
                            approx_scaled: Optional[float] = None
                            if (
                                min_adc is not None
                                and max_adc is not None
                                and scaled_min is not None
                                and scaled_max is not None
                                and max_adc != min_adc
                            ):
                                approx_scaled = float(scaled_min) + (
                                    (adjusted_adc - int(min_adc))
                                    * (float(scaled_max) - float(scaled_min))
                                    / (int(max_adc) - int(min_adc))
                                )

                            yield ChannelSample(
                                window_index=window_index,
                                window_type=window_type,
                                buffer_index=buffer_index,
                                channel_index=channel_index,
                                sample_index=sample_offset + idx,
                                time_seconds=start + idx * interval,
                                adc_raw=raw_adc,
                                adc_adjusted=adjusted_adc,
                                approx_scaled_value=approx_scaled,
                                unit_type=unit_type if isinstance(unit_type, str) else None,
                            )

                        sample_offset += count

    def iter_channel_rows(self, step: int = 1) -> Iterator[dict[str, Any]]:
        """Backward-compatible iterator returning dict rows."""
        for sample in self.iter_channel_samples(step=step):
            yield sample.to_dict()

    def summary(self) -> dict[str, Any]:
        chunks = self.known_chunks()
        return {
            "input": str(self.source),
            "size": len(self.raw_bytes),
            "header": {
                "signature": f"0x{self.header.signature:08X}",
                "file_type_marker": f"0x{self.header.file_type_marker:08X}",
                "file_type": marker_name(self.header.file_type_marker),
                "header_version": self.header.header_version,
                "main_payload_length": self.header.main_payload_length,
                "main_payload_start": self.header.main_payload_start,
                "main_payload_end": self.header.main_payload_end,
            },
            "metadata": {
                "applicationversion": self.metadata_info.app_version,
                "fileguid": self.metadata_info.file_guid,
                "uncompressedlength": self.metadata_info.uncompressed_length,
                "compressedlength": self.metadata_info.compressed_length,
                "binaryversion": self.metadata_info.binary_version,
            },
            "known_chunks": [
                {
                    "magic": item.magic_hex,
                    "name": item.default_name,
                    "size": item.size,
                }
                for item in chunks
            ],
        }


def _build_document(container: ParsedContainer) -> PsDataDocument:
    try:
        metadata_root = ET.fromstring(container.metadata_xml_bytes.decode("utf-8", errors="ignore"))
    except ET.ParseError as ex:
        raise PsDataError(f"Failed to parse metadata XML tree: {ex}") from ex

    try:
        settings_root = ET.fromstring(container.settings_xml_bytes.decode("utf-8", errors="ignore"))
    except ET.ParseError as ex:
        raise PsDataError(f"Failed to parse settings XML tree: {ex}") from ex

    return PsDataDocument(
        source=container.source,
        raw_bytes=container.raw_bytes,
        header=container.header,
        metadata_info=container.metadata,
        metadata_xml_bytes=container.metadata_xml_bytes,
        settings_xml_bytes=container.settings_xml_bytes,
        metadata_root=metadata_root,
        settings_root=settings_root,
    )


def open_psdata(input_file: str | Path) -> PsDataDocument:
    container = parse_container(input_file)
    return _build_document(container)
