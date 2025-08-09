#!/usr/bin/env python3
"""CLI skeleton for the Transaction Finder project.

Currently supports only --help. Further functionality will be added in later tasks.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from typing import List

from dotenv import load_dotenv

import finder  # local module

# Load environment variables from a local .env file, if present
load_dotenv()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find Ethereum transactions that match a given ETH→stablecoin swap criteria."
    )
    parser.add_argument(
        "--date",
        required=True,
        metavar="YYYY-MM-DD",
        help="Target UTC date to search (e.g. 2025-07-10)",
    )
    parser.add_argument(
        "--tokens",
        default="USDC,USDT",
        metavar="SYM1,SYM2",
        help="Comma-separated list of stablecoin symbols to search (default: USDC,USDT)",
    )
    parser.add_argument(
        "--eth",
        type=float,
        default=17.6,
        metavar="AMOUNT",
        help="Target ETH amount (default: 17.6)",
    )
    return parser.parse_args()


def basic_stats(date_str: str, token_syms: List[str]) -> None:
    """Fetch and print basic statistics for the given date and token list."""
    start_ts = finder.ts(date_str, "00:00:00")
    end_ts = finder.ts(date_str, "23:59:59")
    start_block = finder.get_block_by_time(start_ts, "before")
    print(f"Start block (00:00 UTC): {start_block}")
    end_block = finder.get_block_by_time(end_ts, "after")
    print(f"End block   (23:59 UTC): {end_block}\n")

    for sym in token_syms:
        addr = finder.TOKEN_REGISTRY.get(sym.upper())
        if not addr:
            print(f"[!] Unknown token symbol '{sym}'. Skipping.")
            continue

        transfers = finder.get_token_transfers(addr, start_block, end_block)
        print(f"{sym.upper()} transfers on {date_str}: {len(transfers)}")

    print("\nNote: These are raw ERC-20 Transfer events and not yet filtered by amount.")


def main() -> None:
    # argparse handles --help automatically (prints help and exits).
    args = parse_args()

    # Basic environment validation (skipped when --help exits early)
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        raise SystemExit(
            "Missing ETHERSCAN_API_KEY environment variable. "
            "Create a .env file (see .env.example) or export it in your shell."
        )

    # Placeholder behaviour – will be replaced in later tasks
    token_list = [t.strip().upper() for t in args.tokens.split(",") if t.strip()]
    basic_stats(args.date, token_list)


if __name__ == "__main__":
    main()