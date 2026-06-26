# 데이터 원천 후보 및 수집 상태

실제 제출 버전에서는 아래 원천 중 최소 1개 이상의 문화체육관광부/문화공공데이터 계열 데이터를 사용해야 합니다. 현재 수집 코드는 `src/data_collect.py`에 있으며, API 인증키와 Swagger 요청 URL 또는 직접 다운로드 URL을 환경변수로 넣으면 `data/raw/`에 저장합니다.

| 우선순위 | 데이터 | 활용 | 저장 파일 | 수집 방식 |
|---:|---|---|---|---|
| 1 | 한국문화정보원_문화시설조회서비스 | 지역별 문화시설 수, 시설 유형 다양성 | `data/raw/culture_facilities.csv` | OpenAPI XML |
| 2 | 한국문화정보원_한눈에보는문화정보조회서비스 | 공연/전시/행사 공급, 무료 행사 비율 | `data/raw/culture_events.csv` | OpenAPI XML |
| 3 | 행정안전부_지역별 연령별 주민등록 인구현황 | 총인구, 청소년/고령층 비율 | `data/raw/population_age.csv` | 기관 페이지 CSV |
| 4 | 국토교통부_(센서스경계)시군구경계 | 시군구 지도 시각화 | `data/raw/sigungu_boundary.zip` | VWorld SHP |
| 5 | 전국문화축제표준데이터 | 연간 축제 수, 일회성 축제 의존도 | `data/raw/festivals_standard.csv` | 표준데이터 CSV/OpenAPI |
| 6 | 국토교통부_전국 버스정류장 위치정보 | 대중교통 접근성 | `data/raw/bus_stops.csv` | 파일 CSV 또는 자동변환 OpenAPI |

## 환경변수

```powershell
$env:DATA_GO_KR_SERVICE_KEY="공공데이터포털_인증키"
$env:CULTURE_FACILITIES_API_URL="문화시설조회서비스_Swagger_요청URL"
$env:CULTURE_EVENTS_API_URL="한눈에보는문화정보조회서비스_Swagger_요청URL"
$env:FESTIVALS_STANDARD_API_URL="전국문화축제표준데이터_OpenAPI_URL"
$env:BUS_STOPS_API_URL="전국_버스정류장_자동변환_OpenAPI_URL"
```

파일 직접 다운로드 URL이 있으면 아래처럼 넣을 수 있습니다.

```powershell
$env:POPULATION_AGE_DOWNLOAD_URL="인구CSV_직접다운로드URL"
$env:SIGUNGU_BOUNDARY_DOWNLOAD_URL="시군구경계SHP_ZIP_직접다운로드URL"
$env:BUS_STOPS_DOWNLOAD_URL="버스정류장CSV_직접다운로드URL"
$env:VWORLD_API_KEY="VWorld_인증키"
$env:VWORLD_API_DOMAIN="localhost 또는 등록도메인"
$env:VWORLD_ATTR_FILTER="단일검색용_속성필터"
$env:VWORLD_GEOM_FILTER="단일검색용_지오메트리필터"
```

## 실행

```powershell
python src/data_collect.py --plan
python src/data_collect.py --dataset culture_facilities --max-pages 5
python src/data_collect.py --dataset culture_events --max-pages 5
python src/data_collect.py --dataset sigungu_boundary
python src/data_collect.py --dataset all
```

## 교체 방법

1. `src/data_collect.py`로 원천 데이터를 `data/raw/`에 저장합니다.
2. 원천별 컬럼명을 분석용 표준 스키마로 정리합니다.
3. `python src/run_pipeline.py`를 실행합니다.

## 원천 페이지

- 한국문화정보원_문화시설조회서비스: https://www.data.go.kr/data/15138930/openapi.do?recommendDataYn=Y
- 전국박물관미술관정보표준데이터 OpenAPI: https://api.data.go.kr/openapi/tn_pubr_public_museum_artgr_info_api
- 한국문화정보원_한눈에보는문화정보조회서비스: https://www.data.go.kr/data/15138937/openapi.do
- 전국문화축제표준데이터: https://www.data.go.kr/data/15013104/standard.do
- 행정안전부_지역별 연령별 주민등록 인구현황: https://www.data.go.kr/data/3033304/fileData.do
- 국토교통부_(센서스경계)시군구경계: https://www.data.go.kr/data/15125064/fileData.do?recommendDataYn=Y
- VWorld 시군구 경계 API: https://api.vworld.kr/req/data?service=data&request=GetFeature&data=LT_C_ADSIGG_INFO
- 국토교통부_전국 버스정류장 위치정보: https://www.data.go.kr/data/15067528/fileData.do

## 현재 수집 완료

| 파일 | 원천 | 행 수 | 주요 컬럼 |
|---|---|---:|---|
| `data/raw/culture_facilities.csv` | 한국문화정보원_문화시설조회서비스 | 6,476 | `culName`, `culGrpName`, `gpsX`, `gpsY`, `culHomeUrl`, `source_path` |
| `data/raw/museum_artgr_standard.csv` | 전국박물관미술관정보표준데이터 OpenAPI | 1,068 | `fcltyNm`, `fcltyType`, `rdnmadr`, `latitude`, `longitude`, `adultChrge`, `trnsportInfo` |
| `data/raw/culture_events.csv` | 한국문화정보원_한눈에보는문화정보조회서비스 | 8,625 | `serviceName`, `title`, `startDate`, `endDate`, `place`, `realmName`, `area`, `sigungu`, `gpsX`, `gpsY` |

`culture_facilities.csv`는 `artgallery`, `museum`, `hall`, `library`, `performingplace` 5개 기능 경로를 합친 파일입니다.
`culture_events.csv`는 2026년 기간별 목록(`period2`, `from=20260101`, `to=20261231`) 기준입니다.

시군구 경계는 VWorld 인증키가 필요하므로, 키 없이 테스트할 수 있는 샘플을 함께 둡니다.

```text
data/raw/sigungu_boundary_sample.geojson
data/raw/sigungu_boundary_sample.csv
```
