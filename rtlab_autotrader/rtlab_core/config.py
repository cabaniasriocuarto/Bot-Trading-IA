from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


ModeLiteral = Literal["backtest", "dryrun", "paper", "testnet", "live", "capture_only"]


class UniverseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exchange: Literal["bybit", "okx", "binance"]
    market_type: Literal["spot", "perps"]
    whitelist: list[str] = Field(default_factory=list)
    min_volume_24h_usd: float = Field(default=0.0, ge=0.0)
    max_spread_bps: float = Field(default=30.0, gt=0.0)
    max_pairs: int = Field(default=20, ge=1, le=200)


class TimeframesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regime: str = "1h"
    signal: str = "15m"
    trigger: str = "5m"
    execution: str = "1m"


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class MicrostructureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable_vpin: bool = True
    enable_obi: bool = True
    enable_cvd: bool = True
    orderflow_gating_enabled: bool = True


class ExitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_atr_mult: float = Field(default=1.8, gt=0)
    tp_atr_mult: float = Field(default=2.5, gt=0)
    trail_trigger_atr: float = Field(default=1.2, gt=0)
    trail_atr_mult: float = Field(default=1.0, gt=0)
    time_stop_bars: int = Field(default=24, ge=1)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starting_equity: float = Field(default=10000.0, gt=0)
    risk_per_trade: float = Field(default=0.005, gt=0, le=0.05)
    daily_loss_limit_pct: float = Field(default=0.05, gt=0, le=0.05)
    max_drawdown_pct: float = Field(default=0.22, gt=0, le=0.22)
    max_positions: int = Field(default=20, ge=1, le=20)
    max_total_exposure_pct: float = Field(default=1.0, gt=0, le=1.0)
    max_asset_exposure_pct: float = Field(default=0.2, gt=0, le=1.0)
    confidence_multiplier_enabled: bool = True


class CorrelationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    lookback: int = Field(default=250, ge=20)
    cluster_threshold: float = Field(default=0.7, gt=0, lt=1)
    max_positions_per_cluster: int = Field(default=4, ge=1)
    btc_beta_limit: float = Field(default=1.5, ge=0)


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_only: bool = True
    order_timeout_sec: int = Field(default=45, ge=1)
    max_requotes: int = Field(default=2, ge=0)
    maker_fee_bps: float = Field(default=2.0, ge=0)
    taker_fee_bps: float = Field(default=5.5, ge=0)
    slippage_base_bps: float = Field(default=3.0, ge=0)
    slippage_vol_k: float = Field(default=0.8, ge=0)
    funding_proxy_bps: float = Field(default=1.0, ge=0)
    spread_proxy_bps: float = Field(default=4.0, ge=0)


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    safe_mode_enabled: bool = True
    safe_factor: float = Field(default=0.5, gt=0, le=1)
    safe_max_positions: int = Field(default=5, ge=1, le=20)
    safe_vpin_max_percentile: float = Field(default=70.0, ge=0, le=100)
    safe_adx_min: float = Field(default=20.0, ge=0)
    safe_spread_max_bps: float = Field(default=8.0, ge=0)
    kill_on_max_dd: bool = True
    kill_on_critical_errors: int = Field(default=5, ge=1)


class NotificationsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_enabled: bool = True
    bot_token: str | None = None
    chat_id: str | None = None


class BacktestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    realism_gate: bool = True
    stress_fees_mult: float = Field(default=2.0, ge=1)
    stress_slippage_mult: float = Field(default=2.0, ge=1)
    stress_param_variation_pct: float = Field(default=0.15, ge=0)
    min_oos_segments: int = Field(default=2, ge=1)
    reports_dir: str = "user_data/logs/reports"


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ModeLiteral
    universe: UniverseConfig
    timeframes: TimeframesConfig
    strategy: StrategyConfig
    microstructure: MicrostructureConfig
    exits: ExitsConfig
    risk: RiskConfig
    correlation: CorrelationConfig
    execution: ExecutionConfig
    safety: SafetyConfig
    notifications: NotificationsConfig
    backtest: BacktestConfig

    @model_validator(mode="after")
    def validate_guardrails(self) -> "RuntimeConfig":
        if self.safety.safe_max_positions > self.risk.max_positions:
            raise ValueError("safe_max_positions must be <= max_positions")
        if self.safety.safe_spread_max_bps > self.universe.max_spread_bps:
            raise ValueError("safe_spread_max_bps must be <= universe.max_spread_bps")
        return self


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value


def load_config(path: str | Path) -> RuntimeConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    payload = _expand_env(payload)
    try:
        return RuntimeConfig.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid runtime config: {exc}") from exc
