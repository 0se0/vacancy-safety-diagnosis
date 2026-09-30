"""
district_closure_validation.py

closure_risk_classifier.py(상권x업종 폐업위험 RF, AUC 0.881)와 오늘 만든 공실/에너지
지표(건물 단위)는 단위가 달라서(상권코드 vs 도로명주소) 바로 못 붙는다. 상권코드를
자치구로 연결해주는 참조 테이블("서울특별시_우리마을가게 상권분석서비스(상권영역)",
data.go.kr/data/15076394)을 받아서, 자치구 단위로 두 신호를 집계해 상관관계를 본다.

★ 피처로 넣어서 재학습하지 않는 이유(중요): closure_risk_classifier.py는 2024년까지
  학습·2025년으로 검증하는 시계열 모델인데, 공실/에너지 데이터는 2026-09 시점
  스냅샷이다. 이걸 피처로 넣어 재학습하면 미래 정보가 과거 예측에 새는 데이터
  누수가 된다. 그래서 재학습은 하지 않고, 이미 학습된 모델의 "최신 분기 예측치"를
  자치구 단위로 평균 내서, 독립적으로 만든 공실률/에너지 지표와 상관관계가 있는지만
  검증한다(energy_vacancy_indicator.py가 점포수-전력사용량 상관관계를 검증했던 것과
  같은 논리) - 두 신호가 실제로 수렴하면, 그 자체로 서로에 대한 검증이 된다.

돌리는 법:
  1. cvs2/상권영역_자치구매핑.csv 필요 (data.go.kr/data/15076394 다운로드,
     컬럼에 상권코드/자치구명 있어야 함)
  2. cvs/vacancy_candidates.csv, cvs/vacancy_candidates_with_energy.csv 필요
     (commercial_vacancy_screening.py, link_candidates_to_energy.py 실행 결과)
  3. python district_closure_validation.py 실행 (로컬 계산만 있어서 API 호출 없음, 빠름)
  4. 결과: 콘솔에 자치구별 집계표 + Pearson/Spearman 상관계수
"""
import os

import numpy as np
import pandas as pd
from scipy import stats

from closure_risk_classifier import main as run_closure_model

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CVS_DIR = os.path.join(BASE_DIR, "cvs")
CVS2_DIR = os.path.join(BASE_DIR, "cvs2")
MAPPING_PATH = os.path.join(CVS2_DIR, "상권영역_자치구매핑.csv")


def load_trdar_to_gu() -> dict:
    """상권영역 참조 테이블에서 상권코드 -> 자치구명 매핑을 뽑는다.
    컬럼명이 출처마다 조금씩 다를 수 있어(상권_코드/TRDAR_CD 등) 후보를 다 시도한다."""
    if not os.path.exists(MAPPING_PATH):
        raise FileNotFoundError(
            f"{MAPPING_PATH} 없음. data.go.kr/data/15076394 에서 "
            "'서울특별시_우리마을가게 상권분석서비스(상권영역)' CSV를 받아 이 이름으로 저장하세요."
        )
    df = None
    for enc in ["utf-8-sig", "cp949", "euc-kr"]:
        try:
            df = pd.read_csv(MAPPING_PATH, encoding=enc, dtype=str)
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        raise ValueError("상권영역 매핑 파일 인코딩을 확인할 수 없습니다.")

    cols = {c: c.strip() for c in df.columns}
    df = df.rename(columns=cols)

    # 상권_코드(키)와 자치구_코드_명(구 이름) 컬럼을 찾는다.
    # "상권_구분_코드"(A=골목상권 등 유형코드)와 헷갈리면 안 되므로 "구분" 들어간 건 제외.
    # "자치구_코드"(숫자코드)가 아니라 "자치구_코드_명"(구 이름 문자열)이 필요하므로 "명" 붙은 쪽 사용.
    trdar_col = next((c for c in df.columns if "상권" in c and "코드" in c and "명" not in c and "구분" not in c), None)
    gu_col = next((c for c in df.columns if ("자치구" in c or "시군구" in c) and "명" in c), None)
    if trdar_col is None or gu_col is None:
        raise ValueError(f"컬럼을 못 찾음. 실제 컬럼: {list(df.columns)}")

    df = df[[trdar_col, gu_col]].dropna()
    # closure_risk_classifier.py 쪽 trdar_cd는 CSV에서 숫자(int64)로 읽히므로,
    # 매핑 딕셔너리 키도 int로 맞춰야 나중에 map()이 실제로 매칭됨(문자열로 두면 전부 NaN됨).
    df[trdar_col] = pd.to_numeric(df[trdar_col].str.strip(), errors="coerce")
    df = df.dropna(subset=[trdar_col])
    df[trdar_col] = df[trdar_col].astype(int)
    df[gu_col] = df[gu_col].str.strip()
    mapping = dict(zip(df[trdar_col], df[gu_col]))
    print(f"상권코드->자치구 매핑 {len(mapping)}건 로드 (컬럼: {trdar_col} -> {gu_col})")
    return mapping


def gu_level_vacancy_stats() -> pd.DataFrame:
    """구별 공실 후보율/확정공실율을 계산 (commercial_vacancy_screening.py 결과 재사용)."""
    from commercial_vacancy_screening import load_commercial_ledger

    ledger = load_commercial_ledger()
    ledger_counts = ledger.groupby("시군구").size().rename("commercial_buildings")

    candidates = pd.read_csv(os.path.join(CVS_DIR, "vacancy_candidates.csv"), encoding="utf-8-sig", dtype=str)
    cand_counts = candidates.groupby("gu").size().rename("vacancy_candidates")

    stats_df = pd.concat([ledger_counts, cand_counts], axis=1).fillna(0)
    stats_df["vacancy_rate_pct"] = round(stats_df["vacancy_candidates"] / stats_df["commercial_buildings"] * 100, 2)

    energy_path = os.path.join(CVS_DIR, "vacancy_candidates_with_energy.csv")
    if os.path.exists(energy_path):
        we = pd.read_csv(energy_path, encoding="utf-8-sig", dtype=str)
        we["elec_avg"] = pd.to_numeric(we["elec_avg"], errors="coerce")
        we["gas_avg"] = pd.to_numeric(we["gas_avg"], errors="coerce")
        confirmed = we[we["elec_avg"].isna() & we["gas_avg"].isna()]
        confirmed_counts = confirmed.groupby("gu").size().rename("confirmed_vacant")
        stats_df = pd.concat([stats_df, confirmed_counts], axis=1).fillna(0)
        stats_df["confirmed_vacant_rate_pct"] = round(
            stats_df["confirmed_vacant"] / stats_df["commercial_buildings"] * 100, 2)

    return stats_df


def gu_level_closure_risk(latest_full: pd.DataFrame, trdar_to_gu: dict) -> pd.Series:
    df = latest_full.copy()
    df["gu"] = df["trdar_cd"].map(trdar_to_gu)
    unmatched = df["gu"].isna().sum()
    print(f"상권x업종 {len(df):,}건 중 자치구 매핑 실패 {unmatched:,}건 "
          f"({round(unmatched/len(df)*100,1)}%) - 제외하고 진행")
    df = df.dropna(subset=["gu"])
    return df.groupby("gu")["risk_proba"].mean().rename("avg_closure_risk_proba")


if __name__ == "__main__":
    print("=== 1단계: 상권코드->자치구 매핑 로드 ===")
    trdar_to_gu = load_trdar_to_gu()

    print("\n=== 2단계: 폐업위험 모델 실행(기존 학습 그대로, 재학습 아님 - 이미 학습된 결과 재사용) ===")
    closure_result = run_closure_model()
    latest_full = closure_result["latest_full"]

    print("\n=== 3단계: 자치구 단위 집계 ===")
    closure_by_gu = gu_level_closure_risk(latest_full, trdar_to_gu)
    vacancy_by_gu = gu_level_vacancy_stats()

    merged = pd.concat([closure_by_gu, vacancy_by_gu], axis=1).dropna(subset=["avg_closure_risk_proba"])
    print(merged.to_string())

    print("\n=== 4단계: 상관관계 검증 ===")
    for col in ["vacancy_rate_pct", "confirmed_vacant_rate_pct"]:
        if col not in merged.columns:
            continue
        sub = merged.dropna(subset=[col, "avg_closure_risk_proba"])
        if len(sub) < 5:
            print(f"  {col}: 표본 부족({len(sub)}개구), 스킵")
            continue
        pearson_r, pearson_p = stats.pearsonr(sub["avg_closure_risk_proba"], sub[col])
        spearman_r, spearman_p = stats.spearmanr(sub["avg_closure_risk_proba"], sub[col])
        print(f"  폐업위험예측 <-> {col}: Pearson r={pearson_r:.3f}(p={pearson_p:.3f}), "
              f"Spearman r={spearman_r:.3f}(p={spearman_p:.3f}), n={len(sub)}개구")

    out_path = os.path.join(CVS_DIR, "district_closure_vacancy_correlation.csv")
    merged.to_csv(out_path, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")
