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

TOKEN_REGISTRY: dict[str, str] = {
    "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "USDT": "0xdac17f958d2ee523a2206206994597c13d831ec7",
}
TOKEN_DECIMALS: dict[str, int] = {
    "USDC": 6,
    "USDT": 6,
}

WETH_ADDR = "0xC02aaA39B223FE8D0A0E5C4F27eAD9083C756Cc2".lower()
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55aabbb12"[:64]

POLITE_SLEEP = 0.21

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

        if chunk.get("status") == "0" and chunk.get("message") == "No transactions found":
            break

        raw_result = chunk.get("result")
        if raw_result is None or isinstance(raw_result, str):
            page_items = []
        else:
            page_items = raw_result

        results.extend(page_items)

        if len(page_items) < 10000:
            break

        page += 1
        time.sleep(POLITE_SLEEP)
    return results


def get_contract_txs(contract_addr: str, start_block: int, end_block: int) -> List[Dict[str, Any]]:
    """Return normal transactions (external + contract calls) involving *contract_addr* in the block range."""
    page = 1
    results: list[dict[str, Any]] = []
    while True:
        chunk = _call_etherscan(
            {
                "module": "account",
                "action": "txlist",
                "address": contract_addr,
                "page": page,
                "offset": 10000,
                "startblock": start_block,
                "endblock": end_block,
                "sort": "asc",
            },
            timeout=60,
        )

        if chunk.get("status") == "0" and chunk.get("message") == "No transactions found":
            break

        raw = chunk.get("result")
        if raw is None or isinstance(raw, str):
            page_items = []
        else:
            page_items = raw

        results.extend(page_items)
        if len(page_items) < 10000:
            break
        page += 1
        time.sleep(POLITE_SLEEP)
    return results


def wei_to_eth(wei_hex: str) -> float:
    """Convert hex-encoded Wei value to floating ETH."""
    return int(wei_hex, 16) / 1e18


def get_tx_eth_value(txhash: str) -> float | None:
    """Return Ether value directly supplied in *txhash* (None if unavailable)."""
    data = _call_etherscan(
        {
            "module": "proxy",
            "action": "eth_getTransactionByHash",
            "txhash": txhash,
        }
    )

    result = data.get("result") or {}
    val_hex = result.get("value")
    if not val_hex:
        return None
    try:
        return wei_to_eth(val_hex)
    except Exception:
        return None

def _topic_to_addr(topic_hex: str) -> str:
    """Extract the 20-byte address from a 32-byte topic hex string."""
    if topic_hex.startswith("0x"):
        topic_hex = topic_hex[2:]
    return "0x" + topic_hex[-40:]


def get_weth_input_into(txhash: str, router_addr: str) -> float | None:
    """Sum the WETH transferred *into* `router_addr` within `txhash`.

    Returns amount in ETH or None if no such transfer.
    """
    data = _call_etherscan(
        {
            "module": "proxy",
            "action": "eth_getTransactionReceipt",
            "txhash": txhash,
        },
        timeout=60,
    )

    receipt = data.get("result") or {}
    logs = receipt.get("logs") or []
    weth_in = 0.0
    router_addr = router_addr.lower()

    for log in logs:
        if log.get("address", "").lower() != WETH_ADDR:
            continue
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue
        if not topics[0].lower().startswith("0xddf252ad"):
            continue

        to_addr = _topic_to_addr(topics[2]).lower()
        if to_addr != router_addr:
            continue

        raw_val = int(log.get("data", "0x0"), 16)
        weth_in += raw_val / 1e18

    if weth_in > 0:
        return weth_in
    return None

def recent_tx_addresses(addr: str, count: int = 10) -> list[dict[str, Any]]:
    """Return up to *count* most recent transactions involving *addr* (EOA or contract)."""
    data = _call_etherscan(
        {
            "module": "account",
            "action": "txlist",
            "address": addr,
            "page": 1,
            "offset": count,
            "sort": "desc",
        },
        timeout=60,
    )
    return data.get("result", []) or []


def has_recent_mev_activity(addr: str, block_set: set[str], lookback: int = 10) -> bool:
    """Return True if any of the last *lookback* tx involve a known MEV address in *block_set*."""
    txs = recent_tx_addresses(addr, lookback)
    for tx in txs:
        if tx.get("from", "").lower() in block_set or tx.get("to", "").lower() in block_set:
            return True
    return False

ROUTER_ADDRS: set[str] = {
    "0x7a250d5630b4cf539739df2c5dacab4c659f2488",
    "0xe592427a0aece92de3eedee1f18e0157c05861564",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f",
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff",
    "0x1111111254fb6c44bac0bed2854e76f90643097d",
    "0x11111112542d85b3ef69ae05771c2dccff4faa26",
    "0x9008d19f58aabd9ed0d60971565aa8510560ab41",
    "0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b",
    "0xba12222222228d8ba445958a75a0704d566bf2c8",
    "0xf6a4b1bb5ac45e4d3ab33be1284626055310976d",
    "0xdef171fe48cf0115b1d80b88dc8eab59176fee57",
}


def is_router(addr: str) -> bool:
    return addr.lower() in ROUTER_ADDRS