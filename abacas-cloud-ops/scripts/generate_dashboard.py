# -*- coding: utf-8 -*-
"""生成「全链条费效评估」本地可视化仪表盘（模拟平台网页展示，含各城市成本/效益）"""
import argparse
import csv
import io
import json
import os
import sys

ap = argparse.ArgumentParser(description='生成「全链条费效评估」本地可视化仪表盘（基于重命名结果目录）')
ap.add_argument('--dir', default='task255_out', help='结果文件目录（含 measure_SI_summary / BenMAP / Control Case_Reduction_Cost / ReductionScenarioInfo）')
ap.add_argument('--out', default='dashboard_强化治理.html', help='输出 HTML 路径')
ap.add_argument('--source', default='', help='数据源描述（可选，默认用结果目录名）')
_args = ap.parse_args()
OUT = _args.dir
out_html = _args.out

REQUIRED = ['ReductionScenarioInfo.json', 'measure_SI_summary.csv',
            'PM25_BenMAP_apvrx.csv', 'O3_BenMAP_apvrx.csv']
missing = [f for f in REQUIRED if not os.path.exists(os.path.join(OUT, f))]
if missing:
    sys.exit(f'错误: 结果目录 {OUT} 缺少文件 {missing}。'
             f'请先用 download_results.py 下载完整结果，或用 rename_scenarios.py 生成重命名目录。')


def readcsv(fname):
    p = os.path.join(OUT, fname)
    with open(p, encoding='utf-8-sig') as f:
        return list(csv.DictReader(io.StringIO(f.read())))


def yi(v):
    return round(v / 1e8, 2)


# 情景名（含结构校验，避免裸 KeyError）
try:
    scen = json.load(open(os.path.join(OUT, 'ReductionScenarioInfo.json'), encoding='utf-8-sig'))
except (json.JSONDecodeError, FileNotFoundError) as e:
    sys.exit(f'错误: ReductionScenarioInfo.json 无法读取/解析: {e}')
if not isinstance(scen, dict) or not isinstance(scen.get('scenarios'), list) or not scen['scenarios']:
    sys.exit('错误: ReductionScenarioInfo.json 缺少 scenarios 字段，无法确定情景名。')
si_names = [s['scenarioName'] for s in scen['scenarios']]
primary = scen.get('primaryScenarioKey', si_names[0])

# 检查各情景成本文件是否存在（畸形目录友好报错）
missing_cost = [
    f'Case #{n} Control Case_Reduction_Cost.csv'
    for n in si_names
    if not os.path.exists(os.path.join(OUT, f'Case #{n} Control Case_Reduction_Cost.csv'))
]
if missing_cost:
    sys.exit(f'错误: 缺少情景成本文件 {missing_cost}。请确认结果下载完整。')

# measure_SI_summary
si_rows = readcsv('measure_SI_summary.csv')
si_map = {r['measure_id'].strip(): r for r in si_rows}

# BenMAP 汇总（按情景）
def benmap(fname):
    agg = {}
    for r in readcsv(fname):
        c = r.get('Case_Name', '').strip()
        try:
            agg[c] = agg.get(c, 0) + float(r.get('PointEstimate', 0) or 0)
        except (ValueError, TypeError):
            pass
    return agg

pm_ben = benmap('PM25_BenMAP_apvrx.csv')
o3_ben = benmap('O3_BenMAP_apvrx.csv')

# 成本汇总
def cost(fname):
    return sum(float(r.get('Control_Cost(RMB)', 0) or 0) for r in readcsv(fname))

costs = {n: cost(f'Case #{n} Control Case_Reduction_Cost.csv') for n in si_names}

# 费效比（按污染物）
bc_pm = {n: pm_ben.get(n, 0) / costs[n] if costs[n] else 0 for n in si_names}
bc_o3 = {n: o3_ben.get(n, 0) / costs[n] if costs[n] else 0 for n in si_names}

# ---- 各城市成本（按污染物）----
POLS = ['SO2', 'NOx', 'VOC', 'PM2.5', 'NH3']
cost_city = {}
for lbl in si_names:
    d = {}
    for r in readcsv(f'Case #{lbl} Control Case_Reduction_Cost.csv'):
        city = r['Region']; pol = r['Pollutant']
        try:
            v = float(r.get('Control_Cost(RMB)', 0) or 0)
        except (ValueError, TypeError):
            v = 0
        d.setdefault(city, {})[pol] = d.get(city, {}).get(pol, 0) + v
    cost_city[lbl] = d

# ---- 各城市效益（PM2.5 / O3）----
ben_city = {}
for lbl in si_names:
    d = {}
    for fname, key in [('PM25_BenMAP_apvrx.csv', 'PM2.5'), ('O3_BenMAP_apvrx.csv', 'O3')]:
        for r in readcsv(fname):
            if r.get('Case_Name', '').strip() == lbl:
                city = r['Name'].strip()
                if city == '100000':  # 全国汇总行
                    continue
                try:
                    v = float(r.get('PointEstimate', 0) or 0)
                except (ValueError, TypeError):
                    v = 0
                d.setdefault(city, {})[key] = d.get(city, {}).get(key, 0) + v
    ben_city[lbl] = d

# 城市 Top15（按总成本/总效益）
def top_cities(d, key_fn, n=15):
    return sorted(d.keys(), key=lambda c: key_fn(d[c]), reverse=True)[:n]

cost_city_data = {}
for lbl in si_names:
    cities = top_cities(cost_city[lbl], lambda dd: sum(dd.values()))
    cost_city_data[lbl] = [{'city': c, **{p: yi(cost_city[lbl][c].get(p, 0)) for p in POLS}} for c in cities]

ben_city_data = {}
for lbl in si_names:
    cities = top_cities(ben_city[lbl], lambda dd: sum(dd.values()))
    ben_city_data[lbl] = [{'city': c, 'PM2.5': yi(ben_city[lbl][c].get('PM2.5', 0)), 'O3': yi(ben_city[lbl][c].get('O3', 0))} for c in cities]

# ---- 各城市效益比 B/C（效益/成本）----
import re
def norm(c):
    return re.sub(r'(省|市|自治区|壮族|回族|维吾尔|特别行政区)', '', c)

bc_city_data = {}
for lbl in si_names:
    ben_map = {norm(c): c for c in ben_city[lbl]}  # 规范化效益城市名 → 原始
    rows = []
    for c_city, c_pols in cost_city[lbl].items():
        total_cost = sum(c_pols.values())
        if total_cost <= 0:
            continue
        b_city = ben_map.get(norm(c_city))
        if not b_city:
            continue
        pm_b = ben_city[lbl][b_city].get('PM2.5', 0)
        o3_b = ben_city[lbl][b_city].get('O3', 0)
        rows.append({
            'city': c_city,
            'bcPm': round(pm_b / total_cost, 3),
            'bcO3': round(o3_b / total_cost, 3),
            'bcAll': round((pm_b + o3_b) / total_cost, 3),
        })
    rows.sort(key=lambda r: r['bcAll'], reverse=True)
    bc_city_data[lbl] = rows[:15]

data = {
    'scenarios': si_names,
    'primary': primary,
    'aqb': {n: yi(float(si_map[n]['AQB_total'])) for n in si_names},
    'crb': {n: yi(float(si_map[n]['CRB_total'])) for n in si_names},
    'bi': {n: yi(float(si_map[n]['BI_total'])) for n in si_names},
    'si': {n: round(float(si_map[n]['SI_measure']), 4) for n in si_names},
    'pmBenefit': {n: yi(pm_ben.get(n, 0)) for n in si_names},
    'o3Benefit': {n: yi(o3_ben.get(n, 0)) for n in si_names},
    'cost': {n: yi(costs[n]) for n in si_names},
    'bcPm': {n: round(bc_pm[n], 4) for n in si_names},
    'bcO3': {n: round(bc_o3[n], 4) for n in si_names},
    'costCity': cost_city_data,
    'benCity': ben_city_data,
    'bcCity': bc_city_data,
    'pols': POLS,
}

js_data = json.dumps(data, ensure_ascii=False)

html = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>全链条费效评估 - 本地可视化</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  body { font-family: 'Microsoft YaHei', sans-serif; margin: 0; background: #0f1923; color: #e0e6ed; }
  .header { padding: 20px 30px; background: #1a2a3a; border-bottom: 2px solid #2d4a63; }
  .header h1 { margin: 0; font-size: 22px; }
  .header p { margin: 6px 0 0; color: #8fa3b8; font-size: 13px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px 30px; }
  .card { background: #1a2a3a; border-radius: 8px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,.3); }
  .card h3 { margin: 0 0 10px; font-size: 15px; color: #7fd4ff; }
  .chart { width: 100%; height: 320px; }
  .chart.tall { height: 460px; }
  .stats { display: flex; gap: 20px; padding: 16px 30px 0; flex-wrap: wrap; }
  .stat { background: #1a2a3a; border-radius: 8px; padding: 12px 20px; min-width: 180px; }
  .stat .num { font-size: 26px; font-weight: bold; color: #ffd166; }
  .stat .lbl { font-size: 12px; color: #8fa3b8; }
  .tag { display:inline-block; background:#2d4a63; padding:2px 10px; border-radius:10px; margin-left:8px; font-size:12px; }
  select { background:#2d4a63; color:#e0e6ed; border:1px solid #3d5a73; padding:4px 8px; border-radius:4px; }
</style>
</head>
<body>
<div class="header">
  <h1>全链条费效评估 <span class="tag">China 全国</span></h1>
  <p>数据源：__SOURCE__ · 情景：__SCENARIOS__ · 目标污染物：PM2.5、O3</p>
</div>

<div class="stats" id="stats"></div>

<div class="grid">
  <div class="card"><h3>费效比 B/C（效益 / 成本，按污染物）</h3><div id="chartBc" class="chart"></div></div>
  <div class="card"><h3>减排成本（亿元）</h3><div id="chartCost" class="chart"></div></div>
  <div class="card"><h3>空气质量效益总量 AQB / 协同成本 CRB / 总效益 BI（亿元）</h3><div id="chartSi" class="chart"></div></div>
  <div class="card"><h3>健康效益货币化（PM2.5 / O3，亿元）</h3><div id="chartBen" class="chart"></div></div>
  <div class="card"><h3>各城市减排成本（按污染物，亿元）
    <select id="costCitySel"></select></h3><div id="chartCostCity" class="chart tall"></div></div>
  <div class="card"><h3>各城市健康效益（PM2.5 / O3，亿元）
    <select id="benCitySel"></select></h3><div id="chartBenCity" class="chart tall"></div></div>
  <div class="card"><h3>各城市效益比（B/C = 效益 / 成本）
    <select id="bcCitySel"></select></h3><div id="chartBcCity" class="chart tall"></div></div>
</div>

<script>
const DATA = __DATA__;
const scenarios = DATA.scenarios;
const colors = ['#7fd4ff', '#ffd166', '#6b8cff', '#ff8c6b', '#7dffa3'];

function baseChart(id) { return echarts.init(document.getElementById(id)); }
function barOpt(x, series, horizontal) {
  return {
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#e0e6ed' } },
    grid: { left: 60, right: 30, top: 40, bottom: 30 },
    xAxis: horizontal ? { type: 'value', axisLabel: { color: '#e0e6ed' } } : { type: 'category', data: x, axisLabel: { color: '#e0e6ed' } },
    yAxis: horizontal ? { type: 'category', data: x, axisLabel: { color: '#e0e6ed' } } : { type: 'value', axisLabel: { color: '#e0e6ed' } },
    series: series.map(s => ({
      name: s.name, type: 'bar', stack: s.stack || undefined,
      data: s.data, itemStyle: { color: s.color },
      label: { show: s.showLabel, position: 'right', color: '#e0e6ed' }
    }))
  };
}

// 1. 费效比
baseChart('chartBc').setOption(barOpt(scenarios, [
  { name: 'PM2.5 B/C', data: scenarios.map(s => DATA.bcPm[s]), color: '#7fd4ff' },
  { name: 'O3 B/C', data: scenarios.map(s => DATA.bcO3[s]), color: '#ffd166' }
]));

// 2. 成本
baseChart('chartCost').setOption(barOpt(scenarios, [
  { name: '成本(亿)', data: scenarios.map(s => DATA.cost[s]), color: '#ff8c6b' }
]));

// 3. AQB/CRB/BI
baseChart('chartSi').setOption(barOpt(scenarios, [
  { name: 'AQB', data: scenarios.map(s => DATA.aqb[s]), color: '#7fd4ff' },
  { name: 'CRB', data: scenarios.map(s => DATA.crb[s]), color: '#ffd166' },
  { name: 'BI', data: scenarios.map(s => DATA.bi[s]), color: '#7dffa3' }
]));

// 4. 健康效益
baseChart('chartBen').setOption(barOpt(scenarios, [
  { name: 'PM2.5', data: scenarios.map(s => DATA.pmBenefit[s]), color: '#7fd4ff' },
  { name: 'O3', data: scenarios.map(s => DATA.o3Benefit[s]), color: '#ffd166' }
]));

// 5. 各城市成本（按污染物堆叠，横向）
const costCityChart = baseChart('chartCostCity');
const costCitySel = document.getElementById('costCitySel');
scenarios.forEach(s => { const o = document.createElement('option'); o.value = s; o.text = s; costCitySel.appendChild(o); });
function renderCostCity() {
  const s = costCitySel.value;
  const rows = DATA.costCity[s];
  const cities = rows.map(r => r.city).reverse();
  costCityChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#e0e6ed' } },
    grid: { left: 100, right: 40, top: 20, bottom: 30 },
    xAxis: { type: 'value', axisLabel: { color: '#e0e6ed' } },
    yAxis: { type: 'category', data: cities, axisLabel: { color: '#e0e6ed' } },
    series: DATA.pols.map((p, i) => ({
      name: p, type: 'bar', stack: 'total', data: rows.map(r => r[p]).reverse(),
      itemStyle: { color: colors[i] }
    }))
  }, true);
}
costCitySel.onchange = renderCostCity;

// 6. 各城市效益（PM2.5 / O3，横向）
const benCityChart = baseChart('chartBenCity');
const benCitySel = document.getElementById('benCitySel');
scenarios.forEach(s => { const o = document.createElement('option'); o.value = s; o.text = s; benCitySel.appendChild(o); });
function renderBenCity() {
  const s = benCitySel.value;
  const rows = DATA.benCity[s];
  const cities = rows.map(r => r.city).reverse();
  benCityChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#e0e6ed' } },
    grid: { left: 100, right: 40, top: 20, bottom: 30 },
    xAxis: { type: 'value', axisLabel: { color: '#e0e6ed' } },
    yAxis: { type: 'category', data: cities, axisLabel: { color: '#e0e6ed' } },
    series: [
      { name: 'PM2.5', type: 'bar', data: rows.map(r => r['PM2.5']).reverse(), itemStyle: { color: '#7fd4ff' } },
      { name: 'O3', type: 'bar', data: rows.map(r => r['O3']).reverse(), itemStyle: { color: '#ffd166' } }
    ]
  }, true);
}
benCitySel.onchange = renderBenCity;

// 7. 各城市效益比 B/C
const bcCityChart = baseChart('chartBcCity');
const bcCitySel = document.getElementById('bcCitySel');
scenarios.forEach(s => { const o = document.createElement('option'); o.value = s; o.text = s; bcCitySel.appendChild(o); });
function renderBcCity() {
  const s = bcCitySel.value;
  const rows = DATA.bcCity[s];
  const cities = rows.map(r => r.city).reverse();
  bcCityChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#e0e6ed' } },
    grid: { left: 100, right: 40, top: 20, bottom: 30 },
    xAxis: { type: 'value', axisLabel: { color: '#e0e6ed' } },
    yAxis: { type: 'category', data: cities, axisLabel: { color: '#e0e6ed' } },
    series: [
      { name: 'PM2.5 B/C', type: 'bar', data: rows.map(r => r.bcPm).reverse(), itemStyle: { color: '#7fd4ff' } },
      { name: 'O3 B/C', type: 'bar', data: rows.map(r => r.bcO3).reverse(), itemStyle: { color: '#ffd166' } }
    ]
  }, true);
}
bcCitySel.onchange = renderBcCity;

renderCostCity();
renderBenCity();
renderBcCity();

// 顶部统计卡
const stats = document.getElementById('stats');
scenarios.forEach(s => {
  const div = document.createElement('div'); div.className = 'stat';
  div.innerHTML = `<div class="lbl">${s} · PM2.5 费效比 B/C</div><div class="num">${DATA.bcPm[s]}</div>`;
  stats.appendChild(div);
});
scenarios.forEach(s => {
  const div = document.createElement('div'); div.className = 'stat';
  div.innerHTML = `<div class="lbl">${s} · 协同效益指数 SI</div><div class="num">${DATA.si[s]}</div>`;
  stats.appendChild(div);
});
</script>
</body>
</html>
"""

html = html.replace('__DATA__', js_data)
source_desc = _args.source or f'结果目录 {OUT}'
html = html.replace('__SOURCE__', source_desc)
html = html.replace('__SCENARIOS__', ' / '.join(si_names))
with open(out_html, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'✅ 已生成: {out_html}')
print(f'情景: {si_names}')
print(f'PM2.5 B/C: {data["bcPm"]}')
print(f'城市成本样例({si_names[0]}): {cost_city_data[si_names[0]][0] if cost_city_data[si_names[0]] else "无"}')
