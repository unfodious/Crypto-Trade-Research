# Advanced Framework Feasibility

Review date: 2026-05-25

Verdict: do not adopt any advanced framework as the primary pipeline yet. The current pipeline now
has reproducible data ingestion, feature generation, leakage-safe labels, walk-forward evaluation,
baseline comparison, meta-strategy filtering, model registry, inference contract, and promotion
gates. Advanced tools should only enter as adapters or benchmarks when they improve that loop.

## Recommendation Matrix

| Candidate | Verdict | Why | Integration cost |
| --- | --- | --- | --- |
| vectorbt | Use later | Useful for fast parameter grids and signal/backtest experiments. It should not replace the CT-40 walk-forward evaluator until parity tests prove fees, slippage, funding, and rejection reasons match. | Medium: data adapter, cost model parity, walk-forward wrapper, report comparison. |
| Qlib | Use later | Strong quant research platform with supervised, market-dynamics, and RL workflows, but it brings its own data/workflow assumptions. Better as a later experiment once our dataset adapter is stable. | High: crypto/perpetual futures dataset adapter, custom execution assumptions, workflow mapping, reproducibility bridge. |
| NeuralForecast | Use later | Good candidate for deep supervised sequence baselines after linear/tree baselines plateau. Keep outputs as features or estimates, not direct orders. | Medium: panel dataset adapter, rolling windows, calibration, registry/export mapping. |
| PyTorch Forecasting | Use later | Flexible PyTorch sequence modeling for Temporal Fusion Transformer-style experiments. Useful only after supervised benchmark protocol is fixed. | Medium-high: dataset construction, GPU/CPU reproducibility, training config tracking. |
| Darts | Benchmark only | Broad forecasting toolbox with consistent `fit`/`predict`, backtesting, and covariates. Good for quick forecasting baselines, less ideal as core trading evaluation. | Low-medium: adapter for candles/features and metric export. |
| Chronos | Benchmark only | Pretrained forecasting models can be tested as zero-shot/feature-generator baselines. Treat forecasts as research features, not trade decisions. | Medium: dependency/runtime cost, horizon mapping, calibration, leakage audit. |
| TimesFM | Benchmark only | Current TimesFM versions are active and support longer-context forecasting. Useful as a benchmark or feature generator, not a core trading engine. | Medium: dependency/runtime cost, covariate mapping, calibration, reproducibility capture. |
| Stable-Baselines3 | Use later | Mature RL toolkit, but only after a realistic exchange environment, costs, funding, latency, and action constraints exist. | High: Gymnasium environment, reward shaping, offline evaluation, safety constraints. |
| FinRL | Reject now | Useful educational RL framework, but stock-market defaults and RL focus are premature for this crypto pipeline. | High: environment rewrite and risk of optimizing simulator artifacts. |
| TensorTrade-NG | Reject now | Useful for RL environment experiments and interoperates with RL libraries, but RL is out of scope until fake/paper environments are trustworthy. | High: environment design, maintenance review, cost/funding/reconciliation modeling. |

## Adoption Rules

No framework is adopted unless it satisfies all of these:

- consumes our versioned dataset and feature/label manifests without look-ahead leakage
- supports crypto/perpetual futures fees, slippage, funding, and unavailable-data rules
- runs walk-forward evaluation or can be wrapped by our walk-forward evaluator
- writes experiment registry records and promotion gate evidence
- keeps model outputs inside the `ml-inference.v1` take/skip contract
- does not force a production runtime architecture

## Suggested Order

1. Add vectorbt parity spike for fast parameter sweeps against CT-40 outputs.
2. Add Darts or NeuralForecast benchmark for sequence forecasting features.
3. Add TimesFM/Chronos zero-shot benchmark only if forecasting targets show value over simple
   baselines.
4. Consider Qlib only after dataset adapters and model registry mapping are stable.
5. Defer RL frameworks until a realistic fake executor and paper-trading environment exists.

## Sources Checked

- Qlib GitHub: https://github.com/microsoft/qlib
- vectorbt resources: https://vectorbt.dev/getting-started/resources/
- TensorTrade-NG docs: https://tensortrade-ng.io/agents/overview.html
- Darts GitHub: https://github.com/unit8co/darts
- Stable-Baselines3 docs: https://sb3-contrib.readthedocs.io/
- TimesFM GitHub: https://github.com/google-research/timesfm
- Chronos GitHub: https://github.com/amazon-science/chronos-forecasting
- PyTorch Forecasting GitHub: https://github.com/sktime/pytorch-forecasting
