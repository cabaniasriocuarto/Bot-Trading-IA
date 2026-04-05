from __future__ import annotations

from pathlib import Path

import pytest

from rtlab_core.instruments.registry import BinanceInstrumentRegistryService


class _StubResponse:
    def __init__(self, *, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}"
        self.text = ""

    def json(self) -> dict[str, object]:
        return dict(self._payload)


def _service(tmp_path: Path) -> BinanceInstrumentRegistryService:
    return BinanceInstrumentRegistryService(
        db_path=tmp_path / "instrument_registry.sqlite3",
        repo_root=Path.cwd(),
    )


def test_registry_signed_request_preserves_auth_rejection_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    monkeypatch.setenv("BINANCE_API_KEY", "live-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "live-secret")

    def _fake_get(url: str, *, headers: dict[str, str], timeout: float) -> _StubResponse:
        assert "/api/v3/account?" in url
        assert headers["X-MBX-APIKEY"] == "live-key"
        assert timeout > 0
        return _StubResponse(
            status_code=401,
            payload={"code": -2015, "msg": "Invalid API-key, IP, or permissions for action."},
        )

    monkeypatch.setattr("rtlab_core.instruments.registry.requests.get", _fake_get)

    payload, meta = service._request_signed_json(
        "https://api.binance.com/api/v3/account",
        family="spot",
        environment="live",
    )

    assert payload is None
    assert meta["reason"] == "auth_rejected"
    assert meta["error_category"] == "auth"
    assert meta["status_code"] == 401
    assert meta["exchange_code"] == -2015
    assert meta["exchange_msg"] == "Invalid API-key, IP, or permissions for action."
    assert meta["raw_exchange_code"] == -2015
    assert meta["raw_exchange_msg"] == "Invalid API-key, IP, or permissions for action."


def test_registry_signed_request_preserves_margin_account_missing_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    monkeypatch.setenv("BINANCE_API_KEY", "live-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "live-secret")

    def _fake_get(url: str, *, headers: dict[str, str], timeout: float) -> _StubResponse:
        assert "/sapi/v1/margin/account?" in url
        assert headers["X-MBX-APIKEY"] == "live-key"
        assert timeout > 0
        return _StubResponse(
            status_code=400,
            payload={"code": -3003, "msg": "Margin account does not exist."},
        )

    monkeypatch.setattr("rtlab_core.instruments.registry.requests.get", _fake_get)

    payload, meta = service._request_signed_json(
        "https://api.binance.com/sapi/v1/margin/account",
        family="margin",
        environment="live",
    )

    assert payload is None
    assert meta["reason"] == "margin_account_missing"
    assert meta["error_category"] == "account_state"
    assert meta["status_code"] == 400
    assert meta["exchange_code"] == -3003
    assert meta["exchange_msg"] == "Margin account does not exist."
    assert meta["raw_exchange_code"] == -3003
    assert meta["raw_exchange_msg"] == "Margin account does not exist."
