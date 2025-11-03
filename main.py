#!/usr/bin/env python3
"""CLI skeleton for the Transaction Finder project.

Currently supports only --help. Further functionality will be added in later tasks.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
import time
import json
from decimal import Decimal
from pathlib import Path
from typing import List, Set

from dotenv import load_dotenv
import finder
load_dotenv()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find Ethereum transactions that match a given ETH→stablecoin swap criteria."
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Single UTC date to search (e.g. 2025-07-10). Ignored if --start-date is given.",
    )
    parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        help="Start UTC date for multi-day search window.",
    )
    parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        help="End UTC date (inclusive) for multi-day search window.",
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
    parser.add_argument(
        "--stable-amount",
        type=float,
        default=52800.0,
        metavar="USD_AMOUNT",
        help="Approximate target stablecoin amount, e.g. 52800 (default calculates from 17.6*3000)",
    )
    parser.add_argument(
        "--stable-pct-tol",
        type=float,
        default=2.0,
        metavar="PCT",
        help="Percentage tolerance around the stable amount (default 2)",
    )
    parser.add_argument(
        "--eth-tol",
        type=float,
        default=0.02,
        metavar="ETH",
        help="Absolute ETH tolerance for matching combinations (default 0.02)",
    )
    parser.add_argument(
        "--max-combo",
        type=int,
        default=3,
        help="Maximum number of transactions to combine when matching ETH total (default 3)",
    )
    parser.add_argument(
        "--json-file",
        type=str,
        help="Optional path to write detailed results as JSON. If omitted, no JSON file is written.",
    )
    parser.add_argument(
        "--blocklist",
        type=str,
        help="Optional path to a text file with addresses (one per line) to exclude (e.g., MEV bots)",
    )
    parser.add_argument(
        "--mev-lookback",
        type=int,
        default=10,
        help="How many recent tx to inspect for MEV activity on candidate sender address (default 10)",
    )
    parser.add_argument(
        "--require-router",
        action="store_true",
        help="Only consider token transfers where from or to address is a known DEX router (swap).",
    )
    parser.add_argument(
        "--hours-window",
        type=int,
        default=24,
        metavar="H",
        help="Number of hours (centered on --date) to include in search window (default 24). For 48h use 48.",
    )
    parser.add_argument(
        "--eth-only",
        action="store_true",
        help="Search purely for WETH transfers equal to --eth (in ETH) and ignore stable filters.",
    )
    parser.add_argument(
        "--deposit-search",
        action="store_true",
        help="Scan ETH value deposits into WETH contract equal to --eth (within tolerance).",
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
    args = parse_args()

    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        raise SystemExit(
            "Missing ETHERSCAN_API_KEY environment variable. "
            "Create a .env file (see .env.example) or export it in your shell."
        )

    token_list = [t.strip().upper() for t in args.tokens.split(",") if t.strip()]
    if args.date and not args.start_date:
        basic_stats(args.date, token_list)
    else:
        print(f"Searching block range covering {args.start_date} to {args.end_date}\n")
    lo = args.stable_amount * (1 - args.stable_pct_tol / 100)
    hi = args.stable_amount * (1 + args.stable_pct_tol / 100)

    if args.start_date and args.end_date:
        start_ts = finder.ts(args.start_date, "00:00:00")
        end_ts = finder.ts(args.end_date, "23:59:59")
    elif args.date:
        center_start = finder.ts(args.date, "00:00:00")
        window_secs = args.hours_window * 3600
        half = window_secs // 2
        start_ts = center_start - half
        end_ts = center_start + 24*3600 + half - 1 if args.hours_window > 24 else center_start + half - 1
    else:
        raise SystemExit("Provide either --date or both --start-date and --end-date")

    search_window_desc = f"{datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat()} .. {datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat()}"

    start_block = finder.get_block_by_time(start_ts, "before")
    end_block = finder.get_block_by_time(end_ts, "after")

    candidates: list[dict] = []

    def load_blocklist(path: str | None) -> Set[str]:
        if not path:
            return set()
        pth = Path(path).expanduser()
        if not pth.is_file():
            print(f"[!] Warning: blocklist file '{pth}' not found. Ignoring.")
            return set()
        lines = [ln.strip().lower() for ln in pth.read_text().splitlines() if ln.strip()]
        return set(lines)

    block_set = load_blocklist(args.blocklist)

    target_eth = Decimal(str(args.eth))
    eth_tol = Decimal(str(args.eth_tol))

    if args.eth_only:
        print("\n[ETH-only mode] Searching WETH transfers for exact ETH amount…")
        weth_transfers = finder.get_token_transfers(finder.WETH_ADDR, start_block, end_block)
        candidates = []
        for t in weth_transfers:
            val_eth = Decimal(int(t["value"])) / Decimal(1e18)
            if abs(val_eth - target_eth) <= eth_tol:
                candidates.append(
                    {
                        "hash": t["hash"],
                        "time": int(t["timeStamp"]),
                        "time_iso": datetime.fromtimestamp(int(t["timeStamp"]), tz=timezone.utc).isoformat(),
                        "from": t["from"].lower(),
                        "to": t["to"].lower(),
                        "eth": float(val_eth),
                    }
                )

        print(f"Found {len(candidates)} exact-match transfers. Now searching combinations per sender up to {args.max_combo} tx…")

        from collections import defaultdict
        import itertools

        combos: list[dict] = []
        by_sender: dict[str, list[dict]] = defaultdict(list)
        for c in candidates:
            by_sender[c["from"]].append(c)

        for sender, txs in by_sender.items():
            for r in range(1, min(args.max_combo, len(txs)) + 1):
                for combo in itertools.combinations(txs, r):
                    total = sum(Decimal(str(t["eth"])) for t in combo)
                    if abs(total - target_eth) <= eth_tol:
                        combos.append({
                            "sender": sender,
                            "total_eth": float(total),
                            "hashes": [t["hash"] for t in combo],
                        })

        print(f"Matches (senders with combos totalling {target_eth} ETH ±{eth_tol}): {len(combos)}")

        ts_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = Path(f"eth_only_{args.start_date or args.date}_{ts_tag}.json").resolve()
        json.dump({
            "run_utc": datetime.now(timezone.utc).isoformat(),
            "eth": float(target_eth),
            "eth_tol": float(eth_tol),
            "candidates": candidates,
            "matches": combos,
        }, out_path.open("w"), indent=2)
        print(f"[✓] JSON results written to {out_path}")
        return

    if args.deposit_search:
        print("\n[Deposit-search mode] Scanning ETH->WETH deposit transactions…")
        txs = finder.get_contract_txs(finder.WETH_ADDR, start_block, end_block)
        candidates = []
        tgt_wei = int(target_eth * Decimal(1e18))
        tol_wei = int(eth_tol * Decimal(1e18))
        for t in txs:
            val_wei = int(t["value"])
            if abs(val_wei - tgt_wei) <= tol_wei:
                candidates.append({
                    "hash": t["hash"],
                    "time": int(t["timeStamp"]),
                    "time_iso": datetime.fromtimestamp(int(t["timeStamp"]), tz=timezone.utc).isoformat(),
                    "from": t["from"].lower(),
                    "to": t["to"].lower(),
                    "eth": float(Decimal(val_wei) / Decimal(1e18)),
                })

        print(f"Found {len(candidates)} deposit tx with ETH value≈{target_eth} ETH.")

        out_path = Path(f"deposit_search_{args.start_date or args.date}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json").resolve()
        json.dump({
            "run_utc": datetime.now(timezone.utc).isoformat(),
            "eth": float(target_eth),
            "eth_tol": float(eth_tol),
            "candidates": candidates,
        }, out_path.open("w"), indent=2)
        print(f"[✓] JSON results written to {out_path}")
        return

    for sym in token_list:
        addr = finder.TOKEN_REGISTRY.get(sym.upper())
        if not addr:
            continue
        transfers = finder.get_token_transfers(addr, start_block, end_block)
        decimals = finder.TOKEN_DECIMALS.get(sym.upper(), 18)
        for t in transfers:
            frm = t.get("from", "").lower()
            to_addr = t.get("to", "").lower()

            if block_set and (frm in block_set or to_addr in block_set):
                continue

            if args.require_router and not (finder.is_router(frm) or finder.is_router(to_addr)):
                continue

            amount = int(t["value"]) / (10 ** decimals)
            if lo <= amount <= hi:
                candidates.append(
                    {
                        "sym": sym,
                        "hash": t["hash"],
                        "time": int(t["timeStamp"]),
                        "time_iso": datetime.fromtimestamp(int(t["timeStamp"]), tz=timezone.utc).isoformat(),
                        "usdc": amount,
                        "from": frm,
                        "to": to_addr,
                        "eth_in": None,
                    }
                )

    print(f"\nCandidates within {args.stable_amount} ±{args.stable_pct_tol}%: {len(candidates)}")

    for cand in candidates:
        val = finder.get_tx_eth_value(cand["hash"])
        if not val or val == 0:
            router_addr = cand["from"] if finder.is_router(cand["from"]) else cand["to"]
            val = finder.get_weth_input_into(cand["hash"], router_addr)
        cand["eth_in"] = val
        time.sleep(finder.POLITE_SLEEP)

    for cand in candidates:
        ts_iso = datetime.fromtimestamp(cand["time"], tz=timezone.utc).isoformat()
        print(
            f"- {ts_iso} {cand['sym']}={cand['usdc']:.2f} ETH_in={cand['eth_in'] if cand['eth_in'] is not None else 'n/a'} {cand['hash']}"
        )

    with_eth = [c for c in candidates if c["eth_in"] and c["eth_in"] > 0]
    matches: list[tuple[float, list[str]]] = []
    import itertools

    for r in range(1, min(args.max_combo, len(with_eth)) + 1):
        for combo in itertools.combinations(with_eth, r):
            total_eth = sum(x["eth_in"] for x in combo)
            if abs(total_eth - args.eth) <= args.eth_tol:
                matches.append((total_eth, [x["hash"] for x in combo]))

    print(
        f"\nMatches summing to {args.eth} ETH ±{args.eth_tol} using explicit ETH inputs: {len(matches)}"
    )
    for total, hashes in matches:
        print(f"* Total ETH_in={total:.6f} across {len(hashes)} tx:")
        for h in hashes:
            print(f"  - {h}")

    if matches and block_set:
        print("\nMEV lookback analysis (sender addresses):")
        for _, hash_list in matches:
            for h in hash_list:
                cand = next((c for c in candidates if c["hash"] == h), None)
                if not cand:
                    continue
                sender = cand["from"].lower()
                dest = cand["to"].lower()
                direct_flag = dest in block_set
                lookback_flag = finder.has_recent_mev_activity(sender, block_set, args.mev_lookback)
                status_parts = []
                if direct_flag:
                    status_parts.append("dest-is-MEV")
                if lookback_flag:
                    status_parts.append("sender-history-MEV")
                status = " & ".join(status_parts) if status_parts else "clean"
                print(f"- {h}  sender {sender[:6]}…{sender[-4:]} -> dest {dest[:6]}…{dest[-4:]} : {status}")

    json_path: Path | None = None

    if args.json_file:
        out = {
            "date": args.date,
            "tokens": token_list,
            "stable_amount": args.stable_amount,
            "stable_pct_tol": args.stable_pct_tol,
            "eth": args.eth,
            "eth_tol": args.eth_tol,
            "candidates": candidates,
            "matches": matches,
            "blocklist": list(block_set),
        }
        json_path = Path(args.json_file).expanduser().resolve()
    else:
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_path = Path(f"results_{args.date}_{ts_str}.json").resolve()
    if json_path:
        out = {
            "run_utc": datetime.now(timezone.utc).isoformat(),
            "date": args.date,
            "tokens": token_list,
            "stable_amount": args.stable_amount,
            "stable_pct_tol": args.stable_pct_tol,
            "eth": args.eth,
            "eth_tol": args.eth_tol,
            "candidates": candidates,
            "matches": matches,
            "blocklist": list(block_set),
        }
        json_path.write_text(json.dumps(out, indent=2))
        print(f"\n[✓] JSON results written to {json_path}")


if __name__ == "__main__":
    main()