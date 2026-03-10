from __future__ import annotations

import argparse

from psdata import PsData


def main() -> int:
    parser = argparse.ArgumentParser(description="Basic psdata usage example")
    parser.add_argument("input", help="Path to .psdata or .pssettings file")
    parser.add_argument("--window", type=int, default=0, help="Capture window index")
    parser.add_argument("--channel", type=int, default=0, help="Channel index")
    parser.add_argument("--step", type=int, default=100, help="Sample step")
    args = parser.parse_args()

    ps = PsData.open(args.input)
    print("windows_count:", ps.windows_count())
    print("windows_info:", ps.windows_info(include_channels=False))

    print("channels:")
    for ch in ps.channels(window_index=args.window):
        print(f"  idx={ch.channel_index} name={ch.name} enabled={ch.enabled} unit={ch.unit_type}")

    cfg = ps.channel_settings(channel=args.channel, window_index=args.window)
    print("channel_settings:", cfg)

    first = next(
        ps.samples(channel=args.channel, window_index=args.window, step=max(1, args.step)),
        None,
    )
    print("first_sample:", first)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
