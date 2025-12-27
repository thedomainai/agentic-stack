#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Report Generator

Generates a daily summary report from memory and metrics JSONL files.
Output: Markdown report summarizing agent activities, decisions, and metrics.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Any


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent.parent


def read_jsonl_file(filepath: Path, since: datetime | None = None) -> list[dict[str, Any]]:
    """Read entries from a JSONL file, optionally filtering by timestamp."""
    entries = []
    if not filepath.exists():
        return entries

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if since and "timestamp" in entry:
                    entry_time = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    if entry_time < since:
                        continue
                entries.append(entry)
            except json.JSONDecodeError:
                continue
    return entries


def generate_report(date: datetime) -> str:
    """Generate the daily report for a specific date."""
    root = get_project_root()
    memory_dir = root / ".ai" / "memory"
    metrics_dir = root / ".ai" / "metrics"

    # Calculate time range (24 hours for the given date)
    start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Read data from various sources
    decisions = read_jsonl_file(memory_dir / "DECISIONS.jsonl", start_of_day)
    failures = read_jsonl_file(memory_dir / "FAILURES.jsonl", start_of_day)
    discoveries = read_jsonl_file(memory_dir / "DISCOVERIES.jsonl", start_of_day)
    velocity = read_jsonl_file(metrics_dir / "VELOCITY.jsonl", start_of_day)
    budget = read_jsonl_file(metrics_dir / "BUDGET_TRACKER.jsonl", start_of_day)

    # Build report
    report_lines = [
        f"# Daily Report - {date.strftime('%Y-%m-%d')}",
        "",
        f"Generated at: {datetime.now().isoformat()}",
        "",
        "---",
        "",
        "## Summary",
        "",
    ]

    # Summary statistics
    report_lines.extend([
        f"- **Decisions Made**: {len(decisions)}",
        f"- **Failures Recorded**: {len(failures)}",
        f"- **Discoveries**: {len(discoveries)}",
        "",
    ])

    # Decisions by type
    if decisions:
        report_lines.extend(["## Decisions", ""])
        decision_types: dict[str, int] = defaultdict(int)
        for d in decisions:
            dtype = d.get("decision_type", "unknown")
            decision_types[dtype] += 1

        report_lines.append("### By Type")
        for dtype, count in sorted(decision_types.items(), key=lambda x: -x[1]):
            report_lines.append(f"- {dtype}: {count}")
        report_lines.append("")

        # Recent decisions (last 5)
        report_lines.append("### Recent Decisions")
        for d in decisions[-5:]:
            report_lines.append(f"- [{d.get('decision_type', 'N/A')}] {d.get('chosen_option', 'N/A')}")
            if d.get("rationale"):
                report_lines.append(f"  - Rationale: {d['rationale'][:100]}...")
        report_lines.append("")

    # Failures
    if failures:
        report_lines.extend(["## Failures", ""])
        severity_counts: dict[str, int] = defaultdict(int)
        for f in failures:
            severity_counts[f.get("severity", "unknown")] += 1

        report_lines.append("### By Severity")
        for severity in ["critical", "error", "warning"]:
            if severity in severity_counts:
                report_lines.append(f"- {severity}: {severity_counts[severity]}")
        report_lines.append("")

        # Unresolved failures
        unresolved = [f for f in failures if not f.get("resolved", False)]
        if unresolved:
            report_lines.append(f"### Unresolved ({len(unresolved)})")
            for f in unresolved[:5]:
                report_lines.append(f"- [{f.get('severity', 'N/A')}] {f.get('message', 'N/A')[:80]}")
            report_lines.append("")

    # Discoveries
    if discoveries:
        report_lines.extend(["## Discoveries", ""])
        for d in discoveries[-5:]:
            report_lines.append(f"- **{d.get('title', 'Untitled')}**")
            report_lines.append(f"  - Category: {d.get('category', 'N/A')}")
            if d.get("description"):
                report_lines.append(f"  - {d['description'][:100]}...")
        report_lines.append("")

    # Velocity metrics
    if velocity:
        report_lines.extend(["## Velocity Metrics", ""])
        latest = velocity[-1]
        report_lines.extend([
            f"- Tasks Completed: {latest.get('tasks_completed', 0)}",
            f"- Tasks Failed: {latest.get('tasks_failed', 0)}",
            f"- Average Duration: {latest.get('average_duration_ms', 0)}ms",
        ])
        report_lines.append("")

    # Budget metrics
    if budget:
        report_lines.extend(["## Budget Status", ""])
        latest = budget[-1]
        llm_usage = latest.get("llm_usage", {})
        report_lines.extend([
            f"- Input Tokens: {llm_usage.get('input_tokens', 0):,}",
            f"- Output Tokens: {llm_usage.get('output_tokens', 0):,}",
            f"- Total Cost: ${llm_usage.get('total_cost_usd', 0):.2f}",
        ])
        if latest.get("budget_remaining_usd") is not None:
            report_lines.append(f"- Budget Remaining: ${latest['budget_remaining_usd']:.2f}")
        report_lines.append("")

    # Footer
    report_lines.extend([
        "---",
        "",
        "*Report generated by daily_report.py*",
    ])

    return "\n".join(report_lines)


def main() -> int:
    """Main entry point."""
    print("Generating daily report...")

    # Generate report for today
    today = datetime.now()
    report = generate_report(today)

    # Output report
    print(report)

    # Optionally save to file
    root = get_project_root()
    reports_dir = root / ".ai" / "reports"
    reports_dir.mkdir(exist_ok=True)

    report_file = reports_dir / f"daily_{today.strftime('%Y%m%d')}.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nReport saved to: {report_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
