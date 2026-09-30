.PHONY: install verification building-age screening chain-a \
        alt-vacancy risk-grade safety-map chain-b \
        energy vacancy-screening link-energy \
        dashboard clustering industrial closure-risk poc

PYTHON ?= python3

SRC := src

install:
	$(PYTHON) -m pip install -r requirements.txt

## 체인 A: 실측 검증 -> 건물연식 보강 -> 의심건물 스크리닝
verification:
	$(PYTHON) $(SRC)/core/verification_scan.py

building-age: verification
	$(PYTHON) $(SRC)/core/enrich_building_age.py

screening: building-age
	$(PYTHON) $(SRC)/standalone/suspicious_building_ranking.py

chain-a: screening

## 체인 B: 점포수 지표 -> 안전등급 -> 지도
alt-vacancy:
	$(PYTHON) $(SRC)/core/alt_vacancy_indicator.py

risk-grade: alt-vacancy
	$(PYTHON) $(SRC)/core/risk_grade_model.py

safety-map: risk-grade
	$(PYTHON) $(SRC)/core/safety_map.py

chain-b: safety-map

## 체인 C: 에너지 지표 (SANGGA_API_KEY 필요, 25개구 스캔이라 몇 분 걸림)
energy:
	$(PYTHON) $(SRC)/core/energy_vacancy_indicator.py

## 체인 D: 공실 후보 전수 스크리닝 -> 에너지 3중검증
## (BUILDING_API_KEY 일일 쿼터 제한 있음 - link-energy는 하루에 여러 번 이어 실행될 수 있음)
vacancy-screening:
	$(PYTHON) $(SRC)/core/commercial_vacancy_screening.py

link-energy: vacancy-screening
	$(PYTHON) $(SRC)/core/link_candidates_to_energy.py

## 독립 실행 스크립트
dashboard:
	$(PYTHON) $(SRC)/standalone/dashboard.py

clustering:
	$(PYTHON) $(SRC)/standalone/clustering.py

industrial:
	$(PYTHON) $(SRC)/standalone/industrial_vacancy_indicator.py

closure-risk:
	$(PYTHON) $(SRC)/closure_models/closure_risk_classifier.py

poc:
	$(PYTHON) $(SRC)/standalone/vacancy_matching_poc.py
