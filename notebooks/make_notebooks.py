"""노트북 5개를 생성하는 스크립트."""
from __future__ import annotations
import json
from pathlib import Path
import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell


def nb(cells) -> nbformat.NotebookNode:
    notebook = new_notebook()
    notebook.cells = cells
    notebook.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    return notebook


def save(notebook, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        nbformat.write(notebook, f)
    print(f"저장: {path}")


OUT = Path(__file__).parent

# ─────────────────────────────────────────────────────────────
# 01 데이터 로딩
# ─────────────────────────────────────────────────────────────
nb01 = nb([
    new_markdown_cell("# 01. 데이터 로딩\n\n원천 데이터를 읽고 전처리하여 시군구 단위 기본 데이터를 구성합니다."),
    new_code_cell(
        "import sys\n"
        "sys.path.insert(0, '../src')\n"
        "import pandas as pd\n"
        "import warnings\n"
        "warnings.filterwarnings('ignore')\n"
        "pd.set_option('display.max_columns', 50)\n"
        "pd.set_option('display.width', 120)\n"
        "print('환경 로드 완료')"
    ),
    new_markdown_cell("## 1-1. 원천 파일 목록"),
    new_code_cell(
        "from pathlib import Path\n"
        "raw_dir = Path('../data/raw')\n"
        "for f in sorted(raw_dir.iterdir()):\n"
        "    if f.is_file():\n"
        "        size_kb = f.stat().st_size / 1024\n"
        "        print(f'{f.name:50s}  {size_kb:8.0f} KB')"
    ),
    new_markdown_cell("## 1-2. 문화행사 데이터"),
    new_code_cell(
        "from preprocessing import standardize_culture_events\n"
        "events = standardize_culture_events()\n"
        "print(f'행 수: {len(events):,}  / 컬럼: {list(events.columns)}')\n"
        "events.head(5)"
    ),
    new_code_cell(
        "print('시도별 행사 수:')\n"
        "events.groupby('province')['event_name'].count().sort_values(ascending=False)"
    ),
    new_markdown_cell("## 1-3. 박물관·미술관 데이터"),
    new_code_cell(
        "from preprocessing import standardize_museums\n"
        "museums = standardize_museums()\n"
        "print(f'행 수: {len(museums):,}')\n"
        "print('시설 유형:', museums['facility_type'].value_counts().head(5).to_dict())\n"
        "museums.head(5)"
    ),
    new_markdown_cell("## 1-4. 지역축제 데이터"),
    new_code_cell(
        "from preprocessing import standardize_festivals\n"
        "festivals = standardize_festivals()\n"
        "print(f'행 수: {len(festivals):,}  / 시군구: {festivals[\"sigungu\"].nunique()}개')\n"
        "print('상위 시군구:\\n', festivals.groupby([\"province\",\"sigungu\"]).size().sort_values(ascending=False).head(10))"
    ),
    new_markdown_cell("## 1-5. 버스정류장 데이터"),
    new_code_cell(
        "from preprocessing import standardize_bus_stops\n"
        "bus = standardize_bus_stops()\n"
        "print(f'행 수: {len(bus):,}  / 고유 지역: {bus[\"region_name\"].nunique()}개')\n"
        "bus.groupby('province')['bus_stop_id'].count().sort_values(ascending=False)"
    ),
    new_markdown_cell("## 1-6. 시군구 단위 인구 (시도 비례 배분)"),
    new_code_cell(
        "from preprocessing import standardize_population\n"
        "pop = standardize_population()\n"
        "print(f'시군구 수: {len(pop)}개')\n"
        "print('점수 상위 인구 지역:')\n"
        "pop.sort_values('population', ascending=False).head(10)[['region_name','population','youth_ratio','elderly_ratio']]"
    ),
    new_markdown_cell("## 1-7. 전체 raw 로드"),
    new_code_cell(
        "from preprocessing import load_raw_data\n"
        "raw = load_raw_data()\n"
        "for k, v in raw.items():\n"
        "    print(f'{k:15s}: {len(v):6,}행  컬럼={list(v.columns)[:5]}')"
    ),
])
save(nb01, OUT / "01_data_loading.ipynb")


# ─────────────────────────────────────────────────────────────
# 02 피처 엔지니어링
# ─────────────────────────────────────────────────────────────
nb02 = nb([
    new_markdown_cell("# 02. 피처 엔지니어링\n\n시군구별로 문화공급·수요·접근성 변수를 계산합니다."),
    new_code_cell(
        "import sys\n"
        "sys.path.insert(0, '../src')\n"
        "import pandas as pd, warnings\n"
        "warnings.filterwarnings('ignore')\n"
        "from preprocessing import load_raw_data\n"
        "from feature_engineering import build_region_features_from_raw\n"
        "raw = load_raw_data()\n"
        "features = build_region_features_from_raw(raw)\n"
        "print(f'시군구: {len(features)}개 / 피처: {len(features.columns)}개')"
    ),
    new_markdown_cell("## 2-1. 핵심 변수 분포"),
    new_code_cell(
        "key_cols = ['facility_per_10k','event_per_month','museum_count',\n"
        "            'festival_count','bus_stop_count','elderly_ratio','youth_ratio']\n"
        "features[key_cols].describe().round(2)"
    ),
    new_markdown_cell("## 2-2. 문화공급 최상위 시군구"),
    new_code_cell(
        "features.sort_values('event_per_month', ascending=False).head(10)\n"
        "[['region_name','population','event_per_month','museum_count','festival_count','bus_stop_count']]"
    ),
    new_markdown_cell("## 2-3. 접근성 최취약 시군구 (교통 취약 상위)"),
    new_code_cell(
        "features.sort_values('transport_weakness', ascending=False).head(10)\n"
        "[['region_name','province','transport_weakness','rural_flag','elderly_ratio']]"
    ),
    new_markdown_cell("## 2-4. 프로그램 미스매치"),
    new_code_cell(
        "import matplotlib.pyplot as plt\n"
        "plt.rcParams['font.family'] = 'Malgun Gothic'\n"
        "fig, axes = plt.subplots(1, 2, figsize=(12, 4))\n"
        "features['elderly_program_ratio'].hist(bins=20, ax=axes[0], color='#e8956b')\n"
        "axes[0].set_title('고령층 친화 프로그램 비율')\n"
        "axes[0].set_xlabel('비율')\n"
        "features['youth_program_ratio'].hist(bins=20, ax=axes[1], color='#5b8fde')\n"
        "axes[1].set_title('청소년 교육형 프로그램 비율')\n"
        "axes[1].set_xlabel('비율')\n"
        "plt.tight_layout()\n"
        "plt.show()"
    ),
    new_markdown_cell("## 2-5. 피처 상관관계"),
    new_code_cell(
        "corr_cols = ['facility_per_10k','event_per_month','elderly_ratio',\n"
        "             'youth_ratio','transport_weakness','mismatch_raw']\n"
        "features[corr_cols].corr().round(2)"
    ),
])
save(nb02, OUT / "02_feature_engineering.ipynb")


# ─────────────────────────────────────────────────────────────
# 03 문화결핍지수
# ─────────────────────────────────────────────────────────────
nb03 = nb([
    new_markdown_cell(
        "# 03. 문화결핍지수 산출\n\n"
        "문화공급지수·수요지수·접근성 패널티·미스매치 패널티를 결합해\n"
        "시군구별 Culture Gap Score를 산출합니다.\n\n"
        "$$\\text{Culture Gap Score} = 0.4 \\times \\text{Demand} + 0.3 \\times \\text{Supply Deficit} + 0.2 \\times \\text{Access Penalty} + 0.1 \\times \\text{Mismatch}$$"
    ),
    new_code_cell(
        "import sys\n"
        "sys.path.insert(0, '../src')\n"
        "import pandas as pd, matplotlib.pyplot as plt, warnings\n"
        "warnings.filterwarnings('ignore')\n"
        "plt.rcParams['font.family'] = 'Malgun Gothic'\n"
        "from preprocessing import load_raw_data\n"
        "from feature_engineering import build_region_features_from_raw\n"
        "from scoring import add_scores\n"
        "raw = load_raw_data()\n"
        "features = build_region_features_from_raw(raw)\n"
        "scored = add_scores(features)\n"
        "print('점수 통계:')\n"
        "scored[['supply_score','demand_score','access_penalty','mismatch_penalty','culture_gap_score']].describe().round(1)"
    ),
    new_markdown_cell("## 3-1. 위험 등급 분포"),
    new_code_cell(
        "risk_cnt = scored['risk_level'].value_counts()\n"
        "colors = {'고위험':'#c84c3a','주의':'#e8956b','보통':'#f5c842','양호':'#4caf7d'}\n"
        "risk_cnt.plot.pie(colors=[colors.get(r,'gray') for r in risk_cnt.index],\n"
        "                  autopct='%1.1f%%', figsize=(5,5))\n"
        "plt.title('전국 시군구 위험 등급 비율')\n"
        "plt.ylabel('')\n"
        "plt.show()\n"
        "print(risk_cnt)"
    ),
    new_markdown_cell("## 3-2. 점수 구성 요소 분석"),
    new_code_cell(
        "top20 = scored.sort_values('culture_gap_score', ascending=False).head(20)\n"
        "components = top20[['region_name','demand_score','supply_score',\n"
        "                      'access_penalty','mismatch_penalty','culture_gap_score']]\n"
        "components"
    ),
    new_markdown_cell("## 3-3. 시도별 평균 점수"),
    new_code_cell(
        "prov_avg = scored.groupby('province')['culture_gap_score'].mean().sort_values(ascending=False)\n"
        "fig, ax = plt.subplots(figsize=(8, 6))\n"
        "bars = ax.barh(prov_avg.index, prov_avg.values,\n"
        "               color=['#c84c3a' if s >= 60 else '#e8956b' if s >= 55 else '#f5c842' for s in prov_avg.values])\n"
        "ax.axvline(x=60, color='red', linestyle='--', linewidth=0.8)\n"
        "ax.set_xlabel('평균 문화결핍지수')\n"
        "ax.set_title('시도별 평균 문화결핍지수')\n"
        "ax.invert_yaxis()\n"
        "plt.tight_layout()\n"
        "plt.show()"
    ),
    new_markdown_cell("## 3-4. 문화결핍지수 하위 지역 (가장 양호)"),
    new_code_cell(
        "scored.sort_values('culture_gap_score').head(10)\n"
        "[['region_name','province','supply_score','demand_score','culture_gap_score','risk_level']]"
    ),
])
save(nb03, OUT / "03_culture_gap_score.ipynb")


# ─────────────────────────────────────────────────────────────
# 04 군집화
# ─────────────────────────────────────────────────────────────
nb04 = nb([
    new_markdown_cell(
        "# 04. 지역 유형 군집화\n\n"
        "K-Means로 시군구를 문화결핍 유형별로 분류하고\n"
        "맞춤형 정책 추천을 도출합니다."
    ),
    new_code_cell(
        "import sys\n"
        "sys.path.insert(0, '../src')\n"
        "import pandas as pd, matplotlib.pyplot as plt, warnings\n"
        "warnings.filterwarnings('ignore')\n"
        "plt.rcParams['font.family'] = 'Malgun Gothic'\n"
        "from preprocessing import load_raw_data\n"
        "from feature_engineering import build_region_features_from_raw\n"
        "from scoring import add_scores\n"
        "from clustering import add_clusters\n"
        "from recommendation import add_recommendations\n"
        "raw = load_raw_data()\n"
        "features = build_region_features_from_raw(raw)\n"
        "scored = add_scores(features)\n"
        "clustered = add_clusters(scored)\n"
        "result = add_recommendations(clustered)\n"
        "print('군집별 시군구 수:')\n"
        "print(result['cluster'].value_counts().sort_index())"
    ),
    new_markdown_cell("## 4-1. 군집별 평균 지표"),
    new_code_cell(
        "cluster_profile = result.groupby('cluster')[\n"
        "    ['supply_score','demand_score','access_penalty','mismatch_penalty','culture_gap_score']\n"
        "].mean().round(1)\n"
        "cluster_profile"
    ),
    new_markdown_cell("## 4-2. 지역 유형 분포"),
    new_code_cell(
        "type_cnt = result['region_type'].value_counts()\n"
        "type_cnt.plot.barh(figsize=(8, 4), color='#5b8fde')\n"
        "plt.gca().invert_yaxis()\n"
        "plt.xlabel('시군구 수')\n"
        "plt.title('전국 문화결핍 지역 유형 분포')\n"
        "plt.tight_layout()\n"
        "plt.show()"
    ),
    new_markdown_cell("## 4-3. 유형별 대표 지역"),
    new_code_cell(
        "for rtype in result['region_type'].unique():\n"
        "    sub = result[result['region_type']==rtype].sort_values('culture_gap_score', ascending=False)\n"
        "    rep = sub.head(3)['region_name'].tolist()\n"
        "    print(f'[{rtype}] 대표 지역: {rep}')"
    ),
    new_markdown_cell("## 4-4. 정책 추천 샘플"),
    new_code_cell(
        "top = result.sort_values('culture_gap_score', ascending=False).head(5)\n"
        "for _, row in top.iterrows():\n"
        "    print(f\"\\n■ {row['region_name']} ({row['culture_gap_score']}점 / {row['risk_level']})\")\n"
        "    print(f\"  유형: {row['region_type']}\")\n"
        "    print(f\"  원인: {row['main_reasons']}\")\n"
        "    print(f\"  추천: {row['policy_recommendations']}\")"
    ),
])
save(nb04, OUT / "04_clustering.ipynb")


# ─────────────────────────────────────────────────────────────
# 05 시각화
# ─────────────────────────────────────────────────────────────
nb05 = nb([
    new_markdown_cell(
        "# 05. 시각화\n\n"
        "문화결핍지수 지도, 차트, 인터랙티브 지도를 생성합니다.\n\n"
        "생성 파일:\n"
        "- `outputs/figures/top_risk_regions.png`\n"
        "- `outputs/figures/province_summary.png`\n"
        "- `outputs/figures/score_distribution.png`\n"
        "- `outputs/figures/choropleth_map.html`"
    ),
    new_code_cell(
        "import sys\n"
        "sys.path.insert(0, '../src')\n"
        "import pandas as pd, warnings\n"
        "warnings.filterwarnings('ignore')\n"
        "from preprocessing import load_raw_data\n"
        "from feature_engineering import build_region_features_from_raw\n"
        "from scoring import add_scores\n"
        "from clustering import add_clusters\n"
        "from recommendation import add_recommendations\n"
        "from visualization import save_all_charts\n"
        "from pathlib import Path\n"
        "\n"
        "raw = load_raw_data()\n"
        "features = build_region_features_from_raw(raw)\n"
        "scored = add_recommendations(add_clusters(add_scores(features)))\n"
        "print(f'대상 시군구: {len(scored)}개')"
    ),
    new_markdown_cell("## 5-1. Top 15 차트"),
    new_code_cell(
        "import matplotlib.pyplot as plt\n"
        "plt.rcParams['font.family'] = 'Malgun Gothic'\n"
        "plt.rcParams['axes.unicode_minus'] = False\n"
        "\n"
        "top = scored.sort_values('culture_gap_score', ascending=False).head(15)\n"
        "colors = ['#c84c3a' if r=='주의' else '#e8956b' for r in top['risk_level']]\n"
        "fig, ax = plt.subplots(figsize=(10, 6))\n"
        "ax.barh(top['region_name'], top['culture_gap_score'], color=colors)\n"
        "ax.invert_yaxis()\n"
        "ax.axvline(x=60, color='red', linestyle='--', linewidth=0.8)\n"
        "ax.set_xlabel('문화결핍지수')\n"
        "ax.set_title('문화 사각지대 고위험 시군구 Top 15', fontweight='bold')\n"
        "plt.tight_layout()\n"
        "plt.show()"
    ),
    new_markdown_cell("## 5-2. 시도별 요약 차트"),
    new_code_cell(
        "prov = scored.groupby('province')['culture_gap_score'].agg(['mean','count']).sort_values('mean', ascending=False)\n"
        "risk = scored.groupby(['province','risk_level']).size().unstack(fill_value=0)\n"
        "\n"
        "fig, axes = plt.subplots(1, 2, figsize=(14, 6))\n"
        "axes[0].barh(prov.index, prov['mean'],\n"
        "             color=['#c84c3a' if s>=60 else '#e8956b' for s in prov['mean']])\n"
        "axes[0].set_title('시도별 평균 문화결핍지수')\n"
        "axes[0].invert_yaxis()\n"
        "\n"
        "risk_cols = [c for c in ['주의','보통','양호'] if c in risk.columns]\n"
        "risk_colors = {'주의':'#e8956b','보통':'#f5c842','양호':'#4caf7d'}\n"
        "bottom = pd.Series(0, index=risk.index)\n"
        "for col in risk_cols:\n"
        "    axes[1].barh(risk.index, risk[col], left=bottom, label=col, color=risk_colors[col])\n"
        "    bottom += risk[col]\n"
        "axes[1].legend()\n"
        "axes[1].set_title('시도별 위험 등급 분포')\n"
        "axes[1].invert_yaxis()\n"
        "plt.tight_layout()\n"
        "plt.show()"
    ),
    new_markdown_cell("## 5-3. 인터랙티브 지도 생성 및 저장"),
    new_code_cell(
        "geojson_path = Path('../data/raw/sigungu_boundary_full.geojson')\n"
        "figure_dir = Path('../outputs/figures')\n"
        "save_all_charts(scored, figure_dir, geojson_path)\n"
        "print('저장 완료:')\n"
        "for f in sorted(figure_dir.iterdir()):\n"
        "    print(f'  {f.name}')"
    ),
    new_markdown_cell("## 5-4. 인터랙티브 지도 미리보기 (Jupyter)"),
    new_code_cell(
        "from IPython.display import IFrame\n"
        "IFrame('../outputs/figures/choropleth_map.html', width=900, height=550)"
    ),
])
save(nb05, OUT / "05_visualization.ipynb")

print("\\n노트북 5개 생성 완료!")
