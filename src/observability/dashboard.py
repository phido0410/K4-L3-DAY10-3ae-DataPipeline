from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_text

RATIO_METRICS = [
    ("retrieval_hit_rate", "Retrieval Hit Rate"),
    ("mean_token_f1", "Mean Token F1"),
    ("judge_accuracy", "LLM Judge Accuracy"),
]
BIN_DAYS = 30


def _load(path: Path) -> Any:
    return read_json(path) if path.exists() else None


def _states(settings: Settings) -> list[dict[str, Any]]:
    paths = settings.paths
    specs = [
        ("baseline", "Baseline", paths.baseline_metrics, paths.baseline_answers,
         paths.baseline_quality_report, paths.freshness_report, paths.clean_json),
        ("corrupted", "Corrupted", paths.corrupted_metrics, paths.corrupted_answers,
         paths.corrupted_quality_report, paths.quality_dir / "corrupted_freshness_report.json",
         paths.corrupted_clean_json),
        ("repaired", "Repaired", paths.repaired_metrics, paths.repaired_answers,
         paths.quality_dir / "repaired_quality_report.json", paths.quality_dir / "repaired_freshness_report.json",
         paths.repaired_clean_json),
    ]
    return [
        {
            "key": key,
            "label": label,
            "metrics": _load(metrics),
            "answers": _load(answers) or [],
            "quality": _load(quality),
            "freshness": _load(freshness),
            "rows": _load(clean) or [],
        }
        for key, label, metrics, answers, quality, freshness, clean in specs
    ]


def _pct(value: Any) -> str:
    return f"{value:.1%}" if isinstance(value, (int, float)) else "n/a"


def _status(ok: Any, good: str, bad: str) -> str:
    if ok is None:
        return '<span class="badge badge-none">– chưa chạy</span>'
    if ok:
        return f'<span class="badge badge-good">✓ {escape(good)}</span>'
    return f'<span class="badge badge-bad">✕ {escape(bad)}</span>'


def _tiles(states: list[dict[str, Any]]) -> str:
    cards = []
    for state in states:
        metrics, quality, freshness = state["metrics"] or {}, state["quality"] or {}, state["freshness"] or {}
        passed = quality.get("successful_expectations")
        total = quality.get("evaluated_expectations")
        cards.append(
            f"""
      <article class="card tile">
        <h3><span class="swatch s-{state['key']}"></span>{state['label']}</h3>
        <div class="hero">{_pct(metrics.get('mean_token_f1'))}<small>Token F1</small></div>
        <dl>
          <dt>Hit Rate</dt><dd>{_pct(metrics.get('retrieval_hit_rate'))}</dd>
          <dt>Quality Gate</dt><dd>{_status(quality.get('success') if quality else None, 'PASS', 'FAIL')}
            <span class="muted">{passed if passed is not None else '–'}/{total if total is not None else '–'}</span></dd>
          <dt>Freshness</dt><dd>{_status(freshness.get('is_fresh') if freshness else None, 'Fresh', 'Stale')}
            <span class="muted">{_pct(freshness.get('stale_ratio'))} stale</span></dd>
          <dt>Số dòng</dt><dd>{freshness.get('total_rows', '–')}</dd>
        </dl>
      </article>"""
        )
    return '<div class="tiles">' + "".join(cards) + "</div>"


def _metrics_chart(states: list[dict[str, Any]]) -> str:
    groups = []
    for key, label in RATIO_METRICS:
        rows = []
        for state in states:
            value = (state["metrics"] or {}).get(key)
            if not isinstance(value, (int, float)):
                continue
            rows.append(
                f'<div class="bar-row" title="{state["label"]} – {escape(label)}: {value:.1%}">'
                f'<div class="track"><div class="bar bg-{state["key"]}" style="width:{max(value, 0.005):.1%}"></div></div>'
                f'<span class="value">{value:.0%}</span></div>'
            )
        groups.append(f'<div class="metric"><div class="metric-name">{escape(label)}</div><div>{"".join(rows)}</div></div>')
    ticks = "".join(f"<span>{t}</span>" for t in ("0%", "25%", "50%", "75%", "100%"))
    rows = "".join(
        f"<tr><td>{escape(label)}</td>"
        + "".join(f"<td>{_pct((s['metrics'] or {}).get(key))}</td>" for s in states)
        + "</tr>"
        for key, label in RATIO_METRICS
    )
    judge_row = "<tr><td>Mean Judge Score (1–5)</td>" + "".join(
        f"<td>{(s['metrics'] or {}).get('mean_judge_score', 'n/a')}</td>" for s in states
    ) + "</tr>"
    head = "".join(f"<th>{s['label']}</th>" for s in states)
    return (
        f'<div class="bars" role="img" aria-label="So sánh metric 3 trạng thái">{"".join(groups)}'
        f'<div class="metric"><div></div><div class="ticks">{ticks}</div></div></div>'
        f'<details><summary>Xem dạng bảng</summary><div class="table-wrap"><table><thead><tr><th>Metric</th>{head}</tr></thead>'
        f"<tbody>{rows}{judge_row}</tbody></table></div></details>"
    )


def _age_histogram(state: dict[str, Any], threshold: int, max_age: int) -> str:
    ages = [int(row["age_days"]) for row in state["rows"] if isinstance(row.get("age_days"), (int, float))]
    width, height, pad_l, pad_b, pad_t = 300, 150, 28, 22, 14
    plot_w, plot_h = width - pad_l - 8, height - pad_b - pad_t
    bins = max(1, -(-max_age // BIN_DAYS))
    counts = [0] * bins
    for age in ages:
        counts[min(age // BIN_DAYS, bins - 1)] += 1
    peak = max(counts + [1])
    slot = plot_w / bins
    bar_w = min(slot - 2, 24)
    marks = []
    for index, count in enumerate(counts):
        if not count:
            continue
        h = count / peak * plot_h
        x = pad_l + index * slot + (slot - bar_w) / 2
        lo, hi = index * BIN_DAYS, (index + 1) * BIN_DAYS - 1
        marks.append(
            f'<g class="mark"><title>{lo}–{hi} ngày: {count} bài</title>'
            f'<rect class="fill-{state["key"]}" x="{x:.1f}" y="{pad_t + plot_h - h:.1f}" width="{bar_w:.1f}" height="{h:.1f}" rx="2"/></g>'
        )
    tx = pad_l + threshold / (bins * BIN_DAYS) * plot_w
    stale = sum(age > threshold for age in ages)
    ratio = stale / len(ages) if ages else 0
    return f"""
      <figure class="card">
        <figcaption><span class="swatch s-{state['key']}"></span>{state['label']}
          <span class="muted">· {stale}/{len(ages)} bài quá hạn ({ratio:.1%})</span></figcaption>
        <svg viewBox="0 0 {width} {height}" role="img" aria-label="Phân bố age_days – {state['label']}">
          <rect class="stale-zone" x="{tx:.1f}" y="{pad_t}" width="{pad_l + plot_w - tx:.1f}" height="{plot_h}"/>
          <line class="baseline" x1="{pad_l}" x2="{pad_l + plot_w}" y1="{pad_t + plot_h}" y2="{pad_t + plot_h}"/>
          {''.join(marks)}
          <line class="threshold" x1="{tx:.1f}" x2="{tx:.1f}" y1="{pad_t - 6}" y2="{pad_t + plot_h}"/>
          <text class="tick" x="{tx + 4:.1f}" y="{pad_t - 2}">SLA {threshold} ngày</text>
          <text class="tick" x="{pad_l}" y="{height - 6}">0</text>
          <text class="tick" x="{pad_l + plot_w}" y="{height - 6}" text-anchor="end">{bins * BIN_DAYS} ngày</text>
          <text class="tick" x="{pad_l - 6}" y="{pad_t + 4}" text-anchor="end">{peak}</text>
        </svg>
      </figure>"""


def _freshness_section(states: list[dict[str, Any]], threshold: int) -> str:
    all_ages = [int(r["age_days"]) for s in states for r in s["rows"] if isinstance(r.get("age_days"), (int, float))]
    max_age = max(all_ages + [threshold + BIN_DAYS])
    return '<div class="multiples">' + "".join(_age_histogram(s, threshold, max_age) for s in states) + "</div>"


def _gx_table(states: list[dict[str, Any]]) -> str:
    names: list[str] = []
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for state in states:
        for item in (state["quality"] or {}).get("results", []):
            name = item["expectation"] + (f"({item['column']})" if item.get("column") else "")
            if name not in names:
                names.append(name)
            lookup[(state["key"], name)] = item
    rows = []
    for name in names:
        cells = []
        for state in states:
            item = lookup.get((state["key"], name))
            if item is None:
                cells.append("<td>–</td>")
                continue
            detail = item.get("unexpected_count", item.get("observed_value", ""))
            cells.append(f"<td>{_status(item['success'], 'PASS', 'FAIL')} <span class='muted'>{escape(str(detail))}</span></td>")
        rows.append(f"<tr><td><code>{escape(name)}</code></td>{''.join(cells)}</tr>")
    head = "".join(f"<th>{s['label']}</th>" for s in states)
    return f"<table><thead><tr><th>Expectation</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _corruption_table(log: dict[str, Any] | None) -> str:
    if not log:
        return '<p class="muted">Chưa có corruption log.</p>'
    rows = "".join(
        f"<tr><td><code>{escape(item['type'])}</code></td><td class='num'>{item['affected_rows']}</td>"
        f"<td>{escape(item['description'])}</td></tr>"
        for item in log.get("corruptions", [])
    )
    return (
        f"<p class='muted'>{log.get('rows_before')} → {log.get('rows_after')} dòng · seed {log.get('seed')}</p>"
        f"<table><thead><tr><th>Loại lỗi</th><th>Số dòng</th><th>Mô tả</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _question_grid(states: list[dict[str, Any]]) -> str:
    by_state = {s["key"]: {a["id"]: a for a in s["answers"]} for s in states}
    reference = next((s["answers"] for s in states if s["answers"]), [])
    rows = []
    for question in reference:
        cells = []
        for state in states:
            answer = by_state[state["key"]].get(question["id"])
            if answer is None:
                cells.append("<td>–</td>")
                continue
            correct = answer["judge"]["correct"] and answer["token_f1"] > 0
            flag = ""
            if answer["judge"]["correct"] and not answer["answer"].strip():
                flag = ' <span class="flag" title="Judge chấm đúng nhưng câu trả lời rỗng">⚠ judge sai</span>'
            miss = "" if answer["retrieval_hit"] else ' <span class="muted">(miss)</span>'
            tooltip = escape(f"Trả lời: {answer['answer'] or '(rỗng)'}\nĐáp án: {answer['ground_truth']}")
            cells.append(
                f'<td class="{"cell-good" if correct else "cell-bad"}" title="{tooltip}">'
                f'{"✓" if correct else "✕"} F1 {answer["token_f1"]:.2f} · J {answer["judge"]["score"]}{miss}{flag}</td>'
            )
        rows.append(
            f"<tr><td><code>{question['id']}</code></td><td>{escape(question['question_type'])}</td>{''.join(cells)}</tr>"
        )
    head = "".join(f"<th>{s['label']}</th>" for s in states)
    return (
        f"<table class='grid-table'><thead><tr><th>Câu</th><th>Loại</th>{head}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


STYLE = """
:root { color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10);
  --s-baseline:#2a78d6; --s-corrupted:#eb6834; --s-repaired:#1baf7a;
  --good:#0ca30c; --good-ink:#006300; --bad:#d03b3b; --good-bg:rgba(12,163,12,.10); --bad-bg:rgba(208,59,59,.10);
  --stale-zone:rgba(208,59,59,.07); }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --s-baseline:#3987e5; --s-corrupted:#d95926; --s-repaired:#199e70;
  --good-ink:#0ca30c; --good-bg:rgba(12,163,12,.16); --bad-bg:rgba(208,59,59,.18); --stale-zone:rgba(208,59,59,.12); } }
:root[data-theme="dark"] { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --s-baseline:#3987e5; --s-corrupted:#d95926; --s-repaired:#199e70;
  --good-ink:#0ca30c; --good-bg:rgba(12,163,12,.16); --bad-bg:rgba(208,59,59,.18); --stale-zone:rgba(208,59,59,.12); }
* { box-sizing:border-box; }
body { margin:0; background:var(--page); color:var(--ink); font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1080px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:16px; margin:32px 0 12px; } h3 { font-size:14px; margin:0 0 8px; }
.muted { color:var(--muted); } code { font-size:12px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px 16px; margin:0; }
.tiles, .multiples { display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); }
.hero { font-size:30px; font-weight:600; } .hero small { font-size:12px; font-weight:400; color:var(--ink-2); margin-left:6px; }
dl { display:grid; grid-template-columns:auto 1fr; gap:4px 12px; margin:8px 0 0; } dt { color:var(--ink-2); } dd { margin:0; }
.swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; vertical-align:baseline; }
.s-baseline { background:var(--s-baseline); } .s-corrupted { background:var(--s-corrupted); } .s-repaired { background:var(--s-repaired); }
.bg-baseline { background:var(--s-baseline); } .bg-corrupted { background:var(--s-corrupted); } .bg-repaired { background:var(--s-repaired); }
.bars { display:grid; gap:14px; }
.metric { display:grid; grid-template-columns:minmax(110px,160px) 1fr; gap:4px 12px; align-items:center; }
.metric-name { color:var(--ink-2); font-size:13px; }
.bar-row { display:flex; align-items:center; gap:8px; margin:2px 0; }
.track { flex:1; height:10px; background:repeating-linear-gradient(to right, var(--grid) 0 1px, transparent 1px 25%); }
.bar { height:10px; border-radius:0 4px 4px 0; } .bar-row:hover .bar { opacity:.8; }
.value { width:36px; font-size:12px; font-variant-numeric:tabular-nums; }
.ticks { display:flex; justify-content:space-between; color:var(--muted); font-size:11px; margin-right:44px; }
.fill-baseline { fill:var(--s-baseline); } .fill-corrupted { fill:var(--s-corrupted); } .fill-repaired { fill:var(--s-repaired); }
.badge { font-weight:600; white-space:nowrap; } .badge-good { color:var(--good-ink); } .badge-bad { color:var(--bad); } .badge-none { color:var(--muted); }
.legend { display:flex; gap:16px; flex-wrap:wrap; color:var(--ink-2); margin-bottom:8px; }
.chart svg, figure svg { width:100%; height:auto; display:block; overflow:visible; }
svg text { font-family:inherit; } .axis-label { fill:var(--ink-2); font-size:12px; } .value { fill:var(--ink); font-size:11px; }
.tick { fill:var(--muted); font-size:10px; } .grid { stroke:var(--grid); stroke-width:1; } .baseline { stroke:var(--axis); stroke-width:1; }
.threshold { stroke:var(--bad); stroke-width:1.5; stroke-dasharray:4 3; } .stale-zone { fill:var(--stale-zone); }
.mark:hover rect { opacity:.8; }
figcaption { font-weight:600; margin-bottom:6px; }
.table-wrap { overflow-x:auto; }
table { border-collapse:collapse; width:100%; background:var(--surface); border:1px solid var(--border); border-radius:10px; overflow:hidden; }
th, td { text-align:left; padding:7px 10px; border-bottom:1px solid var(--grid); vertical-align:top; font-variant-numeric:tabular-nums; }
th { color:var(--ink-2); font-weight:600; font-size:12px; } td.num { text-align:right; }
.cell-good { background:var(--good-bg); } .cell-bad { background:var(--bad-bg); }
.flag { color:var(--bad); font-size:11px; font-weight:600; white-space:nowrap; }
details { margin-top:8px; } summary { cursor:pointer; color:var(--ink-2); }
"""


def render_dashboard(settings: Settings) -> str:
    states = _states(settings)
    baseline_quality = states[0]["quality"] or {}
    engine = escape(str(baseline_quality.get("engine", "great_expectations")))
    legend = "".join(f'<span><span class="swatch s-{s["key"]}"></span>{s["label"]}</span>' for s in states)
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data Observability Dashboard</title>
<style>{STYLE}</style>
</head>
<body>
<main>
  <h1>Data Observability Dashboard</h1>
  <p class="muted">Nhóm 3ae · Crossref RAG pipeline · {engine} · sinh lúc {now_utc().isoformat(timespec="seconds")} từ artifact trong <code>data/</code></p>

  <h2>1. Trạng thái 3 phiên bản dữ liệu</h2>
  {_tiles(states)}

  <h2>2. Chất lượng RAG: Baseline vs Corrupted vs Repaired</h2>
  <div class="card"><div class="legend">{legend}</div>{_metrics_chart(states)}</div>

  <h2>3. Freshness SLA: phân bố tuổi bài báo (age_days)</h2>
  <p class="muted">Vùng tô đỏ là bài quá {settings.freshness_threshold_days} ngày; dữ liệu stale khi tỷ lệ này vượt 25%.</p>
  {_freshness_section(states, settings.freshness_threshold_days)}

  <h2>4. Quality Gate (Great Expectations 1.x)</h2>
  <div class="table-wrap">{_gx_table(states)}</div>

  <h2>5. Corruption log</h2>
  <div class="table-wrap">{_corruption_table(_load(settings.paths.corruption_log))}</div>

  <h2>6. Kết quả từng câu hỏi</h2>
  <p class="muted">✓ = judge chấm đúng và Token F1 &gt; 0 · J = điểm judge (1–5) · rê chuột để xem câu trả lời.</p>
  <div class="table-wrap">{_question_grid(states)}</div>
</main>
</body>
</html>
"""


def build_dashboard(settings: Settings, output_path: Path | None = None) -> Path:
    path = output_path or settings.paths.project_dir / "data" / "reports" / "dashboard.html"
    write_text(path, render_dashboard(settings))
    return path


def main() -> None:
    path = build_dashboard(load_settings())
    print(f"Dashboard -> {path}")
