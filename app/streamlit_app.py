"""컬처갭 AI — 공공 문화데이터 기반 문화 사각지대 예측지도 대시보드."""
from __future__ import annotations

import json
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------
BASE = Path(__file__).parent.parent
SCORE_PATH = BASE / "data/processed/culture_gap_scores.csv"
REC_PATH   = BASE / "data/processed/event_recommendations.csv"
GEO_PATH   = BASE / "data/raw/sigungu_boundary_full.geojson"
CENTROID_PATH = BASE / "data/processed/region_centroids.json"

# ---------------------------------------------------------------------------
# 데이터 로드
# ---------------------------------------------------------------------------
@st.cache_data
def load_scores() -> pd.DataFrame:
    df = pd.read_csv(SCORE_PATH, encoding="utf-8-sig")
    df["culture_gap_score"] = pd.to_numeric(df["culture_gap_score"], errors="coerce")
    return df

@st.cache_data
def load_recs() -> pd.DataFrame:
    return pd.read_csv(REC_PATH, encoding="utf-8-sig")

@st.cache_data
def load_geojson() -> dict:
    with open(GEO_PATH, encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def load_centroids() -> dict:
    if CENTROID_PATH.exists():
        with open(CENTROID_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}

# ---------------------------------------------------------------------------
# 색상 팔레트
# ---------------------------------------------------------------------------
RISK_COLOR = {"고위험": "#d62728", "주의": "#ff7f0e", "보통": "#bcbd22", "양호": "#2ca02c"}
TYPE_COLOR = {
    "고령층 교통취약형": "#d62728",
    "시설·행사 부족형": "#ff7f0e",
    "교통 취약형":     "#9467bd",
    "균형 관리형":     "#1f77b4",
}

# ---------------------------------------------------------------------------
# 페이지 설정
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="컬처갭 AI | 문화 사각지대 예측지도",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# 사이드바 필터
# ---------------------------------------------------------------------------
st.sidebar.image("https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f5fa.png", width=60)
st.sidebar.title("컬처갭 AI")
st.sidebar.caption("문화 사각지대 예측지도")

scores = load_scores()
recs   = load_recs()

all_provinces = sorted(scores["province"].dropna().unique())
sel_provinces = st.sidebar.multiselect("시도 선택", all_provinces, default=all_provinces)

all_risks = ["고위험", "주의", "보통", "양호"]
sel_risks = st.sidebar.multiselect("위험 등급", all_risks, default=all_risks)

filtered = scores[
    scores["province"].isin(sel_provinces) &
    scores["risk_level"].isin(sel_risks)
].copy()

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**데이터 출처**\n\n"
    "- 문화체육관광부 문화공공데이터\n"
    "- 행정안전부 인구통계\n"
    "- 지역축제 개최 계획 현황\n"
    "- 문화시설 조회서비스"
)

# ---------------------------------------------------------------------------
# 탭
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["전국 지도", "지역 리포트", "행사 추천", "정책 시뮬레이션"])

# ══════════════════════════════════════════════════════════════════════════════
# 탭 1: 전국 문화 사각지대 지도
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("전국 문화 사각지대 예측지도")
    st.caption(
        "Culture Gap Score = 0.40 × 수요지수 + 0.30 × 공급결핍 + 0.20 × 접근성패널티 + 0.10 × 미스매치패널티 (0~100)"
    )

    # 요약 지표
    col1, col2, col3, col4 = st.columns(4)
    top1 = scores.sort_values("culture_gap_score", ascending=False).iloc[0]
    col1.metric("최고 위험 지역", top1["region_name"], f"{top1['culture_gap_score']}점")
    col2.metric("분석 지역 수", f"{len(scores)}개 시군구")
    col3.metric("평균 결핍지수", f"{scores['culture_gap_score'].mean():.1f}점")
    col4.metric("주의 이상 지역", f"{(scores['risk_level'].isin(['고위험','주의'])).sum()}개")

    st.markdown("---")

    # Folium 지도
    m = folium.Map(location=[36.5, 127.5], zoom_start=7, tiles="CartoDB positron")

    if GEO_PATH.exists():
        geo = load_geojson()
        full_nm_key = scores["province"] + " " + scores["region_name"]
        score_dict = dict(zip(full_nm_key, scores["culture_gap_score"]))
        risk_dict  = dict(zip(full_nm_key, scores["risk_level"]))
        type_dict  = dict(zip(full_nm_key, scores["region_type"]))

        def style_fn(feature):
            name  = feature["properties"].get("full_nm", "")
            score = score_dict.get(name, 0)
            color = (
                "#d62728" if score >= 70
                else "#ff7f0e" if score >= 60
                else "#bcbd22" if score >= 40
                else "#2ca02c"
            )
            return {"fillColor": color, "fillOpacity": 0.65, "color": "#555", "weight": 0.5}

        folium.GeoJson(
            geo,
            style_function=style_fn,
            tooltip=folium.GeoJsonTooltip(
                fields=["full_nm"],
                aliases=["지역"],
                style="font-size:13px;font-family:sans-serif",
            ),
        ).add_to(m)

        # 마커 — 상위 10개 지역
        centroids = load_centroids()
        top10 = scores.sort_values("culture_gap_score", ascending=False).head(10)
        for _, row in top10.iterrows():
            latlon = centroids.get(row["province"] + " " + row["region_name"])
            if latlon:
                lat, lon = latlon
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=8,
                    color="#d62728",
                    fill=True,
                    fill_color="#d62728",
                    fill_opacity=0.9,
                    popup=folium.Popup(
                        f"<b>{row['region_name']}</b><br>"
                        f"결핍지수: {row['culture_gap_score']}점<br>"
                        f"유형: {row['region_type']}",
                        max_width=200,
                    ),
                ).add_to(m)

        # 범례
        legend_html = """
        <div style='position:fixed;bottom:40px;left:40px;z-index:1000;
             background:#ffffffee;padding:12px 16px;border-radius:8px;
             font-size:13px;box-shadow:2px 2px 6px rgba(0,0,0,0.3)'>
        <b>문화결핍지수</b><br>
        <span style='color:#d62728'>●</span> 주의 이상 (60점+)<br>
        <span style='color:#ff7f0e'>●</span> 보통 (40~59점)<br>
        <span style='color:#bcbd22'>●</span> 양호 (40점 미만)<br>
        <span style='color:#d62728'>⬤</span> 상위 10개 지역
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

    st_folium(m, width=None, height=560, returned_objects=[])

    # 상위 지역 표
    st.subheader("문화 사각지대 상위 지역")
    display_cols = ["province", "region_name", "culture_gap_score", "risk_level", "region_type", "main_reasons"]
    col_labels   = {"province": "시도", "region_name": "시군구", "culture_gap_score": "결핍지수",
                    "risk_level": "등급", "region_type": "유형", "main_reasons": "주요 원인"}
    st.dataframe(
        filtered.sort_values("culture_gap_score", ascending=False)
        [display_cols].rename(columns=col_labels),
        width="stretch",
        hide_index=True,
        height=320,
    )

# ══════════════════════════════════════════════════════════════════════════════
# 탭 2: 지역별 결핍 원인 리포트
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("지역별 문화결핍 원인 리포트")

    sorted_regions = (
        filtered.sort_values("culture_gap_score", ascending=False)["region_name"].tolist()
    )
    sel_region = st.selectbox("지역 선택", sorted_regions, key="tab2_region")

    if sel_region:
        row = filtered[filtered["region_name"] == sel_region].iloc[0]

        left_col, right_col = st.columns([1, 1])

        with left_col:
            st.subheader(f"{row['province']} {row['region_name']}")
            risk_color = RISK_COLOR.get(row["risk_level"], "#888")
            st.markdown(
                f"<span style='background:{risk_color};color:white;padding:4px 12px;"
                f"border-radius:12px;font-weight:bold'>{row['risk_level']}</span>"
                f"&nbsp;&nbsp;<b>문화결핍지수: {row['culture_gap_score']}점</b>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**지역 유형**: {row['region_type']}")
            st.markdown(f"**인구**: {int(row['population']):,}명")

            st.markdown("---")
            st.markdown("**점수 구성**")

            components = [
                ("문화수요지수",    float(row["demand_score"]),    "수요가 높을수록 결핍 가능성↑"),
                ("문화공급지수",    float(row["supply_score"]),    "낮을수록 공급 부족"),
                ("접근성 패널티",   float(row["access_penalty"]),  "높을수록 교통·거리 불리"),
                ("미스매치 패널티", float(row["mismatch_penalty"]),"높을수록 프로그램 불일치"),
            ]
            for label, val, desc in components:
                pct = min(int(val), 100)
                st.markdown(f"**{label}** — {val:.1f}점")
                st.progress(pct / 100, text=desc)

            st.markdown("---")
            supply_deficit = 100 - float(row["supply_score"])
            final_est = (
                0.40 * float(row["demand_score"])
                + 0.30 * supply_deficit
                + 0.20 * float(row["access_penalty"])
                + 0.10 * float(row["mismatch_penalty"])
            )
            st.markdown(
                f"**최종 문화결핍지수**: "
                f"0.40 × {row['demand_score']:.1f} + 0.30 × {supply_deficit:.1f} "
                f"+ 0.20 × {row['access_penalty']:.1f} + 0.10 × {row['mismatch_penalty']:.1f} "
                f"= **{final_est:.1f}점**"
            )

        with right_col:
            st.subheader("주요 결핍 원인")
            reasons = str(row["main_reasons"]).split("; ")
            for i, reason in enumerate(reasons, 1):
                if reason.strip():
                    st.info(f"{i}. {reason.strip()}")

            st.subheader("맞춤형 정책 추천")
            policies = str(row["policy_recommendations"]).split("; ")
            for i, pol in enumerate(policies, 1):
                if pol.strip():
                    st.success(f"{i}. {pol.strip()}")

            # 같은 유형 지역 비교
            same_type = scores[scores["region_type"] == row["region_type"]]
            st.markdown("---")
            st.markdown(f"**같은 유형 ({row['region_type']}) 지역 평균 비교**")
            compare_data = pd.DataFrame({
                "항목": ["수요", "공급", "접근성", "미스매치", "결핍지수"],
                "이 지역": [
                    row["demand_score"], row["supply_score"],
                    row["access_penalty"], row["mismatch_penalty"], row["culture_gap_score"],
                ],
                "유형 평균": [
                    same_type["demand_score"].mean(),
                    same_type["supply_score"].mean(),
                    same_type["access_penalty"].mean(),
                    same_type["mismatch_penalty"].mean(),
                    same_type["culture_gap_score"].mean(),
                ],
            })
            st.dataframe(
                compare_data.set_index("항목").round(1),
                width="stretch",
            )

# ══════════════════════════════════════════════════════════════════════════════
# 탭 3: 맞춤형 문화행사 추천 카드
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("맞춤형 문화행사 추천")
    st.caption("결핍 유형별 프로필에 맞춰 실제 진행 중인 문화행사를 추천합니다.")

    rec_regions = recs["region_name"].unique().tolist()
    sel_rec_region = st.selectbox("지역 선택", sorted(rec_regions), key="tab3_region")

    if sel_rec_region:
        region_row = scores[scores["region_name"] == sel_rec_region]
        if not region_row.empty:
            rr = region_row.iloc[0]
            st.markdown(
                f"**{rr['province']} {sel_rec_region}** | "
                f"유형: `{rr['region_type']}` | "
                f"결핍지수: **{rr['culture_gap_score']}점** ({rr['risk_level']})"
            )

        region_recs = recs[recs["region_name"] == sel_rec_region].sort_values("rank")
        st.markdown(f"총 **{len(region_recs)}개** 행사 추천")

        for _, ev in region_recs.iterrows():
            with st.expander(
                f"**#{int(ev['rank'])} {ev['event_name']}**  "
                f"[{ev['tag_genre']}] [{ev['tag_price']}]",
                expanded=(ev["rank"] <= 3),
            ):
                cols = st.columns([2, 1])
                with cols[0]:
                    st.markdown(f"**장소**: {ev.get('place','N/A')}")
                    if pd.notna(ev.get("start_date")) and str(ev.get("start_date","")) not in ("", "nan"):
                        st.markdown(f"**기간**: {ev['start_date']} ~ {ev.get('end_date','')}")
                    st.markdown(f"**세부 장르**: {ev.get('detail_genre','')}")
                    if pd.notna(ev.get("distance_km")) and str(ev.get("distance_km","")) not in ("", "nan"):
                        st.markdown(f"**거리**: {ev['distance_km']}")
                with cols[1]:
                    price_color = "#d62728" if ev["tag_price"] == "유료" else "#2ca02c"
                    st.markdown(
                        f"<span style='background:{price_color};color:white;padding:3px 10px;"
                        f"border-radius:10px'>{ev['tag_price']}</span>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"대상: `{ev.get('tag_target','')}`")
                    st.markdown(f"시간대: `{ev.get('tag_time','')}`")
                    url = ev.get("event_url", "")
                    if url and str(url) not in ("", "nan"):
                        st.link_button("문화포털 보기", url)

# ══════════════════════════════════════════════════════════════════════════════
# 탭 4: 정책 시뮬레이션
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("정책 시뮬레이션")
    st.caption("문화공급 개입 시 결핍지수가 얼마나 개선되는지 예측합니다.")

    sim_regions = scores.sort_values("culture_gap_score", ascending=False)["region_name"].tolist()
    sel_sim = st.selectbox("시뮬레이션 지역 선택", sim_regions, key="tab4_region")

    if sel_sim:
        sim_row = scores[scores["region_name"] == sel_sim].iloc[0]

        st.subheader(f"{sim_row['province']} {sel_sim}")
        st.markdown(
            f"현재 문화결핍지수: **{sim_row['culture_gap_score']}점** "
            f"({sim_row['risk_level']}, {sim_row['region_type']})"
        )
        st.markdown("---")

        st.subheader("개입 조건 설정")
        c1, c2, c3 = st.columns(3)

        with c1:
            extra_events = st.slider(
                "월 행사 추가 수",
                min_value=0, max_value=50, value=10, step=5,
                help="공연·전시·체험 행사를 월 몇 개 추가할지 선택"
            )
        with c2:
            free_boost = st.slider(
                "무료 행사 비율 추가 (%p)",
                min_value=0, max_value=30, value=10, step=5,
                help="현재 무료 프로그램 비율에서 몇 %p 올릴지 선택"
            )
        with c3:
            transport_boost = st.slider(
                "교통 접근성 개선 점수",
                min_value=0, max_value=20, value=5, step=1,
                help="셔틀버스, 찾아가는 서비스 등으로 줄일 수 있는 접근성 패널티"
            )

        # 개선 계산
        supply_gain  = extra_events * 0.4 + free_boost * 0.3   # 공급지수 상승분
        new_supply   = min(float(sim_row["supply_score"]) + supply_gain, 100)
        new_access   = max(float(sim_row["access_penalty"]) - transport_boost, 0)
        new_mismatch = max(float(sim_row["mismatch_penalty"]) - (free_boost * 0.2), 0)

        new_gap = (
            0.40 * float(sim_row["demand_score"])
            + 0.30 * (100 - new_supply)
            + 0.20 * new_access
            + 0.10 * new_mismatch
        )
        improvement = float(sim_row["culture_gap_score"]) - new_gap

        def _risk_level(score: float) -> str:
            if score >= 80:   return "고위험"
            elif score >= 60: return "주의"
            elif score >= 40: return "보통"
            else:             return "양호"

        new_risk = _risk_level(new_gap)
        old_risk = sim_row["risk_level"]

        st.markdown("---")
        st.subheader("개선 예측 결과")

        m1, m2, m3 = st.columns(3)
        m1.metric("현재 결핍지수", f"{sim_row['culture_gap_score']}점", help="개입 전")
        m2.metric("예상 결핍지수", f"{new_gap:.1f}점", f"-{improvement:.1f}점 개선")
        m3.metric("등급 변화", new_risk, f"{old_risk} → {new_risk}" if new_risk != old_risk else "유지")

        st.markdown(f"""
**개선 계산 근거:**
- 월 행사 +{extra_events}개 → 공급지수 +{supply_gain:.1f}점 → 공급결핍 -{supply_gain:.1f}점
- 무료 비율 +{free_boost}%p → 미스매치 -{free_boost * 0.2:.1f}점
- 교통 개선 → 접근성 패널티 -{transport_boost}점

새 결핍지수 = 0.40 × {sim_row['demand_score']:.1f} + 0.30 × {100-new_supply:.1f} + 0.20 × {new_access:.1f} + 0.10 × {new_mismatch:.1f} = **{new_gap:.1f}점**
        """)

        if improvement > 5:
            st.success(f"이 조합으로 문화결핍지수를 **{improvement:.1f}점** 낮출 수 있습니다!")
        elif improvement > 0:
            st.info(f"소폭 개선 효과 (+{improvement:.1f}점). 더 강한 개입이 필요합니다.")
        else:
            st.warning("수요가 높아 공급 확충만으로는 한계가 있습니다. 교통 접근성 개선을 우선 검토하세요.")

        # 비교 차트
        st.markdown("---")
        st.subheader("개입 전·후 점수 비교")
        chart_df = pd.DataFrame({
            "항목": ["수요지수", "공급지수", "접근성패널티", "미스매치패널티", "결핍지수"],
            "개입 전": [
                sim_row["demand_score"], sim_row["supply_score"],
                sim_row["access_penalty"], sim_row["mismatch_penalty"],
                sim_row["culture_gap_score"],
            ],
            "개입 후": [
                sim_row["demand_score"], new_supply,
                new_access, new_mismatch, new_gap,
            ],
        }).set_index("항목")
        st.bar_chart(chart_df)
