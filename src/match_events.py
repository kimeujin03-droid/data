"""2단: 시군구 결핍 프로파일 → 행사·축제 매칭 및 추천."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# 지리 유틸
# ---------------------------------------------------------------------------
def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 지점 간 직선 거리 (km)."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _load_centroids(path: str = "data/processed/region_centroids.json") -> dict[str, tuple[float, float]]:
    """시군구 centroid (lat, lon) 로드."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# ---------------------------------------------------------------------------
# 결핍 유형별 태그 조건 정의 (axis, value, weight)
# ---------------------------------------------------------------------------
_DEFICIT_PROFILES: dict[str, list[tuple[str, str, float]]] = {
    "고령층 교통취약형": [
        ("tag_target", "고령친화", 4.0),
        ("tag_price", "무료·저비용", 3.0),
        ("tag_time", "주간", 2.0),
        ("tag_genre", "체험·교육", 1.5),
        ("tag_genre", "공연", 1.0),
    ],
    "시설·행사 부족형": [
        ("tag_genre", "공연", 2.5),
        ("tag_genre", "전시", 2.0),
        ("tag_genre", "체험·교육", 1.5),
        ("tag_genre", "축제", 1.5),
        ("tag_price", "무료·저비용", 1.0),
    ],
    "교통 취약형": [
        ("tag_price", "무료·저비용", 3.0),
        ("tag_time", "종일", 2.0),
        ("tag_genre", "축제", 2.0),
        ("tag_genre", "체험·교육", 1.5),
    ],
    "균형 관리형": [
        ("tag_target", "가족·아동", 2.0),
        ("tag_target", "청소년·교육", 2.0),
        ("tag_genre", "전시", 1.5),
        ("tag_genre", "체험·교육", 1.5),
        ("tag_genre", "공연", 1.0),
    ],
}

_REASON_BOOST: dict[str, list[tuple[str, str, float]]] = {
    "고령층 비율 대비 친화 프로그램이 부족함": [("tag_target", "고령친화", 2.0)],
    "월평균 문화행사 수가 낮음": [("tag_genre", "공연", 1.0), ("tag_genre", "전시", 1.0)],
    "문화시설 또는 행사 공급이 부족함": [("tag_genre", "공연", 1.5), ("tag_genre", "축제", 1.0)],
    "대중교통 및 시설 접근성이 취약함": [("tag_price", "무료·저비용", 1.5), ("tag_time", "종일", 1.0)],
    "무료 프로그램 비율이 낮음": [("tag_price", "무료·저비용", 2.0)],
}

# 지리 점수: 교통취약형은 근거리를 훨씬 강하게 선호
_GEO_BONUS: dict[str, dict[str, float]] = {
    "고령층 교통취약형": {"same_sigungu": 5.0, "same_province": 1.5, "other": -2.0},
    "교통 취약형":       {"same_sigungu": 5.0, "same_province": 1.5, "other": -2.0},
    "시설·행사 부족형":   {"same_sigungu": 3.0, "same_province": 2.0, "other":  0.0},
    "균형 관리형":       {"same_sigungu": 2.0, "same_province": 1.5, "other":  0.0},
}

# 다양성 패널티: 이미 top-1로 선택된 행사가 같은 도 내에서 반복되면 패널티
_REPEAT_PENALTY = 3.0


def _build_need_weights(region_type: str, main_reasons: str) -> list[tuple[str, str, float]]:
    weights = list(_DEFICIT_PROFILES.get(region_type, []))
    for reason_text, boosts in _REASON_BOOST.items():
        if reason_text in str(main_reasons):
            weights.extend(boosts)
    return weights


def _geo_score(
    event_region: str,
    event_province: str,
    target_region: str,
    target_province: str,
    region_type: str,
    dist_km: float | None,
) -> float:
    """지리 점수. 거리 정보가 있으면 거리 기반, 없으면 행정구역 기반."""
    bonuses = _GEO_BONUS.get(region_type, {"same_sigungu": 2.0, "same_province": 1.0, "other": 0.0})

    if event_region == target_region:
        return bonuses["same_sigungu"]

    if dist_km is not None:
        # 거리 기반 점수: 10km 이내 → 3.0, 50km → 1.0, 100km → 0, 100km+ → 음수
        if region_type in ("고령층 교통취약형", "교통 취약형"):
            # 교통취약형: 거리 패널티 훨씬 강하게
            if dist_km <= 10:
                return 4.0
            elif dist_km <= 30:
                return 2.0
            elif dist_km <= 60:
                return 0.5
            elif dist_km <= 100:
                return -1.0
            else:
                return -3.0
        else:
            if dist_km <= 20:
                return 3.0
            elif dist_km <= 50:
                return 1.5
            elif dist_km <= 100:
                return 0.5
            else:
                return bonuses["other"]

    # 거리 정보 없으면 행정구역 기반
    if event_province == target_province:
        return bonuses["same_province"]
    return bonuses["other"]


def _score_event(
    row: pd.Series,
    need_weights: list[tuple[str, str, float]],
    target_region: str,
    target_province: str,
    region_type: str,
    region_lat: float | None,
    region_lon: float | None,
) -> float:
    score = sum(w for axis, val, w in need_weights if row.get(axis) == val)

    # 실제 거리 계산
    dist_km = None
    ev_lat = row.get("latitude")
    ev_lon = row.get("longitude")
    if (region_lat is not None and region_lon is not None
            and ev_lat is not None and not pd.isna(ev_lat)
            and ev_lon is not None and not pd.isna(ev_lon)):
        try:
            dist_km = _haversine_km(region_lat, region_lon, float(ev_lat), float(ev_lon))
        except Exception:
            dist_km = None

    score += _geo_score(
        str(row.get("region_name", "")),
        str(row.get("province", "")),
        target_region,
        target_province,
        region_type,
        dist_km,
    )
    return score


def _diversity_rerank(candidates: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """장르·대상 다양성을 보장하며 top_n개 선택.

    탐욕 알고리즘:
    1. 점수 기준 정렬
    2. 선택 시 이미 뽑힌 (event_name, tag_genre, tag_target) 조합과 동일하면 페널티
    3. 최대 top_n개 선택
    """
    if candidates.empty:
        return candidates.head(top_n)

    seen_names: set[str] = set()
    seen_genres: dict[str, int] = {}
    seen_targets: dict[str, int] = {}
    result_idxs: list[int] = []

    GENRE_REPEAT_PENALTY = 1.5
    TARGET_REPEAT_PENALTY = 1.0
    NAME_REPEAT_PENALTY = 999.0  # 동일 행사 두 번 금지

    scores = candidates["_score"].copy()

    for _ in range(top_n):
        if scores.empty:
            break
        # 현재 최고 점수 선택
        best_idx = scores.idxmax()
        best_row = candidates.loc[best_idx]
        result_idxs.append(best_idx)

        name = str(best_row.get("event_name", ""))
        genre = str(best_row.get("tag_genre", ""))
        target = str(best_row.get("tag_target", ""))

        seen_names.add(name)
        seen_genres[genre] = seen_genres.get(genre, 0) + 1
        seen_targets[target] = seen_targets.get(target, 0) + 1

        scores = scores.drop(best_idx)

        # 남은 후보에 패널티 적용
        for idx in scores.index:
            row = candidates.loc[idx]
            penalty = 0.0
            if str(row.get("event_name", "")) in seen_names:
                penalty += NAME_REPEAT_PENALTY
            if seen_genres.get(str(row.get("tag_genre", "")), 0) >= 2:
                penalty += GENRE_REPEAT_PENALTY
            if seen_targets.get(str(row.get("tag_target", "")), 0) >= 2:
                penalty += TARGET_REPEAT_PENALTY
            scores[idx] -= penalty

    return candidates.loc[result_idxs].reset_index(drop=True)


def _explain_match(ev: pd.Series, need_weights: list[tuple[str, str, float]]) -> str:
    hits = []
    for axis, value, _ in need_weights:
        if ev.get(axis) == value:
            label = {"tag_genre": "장르", "tag_target": "대상", "tag_time": "시간대", "tag_price": "가격"}.get(axis, axis)
            hits.append(f"{label}={value}")
    geo = str(ev.get("_geo_note", ""))
    if geo:
        hits.append(geo)
    return "; ".join(dict.fromkeys(hits))


# ---------------------------------------------------------------------------
# 매칭 메인
# ---------------------------------------------------------------------------
def match_events_to_regions(
    scored: pd.DataFrame,
    classified_db: pd.DataFrame,
    top_n: int = 10,
    centroids: dict | None = None,
) -> pd.DataFrame:
    """각 시군구에 맞는 행사·축제 Top-N 추천."""
    if classified_db.empty or scored.empty:
        return pd.DataFrame()

    if centroids is None:
        centroids = _load_centroids()

    # 날짜 필터: 이미 종료된 행사 제거 (end_date가 오늘 이전)
    import datetime
    today = pd.Timestamp(datetime.date.today())
    db_all = classified_db.copy()
    if "end_date" in db_all.columns:
        end_dt = pd.to_datetime(db_all["end_date"], errors="coerce")
        active = end_dt.isna() | (end_dt >= today)
        db_all = db_all[active].copy()
        print(f"날짜 필터: {len(classified_db)}→{len(db_all)}건 (종료 행사 제거)")

    # 도별 이미 선택된 top-1 event_name 추적 (복붙 방지)
    province_top1: dict[str, set[str]] = {}

    results: list[dict] = []

    # 점수 내림차순 처리 (고위험 지역 우선 → province_top1 먼저 채움)
    order = scored.sort_values("culture_gap_score", ascending=False)

    for _, reg in order.iterrows():
        region_name: str = reg["region_name"]
        region_province: str = reg.get("province", "")
        region_type: str = reg.get("region_type", "균형 관리형")
        main_reasons: str = reg.get("main_reasons", "")

        # 지역 centroid
        centroid = centroids.get(region_name)
        region_lat = centroid[0] if centroid else None
        region_lon = centroid[1] if centroid else None

        need_weights = _build_need_weights(region_type, main_reasons)

        db = db_all.copy()
        db["_score"] = db.apply(
            _score_event,
            axis=1,
            need_weights=need_weights,
            target_region=region_name,
            target_province=region_province,
            region_type=region_type,
            region_lat=region_lat,
            region_lon=region_lon,
        )

        # 도별 이미 top-1인 행사는 첫 후보에서 패널티
        province_used = province_top1.get(region_province, set())
        for used_name in province_used:
            mask = db["event_name"] == used_name
            db.loc[mask, "_score"] -= _REPEAT_PENALTY

        # 다양성 보장 재랭킹
        top = _diversity_rerank(db.nlargest(top_n * 4, "_score"), top_n)

        first = True
        for rank, (_, ev) in enumerate(top.iterrows(), start=1):
            if first:
                province_top1.setdefault(region_province, set()).add(
                    str(ev.get("event_name", ""))
                )
                first = False

            # 지리 노트
            ev_region = str(ev.get("region_name", ""))
            ev_province = str(ev.get("province", ""))
            if ev_region == region_name:
                geo_note = "동일 시군구"
            elif ev_province == region_province:
                geo_note = "동일 시도"
            else:
                geo_note = "타 시도"

            # 실제 거리 계산 (결과 표시용)
            ev_lat = ev.get("latitude")
            ev_lon = ev.get("longitude")
            dist_str = ""
            if (region_lat and region_lon
                    and ev_lat is not None and not pd.isna(ev_lat)
                    and ev_lon is not None and not pd.isna(ev_lon)):
                try:
                    d = _haversine_km(region_lat, region_lon, float(ev_lat), float(ev_lon))
                    dist_str = f"{d:.1f}km"
                except Exception:
                    pass

            ev["_geo_note"] = f"{geo_note}" + (f" ({dist_str})" if dist_str else "")
            reason = _explain_match(ev, need_weights)

            results.append({
                "region_name": region_name,
                "region_province": region_province,
                "region_type": region_type,
                "rank": rank,
                "event_name": ev.get("event_name", ""),
                "detail_genre": ev.get("detail_genre", ev.get("event_type", "")),
                "place": ev.get("place", ""),
                "event_province": ev_province,
                "source": ev.get("source", ""),
                "tag_genre": ev.get("tag_genre", ""),
                "tag_target": ev.get("tag_target", ""),
                "tag_time": ev.get("tag_time", ""),
                "tag_price": ev.get("tag_price", ""),
                "start_date": str(ev.get("start_date", ""))[:10],
                "end_date": str(ev.get("end_date", ""))[:10],
                "distance_km": dist_str,
                "event_url": ev.get("event_url", ""),
                "match_score": round(ev["_score"], 2),
                "match_reason": reason,
            })

    return pd.DataFrame(results)


def summarize_recommendations(matches: pd.DataFrame) -> pd.DataFrame:
    if matches.empty:
        return pd.DataFrame()
    return (
        matches[matches["rank"] == 1]
        .set_index("region_name")[
            ["region_type", "event_name", "tag_genre", "tag_target",
             "tag_price", "match_score", "match_reason"]
        ]
        .copy()
    )


# ---------------------------------------------------------------------------
# 실행 진입점
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os, sys
    os.chdir(Path(__file__).parent.parent)
    sys.path.insert(0, "src")

    from preprocessing import load_raw_data
    from classify_events import build_classified_db, save_classified_db

    raw = load_raw_data()
    db = build_classified_db(raw)
    save_classified_db(db, Path("data/processed/classified_events.csv"))

    scored = pd.read_csv("data/processed/culture_gap_scores.csv", encoding="utf-8-sig")
    target = scored[scored["culture_gap_score"] >= 60].copy()
    print(f"매칭 대상: {len(target)}개 시군구")

    matches = match_events_to_regions(target, db, top_n=10)
    matches.to_csv("data/processed/event_recommendations.csv", index=False, encoding="utf-8-sig")

    summary = summarize_recommendations(matches)
    summary.to_csv("outputs/tables/recommendations_summary.csv", encoding="utf-8-sig")
    print(f"완료: {len(matches)}행 추천 생성")

    # 품질 검증
    print("\n=== 품질 지표 ===")
    print(f"Top-1 행사 고유 수: {summary['event_name'].nunique()} / {len(summary)} 지역")
    print(f"Top-1 가격 분포:\n{summary['tag_price'].value_counts().to_string()}")
    print(f"Top-1 대상 분포:\n{summary['tag_target'].value_counts().to_string()}")

    print("\n=== 결핍 유형별 샘플 ===")
    scored_with_type = scored[["region_name", "culture_gap_score", "region_type"]].merge(
        summary.reset_index(), on="region_name", how="inner"
    )
    for rtype in ["고령층 교통취약형", "시설·행사 부족형", "교통 취약형", "균형 관리형"]:
        s = scored_with_type[scored_with_type["region_type_y"] == rtype].sort_values(
            "culture_gap_score", ascending=False
        ).head(3)
        print(f"\n[{rtype}]")
        for _, r in s.iterrows():
            print(f"  {r['region_name']}({r['culture_gap_score']:.1f}점) → {str(r['event_name'])[:28]}"
                  f" [{r['tag_genre']}/{r['tag_target']}/{r['tag_price']}]")
