"""
지역별 공실 위험도 K-Means 클러스터링 (변수 12개: 7개 분기 평균 + 최근 2년 변동폭)
입력: 중대형/소규모/오피스 공실률 및 임대료 (2024 3Q ~ 2026 1Q 7개 분기 시계열)
  - 지속성 지표 (6개): 7개 분기 평균값
  - 추세 지표 (6개): 최근 2년 변동폭 (2026 1Q - 2024 3Q)
출력: 역산공실탐지기반_클러스터링.html
"""
import csv
import json
import os
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CVS_DIR = os.path.join(BASE_DIR, "cvs")
HTML_DIR = os.path.join(os.path.dirname(BASE_DIR), "html")

REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
           "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]

# 시도 중심 좌표
COORDS = {
    "서울": (37.566, 126.978), "부산": (35.179, 129.075), "대구": (35.871, 128.601),
    "인천": (37.456, 126.705), "광주": (35.160, 126.851), "대전": (36.351, 127.385),
    "울산": (35.538, 129.311), "세종": (36.480, 127.289), "경기": (37.275, 127.009),
    "강원": (37.885, 127.730), "충북": (36.635, 127.491), "충남": (36.658, 126.673),
    "전북": (35.820, 127.108), "전남": (34.816, 126.463), "경북": (36.576, 128.506),
    "경남": (35.238, 128.692), "제주": (33.489, 126.498),
}

FILES = {
    "vac_large":  "임대동향_지역별_공실률_2024년3분기___중대형_상가.csv",
    "vac_small":  "임대동향_지역별_공실률_2024년3분기___소규모_상가.csv",
    "vac_office": "임대동향_지역별_공실률_2024년3분기___오피스.csv",
    "rent_large":  "임대동향_지역별_임대료_2024년3분기___중대형_상가.csv",
    "rent_small":  "임대동향_지역별_임대료_2024년3분기___소규모_상가.csv",
    "rent_office": "임대동향_지역별_임대료_2024년3분기___오피스.csv",
}

QUARTERS = ["2024 3Q", "2024 4Q", "2025 1Q", "2025 2Q", "2025 3Q", "2025 4Q", "2026 1Q"]


def read_timeseries(filename):
    """CSV에서 7개 분기 전체를 읽어 평균(지속성)·변동폭(추세)·원본 시계열을 반환한다."""
    path = os.path.join(CVS_DIR, filename)
    with open(path, encoding="cp949") as f:
        rows = list(csv.reader(f))
    avg_out, diff_out, series_out = {}, {}, {}
    for row in rows[3:]:
        if len(row) < 11:
            continue
        _, a, b, c = row[0], row[1], row[2], row[3]
        if a == b == c and a != "전국":
            vals = [float(x) for x in row[4:11]]  # 2024 3Q ~ 2026 1Q (7개 분기)
            avg_out[a] = sum(vals) / len(vals)
            diff_out[a] = vals[-1] - vals[0]  # 최근 분기 - 과거 최초 분기
            series_out[a] = vals
    return avg_out, diff_out, series_out


def main():
    avg_vals, diff_vals, series_vals = {}, {}, {}
    for k, fn in FILES.items():
        a, d, s = read_timeseries(fn)
        avg_vals[k], diff_vals[k], series_vals[k] = a, d, s

    # 변수 12개 구성 (6개 평균 + 6개 변동폭)
    feature_types = ["vac_large", "vac_small", "vac_office", "rent_large", "rent_small", "rent_office"]

    # 세종시 제외한 16개 시도로 학습 (세종은 오피스 임대동향 조사 미실시)
    fit_regions = [r for r in REGIONS if r != "세종"]

    X_list = []
    for r in fit_regions:
        row = [avg_vals[k][r] for k in feature_types] + [diff_vals[k][r] for k in feature_types]
        X_list.append(row)
    X = np.array(X_list)

    # 표준화 (StandardScaler)
    mean = X.mean(axis=0)
    std = X.std(axis=0, ddof=0)
    std[std == 0] = 1.0  # 0으로 나눔 방지
    Xs = (X - mean) / std

    # K-Means (k=3, random_state=42)
    rng = np.random.default_rng(42)
    k = 3

    def kmeans_plusplus_init(data, k, rng):
        n = data.shape[0]
        centers = [data[rng.integers(n)]]
        for _ in range(1, k):
            d2 = np.min([((data - c) ** 2).sum(axis=1) for c in centers], axis=0)
            probs = d2 / (d2.sum() or 1.0)
            centers.append(data[rng.choice(n, p=probs)])
        return np.array(centers)

    best_inertia, best_labels, best_centers = None, None, None
    for _ in range(20):
        centers = kmeans_plusplus_init(Xs, k, rng)
        for _ in range(100):
            dists = np.linalg.norm(Xs[:, None, :] - centers[None, :, :], axis=2)
            labels = dists.argmin(axis=1)
            new_centers = np.array([
                Xs[labels == c].mean(axis=0) if (labels == c).any() else centers[c]
                for c in range(k)
            ])
            if np.allclose(new_centers, centers):
                break
            centers = new_centers
        inertia = ((Xs - centers[labels]) ** 2).sum()
        if best_inertia is None or inertia < best_inertia:
            best_inertia, best_labels, best_centers = inertia, labels, centers

    labels = best_labels
    centers = best_centers

    # 세종시는 오피스 제외한 8개 상가 변수로 부분거리 매칭
    shop_indices = [0, 1, 3, 4, 6, 7, 9, 10]
    sejong_x = np.array(
        [avg_vals[k]["세종"] for k in ["vac_large", "vac_small", "rent_large", "rent_small"]] +
        [diff_vals[k]["세종"] for k in ["vac_large", "vac_small", "rent_large", "rent_small"]]
    )
    sejong_xs = (sejong_x - mean[shop_indices]) / std[shop_indices]
    sejong_dists = np.linalg.norm(centers[:, shop_indices] - sejong_xs, axis=1)
    sejong_label = int(sejong_dists.argmin())

    all_labels = {r: int(labels[i]) for i, r in enumerate(fit_regions)}
    all_labels["세종"] = sejong_label

    # 위험도 순위: (공실률 평균+변동폭) - (임대료 평균+변동폭) 높을수록 고위험
    vac_idx = [0, 1, 2, 6, 7, 8]
    rent_idx = [3, 4, 5, 9, 10, 11]
    risk_score = {}
    for c in range(k):
        idx = np.where(labels == c)[0]
        risk_score[c] = Xs[idx][:, vac_idx].mean() - Xs[idx][:, rent_idx].mean()
    order = sorted(range(k), key=lambda c: -risk_score[c])
    cluster_rank = {cluster: rank for rank, cluster in enumerate(order)}

    palette = [
        ("고위험", "#e34948", "#fef2f2"),
        ("중위험", "#f59e0b", "#fefce8"),
        ("저위험", "#2a78d6", "#eff6ff"),
    ]

    data_out = []
    for r in REGIONS:
        rank = cluster_rank[all_labels[r]]
        label, color, bg = palette[rank]
        lat, lng = COORDS[r]
        has_office = r != "세종"

        data_out.append({
            "name": r, "cluster": rank, "label": label, "color": color, "bg": bg,
            "lat": lat, "lng": lng,
            # 최근(2026 1Q 근사) 수치 = 평균 + 변동폭의 절반
            "vac_large": round(avg_vals["vac_large"][r] + diff_vals["vac_large"][r] / 2, 1),
            "vac_small": round(avg_vals["vac_small"][r] + diff_vals["vac_small"][r] / 2, 1),
            "vac_office": round(avg_vals["vac_office"][r] + diff_vals["vac_office"][r] / 2, 1) if has_office else None,
            # 추세 변동폭 (2년간, %p)
            "diff_vac_large": round(diff_vals["vac_large"][r], 1),
            "diff_rent_large": round(diff_vals["rent_large"][r], 1),
            "rent_large": round(avg_vals["rent_large"][r] + diff_vals["rent_large"][r] / 2, 1),
            "rent_small": round(avg_vals["rent_small"][r] + diff_vals["rent_small"][r] / 2, 1),
            "rent_office": round(avg_vals["rent_office"][r] + diff_vals["rent_office"][r] / 2, 1) if has_office else None,
        })

    counts = {0: 0, 1: 0, 2: 0}
    for d in data_out:
        counts[d["cluster"]] += 1

    print("고위험", counts[0], "중위험", counts[1], "저위험", counts[2])
    for label_rank, label_name in enumerate(["고위험", "중위험", "저위험"]):
        regs = [d["name"] for d in data_out if d["cluster"] == label_rank]
        print(f"  {label_name}: {'·'.join(regs)}")

    # 클러스터별(고/중/저위험) 중대형 상가 공실률 7개 분기 평균 추이
    trend_lines = {}
    for label_rank, label_name in enumerate(["고위험군", "중위험군", "저위험군"]):
        regs = [d["name"] for d in data_out if d["cluster"] == label_rank]
        quarterly_avg = []
        for qi in range(7):
            vs = [series_vals["vac_large"][r][qi] for r in regs if r in series_vals["vac_large"]]
            quarterly_avg.append(round(sum(vs) / len(vs), 2))
        trend_lines[label_name] = quarterly_avg
        print(f"  {label_name} 공실률 추이: {quarterly_avg}")

    write_html(data_out, counts, trend_lines)
    return data_out


def write_html(data_out, counts, trend_lines):
    high = [d["name"] for d in data_out if d["cluster"] == 0]
    mid = [d["name"] for d in data_out if d["cluster"] == 1]
    low = [d["name"] for d in data_out if d["cluster"] == 2]

    html = HTML_TEMPLATE.format(
        data_json=json.dumps(data_out, ensure_ascii=False),
        high_count=counts[0], mid_count=counts[1], low_count=counts[2],
        high_regions="·".join(high), mid_regions="·".join(mid), low_regions="·".join(low),
        quarters_json=json.dumps(QUARTERS, ensure_ascii=False),
        trend_json=json.dumps(trend_lines, ensure_ascii=False),
    )
    os.makedirs(HTML_DIR, exist_ok=True)
    out_path = os.path.join(HTML_DIR, "역산공실탐지기반_클러스터링.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"생성 완료: {out_path}")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 지역별 공실 위험도 클러스터링 분석</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .layout {{ display: grid; grid-template-columns: 1fr 380px; gap: 20px; margin-bottom: 1.5rem; }}
  .map-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; position: relative; }}
  .map-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  #mapArea {{ width: 100%; height: 420px; border-radius: 8px; overflow: hidden; }}
  .map-legend {{ position: absolute; z-index: 1000; bottom: 1.5rem; left: 1.5rem; background: rgba(255,255,255,0.95); border: 1px solid #e8e7e2; border-radius: 8px; padding: 10px 14px; }}
  .legend-title {{ font-size: 11px; font-weight: 600; color: #1a1a18; margin-bottom: 6px; }}
  .legend-row {{ display: flex; align-items: center; gap: 6px; font-size: 11px; color: #52514e; margin-bottom: 3px; }}
  .legend-dot {{ width: 12px; height: 12px; border-radius: 50%; border: 1.5px solid #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }}
  .cards-box {{ display: flex; flex-direction: column; gap: 12px; }}
  .cluster-card {{ background: #fff; border-radius: 10px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1rem; border-left: 4px solid; }}
  .card-top {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
  .card-badge {{ font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; color: #fff; }}
  .card-regions {{ font-size: 12px; color: #52514e; margin-bottom: 10px; line-height: 1.5; }}
  .card-stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }}
  .stat-box {{ background: #f8f8f7; border-radius: 6px; padding: 6px 8px; }}
  .stat-label {{ font-size: 10px; color: #898781; margin-bottom: 2px; }}
  .stat-val {{ font-size: 14px; font-weight: 600; color: #0b0b0b; }}
  .insight-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; }}
  .insight-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  .insight-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
  .insight-card {{ background: #f8f8f7; border-radius: 8px; padding: 1rem; border-left: 3px solid; }}
  .insight-label {{ font-size: 11px; font-weight: 600; margin-bottom: 6px; }}
  .insight-body {{ font-size: 12px; color: #52514e; line-height: 1.6; }}
  .source {{ font-size: 11px; color: #898781; margin-top: 1.5rem; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 지역별 공실 위험도 시계열 클러스터링 분석</h1>
<div class="subtitle">K-Means 클러스터링 (k=3, 12개 시계열 종합 변수) | 입력 변수: 7개 분기 평균(지속성 6개) + 2년 간 변동폭(추세 6개) | 출처: 한국부동산원 상업용부동산 임대동향조사</div>

<div class="layout">
  <div class="map-box">
    <div class="map-title">시도별 공실 위험도 시계열 클러스터 분포</div>
    <div id="mapArea"></div>
    <div class="map-legend">
      <div class="legend-title">공실 위험도 (지속성+추세)</div>
      <div class="legend-row"><div class="legend-dot" style="background:#e34948;"></div>고위험 — 누적 공실↑ 악화 추세↑</div>
      <div class="legend-row"><div class="legend-dot" style="background:#f59e0b;"></div>중위험 — 공실 보통 완만 변동</div>
      <div class="legend-row"><div class="legend-dot" style="background:#2a78d6;"></div>저위험 — 공실 낮음 임대료 견조</div>
    </div>
  </div>
  <div class="cards-box" id="cards"></div>
</div>

<div class="map-box" style="margin-bottom: 1.5rem;">
  <div class="map-title">클러스터별 중대형 상가 공실률 추이 (2024 3Q ~ 2026 1Q)</div>
  <div style="position: relative; height: 320px;">
    <canvas id="trendChart" role="img" aria-label="고위험군, 중위험군, 저위험군의 중대형 상가 공실률 7개 분기 추이 선그래프"></canvas>
  </div>
</div>



<div class="source">※ 분석 방법: K-Means 클러스터링 (k=3, 12개 시계열 종합 변수 표준화, k-means++ 초기화, random_state=42)<br>
데이터: 한국부동산원 상업용부동산 임대동향조사 (2024년 3분기 ~ 2026년 1분기, 7개 분기 전체)<br>
지속성(7개 분기 평균)과 추세(최근 2년간 증감폭)를 동시 반영해 단일 시점 스냅샷의 한계를 보완했습니다.<br>
세종은 오피스 임대동향 조사 미실시 지역으로 K-means 학습(16개 시도)에서는 제외했고, 실측된 상가 지표(공실률·임대료 평균 및 변동폭) 8개 변수만으로 최근접 중심점(부분거리 방식)을 찾아 군집을 배정했습니다.</div>

<script>
const data = {data_json};

const map = L.map('mapArea').setView([36.2, 127.8], 6.7);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 18,
  attribution: '&copy; OpenStreetMap contributors'
}}).addTo(map);

data.forEach(d => {{
  const circle = L.circleMarker([d.lat, d.lng], {{
    radius: 14,
    fillColor: d.color,
    color: '#fff',
    weight: 2,
    fillOpacity: 0.9,
  }}).addTo(map);
  circle.bindTooltip(`<b>${{d.name}}</b> (${{d.label}})<br>상가공실 ${{d.vac_large}}% (2년 변동: ${{d.diff_vac_large >= 0 ? '+' : ''}}${{d.diff_vac_large}}%p)`);
}});

const cards = document.getElementById('cards');
[{{c:0,label:'고위험',desc:'누적 공실↑ 악화 추세↑',color:'#e34948'}},
 {{c:1,label:'중위험',desc:'공실 보통 완만 변동',color:'#f59e0b'}},
 {{c:2,label:'저위험',desc:'공실 낮음 임대료 견조',color:'#2a78d6'}}].forEach(cl => {{
  const g = data.filter(d => d.cluster === cl.c);
  if (!g.length) return;
  const avg = k => {{
    const vals = g.map(d=>d[k]).filter(v => v != null);
    return vals.length ? (vals.reduce((s,v)=>s+v,0)/vals.length).toFixed(1) : 'N/A';
  }};
  cards.innerHTML += `<div class="cluster-card" style="border-left-color:${{cl.color}};">
    <div class="card-top"><span class="card-badge" style="background:${{cl.color}};">${{cl.label}}군</span><span style="font-size:12px;color:#52514e;">${{cl.desc}}</span></div>
    <div class="card-regions">${{g.map(d=>d.name).join(' · ')}}</div>
    <div class="card-stats">
      <div class="stat-box"><div class="stat-label">중대형상가 공실률</div><div class="stat-val" style="color:${{cl.color}};">${{avg('vac_large')}}%</div></div>
      <div class="stat-box"><div class="stat-label">소규모상가 공실률</div><div class="stat-val" style="color:${{cl.color}};">${{avg('vac_small')}}%</div></div>
      <div class="stat-box"><div class="stat-label">오피스 공실률 (세종 제외)</div><div class="stat-val" style="color:${{cl.color}};">${{avg('vac_office')}}%</div></div>
      <div class="stat-box"><div class="stat-label">중대형상가 2년 변동폭</div><div class="stat-val">${{avg('diff_vac_large')}}%p</div></div>
      <div class="stat-box"><div class="stat-label">중대형상가 임대료</div><div class="stat-val">${{avg('rent_large')}}천원/㎡</div></div>
      <div class="stat-box"><div class="stat-label">중대형임대료 2년 변동폭</div><div class="stat-val">${{avg('diff_rent_large')}}천원/㎡</div></div>
    </div>
  </div>`;
}});

const quarters = {quarters_json};
const trend = {trend_json};
const trendColors = {{ "고위험군": "#e34948", "중위험군": "#eda100", "저위험군": "#2a78d6" }};
const trendDash = {{ "고위험군": [], "중위험군": [6,3], "저위험군": [2,2] }};
const trendPoint = {{ "고위험군": "circle", "중위험군": "rect", "저위험군": "triangle" }};

new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{
    labels: quarters,
    datasets: Object.keys(trend).map(name => ({{
      label: name,
      data: trend[name],
      borderColor: trendColors[name],
      backgroundColor: trendColors[name] + "22",
      borderDash: trendDash[name],
      pointStyle: trendPoint[name],
      borderWidth: 2,
      pointRadius: 4,
      tension: 0.25,
      fill: false,
    }}))
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ font: {{ size: 12 }}, usePointStyle: true }} }},
      tooltip: {{ callbacks: {{ label: ctx => `${{ctx.dataset.label}}: ${{ctx.parsed.y}}%` }} }}
    }},
    scales: {{
      y: {{ title: {{ display: true, text: '공실률 (%)' }}, ticks: {{ callback: v => v + '%' }} }},
      x: {{ grid: {{ display: false }} }}
    }}
  }}
}});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()