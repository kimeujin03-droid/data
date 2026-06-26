from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd
import requests


CONFIG_PATH = Path("config/data_sources.json")


def load_config(path: Path = CONFIG_PATH) -> dict[str, dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def env(name: str | None) -> str | None:
    if not name:
        return None
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def collect_dataset(name: str, spec: dict[str, Any], rows: int, max_pages: int) -> Path:
    output = Path(spec["output"])
    output.parent.mkdir(parents=True, exist_ok=True)

    direct_url = env(spec.get("direct_url_env"))
    endpoint = env(spec.get("endpoint_env")) or spec.get("default_endpoint")
    service_key = env(spec.get("key_env"))

    if direct_url:
        download_file(direct_url, output)
        return output

    if spec.get("kind") == "vworld_data_api":
        if not service_key:
            raise RuntimeError(
                f"{name}: {spec['key_env']} 환경변수가 없습니다. VWorld 인증키를 설정하세요."
            )
        payload = fetch_vworld_geojson(spec, endpoint, service_key)
        output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return output

    if endpoint:
        if spec.get("key_env") and not service_key:
            raise RuntimeError(
                f"{name}: {spec['key_env']} 환경변수가 없습니다. 공공데이터포털 인증키를 설정하세요."
            )
        frame = fetch_dataset_openapi(spec, endpoint, service_key, rows=rows, max_pages=max_pages)
        frame.to_csv(output, index=False, encoding="utf-8-sig")
        return output

    raise RuntimeError(
        f"{name}: 다운로드 URL/엔드포인트가 설정되지 않았습니다. "
        f"{spec.get('endpoint_env') or spec.get('direct_url_env')} 환경변수를 설정하세요."
    )


def download_file(url: str, output: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with output.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)


def fetch_dataset_openapi(
    spec: dict[str, Any], endpoint: str, service_key: str | None, rows: int, max_pages: int
) -> pd.DataFrame:
    paths = spec.get("paths") or [""]
    frames = []
    for path in paths:
        url = endpoint.rstrip("/")
        if path:
            url = f"{url}/{str(path).strip('/')}"
        frame = fetch_paginated_openapi(
            url,
            service_key,
            rows=rows,
            max_pages=max_pages,
            page_param=spec.get("page_param", "pageNo"),
            rows_param=spec.get("rows_param", "numOfRows"),
            default_params=spec.get("default_params", {}),
        )
        if not frame.empty and path:
            frame.insert(0, "source_path", path)
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fetch_vworld_geojson(spec: dict[str, Any], endpoint: str, service_key: str) -> dict[str, Any]:
    params = dict(spec.get("default_params", {}))
    params["key"] = service_key
    domain = env(spec.get("domain_env"))
    if domain:
        params["domain"] = domain
    attr_filter = env(spec.get("attr_filter_env"))
    if attr_filter:
        params["attrFilter"] = attr_filter
    geom_filter = env(spec.get("geom_filter_env"))
    if geom_filter:
        params["geomFilter"] = geom_filter

    features: list[dict[str, Any]] = []
    page = 1
    total = None
    while True:
        params["page"] = page
        response = requests.get(
            endpoint,
            params=params,
            timeout=60,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        payload = response.json()
        body = payload.get("response", {})
        if body.get("status") == "ERROR":
            error = body.get("error", {})
            raise RuntimeError(
                f"VWorld API error code={error.get('code')}, text={error.get('text')}"
            )

        result = body.get("result", {})
        feature_collection = result.get("featureCollection", {})
        page_features = feature_collection.get("features", [])
        features.extend(page_features)

        if total is None:
            total = int(result.get("total", len(features)) or len(features))
        if len(features) >= total or not page_features:
            break
        page += 1

    return {
        "type": "FeatureCollection",
        "name": spec["title"],
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }


def fetch_paginated_openapi(
    endpoint: str,
    service_key: str | None,
    rows: int = 1000,
    max_pages: int = 20,
    page_param: str = "pageNo",
    rows_param: str = "numOfRows",
    default_params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    records: list[dict[str, str]] = []
    total_count: int | None = None

    for page in range(1, max_pages + 1):
        params = {
            page_param: page,
            rows_param: rows,
        }
        if default_params:
            params.update(default_params)
        if service_key:
            params["serviceKey"] = service_key

        response = requests.get(
            endpoint,
            params=params,
            timeout=60,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = "utf-8"
        page_records, page_total = parse_response(response)
        if page_total is not None:
            total_count = page_total
        if not page_records:
            break

        records.extend(page_records)
        if total_count is not None and len(records) >= total_count:
            break
        time.sleep(0.15)

    return pd.DataFrame(records)


def parse_response(response: requests.Response) -> tuple[list[dict[str, str]], int | None]:
    content_type = response.headers.get("content-type", "")
    text = response.text.strip()

    if "json" in content_type or text.startswith("{") or text.startswith("["):
        payload = response.json()
        return parse_json_payload(payload)

    return parse_xml_payload(text)


def parse_json_payload(payload: Any) -> tuple[list[dict[str, str]], int | None]:
    total_count = find_first_int(payload, {"totalCount", "total_count", "totCnt"})
    items = find_items(payload)
    return [flatten_json(item) for item in items], total_count


def parse_xml_payload(text: str) -> tuple[list[dict[str, str]], int | None]:
    root = ET.fromstring(text)
    result_code_node = root.find(".//resultCode")
    result_msg_node = root.find(".//resultMsg")
    if result_code_node is not None:
        result_code = clean_text(result_code_node.text)
        if result_code not in {"", "00", "0000", "0", "INFO-000"}:
            result_msg = clean_text(result_msg_node.text if result_msg_node is not None else "")
            raise RuntimeError(f"API error resultCode={result_code}, resultMsg={result_msg}")

    total_count = None
    total_node = root.find(".//totalCount")
    if total_node is not None and total_node.text and total_node.text.strip().isdigit():
        total_count = int(total_node.text.strip())

    item_nodes = root.findall(".//item")
    if not item_nodes:
        item_nodes = root.findall(".//items/*")

    records = []
    for item in item_nodes:
        record = {child.tag: clean_text(child.text) for child in list(item)}
        if record:
            records.append(record)
    return records, total_count


def find_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ["item", "items", "data", "records", "row", "rows"]:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = find_items(value)
            if nested:
                return nested

    for value in payload.values():
        nested = find_items(value)
        if nested:
            return nested
    return []


def find_first_int(payload: Any, keys: set[str]) -> int | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    pass
            nested = find_first_int(value, keys)
            if nested is not None:
                return nested
    if isinstance(payload, list):
        for value in payload:
            nested = find_first_int(value, keys)
            if nested is not None:
                return nested
    return None


def flatten_json(value: Any, prefix: str = "") -> dict[str, str]:
    if isinstance(value, dict):
        out: dict[str, str] = {}
        for key, nested in value.items():
            nested_key = f"{prefix}_{key}" if prefix else str(key)
            out.update(flatten_json(nested, nested_key))
        return out
    if isinstance(value, list):
        return {prefix: json.dumps(value, ensure_ascii=False)}
    return {prefix: clean_text(value)}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return urllib.parse.unquote(str(value)).strip()


def print_plan(config: dict[str, dict[str, Any]]) -> None:
    print("데이터 수집 설정 상태")
    for name, spec in config.items():
        endpoint_value = env(spec.get("endpoint_env"))
        direct_value = env(spec.get("direct_url_env"))
        default_endpoint = spec.get("default_endpoint")
        key_required = bool(spec.get("key_env"))
        key_ready = bool(env(spec.get("key_env")))
        has_endpoint = bool(endpoint_value or direct_value or default_endpoint)
        if has_endpoint and (not key_required or key_ready):
            status = "ready"
        elif has_endpoint and key_required:
            status = f"needs_key:{spec['key_env']}"
        else:
            status = "needs_url"
        print(f"- {name}: {status} -> {spec['output']}")
        if status == "needs_url":
            if spec.get("endpoint_env"):
                print(f"  set {spec['endpoint_env']} from {spec['source_page']}")
            if spec.get("direct_url_env"):
                print(f"  or set {spec['direct_url_env']}")
        elif status.startswith("needs_key"):
            print(f"  set {spec['key_env']}")
            if spec.get("domain_env"):
                print(f"  optionally set {spec['domain_env']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Culture Gap AI raw data.")
    parser.add_argument("--dataset", default="all", help="Dataset key or all")
    parser.add_argument("--plan", action="store_true", help="Show configured sources only")
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args()

    config = load_config()
    if args.plan:
        print_plan(config)
        return 0

    names = list(config) if args.dataset == "all" else [args.dataset]
    for name in names:
        if name not in config:
            raise SystemExit(f"unknown dataset: {name}")
        output = collect_dataset(name, config[name], rows=args.rows, max_pages=args.max_pages)
        print(f"saved {name}: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
