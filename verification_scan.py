"""
실측 검증 스캔 - 진짜 건물 실측해서 근거자료 만드는 거

건축물대장 등록 전유부수 vs 상가정보 실제 영업중수가 얼마나 차이나는지
실제 건물들 돌면서 확인함. 결과는 CSV 로그로 다 남기고 HTML로 요약함

돌리는 법:
  1. .env에 SANGGA_API_KEY, BUILDING_API_KEY 넣기
  2. python verification_scan.py 실행 (여러 구 도니까 몇 분 걸릴 수 있음)
  3. 결과물:
     - cvs/verification_log.csv   (스캔한 건물 전체 원본 로그)
     - html/역산공실탐지기반_실측검증요약.html (요약 + 불일치 사례)
"""
import requests
import time
import csv
import json
import os
from dotenv import load_dotenv

from seoul_districts import SEOUL_GU_CODES

load_dotenv()

SERVICE_KEY_SANGGA = os.environ.get("SANGGA_API_KEY", "")
SERVICE_KEY_BUILDING = os.environ.get("BUILDING_API_KEY", "")

SANGGA_BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2"
BUILDING_BASE = "https://apis.data.go.kr/1613000/BldRgstHubService"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CVS_DIR = os.path.join(BASE_DIR, "cvs")
HTML_DIR = os.path.join(BASE_DIR, "html")

# 스캔할 구들 - 서울 25개구 전체(commercial_vacancy_screening.py와 동일 범위로 확장,
# 2026-09-01 최초 버전은 8개구 하드코딩이었음). 구당 40건씩 = 최대 1,000건.
SCAN_SIGUNGU_CODES = SEOUL_GU_CODES
NUM_ROWS_PER_REGION = 40
REQUEST_TIMEOUT = 20
MAX_RETRY = 2


def safe_get(url, params):
    for attempt in range(MAX_RETRY + 1):
        try:
            return requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException:
            if attempt < MAX_RETRY:
                time.sleep(1)
                continue
            return None


def fetch_stores(signgu_cd: str, num_rows: int) -> list:
    url = f"{SANGGA_BASE}/storeListInDong"
    params = {"serviceKey": SERVICE_KEY_SANGGA, "divId": "signguCd", "key": signgu_cd,
              "numOfRows": num_rows, "pageNo": 1, "type": "json"}
    resp = safe_get(url, params)
    if resp is None:
        return []
    try:
        return resp.json().get("body", {}).get("items", [])
    except Exception:
        return []


def store_list_in_building(bld_mng_no: str) -> list:
    url = f"{SANGGA_BASE}/storeListInBuilding"
    params = {"serviceKey": SERVICE_KEY_SANGGA, "key": bld_mng_no,
              "numOfRows": 500, "pageNo": 1, "type": "json"}
    resp = safe_get(url, params)
    if resp is None:
        return []
    try:
        return resp.json().get("body", {}).get("items", [])
    except Exception:
        return []


def get_building_title(sigungu_cd: str, bjdong_cd: str, bun: str, ji: str):
    url = f"{BUILDING_BASE}/getBrTitleInfo"
    params = {"serviceKey": SERVICE_KEY_BUILDING, "sigunguCd": sigungu_cd, "bjdongCd": bjdong_cd,
              "bun": bun, "ji": ji, "_type": "json"}
    resp = safe_get(url, params)
    if resp is None:
        return None
    try:
        items = resp.json().get("response", {}).get("body", {}).get("items", {})
        item = items.get("item") if items else None
        if isinstance(item, list):
            return item[0] if item else None
        return item
    except Exception:
        return None


def get_building_expos(sigungu_cd: str, bjdong_cd: str, bun: str, ji: str) -> list:
    url = f"{BUILDING_BASE}/getBrExposInfo"
    params = {"serviceKey": SERVICE_KEY_BUILDING, "sigunguCd": sigungu_cd, "bjdongCd": bjdong_cd,
              "bun": bun, "ji": ji, "numOfRows": 500, "_type": "json"}
    resp = safe_get(url, params)
    if resp is None:
        return []
    try:
        items = resp.json().get("response", {}).get("body", {}).get("items", {})
        item = items.get("item") if items else None
        if item is None:
            return []
        return item if isinstance(item, list) else [item]
    except Exception:
        return []


def run_scan():
    log_rows = []
    seen_jibun = set()

    for signgu_cd, signgu_name in SCAN_SIGUNGU_CODES.items():
        print(f"[{signgu_name}] 스캔 중...")
        stores = fetch_stores(signgu_cd, NUM_ROWS_PER_REGION)
        checked = 0

        for s in stores:
            ldong_cd = s.get("ldongCd", "")
            bun_raw = s.get("lnoMnno", "")
            if not ldong_cd or bun_raw in ("", None):
                continue
            sg, bj = ldong_cd[:5], ldong_cd[5:]
            bun = str(bun_raw).zfill(4)
            ji_raw = s.get("lnoSlno", "")
            ji = str(ji_raw).zfill(4) if ji_raw not in ("", None) else "0000"

            key = (sg, bj, bun, ji)
            if key in seen_jibun:
                continue
            seen_jibun.add(key)
            checked += 1

            title = get_building_title(sg, bj, bun, ji)
            time.sleep(0.15)
            if title is None:
                continue

            gb = title.get("regstrGbCdNm", "?")
            row = {
                "시군구": signgu_name, "상가명": s.get("bizesNm", ""),
                "지번주소": s.get("lnoAdr", ""), "건물명": title.get("bldNm", ""),
                "건물유형": gb, "등록전유부수": None, "실제영업중수": None, "비고": "",
            }

            if gb == "집합":
                bld_mng_no = s.get("bldMngNo")
                occupied = store_list_in_building(bld_mng_no)
                time.sleep(0.15)
                expos = get_building_expos(sg, bj, bun, ji)
                time.sleep(0.15)
                row["등록전유부수"] = len(expos)
                row["실제영업중수"] = len(occupied)
                if len(expos) < len(occupied):
                    row["비고"] = "불일치(등록<실제)"
            else:
                row["비고"] = "일반건축물(단일단위)"

            log_rows.append(row)
            print(f"  [{checked}] {row['상가명']} - {row['건물유형']} "
                  f"(등록:{row['등록전유부수']}, 실제:{row['실제영업중수']}) {row['비고']}")

    return log_rows


def save_csv(log_rows, path):
    if not log_rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(log_rows[0].keys()))
        writer.writeheader()
        writer.writerows(log_rows)


def generate_html(log_rows) -> str:
    total = len(log_rows)
    collective = [r for r in log_rows if r["건물유형"] == "집합"]
    mismatched = [r for r in collective if r["비고"] == "불일치(등록<실제)"]

    mismatched_sorted = sorted(mismatched, key=lambda r: (r["실제영업중수"] or 0) - (r["등록전유부수"] or 0), reverse=True)
    top20 = mismatched_sorted[:20]

    rows_html = ""
    for r in top20:
        gap = (r["실제영업중수"] or 0) - (r["등록전유부수"] or 0)
        rows_html += f"""<tr>
            <td>{r['시군구']}</td><td>{r['상가명']}</td><td>{r['건물명']}</td>
            <td>{r['등록전유부수']}</td><td>{r['실제영업중수']}</td>
            <td style="color:#e34948;font-weight:600;">+{gap}</td>
        </tr>"""

    table_all = ""
    for r in log_rows:
        table_all += f"""<tr>
            <td>{r['시군구']}</td><td>{r['상가명']}</td><td>{r['지번주소']}</td>
            <td>{r['건물유형']}</td><td>{r['등록전유부수'] if r['등록전유부수'] is not None else '-'}</td>
            <td>{r['실제영업중수'] if r['실제영업중수'] is not None else '-'}</td><td>{r['비고']}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 실측 검증 요약 ({total}개 건물)</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 1.5rem; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 1rem; text-align: center; }}
  .kpi-label {{ font-size: 12px; color: #898781; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 24px; font-weight: 600; }}
  .chart-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; margin-bottom: 1.5rem; }}
  .chart-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  th {{ text-align: left; color: #898781; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e8e7e2; position: sticky; top: 0; background: #fff; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #f1f0eb; }}
  .scroll-box {{ max-height: 500px; overflow-y: auto; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 실측 검증 요약</h1>
<div class="subtitle">소상공인 상가정보 API × 국토교통부 건축HUB API 실시간 연동 결과 (자동 스캔, 원본 로그: verification_log.csv)</div>

<div class="kpi-grid">
  <div class="kpi-card"><div class="kpi-label">스캔한 고유 건물(지번) 수</div><div class="kpi-value" style="color:#52514e;">{total}개</div></div>
  <div class="kpi-card"><div class="kpi-label">집합건축물 수</div><div class="kpi-value" style="color:#2a78d6;">{len(collective)}개</div></div>
  <div class="kpi-card"><div class="kpi-label">등록-실제 불일치 사례</div><div class="kpi-value" style="color:#e34948;">{len(mismatched)}개</div></div>
  <div class="kpi-card"><div class="kpi-label">불일치 비율(집합건물 중)</div><div class="kpi-value" style="color:#e34948;">{round(len(mismatched)/len(collective)*100, 1) if collective else 0}%</div></div>
</div>

<div class="chart-box">
  <div class="chart-title">불일치 격차 상위 20건 (실제영업중 - 등록전유부, 큰 순)</div>
  <table>
    <thead><tr><th>시군구</th><th>상가명(기준)</th><th>건물명</th><th>등록전유부</th><th>실제영업중</th><th>격차</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>

<div class="chart-box">
  <div class="chart-title">전체 스캔 로그 (표본 전체 — 실현가능성 증빙 원자료)</div>
  <div class="scroll-box">
    <table>
      <thead><tr><th>시군구</th><th>상가명</th><th>지번주소</th><th>건물유형</th><th>등록전유부</th><th>실제영업중</th><th>비고</th></tr></thead>
      <tbody>{table_all}</tbody>
    </table>
  </div>
</div>

<div class="note">
※ 방법론: 여러 시군구의 상가정보 API 목록에서 고유 지번(건물)을 추출해 건축물대장 표제부로 집합/일반 여부를
확인하고, 집합건축물인 경우 전유부(등록 호실)와 상가정보 건물단위조회(실제 영업중 사업체)를 대조했다.
"등록전유부 &lt; 실제영업중"인 경우를 불일치로 판정했다(등록 절차 없이 내부를 쪼개 임대하는 사례로 추정).
데이터: 소상공인시장진흥공단 상가(상권)정보 API, 국토교통부 건축HUB 건축물대장정보 API (실시간 조회).
</div>
</body>
</html>"""


if __name__ == "__main__":
    print("=" * 60)
    print(f"실측 검증 스캔 시작 (대상: {len(SCAN_SIGUNGU_CODES)}개 구, 구당 최대 {NUM_ROWS_PER_REGION}건)")
    print("=" * 60)
    log_rows = run_scan()

    print(f"\n총 {len(log_rows)}개 고유 건물 스캔 완료")

    csv_path = os.path.join(CVS_DIR, "verification_log.csv")
    save_csv(log_rows, csv_path)
    print(f"CSV 저장 완료: {csv_path}")

    html = generate_html(log_rows)
    html_path = os.path.join(HTML_DIR, "역산공실탐지기반_실측검증요약.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 생성 완료: {html_path}")