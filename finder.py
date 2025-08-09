"""Utility functions for interacting with Etherscan and working with Ethereum blocks/transactions.

This is a lightweight wrapper around Etherscan's free APIs and contains only the
functionality required for the Transaction Finder CLI.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
API = "https://api.etherscan.io/api"

# Stablecoin addresses (mainnet)
TOKEN_REGISTRY: dict[str, str] = {
    "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # 6 decimals
    "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",  # 6 decimals
}

POLITE_SLEEP = 0.21  # seconds – keep within 5 req/sec Etherscan limit


# ---------------------------------------------------------------------------
# Time ↔ block helpers
# ---------------------------------------------------------------------------

def ts(date_str: str, hhmmss: str = "00:00:00") -> int:
    """Return Unix timestamp for a given UTC date-string and optional time."""
    dt = datetime.fromisoformat(f"{date_str}T{hhmmss}").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _call_etherscan(params: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    """Internal helper to call Etherscan API with standard error-handling."""
    if not API_KEY:
        raise RuntimeError("ETHERSCAN_API_KEY environment variable not set.")

    params = {**params, "apikey": API_KEY}
    r = requests.get(API, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def get_block_by_time(unix_ts: int, closest: str) -> int:
    """Return the block number closest *before* or *after* a given timestamp."""
    data = _call_etherscan(
        {
            "module": "block",
            "action": "getblocknobytime",
            "timestamp": unix_ts,
            "closest": closest,
        }
    )
    return int(data["result"])


# ---------------------------------------------------------------------------
# ERC-20 transfer fetcher
# ---------------------------------------------------------------------------

def get_token_transfers(token_addr: str, start_block: int, end_block: int) -> List[Dict[str, Any]]:
    """Return ERC-20 transfer events for *token_addr* between *start_block* and *end_block* (inclusive)."""
    page = 1
    results: list[dict[str, Any]] = []
    while True:
        chunk = _call_etherscan(
            {
                "module": "account",
                "action": "tokentx",
                "contractaddress": token_addr,
                "page": page,
                "offset": 10000,
                "sort": "asc",
                "startblock": start_block,
                "endblock": end_block,
            },
            timeout=60,
        )

        # Etherscan returns status==0 and message=="No transactions found" when done.
        if chunk.get("status") == "0" and chunk.get("message") == "No transactions found":
            break

        # Some non-success responses may still have status==1 but string error in "result".
        raw_result = chunk.get("result")
        if raw_result is None or isinstance(raw_result, str):
            # Treat as empty page and continue / break.
            page_items = []
        else:
            page_items = raw_result

        results.extend(page_items)

        # Less than the page-limit means we're done.
        if len(page_items) < 10000:
            break

        page += 1
        time.sleep(POLITE_SLEEP)
    return results