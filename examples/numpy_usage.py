from __future__ import annotations

import argparse

from psdata import PsData, PsDataError


def main() -> int:
    parser = argparse.ArgumentParser(description="NumPy psdata usage example")
    parser.add_argument("input", help="Path to .psdata or .pssettings file")
    parser.add_argument("--window", type=int, default=0, help="Capture window index")
    parser.add_argument("--buffer", type=int, default=0, help="Buffer index")
    parser.add_argument("--channel", type=int, default=0, help="Channel index")
    parser.add_argument("--step", type=int, default=500, help="Downsampling step")
    args = parser.parse_args()

    ps = PsData.open(args.input)

    try:
        ch = ps.samples_np(
            channel=args.channel,
            window_index=args.window,
            buffer_index=args.buffer,
            value_mode="scaled",
            step=max(1, args.step),
        )
    except PsDataError as ex:
        print(f"NumPy API unavailable: {ex}")
        return 1

    print("samples_np:", ch.values.shape, ch.values.dtype)
    if ch.values.size:
        print("first_value:", float(ch.values[0]))

    spec = ps.fft_np(
        channel=args.channel,
        window_index=args.window,
        buffer_index=args.buffer,
        step=max(1, args.step),
        window_fn="hann",
        detrend="mean",
    )
    print("fft_np:", spec.sample_rate_hz, spec.frequency_hz.shape, spec.magnitude.shape)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
