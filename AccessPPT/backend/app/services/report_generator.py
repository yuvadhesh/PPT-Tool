"""
Report generator service.
"""
import json
import csv
import io
from typing import Any


def generate_report_data(pres, issues: list) -> dict:
    """Build report data dict from presentation and issues."""
    by_severity = {"error": [], "warning": [], "review": [], "pass": []}
    by_category: dict[str, list] = {}

    for issue in issues:
        by_severity.get(issue.severity, []).append(issue)
        by_category.setdefault(issue.category, []).append(issue)

    return {
        "filename": pres.original_filename,
        "slide_count": pres.slide_count or 0,
        "accessibility_score": pres.accessibility_score or 0,
        "error_count": pres.error_count,
        "warning_count": pres.warning_count,
        "review_count": pres.review_count,
        "pass_count": pres.pass_count,
        "by_severity": {k: [_issue_to_dict(i) for i in v] for k, v in by_severity.items()},
        "by_category": {k: [_issue_to_dict(i) for i in v] for k, v in by_category.items()},
        "total_issues": len(issues),
        "generated_at": pres.updated_at.isoformat() if pres.updated_at else "",
    }


def _issue_to_dict(issue) -> dict:
    return {
        "id": issue.id,
        "rule_id": issue.rule_id,
        "category": issue.category,
        "severity": issue.severity,
        "title": issue.title,
        "description": issue.description,
        "recommendation": issue.recommendation,
        "auto_fix_supported": issue.auto_fix_supported,
        "ai_suggestion": issue.ai_suggestion,
        "ai_confidence": issue.ai_confidence,
        "status": issue.status,
    }


def render_report(data: dict, format: str) -> tuple[bytes, str]:
    """Render report in given format, return (bytes, content_type)."""
    if format == "json":
        content = json.dumps(data, indent=2, default=str).encode("utf-8")
        return content, "application/json"

    elif format == "html":
        html = _render_html(data)
        return html.encode("utf-8"), "text/html"

    elif format == "csv":
        content = _render_csv(data)
        return content, "text/csv"

    else:
        content = json.dumps(data, indent=2, default=str).encode("utf-8")
        return content, "application/json"


def _render_html(data: dict) -> str:
    score = data["accessibility_score"]
    score_color = "#22c55e" if score >= 80 else "#f59e0b" if score >= 60 else "#ef4444"

    issue_rows = ""
    for sev, issues in data["by_severity"].items():
        for issue in issues:
            issue_rows += f"""
            <tr>
                <td><span class="badge badge-{sev}">{sev.upper()}</span></td>
                <td>{issue['rule_id']}</td>
                <td>{issue['title']}</td>
                <td>{issue['description']}</td>
                <td>{issue.get('ai_suggestion') or '—'}</td>
            </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Accessibility Report — {data['filename']}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1100px; margin: 0 auto; padding: 2rem; color: #18181b; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
  .score {{ font-size: 3rem; font-weight: 700; color: {score_color}; }}
  .meta {{ color: #71717a; font-size: 0.875rem; margin-bottom: 2rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }}
  .card {{ border: 1px solid #e4e4e7; border-radius: 8px; padding: 1rem; }}
  .card-label {{ font-size: 0.75rem; color: #71717a; text-transform: uppercase; letter-spacing: 0.05em; }}
  .card-value {{ font-size: 1.5rem; font-weight: 700; margin-top: 0.25rem; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 0.75rem; border-bottom: 1px solid #e4e4e7; font-size: 0.875rem; }}
  th {{ font-weight: 600; color: #71717a; }}
  .badge {{ padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
  .badge-error {{ background: #fef2f2; color: #dc2626; }}
  .badge-warning {{ background: #fffbeb; color: #d97706; }}
  .badge-review {{ background: #eff6ff; color: #2563eb; }}
  .badge-pass {{ background: #f0fdf4; color: #16a34a; }}
</style>
</head>
<body>
<h1>Accessibility Report</h1>
<p class="meta">{data['filename']} • {data['slide_count']} slides • Generated {data['generated_at']}</p>
<div class="score">{score:.0f}<span style="font-size:1.5rem;color:#71717a">/100</span></div>
<div class="grid">
  <div class="card"><div class="card-label">Errors</div><div class="card-value" style="color:#dc2626">{data['error_count']}</div></div>
  <div class="card"><div class="card-label">Warnings</div><div class="card-value" style="color:#d97706">{data['warning_count']}</div></div>
  <div class="card"><div class="card-label">Review</div><div class="card-value" style="color:#2563eb">{data['review_count']}</div></div>
  <div class="card"><div class="card-label">Passed</div><div class="card-value" style="color:#16a34a">{data['pass_count']}</div></div>
</div>
<h2>Issues</h2>
<table>
<thead><tr><th>Severity</th><th>Rule</th><th>Issue</th><th>Description</th><th>AI Suggestion</th></tr></thead>
<tbody>{issue_rows}</tbody>
</table>
</body>
</html>"""


def _render_csv(data: dict) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "severity", "rule_id", "title", "description", "recommendation",
        "auto_fix_supported", "ai_suggestion", "ai_confidence", "status"
    ])
    writer.writeheader()
    for sev, issues in data["by_severity"].items():
        for issue in issues:
            writer.writerow({
                "severity": sev,
                "rule_id": issue["rule_id"],
                "title": issue["title"],
                "description": issue["description"],
                "recommendation": issue.get("recommendation", ""),
                "auto_fix_supported": issue.get("auto_fix_supported", False),
                "ai_suggestion": issue.get("ai_suggestion") or "",
                "ai_confidence": issue.get("ai_confidence") or "",
                "status": issue.get("status", "open"),
            })
    return output.getvalue().encode("utf-8")
