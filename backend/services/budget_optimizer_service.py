"""
Budget Allocation Optimizer service layer (Phase 13).

A transparent, fully-documented DECISION-SUPPORT tool. It is NOT causal
optimization, NOT a guarantee of future ROI, and NOT an automated
budget deployment system. Every number is derived from observed
historical data in the connected dataset; every estimate is explicitly
labeled illustrative.

This module is READ-ONLY with respect to the dataset — it never
mutates, filters-in-place, or writes back to the cached dataframe
(all groupby/aggregation operations return new objects).

Reuses analytics_service / campaign_analytics_service group
aggregations where they already exist, rather than recomputing them.

============================================================
DOCUMENTED ALLOCATION SCORE (0-100)
============================================================
The "Allocation Score" is an analytical ranking score created for
THIS PROJECT. It is not a standard industry metric.

It is a weighted blend of four components, each min-max normalized to
0-100 across the groups being compared (so the score is always
relative to the peer set, never an absolute claim):

  1. ROI Performance   (weight 40%) — the group's average ROI
  2. ROI Consistency   (weight 25%) — inverted coefficient of
     variation (std/mean) of ROI; lower volatility scores higher
  3. Cost Efficiency   (weight 20%) — total revenue per unit of
     total acquisition cost spent
  4. Evidence Volume   (weight 15%) — campaign count (more observed
     campaigns = more evidence behind the score)

Weights sum to 100% and deliberately weight realized ROI outcomes
(components 1-2, 65%) above secondary efficiency/volume signals
(components 3-4, 35%).

============================================================
DOCUMENTED RISK LEVEL
============================================================
Each group gets a risk score from three observed signals, each
normalized 0-100 across the peer set, then averaged:

  - ROI volatility (coefficient of variation)
  - Negative-ROI share (% of the group's campaigns with ROI < 0)
  - Evidence scarcity (inverted campaign count — fewer campaigns
    means less evidence, hence more uncertainty)

Bands: LOW < 40, MEDIUM 40-70, HIGH > 70.

Note that a group is never called "high risk" on ROI variance alone —
all three signals contribute, and the contributing values are returned
in the API response so the classification is auditable.
"""

import math

import numpy as np
import pandas as pd

DIMENSION_COLUMNS = {
    "Campaign Type": "Campaign_Type",
    "Customer Segment": "Customer_Segment",
    "Target Audience": "Target_Audience",
    "Channel Group": "Channel_Used",
}

RISK_MODES = ("Conservative", "Balanced", "Performance-focused")

# Channel_Used contains 150+ recorded multi-channel combinations. For a
# budget allocation to be meaningful and feasible under min/max
# constraints, we restrict to the highest-volume combinations. This is
# documented in the API response's assumptions.
MAX_GROUPS_FOR_CHANNEL = 10
MIN_CAMPAIGNS_FOR_CHANNEL_GROUP = 200

# Allocation Score component weights (documented above).
SCORE_WEIGHTS = {
    "roi_performance": 0.40,
    "roi_consistency": 0.25,
    "cost_efficiency": 0.20,
    "evidence_volume": 0.15,
}

# Risk-mode adjustment. The performance weight vector is blended with
# a risk penalty; these exponents are documented, not arbitrary:
#   Conservative       — heavily damps score differences and penalizes
#                        risk most (score^0.5, full risk penalty)
#   Balanced           — moderate (score^1.0, half risk penalty)
#   Performance-focused— amplifies score differences, minimal risk
#                        penalty (score^1.5, quarter risk penalty)
RISK_MODE_SETTINGS = {
    "Conservative": {"score_exponent": 0.5, "risk_penalty_weight": 1.0},
    "Balanced": {"score_exponent": 1.0, "risk_penalty_weight": 0.5},
    "Performance-focused": {"score_exponent": 1.5, "risk_penalty_weight": 0.25},
}

RISK_BANDS = [(70, "HIGH"), (40, "MEDIUM"), (0, "LOW")]


def _safe_round(value, ndigits=4):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return round(float(value), ndigits)


def _minmax_normalize(values):
    """Min-max normalize a list to 0-100. If all values are identical,
    every element receives 50 (neutral) rather than 0 or 100, since
    there is no basis to rank them apart.
    """
    arr = np.asarray(values, dtype=float)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    lo, hi = arr.min(), arr.max()
    if math.isclose(lo, hi):
        return [50.0] * len(arr)
    return list((arr - lo) / (hi - lo) * 100)


class InvalidOptimizerInput(ValueError):
    """Raised for invalid/infeasible user inputs. Routes convert this
    into a clean HTTP 400 with the message.
    """


# ============================================================
# INPUT VALIDATION
# ============================================================


def validate_inputs(dimension, total_budget, min_allocation, max_allocation, risk_mode, group_count=None):
    if dimension not in DIMENSION_COLUMNS:
        raise InvalidOptimizerInput(f"'dimension' must be one of {sorted(DIMENSION_COLUMNS)}.")

    if not isinstance(total_budget, (int, float)) or isinstance(total_budget, bool):
        raise InvalidOptimizerInput("'total_budget' must be a number.")
    if total_budget <= 0:
        raise InvalidOptimizerInput("'total_budget' must be greater than 0.")

    for name, value in (("min_allocation", min_allocation), ("max_allocation", max_allocation)):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise InvalidOptimizerInput(f"'{name}' must be a number.")

    if min_allocation < 0:
        raise InvalidOptimizerInput("'min_allocation' must be 0 or greater.")
    if max_allocation > 100:
        raise InvalidOptimizerInput("'max_allocation' must be 100 or less.")
    if min_allocation > max_allocation:
        raise InvalidOptimizerInput("'min_allocation' must be less than or equal to 'max_allocation'.")

    if risk_mode not in RISK_MODES:
        raise InvalidOptimizerInput(f"'risk_mode' must be one of {list(RISK_MODES)}.")

    if group_count is not None:
        if group_count * min_allocation > 100:
            raise InvalidOptimizerInput(
                f"Allocation constraints are infeasible: {group_count} groups x {min_allocation}% minimum "
                f"= {group_count * min_allocation}%, which exceeds 100%."
            )
        if group_count * max_allocation < 100:
            raise InvalidOptimizerInput(
                f"Allocation constraints are infeasible: {group_count} groups x {max_allocation}% maximum "
                f"= {group_count * max_allocation}%, which is below 100%."
            )


# ============================================================
# HISTORICAL PERFORMANCE BASIS
# ============================================================


def get_group_performance(df, dimension):
    """Observed historical performance per allocation group. All values
    come directly from the connected dataset.
    """
    column = DIMENSION_COLUMNS[dimension]
    if column not in df.columns or df.empty:
        return []

    grouped = df.groupby(column, dropna=False)

    rows = []
    for name, g in grouped:
        roi = g["ROI"]
        total_cost = g["Acquisition_Cost"].sum()
        roi_mean = float(roi.mean())
        roi_std = float(roi.std()) if len(roi) > 1 else 0.0
        cv = abs(roi_std / roi_mean) if roi_mean else 0.0

        rows.append(
            {
                "group": str(name),
                "campaign_count": int(len(g)),
                "average_roi": _safe_round(roi_mean, 4),
                "median_roi": _safe_round(roi.median(), 4),
                "roi_std_dev": _safe_round(roi_std, 4),
                "roi_coefficient_of_variation": _safe_round(cv, 4),
                "negative_roi_percentage": _safe_round(100 * (roi < 0).mean(), 2),
                "total_revenue": _safe_round(g["Revenue"].sum(), 2),
                "total_acquisition_cost": _safe_round(total_cost, 2),
                "average_acquisition_cost": _safe_round(g["Acquisition_Cost"].mean(), 2),
                "conversion_count": int(g["Conversions"].sum()),
                "revenue_per_unit_cost": _safe_round(g["Revenue"].sum() / total_cost, 4) if total_cost else None,
            }
        )

    # Channel Group has 150+ recorded combinations — restrict to the
    # highest-volume ones so allocation remains feasible and evidenced.
    if dimension == "Channel Group":
        rows = [r for r in rows if r["campaign_count"] >= MIN_CAMPAIGNS_FOR_CHANNEL_GROUP]
        rows.sort(key=lambda r: r["campaign_count"], reverse=True)
        rows = rows[:MAX_GROUPS_FOR_CHANNEL]

    rows.sort(key=lambda r: r["group"])
    return rows


# ============================================================
# ALLOCATION SCORE & RISK SCORE
# ============================================================


def compute_scores(groups):
    """Adds allocation_score (0-100), risk_score (0-100), and risk_level
    to each group. Component values are attached so the score is
    auditable from the API response.
    """
    if not groups:
        return groups

    roi_perf = _minmax_normalize([g["average_roi"] or 0 for g in groups])
    # Consistency: lower CV is better, so invert before normalizing.
    consistency = _minmax_normalize([-(g["roi_coefficient_of_variation"] or 0) for g in groups])
    cost_eff = _minmax_normalize([g["revenue_per_unit_cost"] or 0 for g in groups])
    evidence = _minmax_normalize([g["campaign_count"] for g in groups])

    # Risk signals
    volatility_risk = _minmax_normalize([g["roi_coefficient_of_variation"] or 0 for g in groups])
    negative_risk = _minmax_normalize([g["negative_roi_percentage"] or 0 for g in groups])
    scarcity_risk = _minmax_normalize([-g["campaign_count"] for g in groups])

    for i, g in enumerate(groups):
        score = (
            roi_perf[i] * SCORE_WEIGHTS["roi_performance"]
            + consistency[i] * SCORE_WEIGHTS["roi_consistency"]
            + cost_eff[i] * SCORE_WEIGHTS["cost_efficiency"]
            + evidence[i] * SCORE_WEIGHTS["evidence_volume"]
        )
        g["allocation_score"] = _safe_round(score, 2)
        g["allocation_score_components"] = {
            "roi_performance": _safe_round(roi_perf[i], 2),
            "roi_consistency": _safe_round(consistency[i], 2),
            "cost_efficiency": _safe_round(cost_eff[i], 2),
            "evidence_volume": _safe_round(evidence[i], 2),
        }

        risk = (volatility_risk[i] + negative_risk[i] + scarcity_risk[i]) / 3
        g["risk_score"] = _safe_round(risk, 2)
        g["risk_level"] = next(label for threshold, label in RISK_BANDS if risk >= threshold)
        g["risk_score_components"] = {
            "roi_volatility": _safe_round(volatility_risk[i], 2),
            "negative_roi_share": _safe_round(negative_risk[i], 2),
            "evidence_scarcity": _safe_round(scarcity_risk[i], 2),
        }
        g["evidence_basis"] = "OBSERVED"

    return groups


# ============================================================
# ALLOCATION ALGORITHM
# ============================================================


def _apply_constraints(weights, min_allocation, max_allocation):
    """Convert raw non-negative weights into percentages summing to
    exactly 100 while respecting min/max bounds.

    Iterative water-filling: clamp any out-of-bounds allocation, then
    redistribute the remaining budget proportionally among the
    still-free groups, repeating until stable.
    """
    n = len(weights)
    if n == 0:
        return []

    weights = np.asarray(weights, dtype=float)
    weights = np.clip(weights, 0, None)
    if weights.sum() <= 0:
        weights = np.ones(n)

    allocation = weights / weights.sum() * 100
    locked = np.zeros(n, dtype=bool)

    for _ in range(100):  # bounded; converges well before this
        over = (allocation > max_allocation + 1e-9) & ~locked
        under = (allocation < min_allocation - 1e-9) & ~locked
        if not over.any() and not under.any():
            break

        allocation[over] = max_allocation
        allocation[under] = min_allocation
        locked[over | under] = True

        remaining = 100 - allocation[locked].sum()
        free = ~locked
        if not free.any():
            break
        free_weights = weights[free]
        if free_weights.sum() <= 0:
            allocation[free] = remaining / free.sum()
        else:
            allocation[free] = free_weights / free_weights.sum() * remaining

    # Final normalization guard against floating-point drift.
    total = allocation.sum()
    if total > 0:
        allocation = allocation / total * 100

    return list(allocation)


def build_strategy(groups, weights, total_budget, min_allocation, max_allocation, strategy_name):
    allocations = _apply_constraints(weights, min_allocation, max_allocation)

    # Round to 2dp for display, then push any residual rounding drift
    # onto the largest allocation so the DISPLAYED percentages sum to
    # exactly 100.00 (avoids a 100.01% artifact in the UI).
    rounded = [round(p, 2) for p in allocations]
    drift = round(100.0 - sum(rounded), 2)
    if rounded and abs(drift) >= 0.01:
        largest_idx = max(range(len(rounded)), key=lambda i: rounded[i])
        rounded[largest_idx] = round(rounded[largest_idx] + drift, 2)

    results = []
    for g, pct in zip(groups, rounded):
        allocated = total_budget * pct / 100
        avg_roi = g["average_roi"] or 0
        results.append(
            {
                "group": g["group"],
                "allocation_percentage": pct,
                "allocated_budget": _safe_round(allocated, 2),
                "allocation_score": g["allocation_score"],
                "risk_level": g["risk_level"],
                "average_roi": g["average_roi"],
                "illustrative_estimated_profit": _safe_round(allocated * avg_roi, 2),
                "evidence_basis": "OBSERVED",
            }
        )

    return {"strategy": strategy_name, "allocations": results}


def build_all_strategies(groups, total_budget, min_allocation, max_allocation, risk_mode):
    n = len(groups)

    # A. Equal Allocation
    equal = build_strategy(groups, [1.0] * n, total_budget, min_allocation, max_allocation, "Equal Allocation")

    # B. Performance Allocation — weight by allocation score only.
    perf_weights = [g["allocation_score"] or 0 for g in groups]
    performance = build_strategy(groups, perf_weights, total_budget, min_allocation, max_allocation, "Performance Allocation")

    # C. Risk-Adjusted Allocation — allocation score shaped by the
    # selected risk mode and penalized by the group's risk score.
    settings = RISK_MODE_SETTINGS[risk_mode]
    risk_weights = []
    for g in groups:
        score = max(g["allocation_score"] or 0, 0.01)
        shaped = score ** settings["score_exponent"]
        risk_penalty = 1 - (settings["risk_penalty_weight"] * (g["risk_score"] or 0) / 100)
        risk_weights.append(max(shaped * risk_penalty, 0.0))
    risk_adjusted = build_strategy(groups, risk_weights, total_budget, min_allocation, max_allocation, "Risk-Adjusted Allocation")

    return {"equal": equal, "performance": performance, "risk_adjusted": risk_adjusted}


# ============================================================
# STRATEGY COMPARISON
# ============================================================


def _concentration(allocations):
    """Herfindahl-style concentration: sum of squared allocation shares,
    normalized so 0 = perfectly even and 100 = fully concentrated in
    one group. Documented, not arbitrary.
    """
    n = len(allocations)
    if n <= 1:
        return 100.0
    shares = np.asarray([a["allocation_percentage"] / 100 for a in allocations], dtype=float)
    hhi = float((shares ** 2).sum())
    even = 1 / n
    return _safe_round(max(0.0, (hhi - even) / (1 - even)) * 100, 2)


def build_comparison(strategies, total_budget):
    comparison = {}
    for key, strat in strategies.items():
        allocations = strat["allocations"]
        est_profit = sum(a["illustrative_estimated_profit"] or 0 for a in allocations)
        concentration = _concentration(allocations)

        risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
        weighted_risk = 0.0
        for a in allocations:
            risk_counts[a["risk_level"]] = risk_counts.get(a["risk_level"], 0) + 1
            weight = (a["allocation_percentage"] or 0) / 100
            weighted_risk += weight * {"LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(a["risk_level"], 2)

        if weighted_risk < 1.5:
            risk_profile = "Predominantly LOW-risk groups"
        elif weighted_risk < 2.5:
            risk_profile = "Mixed / predominantly MEDIUM-risk groups"
        else:
            risk_profile = "Weighted toward HIGH-risk groups"

        comparison[key] = {
            "strategy": strat["strategy"],
            "total_budget": _safe_round(total_budget, 2),
            "illustrative_estimated_profit": _safe_round(est_profit, 2),
            "illustrative_estimated_return": _safe_round(total_budget + est_profit, 2),
            "allocation_concentration": concentration,
            "risk_profile": risk_profile,
            "risk_group_counts": risk_counts,
        }

    comparison["note"] = (
        "Illustrative historical-performance comparison. No strategy here is presented as superior — "
        "these are alternative allocation shapes derived from observed historical data under the "
        "selected constraints."
    )
    return comparison


# ============================================================
# WHY THIS ALLOCATION
# ============================================================


def build_explanations(groups, strategy):
    """Per-group explanation of why it received its allocation, using
    precise non-causal wording.
    """
    by_group = {g["group"]: g for g in groups}
    explanations = []

    ranked = sorted(strategy["allocations"], key=lambda a: a["allocation_percentage"] or 0, reverse=True)
    for a in ranked:
        g = by_group.get(a["group"])
        if not g:
            continue
        comps = g["allocation_score_components"]
        explanations.append(
            {
                "group": a["group"],
                "allocation_percentage": a["allocation_percentage"],
                "reason": (
                    f"Allocated {a['allocation_percentage']}% because this group had an allocation score of "
                    f"{g['allocation_score']}/100 under the selected constraints and risk mode."
                ),
                "historical_roi_evidence": f"Observed average ROI {g['average_roi']}x (median {g['median_roi']}x) across {g['campaign_count']:,} campaigns.",
                "consistency": f"ROI consistency component scored {comps['roi_consistency']}/100 (coefficient of variation {g['roi_coefficient_of_variation']}).",
                "cost_efficiency": f"Cost efficiency component scored {comps['cost_efficiency']}/100 ({g['revenue_per_unit_cost']} revenue per unit of acquisition cost).",
                "campaign_volume": f"Evidence volume component scored {comps['evidence_volume']}/100 ({g['campaign_count']:,} observed campaigns).",
                "risk_adjustment": f"Risk level {g['risk_level']} (risk score {g['risk_score']}/100).",
                "evidence_strength": "OBSERVED — based on historical campaign records, not a causal finding.",
                "caution": (
                    "This reflects observed historical association under the selected scoring method. It does "
                    "not establish that allocating budget to this group causes higher ROI."
                ),
            }
        )

    return explanations


# ============================================================
# ASSUMPTIONS / LIMITATIONS
# ============================================================


def get_assumptions(dimension):
    assumptions = [
        "Illustrative estimated profit is calculated as allocated budget x the group's observed historical average ROI.",
        "This is a model-derived / historical-performance-based estimate, not guaranteed revenue or profit.",
        "The Allocation Score is an analytical ranking score created for this project; it is not a standard industry metric.",
        "Allocation percentages are relative rankings within the selected dimension's peer set, not absolute optimality claims.",
    ]
    if dimension == "Channel Group":
        assumptions.append(
            f"Channel Group uses recorded Channel_Used values as-is. Multi-channel records are treated as a single "
            f"recorded channel group, never split into individual channel attribution. Only the top "
            f"{MAX_GROUPS_FOR_CHANNEL} combinations with at least {MIN_CAMPAIGNS_FOR_CHANNEL_GROUP} campaigns are "
            f"included, to keep the allocation feasible and sufficiently evidenced."
        )
    return assumptions


LIMITATIONS = [
    "Historical ROI does not establish causality.",
    "The Allocation Score is project-specific and not an industry-standard metric.",
    "Historical performance may not continue.",
    "Estimated profit is illustrative, not guaranteed.",
    "Budget changes do not guarantee proportional returns.",
    "Small groups (low campaign counts) require additional caution.",
    "Major budget changes should be validated experimentally (e.g. A/B testing) before deployment.",
    "Acquisition Cost is a dominant signal in the current early-stage ROI model.",
    "Multi-channel records are treated as recorded channel groups, not individual channel attribution.",
]


# ============================================================
# TOP-LEVEL ENTRY POINT
# ============================================================


def get_budget_optimization(
    df,
    dimension="Campaign Type",
    total_budget=1_000_000,
    min_allocation=5,
    max_allocation=40,
    risk_mode="Balanced",
):
    validate_inputs(dimension, total_budget, min_allocation, max_allocation, risk_mode)

    groups = get_group_performance(df, dimension)
    if not groups:
        raise InvalidOptimizerInput(f"No allocation groups available for dimension '{dimension}' in the connected dataset.")

    # Re-validate now that the actual group count is known.
    validate_inputs(dimension, total_budget, min_allocation, max_allocation, risk_mode, group_count=len(groups))

    groups = compute_scores(groups)
    strategies = build_all_strategies(groups, total_budget, min_allocation, max_allocation, risk_mode)
    comparison = build_comparison(strategies, total_budget)
    explanations = build_explanations(groups, strategies["risk_adjusted"])

    return {
        "status": "success",
        "dimension": dimension,
        "total_budget": _safe_round(total_budget, 2),
        "constraints": {
            "min_allocation_percentage": min_allocation,
            "max_allocation_percentage": max_allocation,
            "risk_mode": risk_mode,
            "group_count": len(groups),
        },
        "scoring_methodology": {
            "allocation_score_weights": SCORE_WEIGHTS,
            "allocation_score_note": (
                "Each component is min-max normalized to 0-100 across the groups being compared, then blended "
                "using the weights above. This is an analytical ranking score created for this project and is "
                "not a standard industry metric."
            ),
            "risk_bands": {"LOW": "< 40", "MEDIUM": "40 - 70", "HIGH": "> 70"},
            "risk_note": (
                "Risk score averages three normalized signals: ROI volatility, negative-ROI share, and evidence "
                "scarcity. A group is never classified HIGH risk on ROI variance alone."
            ),
            "risk_mode_settings": RISK_MODE_SETTINGS[risk_mode],
        },
        "groups": groups,
        "strategies": strategies,
        "comparison": comparison,
        "explanations": explanations,
        "assumptions": get_assumptions(dimension),
        "limitations": LIMITATIONS,
    }
