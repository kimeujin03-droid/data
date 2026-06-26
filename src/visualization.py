from __future__ import annotations

import json
from pathlib import Path

import folium
import matplotlib.pyplot as plt
import pandas as pd
from branca.colormap import LinearColormap


def save_top_regions_chart(scored: pd.DataFrame, output_path: Path) -> None:
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    top = scored.sort_values("culture_gap_score", ascending=False).head(15)
    colors = ["#c84c3a" if r == "주의" else "#e8956b" if r == "보통" else "#4caf7d" for r in top["risk_level"]]
    plt.figure(figsize=(10, 6))
    bars = plt.barh(top["region_name"], top["culture_gap_score"], color=colors)
    plt.gca().invert_yaxis()
    plt.axvline(x=60, color="#c84c3a", linestyle="--", linewidth=0.8, label="주의 기준(60점)")
    plt.axvline(x=40, color="#4caf7d", linestyle="--", linewidth=0.8, label="양호 기준(40점)")
    plt.xlabel("문화결핍지수 (Culture Gap Score)")
    plt.title("문화 사각지대 고위험 시군구 Top 15", fontsize=13, fontweight="bold")
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def save_province_summary_chart(scored: pd.DataFrame, output_path: Path) -> None:
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    prov_avg = (
        scored.groupby("province")["culture_gap_score"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "avg_score", "count": "sigungu_count"})
        .sort_values("avg_score", ascending=False)
    )
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    colors = ["#c84c3a" if s >= 60 else "#e8956b" if s >= 40 else "#4caf7d" for s in prov_avg["avg_score"]]
    ax1.barh(prov_avg.index, prov_avg["avg_score"], color=colors)
    ax1.axvline(x=60, color="#c84c3a", linestyle="--", linewidth=0.8)
    ax1.set_xlabel("평균 문화결핍지수")
    ax1.set_title("시도별 평균 문화결핍지수", fontweight="bold")
    ax1.invert_yaxis()

    risk_dist = scored.groupby(["province", "risk_level"]).size().unstack(fill_value=0)
    risk_cols = [c for c in ["고위험", "주의", "보통", "양호"] if c in risk_dist.columns]
    risk_colors = {"고위험": "#c84c3a", "주의": "#e8956b", "보통": "#f5c842", "양호": "#4caf7d"}
    bottom = pd.Series(0, index=risk_dist.index)
    for col in risk_cols:
        ax2.barh(risk_dist.index, risk_dist[col], left=bottom, label=col, color=risk_colors.get(col, "gray"))
        bottom = bottom + risk_dist[col]
    ax2.set_xlabel("시군구 수")
    ax2.set_title("시도별 위험 등급 분포", fontweight="bold")
    ax2.legend(loc="lower right")
    ax2.invert_yaxis()

    plt.tight_layout()
    plt.savefig(output_path, dpi=160)
    plt.close()


def save_score_distribution_chart(scored: pd.DataFrame, output_path: Path) -> None:
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    axes[0].hist(scored["culture_gap_score"], bins=20, color="#e8956b", edgecolor="white")
    axes[0].axvline(x=60, color="#c84c3a", linestyle="--", label="주의(60)")
    axes[0].axvline(x=40, color="#4caf7d", linestyle="--", label="양호(40)")
    axes[0].set_title("문화결핍지수 분포")
    axes[0].set_xlabel("점수")
    axes[0].legend()

    risk_counts = scored["risk_level"].value_counts()
    colors_pie = [{"고위험": "#c84c3a", "주의": "#e8956b", "보통": "#f5c842", "양호": "#4caf7d"}.get(r, "gray") for r in risk_counts.index]
    axes[1].pie(risk_counts.values, labels=risk_counts.index, colors=colors_pie, autopct="%1.1f%%", startangle=90)
    axes[1].set_title("위험 등급 비율")

    type_counts = scored["region_type"].value_counts().head(6)
    axes[2].barh(type_counts.index, type_counts.values, color="#5b8fde")
    axes[2].invert_yaxis()
    axes[2].set_title("지역 유형 분포")
    axes[2].set_xlabel("시군구 수")

    plt.suptitle("컬처갭 AI — 전국 문화결핍 분석 요약", fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close()


def save_choropleth_map(
    scored: pd.DataFrame,
    geojson_path: Path,
    output_path: Path,
) -> None:
    """전국 시군구 문화결핍지수 Choropleth 지도 (HTML) 생성."""
    if not geojson_path.exists():
        return

    with open(geojson_path, encoding="utf-8") as f:
        gj = json.load(f)

    score_map = scored.set_index("region_name")["culture_gap_score"].to_dict()
    risk_map = scored.set_index("region_name")["risk_level"].to_dict()
    type_map = scored.set_index("region_name")["region_type"].to_dict()
    pop_map = scored.set_index("region_name")["population"].to_dict()
    reason_map = scored.set_index("region_name")["main_reasons"].to_dict()
    rec_map = scored.set_index("region_name")["policy_recommendations"].to_dict()

    m = folium.Map(location=[36.5, 127.8], zoom_start=7, tiles="CartoDB positron")

    colormap = LinearColormap(
        colors=["#4caf7d", "#f5c842", "#e8956b", "#c84c3a"],
        vmin=scored["culture_gap_score"].min(),
        vmax=scored["culture_gap_score"].max(),
        caption="문화결핍지수 (Culture Gap Score)",
    )
    colormap.add_to(m)

    def style_fn(feature):
        full_nm = feature["properties"].get("full_nm", "")
        score = score_map.get(full_nm)
        if score is None:
            return {"fillColor": "#cccccc", "color": "#888", "weight": 0.5, "fillOpacity": 0.3}
        return {
            "fillColor": colormap(score),
            "color": "#555",
            "weight": 0.8,
            "fillOpacity": 0.75,
        }

    def highlight_fn(feature):
        return {"weight": 2.5, "color": "#333", "fillOpacity": 0.9}

    def make_tooltip(feature):
        nm = feature["properties"].get("full_nm", "")
        score = score_map.get(nm)
        if score is None:
            return f"<b>{nm}</b><br>데이터 없음"
        return (
            f"<b>{nm}</b><br>"
            f"점수: {score:.1f} | 등급: {risk_map.get(nm,'')}<br>"
            f"유형: {type_map.get(nm,'')}<br>"
            f"인구: {int(pop_map.get(nm,0)):,}명"
        )

    def make_popup(feature):
        nm = feature["properties"].get("full_nm", "")
        score = score_map.get(nm)
        if score is None:
            return folium.Popup(f"<b>{nm}</b><br>데이터 없음", max_width=280)
        reasons = reason_map.get(nm, "")
        recs = rec_map.get(nm, "")
        html = (
            f"<div style='font-family:sans-serif;font-size:12px;max-width:280px'>"
            f"<b style='font-size:14px'>{nm}</b><br>"
            f"<span style='color:#c84c3a;font-weight:bold'>결핍지수 {score:.1f}점</span> | "
            f"{risk_map.get(nm,'')} | {type_map.get(nm,'')}<br>"
            f"<b>주요 원인:</b> {reasons}<br>"
            f"<b>추천 전략:</b> {recs}"
            f"</div>"
        )
        return folium.Popup(html, max_width=300)

    folium.GeoJson(
        gj,
        style_function=style_fn,
        highlight_function=highlight_fn,
        tooltip=folium.GeoJsonTooltip(
            fields=["full_nm"],
            aliases=["지역"],
            localize=True,
        ),
    ).add_to(m)

    # 점수 기준 상위 10 마커 추가
    for feat in gj["features"]:
        nm = feat["properties"].get("full_nm", "")
        score = score_map.get(nm)
        if score is None or score < 65:
            continue
        try:
            coords = feat["geometry"]["coordinates"]
            geom_type = feat["geometry"]["type"]
            if geom_type == "Polygon":
                pts = coords[0]
            elif geom_type == "MultiPolygon":
                pts = max(coords, key=len)[0]
            else:
                continue
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
        except Exception:
            continue
        folium.CircleMarker(
            location=[cy, cx],
            radius=6,
            color="#c84c3a",
            fill=True,
            fill_color="#c84c3a",
            fill_opacity=0.9,
            tooltip=f"{nm}: {score:.1f}점",
        ).add_to(m)

    m.save(str(output_path))


def save_all_charts(scored: pd.DataFrame, figure_dir: Path, geojson_path: Path | None = None) -> None:
    figure_dir.mkdir(parents=True, exist_ok=True)
    save_top_regions_chart(scored, figure_dir / "top_risk_regions.png")
    save_province_summary_chart(scored, figure_dir / "province_summary.png")
    save_score_distribution_chart(scored, figure_dir / "score_distribution.png")
    if geojson_path and geojson_path.exists():
        save_choropleth_map(scored, geojson_path, figure_dir / "choropleth_map.html")
