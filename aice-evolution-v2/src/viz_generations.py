"""Render an HTML visualization of MAP-Elites lineage progression.

Reads <name>.lineage.json + <name>.elite_map.json and emits a
self-contained HTML file with Chart.js (CDN) charts:

  1. Best / mean / worst composite per generation (line)
  2. Cumulative cells filled per generation (line)
  3. New cells per generation (bar)
  4. Operator breakdown per generation (stacked bar)
  5. Top elites table (sortable by composite)

Usage:
  /usr/bin/python3 -m src.viz_generations <lineage.json> <out.html>
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def render(lineage_path: str, out_path: str) -> None:
    data = json.loads(Path(lineage_path).read_text())
    gens = sorted({d["generation"] for d in data})
    max_gen = max(gens)

    # Aggregate per-generation stats.
    fits_by_gen = defaultdict(list)
    op_count_by_gen = defaultdict(Counter)
    cells_seen = set()
    new_cells_by_gen = defaultdict(int)
    cum_cells = []

    for d in sorted(data, key=lambda x: (x["generation"], x["id"])):
        g = d["generation"]
        fits_by_gen[g].append(d["composite"])
        op_count_by_gen[g][d.get("operator", "?")] += 1
        cell = d.get("cell", "?")
        if cell not in cells_seen:
            cells_seen.add(cell)
            new_cells_by_gen[g] += 1

    running = 0
    for g in range(max_gen + 1):
        running += new_cells_by_gen.get(g, 0)
        cum_cells.append(running)

    best = [max(fits_by_gen.get(g, [None]) or [None]) if fits_by_gen.get(g) else None
            for g in range(max_gen + 1)]
    mean = [sum(fits_by_gen[g]) / len(fits_by_gen[g]) if fits_by_gen.get(g) else None
            for g in range(max_gen + 1)]
    worst = [min(fits_by_gen.get(g, [None]) or [None]) if fits_by_gen.get(g) else None
             for g in range(max_gen + 1)]
    new_cells = [new_cells_by_gen.get(g, 0) for g in range(max_gen + 1)]

    operators = sorted({op for c in op_count_by_gen.values() for op in c})
    op_series = {op: [op_count_by_gen[g].get(op, 0) for g in range(max_gen + 1)]
                 for op in operators}

    # Top elites for the bottom table.
    elites = sorted(data, key=lambda d: -d["composite"])[:10]

    name = Path(lineage_path).stem  # e.g. AIPLSelfHost_A_Metacircular.lineage
    name = name.replace(".lineage", "")

    # Compose HTML.
    op_palette = ["#4f81bd", "#c0504d", "#9bbb59", "#8064a2", "#4bacc6",
                  "#f79646", "#2c4d75", "#772c2a", "#5f7530", "#4d3b62"]

    html = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>{name} — MAP-Elites generations</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue",
                       "Hiragino Sans", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif;
          margin: 24px; color: #222; max-width: 1080px; }}
  h1 {{ font-size: 22px; }}
  h2 {{ font-size: 17px; margin-top: 28px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }}
  .grid > div {{ background: #fafafa; border: 1px solid #e0e0e0; border-radius: 6px; padding: 10px; }}
  table {{ border-collapse: collapse; font-size: 13px; width: 100%; margin-top: 12px; }}
  th, td {{ border: 1px solid #ddd; padding: 5px 8px; text-align: left; vertical-align: top; }}
  th {{ background: #eef2f7; }}
  td.num {{ font-variant-numeric: tabular-nums; text-align: right; }}
  .meta {{ font-size: 13px; color: #555; margin-top: 4px; }}
  .badge {{ display: inline-block; padding: 1px 6px; border-radius: 3px;
            background: #eee; margin-right: 4px; font-size: 11px; }}
  canvas {{ max-height: 280px; }}
</style>
</head>
<body>

<h1>{name} — MAP-Elites 世代進行</h1>
<div class="meta">
  <span class="badge">individuals: {len(data)}</span>
  <span class="badge">max generation: {max_gen}</span>
  <span class="badge">cells filled: {len(cells_seen)}</span>
  <span class="badge">operators: {", ".join(operators)}</span>
</div>

<div class="grid">
  <div>
    <h2>composite fitness 推移</h2>
    <canvas id="fitChart"></canvas>
  </div>
  <div>
    <h2>累積セル数</h2>
    <canvas id="cellsChart"></canvas>
  </div>
  <div>
    <h2>世代ごとに新規発見セル</h2>
    <canvas id="newCellsChart"></canvas>
  </div>
  <div>
    <h2>operator 内訳 (世代別)</h2>
    <canvas id="opChart"></canvas>
  </div>
</div>

<h2>top elites</h2>
<table>
  <thead><tr>
    <th>#</th><th>id</th><th>gen</th><th>composite</th><th>cell</th><th>operator</th>
  </tr></thead>
  <tbody>
"""
    for i, e in enumerate(elites, 1):
        html += (f'    <tr><td>{i}</td><td>{e["id"]}</td><td class="num">{e["generation"]}</td>'
                 f'<td class="num">{e["composite"]:.3f}</td><td>{e.get("cell","?")}</td>'
                 f'<td>{e.get("operator","?")}</td></tr>\n')

    op_datasets = ",\n".join(
        f"        {{ label: {json.dumps(op)}, data: {op_series[op]}, "
        f"backgroundColor: {json.dumps(op_palette[i % len(op_palette)])}, stack: 's' }}"
        for i, op in enumerate(operators)
    )

    labels = list(range(max_gen + 1))

    html += f"""  </tbody>
</table>

<script>
const labels = {labels};

new Chart(document.getElementById('fitChart'), {{
  type: 'line',
  data: {{
    labels: labels,
    datasets: [
      {{ label: 'best',  data: {best},  borderColor: '#c0504d', tension: 0.2 }},
      {{ label: 'mean',  data: {mean},  borderColor: '#4f81bd', tension: 0.2 }},
      {{ label: 'worst', data: {worst}, borderColor: '#9bbb59', tension: 0.2 }}
    ]
  }},
  options: {{ responsive: true, scales: {{ y: {{ beginAtZero: false }} }} }}
}});

new Chart(document.getElementById('cellsChart'), {{
  type: 'line',
  data: {{
    labels: labels,
    datasets: [
      {{ label: 'cumulative cells', data: {cum_cells},
        borderColor: '#8064a2', backgroundColor: 'rgba(128,100,162,0.2)',
        fill: true, tension: 0.1 }}
    ]
  }},
  options: {{ responsive: true, scales: {{ y: {{ beginAtZero: true }} }} }}
}});

new Chart(document.getElementById('newCellsChart'), {{
  type: 'bar',
  data: {{
    labels: labels,
    datasets: [{{ label: 'new cells', data: {new_cells}, backgroundColor: '#4bacc6' }}]
  }},
  options: {{ responsive: true, scales: {{ y: {{ beginAtZero: true, ticks: {{ stepSize: 1 }} }} }} }}
}});

new Chart(document.getElementById('opChart'), {{
  type: 'bar',
  data: {{
    labels: labels,
    datasets: [
{op_datasets}
    ]
  }},
  options: {{ responsive: true,
    scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, beginAtZero: true,
                                              ticks: {{ stepSize: 1 }} }} }} }}
}});
</script>

</body>
</html>
"""
    Path(out_path).write_text(html)
    print(f"wrote {out_path}  ({len(html)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: viz_generations.py <lineage.json> <out.html>", file=sys.stderr)
        sys.exit(2)
    render(sys.argv[1], sys.argv[2])
