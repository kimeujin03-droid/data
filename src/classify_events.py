"""1단: 행사·축제 자동 태깅 (4개 축: 장르·대상계층·시간대·가격)."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# 장르 매핑
# ---------------------------------------------------------------------------
_GENRE_FROM_EVENT_TYPE: dict[str, str] = {
    "음악/콘서트": "공연",
    "뮤지컬/오페라": "공연",
    "연극": "공연",
    "무용/발레": "공연",
    "국악": "공연",
    "전시": "전시",
    "교육/체험": "체험·교육",
    "행사/축제": "축제",
    "아동/가족": "공연",
    "기타": "기타",
}
_GENRE_FROM_FESTIVAL_TYPE: dict[str, str] = {
    "문화예술": "공연",
    "지역특산물": "체험·교육",
    "자연생태": "체험·교육",
    "주민화합": "축제",
    "전통역사": "체험·교육",
}

# ---------------------------------------------------------------------------
# 키워드 사전
# ---------------------------------------------------------------------------

# 대상계층: 명시적으로 "대상" 의미가 강한 키워드만 사용 (주제가 아닌 수혜자)
_ELDERLY_KW = [
    "시니어", "어르신", "경로", "실버", "노인 대상", "노인을 위",
    "노인여가", "노인복지", "시니어프로그램", "생활문화센터",
]
_YOUTH_KW = [
    "청소년", "청년", "학생 대상", "청소년 대상", "진로", "방과후",
    "청소년프로그램", "청년지원", "학교 연계",
]
_CHILD_KW = [
    "아동", "어린이", "유아", "영아", "키즈", "영·유아",
    "어린이집", "유치원", "동화", "동요", "인형극",
]
# 가족은 타겟이 명확할 때만 ("가족 대상", "가족과 함께" 등)
_FAMILY_KW = ["가족과 함께", "온 가족", "가족 대상", "가족 프로그램", "부모와 아이"]

_NIGHT_KW = [
    "야간", "나이트", "야경", "불꽃", "별빛", "나이트콘서트",
    "night", "야간개장", "달빛",
]
_FESTIVAL_ALLDAY_KW = ["축제", "페스티벌", "festival"]

_FREE_KW = ["무료", "공짜", "입장무료", "관람무료", "무료입장", "무료관람", "무료 프로그램"]
_PAID_KW = ["유료", "R석", "S석", "VIP석", "전석 유료"]

# 장르별 기본 가격 (원본 데이터에 가격 없음 → 장르·유형으로 합리적 추론)
# 전문 공연(음악/콘서트·뮤지컬·연극·무용) = 유료 / 전시·교육·축제 = 무료
_GENRE_DEFAULT_PRICE: dict[str, str] = {
    "음악/콘서트": "유료",
    "뮤지컬/오페라": "유료",
    "연극": "유료",
    "무용/발레": "유료",
    "국악": "유료",
    "전시": "무료·저비용",
    "교육/체험": "무료·저비용",
    "행사/축제": "무료·저비용",
    "아동/가족": "유료",   # 어린이 공연은 대체로 유료
    "기타": "무료·저비용",
}


def _kw_match(text: str, keywords: list[str]) -> bool:
    t = str(text).lower()
    return any(k in t for k in keywords)


# ---------------------------------------------------------------------------
# 핵심 분류 함수
# ---------------------------------------------------------------------------
def _classify_target(name: str, event_type: str) -> str:
    """대상계층 분류 — 수혜자(target audience)가 명확한 경우만 분류."""
    if event_type in ("아동/가족",):
        return "가족·아동"
    text = str(name)
    # 가족 키워드 우선 (어린이+부모 조합)
    if _kw_match(text, _FAMILY_KW):
        return "가족·아동"
    # 어린이·유아 단독
    if _kw_match(text, _CHILD_KW):
        return "가족·아동"
    # 청소년 (교육 단독은 제외 — 너무 광범위)
    if _kw_match(text, _YOUTH_KW):
        return "청소년·교육"
    # 고령 — "노인의 꿈" 같은 소재 작품 제외, 수혜자 명시 키워드만
    if _kw_match(text, _ELDERLY_KW):
        return "고령친화"
    return "일반·전문"


def _classify_time(name: str, place: str = "") -> str:
    """시간대 분류 (야간 / 종일 / 주간)."""
    text = str(name) + " " + str(place)
    if _kw_match(text, _NIGHT_KW):
        return "야간"
    if _kw_match(text, _FESTIVAL_ALLDAY_KW):
        return "종일"
    return "주간"


def _classify_price(name: str, event_type: str = "", is_free_flag: int = 0) -> str:
    """가격 분류 — 제목 키워드 우선, 없으면 장르 기반 추론."""
    text = str(name)
    # 제목에 명시된 경우 최우선
    if _kw_match(text, _FREE_KW):
        return "무료·저비용"
    if _kw_match(text, _PAID_KW):
        return "유료"
    if is_free_flag == 1:
        return "무료·저비용"
    # 장르 기반 기본값
    return _GENRE_DEFAULT_PRICE.get(event_type, "무료·저비용")


_CULTURE_URL_BASE = "https://www.culture.go.kr/cultureinfo/content.do?id="


def _make_event_url(seq) -> str:
    if pd.isna(seq) or str(seq).strip() in ("", "nan"):
        return ""
    return f"{_CULTURE_URL_BASE}{int(seq)}"


# ---------------------------------------------------------------------------
# 이벤트 분류
# ---------------------------------------------------------------------------
def classify_events(events: pd.DataFrame) -> pd.DataFrame:
    """culture_events 행사에 4개 태그 + 날짜·좌표·URL·세부장르 컬럼 추가."""
    out = events.copy()
    event_type = out.get("event_type", pd.Series("기타", index=out.index)).fillna("기타")
    event_name = out.get("event_name", pd.Series("", index=out.index)).fillna("")
    place = out.get("place", pd.Series("", index=out.index)).fillna("")
    is_free = out.get("is_free", pd.Series(0, index=out.index)).fillna(0).astype(int)

    # 4개 태그
    out["tag_genre"] = event_type.map(_GENRE_FROM_EVENT_TYPE).fillna("기타")
    out["detail_genre"] = event_type   # 세부 장르 (연극, 음악/콘서트 등)
    out["tag_target"] = [_classify_target(n, t) for n, t in zip(event_name, event_type)]
    out["tag_time"] = [_classify_time(n, p) for n, p in zip(event_name, place)]
    out["tag_price"] = [_classify_price(n, t, f) for n, t, f in zip(event_name, event_type, is_free)]

    # 날짜 (YYYYMMDD → date 문자열 유지, 정렬/필터에 사용)
    out["start_date"] = pd.to_datetime(
        out.get("start_date", pd.Series(pd.NaT, index=out.index)), format="%Y%m%d", errors="coerce"
    )
    out["end_date"] = pd.to_datetime(
        out.get("end_date", pd.Series(pd.NaT, index=out.index)), format="%Y%m%d", errors="coerce"
    )

    # 위도·경도
    out["latitude"] = pd.to_numeric(out.get("latitude", pd.Series(pd.NA, index=out.index)), errors="coerce")
    out["longitude"] = pd.to_numeric(out.get("longitude", pd.Series(pd.NA, index=out.index)), errors="coerce")

    # culture.go.kr 직접 링크 (seq 컬럼이 있는 경우)
    if "seq" in out.columns:
        out["event_url"] = out["seq"].apply(_make_event_url)
    else:
        out["event_url"] = ""

    return out


# ---------------------------------------------------------------------------
# 축제 분류
# ---------------------------------------------------------------------------
def classify_festivals(festivals: pd.DataFrame) -> pd.DataFrame:
    """festival 행에 4개 태그 + 날짜·세부장르 컬럼 추가."""
    out = festivals.copy()
    fname = out.get("festival_name", pd.Series("", index=out.index)).fillna("")
    ftype = out.get("festival_type", pd.Series("", index=out.index)).fillna("")
    days = pd.to_numeric(out.get("festival_days", pd.Series(1, index=out.index)), errors="coerce").fillna(1)

    out["tag_genre"] = ftype.map(_GENRE_FROM_FESTIVAL_TYPE).fillna("축제")
    out["detail_genre"] = ftype
    out["tag_target"] = [_classify_target(n, t) for n, t in zip(fname, ftype)]
    out["tag_time"] = ["종일" if d >= 2 else _classify_time(n) for n, d in zip(fname, days)]
    out["tag_price"] = [_classify_price(n, "행사/축제", 1) for n in fname]

    # 날짜: start_month/end_month → 2026-MM-01 형식으로 추정
    sm = pd.to_numeric(out.get("start_month", pd.Series(pd.NA, index=out.index)), errors="coerce")
    em = pd.to_numeric(out.get("end_month", pd.Series(pd.NA, index=out.index)), errors="coerce")
    out["start_date"] = pd.to_datetime(
        "2026-" + sm.astype("Int64").astype(str).str.zfill(2) + "-01", errors="coerce"
    )
    out["end_date"] = pd.to_datetime(
        "2026-" + em.fillna(sm).astype("Int64").astype(str).str.zfill(2) + "-28", errors="coerce"
    )

    out["latitude"] = pd.NA
    out["longitude"] = pd.NA
    out["event_url"] = ""
    return out


# ---------------------------------------------------------------------------
# 통합 실행 / 저장
# ---------------------------------------------------------------------------
def build_classified_db(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """이벤트 + 축제 통합 분류 DB 반환."""
    events = raw.get("events", pd.DataFrame())
    festivals = raw.get("festivals", pd.DataFrame())

    rows: list[pd.DataFrame] = []

    if not events.empty:
        ev = classify_events(events)
        ev["source"] = "event"
        rows.append(ev)

    if not festivals.empty:
        fest = classify_festivals(festivals)
        # festivals 컬럼을 events 컬럼 이름에 맞춤
        col_map = {
            "festival_name": "event_name",
            "festival_type": "event_type",
            "place_name": "place",
        }
        fest = fest.rename(columns=col_map)
        if "is_free" not in fest.columns:
            fest["is_free"] = 1
        fest["source"] = "festival"
        rows.append(fest)

    if not rows:
        return pd.DataFrame()

    db = pd.concat(rows, ignore_index=True, sort=False)
    keep = [
        "region_name", "province", "event_name", "event_type", "place",
        "is_free", "source",
        "tag_genre", "detail_genre", "tag_target", "tag_time", "tag_price",
        "start_date", "end_date",
        "latitude", "longitude",
        "event_url",
    ]
    available = [c for c in keep if c in db.columns]
    return db[available].copy()


def save_classified_db(db: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    db.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"classified_events 저장: {out_path} ({len(db)}행)")


if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).parent.parent)

    try:
        from preprocessing import load_raw_data
    except ImportError:
        from src.preprocessing import load_raw_data  # type: ignore

    raw = load_raw_data()
    db = build_classified_db(raw)
    save_classified_db(db, Path("data/processed/classified_events.csv"))

    print("\n태그 분포:")
    for col in ["tag_genre", "tag_target", "tag_time", "tag_price"]:
        print(f"\n[{col}]")
        print(db[col].value_counts().to_string())
