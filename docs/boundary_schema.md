# 시군구 경계 데이터 스키마

## 목적

시군구 단위 문화결핍지수를 지도에 표시하기 위한 행정경계 데이터입니다. MVP에서는 시군구 단위 경계를 우선 사용하고, 좌표계는 `EPSG:4326`을 기본값으로 둡니다.

## 요청 파라미터 후보

| 항목 | 설명 | 비고 |
|---|---|---|
| `service` | 요청 서비스명 | 경계/공간정보 서비스명 |
| `request` | 요청 서비스 오퍼레이션 이름 | 조회/다운로드 오퍼레이션 |
| `version` | 요청 서비스 버전 | API 제공 버전에 맞춤 |
| `format` | 응답 포맷 | `json`, `geojson`, `shp` 등 |
| `crs` | 지원 좌표계 | `EPSG:4326` 기본값 |
| `geomFilter` | 지오메트리 필터 | bbox, polygon 등 공간 필터가 필요할 때 사용 |
| `attrFilter` | 속성 필터 | 단일검색에서 행정구역코드/시군구명 조건으로 사용 |
| `data` | 레이어명 | `LT_C_ADSIGG_INFO` |
| `key` | VWorld 인증키 | 필수 |
| `domain` | 인증키 등록 도메인 | 브라우저/웹뷰어가 아닌 호출에서 필요할 수 있음 |

## 단일검색

전체 시군구 경계를 받는 기본 수집은 필터 없이 실행합니다. 특정 시군구만 받을 때는 VWorld의 속성 필터 또는 지오메트리 필터를 환경변수로 지정합니다.

VWorld 레퍼런스 기준으로 `GEOMETRY 데이터 단일검색=Y`인 경우, `geomFilter` 없이도 해당 속성명, 예를 들어 `pnu`, `sig_cd` 같은 컬럼이 포함된 `attrFilter`만으로 검색할 수 있습니다.

```powershell
$env:VWORLD_ATTR_FILTER="sig_cd:=:11650"
python src/data_collect.py --dataset sigungu_boundary
```

`pnu` 속성으로 단일검색을 지원하는 레이어라면 다음 형태를 사용합니다.

```powershell
$env:VWORLD_ATTR_FILTER="pnu:=:1165010800100010000"
python src/data_collect.py --dataset sigungu_boundary
```

`attrFilter` 형식:

```text
속성명A:연산자A:비교값A|속성명B:연산자B:비교값B
```

여러 조건은 `|`로 구분하고, 한 조건의 내부는 `:`로 구분합니다.

연산자:

```text
=
>=
<=
<
>
<>
BETWEEN  포맷: min,max
LIKE
IN       포맷: 값1,값2
```

예시:

```text
attrFilter=uname:like:제2종일반|dyear:between:2000,2015|emdCd:=:41173102
```

단, 단일검색=Y가 있는 경우에는 해당 속성명인 `sig_cd`, `full_nm`, `sig_kor_nm`을 포함하면 `geomFilter` 없이 `attrFilter`만으로 검색할 수 있습니다.

```text
attrFilter=sig_cd:=:검색값
```

단일검색=Y가 없고 `geomFilter`도 없을 경우에는 `emdCd` 읍면동코드 조건이 필수일 수 있습니다. 이 경우 읍면동코드 조회 후 다음처럼 조건을 지정합니다.

```text
attrFilter=emdCd:=:41173102
```

공간 조건으로 제한할 때는 `geomFilter`를 사용합니다.

```powershell
$env:VWORLD_GEOM_FILTER="BOX(126.7,37.4,127.2,37.8)"
python src/data_collect.py --dataset sigungu_boundary
```

`geomFilter` 지원 형식:

```text
POINT(x y)
LINESTRING(x1 y1,x2 y2 [,xn yn])
POLYGON((x1 y1,x2 y2[,xn yn]))
MULTIPOLYGON(((x1 y1,x2 y2[,xn yn]))[,((x1 y1,x2 y2 [,xn yn]))])
BOX(minx,miny,maxx,maxy)
```

## 오퍼레이션

| 항목 | 값 |
|---|---|
| 요청 URL | `https://api.vworld.kr/req/data` |
| 서비스 | `data` |
| 오퍼레이션 | `GetFeature` |
| 레이어 | `LT_C_ADSIGG_INFO` |
| 기본 좌표계 | `EPSG:4326` |
| 기본 포맷 | `json` |

### GetFeature

시군구의 도형과 속성 정보를 조회합니다. WFS보다 간결한 형태의 데이터 조회 기능을 제공하며, 복잡한 Query가 필요할 경우 WFS 사용을 검토합니다.

### GetFeatureType

시군구 데이터의 타입, 즉 스키마를 조회하는 오퍼레이션입니다. 수집 전 필드명, 필수 여부, 지오메트리 타입을 점검할 때 사용합니다. 현재 레퍼런스상 서비스 예정으로 표시되어 있으면 실제 수집에는 `GetFeature` 응답 샘플과 문서 필드표를 기준으로 스키마를 관리합니다.

## 요청파라미터

| 파라미터 | 구분 | 레퍼런스 표기 | 설명 | 예시 |
|---|---|---|---|---|
| `service` | 필수 | `O/1` | 요청 서비스명 | `data` 기본값 |
| `request` | 필수 | `M/1` | 요청 서비스 오퍼레이션 이름 | `GetFeature`, `GetFeatureType` |
| `data` | 필수 | `M/1` | 조회할 데이터 | `LT_C_ADSIGG_INFO` |
| `key` | 필수 | `M/1` | 발급받은 인증키 | `VWorld 인증키` |
| `domain` | 선택 |  | 인증키 등록 도메인 | `localhost` |
| `version` | 선택 | `O/1` | 요청 서비스 버전 | `2.0(기본값)` |
| `format` | 선택 | `O/1` | 응답 결과 포맷 | `json(기본값), xml` |
| `errorFormat` | 선택 | `O/1` | 에러 응답결과 포맷, 생략 시 `format` 파라미터에 지정된 포맷으로 설정 | `json, xml` |
| `crs` | 선택 | `O/1` | 좌표계 | `EPSG:4326` |
| `page` | 선택 | `O/1` | 응답결과 페이지 번호 | 기본값: `1` |
| `size` | 선택 | `O/1` | 한 페이지에 출력될 응답결과 건수 | 숫자, `default(10)`, `min(1)`, `max(1000)` |
| `attrFilter` | 선택 | `O/n` | 속성조회를 위한 조건검색 | `sig_cd:=:11650` |
| `geomFilter` | 선택 | `M/1` | 지오메트리 필터 | `BOX(126.7,37.4,127.2,37.8)` |
| `columns` | 선택 | `O/1` | 응답결과로 받기를 원하는 컬럼, 생략 시 전체 컬럼 반환 | `sig_cd,full_nm,sig_kor_nm` |
| `geometry` | 선택 | `O/1` | 지오메트리 반환 여부 | `true(기본값), false` |
| `attribute` | 선택 | `O/1` | 속성 반환 여부 | `true(기본값), false` |
| `buffer` | 선택 | `O/1` | `geomFilter` 파라미터에 입력한 feature를 `buffer`(거리, 단위:m)만큼 확장 | 숫자, 기본값: `0` |

## 정상 응답 필드 후보

| 필드 | 설명 | 활용 |
|---|---|---|
| `baseDate` 또는 `updateDate` | 갱신일 | 데이터 기준일 표시 |
| `sig_cd` | 시군구 행정구역코드 | 필수값(`Y`), 분석 테이블 조인 키 |
| `admCd` 또는 `sigunguCd` | 행정구역코드 | 원천별 대체 컬럼명 |
| `admNm` 또는 `admName` | 행정구역명 | 지도 툴팁/라벨 |
| `sig_kor_nm` | 시군구 한글명 | 필수값(`Y`), 지도 라벨/툴팁 |
| `sig_eng_nm` | 시군구 영문명 | 필수값(`N`), 영문 지도 라벨/외부 연계 |
| `sigunguNm` | 시군구명 | 원천별 대체 컬럼명 |
| `full_nm` | 전체 행정구역명 | 필수값(`Y`), 예: `서울특별시 서초구` |
| `ag_geom` | 경계 지오메트리 | 필수값(`N`), WKT/원천 지오메트리 보조 컬럼 |
| `geometry` | 선택 | `O/1` | 지오메트리 반환 여부 | `true(기본값), false` |
| `attribute` | 선택 | `O/1` | 속성 반환 여부 | `true(기본값), false` |
| `createdTime` | 응답결과 생성 시간 | 수집 로그/재현성 |

## 오류 응답 필드 후보

| 필드 | 설명 |
|---|---|
| `level` | 에러 레벨 |
| `code` | 에러 코드 |
| `message` | 에러 메시지 |
| `errorMessage` | 오류메세지 |
| `remark` | 비고 |

## 저장 파일

원천 SHP 또는 ZIP:

```text
data/raw/sigungu_boundary.zip
```

변환 후 GeoJSON:

```text
data/processed/sigungu_boundary.geojson
```

키가 없을 때 파서와 지도 결합을 테스트하기 위한 샘플:

```text
data/raw/sigungu_boundary_sample.geojson
data/raw/sigungu_boundary_sample.csv
```

## 분석 결합 기준

문화시설/행사 데이터는 좌표 또는 주소에서 시도/시군구를 추출하고, 경계 데이터의 `sig_cd`, `sig_kor_nm`, `full_nm`과 매칭합니다. 최종 지도 조인은 `region_code` 또는 표준화한 `province + sigungu` 조합을 사용합니다.
