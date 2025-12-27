#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Secrets Check Script

Scans the codebase for accidentally committed secrets and sensitive data.
Checks for patterns that indicate API keys, passwords, tokens, etc.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent.parent


# Patterns that might indicate secrets
SECRET_PATTERNS = [
    # API Keys
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[a-zA-Z0-9_-]{20,}["\']?', "API Key"),
    (r'(?i)sk-[a-zA-Z0-9]{48}', "OpenAI API Key"),
    (r'(?i)sk-ant-[a-zA-Z0-9-]{95}', "Anthropic API Key"),

    # AWS
    (r'(?i)AKIA[0-9A-Z]{16}', "AWS Access Key ID"),
    (r'(?i)(aws[_-]?secret|secret[_-]?key)\s*[=:]\s*["\']?[a-zA-Z0-9/+=]{40}["\']?', "AWS Secret Key"),

    # Generic secrets
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'][^"\']{8,}["\']', "Password"),
    (r'(?i)(secret|token)\s*[=:]\s*["\'][a-zA-Z0-9_-]{16,}["\']', "Secret/Token"),
    (r'(?i)bearer\s+[a-zA-Z0-9_-]{20,}', "Bearer Token"),

    # Private keys
    (r'-----BEGIN (RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----', "Private Key"),
    (r'-----BEGIN PGP PRIVATE KEY BLOCK-----', "PGP Private Key"),

    # Database
    (r'(?i)(mongodb|postgres|mysql|redis)://[^:]+:[^@]+@', "Database Connection String"),

    # JWT
    (r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*', "JWT Token"),

    # Generic high entropy strings (potential secrets)
    (r'["\'][a-zA-Z0-9+/]{40,}={0,2}["\']', "Base64 Encoded (potential secret)"),
]

# Files and directories to skip
SKIP_PATTERNS = [
    r'\.git/',
    r'\.venv/',
    r'__pycache__/',
    r'node_modules/',
    r'\.pyc$',
    r'\.lock$',
    r'\.min\.js$',
    r'\.min\.css$',
    r'\.woff2?$',
    r'\.ttf$',
    r'\.ico$',
    r'\.png$',
    r'\.jpg$',
    r'\.jpeg$',
    r'\.gif$',
    r'\.svg$',
]

# Files that are expected to contain secret patterns (false positives)
ALLOWLIST_FILES = [
    "secrets_check.py",  # This file itself
    "SECRET_MANAGEMENT.yaml",  # Documentation
    ".ai/specs/",  # Specification files
    ".ai/rules/",  # Rule files
]


def should_skip_file(filepath: Path, root: Path) -> bool:
    """Check if a file should be skipped."""
    rel_path = str(filepath.relative_to(root))

    for pattern in SKIP_PATTERNS:
        if re.search(pattern, rel_path):
            return True

    return False


def is_allowlisted(filepath: Path, root: Path) -> bool:
    """Check if a file is in the allowlist."""
    rel_path = str(filepath.relative_to(root))

    for pattern in ALLOWLIST_FILES:
        if pattern in rel_path:
            return True

    return False


def scan_file(filepath: Path) -> list[dict[str, Any]]:
    """Scan a single file for secrets."""
    findings = []

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except IOError:
        return findings

    lines = content.split("\n")

    for line_num, line in enumerate(lines, 1):
        # Skip comment lines (basic check)
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue

        for pattern, secret_type in SECRET_PATTERNS:
            matches = re.finditer(pattern, line)
            for match in matches:
                # Extract a snippet around the match
                start = max(0, match.start() - 10)
                end = min(len(line), match.end() + 10)
                snippet = line[start:end]

                # Mask the potential secret
                masked = re.sub(r'[a-zA-Z0-9]', '*', snippet)

                findings.append({
                    "line": line_num,
                    "type": secret_type,
                    "snippet": masked,
                    "pattern": pattern[:50],  # Truncate pattern for display
                })

    return findings


def scan_directory(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Scan entire directory for secrets."""
    results: dict[str, list[dict[str, Any]]] = {}

    for filepath in root.rglob("*"):
        if not filepath.is_file():
            continue

        if should_skip_file(filepath, root):
            continue

        rel_path = str(filepath.relative_to(root))
        findings = scan_file(filepath)

        if findings:
            # Check if allowlisted
            if is_allowlisted(filepath, root):
                continue
            results[rel_path] = findings

    return results


def check_env_files(root: Path) -> dict[str, Any]:
    """Check for .env files that might contain secrets."""
    results = {
        "env_files_found": [],
        "gitignored": False,
        "issues": [],
    }

    # Find .env files
    env_files = list(root.glob(".env*"))
    results["env_files_found"] = [str(f.relative_to(root)) for f in env_files]

    # Check .gitignore
    gitignore = root / ".gitignore"
    if gitignore.exists():
        with open(gitignore, "r") as f:
            content = f.read()
            if ".env" in content:
                results["gitignored"] = True

    # Check if .env is tracked by git
    for env_file in env_files:
        if env_file.name == ".env" and env_file.exists():
            if not results["gitignored"]:
                results["issues"].append({
                    "type": "env_not_gitignored",
                    "file": str(env_file.relative_to(root)),
                    "severity": "high",
                })

    return results


def write_scan_result(results: dict[str, Any]) -> None:
    """Write scan results to metrics file."""
    root = get_project_root()
    metrics_file = root / ".ai" / "metrics" / "secrets_scans.jsonl"

    entry = {
        "timestamp": datetime.now().isoformat(),
        "scan_type": "secrets",
        "files_with_findings": len(results.get("findings", {})),
        "total_findings": sum(
            len(findings) for findings in results.get("findings", {}).values()
        ),
    }

    with open(metrics_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def format_report(results: dict[str, Any]) -> str:
    """Format scan results as a readable report."""
    lines = [
        "=" * 60,
        "SECRETS SCAN REPORT",
        f"Generated: {datetime.now().isoformat()}",
        "=" * 60,
        "",
    ]

    # File scan results
    findings = results.get("findings", {})
    total_findings = sum(len(f) for f in findings.values())

    lines.append("## Code Scan Results")
    lines.append(f"  Files with potential secrets: {len(findings)}")
    lines.append(f"  Total findings: {total_findings}")
    lines.append("")

    if findings:
        for filepath, file_findings in sorted(findings.items()):
            lines.append(f"  ### {filepath}")
            for finding in file_findings[:5]:  # Limit to 5 per file
                lines.append(f"    Line {finding['line']}: {finding['type']}")
                lines.append(f"      Snippet: {finding['snippet']}")
            if len(file_findings) > 5:
                lines.append(f"    ... and {len(file_findings) - 5} more findings")
            lines.append("")

    # Environment files
    env_results = results.get("env_check", {})
    lines.append("## Environment Files")
    env_files = env_results.get("env_files_found", [])
    lines.append(f"  Found: {', '.join(env_files) if env_files else 'None'}")
    lines.append(f"  .env in .gitignore: {'Yes' if env_results.get('gitignored') else 'No'}")

    env_issues = env_results.get("issues", [])
    if env_issues:
        lines.append("  Issues:")
        for issue in env_issues:
            lines.append(f"    - [{issue['severity'].upper()}] {issue['type']}")
    lines.append("")

    # Summary
    lines.append("=" * 60)
    has_issues = total_findings > 0 or env_issues
    status = "SECRETS FOUND - REVIEW REQUIRED" if has_issues else "CLEAN"
    lines.append(f"STATUS: {status}")
    lines.append("=" * 60)

    if has_issues:
        lines.extend([
            "",
            "IMPORTANT: Review all findings above.",
            "False positives may occur. Verify before taking action.",
            "If secrets are confirmed, rotate them immediately.",
        ])

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    print("Running secrets scan...")

    root = get_project_root()

    results = {
        "findings": scan_directory(root),
        "env_check": check_env_files(root),
    }

    # Format and print report
    report = format_report(results)
    print(report)

    # Write to metrics
    write_scan_result(results)

    # Return non-zero if secrets found
    total_findings = sum(len(f) for f in results["findings"].values())

    if total_findings > 0:
        print(f"\nWARNING: {total_findings} potential secrets found!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
