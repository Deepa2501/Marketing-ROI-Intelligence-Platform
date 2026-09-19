"""
Forecasting & Future Outlook service layer (Phase 11).

This is a deliberately simple, fully-explainable statistical approach
(monthly aggregation + linear trend on the recent period), NOT a
black-box ML model. It reuses backend.services.intelligence_service's
monthly aggregation helper for the historical time series wherever
possible, and reuses data_service's cached dataframe — no new CSV
loading.

Every forecast is explicitly labeled a "directional outlook" / an
"estimated forecast", never a guaranteed prediction. If there isn't
enough history to say anything meaningful, the service returns a
graceful "insufficient history" result instead of fabricating one.

============================================================
DOCUMENTED METHOD (read this before touching the numbers)
============================================================
1. Monthly aggregation: campaigns are grouped by calendar month
   (Date -> YYYY-MM) and summed/averaged per the existing
   intelligence_service.get_trends() definitions.
2. Recent-period trend: rather than fitting a line across the WHOLE
   historical series (which can blend distinct volume regimes and
   produce a misleadingly flat slope), the trend/slope used for both
   direction classification and the 3-month outlook is fit on the
   most recent RECENT_WINDOW_MONTHS months only (default 6, or fewer
   if less history exists) via ordinary least squares (numpy.polyfit,
   degree 1). This is documented explicitly in the API response's
   "methodology" block.
3. Trend direction: the fitted slope is expressed as a percentage of
   the recent-window mean, per month. If the absolute value of that
   percentage is below STABLE_TOLERANCE_PCT (1.5%), the metric is
   classified STABLE; otherwise UP or DOWN by the sign of the slope.
4. 3-month outlook: the same recent-window linear fit is extrapolated
   3 further monthly steps. These are labeled "estimated forecast"
   values, not guarantees.
5. Evidence strength: HIGH / MEDIUM / LOW, based on (a) total months
   of history available, (b) how well the recent-window line actually
   fits the recent data (R²), and (c) the recent window's volatility
   (coefficient of variation = std / mean). See _evidence_strength().
6. Backtest: the full historical series (minus the last
   BACKTEST_HOLDOUT_MONTHS months) is used to fit a line, which is
   then used to "predict" the held-out months; MAE/RMSE against the
   actual held-out values are reported. This measures how well THIS
   SIMPLE METHOD performed historically — it is not a claim about
   future accuracy.
"""

import math

import numpy as np
import pandas as pd

from backend.services import intelligence_service as ins

RECENT_WINDOW_MONTHS = 6
FORECAST_HORIZON_MONTHS = 3
BACKTEST_HOLDOUT_MONTHS = 3
MIN_MONTHS_FOR_TREND = 3
MIN_MONTHS_FOR_BACKTEST = 6  # needs at least 3 training + 3 held-out months

# Trend classification tolerance: a recent-window slope smaller than
# this, expressed as % of the recent-window mean per month, is
# classified STABLE rather than UP/DOWN. Documented, not arbitrary —
# chosen as a round number comfortably above typical month-to-month
# noise seen in a low-volatility metric, while still catching a
# clearly sustained multi-month drift.
STABLE_TOLERANCE_PCT = 1.5

METRICS = {
    "Revenue": "total_revenue",
    "ROI": "average_roi",
    "Conversions": "total_conversions",
}


def _safe_round(value, ndigits=4):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return round(float(value), ndigits)


def _linear_fit(values):
    """OLS linear fit on a 1-D array. Returns (slope, intercept, r2)."""
    y = np.asarray(values, dtype=float)
    x = np.arange(len(y))
    if len(y) < 2 or np.all(y == y[0]):
        return 0.0, float(y[0]) if len(y) else 0.0, 0.0
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = np.sum((y - pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return float(slope), float(intercept), float(r2)


def _classify_direction(slope, mean_value):
    if not mean_value:
        return "STABLE"
    relative_pct = (slope / mean_value) * 100
    if abs(relative_pct) < STABLE_TOLERANCE_PCT:
        return "STABLE"
    return "UP" if relative_pct > 0 else "DOWN"


def _evidence_strength(total_months, recent_r2, recent_cv):
    """Transparent, documented evidence-strength classification.

    HIGH:   >=12 months of history AND the recent-window line fits
            reasonably well (R² >= 0.5) AND the recent window is
            fairly stable (CV < 0.25).
    MEDIUM: >=6 months of history AND (R² >= 0.2 OR CV < 0.4), and
            not already HIGH.
    LOW:    everything else (short history, poor line fit, or high
            volatility).
    """
    if total_months >= 12 and recent_r2 >= 0.5 and recent_cv < 0.25:
        return "HIGH"
    if total_months >= 6 and (recent_r2 >= 0.2 or recent_cv < 0.4):
        return "MEDIUM"
    return "LOW"


def _next_periods(last_period_str, n):
    """Given the last 'YYYY-MM' period label, return the next n
    'YYYY-MM' labels in sequence.
    """
    last = pd.Period(last_period_str, freq="M")
    return [(last + i).strftime("%Y-%m") for i in range(1, n + 1)]


def _get_monthly_series(df):
    """Reuses intelligence_service.get_trends() for the shared metrics
    (Revenue, ROI, Conversions, Engagement), and adds Acquisition Cost
    with the same grouping approach for completeness, since
    get_trends() doesn't already compute it.
    """
    trends = ins.get_trends(df)
    points = trends.get("points", [])
    if not points:
        return [], trends.get("note")

    if "Acquisition_Cost" in df.columns and "Date" in df.columns:
        working = df.copy()
        working["_parsed_date"] = pd.to_datetime(working["Date"], errors="coerce")
        working = working.dropna(subset=["_parsed_date"])
        working["_period"] = working["_parsed_date"].dt.to_period("M").astype(str)
        cost_by_period = working.groupby("_period")["Acquisition_Cost"].mean().to_dict()
        for p in points:
            p["average_acquisition_cost"] = _safe_round(cost_by_period.get(p["period"]), 2)

    return points, None


def _build_metric_forecast(metric_label, field, points):
    """Builds the historical + forecast + trend-direction + evidence
    package for a single metric.
    """
    values = [p[field] for p in points if p.get(field) is not None]
    periods = [p["period"] for p in points if p.get(field) is not None]

    if len(values) < MIN_MONTHS_FOR_TREND:
        return {
            "metric": metric_label,
            "status": "insufficient_history",
            "message": (
                f"Only {len(values)} monthly observation(s) available; at least "
                f"{MIN_MONTHS_FOR_TREND} are needed for a directional outlook."
            ),
            "historical_values": [{"period": p, "value": _safe_round(v, 4)} for p, v in zip(periods, values)],
            "forecast_values": [],
            "trend_direction": None,
            "method": None,
            "evidence_strength": "LOW",
            "caveat": "Insufficient historical data to generate a directional outlook.",
        }

    recent_n = min(RECENT_WINDOW_MONTHS, len(values))
    recent_values = np.array(values[-recent_n:], dtype=float)

    slope, intercept, r2 = _linear_fit(recent_values)
    mean_recent = float(recent_values.mean())
    cv = float(recent_values.std() / mean_recent) if mean_recent else 0.0

    direction = _classify_direction(slope, mean_recent)
    evidence = _evidence_strength(len(values), r2, cv)

    forecast_periods = _next_periods(periods[-1], FORECAST_HORIZON_MONTHS)
    forecast_x = np.arange(recent_n, recent_n + FORECAST_HORIZON_MONTHS)
    forecast_raw = slope * forecast_x + intercept
    # Revenue/Conversions can't sensibly go negative; ROI can.
    if field != "average_roi":
        forecast_raw = np.clip(forecast_raw, 0, None)

    forecast_values = [
        {"period": p, "estimated_value": _safe_round(v, 4)} for p, v in zip(forecast_periods, forecast_raw)
    ]

    return {
        "metric": metric_label,
        "status": "ok",
        "historical_values": [{"period": p, "value": _safe_round(v, 4)} for p, v in zip(periods, values)],
        "forecast_values": forecast_values,
        "trend_direction": direction,
        "method": f"Linear trend fit on the most recent {recent_n} month(s), extrapolated {FORECAST_HORIZON_MONTHS} months forward.",
        "evidence_strength": evidence,
        "recent_window_months": recent_n,
        "recent_window_r2": _safe_round(r2, 4),
        "recent_window_coefficient_of_variation": _safe_round(cv, 4),
        "caveat": (
            "This is a directional, estimated outlook based on a simple recent-trend extrapolation — "
            "not a guaranteed forecast. Historical patterns may not continue."
        ),
    }


def get_backtest(points, field):
    """Trains a linear fit on all months except the last
    BACKTEST_HOLDOUT_MONTHS, predicts those held-out months, and
    reports MAE/RMSE against the actual values.
    """
    values = [p[field] for p in points if p.get(field) is not None]
    periods = [p["period"] for p in points if p.get(field) is not None]

    if len(values) < MIN_MONTHS_FOR_BACKTEST:
        return {
            "status": "unavailable",
            "message": f"At least {MIN_MONTHS_FOR_BACKTEST} monthly observations are needed to run a backtest.",
        }

    train = np.array(values[:-BACKTEST_HOLDOUT_MONTHS], dtype=float)
    test = np.array(values[-BACKTEST_HOLDOUT_MONTHS:], dtype=float)
    test_periods = periods[-BACKTEST_HOLDOUT_MONTHS:]

    slope, intercept, _ = _linear_fit(train)
    x_test = np.arange(len(train), len(train) + BACKTEST_HOLDOUT_MONTHS)
    predicted = slope * x_test + intercept

    mae = float(np.mean(np.abs(predicted - test)))
    rmse = float(np.sqrt(np.mean((predicted - test) ** 2)))
    mean_actual = float(test.mean())
    mae_pct_of_mean = _safe_round(100 * mae / mean_actual, 2) if mean_actual else None

    if mae_pct_of_mean is None:
        interpretation = "Backtest could not be interpreted relative to the held-out period's mean value."
    elif mae_pct_of_mean < 15:
        interpretation = "The simple trend method's historical error was relatively small on this holdout period."
    elif mae_pct_of_mean < 50:
        interpretation = "The simple trend method's historical error was moderate on this holdout period."
    else:
        interpretation = (
            "The simple trend method's historical error was large on this holdout period — the metric likely "
            "shifted between distinct periods that a straight-line trend does not capture well."
        )

    return {
        "status": "ok",
        "mae": _safe_round(mae, 4),
        "rmse": _safe_round(rmse, 4),
        "mae_pct_of_holdout_mean": mae_pct_of_mean,
        "test_period": f"{test_periods[0]} to {test_periods[-1]}",
        "training_months": len(train),
        "interpretation": interpretation,
        "note": "This backtest evaluates how the simple forecasting method performed on historical holdout data. It does not guarantee future accuracy.",
    }


def get_trend_summary(forecasts):
    """Flat table-ready summary for the frontend's Trend Intelligence section."""
    summary = []
    for f in forecasts:
        if f["status"] != "ok":
            summary.append(
                {
                    "metric": f["metric"],
                    "direction": None,
                    "evidence_strength": f.get("evidence_strength", "LOW"),
                    "interpretation": f.get("message", "Insufficient data."),
                }
            )
            continue

        direction = f["trend_direction"]
        phrase = {
            "UP": f"{f['metric']} shows an upward recent trend across the historical monthly series.",
            "DOWN": f"{f['metric']} shows a downward recent trend across the historical monthly series.",
            "STABLE": f"{f['metric']} has been broadly stable across the recent historical monthly series.",
        }.get(direction, "Trend not available.")

        summary.append(
            {
                "metric": f["metric"],
                "direction": direction,
                "evidence_strength": f["evidence_strength"],
                "interpretation": phrase,
            }
        )
    return summary


def get_future_outlook_signals(forecasts, backtests):
    """3-5 dynamic, evidence-tagged insights. Every OBSERVED item comes
    from the historical series; every PREDICTIVE item comes from the
    forecast/backtest results above — never blended.
    """
    signals = []

    for f in forecasts:
        if f["status"] != "ok":
            continue
        metric = f["metric"]
        direction = f["trend_direction"]
        direction_phrase = {
            "UP": "trending up",
            "DOWN": "trending down",
            "STABLE": "stable",
        }.get(direction, "unclear")
        signals.append(
            {
                "title": f"{metric} Momentum",
                "interpretation": (
                    f"Directional outlook suggests {metric.lower()} is {direction_phrase} based on the "
                    f"most recent {f['recent_window_months']} months of data."
                ),
                "evidence_basis": "PREDICTIVE",
                "caution": f["caveat"],
            }
        )

    volatile = [f for f in forecasts if f["status"] == "ok" and f.get("recent_window_coefficient_of_variation", 0) and f["recent_window_coefficient_of_variation"] > 0.3]
    if volatile:
        v = volatile[0]
        signals.append(
            {
                "title": f"{v['metric']} Volatility",
                "interpretation": (
                    f"{v['metric']} has shown relatively high month-to-month variability in the recent period "
                    f"(coefficient of variation = {v['recent_window_coefficient_of_variation']})."
                ),
                "evidence_basis": "OBSERVED",
                "caution": "High volatility reduces confidence in any short-term directional outlook for this metric.",
            }
        )

    for bt_name, bt in backtests.items():
        if bt.get("status") == "ok" and bt.get("mae_pct_of_holdout_mean") is not None and bt["mae_pct_of_holdout_mean"] > 50:
            signals.append(
                {
                    "title": f"{bt_name} Trend Inconsistency",
                    "interpretation": (
                        f"The simple trend method's historical backtest for {bt_name.lower()} showed a large error "
                        f"({bt['mae_pct_of_holdout_mean']}% of the holdout period's mean), suggesting the recent "
                        "trend line does not reliably explain past shifts in this metric."
                    ),
                    "evidence_basis": "OBSERVED",
                    "caution": "Treat the directional outlook for this metric with extra caution.",
                }
            )
            break

    return signals[:5]


def get_forecast_summary(df):
    """Top-level entry point. Validates the Date column, builds the
    monthly series, then the per-metric forecasts, backtests, trend
    summary, and outlook signals.
    """
    if df.empty:
        return {
            "status": "insufficient_history",
            "message": "No campaign data available.",
        }
    if "Date" not in df.columns:
        return {
            "status": "insufficient_history",
            "message": "Date column not found in the connected dataset; cannot build a time series.",
        }

    points, note = _get_monthly_series(df)
    if not points:
        return {
            "status": "insufficient_history",
            "message": note or "Not enough valid, date-parseable monthly observations were found.",
        }

    forecasts = [_build_metric_forecast(label, field, points) for label, field in METRICS.items()]
    backtests = {label: get_backtest(points, field) for label, field in METRICS.items()}

    return {
        "status": "success",
        "historical": {
            "months_available": len(points),
            "period_range": f"{points[0]['period']} to {points[-1]['period']}" if points else None,
            "points": points,
        },
        "forecasts": forecasts,
        "trend_summary": get_trend_summary(forecasts),
        "backtest": backtests,
        "outlook_signals": get_future_outlook_signals(forecasts, backtests),
        "methodology": {
            "steps": [
                "Campaign data is aggregated monthly.",
                "Historical trends are calculated from the monthly series.",
                f"A recent trend/slope is estimated using ordinary least-squares regression on the most recent {RECENT_WINDOW_MONTHS} months (or fewer if less history exists).",
                f"A limited {FORECAST_HORIZON_MONTHS}-month directional outlook is generated by extrapolating that recent trend.",
                f"Historical holdout testing (backtest) is used where at least {MIN_MONTHS_FOR_BACKTEST} months of history exist.",
            ],
            "trend_classification": f"A recent-window slope smaller than {STABLE_TOLERANCE_PCT}% of the recent-window mean per month is classified STABLE; otherwise UP or DOWN by the sign of the slope.",
            "evidence_strength_logic": "HIGH requires >=12 months of history, a well-fitting recent trend line (R² >= 0.5), and low volatility (CV < 0.25). MEDIUM requires >=6 months and either a reasonable fit (R² >= 0.2) or moderate volatility (CV < 0.4). Otherwise LOW.",
            "forecast_horizon": f"Next {FORECAST_HORIZON_MONTHS} months",
        },
        "limitations": [
            "Forecasts are directional estimates, not guaranteed outcomes.",
            "Historical patterns may not continue.",
            "Marketing campaigns can be affected by seasonality, market conditions, pricing, competition, and external events not captured in this dataset.",
            "High volatility reduces forecast reliability.",
            "Short historical series should be treated cautiously.",
            "Forecasts do not establish causality.",
            "Forecasts should support decisions, not replace business judgment.",
        ],
    }
