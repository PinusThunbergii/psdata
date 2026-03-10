from __future__ import annotations

import argparse
from pathlib import Path

from psdata import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Export decoded psdata artifacts")
    parser.add_argument("input", type=Path, help="Path to .psdata or .pssettings file")
    parser.add_argument("--out", type=Path, default=None, help="Output directory")
    parser.add_argument("--step", type=int, default=1, help="Channel CSV sample step")
    parser.add_argument(
        "--no-channel-data",
        action="store_true",
        help="Do not export per-sample channel CSV files",
    )
    args = parser.parse_args()

    out_dir = args.out or args.input.with_suffix(args.input.suffix + ".decoded.example")
    summary = run(
        input_file=args.input,
        out_dir=out_dir,
        extract_channel_series=not args.no_channel_data,
        channel_step=max(1, args.step),
    )
    print("summary:", out_dir / "summary.json")
    print("type:", summary["header"]["file_type"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
