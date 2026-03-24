from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from rtlab_core.learning import LearningService
from rtlab_core.rollout import RolloutManager

from rtlab_core.domains.common import json_load, json_save, utc_now_iso


class BotPolicyStateRepository:
    def __init__(
        self,
        *,
        settings_path: Path,
        bot_state_path: Path,
        bots_path: Path,
        default_mode: Callable[[], str],
        exchange_name: Callable[[], str],
        exchange_keys_present: Callable[[str], bool],
        get_env: Callable[[str, str], str],
        runtime_engine_default: Callable[[], str],
        runtime_engine_real: str,
        runtime_engine_simulated: str,
        runtime_contract_version: str,
        runtime_telemetry_source_synthetic: str,
        runtime_telemetry_source_real: str,
    ) -> None:
        self.settings_path = Path(settings_path)
        self.bot_state_path = Path(bot_state_path)
        self.bots_path = Path(bots_path)
        self._default_mode = default_mode
        self._exchange_name = exchange_name
        self._exchange_keys_present = exchange_keys_present
        self._get_env = get_env
        self._runtime_engine_default = runtime_engine_default
        self._runtime_engine_real = runtime_engine_real
        self._runtime_engine_simulated = runtime_engine_simulated
        self._runtime_contract_version = runtime_contract_version
        self._runtime_telemetry_source_synthetic = runtime_telemetry_source_synthetic
        self._runtime_telemetry_source_real = runtime_telemetry_source_real

    def _ensure_default_settings(self) -> None:
        settings = json_load(self.settings_path, {})
        if settings:
            return
        learning_defaults = LearningService.default_learning_settings()
        rollout_defaults = RolloutManager.default_rollout_config()
        blending_defaults = RolloutManager.default_blending_config()
        settings = {
            "mode": self._default_mode().upper(),
            "exchange": self._exchange_name(),
            "exchange_plugin_options": ["binance", "bybit", "oanda", "alpaca"],
            "credentials": {
                "exchange_configured": self._exchange_keys_present(self._default_mode()),
                "telegram_configured": bool(self._get_env("TELEGRAM_BOT_TOKEN") and self._get_env("TELEGRAM_CHAT_ID")),
                "telegram_chat_id": self._get_env("TELEGRAM_CHAT_ID"),
            },
            "telegram": {
                "enabled": self._get_env("TELEGRAM_ENABLED", "false").lower() == "true",
                "chat_id": self._get_env("TELEGRAM_CHAT_ID"),
            },
            "risk_defaults": {
                "max_daily_loss": 5.0,
                "max_dd": 22.0,
                "max_positions": 20,
                "risk_per_trade": 0.75,
            },
            "execution": {
                "post_only_default": True,
                "slippage_max_bps": 12,
                "request_timeout_ms": 4000,
            },
            "feature_flags": {
                "orderflow": True,
                "vpin": True,
                "ml": False,
                "alerts": True,
            },
            "learning": learning_defaults,
            "rollout": rollout_defaults,
            "blending": blending_defaults,
            "gate_checklist": [],
        }
        self.save_settings(settings)

    def load_settings(self) -> dict[str, Any]:
        settings = json_load(self.settings_path, {})
        if not isinstance(settings, dict) or not settings:
            self._ensure_default_settings()
            settings = json_load(self.settings_path, {})
        if not isinstance(settings, dict):
            return {}
        return settings

    def save_settings(self, settings: dict[str, Any]) -> None:
        if not isinstance(settings, dict):
            settings = {}
        if not isinstance(settings.get("credentials"), dict):
            settings["credentials"] = {}
        if not isinstance(settings.get("telegram"), dict):
            settings["telegram"] = {"enabled": False, "chat_id": ""}
        else:
            settings["telegram"] = {
                "enabled": bool(settings["telegram"].get("enabled", False)),
                "chat_id": str(settings["telegram"].get("chat_id") or ""),
            }
        if not isinstance(settings.get("risk_defaults"), dict):
            settings["risk_defaults"] = {}
        if not isinstance(settings.get("execution"), dict):
            settings["execution"] = {}
        if not isinstance(settings.get("feature_flags"), dict):
            settings["feature_flags"] = {}
        if not isinstance(settings.get("exchange_plugin_options"), list):
            settings["exchange_plugin_options"] = ["binance", "bybit", "oanda", "alpaca"]
        if not isinstance(settings.get("gate_checklist"), list):
            settings["gate_checklist"] = []
        if not isinstance(settings.get("mode"), str) or not str(settings.get("mode") or "").strip():
            settings["mode"] = self._default_mode().upper()
        if not isinstance(settings.get("exchange"), str) or not str(settings.get("exchange") or "").strip():
            settings["exchange"] = self._exchange_name()
        settings["credentials"]["exchange_configured"] = self._exchange_keys_present(str(settings.get("mode", self._default_mode())).lower())
        settings["credentials"]["telegram_configured"] = bool(
            self._get_env("TELEGRAM_BOT_TOKEN") and (settings.get("telegram", {}).get("chat_id") or self._get_env("TELEGRAM_CHAT_ID"))
        )
        settings["credentials"]["telegram_chat_id"] = self._get_env("TELEGRAM_CHAT_ID")
        if self._get_env("TELEGRAM_CHAT_ID"):
            settings["telegram"]["chat_id"] = self._get_env("TELEGRAM_CHAT_ID")
        learning_defaults = LearningService.default_learning_settings()
        rollout_defaults = RolloutManager.default_rollout_config()
        blending_defaults = RolloutManager.default_blending_config()
        learning = settings.get("learning") if isinstance(settings.get("learning"), dict) else {}
        settings["learning"] = {
            **learning_defaults,
            **learning,
            "validation": {**learning_defaults["validation"], **(learning.get("validation") if isinstance(learning.get("validation"), dict) else {})},
            "promotion": {**learning_defaults["promotion"], **(learning.get("promotion") if isinstance(learning.get("promotion"), dict) else {})},
            "risk_profile": {**learning_defaults["risk_profile"], **(learning.get("risk_profile") if isinstance(learning.get("risk_profile"), dict) else {})},
        }
        settings["learning"]["promotion"]["allow_auto_apply"] = False
        settings["learning"]["promotion"]["allow_live"] = False
        rollout = settings.get("rollout") if isinstance(settings.get("rollout"), dict) else {}
        settings["rollout"] = {
            **rollout_defaults,
            **rollout,
            "phases": rollout.get("phases") if isinstance(rollout.get("phases"), list) else rollout_defaults["phases"],
            "abort_thresholds": {**rollout_defaults["abort_thresholds"], **(rollout.get("abort_thresholds") if isinstance(rollout.get("abort_thresholds"), dict) else {})},
            "improve_vs_baseline": {
                **rollout_defaults["improve_vs_baseline"],
                **(rollout.get("improve_vs_baseline") if isinstance(rollout.get("improve_vs_baseline"), dict) else {}),
            },
            "testnet_checks": {**rollout_defaults["testnet_checks"], **(rollout.get("testnet_checks") if isinstance(rollout.get("testnet_checks"), dict) else {})},
        }
        blending = settings.get("blending") if isinstance(settings.get("blending"), dict) else {}
        settings["blending"] = {**blending_defaults, **blending}
        json_save(self.settings_path, settings)

    def ensure_default_bot_state(self) -> None:
        state = json_load(self.bot_state_path, {})
        if state:
            return
        state = {
            "mode": self._default_mode(),
            "runtime_engine": self._runtime_engine_default(),
            "runtime_contract_version": self._runtime_contract_version,
            "runtime_telemetry_source": self._runtime_telemetry_source_synthetic,
            "runtime_loop_alive": False,
            "runtime_executor_connected": False,
            "runtime_reconciliation_ok": False,
            "runtime_operational_safety_ok": False,
            "runtime_operational_safety_status": "",
            "runtime_last_safety_eval_at": "",
            "runtime_unknown_timeout_active": False,
            "runtime_unknown_timeout_since": "",
            "runtime_exchange_connector_ok": False,
            "runtime_exchange_order_ok": False,
            "runtime_exchange_mode": "",
            "runtime_exchange_verified_at": "",
            "runtime_exchange_reason": "",
            "runtime_account_surface_ok": False,
            "runtime_account_surface_verified_at": "",
            "runtime_account_surface_reason": "",
            "runtime_account_can_trade": False,
            "runtime_account_permissions": [],
            "runtime_account_balances_count": 0,
            "runtime_account_positions_ok": False,
            "runtime_account_positions_verified_at": "",
            "runtime_account_positions_reason": "",
            "runtime_last_remote_submit_at": "",
            "runtime_last_remote_client_order_id": "",
            "runtime_last_remote_submit_error": "",
            "runtime_last_signal_action": "",
            "runtime_last_signal_reason": "",
            "runtime_last_signal_strategy_id": "",
            "runtime_last_signal_symbol": "",
            "runtime_last_signal_side": "",
            "runtime_heartbeat_at": "",
            "runtime_last_reconcile_at": "",
            "bot_status": "PAUSED",
            "running": False,
            "safe_mode": False,
            "killed": False,
            "equity": 10000.0,
            "daily_pnl": 0.0,
            "max_dd": -0.04,
            "daily_loss": -0.01,
            "last_heartbeat": utc_now_iso(),
        }
        json_save(self.bot_state_path, state)

    def load_bot_state(self) -> dict[str, Any]:
        state = json_load(self.bot_state_path, {})
        if not state:
            self.ensure_default_bot_state()
            state = json_load(self.bot_state_path, {})
        changed = False
        if str(state.get("runtime_engine") or "").strip().lower() not in {self._runtime_engine_real, self._runtime_engine_simulated}:
            state["runtime_engine"] = self._runtime_engine_default()
            changed = True
        if str(state.get("runtime_contract_version") or "").strip() != self._runtime_contract_version:
            state["runtime_contract_version"] = self._runtime_contract_version
            changed = True
        telemetry_source = str(state.get("runtime_telemetry_source") or "").strip().lower()
        if telemetry_source not in {self._runtime_telemetry_source_synthetic, self._runtime_telemetry_source_real}:
            state["runtime_telemetry_source"] = self._runtime_telemetry_source_synthetic
            changed = True
        for key in (
            "runtime_loop_alive",
            "runtime_executor_connected",
            "runtime_reconciliation_ok",
            "runtime_operational_safety_ok",
            "runtime_unknown_timeout_active",
            "runtime_exchange_connector_ok",
            "runtime_exchange_order_ok",
            "runtime_account_surface_ok",
            "runtime_account_can_trade",
        ):
            if key not in state or not isinstance(state.get(key), bool):
                state[key] = bool(state.get(key, False))
                changed = True
        for key in (
            "runtime_heartbeat_at",
            "runtime_last_reconcile_at",
            "runtime_last_safety_eval_at",
            "runtime_operational_safety_status",
            "runtime_unknown_timeout_since",
            "runtime_exchange_verified_at",
            "runtime_exchange_mode",
            "runtime_exchange_reason",
            "runtime_account_surface_verified_at",
            "runtime_account_surface_reason",
            "runtime_last_signal_action",
            "runtime_last_signal_reason",
            "runtime_last_signal_strategy_id",
            "runtime_last_signal_symbol",
            "runtime_last_signal_side",
        ):
            if key not in state:
                state[key] = ""
                changed = True
        if "runtime_account_permissions" not in state or not isinstance(state.get("runtime_account_permissions"), list):
            state["runtime_account_permissions"] = list(state.get("runtime_account_permissions") or [])
            changed = True
        try:
            balances_count = int(state.get("runtime_account_balances_count", 0))
        except (TypeError, ValueError):
            balances_count = 0
        if state.get("runtime_account_balances_count") != balances_count:
            state["runtime_account_balances_count"] = balances_count
            changed = True
        if changed:
            json_save(self.bot_state_path, state)
        return state

    def save_bot_state(self, state: dict[str, Any]) -> None:
        payload = state if isinstance(state, dict) else {}
        payload["last_heartbeat"] = utc_now_iso()
        json_save(self.bot_state_path, payload)

    def load_bot_rows(self) -> list[dict[str, Any]]:
        payload = json_load(self.bots_path, [])
        if not isinstance(payload, list):
            return []
        return payload

    def save_bot_rows(self, rows: list[dict[str, Any]]) -> None:
        json_save(self.bots_path, rows if isinstance(rows, list) else [])
