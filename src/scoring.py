from __future__ import annotations

import pandas as pd

try:
    from feature_engineering import minmax
except ImportError:  # pragma: no cover
    from .feature_engineering import minmax


def add_scores(features: pd.DataFrame) -> pd.DataFrame:
    scored = features.copy()

    scored["facility_score"] = minmax(scored["facility_per_10k"])
    scored["event_score"] = minmax(scored["event_per_month"])
    scored["program_diversity_score"] = minmax(scored["program_diversity"])
    scored["free_event_score"] = scored["free_event_ratio"] * 100
    scored["regular_program_score_norm"] = scored["regular_program_score"] * 100

    scored["supply_score"] = (
        0.25 * scored["facility_score"]
        + 0.25 * scored["event_score"]
        + 0.20 * scored["program_diversity_score"]
        + 0.15 * scored["free_event_score"]
        + 0.15 * scored["regular_program_score_norm"]
    )
    scored["supply_deficit_score"] = 100 - scored["supply_score"]

    scored["population_score"] = minmax(scored["population"])
    scored["youth_demand_score"] = minmax(scored["youth_ratio"])
    scored["elderly_demand_score"] = minmax(scored["elderly_ratio"])
    scored["single_household_score"] = minmax(scored["single_household_ratio"])
    scored["vulnerability_score_norm"] = scored["vulnerability_score"]
    scored["demand_score"] = (
        0.30 * scored["population_score"]
        + 0.20 * scored["youth_demand_score"]
        + 0.20 * scored["elderly_demand_score"]
        + 0.15 * scored["single_household_score"]
        + 0.15 * scored["vulnerability_score_norm"]
    )

    scored["distance_disadvantage"] = scored["supply_deficit_score"]
    scored["access_penalty"] = (
        0.40 * scored["distance_disadvantage"]
        + 0.30 * scored["transport_weakness"]
        + 0.20 * scored["rural_penalty"]
        + 0.10 * scored["elderly_access_penalty"]
    )
    scored["mismatch_penalty"] = minmax(scored["mismatch_raw"])

    scored["culture_gap_score"] = (
        0.40 * scored["demand_score"]
        + 0.30 * scored["supply_deficit_score"]
        + 0.20 * scored["access_penalty"]
        + 0.10 * scored["mismatch_penalty"]
    ).round(1)
    scored["risk_level"] = scored["culture_gap_score"].apply(risk_level)
    return scored


def risk_level(score: float) -> str:
    if score >= 80:
        return "고위험"
    if score >= 60:
        return "주의"
    if score >= 40:
        return "보통"
    return "양호"

