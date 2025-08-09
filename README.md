# Transaction Finder

CLI utility to locate Ethereum transactions matching a given **ETH → stablecoin** swap (USDC, USDT) on a target UTC date.

## Features
* Date-to-block mapping via Etherscan API.
* Fetches ERC-20 Transfer events for USDC & USDT with paging ≥10k.
* Filters transfers by approximate stablecoin amount ± tolerance.
* Retrieves explicit ETH input, falling back to WETH path detection via receipt logs.
* Matches combinations of up to _N_ transactions that sum to the desired ETH amount.

## Installation
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration
Create a `.env` file (or export env var) with your API key:
```ini
ETHERSCAN_API_KEY=YOUR_KEY_HERE
```

## Usage
```bash
python main.py \
  --date 2025-07-10 \
  --tokens USDC,USDT \
  --eth 17.6 \
  --stable-amount 52800 \
  --stable-pct-tol 2 \
  --eth-tol 0.02 \
  --blocklist mev_blocklist.txt \
  --json-file results.json
```

* `mev_blocklist.txt` should contain one address per line (lower- or mixed-case). Any transfer whose `from` **or** `to` address is on the list will be skipped.

## Testing
```bash
pytest -q  # runs unit tests
```