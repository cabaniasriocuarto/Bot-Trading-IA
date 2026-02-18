import pytest

from rtlab_core.strategy_packs.dsl_parser import DSLParseError, evaluate_expression, evaluate_rule_set


def _context() -> dict:
    return {
        "EMA": lambda n: 100.0 if int(n) == 20 else 99.0,
        "RSI": lambda n: 55.0,
        "ATR": lambda n: 2.0,
        "ADX": lambda n: 25.0,
        "CLOSE": lambda: 101.0,
        "OPEN": lambda: 100.0,
        "HIGH": lambda: 102.0,
        "LOW": lambda: 99.0,
        "VOLUME": lambda: 1000.0,
        "SPREAD_BPS": lambda: 8.0,
        "OBI_TOPN": lambda: 0.56,
        "CVD": lambda m: 10.0,
        "VPIN_PCTL": lambda: 60.0,
        "TSCAN_TMAX": lambda: 2.3,
        "DIST_TO_EMA": lambda n: 1.0,
        "LIQUIDITY_OK": lambda: True,
    }


def test_dsl_expression_evaluation() -> None:
    value = evaluate_expression("EMA(20) > EMA(50) and RSI(14) >= 45", _context())
    assert value is True


def test_if_orderflow_enabled() -> None:
    expr = "IF_ORDERFLOW_ENABLED(OBI_TOPN() > 0.55 and CVD(20) > 0)"
    assert evaluate_expression(expr, _context(), orderflow_enabled=True) is True
    assert evaluate_expression(expr, _context(), orderflow_enabled=False) is True


def test_rule_set_explainability() -> None:
    rules = {
        "env": "LIQUIDITY_OK() and SPREAD_BPS() < 10",
        "entry": "RSI(14) > 70",
    }
    result = evaluate_rule_set(rules, _context())
    assert not result.value
    assert result.failed_checks == ["entry"]


def test_disallow_unknown_function() -> None:
    with pytest.raises(DSLParseError):
        evaluate_expression("HACK(1) > 0", _context())
