from __future__ import annotations

from pathlib import Path

try:
    from classify_events import build_classified_db, save_classified_db
    from clustering import add_clusters
    from feature_engineering import build_region_features_from_raw
    from match_events import match_events_to_regions, summarize_recommendations
    from preprocessing import load_raw_data
    from recommendation import add_recommendations
    from scoring import add_scores
    from visualization import save_all_charts
except ImportError:  # pragma: no cover
    from .classify_events import build_classified_db, save_classified_db
    from .clustering import add_clusters
    from .feature_engineering import build_region_features_from_raw
    from .match_events import match_events_to_regions, summarize_recommendations
    from .preprocessing import load_raw_data
    from .recommendation import add_recommendations
    from .scoring import add_scores
    from .visualization import save_all_charts


PROCESSED_DIR = Path("data/processed")
TABLE_DIR = Path("outputs/tables")
REPORT_DIR = Path("outputs/reports")
FIGURE_DIR = Path("outputs/figures")


def main() -> None:
    for path in [PROCESSED_DIR, TABLE_DIR, REPORT_DIR, FIGURE_DIR]:
        path.mkdir(parents=True, exist_ok=True)

    raw = load_raw_data()
    features = build_region_features_from_raw(raw)
    scored = add_recommendations(add_clusters(add_scores(features)))

    score_cols = [
        "region_code",
        "province",
        "region_name",
        "population",
        "supply_score",
        "demand_score",
        "access_penalty",
        "mismatch_penalty",
        "culture_gap_score",
        "risk_level",
        "region_type",
        "main_reasons",
        "policy_recommendations",
        "cluster",
    ]
    scored[score_cols].sort_values("culture_gap_score", ascending=False).to_csv(
        PROCESSED_DIR / "culture_gap_scores.csv", index=False, encoding="utf-8-sig"
    )
    features.to_csv(PROCESSED_DIR / "region_features.csv", index=False, encoding="utf-8-sig")
    scored[["region_code", "region_name", "region_type", "cluster"]].to_csv(
        PROCESSED_DIR / "region_clusters.csv", index=False, encoding="utf-8-sig"
    )

    top = scored[score_cols].sort_values("culture_gap_score", ascending=False).head(10)
    top.to_csv(TABLE_DIR / "top_risk_regions.csv", index=False, encoding="utf-8-sig")

    geojson_path = Path("data/raw/sigungu_boundary_full.geojson")
    save_all_charts(scored, FIGURE_DIR, geojson_path)
    write_summary(top, REPORT_DIR / "mvp_summary.md")

    # 1단: 행사 분류 태깅
    classified_db = build_classified_db(raw)
    save_classified_db(classified_db, PROCESSED_DIR / "classified_events.csv")

    # 2단: 결핍 지역 → 행사 매칭
    target = scored[scored["culture_gap_score"] >= 60].copy()
    matches = match_events_to_regions(target, classified_db, top_n=10)
    matches.to_csv(PROCESSED_DIR / "event_recommendations.csv", index=False, encoding="utf-8-sig")

    summary = summarize_recommendations(matches)
    summary.to_csv(TABLE_DIR / "recommendations_summary.csv", encoding="utf-8-sig")

    print("Pipeline complete")
    print(f"- {PROCESSED_DIR / 'culture_gap_scores.csv'}")
    print(f"- {TABLE_DIR / 'top_risk_regions.csv'}")
    print(f"- {REPORT_DIR / 'mvp_summary.md'}")


def write_summary(top, output_path: Path) -> None:
    lines = [
        "# 컬처갭 AI MVP 분석 요약",
        "",
        "실제 raw 데이터를 기반으로 문화결핍지수를 산출했습니다.",
        "현재 인구 원천이 시도 단위라서 출력은 시도 단위로 집계됩니다.",
        "",
        "## 문화 사각지대 상위 후보",
        "",
        "| 순위 | 지역 | 점수 | 등급 | 유형 | 주요 원인 | 추천 전략 |",
        "|---:|---|---:|---|---|---|---|",
    ]
    for rank, (_, row) in enumerate(top.iterrows(), start=1):
        lines.append(
            f"| {rank} | {row['region_name']} | "
            f"{row['culture_gap_score']} | {row['risk_level']} | {row['region_type']} | "
            f"{row['main_reasons']} | {row['policy_recommendations']} |"
        )
    lines.extend(
        [
            "",
            "## 해석",
            "",
            "점수가 높은 지역은 문화수요가 높거나 공급 부족, 교통 취약성, 프로그램 미스매치가 동시에 나타나는 지역입니다. 실제 제출 버전에서는 샘플 데이터를 공공 문화데이터 원천으로 교체해 같은 산식으로 재계산합니다.",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
