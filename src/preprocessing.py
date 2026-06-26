from __future__ import annotations

import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RAW_DIR = Path("data/raw")


PROVINCE_MAP = {
    "서울": "서울특별시",
    "서울특별시": "서울특별시",
    "서울시": "서울특별시",
    "부산": "부산광역시",
    "부산광역시": "부산광역시",
    "대구": "대구광역시",
    "대구광역시": "대구광역시",
    "인천": "인천광역시",
    "인천광역시": "인천광역시",
    "광주": "광주광역시",
    "광주광역시": "광주광역시",
    "대전": "대전광역시",
    "대전광역시": "대전광역시",
    "울산": "울산광역시",
    "울산광역시": "울산광역시",
    "세종": "세종특별자치시",
    "세종특별자치시": "세종특별자치시",
    "경기": "경기도",
    "경기도": "경기도",
    "강원": "강원특별자치도",
    "강원특별자치도": "강원특별자치도",
    "강원도": "강원특별자치도",
    "충북": "충청북도",
    "충청북도": "충청북도",
    "충남": "충청남도",
    "충청남도": "충청남도",
    "전북": "전북특별자치도",
    "전북특별자치도": "전북특별자치도",
    "전라북도": "전북특별자치도",
    "전남": "전라남도",
    "전라남도": "전라남도",
    "경북": "경상북도",
    "경상북도": "경상북도",
    "경남": "경상남도",
    "경상남도": "경상남도",
    "제주": "제주특별자치도",
    "제주특별자치도": "제주특별자치도",
}

METRO_PROVINCES = {
    "서울특별시",
    "부산광역시",
    "대구광역시",
    "인천광역시",
    "광주광역시",
    "대전광역시",
    "울산광역시",
}

TARGET_KEYWORDS = {
    "youth": ["청소년", "진로", "창작", "캠프", "미디어", "워크숍", "교육"],
    "elderly": ["고령", "시니어", "낮 시간", "생활문화", "건강", "복지"],
    "tourism": ["관광", "축제", "체험", "해변", "지역문화"],
    "resident": ["주민", "동네", "생활문화", "마을", "문화교실"],
}


def find_raw_file(patterns: list[str]) -> Path | None:
    for pattern in patterns:
        matches = sorted(RAW_DIR.glob(pattern))
        if matches:
            return matches[0]
    return None


def read_csv_auto(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, encoding="latin1")


def strip_prefix(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    text = re.sub(r"^\d+\.\s*", "", text)
    return text


def normalize_province(text: str) -> str:
    cleaned = strip_prefix(text)
    return PROVINCE_MAP.get(cleaned, cleaned)


def make_region_name(province: str | None, sigungu: str | None) -> str:
    province_name = normalize_province(province or "")
    sigungu_name = strip_prefix(sigungu or "")
    if not province_name:
        return sigungu_name
    if not sigungu_name:
        return province_name
    return f"{province_name} {sigungu_name}"


def parse_region_from_raw_text(text: str) -> tuple[str, str | None, str | None]:
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", str(text).strip())
    parts = cleaned.split()
    if len(parts) >= 2:
        province = normalize_province(parts[0])
        region_name = cleaned
        return region_name, province, " ".join(parts[1:])
    return cleaned, None, None


# ---------------------------------------------------------------------------
# Population: 시군구 단위 직접 파싱 (또는 시도→시군구 비례 배분 폴백)
# ---------------------------------------------------------------------------

def _parse_numeric_col(df: pd.DataFrame, col: str | None) -> pd.Series:
    if col is None:
        return pd.Series(0, index=df.index)
    return pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce").fillna(0)


def _parse_sigungu_population(path: Path) -> pd.DataFrame:
    """행정안전부 연령별인구현황 CSV(시군구 포함 버전)를 직접 파싱."""
    df = read_csv_auto(path)

    total_col = next((c for c in df.columns if c.endswith("_계_총인구수")), None)
    youth_col = next((c for c in df.columns if c.endswith("_계_10~19세")), None)
    elderly_cols = [
        c for c in df.columns
        if any(x in c for x in ["_계_60~69세", "_계_70~79세", "_계_80~89세", "_계_90~99세", "_계_100세 이상"])
    ]
    if total_col is None:
        return pd.DataFrame()

    codes = df["행정구역"].astype(str).str.extract(r"\((\d+)\)")[0]
    region_names = (
        df["행정구역"].astype(str)
        .str.replace(r"\s*\([^)]*\)\s*$", "", regex=True)
        .str.strip()
    )

    # 시도: code[2:] == '00000000' / 전국: region_name == '전국'
    is_sido = codes.str[2:].eq("00000000") | region_names.eq("전국")
    df_sg = df[~is_sido].copy()
    codes_sg = codes[~is_sido]
    names_sg = region_names[~is_sido]

    population = _parse_numeric_col(df_sg, total_col)
    youth_pop = _parse_numeric_col(df_sg, youth_col)
    elderly_pop = (
        df_sg[elderly_cols]
        .apply(lambda s: pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce"))
        .sum(axis=1)
        if elderly_cols else pd.Series(0, index=df_sg.index)
    )

    province = names_sg.str.split().str[0].map(normalize_province)
    sigungu = names_sg.str.split(n=1).str[1].fillna("").str.strip()
    region_name = (province + " " + sigungu).str.strip()

    codes_arr = pd.Series(codes_sg.values, dtype=str)

    # trailing zeros 기반으로 시(市) 총합 행 식별 (6개 trailing zeros)
    # 구(區) 하위 행정구역이 있는 시 총합 행 제거 → double counting 방지
    trailing_zeros = codes_arr.apply(lambda c: len(c) - len(c.rstrip("0")) if c == c else 0)
    city_prefix = codes_arr.str[:4]
    prefix_counts = city_prefix.value_counts()
    has_gu_subrows = city_prefix.map(prefix_counts) > 1  # 같은 앞4자리 코드가 여러 개 → 구 하위 행
    is_city_total = (trailing_zeros == 6) & has_gu_subrows

    valid = ~is_city_total.values

    out = pd.DataFrame({
        "region_code": codes_arr[valid].values,
        "region_name": region_name.values[valid],
        "province": province.values[valid],
        "population": population.values[valid],
        "youth_ratio": (youth_pop.values[valid] / np.where(population.values[valid] > 0, population.values[valid], np.nan) * 100),
        "elderly_ratio": (elderly_pop.values[valid] / np.where(population.values[valid] > 0, population.values[valid], np.nan) * 100),
        "single_household_ratio": 30.0,
    })
    out["youth_ratio"] = out["youth_ratio"].fillna(0)
    out["elderly_ratio"] = out["elderly_ratio"].fillna(0)
    out = out[out["population"] > 0].copy()
    return out[["region_code", "region_name", "province", "population", "youth_ratio", "elderly_ratio", "single_household_ratio"]]


def _read_province_population(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """시도 단위 인구 CSV 읽기 → (province, population, youth_ratio, elderly_ratio) 반환."""
    path = find_raw_file(["*연령별인구현황*csv"])
    if path is None:
        return pd.DataFrame()
    df = read_csv_auto(path)
    total_col = next((c for c in df.columns if c.endswith("_계_총인구수")), None)
    youth_col = next((c for c in df.columns if c.endswith("_계_10~19세")), None)
    elderly_cols = [
        c for c in df.columns
        if any(x in c for x in ["_계_60~69세", "_계_70~79세", "_계_80~89세", "_계_90~99세", "_계_100세 이상"])
    ]
    if total_col is None:
        return pd.DataFrame()

    code_match = df["행정구역"].astype(str).str.extract(r"\((\d+)\)")
    region_name = df["행정구역"].astype(str).str.replace(r"\s*\([^)]*\)\s*$", "", regex=True).str.strip()

    out = pd.DataFrame({
        "region_code": code_match[0],
        "region_name": region_name,
        "province": region_name.str.split().str[0].map(normalize_province),
        "population": pd.to_numeric(df[total_col].astype(str).str.replace(",", ""), errors="coerce"),
        "youth_population": pd.to_numeric(df[youth_col].astype(str).str.replace(",", ""), errors="coerce") if youth_col else 0,
    })
    if elderly_cols:
        elderly_num = df[elderly_cols].apply(lambda s: pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce"))
        out["elderly_population"] = elderly_num.sum(axis=1)
    else:
        out["elderly_population"] = 0

    out = out[out["population"].notna() & out["region_name"].ne("전국")].copy()
    out["youth_ratio"] = out["youth_population"] / out["population"] * 100
    out["elderly_ratio"] = out["elderly_population"] / out["population"] * 100
    out["single_household_ratio"] = 30.0
    return out[["region_code", "region_name", "province", "population", "youth_ratio", "elderly_ratio", "single_household_ratio"]]


def _is_sigungu_level(sigungu: str) -> bool:
    """시군구 단위인지 확인 (읍·면·동·리 등 하위 행정구역 및 오염 값 제외)."""
    sg = sigungu.strip()
    if not sg or sg in ("-", "nan", "None"):
        return False
    # 복수 구 이름 (쉼표 포함) 제외
    if "," in sg or "·" in sg:
        return False
    # 읍·면·동·리 로 끝나는 하위 행정구역 제외
    if re.search(r"(읍|면|동|리|로|길)$", sg):
        return False
    # 시군구가 아닌 숫자나 특수문자만 있는 경우 제외
    if not re.search(r"[\w가-힣]", sg):
        return False
    return True


def _normalize_sigungu(province: str, sigungu: str) -> str:
    """세종시처럼 도시명=도 이름인 경우 정규화."""
    sg = sigungu.strip()
    # 세종특별자치시 내부 '세종', '세종시' → 동일 처리
    if province == "세종특별자치시" and sg in ("세종", "세종시", "세종특별자치시"):
        return "세종시"
    return sg


def _build_sigungu_weights(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """이벤트 + 축제 기반으로 (province, sigungu, weight) 생성.
    시·군·구 단위만 포함하고 읍·면·동 하위 단위는 제외한다."""
    rows: list[dict] = []

    ev_path = find_raw_file(["culture_events.csv"])
    if ev_path:
        ev = read_csv_auto(ev_path)
        for (area, sigungu), grp in ev.groupby(["area", "sigungu"], dropna=True):
            prov = normalize_province(str(area))
            sg = _normalize_sigungu(prov, strip_prefix(str(sigungu)))
            if _is_sigungu_level(sg):
                rows.append({"province": prov, "sigungu": sg, "ev_count": len(grp)})

    fest_path = find_raw_file(["*festival*.zip"])
    if fest_path:
        fest = standardize_festivals(raw_dir)
        for (prov, sigungu), grp in fest.groupby(["province", "sigungu"], dropna=True):
            sg = _normalize_sigungu(str(prov), str(sigungu).strip())
            if _is_sigungu_level(sg):
                rows.append({"province": prov, "sigungu": sg, "fest_count": len(grp)})

    if not rows:
        return pd.DataFrame(columns=["province", "sigungu", "weight"])

    df = pd.DataFrame(rows)
    agg_dict: dict = {}
    if "ev_count" in df.columns:
        agg_dict["ev_count"] = ("ev_count", "sum")
    if "fest_count" in df.columns:
        agg_dict["fest_count"] = ("fest_count", "sum")
    if not agg_dict:
        agg_dict["n"] = ("sigungu", "count")

    df = df.groupby(["province", "sigungu"]).agg(**agg_dict).reset_index().fillna(0)
    df["weight"] = df.get("ev_count", pd.Series(0, index=df.index)) + df.get("fest_count", pd.Series(0, index=df.index)) * 0.5
    df["weight"] = df["weight"].clip(lower=1.0)
    return df[["province", "sigungu", "weight"]]


def standardize_population(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """시군구 단위 인구 DataFrame 반환.

    시군구 직접 파일(sigungu_age_pop_*.csv)이 있으면 우선 사용,
    없으면 시도 인구를 이벤트 가중치로 비례 배분.
    """
    sigungu_path = find_raw_file(["sigungu_age_pop_*.csv"])
    if sigungu_path:
        result = _parse_sigungu_population(sigungu_path)
        if not result.empty:
            return result

    province_pop = _read_province_population(raw_dir)
    if province_pop.empty:
        return pd.DataFrame()

    weights = _build_sigungu_weights(raw_dir)
    if weights.empty:
        return province_pop

    # 시도명 정규화
    province_pop["province"] = province_pop["region_name"].str.split().str[0].map(normalize_province)
    province_pop = province_pop.set_index("province")

    records: list[dict] = []
    for province, grp in weights.groupby("province"):
        if province not in province_pop.index:
            continue
        prow = province_pop.loc[province]
        total_weight = grp["weight"].sum()
        for _, sg_row in grp.iterrows():
            share = sg_row["weight"] / total_weight
            region_name = f"{province} {sg_row['sigungu']}"
            records.append({
                "region_code": "",
                "region_name": region_name,
                "province": province,
                "population": round(prow["population"] * share),
                "youth_ratio": prow["youth_ratio"],
                "elderly_ratio": prow["elderly_ratio"],
                "single_household_ratio": prow["single_household_ratio"],
            })

    # 세종·제주처럼 시군구 없이 단독인 시도 처리
    assigned_provinces = set(weights["province"].unique())
    for province, prow in province_pop.iterrows():
        if province not in assigned_provinces:
            records.append({
                "region_code": prow.get("region_code", ""),
                "region_name": province,
                "province": province,
                "population": prow["population"],
                "youth_ratio": prow["youth_ratio"],
                "elderly_ratio": prow["elderly_ratio"],
                "single_household_ratio": prow["single_household_ratio"],
            })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Bus stops: 광역시 단위 → 구 단위 비례 배분
# ---------------------------------------------------------------------------

def _get_metro_gu_ev_counts(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """광역시 구별 이벤트 건수 반환 (버스정류장 배분용)."""
    ev_path = find_raw_file(["culture_events.csv"])
    if ev_path is None:
        return pd.DataFrame(columns=["province", "sigungu", "ev_count"])
    ev = read_csv_auto(ev_path)
    ev["province"] = ev["area"].astype(str).map(normalize_province)
    ev = ev[ev["province"].isin(METRO_PROVINCES)]
    ev["sigungu"] = ev["sigungu"].astype(str).apply(strip_prefix)
    grp = ev.groupby(["province", "sigungu"]).size().reset_index(name="ev_count")
    return grp[grp["sigungu"].str.strip().ne("")]


def standardize_bus_stops(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """버스정류장 데이터를 시군구 단위로 반환.
    광역시 단일 항목은 이벤트 건수에 비례해 구별로 배분한다."""
    path = find_raw_file(["*버스정류장*csv"])
    if path is None:
        return pd.DataFrame()
    df = read_csv_auto(path)

    city_col = "도시명"
    is_two_word = df[city_col].str.split().str.len() >= 2
    도_rows = df[is_two_word].copy()
    metro_rows = df[~is_two_word].copy()

    # 도 단위: "경기도 수원시" → province + sigungu
    parts = 도_rows[city_col].str.split(n=1, expand=True)
    도_rows["province"] = parts[0].map(normalize_province)
    도_rows["sigungu"] = parts[1].fillna("").str.strip()
    도_rows["region_name"] = 도_rows["province"] + " " + 도_rows["sigungu"]
    도_rows["bus_stop_id"] = df.loc[is_two_word, "정류장번호"].astype(str)
    도_rows["bus_stop_name"] = df.loc[is_two_word, "정류장명"].astype(str)
    도_rows["latitude"] = pd.to_numeric(df.loc[is_two_word, "위도"], errors="coerce")
    도_rows["longitude"] = pd.to_numeric(df.loc[is_two_word, "경도"], errors="coerce")

    # 광역시: 이벤트 비례로 구별 가상 행 생성
    metro_gu_ev = _get_metro_gu_ev_counts(raw_dir)
    metro_expanded_parts: list[pd.DataFrame] = []

    for city_name, city_grp in metro_rows.groupby(city_col):
        province = normalize_province(str(city_name))
        city_stop_count = len(city_grp)
        gu_list = metro_gu_ev[metro_gu_ev["province"] == province].copy()
        if gu_list.empty:
            # 구 정보 없으면 시 단위 그대로 유지
            sub = city_grp[["정류장번호", "정류장명", "위도", "경도"]].copy()
            sub.columns = ["bus_stop_id", "bus_stop_name", "latitude", "longitude"]
            sub["region_name"] = province
            sub["province"] = province
            sub["sigungu"] = ""
            sub["latitude"] = pd.to_numeric(sub["latitude"], errors="coerce")
            sub["longitude"] = pd.to_numeric(sub["longitude"], errors="coerce")
            metro_expanded_parts.append(sub)
            continue

        total_ev = gu_list["ev_count"].sum()
        gu_list["stop_count"] = (gu_list["ev_count"] / total_ev * city_stop_count).round().astype(int)
        gu_list["stop_count"] = gu_list["stop_count"].clip(lower=1)

        rows = []
        for _, gu_row in gu_list.iterrows():
            for i in range(int(gu_row["stop_count"])):
                rows.append({
                    "region_name": f"{province} {gu_row['sigungu']}",
                    "province": province,
                    "sigungu": gu_row["sigungu"],
                    "bus_stop_id": f"{province}_{gu_row['sigungu']}_{i}",
                    "bus_stop_name": "",
                    "latitude": np.nan,
                    "longitude": np.nan,
                })
        metro_expanded_parts.append(pd.DataFrame(rows))

    out_parts = [도_rows[["region_name", "province", "sigungu", "bus_stop_id", "bus_stop_name", "latitude", "longitude"]]]
    out_parts.extend(metro_expanded_parts)
    return pd.concat(out_parts, ignore_index=True)


# ---------------------------------------------------------------------------
# Culture events
# ---------------------------------------------------------------------------

def standardize_culture_events(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    path = find_raw_file(["culture_events.csv"])
    if path is None:
        return pd.DataFrame()
    df = read_csv_auto(path)
    df["region_name"] = df.apply(lambda r: make_region_name(r.get("area"), r.get("sigungu")), axis=1)
    text = (
        df["title"].fillna("").astype(str)
        + " "
        + df["realmName"].fillna("").astype(str)
        + " "
        + df["place"].fillna("").astype(str)
        + " "
        + df["serviceName"].fillna("").astype(str)
    )
    out = pd.DataFrame({
        "region_name": df["region_name"],
        "province": df["area"].astype(str).map(normalize_province),
        "event_name": df["title"].astype(str),
        "event_type": df["realmName"].astype(str),
        "service_name": df["serviceName"].astype(str),
        "start_date": df["startDate"],
        "end_date": df["endDate"],
        "place": df["place"].astype(str),
        "latitude": pd.to_numeric(df["gpsY"], errors="coerce"),
        "longitude": pd.to_numeric(df["gpsX"], errors="coerce"),
        "seq": df.get("seq", pd.Series(pd.NA, index=df.index)),
        "is_free": text.str.contains("무료|free", case=False, regex=True).astype(int),
        "is_youth": text.str.contains("|".join(TARGET_KEYWORDS["youth"]), case=False, regex=True).astype(int),
        "is_elderly": text.str.contains("|".join(TARGET_KEYWORDS["elderly"]), case=False, regex=True).astype(int),
        "is_tourism": text.str.contains("|".join(TARGET_KEYWORDS["tourism"]), case=False, regex=True).astype(int),
        "is_resident": text.str.contains("|".join(TARGET_KEYWORDS["resident"]), case=False, regex=True).astype(int),
    })
    return out


# ---------------------------------------------------------------------------
# Museums
# ---------------------------------------------------------------------------

def standardize_museums(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    path = find_raw_file(["museum_artgr_standard.csv"])
    if path is None:
        return pd.DataFrame()
    df = read_csv_auto(path)
    # insttNm 형식: "서울특별시 종로구", "경기도 김포시" → 그대로 region_name으로 사용
    region_name = df["insttNm"].astype(str).str.strip()
    # 주소에서 보강: insttNm이 시도 단독인 경우 rdnmadr 1·2번째 단어 사용
    addr_parts = df["rdnmadr"].astype(str).str.split(n=2)
    addr_province = addr_parts.str[0].map(normalize_province)
    addr_sigungu = addr_parts.str[1].fillna("")
    addr_region = addr_province + " " + addr_sigungu
    region_name = region_name.where(
        region_name.str.split().str.len() >= 2,
        addr_region.str.strip()
    )
    province = region_name.str.split().str[0].map(normalize_province)

    charge_cols = [c for c in ["adultChrge", "yngbgsChrge", "childChrge"] if c in df.columns]
    charge_frame = df[charge_cols].astype(str).replace(",", "", regex=True)
    free_mask = charge_frame.fillna("0").apply(
        lambda col: col.map(lambda x: str(x).strip() in {"0", "0.0", "", "무료"})
    ).all(axis=1)

    out = pd.DataFrame({
        "region_name": region_name,
        "province": province,
        "museum_name": df["fcltyNm"].astype(str),
        "facility_type": df["fcltyType"].astype(str),
        "address": df["rdnmadr"].astype(str),
        "latitude": pd.to_numeric(df["latitude"], errors="coerce"),
        "longitude": pd.to_numeric(df["longitude"], errors="coerce"),
        "is_free": free_mask.astype(int),
        "has_transport": df.get("trnsportInfo", "").astype(str).str.strip().ne(""),
    })
    return out


# ---------------------------------------------------------------------------
# Facilities (raw, used for national diversity metrics only)
# ---------------------------------------------------------------------------

def standardize_facilities(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    path = find_raw_file(["culture_facilities.csv"])
    if path is None:
        return pd.DataFrame()
    return read_csv_auto(path)


# ---------------------------------------------------------------------------
# Festivals (xlsx inside zip)
# ---------------------------------------------------------------------------

def _read_xlsx_sheet_rows(zip_path: Path) -> list[list[str]]:
    def col_index(cell_ref: str) -> int:
        m = re.match(r"([A-Z]+)", cell_ref)
        if not m:
            return 0
        n = 0
        for ch in m.group(1):
            n = n * 26 + (ord(ch) - 64)
        return n - 1

    with zipfile.ZipFile(zip_path) as outer:
        xlsx_name = next((name for name in outer.namelist() if name.lower().endswith(".xlsx")), None)
        if xlsx_name is None:
            return []
        with zipfile.ZipFile(io.BytesIO(outer.read(xlsx_name))) as z:
            names = z.namelist()
            workbook = ET.fromstring(z.read("xl/workbook.xml"))
            rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            rel_map = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
            sheets = workbook.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets")
            target = None
            for sheet in sheets:
                if sheet.attrib.get("name") == "조사표":
                    rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
                    target = rel_map[rid]
                    break
            if target is None:
                return []
            sheet_path = target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                shared_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in shared_root.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                    shared.append(
                        "".join(t.text or "" for t in si.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
                    )
            sheet = ET.fromstring(z.read(sheet_path))
            rows_out: list[list[str]] = []
            for row in sheet.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
                values: dict[int, str] = {}
                for cell in row.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                    idx = col_index(cell.attrib.get("r", "A1"))
                    t = cell.attrib.get("t")
                    v = cell.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                    if v is None:
                        value = ""
                    else:
                        value = v.text or ""
                        if t == "s":
                            value = shared[int(value)]
                    values[idx] = value
                if values:
                    max_idx = max(values)
                    rows_out.append([values.get(i, "") for i in range(max_idx + 1)])
            return rows_out


def standardize_festivals(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    zip_path = find_raw_file(["*festival*.zip"])
    if zip_path is None:
        return pd.DataFrame()
    rows = _read_xlsx_sheet_rows(zip_path)
    if len(rows) < 8:
        return pd.DataFrame()
    records: list[dict[str, Any]] = []
    for row in rows[7:]:
        if not any(str(v).strip() for v in row):
            continue
        province = row[8] if len(row) > 8 else ""
        sigungu = row[9] if len(row) > 9 else ""
        region_name = make_region_name(province, sigungu)
        record = {
            "region_name": region_name,
            "province": normalize_province(province),
            "sigungu": strip_prefix(sigungu),
            "festival_name": row[4] if len(row) > 4 else "",
            "festival_type": strip_prefix(row[5]) if len(row) > 5 else "",
            "place_name": row[6] if len(row) > 6 else "",
            "place_type": strip_prefix(row[7]) if len(row) > 7 else "",
            "start_year": row[11] if len(row) > 11 else "",
            "start_month": row[12] if len(row) > 12 else "",
            "start_day": row[13] if len(row) > 13 else "",
            "end_year": row[14] if len(row) > 14 else "",
            "end_month": row[15] if len(row) > 15 else "",
            "end_day": row[16] if len(row) > 16 else "",
            "festival_days": row[17] if len(row) > 17 else "",
            "cycle": strip_prefix(row[19]) if len(row) > 19 else "",
            "first_year": row[20] if len(row) > 20 else "",
            "budget_total": pd.to_numeric(row[21] if len(row) > 21 else "", errors="coerce"),
            "budget_national": pd.to_numeric(row[22] if len(row) > 22 else "", errors="coerce"),
            "budget_local": pd.to_numeric(row[23] if len(row) > 23 else "", errors="coerce"),
            "budget_private": pd.to_numeric(row[24] if len(row) > 24 else "", errors="coerce"),
            "support_ministry": row[25] if len(row) > 25 else "",
            "visitor_total": pd.to_numeric(row[26] if len(row) > 26 else "", errors="coerce"),
            "visitor_local": pd.to_numeric(row[27] if len(row) > 27 else "", errors="coerce"),
            "visitor_foreign": pd.to_numeric(row[28] if len(row) > 28 else "", errors="coerce"),
        }
        records.append(record)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def load_raw_data(raw_dir: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    return {
        "population": standardize_population(raw_dir),
        "bus_stops": standardize_bus_stops(raw_dir),
        "events": standardize_culture_events(raw_dir),
        "museums": standardize_museums(raw_dir),
        "festivals": standardize_festivals(raw_dir),
        "facilities": standardize_facilities(raw_dir),
    }
