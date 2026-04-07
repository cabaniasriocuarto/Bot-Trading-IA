from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from rtlab_core.src.data.binance_futures_bootstrap import bootstrap_futures_datasets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap canonico de datasets Binance Futures (1m base + resample) con zips oficiales y fallback REST."
    )
    parser.add_argument("--user-data-dir", default=str(BACKEND_ROOT / "user_data"))
    parser.add_argument("--market-family", required=True, choices=["usdm", "coinm"])
    parser.add_argument("--symbols", nargs="*", default=[])
    parser.add_argument("--top-n", type=int, default=0)
    parser.add_argument("--start-month", required=True, help="YYYY-MM")
    parser.add_argument("--end-month", required=True, help="YYYY-MM")
    parser.add_argument(
        "--resample-timeframes",
        nargs="*",
        default=["5m", "15m", "1h", "4h", "1d"],
        help="Timeframes derivados desde 1m",
    )
    parser.add_argument("--skip-checksum", action="store_true")
    parser.add_argument("--no-rest-fallback", action="store_true")
    args = parser.parse_args()

    payload = bootstrap_futures_datasets(
        user_data_dir=Path(args.user_data_dir).resolve(),
        market_family=args.market_family,
        start_month=args.start_month,
        end_month=args.end_month,
        symbols=list(args.symbols or []),
        top_n=(int(args.top_n) if int(args.top_n or 0) > 0 else None),
        resample_timeframes=list(args.resample_timeframes or []),
        skip_checksum=bool(args.skip_checksum),
        allow_rest_fallback=not bool(args.no_rest_fallback),
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
