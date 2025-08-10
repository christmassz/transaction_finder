#!/usr/bin/env python3
"""Search BigQuery public Ethereum dataset for ETH transfers around a target amount.

Usage:
  python bigquery_search.py --start 2025-07-06 --end 2025-07-20 --eth 17.6 --tol 0.001
Requires:
  - google-cloud-bigquery in requirements
  - GOOGLE_APPLICATION_CREDENTIALS env var pointing to service-account JSON
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from datetime import datetime
from pathlib import Path
import json
import os

from google.cloud import bigquery
from google.cloud.bigquery import Client


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Find ETH transfers of a given amount via BigQuery")
    p.add_argument("--start", required=True, help="Start UTC date YYYY-MM-DD")
    p.add_argument("--end", required=True, help="End UTC date YYYY-MM-DD (inclusive)")
    p.add_argument("--eth", type=float, required=True, help="Target ETH amount, e.g., 17.6")
    p.add_argument("--tol", type=float, default=0.000001, help="Tolerance in ETH (default 1e-6)")
    p.add_argument("--out", default="bq_results.json", help="Output JSON file path")
    return p.parse_args()


def build_query(start: str, end: str, target_eth: float, tol_eth: float) -> str:
    return f"""
    DECLARE target_eth FLOAT64 DEFAULT {target_eth};
    DECLARE tol_eth    FLOAT64 DEFAULT {tol_eth};
    SELECT
      block_number,
      block_timestamp,
      `hash`,
      from_address,
      to_address,
      value / 1e18 AS eth_value
    FROM `bigquery-public-data.crypto_ethereum.transactions`
    WHERE
      block_timestamp BETWEEN '{start} 00:00:00' AND '{end} 23:59:59'
      AND ABS(value / 1e18 - target_eth) <= tol_eth
    ORDER BY block_timestamp;
    """


def run_query(client: Client, query: str):
    job = client.query(query)
    return list(job.result())


def main() -> None:
    args = parse_args()
    target = Decimal(str(args.eth))
    tol = Decimal(str(args.tol))
    target_eth_f = float(target)
    tol_eth_f = float(tol)

    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds or not Path(creds).is_file():
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS not set or file missing.")

    client = bigquery.Client()
    sql = build_query(args.start, args.end, target_eth_f, tol_eth_f)
    print("Running BigQuery… this may take a minute…")
    rows = run_query(client, sql)
    print(f"Rows returned: {len(rows)}")

    data = [dict(r) for r in rows]
    Path(args.out).write_text(json.dumps(data, indent=2, default=str))
    print(f"[✓] Saved results to {args.out}")


if __name__ == "__main__":
    main()