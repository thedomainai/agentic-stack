#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Environment Parity Check Script

Verifies consistency between different environments by checking:
- Configuration file presence and schema
- Docker image versions
- Service configurations
- Documented vs actual differences
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent.parent


def load_yaml_file(filepath: Path) -> dict[str, Any] | None:
    """Load a YAML file safely."""
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return None


def check_config_parity() -> dict[str, Any]:
    """Check that all configuration files exist and have consistent schemas."""
    root = get_project_root()
    results = {
        "checked": True,
        "issues": [],
        "files_checked": [],
    }

    # Check .ai/specs files
    specs_dir = root / ".ai" / "specs"
    required_specs = [
        "ARCHITECTURE.yaml",
        "DATA_MODELS.yaml",
        "API_CONTRACTS.yaml",
        "PRODUCT_SPEC.yaml",
    ]

    for spec in required_specs:
        filepath = specs_dir / spec
        results["files_checked"].append(str(filepath.relative_to(root)))

        if not filepath.exists():
            results["issues"].append({
                "type": "missing_file",
                "file": spec,
                "severity": "high",
            })
            continue

        content = load_yaml_file(filepath)
        if content is None:
            results["issues"].append({
                "type": "invalid_yaml",
                "file": spec,
                "severity": "high",
            })
            continue

        if not content:
            results["issues"].append({
                "type": "empty_file",
                "file": spec,
                "severity": "medium",
            })

    # Check .ai/rules files
    rules_dir = root / ".ai" / "rules"
    required_rules = [
        "GOVERNANCE.yaml",
        "SECRET_MANAGEMENT.yaml",
        "MODEL_SELECTION.yaml",
        "QUALITY_GATES.yaml",
        "RECOVERY_PROTOCOL.yaml",
    ]

    for rule in required_rules:
        filepath = rules_dir / rule
        results["files_checked"].append(str(filepath.relative_to(root)))

        if not filepath.exists():
            results["issues"].append({
                "type": "missing_file",
                "file": rule,
                "severity": "medium",
            })
            continue

        content = load_yaml_file(filepath)
        if content is None:
            results["issues"].append({
                "type": "invalid_yaml",
                "file": rule,
                "severity": "medium",
            })
        elif not content:
            results["issues"].append({
                "type": "empty_file",
                "file": rule,
                "severity": "low",
            })

    return results


def check_docker_parity() -> dict[str, Any]:
    """Check Docker configuration consistency."""
    root = get_project_root()
    results = {
        "checked": True,
        "issues": [],
        "services": [],
    }

    compose_file = root / "docker-compose.yml"

    if not compose_file.exists():
        results["issues"].append({
            "type": "missing_file",
            "file": "docker-compose.yml",
            "severity": "critical",
        })
        return results

    compose = load_yaml_file(compose_file)
    if compose is None:
        results["issues"].append({
            "type": "invalid_yaml",
            "file": "docker-compose.yml",
            "severity": "critical",
        })
        return results

    services = compose.get("services", {})

    for service_name, service_config in services.items():
        service_info = {
            "name": service_name,
            "image": service_config.get("image", "N/A"),
            "has_healthcheck": "healthcheck" in service_config,
            "has_volumes": "volumes" in service_config,
            "restart_policy": service_config.get("restart", "none"),
        }
        results["services"].append(service_info)

        # Check for missing health checks
        if "healthcheck" not in service_config:
            results["issues"].append({
                "type": "missing_healthcheck",
                "service": service_name,
                "severity": "medium",
            })

        # Check restart policy
        if service_config.get("restart") not in ("always", "unless-stopped"):
            results["issues"].append({
                "type": "weak_restart_policy",
                "service": service_name,
                "severity": "low",
            })

    return results


def check_memory_parity() -> dict[str, Any]:
    """Check that memory/metrics files have consistent schemas."""
    root = get_project_root()
    results = {
        "checked": True,
        "issues": [],
        "files_checked": [],
    }

    memory_dir = root / ".ai" / "memory"
    metrics_dir = root / ".ai" / "metrics"

    jsonl_files = list(memory_dir.glob("*.jsonl")) + list(metrics_dir.glob("*.jsonl"))

    for filepath in jsonl_files:
        results["files_checked"].append(str(filepath.relative_to(root)))

        # Check file is valid JSONL
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as e:
                        results["issues"].append({
                            "type": "invalid_jsonl",
                            "file": filepath.name,
                            "line": line_num,
                            "error": str(e),
                            "severity": "high",
                        })
                        break
        except IOError as e:
            results["issues"].append({
                "type": "read_error",
                "file": filepath.name,
                "error": str(e),
                "severity": "high",
            })

    return results


def check_environment_variables() -> dict[str, Any]:
    """Check for required environment variable documentation."""
    root = get_project_root()
    results = {
        "checked": True,
        "issues": [],
        "env_files": [],
    }

    # Check for .env.example
    env_example = root / ".env.example"
    env_local = root / ".env"

    if env_example.exists():
        results["env_files"].append(".env.example")
    else:
        results["issues"].append({
            "type": "missing_file",
            "file": ".env.example",
            "severity": "low",
            "note": "Environment variable template not found",
        })

    if env_local.exists():
        results["env_files"].append(".env")

    return results


def write_parity_result(results: dict[str, Any]) -> None:
    """Write parity check results to metrics file."""
    root = get_project_root()
    metrics_file = root / ".ai" / "metrics" / "parity_checks.jsonl"

    entry = {
        "timestamp": datetime.now().isoformat(),
        "check_type": "parity",
        "results": results,
    }

    with open(metrics_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def format_report(results: dict[str, Any]) -> str:
    """Format parity check results as a readable report."""
    lines = [
        "=" * 60,
        "ENVIRONMENT PARITY CHECK REPORT",
        f"Generated: {datetime.now().isoformat()}",
        "=" * 60,
        "",
    ]

    total_issues = 0

    # Configuration parity
    config = results.get("config_parity", {})
    lines.append("## Configuration Parity")
    lines.append(f"  Files checked: {len(config.get('files_checked', []))}")
    issues = config.get("issues", [])
    total_issues += len(issues)
    if issues:
        lines.append(f"  Issues found: {len(issues)}")
        for issue in issues:
            lines.append(f"    - [{issue['severity'].upper()}] {issue['type']}: {issue.get('file', 'N/A')}")
    else:
        lines.append("  No issues found")
    lines.append("")

    # Docker parity
    docker = results.get("docker_parity", {})
    lines.append("## Docker Configuration")
    services = docker.get("services", [])
    lines.append(f"  Services defined: {len(services)}")
    for svc in services:
        lines.append(f"    - {svc['name']}: {svc['image']}")
    issues = docker.get("issues", [])
    total_issues += len(issues)
    if issues:
        lines.append(f"  Issues found: {len(issues)}")
        for issue in issues:
            lines.append(f"    - [{issue['severity'].upper()}] {issue['type']}: {issue.get('service', 'N/A')}")
    lines.append("")

    # Memory/metrics parity
    memory = results.get("memory_parity", {})
    lines.append("## Memory/Metrics Files")
    lines.append(f"  Files checked: {len(memory.get('files_checked', []))}")
    issues = memory.get("issues", [])
    total_issues += len(issues)
    if issues:
        lines.append(f"  Issues found: {len(issues)}")
        for issue in issues:
            lines.append(f"    - [{issue['severity'].upper()}] {issue['type']}: {issue.get('file', 'N/A')}")
    else:
        lines.append("  No issues found")
    lines.append("")

    # Environment variables
    env = results.get("env_parity", {})
    lines.append("## Environment Configuration")
    lines.append(f"  Env files found: {', '.join(env.get('env_files', [])) or 'None'}")
    issues = env.get("issues", [])
    total_issues += len(issues)
    if issues:
        for issue in issues:
            lines.append(f"    - [{issue['severity'].upper()}] {issue.get('note', issue['type'])}")
    lines.append("")

    # Summary
    lines.append("=" * 60)
    status = "HEALTHY" if total_issues == 0 else f"ISSUES FOUND ({total_issues})"
    lines.append(f"STATUS: {status}")
    lines.append("=" * 60)

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    print("Running environment parity check...")

    results = {
        "config_parity": check_config_parity(),
        "docker_parity": check_docker_parity(),
        "memory_parity": check_memory_parity(),
        "env_parity": check_environment_variables(),
    }

    # Format and print report
    report = format_report(results)
    print(report)

    # Write to metrics
    write_parity_result(results)

    # Count critical issues
    critical_issues = 0
    for check_result in results.values():
        for issue in check_result.get("issues", []):
            if issue.get("severity") in ("critical", "high"):
                critical_issues += 1

    if critical_issues > 0:
        print(f"\nWARNING: {critical_issues} critical/high issues found!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
