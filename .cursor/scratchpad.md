# Background and Motivation
We need to locate the Ethereum transaction(s) that correspond to **selling exactly 17.6 ETH for USDC or USDT on 2025-07-10 at an approximate price of 3 000 USD/ETH**.  
A script (see user-supplied code) already exists that searches for USDC transfers within a block range and tries to match ETH input amounts, but it needs polishing, extension to USDT, and more robust matching (e.g. WETH paths).

# Key Challenges and Analysis
1. **Date-to-Block mapping** – correctly identifying the first and last blocks for the UTC day so we neither miss nor include extraneous transactions.
2. **Token coverage** – searching both USDC (6 decimals) and USDT (6 decimals) transfers with a reusable helper.
3. **Swap path complexity** – many swaps route via WETH or through routers; `eth_getTransactionByHash` will show `value = 0x0` for those.  We may need to fall back to parsing swap logs (Uniswap V2/V3, 1inch, 0x, etc.) to derive the actual ETH input.
4. **Rate limits & performance** – Etherscan allows 5 requests/sec; pagination for busy days can be large.  Caching and polite sleeps are required.
5. **Tolerance windows** – allowing ±0.02 ETH and ±2 % stablecoin to account for slippage and ETH price variance.
6. **Testing & reproducibility** – we should add unit tests for helpers (block lookup, unit conversions) and optionally integration tests with mocked API responses.

# High-level Task Breakdown
- [x] **T1 – Project skeleton & environment**  
    Success: repo contains `requirements.txt` and `.env.example` with `ETHERSCAN_API_KEY`; script runs `python main.py --help` without errors.
- [x] **T2 – Refactor script into reusable functions & CLI**  
    Success: `python main.py --date 2025-07-10 --tokens USDC,USDT` prints basic stats.
- [x] **T3 – Generic token transfer fetcher**  
    Success: function `get_token_transfers(token_address, start_block, end_block)` returns >0 transfers for USDC on a known busy day.
- [x] **T4 – Support USDT in search**  
    Success: candidates list includes transfers in USDT amount window.
- [x] **T5 – Improve ETH input detection including WETH paths**  
    Success: for a known swap routed through WETH, script reports correct ETH amount.
- [x] **T6 – Combination matching logic & output**  
    Success: given synthetic or historical data, script prints the matching hash(es) totalling 17.6 ETH ±0.02.
- [x] **T7 – Unit tests & CI**  
    Success: `pytest` passes locally and in CI.
- [x] **T8 – Documentation**  
    Success: `README.md` explains usage and assumptions.

# Project Status Board
- [x] T1 – Project skeleton & environment *(completed)*
- [x] T2 – Refactor script into CLI *(completed)*
- [x] T3 – Generic token transfer fetcher *(completed)*
- [x] T4 – USDT support *(completed)*
- [x] T5 – WETH path detection *(completed)*
- [x] T6 – Combination matching *(completed)*
- [x] T7 – Tests & CI *(completed)*
- [x] T8 – Documentation *(completed)*

# Current Status / Progress Tracking
T1 completed – CLI skeleton runs `python main.py --help` successfully.
T2 – Refactor completed: basic stats printed for multiple tokens.
T3 completed: get_token_transfers tested with unit tests; pagination logic verified; pytest passes (2 tests).
T4 completed: CLI now filters candidates by stablecoin amount for both USDC & USDT; combination matching implemented.
T5 – WETH path detection implemented: new finder.get_weth_input uses receipts to sum WETH Transfer events; main switches to fallback when ETH_in=0.
T6 completed: matching logic integrated.
T7 completed: Added tests for WETH detection; pytest passes 3 tests.
T8 completed: README.md with installation, usage, testing.
T6+ updates: Added multi-day search (--start-date/--end-date), extended router list (1inch v6, Uniswap Universal), WETH-into-router exact filtering to find 17.6 ETH swaps.

# Executor's Feedback or Assistance Requests
_(empty)_

# Lessons
_(empty)_

## Experiment log
- E1: Router-only, 48h window, max-combo=1 → no 17.6 ETH match.
- E2: Increase max-combo to 3 → no match.
- E3: Add Balancer, Curve, Kyber routers; keep max-combo=3.