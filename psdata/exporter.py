"""Export utilities for psdata reader.

This module contains CSV/decoded-folder export logic extracted from reader.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from .model import Header, PsDataError
from .parser import (
    decode_binary_blob_from_node,
    direct_attr,
    marker_name,
    read_known_chunks,
    to_float,
    to_int,
    xml_value,
)
from .reader import open_psdata


def export_settings_csvs(settings_xml: bytes, out_dir: Path) -> dict:
    try:
        root = ET.fromstring(settings_xml.decode("utf-8", errors="ignore"))
    except ET.ParseError as ex:
        raise PsDataError(f"Failed to parse settings XML for CSV export: {ex}") from ex

    capture_windows_path = out_dir / "capture_windows.csv"
    channels_path = out_dir / "channels.csv"
    channel_repo_path = out_dir / "channel_repository.csv"

    capture_window_fields = [
        "window_index",
        "window_type",
        "device_reference_guid",
        "circular_currentindex",
        "circular_capacity",
        "downloadmanager",
        "channels_count",
        "maths_channels_count",
        "notes",
    ]
    channel_fields = [
        "window_index",
        "window_type",
        "channel_index",
        "enabled",
        "coupling",
        "isautoranging",
        "value",
        "unit_type",
        "probe_guid",
        "probe_name_en_us",
        "probe_name_any",
        "range_scaled_min",
        "range_scaled_max",
        "range_input_min",
        "range_input_max",
        "minadccounts",
        "maxadccounts",
        "adccountszerooffset",
    ]
    repo_fields = [
        "window_index",
        "window_type",
        "repo_type",
        "channel_index",
        "formula",
        "formula_name",
        "formula_colour",
        "range_min",
        "range_max",
        "unit_type",
        "full_name",
        "short_name",
        "si",
    ]

    capture_rows = []
    channel_rows = []
    repo_rows = []

    capture_windows = root.findall("./capturewindows/capturewindow")
    for window_index, cw in enumerate(capture_windows):
        window_type = xml_value(cw, "capturewindowtype")
        dev_ref_guid = direct_attr(cw.find("devicereference"), "guid")

        channel_nodes = cw.findall("./circularBuffer/devicemodeladapters/devicesettings/channelconfig/channels/channel")
        maths_nodes = cw.findall("./channelrepository/mathsChannelCollection/mathsChannel")

        notes_elem = cw.find("capturewindownotes")
        notes_value = (
            direct_attr(notes_elem, "value")
            or xml_value(notes_elem, "value")
            or ((notes_elem.text or "").strip() if notes_elem is not None else None)
        )

        capture_rows.append(
            {
                "window_index": window_index,
                "window_type": window_type,
                "device_reference_guid": dev_ref_guid,
                "circular_currentindex": xml_value(cw, "circularBuffer/currentindex"),
                "circular_capacity": xml_value(cw, "circularBuffer/capacity"),
                "downloadmanager": xml_value(cw, "circularBuffer/downloadmanager"),
                "channels_count": len(channel_nodes),
                "maths_channels_count": len(maths_nodes),
                "notes": notes_value,
            }
        )

        for channel_index, ch in enumerate(channel_nodes):
            probe = ch.find("./probesettings/probe")
            probe_guid = direct_attr(probe, "guid")

            names = {}
            for name_node in ch.findall("./probesettings/probe/names/name"):
                culture = direct_attr(name_node, "culture") or ""
                val = xml_value(name_node, "value")
                if val is not None:
                    names[culture] = val

            probe_name_en = names.get("en-US")
            probe_name_any = probe_name_en or (next(iter(names.values())) if names else None)

            channel_rows.append(
                {
                    "window_index": window_index,
                    "window_type": window_type,
                    "channel_index": channel_index,
                    "enabled": xml_value(ch, "enabled"),
                    "coupling": xml_value(ch, "coupling"),
                    "isautoranging": xml_value(ch, "isautoranging"),
                    "value": xml_value(ch, "value"),
                    "unit_type": xml_value(ch, "unit/unittype"),
                    "probe_guid": probe_guid,
                    "probe_name_en_us": probe_name_en,
                    "probe_name_any": probe_name_any,
                    "range_scaled_min": xml_value(ch, "probesettings/range/scaledrange/min/value"),
                    "range_scaled_max": xml_value(ch, "probesettings/range/scaledrange/max/value"),
                    "range_input_min": xml_value(ch, "probesettings/range/inputrange/min/value"),
                    "range_input_max": xml_value(ch, "probesettings/range/inputrange/max/value"),
                    "minadccounts": xml_value(ch, "minadccounts"),
                    "maxadccounts": xml_value(ch, "maxadccounts"),
                    "adccountszerooffset": xml_value(ch, "adccountszerooffset"),
                }
            )

        for math_node in maths_nodes:
            formula = math_node.find("mathsformula")
            repo_rows.append(
                {
                    "window_index": window_index,
                    "window_type": window_type,
                    "repo_type": "mathsChannel",
                    "channel_index": xml_value(math_node, "channelIndex"),
                    "formula": xml_value(formula, "formula"),
                    "formula_name": xml_value(formula, "formulaname"),
                    "formula_colour": xml_value(formula, "formulacolour"),
                    "range_min": xml_value(formula, "rangemin"),
                    "range_max": xml_value(formula, "rangemax"),
                    "unit_type": xml_value(formula, "unittype"),
                    "full_name": xml_value(formula, "fullname"),
                    "short_name": xml_value(formula, "shortname"),
                    "si": xml_value(formula, "si"),
                }
            )

    with capture_windows_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=capture_window_fields)
        writer.writeheader()
        writer.writerows(capture_rows)

    with channels_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=channel_fields)
        writer.writeheader()
        writer.writerows(channel_rows)

    with channel_repo_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=repo_fields)
        writer.writeheader()
        writer.writerows(repo_rows)

    return {
        "capture_windows_csv": str(capture_windows_path),
        "channels_csv": str(channels_path),
        "channel_repository_csv": str(channel_repo_path),
        "counts": {
            "capture_windows": len(capture_rows),
            "channels": len(channel_rows),
            "channel_repository_rows": len(repo_rows),
        },
    }


def export_channel_data(settings_xml: bytes, data: bytes, header: Header, out_dir: Path, step: int = 1) -> dict:
    if step < 1:
        step = 1

    try:
        root = ET.fromstring(settings_xml.decode("utf-8", errors="ignore"))
    except ET.ParseError as ex:
        raise PsDataError(f"Failed to parse settings XML for channel data export: {ex}") from ex

    channel_data_dir = out_dir / "channel_data"
    channel_data_dir.mkdir(parents=True, exist_ok=True)

    exports = []
    capture_windows = root.findall("./capturewindows/capturewindow")
    for window_index, cw in enumerate(capture_windows):
        window_type = xml_value(cw, "capturewindowtype")

        config_by_index = {}
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
                csv_path = out_dir / "channel_data" / f"window{window_index}_buffer{buffer_index}_channel{channel_index}.csv"
                source_samples = 0
                written_rows = 0

                with csv_path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "window_index",
                            "window_type",
                            "buffer_index",
                            "channel_index",
                            "sample_index",
                            "time_seconds",
                            "adc_raw",
                            "adc_adjusted",
                            "approx_scaled_value",
                            "unit_type",
                        ]
                    )

                    sample_offset = 0
                    for chunk_idx, value_chunk in enumerate(value_chunks):
                        binary = value_chunk.find("binary")
                        if binary is None:
                            continue

                        raw = decode_binary_blob_from_node(data, header, binary)
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
                        adc_zero = cfg.get("adc_zero_offset", 0)
                        scaled_min = cfg.get("scaled_min")
                        scaled_max = cfg.get("scaled_max")
                        unit_type = cfg.get("unit_type")

                        for i in range(0, count, step):
                            raw_adc = int(values[i])
                            adjusted_adc = raw_adc - int(adc_zero)
                            approx_scaled = None
                            if (
                                min_adc is not None
                                and max_adc is not None
                                and scaled_min is not None
                                and scaled_max is not None
                                and max_adc != min_adc
                            ):
                                approx_scaled = scaled_min + (
                                    (adjusted_adc - min_adc)
                                    * (scaled_max - scaled_min)
                                    / (max_adc - min_adc)
                                )

                            writer.writerow(
                                [
                                    window_index,
                                    window_type,
                                    buffer_index,
                                    channel_index,
                                    sample_offset + i,
                                    start + i * interval,
                                    raw_adc,
                                    adjusted_adc,
                                    approx_scaled,
                                    unit_type,
                                ]
                            )
                            written_rows += 1

                        sample_offset += count
                        source_samples += count

                exports.append(
                    {
                        "window_index": window_index,
                        "window_type": window_type,
                        "buffer_index": buffer_index,
                        "channel_index": channel_index,
                        "source_samples": source_samples,
                        "written_rows": written_rows,
                        "step": step,
                        "file": str(csv_path),
                    }
                )

    return {
        "directory": str(channel_data_dir),
        "files": exports,
        "count": len(exports),
    }


def run(input_file: Path, out_dir: Path, extract_channel_series: bool = True, channel_step: int = 1) -> dict:
    doc = open_psdata(input_file)
    data = doc.raw_bytes
    header = doc.header
    meta = doc.metadata_info
    meta_xml_bytes = doc.metadata_xml_bytes
    settings_xml = doc.settings_xml_bytes

    out_dir.mkdir(parents=True, exist_ok=True)

    metadata_xml_path = out_dir / "metadata.xml"
    metadata_xml_path.write_bytes(meta_xml_bytes)

    settings_xml_path = out_dir / "settings.xml"
    settings_xml_path.write_bytes(settings_xml)
    csv_info = export_settings_csvs(settings_xml, out_dir)
    channel_data_info = export_channel_data(settings_xml, data, header, out_dir, step=channel_step) if extract_channel_series else None

    chunks = []
    for item in read_known_chunks(data):
        path = out_dir / item.default_name
        path.write_bytes(item.payload)
        chunks.append(
            {
                "magic": item.magic_hex,
                "with_length": item.with_length,
                "size": item.size,
                "file": str(path),
            }
        )

    summary = {
        "input": str(input_file),
        "size": len(data),
        "header": {
            "signature": f"0x{header.signature:08X}",
            "file_type_marker": f"0x{header.file_type_marker:08X}",
            "file_type": marker_name(header.file_type_marker),
            "header_version": header.header_version,
            "main_payload_length": header.main_payload_length,
            "main_payload_start": header.main_payload_start,
            "main_payload_end": header.main_payload_end,
        },
        "metadata": {
            "applicationversion": meta.app_version,
            "fileguid": meta.file_guid,
            "uncompressedlength": meta.uncompressed_length,
            "compressedlength": meta.compressed_length,
            "binaryversion": meta.binary_version,
        },
        "outputs": {
            "metadata_xml": str(metadata_xml_path),
            "settings_xml": str(settings_xml_path),
            "csv": csv_info,
            "channel_data": channel_data_info,
            "chunks": chunks,
        },
    }

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse PicoScope .psdata/.pssettings container")
    parser.add_argument("input", type=Path, help="Path to .psdata/.pssettings file")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: <input>.decoded)")
    parser.add_argument("--channel-step", type=int, default=1, help="Write every N-th sample to channel CSV (default: 1)")
    parser.add_argument("--no-channel-data", action="store_true", help="Skip per-sample channel data extraction")
    args = parser.parse_args()

    input_file: Path = args.input
    if not input_file.exists():
        raise SystemExit(f"Input file not found: {input_file}")

    out_dir = args.out or input_file.with_suffix(input_file.suffix + ".decoded")

    try:
        summary = run(
            input_file,
            out_dir,
            extract_channel_series=not args.no_channel_data,
            channel_step=max(1, args.channel_step),
        )
    except PsDataError as ex:
        raise SystemExit(f"Parse error: {ex}") from ex

    print(f"Parsed: {summary['input']}")
    print(f"Type: {summary['header']['file_type']} | Header version: {summary['header']['header_version']}")
    print(f"Decoded settings: {summary['outputs']['settings_xml']}")
    print(f"Decoded metadata: {summary['outputs']['metadata_xml']}")
    print("CSV exports:")
    print(f"  capture_windows: {summary['outputs']['csv']['capture_windows_csv']}")
    print(f"  channels: {summary['outputs']['csv']['channels_csv']}")
    print(f"  channel_repository: {summary['outputs']['csv']['channel_repository_csv']}")
    print(
        "  counts: "
        f"windows={summary['outputs']['csv']['counts']['capture_windows']}, "
        f"channels={summary['outputs']['csv']['counts']['channels']}, "
        f"repo_rows={summary['outputs']['csv']['counts']['channel_repository_rows']}"
    )
    if summary["outputs"]["channel_data"] is not None:
        chd = summary["outputs"]["channel_data"]
        print(f"Channel data files: {chd['count']} (dir: {chd['directory']})")
        for item in chd["files"]:
            print(
                f"  ch={item['channel_index']} buf={item['buffer_index']} "
                f"rows={item['written_rows']} src={item['source_samples']} step={item['step']} -> {item['file']}"
            )
    if summary["outputs"]["chunks"]:
        print("Extracted chunks:")
        for ch in summary["outputs"]["chunks"]:
            print(f"  {ch['magic']} -> {ch['file']} ({ch['size']} bytes)")
    else:
        print("No known trailer chunks found.")
    print(f"Summary JSON: {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
