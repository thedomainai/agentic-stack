#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dependency Audit Script

Checks for security vulnerabilities and outdated dependencies.
Outputs results to stdout and optionally to JSONL metrics file.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent.parent


def run_command(cmd: list[str], capture: bool = True) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=300,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"


def check_python_dependencies() -> dict[str, Any]:
    """Check Python dependencies for vulnerabilities."""
    results = {
        "tool": "pip-audit",
        "checked": False,
        "vulnerabilities": [],
        "error": None,
    }

    # Try pip-audit first
    code, stdout, stderr = run_command(["pip-audit", "--format", "json"])

    if code == -1 and "not found" in stderr.lower():
        # Try safety as fallback
        code, stdout, stderr = run_command(["safety", "check", "--json"])
        results["tool"] = "safety"

    if code == -1:
        results["error"] = stderr
        return results

    results["checked"] = True

    if code != 0:
        try:
            vulns = json.loads(stdout)
            if isinstance(vulns, list):
                results["vulnerabilities"] = vulns
            elif isinstance(vulns, dict):
                results["vulnerabilities"] = vulns.get("vulnerabilities", [])
        except json.JSONDecodeError:
            results["error"] = "Failed to parse vulnerability report"

    return results


def check_outdated_packages() -> dict[str, Any]:
    """Check for outdated Python packages."""
    results = {
        "checked": False,
        "outdated": [],
        "error": None,
    }

    code, stdout, stderr = run_command(
        ["pip", "list", "--outdated", "--format", "json"]
    )

    if code == -1:
        results["error"] = stderr
        return results

    results["checked"] = True

    try:
        outdated = json.loads(stdout)
        results["outdated"] = outdated
    except json.JSONDecodeError:
        results["error"] = "Failed to parse outdated packages"

    return results


def check_docker_images() -> dict[str, Any]:
    """Check Docker images for updates (basic check)."""
    results = {
        "checked": False,
        "images": [],
        "error": None,
    }

    root = get_project_root()
    compose_file = root / "docker-compose.yml"

    if not compose_file.exists():
        results["error"] = "docker-compose.yml not found"
        return results

    # Parse images from docker-compose
    import re

    with open(compose_file, "r") as f:
        content = f.read()

    image_pattern = r'image:\s*([^\s]+)'
    images = re.findall(image_pattern, content)

    results["checked"] = True
    results["images"] = [{"name": img, "status": "check_manually"} for img in images]

    return results


def write_audit_result(results: dict[str, Any]) -> None:
    """Write audit results to metrics file."""
    root = get_project_root()
    metrics_file = root / ".ai" / "metrics" / "dependency_health.jsonl"

    entry = {
        "timestamp": datetime.now().isoformat(),
        "audit_type": "dependency",
        "results": results,
    }

    with open(metrics_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def format_report(results: dict[str, Any]) -> str:
    """Format audit results as a readable report."""
    lines = [
        "=" * 60,
        "DEPENDENCY AUDIT REPORT",
        f"Generated: {datetime.now().isoformat()}",
        "=" * 60,
        "",
    ]

    # Python vulnerabilities
    py_results = results.get("python_vulnerabilities", {})
    lines.append(f"## Python Vulnerabilities ({py_results.get('tool', 'N/A')})")

    if py_results.get("error"):
        lines.append(f"  ERROR: {py_results['error']}")
    elif not py_results.get("checked"):
        lines.append("  Not checked (tool not available)")
    else:
        vulns = py_results.get("vulnerabilities", [])
        if vulns:
            lines.append(f"  FOUND {len(vulns)} vulnerabilities:")
            for v in vulns[:10]:
                name = v.get("name", v.get("package_name", "unknown"))
                severity = v.get("severity", v.get("vulnerability_id", "N/A"))
                lines.append(f"    - {name}: {severity}")
        else:
            lines.append("  No vulnerabilities found")
    lines.append("")

    # Outdated packages
    outdated_results = results.get("outdated_packages", {})
    lines.append("## Outdated Packages")

    if outdated_results.get("error"):
        lines.append(f"  ERROR: {outdated_results['error']}")
    elif not outdated_results.get("checked"):
        lines.append("  Not checked")
    else:
        outdated = outdated_results.get("outdated", [])
        if outdated:
            lines.append(f"  FOUND {len(outdated)} outdated packages:")
            for pkg in outdated[:10]:
                lines.append(
                    f"    - {pkg.get('name')}: "
                    f"{pkg.get('version')} -> {pkg.get('latest_version')}"
                )
            if len(outdated) > 10:
                lines.append(f"    ... and {len(outdated) - 10} more")
        else:
            lines.append("  All packages up to date")
    lines.append("")

    # Docker images
    docker_results = results.get("docker_images", {})
    lines.append("## Docker Images")

    if docker_results.get("error"):
        lines.append(f"  ERROR: {docker_results['error']}")
    elif not docker_results.get("checked"):
        lines.append("  Not checked")
    else:
        images = docker_results.get("images", [])
        for img in images:
            lines.append(f"    - {img['name']}: {img['status']}")
    lines.append("")

    # Summary
    lines.append("=" * 60)
    has_issues = (
        bool(py_results.get("vulnerabilities")) or
        bool(outdated_results.get("outdated"))
    )
    lines.append(f"STATUS: {'ISSUES FOUND' if has_issues else 'HEALTHY'}")
    lines.append("=" * 60)

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    print("Running dependency audit...")

    results = {
        "python_vulnerabilities": check_python_dependencies(),
        "outdated_packages": check_outdated_packages(),
        "docker_images": check_docker_images(),
    }

    # Format and print report
    report = format_report(results)
    print(report)

    # Write to metrics
    write_audit_result(results)

    # Return non-zero if vulnerabilities found
    vulns = results["python_vulnerabilities"].get("vulnerabilities", [])
    critical_vulns = [v for v in vulns if v.get("severity", "").lower() in ("critical", "high")]

    if critical_vulns:
        print(f"\nWARNING: {len(critical_vulns)} critical/high vulnerabilities found!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
