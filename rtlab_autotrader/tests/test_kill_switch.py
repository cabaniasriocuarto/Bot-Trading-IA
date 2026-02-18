from rtlab_core.risk.kill_switch import KillSwitch


def test_kill_switch_trigger_and_reset() -> None:
    ks = KillSwitch()
    assert not ks.is_triggered()

    state = ks.trigger("max_drawdown")
    assert state.triggered
    assert state.reason == "max_drawdown"

    ks.reset()
    assert not ks.is_triggered()
