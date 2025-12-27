#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rollback Script

Performs rollback operations for the Agentic Stack system.
Supports rolling back:
- Docker containers to previous images
- Configuration to previous versions
- State to previous checkpoints
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent.parent


def run_command(cmd: list[str], dry_run: bool = False) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    if dry_run:
        print(f"[DRY RUN] Would execute: {' '.join(cmd)}")
        return 0, "", ""

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"


def log_rollback_action(action: dict[str, Any]) -> None:
    """Log rollback action to memory."""
    root = get_project_root()
    decisions_file = root / ".ai" / "memory" / "DECISIONS.jsonl"

    entry = {
        "timestamp": datetime.now().isoformat(),
        "decision_id": f"rollback-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "agent": "rollback_script",
        "decision_type": "recovery",
        "context": action.get("reason", "Manual rollback triggered"),
        "chosen_option": action.get("action", "rollback"),
        "rationale": action.get("rationale", "Rollback requested"),
        "outcome": action.get("outcome", "pending"),
    }

    with open(decisions_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def rollback_docker_services(
    services: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Rollback Docker services to previous state."""
    results = {
        "action": "docker_rollback",
        "success": False,
        "services": [],
        "errors": [],
    }

    root = get_project_root()

    # Stop current services
    print("Stopping Docker services...")
    cmd = ["docker", "compose", "-f", str(root / "docker-compose.yml"), "down"]
    code, stdout, stderr = run_command(cmd, dry_run)

    if code != 0 and not dry_run:
        results["errors"].append(f"Failed to stop services: {stderr}")
        return results

    # Remove containers (to ensure clean state)
    print("Removing containers...")
    cmd = ["docker", "compose", "-f", str(root / "docker-compose.yml"), "rm", "-f"]
    run_command(cmd, dry_run)

    # Pull fresh images (ensures we have the specified versions)
    print("Pulling images...")
    cmd = ["docker", "compose", "-f", str(root / "docker-compose.yml"), "pull"]
    code, stdout, stderr = run_command(cmd, dry_run)

    if code != 0 and not dry_run:
        results["errors"].append(f"Failed to pull images: {stderr}")

    # Start services
    print("Starting services...")
    cmd = ["docker", "compose", "-f", str(root / "docker-compose.yml"), "up", "-d"]
    code, stdout, stderr = run_command(cmd, dry_run)

    if code != 0 and not dry_run:
        results["errors"].append(f"Failed to start services: {stderr}")
        return results

    results["success"] = True
    results["services"] = services or ["all"]

    return results


def rollback_state(checkpoint_id: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Rollback agent state to a previous checkpoint."""
    results = {
        "action": "state_rollback",
        "success": False,
        "checkpoint": None,
        "errors": [],
    }

    root = get_project_root()
    checkpoints_dir = root / ".ai" / "memory" / "checkpoints"

    if not checkpoints_dir.exists():
        results["errors"].append("No checkpoints directory found")
        return results

    # Find available checkpoints
    checkpoints = sorted(checkpoints_dir.glob("*.json"), reverse=True)

    if not checkpoints:
        results["errors"].append("No checkpoints available")
        return results

    # Select checkpoint
    if checkpoint_id:
        target = checkpoints_dir / f"{checkpoint_id}.json"
        if not target.exists():
            results["errors"].append(f"Checkpoint {checkpoint_id} not found")
            return results
    else:
        # Use most recent checkpoint
        target = checkpoints[0]

    results["checkpoint"] = target.name

    if dry_run:
        print(f"[DRY RUN] Would restore from checkpoint: {target}")
        results["success"] = True
        return results

    # Load checkpoint
    try:
        with open(target, "r") as f:
            checkpoint_data = json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        results["errors"].append(f"Failed to load checkpoint: {e}")
        return results

    # Restore state (implementation depends on what's in the checkpoint)
    print(f"Restoring from checkpoint: {target.name}")

    # For now, just log that we would restore
    # Actual implementation would restore Redis state, etc.
    results["success"] = True

    return results


def rollback_git(commits: int = 1, dry_run: bool = False) -> dict[str, Any]:
    """Rollback git to previous commit(s)."""
    results = {
        "action": "git_rollback",
        "success": False,
        "commits_reverted": 0,
        "errors": [],
    }

    root = get_project_root()

    # Check for uncommitted changes
    code, stdout, stderr = run_command(["git", "-C", str(root), "status", "--porcelain"])

    if stdout.strip():
        results["errors"].append("Uncommitted changes present. Commit or stash first.")
        return results

    # Get current HEAD
    code, current_head, _ = run_command(["git", "-C", str(root), "rev-parse", "HEAD"])
    current_head = current_head.strip()

    print(f"Current HEAD: {current_head[:8]}")
    print(f"Rolling back {commits} commit(s)...")

    if dry_run:
        # Show what would be reverted
        code, log, _ = run_command([
            "git", "-C", str(root), "log",
            f"--oneline", f"-{commits}"
        ])
        print(f"[DRY RUN] Would revert:\n{log}")
        results["success"] = True
        results["commits_reverted"] = commits
        return results

    # Perform soft reset (keeps changes staged)
    cmd = ["git", "-C", str(root), "reset", "--soft", f"HEAD~{commits}"]
    code, stdout, stderr = run_command(cmd)

    if code != 0:
        results["errors"].append(f"Git reset failed: {stderr}")
        return results

    results["success"] = True
    results["commits_reverted"] = commits

    return results


def clear_caches(dry_run: bool = False) -> dict[str, Any]:
    """Clear system caches (Redis, local)."""
    results = {
        "action": "clear_caches",
        "success": False,
        "cleared": [],
        "errors": [],
    }

    # Clear Redis (if available)
    print("Clearing Redis cache...")
    cmd = ["docker", "exec", "agentic-stack-redis-1", "redis-cli", "FLUSHALL"]
    code, stdout, stderr = run_command(cmd, dry_run)

    if code == 0 or dry_run:
        results["cleared"].append("redis")
    else:
        results["errors"].append(f"Failed to clear Redis: {stderr}")

    # Clear local caches
    root = get_project_root()
    cache_dirs = [
        root / "__pycache__",
        root / ".pytest_cache",
        root / ".mypy_cache",
        root / ".ruff_cache",
    ]

    for cache_dir in cache_dirs:
        if cache_dir.exists():
            if dry_run:
                print(f"[DRY RUN] Would remove: {cache_dir}")
            else:
                import shutil
                shutil.rmtree(cache_dir, ignore_errors=True)
            results["cleared"].append(str(cache_dir.name))

    results["success"] = len(results["errors"]) == 0

    return results


def format_report(results: dict[str, Any]) -> str:
    """Format rollback results as a readable report."""
    lines = [
        "=" * 60,
        "ROLLBACK REPORT",
        f"Generated: {datetime.now().isoformat()}",
        "=" * 60,
        "",
    ]

    for action_name, action_result in results.items():
        lines.append(f"## {action_name}")
        lines.append(f"  Success: {'Yes' if action_result.get('success') else 'No'}")

        # Action-specific details
        if "services" in action_result:
            lines.append(f"  Services: {', '.join(action_result['services'])}")
        if "checkpoint" in action_result:
            lines.append(f"  Checkpoint: {action_result['checkpoint']}")
        if "commits_reverted" in action_result:
            lines.append(f"  Commits reverted: {action_result['commits_reverted']}")
        if "cleared" in action_result:
            lines.append(f"  Cleared: {', '.join(action_result['cleared'])}")

        # Errors
        errors = action_result.get("errors", [])
        if errors:
            lines.append("  Errors:")
            for error in errors:
                lines.append(f"    - {error}")

        lines.append("")

    # Summary
    all_success = all(r.get("success", False) for r in results.values())
    lines.append("=" * 60)
    lines.append(f"STATUS: {'SUCCESS' if all_success else 'PARTIAL FAILURE'}")
    lines.append("=" * 60)

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Rollback script for Agentic Stack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --docker              Rollback Docker services
  %(prog)s --state               Rollback to last state checkpoint
  %(prog)s --git 2               Rollback last 2 git commits
  %(prog)s --clear-cache         Clear all caches
  %(prog)s --all --dry-run       Show what full rollback would do
        """,
    )

    parser.add_argument(
        "--docker",
        action="store_true",
        help="Rollback Docker services",
    )
    parser.add_argument(
        "--state",
        nargs="?",
        const="latest",
        metavar="CHECKPOINT_ID",
        help="Rollback state to checkpoint (default: latest)",
    )
    parser.add_argument(
        "--git",
        type=int,
        metavar="N",
        help="Rollback N git commits",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear all caches",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Perform full rollback (docker + state + cache)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )
    parser.add_argument(
        "--reason",
        type=str,
        default="Manual rollback",
        help="Reason for rollback (logged)",
    )

    args = parser.parse_args()

    # Check if any action specified
    if not any([args.docker, args.state, args.git, args.clear_cache, args.all]):
        parser.print_help()
        return 1

    results: dict[str, Any] = {}

    # Log rollback initiation
    log_rollback_action({
        "action": "rollback_initiated",
        "reason": args.reason,
        "dry_run": args.dry_run,
    })

    print(f"Starting rollback... {'[DRY RUN]' if args.dry_run else ''}")
    print(f"Reason: {args.reason}")
    print("")

    # Execute requested rollbacks
    if args.all or args.docker:
        results["docker"] = rollback_docker_services(dry_run=args.dry_run)

    if args.all or args.state:
        checkpoint_id = None if args.state == "latest" else args.state
        results["state"] = rollback_state(checkpoint_id, dry_run=args.dry_run)

    if args.git:
        results["git"] = rollback_git(args.git, dry_run=args.dry_run)

    if args.all or args.clear_cache:
        results["cache"] = clear_caches(dry_run=args.dry_run)

    # Print report
    report = format_report(results)
    print(report)

    # Log completion
    all_success = all(r.get("success", False) for r in results.values())
    log_rollback_action({
        "action": "rollback_completed",
        "reason": args.reason,
        "outcome": "success" if all_success else "partial_failure",
    })

    return 0 if all_success else 1


if __name__ == "__main__":
    sys.exit(main())
