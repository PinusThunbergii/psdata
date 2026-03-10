"""Low-level parser and binary decoding for PicoScope psdata containers."""

from __future__ import annotations

import gzip
import io
import struct
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from .model import BinaryDescriptor, Header, KnownChunk, MetadataInfo, ParsedContainer, PsDataError

SIGNATURE = 0x4457574A
FILETYPE_DATA = 0x049BA5E3
FILETYPE_SETTINGS = 0x9EB3687E
CORE_MARKER = 0x45E3F55B

CHUNK_PREVIEW_SMALL = 0xF007BA11
CHUNK_PREVIEW_LARGE = 0x6A706863
CHUNK_REFERENCE_WAVEFORMS = 0x6368706A
CHUNK_AUTOMOTIVE_DETAILS = 0x464D4954


def u32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise PsDataError(f"Unexpected EOF while reading uint32 at offset {offset}")
    return struct.unpack_from("<I", data, offset)[0]


def i32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise PsDataError(f"Unexpected EOF while reading int32 at offset {offset}")
    return struct.unpack_from("<i", data, offset)[0]


def i64(data: bytes, offset: int) -> int:
    if offset + 8 > len(data):
        raise PsDataError(f"Unexpected EOF while reading int64 at offset {offset}")
    return struct.unpack_from("<q", data, offset)[0]


def bitreverse32(value: int) -> int:
    value = ((value >> 1) & 0x55555555) | ((value & 0x55555555) << 1)
    value = ((value >> 2) & 0x33333333) | ((value & 0x33333333) << 2)
    value = ((value >> 4) & 0x0F0F0F0F) | ((value & 0x0F0F0F0F) << 4)
    value = ((value >> 8) & 0x00FF00FF) | ((value & 0x00FF00FF) << 8)
    return ((value >> 16) | (value << 16)) & 0xFFFFFFFF


def er_transform(payload: bytes, seed: int, warmup_words: int = 0) -> bytes:
    data = bytearray(payload)
    word_count = (len(data) + 3) // 4
    words = [0] * word_count

    for idx, byte in enumerate(data):
        words[idx // 4] |= byte << (8 * (3 - (idx % 4)))

    seed &= 0xFFFFFFFF
    for idx in range(word_count + warmup_words):
        feedback = ((seed >> 31) ^ (seed >> 21) ^ (seed >> 1) ^ seed) & 1
        seed = ((seed << 1) | feedback) & 0xFFFFFFFF
        if idx < word_count:
            words[idx] ^= seed
            words[idx] ^= bitreverse32(seed)

    for idx in range(len(data)):
        data[idx] = (words[idx // 4] >> (8 * (3 - (idx % 4)))) & 0xFF

    return bytes(data)


def clean_settings_xml(raw: bytes) -> bytes:
    raw = raw.lstrip(b"\xef\xbb\xbf")
    end = raw.find(b"</settings>")
    if end != -1:
        raw = raw[: end + len(b"</settings>")]
    return raw.rstrip(b"\x00\r\n\t ")


def parse_header(data: bytes) -> Header:
    if len(data) < 84:
        raise PsDataError("File too small to be PS6 container")

    sig = u32(data, 0)
    ftype = u32(data, 4)
    version = u32(data, 8)
    main_len = i64(data, 12)

    if sig != SIGNATURE:
        raise PsDataError(f"Unexpected signature 0x{sig:08X}, expected 0x{SIGNATURE:08X}")

    main_start = 20 + 64
    main_end = main_start + main_len
    if main_end > len(data):
        raise PsDataError("Main payload length points past EOF")

    return Header(
        signature=sig,
        file_type_marker=ftype,
        header_version=version,
        main_payload_length=main_len,
        main_payload_start=main_start,
        main_payload_end=main_end,
    )


def read_kq_block(data: bytes, offset: int) -> tuple[bytes, int]:
    compressed_flag = i32(data, offset)
    uncompressed_len = i64(data, offset + 4)
    payload_offset = offset + 4 + 8 + 64

    if payload_offset > len(data):
        raise PsDataError("kq payload offset beyond file size")

    if compressed_flag:
        bio = io.BytesIO(data[payload_offset:])
        with gzip.GzipFile(fileobj=bio, mode="rb") as gz:
            payload = gz.read(uncompressed_len)
        consumed = bio.tell()
        next_offset = payload_offset + consumed
    else:
        end = payload_offset + uncompressed_len
        if end > len(data):
            raise PsDataError("kq uncompressed payload runs past EOF")
        payload = data[payload_offset:end]
        next_offset = end

    return payload, next_offset


def parse_metadata_xml(xml_bytes: bytes) -> MetadataInfo:
    xml_bytes = clean_settings_xml(xml_bytes)
    text = xml_bytes.decode("utf-8", errors="ignore")

    try:
        root = ET.fromstring(text)
    except ET.ParseError as ex:
        raise PsDataError(f"Failed to parse metadata XML: {ex}") from ex

    def item_value(tag: str) -> Optional[str]:
        elem = root.find(tag)
        if elem is None:
            return None
        return elem.attrib.get("value")

    def as_int(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    return MetadataInfo(
        app_version=item_value("applicationversion"),
        file_guid=item_value("fileguid"),
        uncompressed_length=as_int(item_value("uncompressedlength")),
        compressed_length=as_int(item_value("compressedlength")),
        binary_version=as_int(item_value("binaryversion")),
    )


def decode_settings_payload(data: bytes, header: Header, meta: MetadataInfo, meta_xml_bytes: bytes) -> bytes:
    if meta.binary_version == 0:
        return clean_settings_xml(meta_xml_bytes)

    if meta.binary_version != 2:
        raise PsDataError(f"Unsupported binaryversion={meta.binary_version}")

    if not meta.file_guid or meta.uncompressed_length is None or meta.compressed_length is None:
        raise PsDataError("Metadata XML does not contain required fields for binaryversion=2")

    comp_len = meta.compressed_length
    settings_start = header.main_payload_start + header.main_payload_length - comp_len
    settings_end = settings_start + comp_len
    if settings_start < header.main_payload_start or settings_end > len(data):
        raise PsDataError("Compressed settings range is invalid")

    encrypted = data[settings_start:settings_end]
    guid_bytes = uuid.UUID(meta.file_guid).bytes_le
    seed64 = int.from_bytes(guid_bytes[:8], "little", signed=False)
    seed = (seed64 ^ settings_start ^ meta.uncompressed_length) & 0xFFFFFFFF
    transformed = er_transform(encrypted, seed, warmup_words=0)
    xml_bytes = gzip.decompress(transformed)
    return clean_settings_xml(xml_bytes)


def find_chunk(data: bytes, magic: int, with_length: bool, start_position: int = 0) -> Optional[bytes]:
    stream = io.BytesIO(data)
    stream.seek(0, io.SEEK_END)

    while True:
        try:
            num = stream.seek(-8, io.SEEK_CUR)
        except OSError:
            return None

        ptr_raw = stream.read(8)
        if len(ptr_raw) < 8:
            return None
        chunk_start = struct.unpack("<q", ptr_raw)[0]

        if chunk_start > stream.tell() or chunk_start < start_position:
            return None

        stream.seek(chunk_start, io.SEEK_SET)
        m_raw = stream.read(4)
        if len(m_raw) < 4:
            return None
        chunk_magic = struct.unpack("<I", m_raw)[0]

        if chunk_magic == magic:
            if with_length:
                n3_raw = stream.read(8)
                if len(n3_raw) < 8:
                    return None
                payload_len = struct.unpack("<q", n3_raw)[0]
            else:
                payload_len = num - chunk_start

            current = stream.tell()
            if current + payload_len > num + 4 or current + payload_len < chunk_start:
                return None
            return stream.read(payload_len)

        stream.seek(-4, io.SEEK_CUR)


def marker_name(marker: int) -> str:
    if marker == FILETYPE_DATA:
        return "data"
    if marker == FILETYPE_SETTINGS:
        return "settings"
    return f"unknown(0x{marker:08X})"


def xml_value(node: Optional[ET.Element], path: str) -> Optional[str]:
    elem = node.find(path) if node is not None else None
    if elem is None:
        return None
    if "value" in elem.attrib:
        return elem.attrib.get("value")
    text = (elem.text or "").strip()
    return text or None


def direct_attr(node: Optional[ET.Element], attr: str) -> Optional[str]:
    if node is None:
        return None
    return node.attrib.get(attr)


def to_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def descriptor_from_binary_node(binary_node: ET.Element) -> BinaryDescriptor:
    return BinaryDescriptor.from_xml_values(
        guid=direct_attr(binary_node, "guid"),
        uncompressed_length=to_int(xml_value(binary_node, "uncompressedlength")) or 0,
        binary_version=to_int(xml_value(binary_node, "binaryversion")) or 0,
        relative_offset=to_int(xml_value(binary_node, "offset")) or 0,
        compression_type=(xml_value(binary_node, "compressiontype") or "none"),
        compressed_length=to_int(xml_value(binary_node, "compressedlength")) or 0,
    )


def decode_binary_blob(data: bytes, header: Header, descriptor: BinaryDescriptor) -> bytes:
    absolute_start = header.main_payload_start + descriptor.relative_offset
    if absolute_start < 0 or absolute_start > len(data):
        raise PsDataError(f"Binary blob offset out of range: {absolute_start}")

    if descriptor.compression_type == "none":
        absolute_end = absolute_start + descriptor.uncompressed_length
        if absolute_end > len(data):
            raise PsDataError("Uncompressed binary blob runs past EOF")
        return data[absolute_start:absolute_end]

    if descriptor.compression_type != "gzip":
        raise PsDataError(f"Unsupported compression type: {descriptor.compression_type}")

    absolute_end = absolute_start + descriptor.compressed_length
    if absolute_end > len(data):
        raise PsDataError("Compressed binary blob runs past EOF")

    blob = data[absolute_start:absolute_end]
    if descriptor.binary_version == 2 and descriptor.guid:
        guid_bytes = uuid.UUID(descriptor.guid).bytes_le
        seed64 = int.from_bytes(guid_bytes[:8], "little", signed=False)
        seed = (seed64 ^ absolute_start ^ descriptor.uncompressed_length) & 0xFFFFFFFF
        blob = er_transform(blob, seed, warmup_words=0)

    payload = gzip.decompress(blob)
    if descriptor.uncompressed_length and len(payload) > descriptor.uncompressed_length:
        payload = payload[: descriptor.uncompressed_length]
    return payload


def decode_binary_blob_from_node(data: bytes, header: Header, binary_node: ET.Element) -> bytes:
    descriptor = descriptor_from_binary_node(binary_node)
    return decode_binary_blob(data=data, header=header, descriptor=descriptor)


def read_known_chunks(data: bytes) -> list[KnownChunk]:
    result: list[KnownChunk] = []
    for magic, with_length, default_name in [
        (CHUNK_PREVIEW_SMALL, False, "preview_small.png"),
        (CHUNK_PREVIEW_LARGE, False, "preview_large.png"),
        (CHUNK_REFERENCE_WAVEFORMS, False, "reference_waveforms.bin"),
        (CHUNK_AUTOMOTIVE_DETAILS, True, "automotive_details.xml"),
    ]:
        payload = find_chunk(data, magic, with_length, start_position=0)
        if payload is None:
            continue
        if magic == CHUNK_AUTOMOTIVE_DETAILS:
            payload = payload.rstrip(b"\x00")
        result.append(
            KnownChunk(
                magic=magic,
                magic_hex=f"0x{magic:08X}",
                with_length=with_length,
                default_name=default_name,
                payload=payload,
                size=len(payload),
            )
        )
    return result


def parse_container(path: str | Path) -> ParsedContainer:
    source = Path(path)
    data = source.read_bytes()
    header = parse_header(data)

    if u32(data, header.main_payload_end) != CORE_MARKER:
        raise PsDataError("Core marker after main payload not found")

    kq_offset = header.main_payload_end + 4 + 8
    metadata_xml_bytes, _ = read_kq_block(data, kq_offset)
    metadata_xml_bytes = clean_settings_xml(metadata_xml_bytes)
    metadata = parse_metadata_xml(metadata_xml_bytes)
    settings_xml_bytes = decode_settings_payload(data, header, metadata, metadata_xml_bytes)

    return ParsedContainer(
        source=source,
        raw_bytes=data,
        header=header,
        metadata=metadata,
        metadata_xml_bytes=metadata_xml_bytes,
        settings_xml_bytes=settings_xml_bytes,
    )
