"""
Data service layer for the Marketing ROI Intelligence Platform.

Responsible for locating and loading the existing cleaned dataset at
data/cleaned/marketing_campaign_cleaned.csv. This service does NOT copy,
duplicate, or modify that file. It loads it once and caches the result
in memory for reuse across API calls (Section 15 / 16 of the spec).

Phase 1 scope: connection status only. Real aggregation logic
(EDA figures, correlations, A/B test results, etc.) is added in later
phases once the analytics endpoints are built.
"""

import os
import threading
from typing import Optional

import pandas as pd

_lock = threading.Lock()
_cache: dict = {"df": None, "loaded": False, "error": None}

EXPECTED_COLUMNS = [
    "Campaign_ID",
    "Campaign_Type",
    "Target_Audience",
    "Duration",
    "Channel_Used",
    "Impressions",
    "Clicks",
    "Leads",
    "Conversions",
    "Revenue",
    "Acquisition_Cost",
    "ROI",
    "Language",
    "Engagement_Score",
    "Customer_Segment",
    "Date",
]


def get_dataframe(data_path: str) -> Optional[pd.DataFrame]:
    """Return the cached dataframe, loading it once from disk if available.

    Returns None if the dataset has not been connected yet (e.g. the
    repository's data/cleaned/marketing_campaign_cleaned.csv is not
    present in this environment). Callers must not fabricate data when
    this returns None.
    """
    with _lock:
        if _cache["loaded"]:
            return _cache["df"]

        if not os.path.exists(data_path):
            _cache["loaded"] = True
            _cache["df"] = None
            _cache["error"] = "dataset_not_found"
            return None

        try:
            df = pd.read_csv(data_path)
            _cache["df"] = df
            _cache["loaded"] = True
            _cache["error"] = None
            return df
        except Exception as exc:  # noqa: BLE001 — surfaced via status, not raised to client
            _cache["loaded"] = True
            _cache["df"] = None
            _cache["error"] = f"load_error: {exc.__class__.__name__}"
            return None


def get_connection_status(data_path: str) -> dict:
    """Report dataset connection status without exposing filesystem paths
    or computing/inventing any business metrics.
    """
    df = get_dataframe(data_path)

    if df is None:
        return {
            "connected": False,
            "reason": _cache["error"] or "dataset_not_found",
            "message": "Dataset connection pending.",
        }

    missing_cols = [c for c in EXPECTED_COLUMNS if c not in df.columns]

    return {
        "connected": True,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "schema_matches_expected": len(missing_cols) == 0,
        "missing_expected_columns": missing_cols,
    }


def reset_cache() -> None:
    """Utility for tests: clear the in-memory cache."""
    with _lock:
        _cache["df"] = None
        _cache["loaded"] = False
        _cache["error"] = None


class DatasetUnavailableError(Exception):
    """Raised by service functions when the dataset has not been
    connected yet. Routes catch this and return a clear 503 rather
    than a stack trace.
    """


def require_dataframe(data_path: str) -> pd.DataFrame:
    """Return the cached dataframe or raise DatasetUnavailableError.

    Analytics/statistics/A-B-test services call this instead of
    get_dataframe directly so every route gets consistent error
    handling without repeating the None-check everywhere.
    """
    df = get_dataframe(data_path)
    if df is None:
        raise DatasetUnavailableError(
            "Dataset connection pending: "
            "data/cleaned/marketing_campaign_cleaned.csv was not found or could not be loaded."
        )
    return df
