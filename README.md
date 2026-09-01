# 역산공실탐지기반 — 노후 상업건물 안전사각지대 해소 모델

건축물대장(등록정보)과 상가정보(실제운영정보)의 차집합으로 공실을 역산하고,
노후 대형상가는 점포수·에너지 사용량 시계열로 대안 진단해 안전관리 우선순위
등급(A~D)을 산출하는 프로젝트. 산출물 목록은 `index.html` 참고.

## 환경 설정

```bash
pip install -r requirements.txt
```

시스템 기본 `python3`(예: macOS Homebrew python)에는 pandas 등이 안 깔려있을 수 있습니다.
conda 환경 등 별도 인터프리터를 쓴다면 아래처럼 `PYTHON` 변수로 지정합니다:

```bash
make install PYTHON=/opt/anaconda3/bin/python
make chain-a PYTHON=/opt/anaconda3/bin/python
```

`.env` 파일에 다음 키가 필요합니다 (스크립트별로 필요한 키가 다름):

```
SANGGA_API_KEY=   # 소상공인시장진흥공단 상가정보 API
BUILDING_API_KEY= # 국토교통부 건축HUB API
```

두 API 모두 [공공데이터포털](https://www.data.go.kr)에서 활용신청 후 발급받습니다.
`BUILDING_API_KEY`는 일일 호출한도가 있고(실측 약 1만 건/일), 초과 시 HTTP 429
(`LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR`)가 발생합니다.

## 필요한 원본 데이터 (커밋되지 않음 — `.gitignore`에 `cvs2/`, `*.csv` 포함)

| 파일/폴더 | 출처 | 비고 |
|---|---|---|
| `cvs/서울시_상권분석서비스_점포-상권__20XX년.csv` (2021~2025) | 서울시 우리마을가게 상권분석서비스 | |
| `cvs/임대동향_지역별_*.csv` | 한국부동산원 상업용부동산 임대동향 | |
| `cvs/한국산업단지공단_전국산업단지현황통계_노후산업단지_*.csv` | 한국산업단지공단 | |
| `국토교통부_전국_법정동_20260630.csv` | 국토교통부 | 법정동코드 매핑용 |
| `cvs2/전기에너지/*.csv`, `cvs2/가스에너지/*.csv` | 한국전력·도시가스 공급량 통계 (월별, 지역별) | 용량이 커서 로컬 전용 |
| `cvs2/건축물대장 정보_표제부.csv` | 건축데이터 개방시스템(open.eais.go.kr) | 서울 일부 표본 |
| `cvs2/건축물대장_표제부_8개구_전체.csv` | 건축HUB "원하는대로 건축데이터" (지역: 8개구, 종류: 건축물대장, CSV) | commercial_vacancy_screening.py 필수 입력 |

## 실행 순서

스크립트 간 실행 순서를 강제하는 장치는 없으므로(Makefile 없음) 아래 순서를
사람이 지켜서 실행해야 합니다. 괄호 안은 각 단계가 만드는 산출물입니다.

**체인 A — 실측 검증 → 건물연식 보강 → 의심건물 스크리닝**
```
python verification_scan.py          # cvs/verification_log.csv
python enrich_building_age.py        # cvs/verification_log_with_age.csv
python suspicious_building_ranking.py
```

**체인 B — 점포수 지표 → 안전등급 → 지도**
```
python alt_vacancy_indicator.py      # (risk_grade_model.py가 analyze() 재사용)
python risk_grade_model.py           # (safety_map.py가 compute_risk_grades() 재사용)
python safety_map.py
```

**체인 C — 에너지 지표 (전기/가스 사용량)**
```
python energy_vacancy_indicator.py   # 8개구 상가 스캔(캡 있음) + 에너지 조인 + 상관관계
```

**체인 D — 공실 후보 전수 스크리닝 → 에너지 3중검증**
```
python commercial_vacancy_screening.py   # cvs/vacancy_candidates.csv (8개구 전수 차집합)
python link_candidates_to_energy.py      # 위 후보를 새주소코드 확보 후 에너지와 조인
                                          # (일일 API 쿼터 제한으로 여러 날에 걸쳐 이어 실행될 수 있음.
                                          #  재실행 시 이미 해결된 후보는 자동으로 건너뜀)
```

**독립 실행 (서로 의존관계 없음)**
```
python dashboard.py
python clustering.py
python industrial_vacancy_indicator.py
python closure_risk_classifier.py
python vacancy_matching_poc.py
```

## 알려진 한계 (재현성 관련)

- 스크립트 간 실행 순서를 강제하는 자동화(Makefile 등)가 없음 — 수동으로 위 순서를 지켜야 함
- 단위 테스트 없음
- `html/*.html` 산출물은 스크립트가 생성하지만 git에는 수동 스냅샷으로 커밋되어 있어,
  코드를 수정한 뒤에는 해당 스크립트를 다시 실행해 리포트를 갱신해야 함
