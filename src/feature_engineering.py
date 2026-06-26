from __future__ import annotations

import numpy as np
import pandas as pd


TARGET_KEYWORDS = {
    "youth": ["청소년", "진로", "창작", "캠프", "미디어", "워크숍", "교육"],
    "elderly": ["고령", "시니어", "낮 시간", "생활문화", "건강", "복지"],
    "tourism": ["관광", "축제", "체험", "해변", "지역문화"],
    "resident": ["주민", "동네", "생활문화", "마을", "문화교실"],
}


def minmax(series: pd.Series, reverse: bool = False) -> pd.Series:
    values = series.astype(float)
    spread = values.max() - values.min()
    if spread == 0:
        normalized = pd.Series(50.0, index=series.index)
    else:
        normalized = 100 * (values - values.min()) / spread
    return 100 - normalized if reverse else normalized


def classify_event_targets(events: pd.DataFrame) -> pd.DataFrame:
    classified = events.copy()
    text = classified["text"].fillna("")
    for target, keywords in TARGET_KEYWORDS.items():
        pattern = "|".join(keywords)
        classified[f"is_{target}"] = text.str.contains(pattern, case=False, regex=True).astype(int)
    return classified


def build_region_features_from_raw(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    population = raw.get("population", pd.DataFrame()).copy()
    bus_stops = raw.get("bus_stops", pd.DataFrame()).copy()
    events = raw.get("events", pd.DataFrame()).copy()
    museums = raw.get("museums", pd.DataFrame()).copy()
    festivals = raw.get("festivals", pd.DataFrame()).copy()
    facilities = raw.get("facilities", pd.DataFrame()).copy()

    if not events.empty:
        events = classify_event_targets(_ensure_event_text(events))

    pop_agg = _aggregate_population(population)
    event_agg = _aggregate_events(events)
    museum_agg = _aggregate_museums(museums)
    festival_agg = _aggregate_festivals(festivals)
    bus_agg = _aggregate_bus(bus_stops)

    # 시(市) 단위 이벤트를 구(區) 하위 행정구역에 인구 비례 배분
    event_agg = _distribute_city_events_to_gu(event_agg, pop_agg)
    festival_agg = _distribute_city_events_to_gu(festival_agg, pop_agg)

    features = pop_agg
    for frame in [event_agg, museum_agg, festival_agg, bus_agg]:
        if not frame.empty:
            features = features.merge(frame, on=["region_name", "province"], how="outer")

    if "population" in features.columns:
        features = features[features["population"].notna()].copy()

    features = _post_process_features(features)
    features["facility_national_count"] = len(facilities)
    features["facility_national_diversity"] = facilities["culGrpName"].nunique() if not facilities.empty and "culGrpName" in facilities.columns else 0
    return features


def _ensure_event_text(events: pd.DataFrame) -> pd.DataFrame:
    if "text" in events.columns:
        return events
    out = events.copy()
    out["text"] = (
        out.get("event_name", "").astype(str)
        + " "
        + out.get("event_type", "").astype(str)
        + " "
        + out.get("place", "").astype(str)
        + " "
        + out.get("service_name", "").astype(str)
    )
    return out


def _distribute_city_events_to_gu(
    agg: pd.DataFrame,
    pop_agg: pd.DataFrame,
) -> pd.DataFrame:
    """시(市) 단위 집계 이벤트/축제를 구(區) 하위 행정구역에 인구 비례로 배분.

    예: '경기도 성남시' 이벤트 120건 → 분당구/수정구/중원구에 인구 비율대로 분배.
    구(區) 데이터가 이미 있으면 배분 없이 그대로 둔다.
    """
    if agg.empty or pop_agg.empty:
        return agg

    # 인구 데이터에서 구(區) 단위 파악: region_name이 '시도 시 구' 형태
    def _parent_city(region: str) -> str | None:
        parts = region.strip().split()
        if len(parts) == 3 and parts[2].endswith("구"):
            return f"{parts[0]} {parts[1]}"
        return None

    pop_agg = pop_agg.copy()
    pop_agg["_parent"] = pop_agg["region_name"].map(_parent_city)
    gu_rows = pop_agg[pop_agg["_parent"].notna()].copy()

    if gu_rows.empty:
        return agg

    # 구 단위 인구 합계 → 부모 시 인구 (= 가중치 분모)
    city_pop_total = gu_rows.groupby("_parent")["population"].sum().rename("city_total")
    gu_rows = gu_rows.join(city_pop_total, on="_parent")
    gu_rows["pop_share"] = gu_rows["population"] / gu_rows["city_total"].replace(0, np.nan)

    # 집계 DataFrame에서 수치 컬럼 추출
    num_cols = agg.select_dtypes(include="number").columns.tolist()
    if not num_cols:
        return agg

    agg_idx = agg.set_index("region_name")
    new_rows: list[dict] = []

    for parent_city, gu_group in gu_rows.groupby("_parent"):
        if parent_city not in agg_idx.index:
            continue
        # 이미 구(區) 단위 이벤트 행이 있으면 배분 불필요
        has_gu_event = any(rn in agg_idx.index for rn in gu_group["region_name"])
        if has_gu_event:
            continue

        parent_row = agg_idx.loc[parent_city]
        for _, gu_row in gu_group.iterrows():
            share = gu_row["pop_share"] if not np.isnan(gu_row["pop_share"]) else 0.0
            row = {"region_name": gu_row["region_name"], "province": gu_row["province"]}
            for col in num_cols:
                val = parent_row[col] if col in parent_row.index else 0
                if col.endswith(("_ratio", "_ratio_mean", "_mean")) or col in ("free_event_ratio", "museum_free_ratio", "transport_info_ratio"):
                    row[col] = float(val)
                else:
                    row[col] = round(float(val) * share)
            new_rows.append(row)

    if not new_rows:
        return agg

    new_df = pd.DataFrame(new_rows)
    # 부모 시 행은 구 단위로 쪼갰으므로 제거
    cities_replaced = {r["region_name"].rsplit(" ", 1)[0] + " " + r["region_name"].rsplit(" ", 1)[0].split()[-1]
                       for r in new_rows}
    parent_cities_to_drop = {_parent_city(r["region_name"]) for r in new_rows}
    keep_mask = ~agg["region_name"].isin(parent_cities_to_drop)
    return pd.concat([agg[keep_mask], new_df], ignore_index=True)


def _aggregate_population(population: pd.DataFrame) -> pd.DataFrame:
    if population.empty:
        return pd.DataFrame(columns=["region_code", "region_name", "province", "population", "youth_ratio", "elderly_ratio", "single_household_ratio"])
    cols = ["region_code", "region_name", "province", "population", "youth_ratio", "elderly_ratio", "single_household_ratio"]
    out = population[cols].copy()
    out["region_code"] = out["region_code"].fillna("").astype(str)
    return out


def _aggregate_events(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["region_name", "province"])
    agg = (
        events.groupby(["region_name", "province"], dropna=False)
        .agg(
            event_count=("event_name", "count"),
            program_diversity=("event_type", "nunique"),
            free_event_ratio=("is_free", "mean"),
            youth_program_ratio=("is_youth", "mean"),
            elderly_program_ratio=("is_elderly", "mean"),
            tourism_program_ratio=("is_tourism", "mean"),
            resident_program_ratio=("is_resident", "mean"),
        )
        .reset_index()
    )
    return agg[[
        "region_name",
        "province",
        "event_count",
        "program_diversity",
        "free_event_ratio",
        "youth_program_ratio",
        "elderly_program_ratio",
        "tourism_program_ratio",
        "resident_program_ratio",
    ]]


def _aggregate_museums(museums: pd.DataFrame) -> pd.DataFrame:
    if museums.empty:
        return pd.DataFrame(columns=["region_name", "province"])
    agg = (
        museums.groupby(["region_name", "province"], dropna=False)
        .agg(
            museum_count=("museum_name", "count"),
            facility_type_count=("facility_type", "nunique"),
            museum_free_ratio=("is_free", "mean"),
            transport_info_ratio=("has_transport", "mean"),
        )
        .reset_index()
    )
    return agg[["region_name", "province", "museum_count", "facility_type_count", "museum_free_ratio", "transport_info_ratio"]]


def _aggregate_festivals(festivals: pd.DataFrame) -> pd.DataFrame:
    if festivals.empty:
        return pd.DataFrame(columns=["region_name", "province"])
    agg = (
        festivals.groupby(["region_name", "province"], dropna=False)
        .agg(
            festival_count=("festival_name", "count"),
            festival_type_count=("festival_type", "nunique"),
            festival_budget=("budget_total", "sum"),
            visitor_total=("visitor_total", "sum"),
        )
        .reset_index()
    )
    return agg[["region_name", "province", "festival_count", "festival_type_count", "festival_budget", "visitor_total"]]


def _aggregate_bus(bus_stops: pd.DataFrame) -> pd.DataFrame:
    if bus_stops.empty:
        return pd.DataFrame(columns=["region_name", "province"])
    agg = (
        bus_stops.groupby("region_name", dropna=False)
        .agg(bus_stop_count=("bus_stop_id", "count"))
        .reset_index()
    )
    agg["province"] = agg["region_name"].str.split().str[0]
    # 광역시 단위 집계는 이미 구 단위로 배분됐으므로 그대로 반환
    return agg[["region_name", "province", "bus_stop_count"]]


def _post_process_features(features: pd.DataFrame) -> pd.DataFrame:
    out = features.copy()
    if out.empty:
        return out

    numeric_cols = [
        "population",
        "youth_ratio",
        "elderly_ratio",
        "single_household_ratio",
        "event_count",
        "program_diversity",
        "free_event_ratio",
        "youth_program_ratio",
        "elderly_program_ratio",
        "tourism_program_ratio",
        "resident_program_ratio",
        "museum_count",
        "facility_type_count",
        "museum_free_ratio",
        "transport_info_ratio",
        "festival_count",
        "festival_type_count",
        "festival_budget",
        "visitor_total",
        "bus_stop_count",
    ]
    for col in numeric_cols:
        if col not in out.columns:
            out[col] = np.nan
    out[numeric_cols] = out[numeric_cols].fillna(0)
    out["population"] = out["population"].replace(0, np.nan)
    out["youth_ratio"] = out["youth_ratio"].fillna(0)
    out["elderly_ratio"] = out["elderly_ratio"].fillna(0)
    out["single_household_ratio"] = out["single_household_ratio"].fillna(30.0)

    out["museum_count"] = out["museum_count"].fillna(0)
    out["festival_count"] = out["festival_count"].fillna(0)
    out["event_count"] = out["event_count"].fillna(0)
    out["bus_stop_count"] = out["bus_stop_count"].fillna(0)

    out["facility_count"] = out["museum_count"] + 0.2 * out["festival_count"]
    out["facility_per_10k"] = out["facility_count"] / out["population"] * 10000
    out["event_per_month"] = (out["event_count"] + out["festival_count"]) / 12
    out["program_diversity"] = out[["program_diversity", "festival_type_count"]].max(axis=1)
    out["free_event_ratio"] = out[["free_event_ratio", "museum_free_ratio"]].mean(axis=1)
    out["regular_program_score"] = np.where((out["event_count"] + out["festival_count"]) > 0, 1.0, 0.0)

    out["public_transport_score"] = minmax(out["bus_stop_count"])
    out["transport_weakness"] = 100 - out["public_transport_score"]
    out["rural_flag"] = out["region_name"].str.contains(r"군|읍|면", regex=True).astype(int)
    out["rural_penalty"] = out["rural_flag"] * 100
    out["elderly_access_penalty"] = np.where(out["elderly_ratio"] >= 30, 100, 40)
    out["vulnerability_score"] = minmax(out["elderly_ratio"] + out["transport_weakness"] / 2)

    youth_need = minmax(out["youth_ratio"])
    elderly_need = minmax(out["elderly_ratio"])
    youth_supply_gap = 100 - (out["youth_program_ratio"] * 100)
    elderly_supply_gap = 100 - (out["elderly_program_ratio"] * 100)
    resident_supply_gap = 100 - (out["resident_program_ratio"] * 100)
    tourism_supply_gap = 100 - (out["tourism_program_ratio"] * 100)
    out["mismatch_raw"] = (
        0.30 * youth_need * youth_supply_gap / 100
        + 0.30 * elderly_need * elderly_supply_gap / 100
        + 0.20 * resident_supply_gap
        + 0.20 * tourism_supply_gap
    )
    return out


def build_region_features(
    regions: pd.DataFrame, facilities: pd.DataFrame, events: pd.DataFrame
) -> pd.DataFrame:
    # Backward-compatible adapter for the older sample-data path.
    features = regions.merge(
        facilities.groupby("region_code")
        .agg(
            facility_count=("facility_name", "count"),
            facility_type_count=("facility_type", "nunique"),
        )
        .reset_index(),
        on="region_code",
        how="left",
    ).merge(
        events.groupby("region_code")
        .agg(
            event_count=("event_name", "count"),
            program_diversity=("category", "nunique"),
            free_event_ratio=("is_free", "mean"),
            regular_program_score=("is_regular", "mean"),
            youth_program_ratio=("is_youth", "mean"),
            elderly_program_ratio=("is_elderly", "mean"),
            tourism_program_ratio=("is_tourism", "mean"),
            resident_program_ratio=("is_resident", "mean"),
        )
        .reset_index(),
        on="region_code",
        how="left",
    )
    fill_zero_cols = [
        "facility_count",
        "facility_type_count",
        "event_count",
        "program_diversity",
        "free_event_ratio",
        "regular_program_score",
        "youth_program_ratio",
        "elderly_program_ratio",
        "tourism_program_ratio",
        "resident_program_ratio",
    ]
    features[fill_zero_cols] = features[fill_zero_cols].fillna(0)
    features["facility_per_10k"] = features["facility_count"] / features["population"] * 10000
    features["event_per_month"] = features["event_count"] / 12
    features["facility_diversity"] = features["facility_type_count"]
    features["transport_weakness"] = 100 - features["public_transport_score"]
    features["rural_penalty"] = features["rural_flag"] * 100
    features["elderly_access_penalty"] = np.where(features["elderly_ratio"] >= 30, 100, 40)

    youth_need = minmax(features["youth_ratio"])
    elderly_need = minmax(features["elderly_ratio"])
    youth_supply_gap = 100 - (features["youth_program_ratio"] * 100)
    elderly_supply_gap = 100 - (features["elderly_program_ratio"] * 100)
    resident_supply_gap = 100 - (features["resident_program_ratio"] * 100)
    features["mismatch_raw"] = (
        0.35 * youth_need * youth_supply_gap / 100
        + 0.35 * elderly_need * elderly_supply_gap / 100
        + 0.30 * resident_supply_gap
    )
    return features
    facilities_agg = (
        facilities.groupby("region_code")
        .agg(
            facility_count=("facility_name", "count"),
            facility_type_count=("facility_type", "nunique"),
        )
        .reset_index()
    )

    events_agg = (
        events.groupby("region_code")
        .agg(
            event_count=("event_name", "count"),
            program_diversity=("category", "nunique"),
            free_event_ratio=("is_free", "mean"),
            regular_program_score=("is_regular", "mean"),
            youth_program_ratio=("is_youth", "mean"),
            elderly_program_ratio=("is_elderly", "mean"),
            tourism_program_ratio=("is_tourism", "mean"),
            resident_program_ratio=("is_resident", "mean"),
        )
        .reset_index()
    )

    features = regions.merge(facilities_agg, on="region_code", how="left").merge(
        events_agg, on="region_code", how="left"
    )
    fill_zero_cols = [
        "facility_count",
        "facility_type_count",
        "event_count",
        "program_diversity",
        "free_event_ratio",
        "regular_program_score",
        "youth_program_ratio",
        "elderly_program_ratio",
        "tourism_program_ratio",
        "resident_program_ratio",
    ]
    features[fill_zero_cols] = features[fill_zero_cols].fillna(0)

    features["facility_per_10k"] = features["facility_count"] / features["population"] * 10000
    features["event_per_month"] = features["event_count"] / 12
    features["facility_diversity"] = features["facility_type_count"]
    features["transport_weakness"] = 100 - features["public_transport_score"]
    features["rural_penalty"] = features["rural_flag"] * 100
    features["elderly_access_penalty"] = np.where(features["elderly_ratio"] >= 30, 100, 40)

    youth_need = minmax(features["youth_ratio"])
    elderly_need = minmax(features["elderly_ratio"])
    youth_supply_gap = 100 - (features["youth_program_ratio"] * 100)
    elderly_supply_gap = 100 - (features["elderly_program_ratio"] * 100)
    resident_supply_gap = 100 - (features["resident_program_ratio"] * 100)
    features["mismatch_raw"] = (
        0.35 * youth_need * youth_supply_gap / 100
        + 0.35 * elderly_need * elderly_supply_gap / 100
        + 0.30 * resident_supply_gap
    )
    return features
