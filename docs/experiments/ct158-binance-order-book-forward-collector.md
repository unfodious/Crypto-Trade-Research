# CT-158 Binance Order-Book Depth Forward Collector

Date: 2026-05-27

Issue: CT-158

Epic: CT-113

Status: research-only collector, not a trading model

## Objective

Test whether the "unusual large visible orders at unusual prices" idea can become usable
point-in-time evidence for CT-113. Historical Binance USD-M depth is not available through the
current public REST endpoint, so this issue creates a forward collector instead of backfilling a
backtest dataset.

## Data Source

- Source: Binance USD-M Futures public REST `GET /fapi/v1/depth`
- Official endpoint checked on 2026-05-27:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Order-Book>
- Config: `configs/ct158-binance-order-book-forward-snapshot.json`
- Runner: `scripts/run_ct158_binance_order_book_snapshot_once.sh`
- Output prefix: `data/generated/ct158_binance_order_book_forward`
- Universe: `SOLUSDT`, `SUIUSDT`, `AVAXUSDT`, `ADAUSDT`, `ICPUSDT`, `ATOMUSDT`, `XRPUSDT`,
  `TONUSDT`, `DOTUSDT`, `BTCUSDT`, `ETHUSDT`
- Depth limit: 20 levels per side

Expected healthy one-shot count for the 11-symbol universe:

- summary rows: 11
- level rows: 440
- total rows: 451

## Schema

Each run writes:

- `clean/order_book_summary.parquet`
- `clean/order_book_levels.parquet`
- `manifest.json`
- latest compact run summary at
  `data/generated/ct158_binance_order_book_forward/order_book_run.json`

Summary fields include best bid/ask, mid price, spread bps, bid/ask quantity and notional totals,
quantity and notional imbalance, largest visible bid/ask level notional, and distance from mid.

Level fields include side, level index, price, quantity, notional, mid price, and distance from mid.

## Research Notes

This is visible resting liquidity only. A single large level can be cancelled or spoofed, so it
should not be used directly as a trade trigger. The useful future signal is likely persistence and
change over repeated snapshots:

- large level appears and stays for multiple snapshots;
- imbalance persists near the current price;
- price reacts after the imbalance rather than before it;
- signal improves CT-145/CT-156 paper streams without increasing drawdown.

This collector does not place, cancel, resize, or authorize orders. It uses only public REST reads.

## Validation Plan

1. Run the collector locally and on the droplet.
2. Monitor for 30+ days with the same forward-only discipline as CT-151/CT-153.
3. Build derived features only after enough snapshots exist:
   - persistent bid/ask wall notional;
   - wall distance buckets;
   - order-book notional imbalance;
   - imbalance changes over 5m/15m windows;
   - relationship to CT-145/CT-156 candidate decisions.
4. Reject the branch if snapshots are too noisy, too sparse, rate-limited, or fail to improve
   forward paper evidence after costs.

## Initial Decision

CT-158 is a data-expansion task, not a candidate promotion. It keeps CT-113 open and creates the
missing point-in-time external dataset required before testing the large-order hypothesis.

## Initial Smoke Result

Local one-shot on 2026-05-27 wrote:

- manifest:
  `data/generated/ct158_binance_order_book_forward_20260527T135342Z/manifest.json`
- row count: 451
- summary rows: 11
- level rows: 440
- warnings: none

Droplet one-shot on 2026-05-27 wrote:

- manifest:
  `data/generated/ct158_binance_order_book_forward_20260527T135455Z/manifest.json`
- row count: 451
- summary rows: 11
- level rows: 440
- warnings: none

Droplet deployment:

- service: `ct158-binance-order-book-snapshot.service`
- timer: `ct158-binance-order-book-snapshot.timer`
- cadence: every 5 minutes with randomized delay
- first systemd run: `Result=success`, `ExecMainStatus=0`
- timer state: `active/waiting`
- monitoring issue: CT-159
- daily local automation: `ct-159-order-book-daily-check`
