# 컬처갭 AI

> 공공 문화데이터 기반 문화 사각지대 예측지도  
> 제4회 문화체육관광 인공지능·데이터 활용 공모전 MVP

문화시설 수뿐 아니라 **행사 공급 밀도·프로그램 다양성·무료 접근성·인구구조·교통 취약성**을 함께 반영해  
전국 247개 시군구의 **문화결핍지수(Culture Gap Score)** 를 산출하고,  
지역별 결핍 원인과 맞춤형 문화행사를 추천합니다.

---

## 빠른 실행

```powershell
pip install -r requirements.txt
python src/run_pipeline.py
streamlit run app/streamlit_app.py
```

---

## 분석 결과 요약

| 항목 | 수치 |
|---|---|
| 분석 지역 | 247개 시군구 |
| 평균 문화결핍지수 | 59.9점 |
| 주의 이상 지역 | 135개 (55%) |
| 분류된 행사 수 | 9,890건 (활성: 1,898건) |
| 추천 생성 | 1,350건 (135개 지역 × Top 10) |
| Top-1 행사 고유 비율 | 134 / 135개 지역 |

**주요 문화 사각지대 (상위 5개)**

| 순위 | 지역 | 결핍지수 | 유형 |
|---:|---|---:|---|
| 1 | 경기도 고양시 일산서구 | 72.2 | 시설·행사 부족형 |
| 2 | 세종특별자치시 | 69.4 | 시설·행사 부족형 |
| 3 | 경기도 용인시 수지구 | 68.4 | 시설·행사 부족형 |
| 4 | 인천광역시 강화군 | 68.6 | 고령층 교통취약형 |
| 5 | 전라남도 강진군 | 67.6 | 고령층 교통취약형 |

---

## 산식

```
Culture Gap Score
= 0.40 × 문화수요지수
+ 0.30 × 공급결핍 (= 100 - 공급지수)
+ 0.20 × 접근성 패널티
+ 0.10 × 미스매치 패널티
```

각 구성 점수는 전국 0~100 min-max 정규화.

---

## AI 활용 포인트

### 1단: 행사 텍스트 자동 분류 (`src/classify_events.py`)

9,890건 행사·축제에 4개 축 자동 태깅:

- **장르**: 공연 / 전시 / 체험·교육 / 축제 / 기타
- **대상계층**: 일반·전문 / 가족·아동 / 청소년·교육 / 고령친화 (수혜자 명시 키워드만 허용)
- **시간대**: 주간 / 야간 / 종일
- **가격**: 유료 / 무료·저비용 (제목 키워드 우선, 장르 기본값 보완)

### 2단: 결핍 지역 맞춤 행사 매칭 (`src/match_events.py`)

- 종료 행사 필터: 9,890 → 1,898건 (오늘 기준)
- 지역 결핍 프로필 × 행사 태그 점수 매칭
- Haversine 거리 계산 → 교통취약 지역 원거리 행사 강력 패널티
- 다양성 재랭킹: 복붙 없음 (134/135개 지역 고유 추천)
- culture.go.kr 직접 링크 포함

### 지역 유형 군집화 (`src/clustering.py`)

K-Means로 4가지 결핍 유형 분류:

| 유형 | 지역 수 | 핵심 문제 | 추천 정책 |
|---|---:|---|---|
| 고령층 교통취약형 | 92개 | 고령 인구 높고 교통 취약 | 찾아가는 문화버스, 낮 시간 무료 프로그램 |
| 시설·행사 부족형 | 73개 | 공연·전시 행사 절대적 부족 | 순회공연 유치, 문화재단 연계 기획전 |
| 균형 관리형 | 74개 | 전반 양호, 특정 계층 공백 | 청소년·가족 프로그램 다양화 |
| 교통 취약형 | 8개 | 시설은 있지만 접근 어려움 | 셔틀, 찾아가는 문화서비스 |

---

## Streamlit 대시보드

```powershell
streamlit run app/streamlit_app.py
```

4개 탭 구성:

- **전국 지도**: 시군구별 결핍지수 choropleth, 상위 10개 지역 마커
- **지역 리포트**: 수요·공급·접근성·미스매치 점수 상세, 원인 카드, 정책 추천
- **행사 추천**: 지역 결핍 프로필 맞춤 행사 Top 10 (장르·가격·거리·링크)
- **정책 시뮬레이션**: 행사 추가·무료 비율·교통 개선 → 개선 점수 즉시 예측

---

## 주요 산출물

| 파일 | 설명 |
|---|---|
| `data/processed/culture_gap_scores.csv` | 247개 시군구 최종 점수 |
| `data/processed/classified_events.csv` | 9,890개 행사 태그 분류 결과 |
| `data/processed/event_recommendations.csv` | 1,350건 맞춤 행사 추천 |
| `outputs/tables/top_risk_regions.csv` | 문화 사각지대 상위 10개 |
| `outputs/figures/choropleth_map.html` | 전국 결핍지수 지도 (14MB) |
| `outputs/reports/mvp_summary.md` | 분석 요약 보고서 |
| `docs/proposal_draft.md` | 공모전 제출 기획서 |

---

## 데이터 출처

전체 출처와 API 키 설정 방법: `data/external/data_source_urls.md`

| 데이터 | 기관 |
|---|---|
| 공연·전시·문화행사 (8,625건) | culture.go.kr (문체부) |
| 전국 지역축제 (1,265건) | 문화체육관광부 |
| 문화시설 (6,476건) | culture.go.kr (문체부) |
| 박물관·미술관 (1,068개) | 공공데이터포털 |
| 시군구 인구 (2026.05) | 행정안전부 |
| 버스정류장 (2025.10) | 국토교통부 |
| 행정경계 GeoJSON | 국토교통부 / VWorld |

---

## 폴더 구조

```
개개비/
├── app/
│   └── streamlit_app.py      # 4탭 대시보드
├── src/
│   ├── run_pipeline.py       # 전체 파이프라인 실행
│   ├── preprocessing.py      # 데이터 로드·정제
│   ├── feature_engineering.py# 시군구별 특성 집계
│   ├── scoring.py            # 문화결핍지수 계산
│   ├── clustering.py         # 지역 유형 군집화
│   ├── classify_events.py    # AI 행사 분류 (1단)
│   ├── match_events.py       # 맞춤 행사 추천 (2단)
│   └── visualization.py      # 지도·차트 생성
├── data/
│   ├── raw/                  # 원본 공공데이터
│   └── processed/            # 분석 결과
├── outputs/
│   ├── figures/              # 지도·차트
│   ├── tables/               # 상위 지역 표
│   └── reports/              # 요약 보고서
├── docs/
│   ├── proposal_draft.md     # 공모전 제출 기획서
│   ├── competition_summary.md# 공모전 대응 전략
│   ├── scoring_criteria_mapping.md
│   └── presentation_outline.md
└── requirements.txt
```
