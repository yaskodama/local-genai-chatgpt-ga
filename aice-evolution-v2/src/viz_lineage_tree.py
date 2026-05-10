"""Render an SVG lineage tree from a MAP-Elites lineage.json.

Layout:
  - x = generation (left to right)
  - y = stacked rank within the generation
  - nodes are coloured by operator (seed / axis_resample / crossover / ...)
  - edges from each parent to each child (so crossover individuals
    appear as join points with two incoming edges)

The output is a self-contained HTML file with inline SVG; opens in
any browser, no JS required.

Usage:
  /usr/bin/python3 -m src.viz_lineage_tree <lineage.json> <out.html>
"""

import json
import sys
from collections import defaultdict
from pathlib import Path


# Operator colour palette.  Real operator names from the lineage carry
# a "mutation:" or "crossover:" prefix and a sub-kind, so we match by
# substring rather than equality.
OP_COLORS_MAP = [
    ("seed",                       "#666666"),  # gen-0 random seeds
    ("axis_resample",              "#4f81bd"),  # single-axis mutation
    ("coherent_paradigm_shift",    "#9bbb59"),  # multi-axis mutation
    ("llm_new_axis",               "#c0504d"),  # LLM proposes a new axis
    ("llm_proposal",               "#8064a2"),  # LLM proposes a value
    ("uniform_crossover",          "#f79646"),  # 2-parent uniform XOR
    ("schema_partition_crossover", "#e6a160"),  # 2-parent partitioned XOR
    ("crossover",                  "#f79646"),  # generic crossover fallback
]


def color_for(op: str) -> str:
    if not op:
        return "#aaa"
    for needle, col in OP_COLORS_MAP:
        if needle in op:
            return col
    return "#aaa"


def render(lineage_path: str, out_path: str) -> None:
    data = json.loads(Path(lineage_path).read_text())
    by_id = {d["id"]: d for d in data}
    max_gen = max(d["generation"] for d in data)

    # Group by generation, then assign a per-generation y rank
    # in order of best -> worst composite.
    gen_buckets = defaultdict(list)
    for d in data:
        gen_buckets[d["generation"]].append(d)
    pos = {}
    max_rank = 0
    for g, xs in gen_buckets.items():
        xs.sort(key=lambda d: -d["composite"])
        for rank, d in enumerate(xs):
            pos[d["id"]] = (g, rank)
            max_rank = max(max_rank, rank)

    # SVG canvas geometry.
    col_w = 60
    row_h = 36
    pad_x = 80
    pad_y = 80
    width = pad_x * 2 + (max_gen + 1) * col_w
    height = pad_y * 2 + (max_rank + 1) * row_h

    def xy(node_id):
        g, r = pos[node_id]
        return (pad_x + g * col_w, pad_y + r * row_h)

    # Edges first (so they go behind nodes).
    edges = []
    for d in data:
        for p in d.get("parents", []) or []:
            if p in pos:
                x1, y1 = xy(p)
                x2, y2 = xy(d["id"])
                edges.append((x1, y1, x2, y2))

    # Build SVG body.
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" style="background:#fff">'
    ]

    # Generation guide-lines and labels.
    for g in range(max_gen + 1):
        x = pad_x + g * col_w
        svg_parts.append(
            f'<line x1="{x}" y1="{pad_y - 30}" x2="{x}" y2="{height - pad_y + 20}" '
            f'stroke="#eee" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="{x}" y="{pad_y - 38}" text-anchor="middle" '
            f'font-size="11" fill="#888">gen {g}</text>'
        )

    # Edges (behind).
    for x1, y1, x2, y2 in edges:
        # smooth bezier-ish horizontal path
        midx = (x1 + x2) / 2
        d = f"M {x1} {y1} C {midx} {y1}, {midx} {y2}, {x2} {y2}"
        svg_parts.append(f'<path d="{d}" stroke="#bbb" fill="none" stroke-width="1.2"/>')

    # Nodes.
    for d in data:
        x, y = xy(d["id"])
        op = d.get("operator", "?")
        color = color_for(op)
        # Node radius scaled mildly by composite (bigger = better).
        r = 7 + (d["composite"] - 0.55) * 14
        if r < 4:
            r = 4
        if r > 14:
            r = 14
        svg_parts.append(
            f'<circle cx="{x}" cy="{y}" r="{r:.1f}" fill="{color}" '
            f'stroke="#fff" stroke-width="1.5">'
            f'<title>{d["id"]} (gen {d["generation"]}, {op})\n'
            f'composite={d["composite"]:.3f}\n'
            f'cell={d.get("cell","?")}\n'
            f'parents={d.get("parents",[])}</title></circle>'
        )

    # Highlight best-fitness individual.
    best = max(data, key=lambda d: d["composite"])
    bx, by = xy(best["id"])
    svg_parts.append(
        f'<circle cx="{bx}" cy="{by}" r="18" fill="none" '
        f'stroke="#c0504d" stroke-width="2.5" stroke-dasharray="4,3"/>'
    )

    svg_parts.append('</svg>')

    # Legend (shows operators that actually appeared, with full names).
    seen_ops = sorted({d.get("operator", "?") for d in data})
    legend_html = '<div class="legend">'
    for op in seen_ops:
        legend_html += (f'<span class="lg"><span class="dot" '
                        f'style="background:{color_for(op)}"></span>{op}</span>')
    legend_html += '</div>'

    name = Path(lineage_path).stem.replace(".lineage", "")

    html = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>{name} — lineage tree</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue",
                       "Hiragino Sans", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif;
          margin: 24px; color: #222; }}
  h1 {{ font-size: 22px; }}
  .meta {{ font-size: 13px; color: #555; margin-bottom: 10px; }}
  .legend {{ font-size: 12px; margin: 12px 0 16px 0; }}
  .lg {{ display: inline-block; margin-right: 14px; white-space: nowrap; }}
  .dot {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%;
         margin-right: 4px; vertical-align: middle; }}
  .scroll {{ overflow-x: auto; border: 1px solid #e0e0e0; border-radius: 6px; padding: 4px; }}
  .note {{ font-size: 12px; color: #777; margin-top: 6px; }}
</style>
</head>
<body>
<h1>{name} — 系統樹 (lineage tree)</h1>
<p class="meta">
  個体 {len(data)} / 世代 0–{max_gen} / セル {len({d.get("cell") for d in data})} 種.
  各ノードはホバーで詳細表示. 大きさ ∝ composite fitness.
  破線円は最高 fitness 個体.
</p>
{legend_html}
<div class="scroll">
{"".join(svg_parts)}
</div>
<p class="note">
  矢印の集約 (1 ノードに複数の入力エッジ) は crossover 個体を意味します.
  分岐 (1 ノードから複数の出力エッジ) は 1 親が複数の子に派生したことを意味します.
</p>
</body>
</html>
"""
    Path(out_path).write_text(html)
    print(f"wrote {out_path}  ({len(html)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: viz_lineage_tree.py <lineage.json> <out.html>", file=sys.stderr)
        sys.exit(2)
    render(sys.argv[1], sys.argv[2])
