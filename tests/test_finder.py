import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import finder


def test_ts_roundtrip():
    """Basic sanity check that ts() converts a date string to expected timestamp."""
    # 1970-01-01 00:00:00 UTC should be zero.
    assert finder.ts("1970-01-01") == 0


def test_get_token_transfers_pagination(monkeypatch):
    """Simulate Etherscan paginated responses and ensure aggregation works."""

    # Build fake responses based on page number.
    def fake_call(params, timeout=30):
        page = params.get("page", 1)
        if page == 1:
            # Return max page (10_000) to force second page.
            return {
                "status": "1",
                "message": "OK",
                "result": [{"hash": f"0x{idx}"} for idx in range(10_000)],
            }
        elif page == 2:
            # Final smaller page (<10_000) triggers break.
            return {
                "status": "1",
                "message": "OK",
                "result": [{"hash": f"0x{10000 + idx}"} for idx in range(123)],
            }
        else:
            return {"status": "0", "message": "No transactions found", "result": []}

    # Monkeypatch the internal API caller.
    monkeypatch.setattr(finder, "_call_etherscan", fake_call)

    transfers = finder.get_token_transfers("0xdeadbeef", 0, 0)
    # We expect 10_000 + 123 = 10_123 total items aggregated.
    assert len(transfers) == 10_123