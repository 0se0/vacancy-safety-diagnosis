"""
anomaly_detection.py

closure_risk_classifier.py의 지도학습(Random Forest) 조기경보와 별개로, 같은
피처셋에 비지도 이상탐지(Isolation Forest)를 적용해본다. RF는 "다음 분기에
폐업률이 통계적으로 유의하게 증가한다"는 라벨을 보고 학습한 것이고, Isolation
Forest는 라벨을 전혀 안 보고 "이 상권x업종의 이번 분기 지표 패턴 자체가 전체
분포에서 얼마나 동떨어져 있는가"만 본다. 그래서 두 가지를 확인할 수 있다:

  1. 라벨을 하나도 안 보고도 미래 위험(risk_label)을 어느 정도 맞추는가
     (검증셋 risk_label에 대한 AUC로 측정 - 학습에는 절대 안 쓰고 평가에만 씀)
  2. RF가 "위험하다"고 본 상위 그룹과 Isolation Forest가 "이상하다"고 본 상위
     그룹이 얼마나 겹치는가 - 완전히 겹치면 두 관점이 같은 신호를 보는 것이고,
     안 겹치면 서로 다른 종류의 이상을 잡고 있다는 뜻

★ RF와 동일한 전처리·피처·train/test 시계열 분할을 그대로 재현한다
  (closure_risk_classifier.py와 다른 전처리를 쓰면 비교 자체가 무의미해지므로,
  함수로 분리돼 있지 않은 라벨 생성 로직까지 그대로 복제했다).
★ contamination(이상치로 볼 비율)은 RF 라벨의 실측 위험비율(4.8%)에 맞췄다 -
  "전체 중 몇 %를 위험군으로 볼 것인가"를 두 모델이 같은 기준으로 보게 하기 위해.

★ 결과: Isolation Forest AUC 0.555 (RF 0.881보다 한참 낮음, 그래도 랜덤 0.5보다는
  나음). 이상치로 잡힌 그룹을 까보니 대부분 "점포수·프랜차이즈점포수가 큰 대형
  상권"이었다(예: 유사업종 점포수 434 vs 정상군 58) - 절대량이 큰 값을 이상치로
  보는 흔한 함정처럼 보여서, (a) StandardScaler로 표준화, (b) 절대 카운트 피처
  (점포수 등)를 빼고 비율/추세 피처만 남기는 두 가지를 시도했다. 결과는 각각
  0.555(변화 없음), 0.507(오히려 랜덤 수준으로 하락) - 가설이 틀렸다는 게
  실측으로 확인됐다. 진짜 원인은 스케일이 아니라, RF의 라벨("다음 분기에
  폐업률이 유의하게 증가")이 애초에 "미래의 변화"를 보는 라벨이라 "현재 시점의
  이례성"만 보는 비지도 이상탐지로는 구조적으로 잡기 어렵다는 것 - naive_auc가
  0.183(현재 수준과 미래 악화가 오히려 반비례)이었던 것과 같은 맥락이다.

돌리는 법:
  python anomaly_detection.py
  결과: html/역산공실탐지기반_이상탐지비교.html
"""
import json
import os

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import LabelEncoder

from closure_risk_classifier import (
    FEATURES,
    FEATURE_LABELS,
    MIN_STOR,
    TEST_MIN_Q,
    TRAIN_MAX_Q,
    Z_THRESHOLD,
    build_features,
    load_panel,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_DIR = os.path.join(BASE_DIR, "html")

CONTAMINATION = 0.048  # RF 라벨의 실측 위험비율(4.8%)과 맞춤 - 공정 비교를 위해


def prepare():
    """closure_risk_classifier.main()과 동일한 전처리 (비교 정합성을 위해 그대로 재현)."""
    full = load_panel()
    full = build_features(full)
    le_se, le_induty = LabelEncoder(), LabelEncoder()
    full['trdar_se_enc'] = le_se.fit_transform(full['trdar_se_cd'])
    full['induty_enc'] = le_induty.fit_transform(full['svc_induty_cd'])

    needed = ['target_next_clsbiz_stor_co', 'target_next_stor_co', 'prev_clsbiz_rt', 'prev_opbiz_rt',
              'clsbiz_rt_ma3', 'clsbiz_rt_slope3']
    model_df = full.dropna(subset=needed)
    sub = model_df[model_df['stor_co'] >= MIN_STOR].copy()

    p1 = sub['clsbiz_stor_co'] / sub['stor_co']
    n1 = sub['stor_co']
    p2 = sub['target_next_clsbiz_stor_co'] / sub['target_next_stor_co']
    n2 = sub['target_next_stor_co']
    p_pool = (sub['clsbiz_stor_co'] + sub['target_next_clsbiz_stor_co']) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    sub['z_score'] = (p2 - p1) / se
    sub = sub[sub['z_score'].notna() & np.isfinite(sub['z_score'])]
    sub['risk_label'] = (sub['z_score'] >= Z_THRESHOLD).astype(int)

    train = sub[sub['stdr_yyqu_cd'] <= TRAIN_MAX_Q]
    test = sub[sub['stdr_yyqu_cd'] >= TEST_MIN_Q]
    return train, test


def fit_rf(train, test):
    base_clf = RandomForestClassifier(n_estimators=300, max_depth=8, min_samples_leaf=15,
                                       class_weight='balanced', n_jobs=-1, random_state=42)
    clf = CalibratedClassifierCV(base_clf, method='isotonic', cv=3)
    clf.fit(train[FEATURES], train['risk_label'])
    return clf.predict_proba(test[FEATURES])[:, 1]


def fit_isolation_forest(train, test):
    """라벨을 전혀 안 씀(train['risk_label']을 fit에 넘기지 않음) - 순수 비지도."""
    iso = IsolationForest(n_estimators=300, contamination=CONTAMINATION,
                           random_state=42, n_jobs=-1)
    iso.fit(train[FEATURES])
    # decision_function: 높을수록 정상, 낮을수록 이상 -> 부호 뒤집어서 "이상 점수"로 통일
    anomaly_score = -iso.decision_function(test[FEATURES])
    return anomaly_score, iso


def overlap_at_k(rf_proba, iso_score, k_frac):
    n = len(rf_proba)
    k = max(1, int(round(n * k_frac)))
    rf_top = set(np.argsort(-rf_proba)[:k])
    iso_top = set(np.argsort(-iso_score)[:k])
    inter = rf_top & iso_top
    union = rf_top | iso_top
    return {
        "k": k, "n": n,
        "overlap_count": len(inter),
        "jaccard": round(len(inter) / len(union), 3) if union else 0.0,
        "overlap_pct_of_k": round(len(inter) / k * 100, 1),
    }


def feature_gap(train, iso, test, top_idx_iso, bottom_idx_iso):
    """Isolation Forest가 '이상'으로 본 그룹과 '정상'으로 본 그룹의 피처 평균 차이 - 어떤 지표가 이상 판정을 이끄는지."""
    top = test.iloc[top_idx_iso][FEATURES].mean()
    rest = test.iloc[bottom_idx_iso][FEATURES].mean()
    gap = (top - rest).sort_values(key=lambda s: s.abs(), ascending=False)
    return [{"name": FEATURE_LABELS.get(k, k), "top": round(float(top[k]), 2),
              "rest": round(float(rest[k]), 2)} for k in gap.index[:6]]


def generate(ctx: dict) -> str:
    kpi_rf_auc = ctx["rf_auc"]
    kpi_iso_auc = ctx["iso_auc"]
    kpi_naive_auc = ctx["naive_auc"]
    ov = ctx["overlap"]
    gaps = ctx["gaps"]
    gap_rows = "".join(
        f"<tr><td>{g['name']}</td><td>{g['top']}</td><td>{g['rest']}</td></tr>" for g in gaps
    )
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 지도학습 vs 비지도 이상탐지 비교</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .caveat {{ background: #eff6ff; border-left: 3px solid #2a78d6; padding: 0.875rem 1.1rem; font-size: 12px; color: #52514e; margin-bottom: 1.5rem; line-height: 1.7; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 1.5rem; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 1rem; text-align: center; }}
  .kpi-label {{ font-size: 12px; color: #898781; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 24px; font-weight: 600; }}
  .kpi-sub {{ font-size: 11px; color: #898781; margin-top: 4px; }}
  .chart-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; margin-bottom: 1.5rem; }}
  .chart-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: #898781; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e8e7e2; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #f1f0eb; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
</style>
</head>
<body>
<h1>지도학습(Random Forest) vs 비지도 이상탐지(Isolation Forest)</h1>
<div class="subtitle">같은 상권x업종 피처셋, 같은 검증셋(2025년 1~3분기)에 두 가지 다른 관점을 적용</div>

<div class="caveat">
📍 Isolation Forest는 폐업위험 라벨을 <b>전혀 보지 않고</b> 학습했다. "이 상권x업종의 이번 분기 지표 패턴이 전체
분포에서 얼마나 동떨어져 있는가"만으로 이상치를 골라낸 뒤, 그 순위를 나중에 실제 라벨과 대조했다.<br>
비지도 방식이 지도학습만큼 미래 위험을 맞히면, 라벨(다음 분기 데이터)이 아직 없는 새 업종·신규 상권에도
곧바로 적용할 수 있다는 뜻이라 실용적 의미가 있다.
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">Random Forest (지도학습)</div>
    <div class="kpi-value" style="color:#2a78d6;">{kpi_rf_auc}</div>
    <div class="kpi-sub">AUC · 라벨을 보고 학습</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">Isolation Forest (비지도)</div>
    <div class="kpi-value" style="color:#8b5cf6;">{kpi_iso_auc}</div>
    <div class="kpi-sub">AUC · 라벨 없이 이상치만으로 순위화</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">단순규칙 대조군</div>
    <div class="kpi-value" style="color:#898781;">{kpi_naive_auc}</div>
    <div class="kpi-sub">현재 폐업률로만 순위화</div>
  </div>
</div>

<div class="chart-box">
  <div class="chart-title">상위 위험군 겹침도 (상위 {ov['k']:,}건, 검증셋의 {ov['k']/ov['n']*100:.1f}%)</div>
  <table>
    <tr><th>지표</th><th>값</th></tr>
    <tr><td>두 모델 모두 상위권으로 꼽은 건수</td><td>{ov['overlap_count']:,} / {ov['k']:,}</td></tr>
    <tr><td>Jaccard 유사도</td><td>{ov['jaccard']}</td></tr>
    <tr><td>RF 상위군 중 Isolation Forest도 이상치로 본 비율</td><td>{ov['overlap_pct_of_k']}%</td></tr>
  </table>
</div>

<div class="chart-box">
  <div class="chart-title">Isolation Forest가 "이상"으로 본 그룹 vs "정상"으로 본 그룹의 피처 평균 차이 (격차 큰 순)</div>
  <table>
    <thead><tr><th>피처</th><th>이상 그룹 평균</th><th>정상 그룹 평균</th></tr></thead>
    <tbody>{gap_rows}</tbody>
  </table>
</div>

<div class="note">
※ 방법론: closure_risk_classifier.py와 동일한 전처리·피처(17개)·시계열 분할(2024년 4분기까지 학습, 2025년
1~3분기 검증)을 그대로 재사용. Isolation Forest는 train 구간의 피처 분포만으로 학습했고, contamination은
RF 라벨의 실측 위험비율(4.8%)에 맞춰 "상위 몇 %를 위험군으로 볼지" 기준을 통일했다.<br>
※ Isolation Forest의 AUC(0.555)가 RF(0.881)보다 한참 낮다. 이상치로 잡힌 그룹이 대부분 점포수·
프랜차이즈점포수가 큰 대형 상권이라 "절대량이 큰 값을 이상치로 보는" 흔한 함정을 의심해 표준화(AUC 변화
없음, 0.555)와 절대 카운트 피처 제외(오히려 랜덤 수준인 0.507로 하락) 두 가지를 시도했지만 개선되지
않았다. 진짜 원인은 스케일이 아니라 구조적인 문제로 보인다 — RF의 라벨은 "다음 분기의 변화"를 보는데,
비지도 이상탐지는 "현재 시점의 이례성"만 볼 수 있어서다. 현재 폐업률만으로 순위를 매긴 단순규칙(AUC
0.183, 대조군)이 랜덤보다도 나빴던 것과 같은 맥락 — 이 도메인에서는 현재 상태가 미래 악화와 직접
비례하지 않는다.<br>
겹침도가 낮다는 것(1.9%)도 같은 이유다 — 두 모델이 "위험"을 다른 방식으로 정의하고 있어서, 병행 사용의
장점보다는 이 문제엔 지도학습(변화를 아는 라벨)이 비지도보다 구조적으로 유리하다는 결론에 더 가깝다.
</div>

</body>
</html>"""


if __name__ == "__main__":
    print("1) 전처리 (closure_risk_classifier.py와 동일 로직 재현)")
    train, test = prepare()
    print(f"   학습 {len(train):,}행 / 검증 {len(test):,}행, 검증셋 실제 위험비율 {test['risk_label'].mean()*100:.1f}%")

    print("2) Random Forest (지도학습, 기존 모델 재현)")
    rf_proba = fit_rf(train, test)
    rf_auc = roc_auc_score(test['risk_label'], rf_proba)
    print(f"   AUC {rf_auc:.3f}")

    print("3) Isolation Forest (비지도 이상탐지, 신규)")
    iso_score, iso_model = fit_isolation_forest(train, test)
    iso_auc = roc_auc_score(test['risk_label'], iso_score)
    print(f"   AUC {iso_auc:.3f} (라벨을 전혀 안 보고 계산한 이상치 점수 기준)")

    naive_proba = test['clsbiz_rt'] / test['clsbiz_rt'].max()
    naive_auc = roc_auc_score(test['risk_label'], naive_proba)
    print(f"   [대조군] 단순규칙 AUC {naive_auc:.3f}")

    print("4) 두 모델의 상위 위험군 겹침도")
    ov = overlap_at_k(rf_proba, iso_score, CONTAMINATION)
    print(f"   상위 {ov['k']}건(={CONTAMINATION*100:.1f}%) 기준: {ov['overlap_count']}건 겹침 "
          f"(Jaccard {ov['jaccard']}, RF 상위군의 {ov['overlap_pct_of_k']}%가 이상치로도 잡힘)")

    print("5) 이상 그룹 vs 정상 그룹 피처 차이")
    n = len(test)
    k = ov['k']
    order = np.argsort(-iso_score)
    top_idx, rest_idx = order[:k], order[k:]
    gaps = feature_gap(train, iso_model, test, top_idx, rest_idx)
    for g in gaps:
        print(f"   {g['name']}: 이상군 {g['top']} vs 정상군 {g['rest']}")

    html = generate({
        "rf_auc": round(float(rf_auc), 3), "iso_auc": round(float(iso_auc), 3),
        "naive_auc": round(float(naive_auc), 3), "overlap": ov, "gaps": gaps,
    })
    out_path = os.path.join(HTML_DIR, "역산공실탐지기반_이상탐지비교.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML 생성 완료: {out_path}")
