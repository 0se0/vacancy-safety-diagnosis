"""
link_candidates_to_energy.py

commercial_vacancy_screening.py가 뽑은 공실 후보(서울 25개구 전체, 33,135건)는
지번 기반이라 도로명코드가 없어 에너지 데이터와 못 붙었다. 이 스크립트는 전체
후보(오래된 건물 우선 - 이미 vacancy_candidates.csv가 사용승인일 순 정렬돼 있음)를
건축HUB getBrTitleInfo API로 개별 조회해서 새주소도로코드(naRoadCd)를 얻고,
energy_vacancy_indicator.py가 이미 만들어둔 에너지 사용량 로더로 조인한다.

★ 전체를 한 번에 돌리지 않는 이유: 건당 API 호출이 필요해서 전체를
  돌리면 여러 시간 걸리고, 공공데이터포털 API 일일 호출한도(실측: 약 1만 건/일에서
  호출한도 초과 에러 LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR 발생)를
  초과할 수 있음. 그래서 매 실행마다 "아직 해결 안 된" 후보만 골라 처리하고,
  "조회 자체가 실패(네트워크/HTTP 429·5xx/포털 호출한도 에러)"가 연속으로 일정
  횟수 이상 반복되면 쿼터 소진 또는 API 장애로 보고 즉시 멈춰서 남은 호출을 낭비하지
  않는다. get_building_title()이 "정상 응답이지만 해당 지번 없음"(-> 영구실패로 기록,
  실패 스트릭 리셋)과 "조회 실패"(-> API_FAILURE, 스트릭 누적)를 구분해 주므로,
  건축HUB에 없는 지번이 우연히 여러 건 연속돼도 쿼터로 오판하지 않는다.
★ 처리 도중 끊겨도 데이터가 안 날아가게:
  - 새주소코드 확보 성공 -> cvs/vacancy_candidates_enriched.csv에 매 건 즉시 append
  - "새주소 자체가 없음"으로 확인된 건(영구적 사실, 재시도 무의미)
    -> cvs/vacancy_candidates_unresolvable.csv에 매 건 즉시 append
  - 다음 실행 시 이 두 파일에 이미 있는 건은 건너뛰고, 나머지(=API 실패로 결론이
    안 난 건)만 자동으로 이어서 처리 -> 별도 구간 설정 없이 그냥 다시 실행하면 됨

돌리는 법:
  1. .env에 BUILDING_API_KEY 필요 (enrich_building_age.py와 동일 키)
  2. cvs/vacancy_candidates.csv, cvs2/전기에너지, cvs2/가스에너지 필요
  3. python link_candidates_to_energy.py 실행 (쿼터 남은 만큼 자동으로 처리)
  4. 결과: cvs/vacancy_candidates_enriched.csv, cvs/vacancy_candidates_unresolvable.csv
           (둘 다 누적) + cvs/vacancy_candidates_with_energy.csv (누적, 에너지 조인) +
           html/역산공실탐지기반_공실후보_에너지연결.html (누적 기준 재생성)
"""
import csv
import os
import time

from dotenv import load_dotenv

from enrich_building_age import (
    API_FAILURE,
    get_building_title,
    load_bjdong_table,
)
from energy_vacancy_indicator import load_energy_usage
from seoul_districts import SEOUL_GU_CODES, SEOUL_GU_NAME_TO_CODE

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CVS_DIR = os.path.join(BASE_DIR, "cvs")
HTML_DIR = os.path.join(BASE_DIR, "html")
ENRICHED_CSV = os.path.join(CVS_DIR, "vacancy_candidates_enriched.csv")
UNRESOLVABLE_CSV = os.path.join(CVS_DIR, "vacancy_candidates_unresolvable.csv")

SLEEP_BETWEEN_CALLS = 0.15
# 이 횟수만큼 "조회 자체 실패(API_FAILURE)"가 연속되면 쿼터 소진/API 장애로 보고 즉시 중단.
# (쿼터가 다 찬 뒤에는 어차피 나머지 전부 실패하므로 계속 돌리는 건 시간 낭비)
# ※ "정상 응답이지만 해당 지번 없음"은 이 카운트에 안 들어감 - 스트릭을 리셋한다.
CONSECUTIVE_FAIL_LIMIT = 15

ENRICHED_FIELDNAMES = ["gu", "dong", "bun", "ji", "addr", "bld_nm", "use", "area",
                        "floors", "approval_date", "na_road_cd", "na_bbno", "na_buno"]
CANDIDATE_KEY_FIELDS = ["gu", "dong", "bun", "ji"]


def _key(row: dict) -> tuple:
    return tuple(row[f] for f in CANDIDATE_KEY_FIELDS)


def load_candidates() -> list:
    path = os.path.join(CVS_DIR, "vacancy_candidates.csv")
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))  # 이미 사용승인일(오래된 순)로 정렬돼 저장돼 있음


def load_resolved_keys() -> set:
    """이미 결론(성공 또는 영구실패)이 난 후보 키 집합 - 이번 실행에서 건너뛸 대상."""
    resolved = set()
    for path in (ENRICHED_CSV, UNRESOLVABLE_CSV):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                resolved.add(_key(row))
    return resolved


def enrich_with_road_code(candidates: list, bjdong_table: dict) -> list:
    """
    아직 안 풀린 후보만 처리. 성공/영구실패는 매 건 즉시 파일에 append(중단내성).
    "조회 자체 실패(API_FAILURE)"가 CONSECUTIVE_FAIL_LIMIT회 연속되면 쿼터 소진/장애로
    보고 즉시 중단. "정상 응답이지만 지번 없음"은 영구실패로 기록하고 스트릭을 리셋한다.
    """
    enriched = []
    no_bjdong, no_naroad, no_building, api_fail = 0, 0, 0, 0
    consecutive_fail = 0
    quota_hit = False

    enr_exists = os.path.exists(ENRICHED_CSV)
    unres_exists = os.path.exists(UNRESOLVABLE_CSV)
    enr_f = open(ENRICHED_CSV, "a", encoding="utf-8-sig", newline="")
    unres_f = open(UNRESOLVABLE_CSV, "a", encoding="utf-8-sig", newline="")
    enr_writer = csv.DictWriter(enr_f, fieldnames=ENRICHED_FIELDNAMES)
    unres_writer = csv.DictWriter(unres_f, fieldnames=CANDIDATE_KEY_FIELDS)
    if not enr_exists:
        enr_writer.writeheader()
    if not unres_exists:
        unres_writer.writeheader()

    try:
        for i, c in enumerate(candidates, 1):
            gu = c["gu"]
            dong = c["dong"]
            sigungu_cd = SEOUL_GU_NAME_TO_CODE.get(gu)
            bjdong_cd = bjdong_table.get((gu, dong))
            if not sigungu_cd or not bjdong_cd:
                no_bjdong += 1
                unres_writer.writerow({f: c[f] for f in CANDIDATE_KEY_FIELDS})
                unres_f.flush()
                continue

            bun = str(c["bun"]).zfill(4)
            ji = str(c["ji"]).zfill(4)
            title = get_building_title(sigungu_cd, bjdong_cd, bun, ji)
            time.sleep(SLEEP_BETWEEN_CALLS)

            if title is API_FAILURE:
                # 조회 자체가 실패(네트워크/429/5xx/포털 호출한도). 재시도 대상 - 파일에 안 남김.
                api_fail += 1
                consecutive_fail += 1
                if consecutive_fail >= CONSECUTIVE_FAIL_LIMIT:
                    quota_hit = True
                    print(f"  ⚠️ 조회 실패가 {CONSECUTIVE_FAIL_LIMIT}회 연속 -> "
                          f"일일 쿼터 소진 또는 API 장애로 판단, [{i}/{len(candidates)}]에서 중단합니다.")
                    break
                continue
            # 정상 응답을 받았으면(건물이 있든 없든) 실패 스트릭 리셋
            consecutive_fail = 0

            if title is None:
                # 정상 응답이지만 건축HUB에 해당 지번의 건물이 없음 -> 영구, 재시도 무의미
                no_building += 1
                unres_writer.writerow({f: c[f] for f in CANDIDATE_KEY_FIELDS})
                unres_f.flush()
                continue

            na_road_cd = (title.get("naRoadCd") or "").strip()
            na_main_bun = (title.get("naMainBun") or "").strip()
            na_sub_bun = (title.get("naSubBun") or "").strip()
            valid = na_road_cd and na_main_bun
            key = None
            if valid:
                try:
                    key = (na_road_cd, int(na_main_bun), int(na_sub_bun) if na_sub_bun else 0)
                except ValueError:
                    valid = False

            if not valid:
                no_naroad += 1
                unres_writer.writerow({f: c[f] for f in CANDIDATE_KEY_FIELDS})
                unres_f.flush()
                continue

            c2 = dict(c)
            c2["na_road_cd"], c2["na_bbno"], c2["na_buno"] = key
            enriched.append(c2)
            enr_writer.writerow({fn: c2.get(fn, "") for fn in ENRICHED_FIELDNAMES})
            enr_f.flush()

            if i % 200 == 0:
                print(f"  [{i}/{len(candidates)}] 처리 중... (새주소 확보 {len(enriched)}건, "
                      f"동코드매핑실패 {no_bjdong}, 미등록지번 {no_building}, 새주소없음 {no_naroad}, "
                      f"조회실패 {api_fail})")
    finally:
        enr_f.close()
        unres_f.close()

    print(f"\n이번 실행 새주소코드 확보: {len(enriched)}/{len(candidates)}건")
    print(f"  - 동코드 매핑 실패(영구): {no_bjdong}건")
    print(f"  - 건축HUB 미등록 지번(영구): {no_building}건")
    print(f"  - 새주소코드 없음(영구): {no_naroad}건")
    print(f"  - 조회 실패(재시도 대상): {api_fail}건{' - 쿼터 소진/장애로 조기 중단됨' if quota_hit else ''}")
    return enriched


def load_all_enriched() -> list:
    """
    이전 실행분까지 포함해 ENRICHED_CSV 전체를 누적 로드.
    실행이 중간에 끊겼다가 재시작되면 중복 행이 생길 수 있어
    (지번,동,번,지) 키 기준으로 중복 제거(나중 값 유지).
    """
    if not os.path.exists(ENRICHED_CSV):
        return []
    with open(ENRICHED_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["na_bbno"] = int(r["na_bbno"])
        r["na_buno"] = int(r["na_buno"])
    dedup = {(r["gu"], r["dong"], r["bun"], r["ji"]): r for r in rows}
    return list(dedup.values())


def join_energy(enriched: list, usage: dict) -> list:
    matched = []
    for c in enriched:
        key = (c["na_road_cd"], c["na_bbno"], c["na_buno"])
        u = usage.get(key)
        if u is None:
            continue
        elec_months = u["elec"]
        gas_months = u["gas"]
        if not elec_months and not gas_months:
            continue
        c2 = dict(c)
        c2["elec_avg"] = round(sum(elec_months.values()) / len(elec_months), 1) if elec_months else None
        c2["gas_avg"] = round(sum(gas_months.values()) / len(gas_months), 1) if gas_months else None
        c2["elec_months"] = len(elec_months)
        matched.append(c2)
    return matched


def generate(matched: list, n_candidates_tried: int, n_with_road_code: int) -> str:
    n = len(matched)
    rows_html = ""
    for m in matched[:200]:
        elec_str = f"{m['elec_avg']:,.0f} kWh" if m.get("elec_avg") is not None else "-"
        gas_str = f"{m['gas_avg']:,.0f} ㎥" if m.get("gas_avg") is not None else "-"
        rows_html += f"""<tr>
            <td>{m['gu']}</td>
            <td>{m['addr']}</td>
            <td>{m['use']}</td>
            <td>{m['approval_date'] or '미상'}</td>
            <td>{elec_str}</td>
            <td>{gas_str}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 공실 후보 에너지 연결 (전체 {n_candidates_tried:,}건 중 진행)</title>
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
  .chart-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; }}
  .chart-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: #898781; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e8e7e2; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #f1f0eb; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 공실 후보 에너지 연결 (전체 {n_candidates_tried:,}건 중 진행)</h1>
<div class="subtitle">서울 25개구 공실 후보 {n_candidates_tried:,}건 전체를 사용승인일 오래된 순으로 순차 조회 중 (일일 API 쿼터 제한으로 여러 회차에 걸쳐 진행)</div>

<div class="caveat">
📍 공실 후보는 지번 기반이라 도로명코드가 없어, 건축HUB API(getBrTitleInfo)로 개별
조회해 새주소도로코드를 확보한 뒤 전기/가스 에너지 사용량과 조인했다. API 일일 호출한도 제약으로 전체
{n_candidates_tried:,}건을 한 번에 끝내지 못하고 쿼터가 풀릴 때마다 이어서 처리 중이며, 일부 건물은 새주소 자체가
등록돼 있지 않아 매칭이 원천적으로 불가능하다.
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">공실 후보 전체</div>
    <div class="kpi-value gray">{n_candidates_tried:,}건</div>
    <div class="kpi-sub">서울 25개구 전수조사 기준</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">새주소코드 확보</div>
    <div class="kpi-value gray">{n_with_road_code:,}건</div>
    <div class="kpi-sub">{round(n_with_road_code/n_candidates_tried*100,1) if n_candidates_tried else 0}%</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">에너지 사용량 확인</div>
    <div class="kpi-value red">{n:,}건</div>
    <div class="kpi-sub">공실 후보인데 에너지 사용 흔적 있음</div>
  </div>
</div>

<div class="chart-box">
  <div class="chart-title">공실 후보 + 에너지 사용량 (상위 {min(200, n)}건)</div>
  <table>
    <thead><tr><th>구</th><th>지번주소</th><th>주용도</th><th>사용승인일</th><th>월평균 전력사용량</th><th>월평균 가스사용량</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>

<div class="note">
※ "에너지 사용량 확인"된 건물은 상가정보 API엔 안 잡혔지만 전기/가스는 쓰고 있는 곳이다 — 완전공실이 아니라
비신고 영업, 개인 창고 활용, 최근 개업(API 미반영 시차) 등일 수 있다. 반대로 여기 없는 건물(새주소코드는
확보했지만 에너지 데이터에도 안 잡히는 곳)이 오히려 완전공실에 더 가까운 후보다.<br>
전체 목록은 cvs/vacancy_candidates_with_energy.csv에 저장.
</div>

</body>
</html>"""


if __name__ == "__main__":
    all_candidates = load_candidates()
    resolved = load_resolved_keys()
    todo = [c for c in all_candidates if _key(c) not in resolved]
    print(f"=== 1단계: 미해결 공실 후보 로드 (전체 {len(all_candidates)}건 중 "
          f"이미 해결된 {len(resolved)}건 제외 -> {len(todo)}건 남음) ===\n")

    print("=== 2단계: 법정동코드 테이블 로드 ===")
    bjdong_table = load_bjdong_table()

    print(f"\n=== 3단계: 건축HUB API 개별 조회 (새주소도로코드 확보, 성공/영구실패 시마다 즉시 저장) ===")
    enrich_with_road_code(todo, bjdong_table)  # ENRICHED_CSV / UNRESOLVABLE_CSV에 append됨

    print("\n=== 4단계: 누적 결과 로드 + 에너지 사용량 조인 (이전 실행분 포함) ===")
    all_enriched = load_all_enriched()
    total_tried = len(all_candidates)
    print(f"누적 새주소코드 확보: {len(all_enriched)}건 (전체 후보 {total_tried}건 중)")

    usage = load_energy_usage(signgu_codes=SEOUL_GU_CODES.keys())
    matched = join_energy(all_enriched, usage)
    print(f"\n누적 공실 후보 중 에너지 사용 흔적 있는 건물: {len(matched)}/{len(all_enriched)}건")

    out_csv = os.path.join(CVS_DIR, "vacancy_candidates_with_energy.csv")
    if all_enriched:
        fieldnames = ENRICHED_FIELDNAMES + ["elec_avg", "gas_avg", "elec_months"]
        matched_by_key = {(m["gu"], m["dong"], m["bun"], m["ji"]): m for m in matched}
        with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for c in all_enriched:
                k = (c["gu"], c["dong"], c["bun"], c["ji"])
                row = matched_by_key.get(k, c)
                writer.writerow({fn: row.get(fn, "") for fn in fieldnames})
    print(f"저장(누적): {out_csv}")

    html = generate(matched, total_tried, len(all_enriched))
    output_path = os.path.join(HTML_DIR, "역산공실탐지기반_공실후보_에너지연결.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 생성 완료(누적 기준): {output_path}")
