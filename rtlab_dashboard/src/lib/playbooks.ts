const playbooks: Record<string, string> = {
  "trend-pullback": `Trend + pullback with microstructure confirmation.
- Regime filter on higher timeframe trend.
- Entry on pullback into dynamic support/resistance.
- Orderflow checks: OBI/CVD/VPIN gate before submit.
- Cost-aware execution and spread guard.`,
  "mean-reversion": `Mean-reversion with volatility and liquidity guardrails.
- Detect extreme deviations from rolling mean.
- Confirm reversion setup only in non-trending regime.
- Tight invalidation and time-stop enforcement.
- Position sizing scaled by drawdown state.`,
  momentum: `Cross-sectional momentum with turnover control.
- Rank symbols by recent risk-adjusted momentum.
- Enter top decile under spread/volume constraints.
- Dynamic exits with trailing and volatility scaling.
- Stress-tested under fee/slippage shocks.`,
};

export function getPlaybook(strategyName: string) {
  return playbooks[strategyName] || "No playbook available.";
}

