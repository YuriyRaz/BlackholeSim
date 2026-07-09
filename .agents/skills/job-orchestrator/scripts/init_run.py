#!/usr/bin/env python3
"""Compatibility wrapper for ``jobctl init``."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


JOBCTL = Path(__file__).with_name("jobctl.py")
SKILL_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a new durable job-orchestrator run."
    )
    request = parser.add_mutually_exclusive_group(required=True)
    request.add_argument("--request-file", type=Path)
    request.add_argument("--request")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--state-root", type=Path, default=SKILL_ROOT / "runs")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = [sys.executable, str(JOBCTL), "init", "--goal", args.goal,
               "--state-root", str(args.state_root), "--workspace", str(args.workspace)]
    if args.request_file:
        command.extend(["--request-file", str(args.request_file)])
    else:
        command.extend(["--request", args.request])
    if args.run_id:
        command.extend(["--run-id", args.run_id])
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
