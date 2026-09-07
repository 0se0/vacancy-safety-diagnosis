"""
geocode_missing_markets.py

alt_vacancy_indicator.py의 TARGET_MARKETS를 48개 -> 277개로 확장(2026-09-07)한
뒤, safety_map.py의 MARKET_COORDS는 여전히 원래 48개만 수작업으로 좌표가 찍혀
있어서 나머지 229곳이 지도에 안 나오는 상태였다. 이 스크립트는 나머지를
OpenStreetMap Nominatim(무료, API 키 불필요)으로 지오코딩해서 채운다.

★ 왜 SANGGA_API_KEY(상가업소정보)로 안 하나: 그 API는 storeListInDong처럼
  시군구코드(구)로 먼저 좁혀야 검색이 되는데, TARGET_MARKETS 리스트 자체엔
  어느 구인지 정보가 전혀 없다(상권분석서비스 CSV엔 상권명과 점포수만 있음).
  25개구를 다 훑어서 상권명이 매장명에 들어간 걸 찾는 건 API 호출량이 너무
  커진다. Nominatim은 상권명을 주소 텍스트로 바로 검색할 수 있어 이 문제를
  피한다. 다만 정밀도는 낮다 - 시장의 정확한 대표지점이 아니라 "이 이름으로
  OSM에 등록된 가장 근접한 지점"이며, MARKET_COORDS 원본 48개(수작업 근사치)와
  동일하게 "근사 좌표"라는 성격은 같다.

★ 실패 처리: 검색 결과가 없거나 서울 바깥이면 미확보로 남긴다(지어내지 않음).
  이름에 괄호로 별칭이 붙어 있거나("OO시장(OO상점가)") "역 1번" 같은 출입구
  표기가 붙어 있으면 원 검색이 실패하기 쉬워서, 괄호 앞부분 -> "역 N번" 접미사
  제거 순으로 재시도한다.

★ Nominatim 이용정책(1req/sec, User-Agent 명시) 준수 - 매 요청 사이 1.1초 대기.

돌리는 법:
  python geocode_missing_markets.py
  결과: cvs/market_coords_geocoded.csv (누적, 중단돼도 이어서 실행 가능)
"""
import csv
import os
import re
import time

import requests

from alt_vacancy_indicator import TARGET_MARKETS
from safety_map import MARKET_COORDS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CVS_DIR = os.path.join(BASE_DIR, "cvs")
OUT_CSV = os.path.join(CVS_DIR, "market_coords_geocoded.csv")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "vacancy-safety-diagnosis-research/1.0 (portfolio project, personal use)"}
SLEEP_BETWEEN_CALLS = 1.1  # Nominatim 정책: 1req/sec 이하
FIELDNAMES = ["market", "lat", "lon", "district", "matched_query"]


def _query_variants(name: str) -> list:
    """원본 -> 괄호 앞부분만 -> '역 N번' 접미사 제거, 순서대로 시도할 검색어 목록."""
    variants = [name]
    base = re.split(r"[（(]", name)[0].strip()
    if base and base not in variants:
        variants.append(base)
    no_exit = re.sub(r"역\s*\d+번$", "역", base).strip()
    if no_exit and no_exit not in variants:
        variants.append(no_exit)
    no_station = re.sub(r"역$", "", no_exit).strip()
    if no_station and no_station not in variants:
        variants.append(no_station)
    return variants


def geocode_one(name: str):
    """성공하면 (lat, lon, district, 사용된 검색어) 반환, 실패하면 None."""
    for query in _query_variants(name):
        params = {
            "q": f"서울 {query}", "format": "json", "limit": 1,
            "countrycodes": "kr", "addressdetails": 1,
        }
        try:
            resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=15)
        except requests.exceptions.RequestException:
            time.sleep(SLEEP_BETWEEN_CALLS)
            continue
        time.sleep(SLEEP_BETWEEN_CALLS)
        try:
            results = resp.json()
        except ValueError:
            continue
        if not results:
            continue
        item = results[0]
        addr = item.get("address", {})
        city = addr.get("city", "")
        if "서울" not in city:
            continue  # 서울 밖 동명이인 매칭은 버림
        district = addr.get("borough") or addr.get("city_district") or addr.get("county") or ""
        return float(item["lat"]), float(item["lon"]), district, query
    return None


def load_resolved() -> set:
    if not os.path.exists(OUT_CSV):
        return set()
    with open(OUT_CSV, encoding="utf-8-sig") as f:
        return {row["market"] for row in csv.DictReader(f)}


if __name__ == "__main__":
    missing = [m for m in TARGET_MARKETS if m not in MARKET_COORDS]
    resolved = load_resolved()
    todo = [m for m in missing if m not in resolved]
    print(f"좌표 없는 상권 {len(missing)}곳 중 이미 처리된 {len(resolved)}곳 제외 -> {len(todo)}곳 진행")

    exists = os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not exists:
            writer.writeheader()

        success, fail = 0, 0
        for i, name in enumerate(todo, 1):
            result = geocode_one(name)
            if result is None:
                fail += 1
                writer.writerow({"market": name, "lat": "", "lon": "", "district": "", "matched_query": ""})
            else:
                lat, lon, district, query = result
                success += 1
                writer.writerow({"market": name, "lat": lat, "lon": lon,
                                  "district": district, "matched_query": query})
            f.flush()
            if i % 20 == 0:
                print(f"  [{i}/{len(todo)}] 성공 {success} / 실패 {fail}")

    print(f"\n완료: 성공 {success}/{len(todo)}, 실패(미확보) {fail}/{len(todo)}")
    print(f"저장: {OUT_CSV}")
