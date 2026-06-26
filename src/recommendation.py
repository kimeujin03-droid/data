from __future__ import annotations

import pandas as pd


def diagnose_region(row: pd.Series) -> tuple[str, list[str], list[str]]:
    reasons: list[str] = []
    recommendations: list[str] = []

    if row["supply_deficit_score"] >= 65:
        reasons.append("문화시설 또는 행사 공급이 부족함")
        recommendations.append("작은 문화거점과 순회공연을 우선 배치")
    if row["event_score"] <= 35:
        reasons.append("월평균 문화행사 수가 낮음")
        recommendations.append("월 2회 이상 기획 공연/전시 프로그램 편성")
    if row["access_penalty"] >= 65:
        reasons.append("대중교통 및 시설 접근성이 취약함")
        recommendations.append("찾아가는 문화버스와 셔틀 연계")
    if row["elderly_ratio"] >= 30 and row["elderly_program_ratio"] < 0.3:
        reasons.append("고령층 비율 대비 친화 프로그램이 부족함")
        recommendations.append("낮 시간대 무료 생활문화/건강 연계 프로그램 운영")
    if row["youth_ratio"] >= 16 and row["youth_program_ratio"] < 0.3:
        reasons.append("청소년 인구 대비 교육·체험형 프로그램이 부족함")
        recommendations.append("방과후 창작 워크숍과 지역 예술가 멘토링 운영")
    if row["tourism_program_ratio"] >= 0.5 and row["resident_program_ratio"] < 0.3:
        reasons.append("관광형 콘텐츠에 비해 주민 생활문화 공급이 약함")
        recommendations.append("축제 콘텐츠를 연중 주민 프로그램으로 전환")

    if not reasons:
        reasons.append("주요 지표가 비교적 균형적임")
        recommendations.append("현재 공급 수준을 유지하며 취약 계층 프로그램 모니터링")

    region_type = classify_region_type(row)
    return region_type, reasons[:3], recommendations[:3]


def classify_region_type(row: pd.Series) -> str:
    if row["access_penalty"] >= 70 and row["elderly_ratio"] >= 30:
        return "고령층 교통취약형"
    if row["youth_ratio"] >= 16 and row["youth_program_ratio"] < 0.3:
        return "청소년 문화공백형"
    if row["supply_deficit_score"] >= 70:
        return "시설·행사 부족형"
    if row["tourism_program_ratio"] >= 0.5 and row["regular_program_score"] < 0.4:
        return "일회성 축제 의존형"
    if row["access_penalty"] >= 65:
        return "교통 취약형"
    return "균형 관리형"


def add_recommendations(scored: pd.DataFrame) -> pd.DataFrame:
    enriched = scored.copy()
    diagnoses = enriched.apply(diagnose_region, axis=1)
    enriched["region_type"] = [item[0] for item in diagnoses]
    enriched["main_reasons"] = ["; ".join(item[1]) for item in diagnoses]
    enriched["policy_recommendations"] = ["; ".join(item[2]) for item in diagnoses]
    return enriched

