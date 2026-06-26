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
BASE          = Path(__file__).parent.parent
SCORE_PATH    = BASE / "data/processed/culture_gap_scores.csv"
REC_PATH      = BASE / "data/processed/event_recommendations.csv"
GEO_PATH      = BASE / "data/raw/sigungu_boundary_full.geojson"
CENTROID_PATH = BASE / "data/processed/region_centroids.json"

# ---------------------------------------------------------------------------
# 페이지 설정 (가장 먼저)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="컬처갭 AI | 문화 사각지대 예측지도",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# 전역 CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
.banner {
    background: linear-gradient(135deg, #1a1f2e 0%, #0e1422 100%);
    border-left: 4px solid #4c8bf5;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 16px;
    color: #e0e6f0;
}
.banner h2 { margin: 0 0 6px 0; font-size: 1.15rem; color: #7ab3f5; }
.banner p  { margin: 0; font-size: 0.85rem; color: #a0b0c8; line-height: 1.5; }

.region-card {
    background: linear-gradient(135deg, #1a2744 0%, #111827 100%);
    border: 1px solid #2d3f5c;
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 16px;
}
.region-card .region-name { font-size: 1.4rem; font-weight: 700; color: #e8f0ff; margin: 0; }
.region-card .region-sub  { font-size: 0.9rem; color: #7a9cc8; margin-top: 6px; }

.badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 12px;
    font-size: 0.82rem;
    font-weight: 700;
    margin-right: 8px;
}
.badge-danger  { background: #7f1d1d; color: #fca5a5; border: 1px solid #991b1b; }
.badge-warn    { background: #78350f; color: #fcd34d; border: 1px solid #92400e; }
.badge-ok      { background: #064e3b; color: #6ee7b7; border: 1px solid #065f46; }
.badge-normal  { background: #1e3a5f; color: #93c5fd; border: 1px solid #1e40af; }
.badge-price-free    { background: #064e3b; color: #6ee7b7; border: 1px solid #065f46; }
.badge-price-pay     { background: #7f1d1d; color: #fca5a5; border: 1px solid #991b1b; }
.badge-price-unknown { background: #374151; color: #9ca3af; border: 1px solid #4b5563; }

.formula-box {
    background: #111827;
    border: 1px solid #2d3f5c;
    border-radius: 8px;
    padding: 12px 16px;
    font-family: monospace;
    font-size: 0.88rem;
    color: #93c5fd;
    margin-top: 8px;
    line-height: 1.8;
}

.coef-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.coef-table th { background: #1e3a5f; color: #93c5fd; padding: 6px 10px; text-align: left; }
.coef-table td { padding: 5px 10px; border-bottom: 1px solid #1f2d3d; color: #c8d6e8; }
</style>
""", unsafe_allow_html=True)

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
# 헬퍼
# ---------------------------------------------------------------------------
RISK_CSS = {
    "고위험": "badge-danger",
    "주의":   "badge-warn",
    "보통":   "badge-normal",
    "양호":   "badge-ok",
}

def risk_badge(level: str) -> str:
    css = RISK_CSS.get(level, "badge-normal")
    return f"<span class='badge {css}'>{level}</span>"

def price_badge(tag: str) -> str:
    if tag == "유료":
        return "<span class='badge badge-price-pay'>유료</span>"
    if tag in ("무료·저비용", "무료", "저비용"):
        return f"<span class='badge badge-price-free'>{tag}</span>"
    return "<span class='badge badge-price-unknown'>미확인</span>"

def _is_valid(val) -> bool:
    return bool(val and str(val).strip() not in ("", "nan", "NaT", "None", "none"))

# ---------------------------------------------------------------------------
# 사이드바
# ---------------------------------------------------------------------------
st.sidebar.markdown("## 🗺️ 컬처갭 AI")
st.sidebar.caption("문화 사각지대 예측지도")

scores = load_scores()
recs   = load_recs()

all_provinces = sorted(scores["province"].dropna().unique())
sel_provinces = st.sidebar.multiselect("📍 시도 선택", all_provinces, default=all_provinces)

all_risks = ["고위험", "주의", "보통", "양호"]
sel_risks = st.sidebar.multiselect("⚠️ 위험 등급", all_risks, default=all_risks)

filtered = scores[
    scores["province"].isin(sel_provinces) &
    scores["risk_level"].isin(sel_risks)
].copy()

st.sidebar.markdown("---")
st.sidebar.markdown("""**데이터 출처**
- 문화체육관광부 한눈에보는문화정보
- 문화시설·박물관·미술관 OpenAPI
- 전국 지역축제 개최 계획 현황
- 행정안전부 연령별 인구통계
- 국토교통부 전국 버스정류장""")

# ---------------------------------------------------------------------------
# 탭
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["🗺 전국 지도", "📊 지역 리포트", "🎭 행사 추천", "🧪 정책 시뮬레이션"])

# ══════════════════════════════════════════════════════════════════════════════
# 탭 1: 전국 지도
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("""<div class='banner'>
<h2>🗺 전국 문화 사각지대 예측지도</h2>
<p>전국 247개 시군구의 문화결핍지수를 AI로 분석합니다.
수요(고령·청소년 인구)와 공급(행사·시설·축제)의 괴리를 시각화하여
정책 개입이 가장 시급한 지역을 식별합니다.</p>
</div>""", unsafe_allow_html=True)

    with st.expander("ℹ️ 문화결핍지수 계산 공식", expanded=False):
        st.markdown("""
<div class='formula-box'>
문화결핍지수 = 0.40 × 수요지수 + 0.30 × (100 - 공급지수) + 0.20 × 접근성패널티 + 0.10 × 미스매치패널티
</div>

| 구성 요소 | 가중치 | 설명 |
|---|---|---|
| 수요지수 | 40% | 고령층·청소년 비율, 문화소외 취약계층 규모 |
| 공급결핍 | 30% | 행사·시설·축제 수 대비 인구 공급 부족분 |
| 접근성패널티 | 20% | 버스 정류장 밀도, 대중교통 접근 불리 |
| 미스매치패널티 | 10% | 대상 불일치, 유료 프로그램 비중 과다 |
        """, unsafe_allow_html=True)

    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    top1 = scores.sort_values("culture_gap_score", ascending=False).iloc[0]
    col1.metric("🚨 최고 위험 지역", top1["region_name"].split()[-1], f"{top1['culture_gap_score']}점")
    col2.metric("📍 분석 시군구", f"{len(scores)}개")
    col3.metric("📈 평균 결핍지수", f"{scores['culture_gap_score'].mean():.1f}점")
    col4.metric("⚠️ 주의 이상 지역", f"{(scores['risk_level'].isin(['고위험','주의'])).sum()}개")

    st.markdown("---")

    m = folium.Map(location=[36.5, 127.5], zoom_start=7, tiles="CartoDB dark_matter")

    if GEO_PATH.exists():
        geo = load_geojson()
        # scores["region_name"]은 province를 이미 포함 — GeoJSON full_nm과 직접 매칭
        score_dict = dict(zip(scores["region_name"], scores["culture_gap_score"]))
        risk_dict  = dict(zip(scores["region_name"], scores["risk_level"]))
        type_dict  = dict(zip(scores["region_name"], scores["region_type"]))

        def style_fn(feature):
            name  = feature["properties"].get("full_nm", "")
            score = score_dict.get(name, -1)
            if score < 0:
                return {"fillColor": "#2d3748", "fillOpacity": 0.25, "color": "#4a5568", "weight": 0.3}
            color = (
                "#ef4444" if score >= 70
                else "#f97316" if score >= 60
                else "#eab308" if score >= 50
                else "#22c55e" if score >= 40
                else "#3b82f6"
            )
            return {"fillColor": color, "fillOpacity": 0.70, "color": "#1a1a2e", "weight": 0.5}

        folium.GeoJson(
            geo,
            style_function=style_fn,
            tooltip=folium.GeoJsonTooltip(
                fields=["full_nm"],
                aliases=["지역"],
                style=(
                    "background:#1a1f2e;color:#e0e6f0;font-size:13px;"
                    "font-family:sans-serif;border:1px solid #4c8bf5;"
                ),
            ),
        ).add_to(m)

        centroids = load_centroids()
        top10 = scores.sort_values("culture_gap_score", ascending=False).head(10)
        for _, row in top10.iterrows():
            # centroids 키도 region_name과 동일 형식
            latlon = centroids.get(row["region_name"])
            if latlon:
                lat, lon = latlon
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=9,
                    color="#ef4444",
                    fill=True,
                    fill_color="#ef4444",
                    fill_opacity=0.9,
                    popup=folium.Popup(
                        f"<b style='color:#1a1f2e'>{row['region_name']}</b><br>"
                        f"결핍지수: <b>{row['culture_gap_score']}점</b><br>"
                        f"등급: {row['risk_level']}<br>유형: {row['region_type']}",
                        max_width=220,
                    ),
                ).add_to(m)

        legend_html = """
        <div style='position:fixed;bottom:40px;left:40px;z-index:1000;
             background:#1a1f2eee;color:#e0e6f0;padding:14px 18px;
             border-radius:10px;font-size:12px;border:1px solid #4c8bf5;
             box-shadow:0 4px 12px rgba(0,0,0,0.5)'>
        <b style='font-size:13px'>📊 문화결핍지수</b><br><br>
        <span style='color:#ef4444'>●</span> 고위험 (70점+)<br>
        <span style='color:#f97316'>●</span> 주의 (60~69점)<br>
        <span style='color:#eab308'>●</span> 보통 (50~59점)<br>
        <span style='color:#22c55e'>●</span> 양호 (40~49점)<br>
        <span style='color:#3b82f6'>●</span> 우수 (40점 미만)<br>
        <hr style='border-color:#2d3748;margin:8px 0'>
        <span style='color:#ef4444'>⬤</span> 상위 10개 위험 지역
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

    st_folium(m, width=None, height=560, returned_objects=[])

    st.subheader("📋 문화 사각지대 상위 지역")
    display_cols = ["region_name", "culture_gap_score", "risk_level", "region_type", "main_reasons"]
    col_labels   = {
        "region_name": "지역", "culture_gap_score": "결핍지수",
        "risk_level": "등급", "region_type": "유형", "main_reasons": "주요 원인",
    }
    st.dataframe(
        filtered.sort_values("culture_gap_score", ascending=False)
        [display_cols].rename(columns=col_labels),
        use_container_width=True,
        hide_index=True,
        height=340,
    )

# ══════════════════════════════════════════════════════════════════════════════
# 탭 2: 지역별 결핍 원인 리포트
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("""<div class='banner'>
<h2>📊 지역별 문화결핍 원인 리포트</h2>
<p>선택한 시군구의 결핍지수 구성 요소를 분해하고, 같은 유형 지역과 비교합니다.
주요 원인과 맞춤형 정책 제언을 확인하세요.</p>
</div>""", unsafe_allow_html=True)

    sorted_regions = (
        filtered.sort_values("culture_gap_score", ascending=False)["region_name"].tolist()
    )
    sel_region = st.selectbox("지역 선택 (결핍지수 높은 순)", sorted_regions, key="tab2_region")

    if sel_region:
        row = filtered[filtered["region_name"] == sel_region].iloc[0]
        risk_css = RISK_CSS.get(row["risk_level"], "badge-normal")

        st.markdown(
            f"<div class='region-card'>"
            f"<p class='region-name'>{row['region_name']}</p>"
            f"<p class='region-sub'>"
            f"<span class='badge {risk_css}'>{row['risk_level']}</span>"
            f"문화결핍지수 <b style='color:#7ab3f5;font-size:1.1rem'>{row['culture_gap_score']}점</b>"
            f"&nbsp;|&nbsp;{row['region_type']}"
            f"&nbsp;|&nbsp;인구 {int(row['population']):,}명"
            f"</p></div>",
            unsafe_allow_html=True,
        )

        left_col, right_col = st.columns([1, 1])

        with left_col:
            st.markdown("#### 📐 점수 구성")

            supply_deficit = 100 - float(row["supply_score"])
            final_est = (
                0.40 * float(row["demand_score"])
                + 0.30 * supply_deficit
                + 0.20 * float(row["access_penalty"])
                + 0.10 * float(row["mismatch_penalty"])
            )
            with st.expander("ℹ️ 이 지역 결핍지수 계산 과정", expanded=False):
                st.markdown(
                    f"<div class='formula-box'>"
                    f"= 0.40 × {row['demand_score']:.1f} &nbsp;(수요지수)<br>"
                    f"+ 0.30 × {supply_deficit:.1f} &nbsp;(공급결핍 = 100 - {row['supply_score']:.1f})<br>"
                    f"+ 0.20 × {row['access_penalty']:.1f} &nbsp;(접근성패널티)<br>"
                    f"+ 0.10 × {row['mismatch_penalty']:.1f} &nbsp;(미스매치패널티)<br>"
                    f"= <b style='color:#fff'>{final_est:.1f}점</b></div>",
                    unsafe_allow_html=True,
                )

            components = [
                ("📈 문화수요지수",    float(row["demand_score"]),    50,  "높을수록 취약계층 수요↑"),
                ("📉 문화공급지수",    float(row["supply_score"]),    100, "낮을수록 공급 부족"),
                ("🚌 접근성 패널티",   float(row["access_penalty"]),  100, "높을수록 교통·거리 불리"),
                ("🎯 미스매치 패널티", float(row["mismatch_penalty"]),100, "높을수록 프로그램 불일치"),
            ]
            for label, val, denom, desc in components:
                pct = min(int(val / denom * 100), 100)
                st.markdown(f"**{label}** &nbsp; `{val:.1f}점`")
                st.progress(pct / 100, text=desc)

        with right_col:
            st.markdown("#### 🔍 주요 결핍 원인")
            reasons = [r.strip() for r in str(row["main_reasons"]).split(";") if r.strip()]
            for i, reason in enumerate(reasons, 1):
                st.info(f"**{i}.** {reason}")

            st.markdown("#### 💡 맞춤형 정책 추천")
            policies = [p.strip() for p in str(row["policy_recommendations"]).split(";") if p.strip()]
            for i, pol in enumerate(policies, 1):
                st.success(f"**{i}.** {pol}")

        st.markdown("---")
        st.markdown(f"#### 📊 같은 유형({row['region_type']}) 평균 비교")
        same_type = scores[scores["region_type"] == row["region_type"]]
        short_name = row["region_name"].split()[-1]
        compare_data = pd.DataFrame({
            "항목": ["수요지수", "공급지수", "접근성패널티", "미스매치패널티", "결핍지수"],
            f"이 지역 ({short_name})": [
                row["demand_score"], row["supply_score"],
                row["access_penalty"], row["mismatch_penalty"], row["culture_gap_score"],
            ],
            "유형 평균": [
                same_type["demand_score"].mean(), same_type["supply_score"].mean(),
                same_type["access_penalty"].mean(), same_type["mismatch_penalty"].mean(),
                same_type["culture_gap_score"].mean(),
            ],
        }).set_index("항목").round(1)
        st.dataframe(compare_data, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# 탭 3: 맞춤형 문화행사 추천
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("""<div class='banner'>
<h2>🎭 맞춤형 문화행사 추천</h2>
<p>지역의 결핍 유형(고령층 교통취약·시설부족·교통취약·균형관리)에 맞춰
실제 진행 예정인 문화행사를 AI가 자동 선별합니다.
같은 시도 내 이벤트 중 매칭 점수 상위 행사를 제안합니다.</p>
</div>""", unsafe_allow_html=True)

    rec_regions = sorted(recs["region_name"].unique().tolist())

    c_filter1, c_filter2 = st.columns([2, 1])
    with c_filter1:
        sel_rec_region = st.selectbox("지역 선택", rec_regions, key="tab3_region")
    with c_filter2:
        dist_filter = st.number_input(
            "최대 거리 (km, 0=전체)", min_value=0, max_value=500, value=100, step=10,
            help="거리 정보가 있는 행사만 필터. 0이면 거리 무관 전체 표시.",
        )

    if sel_rec_region:
        region_row = scores[scores["region_name"] == sel_rec_region]
        if not region_row.empty:
            rr = region_row.iloc[0]
            risk_css = RISK_CSS.get(rr["risk_level"], "badge-normal")
            st.markdown(
                f"<div class='region-card'>"
                f"<p class='region-name'>{rr['region_name']}</p>"
                f"<p class='region-sub'>"
                f"<span class='badge {risk_css}'>{rr['risk_level']}</span>"
                f"결핍지수 <b style='color:#7ab3f5'>{rr['culture_gap_score']}점</b>"
                f"&nbsp;|&nbsp;{rr['region_type']}"
                f"</p></div>",
                unsafe_allow_html=True,
            )

        region_recs = recs[recs["region_name"] == sel_rec_region].sort_values("rank").copy()

        if dist_filter > 0:
            def _extract_km(val) -> float | None:
                if not _is_valid(val):
                    return None
                try:
                    return float(str(val).replace("km", "").strip())
                except ValueError:
                    return None
            region_recs["_dist_num"] = region_recs["distance_km"].apply(_extract_km)
            region_recs = region_recs[
                region_recs["_dist_num"].isna() | (region_recs["_dist_num"] <= dist_filter)
            ]

        st.markdown(f"총 **{len(region_recs)}개** 행사 추천")

        for _, ev in region_recs.iterrows():
            tag_price = str(ev.get("tag_price", "")).strip()
            with st.expander(f"**#{int(ev['rank'])}** {ev['event_name']}", expanded=(ev["rank"] <= 3)):
                cols = st.columns([3, 1])
                with cols[0]:
                    st.markdown(f"**장소** : {ev.get('place', 'N/A')}")
                    sd = str(ev.get("start_date", ""))
                    ed = str(ev.get("end_date", ""))
                    if _is_valid(sd):
                        end_str = f" ~ {ed}" if _is_valid(ed) else ""
                        st.markdown(f"**기간** : {sd}{end_str}")
                    if _is_valid(ev.get("detail_genre")):
                        st.markdown(f"**장르** : {ev['detail_genre']}")
                    dist_val = ev.get("distance_km", "")
                    if _is_valid(dist_val):
                        st.markdown(f"**거리** : {dist_val}")
                    if _is_valid(ev.get("match_reason")):
                        st.caption(f"추천 이유: {ev['match_reason']}")

                with cols[1]:
                    st.markdown(price_badge(tag_price), unsafe_allow_html=True)
                    if _is_valid(ev.get("tag_genre")):
                        st.markdown(f"**장르** `{ev['tag_genre']}`")
                    if _is_valid(ev.get("tag_target")):
                        st.markdown(f"**대상** `{ev['tag_target']}`")
                    if _is_valid(ev.get("tag_time")):
                        st.markdown(f"**시간** `{ev['tag_time']}`")
                    url = ev.get("event_url", "")
                    if _is_valid(url):
                        st.link_button("🔗 문화포털", str(url))

# ══════════════════════════════════════════════════════════════════════════════
# 탭 4: 정책 시뮬레이션
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("""<div class='banner'>
<h2>🧪 정책 시뮬레이션</h2>
<p>행사 확충, 무료 프로그램 비율 제고, 교통 접근성 개선 시
문화결핍지수가 얼마나 개선되는지 예측합니다.
각 개입 조건의 가중치는 아래 계수 테이블을 참고하세요.</p>
</div>""", unsafe_allow_html=True)

    sim_regions = scores.sort_values("culture_gap_score", ascending=False)["region_name"].tolist()
    sel_sim = st.selectbox("시뮬레이션 지역 선택", sim_regions, key="tab4_region")

    if sel_sim:
        sim_row = scores[scores["region_name"] == sel_sim].iloc[0]
        risk_css = RISK_CSS.get(sim_row["risk_level"], "badge-normal")

        st.markdown(
            f"<div class='region-card'>"
            f"<p class='region-name'>{sim_row['region_name']}</p>"
            f"<p class='region-sub'>"
            f"<span class='badge {risk_css}'>{sim_row['risk_level']}</span>"
            f"현재 결핍지수 <b style='color:#7ab3f5;font-size:1.1rem'>{sim_row['culture_gap_score']}점</b>"
            f"&nbsp;|&nbsp;{sim_row['region_type']}"
            f"</p></div>",
            unsafe_allow_html=True,
        )

        with st.expander("📋 시뮬레이션 계수 테이블", expanded=False):
            st.markdown("""
<table class='coef-table'>
<tr><th>개입 조건</th><th>계수</th><th>효과</th></tr>
<tr><td>월 행사 +1개</td><td>× 0.40</td><td>공급지수 +0.4점</td></tr>
<tr><td>무료 비율 +1%p</td><td>× 0.30</td><td>공급지수 +0.3점</td></tr>
<tr><td>무료 비율 +1%p</td><td>× 0.20</td><td>미스매치 패널티 -0.2점</td></tr>
<tr><td>교통 개선 점수 +1</td><td>× 1.00</td><td>접근성 패널티 -1점</td></tr>
</table>
            """, unsafe_allow_html=True)

        st.markdown("#### ⚙️ 개입 조건 설정")
        c1, c2, c3 = st.columns(3)
        with c1:
            extra_events = st.slider("월 행사 추가 수", 0, 50, 10, 5,
                                     help="공연·전시·체험 행사를 월 몇 개 추가할지")
        with c2:
            free_boost = st.slider("무료 행사 비율 추가 (%p)", 0, 30, 10, 5,
                                   help="현재 무료 프로그램 비율에서 몇 %p 올릴지")
        with c3:
            transport_boost = st.slider("교통 접근성 개선 점수", 0, 20, 5, 1,
                                        help="셔틀버스·찾아가는 서비스로 줄이는 접근성 패널티")

        supply_gain  = extra_events * 0.4 + free_boost * 0.3
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
            if score >= 70:   return "고위험"
            elif score >= 60: return "주의"
            elif score >= 40: return "보통"
            else:             return "양호"

        new_risk = _risk_level(new_gap)
        old_risk  = sim_row["risk_level"]

        st.markdown("---")
        st.markdown("#### 📈 개선 예측 결과")
        m1, m2, m3 = st.columns(3)
        m1.metric("현재 결핍지수", f"{sim_row['culture_gap_score']}점")
        m2.metric("예상 결핍지수", f"{new_gap:.1f}점", f"-{improvement:.1f}점")
        m3.metric("등급 변화", new_risk,
                  f"{old_risk} → {new_risk}" if new_risk != old_risk else "유지")

        st.markdown(
            f"<div class='formula-box'>"
            f"개선 후 = 0.40 × {sim_row['demand_score']:.1f} "
            f"+ 0.30 × {100 - new_supply:.1f} "
            f"+ 0.20 × {new_access:.1f} "
            f"+ 0.10 × {new_mismatch:.1f} = <b style='color:#fff'>{new_gap:.1f}점</b>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if improvement >= 10:
            st.success(f"🎉 이 조합으로 결핍지수를 **{improvement:.1f}점** 낮출 수 있습니다!")
        elif improvement > 3:
            st.info(f"✅ **{improvement:.1f}점** 개선 효과. 더 강한 개입을 병행하면 효과가 커집니다.")
        elif improvement > 0:
            st.warning(f"⚠️ 소폭 개선 (+{improvement:.1f}점). 세 조건을 모두 늘려보세요.")
        else:
            st.error("수요 자체가 높아 공급 확충만으로는 한계가 있습니다. 교통 접근성 개선을 우선 검토하세요.")

        st.markdown("---")
        st.markdown("#### 📊 개입 전·후 비교")
        chart_df = pd.DataFrame({
            "항목": ["수요지수", "공급지수", "접근성패널티", "미스매치패널티", "결핍지수"],
            "개입 전": [
                float(sim_row["demand_score"]), float(sim_row["supply_score"]),
                float(sim_row["access_penalty"]), float(sim_row["mismatch_penalty"]),
                float(sim_row["culture_gap_score"]),
            ],
            "개입 후": [
                float(sim_row["demand_score"]), new_supply,
                new_access, new_mismatch, new_gap,
            ],
        }).set_index("항목")
        st.bar_chart(chart_df)
