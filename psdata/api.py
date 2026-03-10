"""Simple high-level API for reading channels, samples and settings."""

from __future__ import annotations

import ast
import math as pymath
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

from .model import (
    ChannelArray,
    ChannelInfo,
    ChannelSample,
    ChannelSettings,
    MathChannelArray,
    MathChannelInfo,
    MathChannelSample,
    PsDataError,
    SpectrumArray,
    ValueMode,
    WindowInfo,
)
from .parser import direct_attr, to_float, to_int, xml_value
from .reader import PsDataDocument, open_psdata

_MATH_FUNCS: dict[str, Any] = {
    "abs": abs,
    "sqrt": pymath.sqrt,
    "sin": pymath.sin,
    "cos": pymath.cos,
    "tan": pymath.tan,
    "asin": pymath.asin,
    "acos": pymath.acos,
    "atan": pymath.atan,
    "exp": pymath.exp,
    "log": pymath.log,
    "log10": pymath.log10,
    "floor": pymath.floor,
    "ceil": pymath.ceil,
    "round": round,
    "min": min,
    "max": max,
}

_MATH_CONSTS: dict[str, float] = {
    "pi": pymath.pi,
    "e": pymath.e,
}


def _to_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    v = value.strip().lower()
    if v in {"true", "1", "yes"}:
        return True
    if v in {"false", "0", "no"}:
        return False
    return None


def _channel_name(channel_index: int) -> str:
    if 0 <= channel_index < 26:
        return chr(ord("A") + channel_index)
    return f"CH{channel_index}"


def _extract_channel_refs(formula: str) -> list[int]:
    refs = {int(match.group(1)) for match in re.finditer(r"#(\d+)", formula)}
    return sorted(refs)


def _compile_math_expression(formula: str) -> ast.AST:
    normalized = formula.replace("^", "**")
    normalized = re.sub(r"#(\d+)", r"ch_\1", normalized)

    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as ex:
        raise PsDataError(f"Unsupported math formula syntax: {formula}") from ex

    def validate(node: ast.AST) -> None:
        if isinstance(node, ast.Expression):
            validate(node.body)
            return

        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return
            raise PsDataError(f"Unsupported constant in math formula: {node.value!r}")

        if isinstance(node, ast.Name):
            if node.id.startswith("ch_"):
                return
            if node.id.lower() in _MATH_CONSTS:
                return
            raise PsDataError(f"Unsupported identifier in math formula: {node.id}")

        if isinstance(node, ast.BinOp):
            if not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
                raise PsDataError(f"Unsupported operator in math formula: {type(node.op).__name__}")
            validate(node.left)
            validate(node.right)
            return

        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.UAdd, ast.USub)):
                raise PsDataError(f"Unsupported unary operator in math formula: {type(node.op).__name__}")
            validate(node.operand)
            return

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise PsDataError("Only simple function calls are supported in math formulas")
            fn = node.func.id.lower()
            if fn == "fft":
                raise PsDataError("FFT() formulas are not supported by eval_math_channel() v1")
            if fn not in _MATH_FUNCS:
                raise PsDataError(f"Unsupported function in math formula: {node.func.id}")
            for arg in node.args:
                validate(arg)
            for kw in node.keywords:
                validate(kw.value)
            return

        raise PsDataError(f"Unsupported AST node in math formula: {type(node).__name__}")

    validate(tree)
    return tree


def _eval_math_ast(node: ast.AST, env: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval_math_ast(node.body, env)

    if isinstance(node, ast.Constant):
        return float(node.value)

    if isinstance(node, ast.Name):
        if node.id in env:
            return float(env[node.id])
        const_val = _MATH_CONSTS.get(node.id.lower())
        if const_val is not None:
            return float(const_val)
        raise PsDataError(f"Unknown identifier during math evaluation: {node.id}")

    if isinstance(node, ast.UnaryOp):
        operand = _eval_math_ast(node.operand, env)
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise PsDataError(f"Unsupported unary operator: {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        left = _eval_math_ast(node.left, env)
        right = _eval_math_ast(node.right, env)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            return left**right
        raise PsDataError(f"Unsupported operator: {type(node.op).__name__}")

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise PsDataError("Unsupported function call target")
        fn_name = node.func.id.lower()
        func = _MATH_FUNCS.get(fn_name)
        if func is None:
            raise PsDataError(f"Unsupported function: {node.func.id}")
        args = [_eval_math_ast(arg, env) for arg in node.args]
        kwargs = {kw.arg: _eval_math_ast(kw.value, env) for kw in node.keywords if kw.arg}
        return float(func(*args, **kwargs))

    raise PsDataError(f"Unsupported node during evaluation: {type(node).__name__}")


def _sample_numeric_value(sample: ChannelSample) -> float:
    if sample.approx_scaled_value is not None:
        return float(sample.approx_scaled_value)
    return float(sample.adc_adjusted)


def _interval_to_seconds(interval_value: Optional[float], unit_type: Optional[str]) -> Optional[float]:
    if interval_value is None:
        return None
    unit = (unit_type or "seconds").strip().lower()
    if unit in {"seconds", "second", "sec", "s"}:
        factor = 1.0
    elif unit in {"milliseconds", "millisecond", "ms"}:
        factor = 1e-3
    elif unit in {"microseconds", "microsecond", "us", "µs"}:
        factor = 1e-6
    elif unit in {"nanoseconds", "nanosecond", "ns"}:
        factor = 1e-9
    else:
        factor = 1.0
    return float(interval_value) * factor


def _channel_sample_rate_hz(window_node: ET.Element, channel_index: int) -> Optional[float]:
    buffers = window_node.findall("./circularBuffer/buffers/buffer")
    for buffer_node in buffers:
        for enabled in buffer_node.findall("./enabledchannels/enabled"):
            if to_int(xml_value(enabled, "channel")) != channel_index:
                continue
            first_timechunk = enabled.find("./collectiontimearray/timechunk")
            if first_timechunk is None:
                continue
            interval_raw = to_float(xml_value(first_timechunk, "interval"))
            interval_seconds = _interval_to_seconds(interval_raw, unit_type="seconds")
            if interval_seconds and interval_seconds > 0:
                return 1.0 / interval_seconds

    cfg_interval_raw = to_float(
        xml_value(window_node, "circularBuffer/devicemodeladapters/devicesettings/samplingconfig/interval/value")
    )
    cfg_interval_unit = xml_value(
        window_node, "circularBuffer/devicemodeladapters/devicesettings/samplingconfig/interval/unit/unittype"
    )
    cfg_interval_seconds = _interval_to_seconds(cfg_interval_raw, cfg_interval_unit)
    if cfg_interval_seconds and cfg_interval_seconds > 0:
        return 1.0 / cfg_interval_seconds

    return None


@dataclass
class XmlAccessor:
    """Dot-path accessor for XML trees.

    Examples:
    - `capturewindows.capturewindow.0.capturewindowtype`
    - `capturewindows.0.capturewindowtype` (shortcut: index inside the collection node)
    """

    root: ET.Element

    def _resolve(self, path: str) -> Optional[ET.Element]:
        if not path:
            return self.root

        tokens = [t for t in path.strip(".").split(".") if t]
        node = self.root
        if tokens and tokens[0] == node.tag:
            tokens = tokens[1:]

        idx = 0
        while idx < len(tokens):
            token = tokens[idx]

            if token.isdigit():
                children = list(node)
                index = int(token)
                if index < 0 or index >= len(children):
                    return None
                node = children[index]
                idx += 1
                continue

            if idx + 1 < len(tokens) and tokens[idx + 1].isdigit():
                child_index = int(tokens[idx + 1])
                matches = [child for child in list(node) if child.tag == token]
                if matches:
                    if child_index < 0 or child_index >= len(matches):
                        return None
                    node = matches[child_index]
                    idx += 2
                    continue

                child = node.find(token)
                if child is None:
                    return None
                nested = list(child)
                if child_index < 0 or child_index >= len(nested):
                    return None
                node = nested[child_index]
                idx += 2
                continue

            child = node.find(token)
            if child is None:
                return None
            node = child
            idx += 1

        return node

    def node(self, path: str) -> Optional[ET.Element]:
        return self._resolve(path)

    def get(self, path: str, default: Optional[str] = None, attr: str = "value") -> Optional[str]:
        node = self._resolve(path)
        if node is None:
            return default
        if attr == "text":
            text = (node.text or "").strip()
            return text or default
        if attr in node.attrib:
            return node.attrib[attr]
        if attr == "value":
            return node.attrib.get("value", default)
        return default


@dataclass
class PsData:
    """Convenient high-level facade over `PsDataDocument`."""

    document: PsDataDocument
    settings: XmlAccessor
    metadata: XmlAccessor

    @classmethod
    def open(cls, path: str | Path) -> "PsData":
        doc = open_psdata(path)
        return cls(document=doc, settings=XmlAccessor(doc.settings_root), metadata=XmlAccessor(doc.metadata_root))

    def windows_count(self) -> int:
        return len(self.document.settings_root.findall("./capturewindows/capturewindow"))

    def windows_info(self, include_channels: bool = True) -> list[WindowInfo]:
        windows = self.document.settings_root.findall("./capturewindows/capturewindow")
        result: list[WindowInfo] = []

        for window_index, window_node in enumerate(windows):
            all_channels = self.channels(window_index=window_index, enabled_only=False)
            channels = all_channels if include_channels else []
            enabled_channels_count = sum(1 for ch in all_channels if ch.enabled is True)

            notes_elem = window_node.find("capturewindownotes")
            notes = (
                direct_attr(notes_elem, "value")
                or xml_value(notes_elem, "value")
                or ((notes_elem.text or "").strip() if notes_elem is not None else None)
            )

            buffers = window_node.findall("./circularBuffer/buffers/buffer")
            maths = window_node.findall("./channelrepository/mathsChannelCollection/mathsChannel")

            result.append(
                WindowInfo(
                    window_index=window_index,
                    window_type=xml_value(window_node, "capturewindowtype"),
                    device_reference_guid=direct_attr(window_node.find("devicereference"), "guid"),
                    notes=notes,
                    buffer_count=len(buffers),
                    channels_count=len(all_channels),
                    enabled_channels_count=enabled_channels_count,
                    maths_channels_count=len(maths),
                    download_manager=xml_value(window_node, "circularBuffer/downloadmanager"),
                    channels=channels,
                )
            )

        return result

    def has_math_channels(self, window_index: int = 0) -> bool:
        return len(self.math_channels(window_index=window_index)) > 0

    def math_channels(self, window_index: int = 0) -> list[MathChannelInfo]:
        windows = self.document.settings_root.findall("./capturewindows/capturewindow")
        if window_index < 0 or window_index >= len(windows):
            raise PsDataError(f"Window index out of range: {window_index}")

        nodes = windows[window_index].findall("./channelrepository/mathsChannelCollection/mathsChannel")
        result: list[MathChannelInfo] = []
        for list_index, math_node in enumerate(nodes):
            formula_node = math_node.find("mathsformula")
            result.append(
                MathChannelInfo(
                    window_index=window_index,
                    list_index=list_index,
                    channel_index=to_int(xml_value(math_node, "channelIndex")),
                    formula=xml_value(formula_node, "formula"),
                    formula_name=xml_value(formula_node, "formulaname"),
                    formula_colour=xml_value(formula_node, "formulacolour"),
                    range_min=to_float(xml_value(formula_node, "rangemin")),
                    range_max=to_float(xml_value(formula_node, "rangemax")),
                    unit_type=xml_value(formula_node, "unittype"),
                    full_name=xml_value(formula_node, "fullname"),
                    short_name=xml_value(formula_node, "shortname"),
                    si=xml_value(formula_node, "si"),
                )
            )
        return result

    def math_channel(self, index: int, window_index: int = 0) -> MathChannelInfo:
        channels = self.math_channels(window_index=window_index)
        if index < 0 or index >= len(channels):
            raise PsDataError(f"Math channel index out of range: {index}")
        return channels[index]

    def eval_math_channel(
        self,
        index: int,
        *,
        window_index: int = 0,
        buffer_index: int = 0,
        step: int = 1,
    ) -> Iterator[MathChannelSample]:
        math_channel = self.math_channel(index=index, window_index=window_index)
        if not math_channel.formula:
            return

        formula_ast = _compile_math_expression(math_channel.formula)
        refs = _extract_channel_refs(math_channel.formula)
        if not refs:
            raise PsDataError("Math formula has no channel references (#N), cannot build sample timeline")

        per_channel_samples: dict[int, dict[int, ChannelSample]] = {}
        for ref in refs:
            samples_for_channel: dict[int, ChannelSample] = {}
            for sample in self.samples(
                channel=ref,
                window_index=window_index,
                buffer_index=buffer_index,
                step=step,
            ):
                samples_for_channel[sample.sample_index] = sample
            if not samples_for_channel:
                raise PsDataError(
                    f"No source samples for referenced channel #{ref} "
                    f"(window={window_index}, buffer={buffer_index})"
                )
            per_channel_samples[ref] = samples_for_channel

        common_indices: set[int] = set(next(iter(per_channel_samples.values())).keys())
        for channel_map in per_channel_samples.values():
            common_indices &= set(channel_map.keys())

        for sample_index in sorted(common_indices):
            env: dict[str, float] = {}
            base_sample: Optional[ChannelSample] = None

            for ref in refs:
                sample = per_channel_samples[ref][sample_index]
                if base_sample is None:
                    base_sample = sample
                env[f"ch_{ref}"] = _sample_numeric_value(sample)

            if base_sample is None:
                continue

            value = _eval_math_ast(formula_ast, env)
            yield MathChannelSample(
                window_index=window_index,
                buffer_index=buffer_index,
                list_index=math_channel.list_index,
                channel_index=math_channel.channel_index,
                sample_index=sample_index,
                time_seconds=base_sample.time_seconds,
                value=value,
                unit_type=math_channel.unit_type,
                formula_name=math_channel.formula_name,
                formula=math_channel.formula,
            )

    def eval_math_channel_rows(
        self,
        index: int,
        *,
        window_index: int = 0,
        buffer_index: int = 0,
        step: int = 1,
    ) -> Iterator[dict[str, Any]]:
        for sample in self.eval_math_channel(
            index=index,
            window_index=window_index,
            buffer_index=buffer_index,
            step=step,
        ):
            yield sample.to_dict()

    def channels(self, window_index: int = 0, enabled_only: bool = False) -> list[ChannelInfo]:
        windows = self.document.settings_root.findall("./capturewindows/capturewindow")
        if window_index < 0 or window_index >= len(windows):
            raise PsDataError(f"Window index out of range: {window_index}")

        channels = windows[window_index].findall("./circularBuffer/devicemodeladapters/devicesettings/channelconfig/channels/channel")
        result: list[ChannelInfo] = []
        for channel_index, ch in enumerate(channels):
            enabled = _to_bool(xml_value(ch, "enabled"))
            if enabled_only and enabled is not True:
                continue

            probe_names = ch.findall("./probesettings/probe/names/name")
            probe_name = None
            for name_node in probe_names:
                culture = name_node.attrib.get("culture")
                value = xml_value(name_node, "value")
                if culture == "en-US" and value:
                    probe_name = value
                    break
                if probe_name is None and value:
                    probe_name = value

            result.append(
                ChannelInfo(
                    window_index=window_index,
                    channel_index=channel_index,
                    name=_channel_name(channel_index),
                    enabled=enabled,
                    unit_type=xml_value(ch, "unit/unittype"),
                    coupling=xml_value(ch, "coupling"),
                    probe_name=probe_name,
                )
            )
        return result

    def channel_settings(self, channel: int, window_index: int = 0) -> ChannelSettings:
        windows = self.document.settings_root.findall("./capturewindows/capturewindow")
        if window_index < 0 or window_index >= len(windows):
            raise PsDataError(f"Window index out of range: {window_index}")
        window_node = windows[window_index]

        channels = window_node.findall("./circularBuffer/devicemodeladapters/devicesettings/channelconfig/channels/channel")
        if channel < 0 or channel >= len(channels):
            raise PsDataError(f"Channel index out of range: {channel}")

        ch = channels[channel]
        probe_name = None
        for name_node in ch.findall("./probesettings/probe/names/name"):
            value = xml_value(name_node, "value")
            culture = name_node.attrib.get("culture")
            if culture == "en-US" and value:
                probe_name = value
                break
            if probe_name is None and value:
                probe_name = value

        return ChannelSettings(
            window_index=window_index,
            channel_index=channel,
            name=_channel_name(channel),
            enabled=_to_bool(xml_value(ch, "enabled")),
            coupling=xml_value(ch, "coupling"),
            is_autoranging=_to_bool(xml_value(ch, "isautoranging")),
            unit_type=xml_value(ch, "unit/unittype"),
            probe_name=probe_name,
            min_adc=to_int(xml_value(ch, "minadccounts")),
            max_adc=to_int(xml_value(ch, "maxadccounts")),
            adc_zero_offset=to_int(xml_value(ch, "adccountszerooffset")),
            scaled_min=to_float(xml_value(ch, "probesettings/range/scaledrange/min/value")),
            scaled_max=to_float(xml_value(ch, "probesettings/range/scaledrange/max/value")),
            input_min=to_float(xml_value(ch, "probesettings/range/inputrange/min/value")),
            input_max=to_float(xml_value(ch, "probesettings/range/inputrange/max/value")),
            bandwidth_limit=xml_value(ch, "bandwidthlimit"),
            sample_rate_hz=_channel_sample_rate_hz(window_node, channel),
        )

    def samples(
        self,
        *,
        channel: Optional[int] = None,
        window_index: Optional[int] = None,
        buffer_index: Optional[int] = None,
        step: int = 1,
    ) -> Iterator[ChannelSample]:
        for sample in self.document.iter_channel_samples(step=step):
            if channel is not None and sample.channel_index != channel:
                continue
            if window_index is not None and sample.window_index != window_index:
                continue
            if buffer_index is not None and sample.buffer_index != buffer_index:
                continue
            yield sample

    def samples_map(
        self,
        *,
        window_index: int = 0,
        buffer_index: Optional[int] = None,
        step: int = 1,
        enabled_only: bool = True,
    ) -> dict[int, Iterator[ChannelSample]]:
        return {
            ch.channel_index: self.samples(
                channel=ch.channel_index,
                window_index=window_index,
                buffer_index=buffer_index,
                step=step,
            )
            for ch in self.channels(window_index=window_index, enabled_only=enabled_only)
        }

    def samples_np(
        self,
        channel: int,
        *,
        window_index: int = 0,
        buffer_index: int = 0,
        value_mode: ValueMode = "scaled",
        step: int = 1,
        dtype: Any = None,
    ) -> ChannelArray:
        from .arrays import samples_np as _samples_np

        return _samples_np(
            self,
            channel=channel,
            window_index=window_index,
            buffer_index=buffer_index,
            value_mode=value_mode,
            step=step,
            dtype=dtype,
        )

    def channels_np(
        self,
        *,
        window_index: int = 0,
        buffer_index: int = 0,
        value_mode: ValueMode = "scaled",
        step: int = 1,
        enabled_only: bool = True,
        dtype: Any = None,
    ) -> dict[int, ChannelArray]:
        from .arrays import channels_np as _channels_np

        return _channels_np(
            self,
            window_index=window_index,
            buffer_index=buffer_index,
            value_mode=value_mode,
            step=step,
            enabled_only=enabled_only,
            dtype=dtype,
        )

    def math_np(
        self,
        index: int,
        *,
        window_index: int = 0,
        buffer_index: int = 0,
        step: int = 1,
        dtype: Any = None,
    ) -> MathChannelArray:
        from .arrays import math_np as _math_np

        return _math_np(
            self,
            index=index,
            window_index=window_index,
            buffer_index=buffer_index,
            step=step,
            dtype=dtype,
        )

    def fft_np(
        self,
        *,
        channel: Optional[int] = None,
        math_index: Optional[int] = None,
        window_index: int = 0,
        buffer_index: int = 0,
        value_mode: ValueMode = "scaled",
        step: int = 1,
        window_fn: str = "hann",
        detrend: str = "mean",
        nfft: Optional[int] = None,
        dtype: Any = None,
    ) -> SpectrumArray:
        from .arrays import fft_np as _fft_np

        return _fft_np(
            self,
            channel=channel,
            math_index=math_index,
            window_index=window_index,
            buffer_index=buffer_index,
            value_mode=value_mode,
            step=step,
            window_fn=window_fn,
            detrend=detrend,
            nfft=nfft,
            dtype=dtype,
        )
