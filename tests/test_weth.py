import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import finder


def test_get_weth_input(monkeypatch):
    """Ensure get_weth_input sums WETH Transfer amounts from receipt logs."""
    txhash = "0xabc"

    # Build fake receipt with two WETH Transfer events of 5 ETH each (10e18 Wei total).
    topic_transfer = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55aabbb12f123"

    def make_log(amount_eth: float):
        return {
            "address": finder.WETH_ADDR,
            "topics": [topic_transfer],
            "data": hex(int(amount_eth * 10 ** 18)),
        }

    log1 = make_log(5)
    log2 = make_log(5)

    fake_receipt = {
        "status": "0x1",
        "logs": [log1, log2],
    }

    def fake_call(params, timeout=30):
        return {"result": fake_receipt}

    monkeypatch.setattr(finder, "_call_etherscan", fake_call)

    eth_in = finder.get_weth_input(txhash)
    assert eth_in == 10.0