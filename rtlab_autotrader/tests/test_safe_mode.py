from rtlab_core.risk.safe_mode import SafeModeController


def test_safe_mode_enable_disable() -> None:
    safe = SafeModeController(safe_factor=0.4)
    state = safe.enable("ws_lag")
    assert state.enabled
    assert state.reason == "ws_lag"
    assert state.disable_shorts

    off = safe.disable()
    assert not off.enabled
    assert off.reason is None
