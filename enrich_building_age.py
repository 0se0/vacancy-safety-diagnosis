"""
enrich_building_age.py

verification_scan.py가 이미 만들어둔 verification_log.csv 중
"불일치(등록<실제)"로 판정된 건물들에 한해, 건축HUB 표제부 API에서
사용승인일(준공연도)만 추가로 조회해서 붙이는 보강 스크립트.

★ 기존 verification_scan.py는 전혀 건드리지 않음 — 그 파일이 만든
  등록전유부수·실제영업중수·92.2% 같은 숫자는 이 스크립트로 절대 안 바뀜.
★ 상가정보(실시간, 매번 바뀔 수 있는 API)는 여기서 아예 호출하지 않음.
  건축물대장 표제부(준공연도 = 이미 확정된 과거 사실)만 조회함.

필요파일:
  1. verification_scan.py가 이미 실행되어 cvs/verification_log.csv가 존재해야 함
  2. 법정동코드 전체자료 
     - 법정동코드 전체자료.txt (탭 구분) 또는 .csv
     - 컬럼: 법정동코드, 법정동명, 폐지여부  (예: "1168010100  서울특별시 강남구 역삼동  존재")
     - 이 스크립트 옆에 "법정동코드_전체자료.txt"로 저장해두면 자동으로 읽음
  3. .env에 BUILDING_API_KEY (verification_scan.py와 동일한 키 사용)

결과:
  cvs/verification_log_with_age.csv
    - 원본 71개 불일치 건물 + 사용승인일·건물연식 컬럼 추가
    - 원본 verification_log.csv는 그대로 보존, 별도 파일로 저장
"""
import csv
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

SERVICE_KEY_BUILDING = os.environ.get("BUILDING_API_KEY", "")
BUILDING_BASE = "https://apis.data.go.kr/1613000/BldRgstHubService"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CVS_DIR = os.path.join(BASE_DIR, "cvs")
BJDONG_CODE_FILE_CANDIDATES = [
    os.path.join(BASE_DIR, "국토교통부_전국_법정동_20260630.csv"),
    os.path.join(CVS_DIR, "국토교통부_전국_법정동_20260630.csv"),
    os.path.join(BASE_DIR, "법정동코드_전체자료.txt"),
    os.path.join(BASE_DIR, "법정동코드_전체자료.csv"),
    os.path.join(CVS_DIR, "법정동코드_전체자료.txt"),
    os.path.join(CVS_DIR, "법정동코드_전체자료.csv"),
]

REQUEST_TIMEOUT = 20
MAX_RETRY = 2

# verification_scan.py의 SCAN_SIGUNGU_CODES와 동일 (구 이름 -> 시군구코드 역매핑용)
SIGUNGU_NAME_TO_CODE = {
    "강남구": "11680", "마포구": "11440", "광진구": "11215", "종로구": "11110",
    "중구": "11140", "영등포구": "11560", "성동구": "11200", "강북구": "11305",
}


# get_building_title()가 "조회 자체가 실패"했을 때 돌려주는 sentinel.
#   - 네트워크 오류/타임아웃, HTTP 429·5xx, 공공데이터포털 호출한도 에러 응답
#     (LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR 등), 파싱 불가 응답
# "정상 응답인데 해당 지번이 건축HUB에 없음"(-> None)과 구분하기 위한 것.
# link_candidates_to_energy.py가 이 값만 세어서 "쿼터/장애로 조기 중단" 판단에 쓴다.
API_FAILURE = object()

# 포털이 정상 처리했다고 보는 resultCode (BldRgstHubService 기준 "00").
# 그 외 값(예: "22" = 트래픽 초과)은 조회 실패로 취급.
_OK_RESULT_CODES = {"00", "0", "NORMAL SERVICE.", "NORMAL_SERVICE"}


def safe_get(url, params):
    """HTTP 요청 1건. 네트워크 예외면 재시도 후 None, 응답을 받으면 상태코드 무관하게 그대로 반환."""
    for attempt in range(MAX_RETRY + 1):
        try:
            return requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException:
            if attempt < MAX_RETRY:
                time.sleep(1)
                continue
            return None


def get_building_title(sigungu_cd: str, bjdong_cd: str, bun: str, ji: str):
    """
    건축HUB 표제부(getBrTitleInfo) 조회. 반환값 3가지를 구분한다:
      - dict          : 조회 성공, 표제부 항목
      - None          : 정상 응답이지만 해당 지번의 건물이 없음 (영구 사실)
      - API_FAILURE   : 조회 자체 실패 (네트워크/429/5xx/포털 호출한도 에러/파싱불가)
    """
    url = f"{BUILDING_BASE}/getBrTitleInfo"
    params = {"serviceKey": SERVICE_KEY_BUILDING, "sigunguCd": sigungu_cd, "bjdongCd": bjdong_cd,
              "bun": bun, "ji": ji, "_type": "json"}
    resp = safe_get(url, params)
    if resp is None:
        return API_FAILURE  # 네트워크 오류/타임아웃 (재시도 후에도 실패)
    if resp.status_code == 429 or resp.status_code >= 500:
        return API_FAILURE  # 게이트웨이 호출한도 / 서버 오류

    try:
        payload = resp.json()
    except ValueError:
        # 쿼터 초과 시 포털이 JSON 요청에도 XML 에러(OpenAPI_ServiceResponse)를 주는 경우가 있음
        return API_FAILURE

    # 포털 공통 에러 엔벨로프 확인 (resultCode가 "00"이 아니면 데이터가 아니라 에러)
    result_code = str(
        payload.get("response", {}).get("header", {}).get("resultCode", "")
    ).strip()
    if result_code and result_code not in _OK_RESULT_CODES:
        return API_FAILURE

    try:
        items = payload.get("response", {}).get("body", {}).get("items", {})
        item = items.get("item") if items else None
        if isinstance(item, list):
            return item[0] if item else None
        return item  # dict(정상) 또는 None(해당 지번 없음)
    except Exception:
        return API_FAILURE


def load_bjdong_table():
    """
    국토교통부 '전국 법정동' CSV를 읽어 {(시군구명, 읍면동명): 법정동코드(뒤 5자리)}로 반환.
    파일 컬럼: 법정동코드, 시도명, 시군구명, 읍면동명, 리명, 순위, 생성일자
    예: '1120011400','서울특별시','성동구','성수동1가',...  -> {('성동구','성수동1가'): '11400'}
    """
    path = None
    for cand in BJDONG_CODE_FILE_CANDIDATES:
        if os.path.exists(cand):
            path = cand
            break
    if path is None:
        print("⚠️ 법정동코드 파일을 찾을 수 없습니다.")
        print(f"   다음 경로 중 하나에 저장해주세요: {BJDONG_CODE_FILE_CANDIDATES}")
        return {}

    table = {}
    for enc in ["utf-8-sig", "cp949"]:
        try:
            with open(path, encoding=enc) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = (row.get("법정동코드") or "").strip()
                    sido = (row.get("시도명") or "").strip()
                    gu = (row.get("시군구명") or "").strip()
                    dong = (row.get("읍면동명") or "").strip()
                    if sido != "서울특별시" or not gu or not dong:
                        continue
                    if len(code) != 10 or not code.isdigit():
                        continue
                    bjdong_cd = code[5:10]  # 뒤 5자리만 API bjdongCd로 사용
                    table[(gu, dong)] = bjdong_cd
            break
        except UnicodeDecodeError:
            continue
    print(f"✅ 법정동코드 {len(table)}건 로드 완료 ({path})")
    return table


def parse_jibun_address(addr: str):
    """
    '서울특별시 강남구 수서동 714' / '서울특별시 강남구 논현동 145-16' /
    '서울특별시 성동구 성수동1가 13-164' / '서울특별시 강남구 역삼동 산 12-3' 형태를 파싱.
    법정동코드 테이블에 '동N가'까지 통째로 들어있으므로, 정규식 대신
    "구/동/번지" 토큰을 단순 분리해서 처리 (지난 정규식은 '동N가'를 놓쳤음).
    반환: (구이름, 동이름, 번, 지) 또는 None
    """
    if not addr:
        return None
    tokens = addr.split()
    # tokens 예: ['서울특별시','강남구','수서동','714'] 또는 [...,'역삼동','산','12-3']
    gu_name = next((t for t in tokens if t.endswith("구")), None)
    if gu_name is None:
        return None
    gu_idx = tokens.index(gu_name)
    remaining = tokens[gu_idx + 1:]
    if not remaining:
        return None

    dong_name = remaining[0]  # '성수동1가', '을지로6가', '역삼동' 등 통째로 한 토큰
    rest = remaining[1:]
    if rest and rest[0] == "산":
        rest = rest[1:]
    if not rest:
        return None

    bunji = rest[0]
    if "-" in bunji:
        bun_raw, ji_raw = bunji.split("-", 1)
    else:
        bun_raw, ji_raw = bunji, "0"

    if not bun_raw.isdigit():
        return None
    bun = bun_raw.zfill(4)
    ji = (ji_raw if ji_raw.isdigit() else "0").zfill(4)
    return gu_name, dong_name, bun, ji


def main():
    log_path = os.path.join(CVS_DIR, "verification_log.csv")
    if not os.path.exists(log_path):
        print(f"❌ {log_path} 가 없습니다. verification_scan.py를 먼저 실행하세요.")
        return

    with open(log_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    mismatched = [r for r in rows if r.get("비고") == "불일치(등록<실제)"]
    print(f"불일치 건물 {len(mismatched)}건에 사용승인일 보강 조회를 시작합니다.\n")

    bjdong_table = load_bjdong_table()

    success, failed = 0, 0
    for i, r in enumerate(mismatched, 1):
        parsed = parse_jibun_address(r.get("지번주소", ""))
        if parsed is None:
            r["사용승인일"] = ""
            r["건물연식"] = ""
            failed += 1
            print(f"  [{i}/{len(mismatched)}] 주소 파싱 실패: {r.get('지번주소')}")
            continue

        gu_name, dong_name, bun, ji = parsed
        sigungu_cd = SIGUNGU_NAME_TO_CODE.get(gu_name)
        bjdong_cd = bjdong_table.get((gu_name, dong_name))

        if not sigungu_cd or not bjdong_cd:
            r["사용승인일"] = ""
            r["건물연식"] = ""
            failed += 1
            print(f"  [{i}/{len(mismatched)}] 코드 매핑 실패: {gu_name} {dong_name}")
            continue

        title = get_building_title(sigungu_cd, bjdong_cd, bun, ji)
        time.sleep(0.15)

        if title is None or title is API_FAILURE:
            r["사용승인일"] = ""
            r["건물연식"] = ""
            failed += 1
            reason = "미등록 지번" if title is None else "API 조회 실패"
            print(f"  [{i}/{len(mismatched)}] {reason}: {r.get('상가명')}")
            continue

        # ⚠️ 국토교통부 표제부 API 응답 필드명이 실제로 'useAprDay'가 맞는지
        #    아래 print로 첫 몇 건은 꼭 직접 확인하세요. 다르면 이 키만 바꾸면 됩니다.
        if i <= 3:
            print(f"  [샘플 응답 확인용] {r.get('상가명')}: {title}")

        use_apr_day = title.get("useAprDay", "")
        r["사용승인일"] = use_apr_day

        if use_apr_day and len(use_apr_day) >= 4 and use_apr_day[:4].isdigit():
            approval_year = int(use_apr_day[:4])
            r["건물연식"] = datetime.now().year - approval_year
            success += 1
        else:
            r["건물연식"] = ""
            failed += 1

        print(f"  [{i}/{len(mismatched)}] {r.get('상가명')} - 사용승인일: {use_apr_day or '없음'}")

    out_path = os.path.join(CVS_DIR, "verification_log_with_age.csv")
    if mismatched:
        fieldnames = list(mismatched[0].keys())
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(mismatched)

    print("\n" + "=" * 60)
    print(f"완료: 성공 {success}건 / 실패 {failed}건 (전체 {len(mismatched)}건)")
    print(f"저장 위치: {out_path}")
    print("=" * 60)
    print("\n※ 원본 verification_log.csv는 전혀 수정되지 않았습니다.")
    print("※ 이 스크립트는 등록전유부수·실제영업중수를 다시 조회하지 않으므로")
    print("  기존 보고서의 71건/92.2% 등의 수치는 그대로 유효합니다.")


if __name__ == "__main__":
    main()