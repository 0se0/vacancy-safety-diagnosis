"""
commercial_vacancy_screening.py

서울 25개구 전체 규모로 "건축물대장(상업용도) - 상가정보(실제영업중)" 차집합을 구해서
공실 후보 주소를 스크리닝한다. verification_scan.py가 303건 표본으로 했던
"등록 전유부수 vs 실제 영업중수" 비교를, 상업용 건물 규모로 확장한 버전.

★ 2026-09-01에는 8개구(강남·마포·광진·종로·중구·영등포·성동·강북)만 있었음
  (건축물대장 벌크 데이터가 8개구치만 있었어서). 2026-09-02에 나머지 17개구
  건축물대장(cvs2/건축물대장_표제부_17개구_전체.csv)을 추가로 받아 25개구
  전체로 확장. 건물대장은 파일 2개(8개구/17개구)를 합쳐서 쓰고, 상가정보 API
  스캔은 seoul_districts.py의 25개구 전체로 돈다.

건축HUB "원하는대로 건축데이터"에서 받은 벌크 표제부는 지번(시군구/법정동/번/지)
기반이라 도로명코드가 없다 -> energy_vacancy_indicator.py가 쓰는 에너지 데이터와는
바로 못 붙는다(에너지 데이터는 도로명코드만 있음). 그래서 이 스크립트의 결과물은
"공실 후보 주소 리스트"까지이며, 에너지 사용량 연결은 이 후보 중 일부를 건축HUB
API로 개별 조회해 새주소 코드를 붙이는 후속 작업으로 남긴다(link_candidates_to_energy.py).

주의: 상가정보 API는 "현재 영업 중인 사업체"만 반환한다. 건축물대장에는 공동/단독
주택 등 애초에 상가가 아닌 건물도 다수 포함돼 있어서, 필터링 없이 그냥 차집합을
구하면 일반 주택이 전부 "공실"로 오탐된다. 그래서 건축물대장을 주용도 기준으로
근린생활시설(1종/2종)·판매시설만 남긴 뒤 차집합을 구한다.

돌리는 법:
  1. .env에 SANGGA_API_KEY 필요 (verification_scan.py와 동일 키)
  2. cvs2/건축물대장_표제부_8개구_전체.csv, cvs2/건축물대장_표제부_17개구_전체.csv
     둘 다 필요 (건축HUB "원하는대로 건축데이터"에서 지역 선택, 건축물대장/표제부,
     CSV로 다운받아 이 이름으로 저장 - 한 번에 다 안 받아지면 나눠 받아도 됨)
  3. python commercial_vacancy_screening.py 실행
     (25개구 상가 전체 스캔이라 몇 분~10분 넘게 걸릴 수 있음)
  4. 결과: cvs/vacancy_candidates.csv (전체 후보) +
           html/역산공실탐지기반_공실후보스크리닝.html
"""
import csv
import os
import time
from collections import defaultdict

import pandas as pd
import requests
from dotenv import load_dotenv

from seoul_districts import SEOUL_GU_CODES

load_dotenv()

SERVICE_KEY_SANGGA = os.environ.get("SANGGA_API_KEY", "")
SANGGA_BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CVS_DIR = os.path.join(BASE_DIR, "cvs")
CVS2_DIR = os.path.join(BASE_DIR, "cvs2")
HTML_DIR = os.path.join(BASE_DIR, "html")
LEDGER_PATHS = [
    os.path.join(CVS2_DIR, "건축물대장_표제부_8개구_전체.csv"),
    os.path.join(CVS2_DIR, "건축물대장_표제부_17개구_전체.csv"),
]

# 서울 25개구 전체 (seoul_districts.py) - 2026-09-01엔 이 중 8개구만 스캔했었음
SCAN_SIGUNGU_CODES = SEOUL_GU_CODES
NUM_ROWS_PER_PAGE = 1000
REQUEST_TIMEOUT = 20
MAX_RETRY = 2

# "상가"로 볼 상업용도 (일반 주택류 제외 - 안 걸러내면 단독/공동주택이 전부 공실 오탐됨)
COMMERCIAL_USES = {"제1종근린생활시설", "제2종근린생활시설", "근린생활시설", "판매시설"}


def safe_get(url, params):
    for attempt in range(MAX_RETRY + 1):
        try:
            return requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException:
            if attempt < MAX_RETRY:
                time.sleep(1)
                continue
            return None


def scan_all_stores(signgu_cd: str) -> list:
    """구 전체 상가업소를 totalCount까지 빠짐없이 페이지네이션 스캔."""
    url = f"{SANGGA_BASE}/storeListInDong"
    items = []
    page = 1
    total_count = None
    while True:
        params = {"serviceKey": SERVICE_KEY_SANGGA, "divId": "signguCd", "key": signgu_cd,
                   "numOfRows": NUM_ROWS_PER_PAGE, "pageNo": page, "type": "json"}
        resp = safe_get(url, params)
        if resp is None:
            break
        try:
            body = resp.json().get("body", {})
        except Exception:
            break
        if total_count is None:
            total_count = body.get("totalCount", 0)
        page_items = body.get("items", [])
        if not page_items:
            break
        items.extend(page_items)
        if len(items) >= total_count or len(page_items) < NUM_ROWS_PER_PAGE:
            break
        page += 1
        time.sleep(0.2)
    return items


def collect_active_jibun_set() -> dict:
    """
    SCAN_SIGUNGU_CODES 전체 상가를 무제한 스캔해서 (구명,동명,번,지) 지번 키 -> 실제영업중 점포수로 집계.
    """
    active = defaultdict(int)
    for signgu_cd, gu_name in SCAN_SIGUNGU_CODES.items():
        print(f"  {gu_name}({signgu_cd}) 전체 스캔 중...")
        stores = scan_all_stores(signgu_cd)
        print(f"    -> {len(stores):,}건 조회")
        for s in stores:
            gu = s.get("signguNm")
            dong = s.get("ldongNm")
            mnno = s.get("lnoMnno")
            slno = s.get("lnoSlno")
            if not gu or not dong or mnno in (None, ""):
                continue
            try:
                bun = int(mnno)
                ji = int(slno) if slno not in (None, "") else 0
            except (TypeError, ValueError):
                continue
            key = (gu, dong, bun, ji)
            active[key] += 1
    return dict(active)


def load_commercial_ledger() -> pd.DataFrame:
    """건축물대장 벌크(8개구+17개구, 있는 파일만) 로드해 상업용도만 남긴다."""
    usecols = ["시군구", "법정동", "번", "지", "건물명", "주용도", "연면적(㎡)",
               "지상층수", "사용승인일"]
    frames = []
    for path in LEDGER_PATHS:
        if not os.path.exists(path):
            print(f"  ⚠️ {path} 없음, 스킵")
            continue
        frames.append(pd.read_csv(path, encoding="utf-8-sig", dtype=str, usecols=usecols))
    if not frames:
        raise FileNotFoundError(f"건축물대장 벌크 파일이 하나도 없습니다: {LEDGER_PATHS}")
    df = pd.concat(frames, ignore_index=True)
    df = df[df["주용도"].isin(COMMERCIAL_USES)].copy()
    df["번"] = pd.to_numeric(df["번"], errors="coerce")
    df["지"] = pd.to_numeric(df["지"], errors="coerce").fillna(0)
    df = df.dropna(subset=["번"])
    df["번"] = df["번"].astype(int)
    df["지"] = df["지"].astype(int)
    # 사용승인일이 빈 값일 때 ""가 아니라 공백으로 채워져 오는 행들이 있어 strip 후 처리.
    # "11111111" 같은 더미값·연도만 있는 축약값도 섞여 있어 YYYYMMDD(19xx/20xx) 형식만
    # 유효한 날짜로 인정하고 나머지는 전부 "미상"(NaN)으로 처리 -> 정렬 시 맨 뒤로 감
    df["사용승인일"] = df["사용승인일"].str.strip()
    valid_date = df["사용승인일"].str.match(r"^(19|20)\d{6}$", na=False)
    df.loc[~valid_date, "사용승인일"] = pd.NA
    # 같은 지번에 동(棟)별로 여러 행이 있을 수 있어 지번 단위로 대표 1건만 남김
    # (사용승인일이 있는 행을 우선하고, 그중 가장 오래된 것을 대표로)
    df = df.sort_values("사용승인일", na_position="last")
    df = df.drop_duplicates(subset=["시군구", "법정동", "번", "지"], keep="first")
    return df


def find_vacancy_candidates(ledger: pd.DataFrame, active: dict) -> list:
    candidates = []
    for row in ledger.itertuples(index=False):
        key = (row.시군구, row.법정동, row.번, row.지)
        if key in active:
            continue  # 상가정보 API에서 실제 영업중 사업체가 발견됨 -> 공실 아님
        candidates.append({
            "gu": row.시군구, "dong": row.법정동, "bun": row.번, "ji": row.지,
            "addr": f"{row.시군구} {row.법정동} {row.번}" + (f"-{row.지}" if row.지 else ""),
            "bld_nm": row.건물명 if pd.notna(row.건물명) else "",
            "use": row.주용도,
            "area": row._5 if pd.notna(row._5) else "",  # 연면적(㎡) - 괄호 있는 컬럼명이라 itertuples가 위치명(_5)으로 리네임함 (index=False라 0부터 시작)
            "floors": row.지상층수 if pd.notna(row.지상층수) else "",
            "approval_date": row.사용승인일 if pd.notna(row.사용승인일) else "",
        })
    # 오래된 건물(사용승인일 빠른 순) 우선 - 이 프로젝트의 "노후상가" 초점과 일치
    candidates.sort(key=lambda c: (c["approval_date"] or "99999999"))
    return candidates


def generate(candidates: list, ledger_total: int, active_total: int) -> str:
    n = len(candidates)
    gu_counts = defaultdict(int)
    for c in candidates:
        gu_counts[c["gu"]] += 1
    gu_rows = "".join(
        f"<tr><td>{gu}</td><td>{cnt:,}</td></tr>"
        for gu, cnt in sorted(gu_counts.items(), key=lambda x: -x[1])
    )

    rows_html = ""
    for c in candidates[:300]:
        rows_html += f"""<tr>
            <td>{c['gu']}</td>
            <td>{c['addr']}</td>
            <td>{c['bld_nm']}</td>
            <td>{c['use']}</td>
            <td>{c['area'] or '-'}</td>
            <td>{c['floors'] or '-'}</td>
            <td>{c['approval_date'] or '미상'}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 공실 후보 스크리닝 (서울 25개구 상업용도 전수조사)</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .caveat {{ background: #fff7ed; border-left: 3px solid #f59e0b; padding: 0.875rem 1.1rem; font-size: 12px; color: #52514e; margin-bottom: 1.5rem; line-height: 1.7; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 1.5rem; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 1rem; text-align: center; }}
  .kpi-label {{ font-size: 12px; color: #898781; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 24px; font-weight: 500; }}
  .kpi-sub {{ font-size: 11px; color: #898781; margin-top: 4px; }}
  .red {{ color: #e34948; }} .gray {{ color: #52514e; }}
  .chart-grid {{ display: grid; grid-template-columns: 1fr 2fr; gap: 20px; margin-bottom: 1.5rem; }}
  .chart-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; }}
  .chart-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: #898781; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e8e7e2; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #f1f0eb; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 공실 후보 스크리닝 (서울 25개구 상업용도 전수조사)</h1>
<div class="subtitle">건축물대장(근린생활시설·판매시설) {ledger_total:,}건 vs 상가정보 API 실제영업중 {active_total:,}건 차집합</div>

<div class="caveat">
📍 <b>이 지표의 배경:</b> 건축물대장에서 주용도가 근린생활시설(1종/2종)·판매시설인 상업용 건물만 걸러낸 뒤,
같은 지번(시군구·법정동·번·지)에 상가정보 API 실측 결과 영업 중인 사업체가 하나도 없는 건물을 공실 후보로 추출했다.<br>
verification_scan.py가 303건 표본으로 했던 "등록 vs 실제" 비교를 서울 25개구 상업용 건물 전체({ledger_total:,}건) 규모로 확장한 버전이다.<br>
⚠️ 상가정보 API에 누락된 최근 개업 업체, 지번-법정동명 표기 차이로 인한 미스매치 등으로 인한 오탐이 섞여 있을 수 있어
"확정 공실"이 아니라 "현장 확인이 필요한 후보"로 해석해야 한다.
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">상업용 건물 (서울 25개구 전체)</div>
    <div class="kpi-value gray">{ledger_total:,}</div>
    <div class="kpi-sub">근린생활시설·판매시설</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">실제 영업중 지번(상가정보 API)</div>
    <div class="kpi-value gray">{active_total:,}</div>
    <div class="kpi-sub">25개구 전수 스캔</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">공실 후보</div>
    <div class="kpi-value red">{n:,}</div>
    <div class="kpi-sub">전체의 {round(n/ledger_total*100,1) if ledger_total else 0}%</div>
  </div>
</div>

<div class="chart-grid">
  <div class="chart-box">
    <div class="chart-title">구별 공실 후보 수</div>
    <table><thead><tr><th>구</th><th>후보수</th></tr></thead><tbody>{gu_rows}</tbody></table>
  </div>
  <div class="chart-box">
    <div class="chart-title">공실 후보 상세 (사용승인일 오래된 순, 상위 {min(300, n)}건)</div>
    <table>
      <thead><tr><th>구</th><th>지번주소</th><th>건물명</th><th>주용도</th><th>연면적(㎡)</th><th>지상층수</th><th>사용승인일</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>

<div class="note">
※ 방법론: 건축HUB "원하는대로 건축데이터"로 서울 25개구 건축물대장 표제부 전체를
다운로드해 주용도가 제1·2종근린생활시설·판매시설인 {ledger_total:,}건만 남김. 같은 25개구를 소상공인 상가정보 API(storeListInDong)로
누락 없이 전수 스캔({active_total:,}건 지번)해, 상업용 건물 중 실제 영업중 사업체가 하나도 매칭되지 않는 지번을 공실 후보로 추출.<br>
전체 후보 목록은 cvs/vacancy_candidates.csv에 저장. 도로명코드가 없는 지번 기반 데이터라 전기/가스 에너지 사용량과는 아직 연결되지
않았으며, 상위 후보를 건축HUB API로 개별 조회해 새주소 코드를 붙이는 것이 다음 단계다.
</div>

</body>
</html>"""


if __name__ == "__main__":
    print("=== 1단계: 상가정보 API 서울 25개구 전체 스캔 (누락 없이) ===")
    active = collect_active_jibun_set()
    print(f"\n실제 영업중 지번 {len(active):,}건 식별 완료\n")

    print("=== 2단계: 건축물대장 로드 및 상업용도 필터링 ===")
    ledger = load_commercial_ledger()
    print(f"상업용 건물(근린생활시설·판매시설) {len(ledger):,}건\n")

    print("=== 3단계: 차집합 계산 (공실 후보 추출) ===")
    candidates = find_vacancy_candidates(ledger, active)
    print(f"공실 후보: {len(candidates):,}건 (상업용 건물의 {round(len(candidates)/len(ledger)*100,1)}%)")

    out_csv = os.path.join(CVS_DIR, "vacancy_candidates.csv")
    if candidates:
        with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(candidates[0].keys()))
            writer.writeheader()
            writer.writerows(candidates)
    print(f"전체 후보 저장: {out_csv}")

    html = generate(candidates, len(ledger), len(active))
    output_path = os.path.join(HTML_DIR, "역산공실탐지기반_공실후보스크리닝.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 생성 완료: {output_path}")
