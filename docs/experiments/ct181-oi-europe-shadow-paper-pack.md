# CT-181 OI/Europe Shadow Paper Pack

Status: shadow paper pack prepared; no live approval.

CT-180 promoted the `oi_high_or_europe` refinement to paper-trading/shadow candidate planning. CT-181
turns that research decision into a forward-paper pack and runner.

This remains research-only. It can log signals, paper skips, and paper fills. It must not place,
cancel, size, or modify live orders.

## Candidate

Pack:

- `ct180_oi_europe_shadow_paper_pack`
- candidate: `ct180_oi_high_or_europe`
- base model artifact: CT-144 no-TON negative-funding expected-R model
- entry family: CT-145/CT-144 five-symbol no-TON long setup

Candidate entry symbols:

- `SOLUSDT`
- `SUIUSDT`
- `AVAXUSDT`
- `ADAUSDT`
- `ICPUSDT`

Context symbols still include the full CT-113 universe so BTC/ETH and breadth features remain
available.

## Rule

The pack keeps the CT-145 entry filters and ranking:

- `funding_rate <= -0.00002`
- `funding_rate_zscore_20 <= -0.25`
- `close_location >= 0.45`
- `risk_on_score_20 >= 0.35`
- `mtf_5m_risk_on_score_20 >= 0.35`
- expected-R ridge ranking
- top `3` per decision time
- selected expected-R threshold `-0.20`
- selected probability threshold `0.55`

CT-181 adds the CT-180 abstention layer:

- skip if `fm_oi_value_change_1h > 0.015`;
- skip if `fm_session_europe >= 1`, where Europe is `08:00 <= UTC hour < 16:00`;
- fail closed if required abstention features are missing.

The open-interest feature uses Binance USD-M Futures Open Interest Statistics,
`GET /futures/data/openInterestHist`, with `period=5m`. Binance documents the returned
`sumOpenInterestValue` field and notes that only the latest one month is available through the REST
endpoint: <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics>.

## Implementation

Added pack and forward configs:

- `configs/ct180-oi-europe-shadow-paper-pack.json`
- `configs/ct180-oi-europe-forward-paper-run.json`

Added runner:

- `scripts/run_ct180_forward_paper_once.sh`

Updated the paper forward path:

- fetches fresh public USD-M klines and funding as before;
- fetches public USD-M open-interest history only when a pack requires `fm_*` abstention features;
- adds `fm_session_asia`, `fm_session_europe`, `fm_session_us`;
- adds `fm_sum_open_interest_value`, `fm_metrics_age_minutes`, and `fm_oi_value_change_1h`.

Updated the paper collector:

- supports `strategy.abstention_filters` and `strategy.abstention_filter_groups`;
- applies abstention after model scoring/ranking and before paper ledger creation;
- records abstention details in the `ml-inference.v1` signal payload;
- blocks otherwise valid takes if abstention features are missing.

## Local Fresh Tick

Command:

```sh
.venv/bin/python -m crypto_trade_research.paper_trading \
  --config configs/ct180-oi-europe-shadow-paper-pack.json

.venv/bin/python -m crypto_trade_research.paper_forward \
  --config configs/ct180-oi-europe-forward-paper-run.json
```

Result:

| Field | Value |
| --- | ---: |
| decision time | `2026-05-30T07:55:00Z` |
| candle rows | `4,631` |
| funding rows | `300` |
| futures metrics rows | `396` |
| latest feature rows | `11` |
| candidate count | `0` |
| signal count | `0` |
| paper takes | `0` |
| cumulative trades | `0` |
| monitoring status | `gate_failed` |

This is a valid no-trade state for a single fresh tick. It only means the current public market
snapshot did not pass the entry filters. It is not a rejection of CT-180.

Generated artifacts:

- `data/generated/ct180_oi_europe_shadow_paper_pack/pack_manifest.json`
- `data/generated/ct180_oi_europe_shadow_forward_paper/forward_run.json`
- `data/generated/ct180_oi_europe_shadow_forward_paper/monitoring_report.json`

Generated artifacts are not committed.

## Droplet Plan

Run the CT-180 stream as a separate hourly shadow timer, not as a replacement for existing streams.

Suggested units:

- `ct180-forward-paper.service`
- `ct180-forward-paper.timer`

The service command should be:

```sh
/opt/crypto-trade-research/scripts/run_ct180_forward_paper_once.sh
```

The droplet needs only public Binance REST access. No Binance account keys are required.

## Gate

Before any live-trading discussion:

- run at least `30` calendar days;
- collect at least `100` closed paper trades;
- average R after costs must stay positive;
- max simulated drawdown must stay under `8%`;
- symbol breadth must remain at least `50%` positive;
- session breadth must remain at least `50%` positive;
- no Europe-session trade may be taken;
- no `fm_oi_value_change_1h > 0.015` trade may be taken;
- missing OI metrics for a selected candidate must produce a skip.

## Safety Boundary

No live trading approval.

No working-model claim.

No order placement, cancellation, leverage, margin, sizing, or runtime trade-state writes.

The pack manifest keeps `live_order_authority=false` and the forward runner only writes generated
research artifacts.
