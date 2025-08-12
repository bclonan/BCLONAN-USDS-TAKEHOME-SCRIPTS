"""Analyzer plugin for advanced regulatory metrics.

Two pipeline steps (minimal initial implementation):
  - analyze_ingest: load normalized section artifacts into analyzer SQLite DB
  - analyze_metrics: compute primitive metrics over ingested sections

The FastAPI router (api.py) is conditionally mounted by pipeline.apiserve
if import succeeds and analyzer DB exists.
"""
from __future__ import annotations

__all__ = [
    "ingest",
    "metrics",
    "api",
    "schema",
]

from . import ingest, metrics, api, schema  # noqa: E402,F401
