# CT-166 Forward Funding Decimal Feature Fix

Date: 2026-05-27

Issue: CT-166

Epic: CT-113

## Finding

CT-145 and CT-156 forward-paper streams were producing zero candidates. The immediate cause was not
only market scarcity:

- `paper_forward` normalizes live Binance funding rows as `Decimal`;
- feature generation accepted only `int` and `float` in `_number()`;
- therefore `funding_rate` and `funding_rate_zscore_20` became `None`;
- the first funding filters in both packs rejected every row.

## Fix

Feature generation now treats `Decimal` as numeric. A regression test verifies that Decimal funding
rows populate:

- `funding_rate`;
- `funding_rate_zscore_N`;
- `funding_rate_abs`;
- `funding_rate_positive`.

## Local Smoke

After the fix, CT-145 and CT-156 one-shots populated funding fields for all 11 latest feature rows:

- funding non-null rows: 11 / 11
- funding z-score non-null rows: 11 / 11

The current market window still produced zero paper candidates. That is now interpreted as actual
filter scarcity rather than missing funding data.

## Safety

This change affects research feature generation only. It does not place orders, change live runtime
trading, alter leverage, stops, or approve live trading.
