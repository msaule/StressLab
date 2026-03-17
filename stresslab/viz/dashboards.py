"""Static dashboard summaries."""

from __future__ import annotations

from pathlib import Path


def dashboard_summary(output_dir: Path, plots: dict[str, str]) -> Path:
    """Build a minimal dashboard index page."""

    html = ["<html><body><h1>StressLab Dashboard</h1>"]
    for label, plot_path in plots.items():
        html.append(f"<h2>{label.replace('_', ' ').title()}</h2>")
        html.append(f"<img src='{Path(plot_path).name}' style='max-width: 100%;'>")
    html.append("</body></html>")
    path = output_dir / "dashboard.html"
    path.write_text("\n".join(html), encoding="utf-8")
    return path
