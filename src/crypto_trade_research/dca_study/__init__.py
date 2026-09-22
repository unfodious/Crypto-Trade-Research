"""Execution-timing study for long-horizon spot dollar-cost averaging.

This module does not predict direction. Two prior studies
(`docs/research/strategy-audit-2026-09-21.md`,
`docs/research/edge-study-4h-2026-09-22.md`) found no predictive edge on these
assets, and nothing here contradicts that. The question asked here is much
weaker: given that a fixed amount of money *is* going to be spent on spot every
month, does the calendar on which it is spent change the cost basis by an
amount that is large relative to the noise?

Research only. There is no exchange client, no credential and no order path in
this package.
"""

from __future__ import annotations

__all__ = ["data", "schedules", "metrics", "study"]
