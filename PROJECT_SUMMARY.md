# 컬처갭 AI — 프로젝트 진행 요약

> 제4회 문화체육관광 인공지능·데이터 활용 공모전 출품작  
> 전국 시군구 단위 **문화결핍지수(Culture Gap Score)** 산출 및 사각지대 예측지도 서비스

---

## 1. 프로젝트 개요

**목표:** 문화 공급(시설·이벤트)과 수요(인구·고령화) 간의 불균형을 수치화해, 문화 지원이 필요한 시군구를 자동으로 탐지하는 AI 파이프라인 구축.

**문화결핍지수 공식:**
```
Culture Gap Score = 0.4 × 수요점수 + 0.3 × 공급결핍점수 + 0.2 × 접근성패널티 + 0.1 × 미스매치패널티
```

---

## 2. 데이터 현황

### raw 데이터 (`data/raw/`)

| 파일 | 내용 | 행 수 |
|------|------|-------|
| `culture_events.csv` | 공연·전시·행사 (area + sigungu 컬럼) | 8,625 |
| `culture_facilities.csv` | 문화시설 위경도·유형 | 6,476 |
| `museum_artgr_standard.csv` | 박물관·미술관 (`insttNm` = "시도 시군구" 형식) | 1,068 |
| `2026_festival.zip` | 축제 정보, 207개 시군구 커버 | 1,265 |
| `국토교통부_전국 버스정류장 위치정보_20251031.csv` | 전국 버스정류장 | 227,065 |
| `sigungu_age_pop_202605.csv` | **시군구 단위 연령별 인구** (행안부, 2026.05) | 296 |
| `sigungu_boundary_full.geojson` | 전국 시군구 경계 GeoJSON (14MB, 229개 피처) | — |

### processed 데이터 (`data/processed/`)

| 파일 | 내용 |
|------|------|
| `region_features.csv` | 247개 시군구 × 36개 피처 |
| `culture_gap_scores.csv` | 247개 시군구 점수·등급·유형·추천 |
| `region_clusters.csv` | 247개 시군구 군집 레이블 |

---

## 3. 파이프라인 구조

```
data/raw/  →  preprocessing.py  →  feature_engineering.py  →  scoring.py
                                                                    ↓
outputs/   ←  visualization.py  ←  recommendation.py  ←  clustering.py
```

### 각 모듈 역할

| 모듈 | 역할 |
|------|------|
| `preprocessing.py` | raw CSV 정제, 시군구 단위 통합, 인구 파싱 |
| `feature_engineering.py` | 시군구별 피처 36개 생성 |
| `scoring.py` | 문화결핍지수 및 위험 등급 산출 |
| `clustering.py` | KMeans(n=4) 지역 유형 군집화 |
| `recommendation.py` | 군집별 맞춤 정책 추천 문구 생성 |
| `visualization.py` | 차트 4종 + folium 인터랙티브 지도 |
| `run_pipeline.py` | 전체 파이프라인 실행 진입점 |

실행: `python src/run_pipeline.py` (프로젝트 루트 기준)

---

## 4. 주요 작업 이력

### 4-1. 초기 구조 설계
- 17개 시도 단위로 시작 → 5개 점수 차원(수요·공급·접근성·미스매치·취약성) 정의
- 위험 등급: 고위험(≥80) / 주의(60~79) / 보통(40~59) / 양호(<40)

### 4-2. 전국 시군구 단위 확장
- **문제:** 인구·이벤트 데이터가 시도 단위 → 시군구로 쪼개야 함
- **해결:** 이벤트+축제 건수를 가중치로 시도 인구를 시군구에 비례 배분
- **광역시 버스정류장:** 시 단위 정류장 수를 구별 이벤트 건수 비례로 배분

### 4-3. 데이터 정제 트러블슈팅
- `_is_sigungu_level()` — 읍·면·동·리 등 하위 행정구역 및 쉼표 포함 오염 항목 제거
- `_normalize_sigungu()` — "세종", "세종시", "세종특별자치시" 등 표기 통일
- 박물관 집계 오류 — `groupby("region_name")` → `groupby(["region_name","province"])`로 수정

### 4-4. 전국 GeoJSON 구축
- GADM 2013 기반 GeoJSON 다운로드 (southkorea-maps)
- 영문 `NAME_1`/`NAME_2` → 한글 `full_nm` 매핑: unidecode 정규화 + 39개 수동 보정 테이블로 **229/229 완전 매칭**
- folium 인터랙티브 지도 생성: LinearColormap + GeoJson 레이어 + CircleMarker + Popup

### 4-5. 시군구 단위 실제 인구 데이터 확보
- **문제:** 시도 단위 인구 CSV(18행)로는 시군구별 elderly_ratio가 도 내 전체 동일
- **시도:** KOSIS OpenAPI (키 없음) → 행안부 jumin.mois.go.kr (JS 기반 다운로드)
- **해결:** 행안부 POST 엔드포인트 직접 발견
  ```
  POST https://jumin.mois.go.kr/downloadCsvAge.do?searchYearMonth=month&xlsStats=2
  (state=2 = 전체시군구현황)
  ```
  → `sigungu_age_pop_202605.csv` 104KB, 296행 자동 다운로드 성공

### 4-6. 시(市)/구(區) granularity 정합 처리
- **문제:** 인구 CSV에는 "성남시"와 "성남시 분당구/수정구/중원구"가 **동시에** 존재 → double counting
- **해결1 (`preprocessing.py`):** trailing zeros 패턴으로 구 하위 행이 있는 시 총합 행 제거
  - 시 총합 코드: trailing zeros = 6 (예: `4113000000`)
  - 구 단위 코드: trailing zeros = 5 (예: `4113500000`)
- **문제2:** 이벤트 데이터는 "성남시" 단위로 집계 → "성남시 분당구" 행사 수 = 0이 되어 점수 왜곡
- **해결2 (`feature_engineering.py`):** `_distribute_city_events_to_gu()` 추가
  - 구 하위 행정구역이 있는 시의 이벤트를 인구 비례로 각 구에 배분

### 4-7. 노트북 생성
- `notebooks/make_notebooks.py` — nbformat으로 01~05번 노트북 자동 생성
  - 01_data_loading / 02_feature_engineering / 03_culture_gap_score / 04_clustering / 05_visualization

---

## 5. 현재 결과

| 지표 | 값 |
|------|-----|
| 분석 대상 시군구 | **247개** |
| 점수 범위 | 26.0 ~ 72.2 |
| 평균 점수 | 59.9 |
| 주의 등급 | 135개 (54.7%) |
| 보통 | 111개 (44.9%) |
| 양호 | 1개 (0.4%) |

### 상위 문화결핍 지역 Top 10

| 순위 | 지역 | 점수 | 특성 |
|-----:|------|-----:|------|
| 1 | 경기도 고양시 일산서구 | 72.2 | 대규모 인구 대비 공공이벤트 부족 |
| 2 | 세종특별자치시 | 69.4 | 신행정도시, 인구 급증 대비 문화 인프라 미성숙 |
| 3 | 인천광역시 강화군 | 68.6 | 섬 지역, 교통 취약 |
| 4 | 경기도 용인시 수지구 | 68.4 | 신도시 베드타운 |
| 5 | 경기도 화성시 효행구 | 67.9 | 신설 행정구역, 문화시설 미비 |
| 6 | 경기도 화성시 병점구 | 67.6 | 동일 |
| 7 | 전라남도 강진군 | 67.6 | 고령화율 51.3%, 농촌 교통취약형 |
| 8 | 경상북도 포항시 북구 | 66.7 | 중소도시, 이벤트 밀도 낮음 |
| 9 | 전라남도 장흥군 | 66.4 | 고령화, 인구 감소 농촌 |
| 10 | 전북특별자치도 전주시 덕진구 | 66.3 | 시 이벤트 구 분배 후 비중 큰 구 |

가장 양호: **서울특별시 종로구 (26.0)** — 세종문화회관·인사동·국립박물관 등 최고 문화 집적지

---

## 6. 산출물

### 코드 (`src/`)
- `preprocessing.py` — raw 데이터 정제 및 시군구 단위 통합
- `feature_engineering.py` — 피처 생성 + 시→구 이벤트 배분
- `scoring.py` — 문화결핍지수 산출
- `clustering.py` — 지역 유형 군집화
- `recommendation.py` — 맞춤 정책 추천
- `visualization.py` — 차트 + 지도
- `run_pipeline.py` — 실행 진입점

### 시각화 (`outputs/figures/`)
- `top_risk_regions.png` — 상위 15 시군구 가로 막대 차트
- `province_summary.png` — 시도별 평균점수 + 위험등급 스택 차트
- `score_distribution.png` — 점수 분포 히스토그램 + 파이차트 + 지역유형 차트
- `choropleth_map.html` — 전국 시군구 인터랙티브 단계구분도 (14MB, folium)

### 노트북 (`notebooks/`)
- `01_data_loading.ipynb` ~ `05_visualization.ipynb`

---

## 7. 알려진 한계

1. **공공 이벤트 데이터만 집계** — 사립 문화시설(CGV, 클래식 홀 등)이 많은 경기 신도시 구는 점수 과대 가능성
2. **시→구 이벤트 인구 비례 배분** — 실제 구별 이벤트 분포와 차이 존재
3. **GeoJSON 세종 미포함** — GADM 2013 기준으로 세종특별자치시 경계 없음
4. **1인가구비율 고정값(30%)** — 시군구별 실제 1인가구율 미반영
