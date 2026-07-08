#!/usr/bin/env python3
"""Initialize a durable job-orchestrator run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "run-template"
JOB_PROTOCOL_SOURCE = SKILL_ROOT / "references" / "job-protocol.md"
PROTOCOL_VERSION = 1


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


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:40] or "run"


def load_request(args: argparse.Namespace) -> str:
    if args.request_file:
        return args.request_file.resolve().read_text(encoding="utf-8")
    return args.request


def render_json_template(name: str, replacements: dict[str, str]) -> object:
    text = (TEMPLATE_ROOT / name).read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace("{{" + key + "}}", json.dumps(value)[1:-1])
    return json.loads(text)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)
    created_at = now.isoformat().replace("+00:00", "Z")
    run_id = args.run_id or f"{now:%Y%m%d-%H%M%S}-{safe_slug(args.goal)}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        print("error: invalid run ID", file=sys.stderr)
        return 2

    state_root = args.state_root.expanduser().resolve()
    workspace = args.workspace.expanduser().resolve()
    run_root = state_root / run_id
    if run_root.exists():
        print(f"error: run already exists: {run_root}", file=sys.stderr)
        return 3

    jobs_root = run_root / "jobs"
    protocol_root = run_root / "protocol"
    jobs_root.mkdir(parents=True)
    protocol_root.mkdir()

    protocol_bytes = JOB_PROTOCOL_SOURCE.read_bytes()
    protocol_sha256 = hashlib.sha256(protocol_bytes).hexdigest()

    replacements = {
        "RUN_ID": run_id,
        "GOAL": args.goal,
        "CREATED_AT": created_at,
        "WORKSPACE": str(workspace),
        "STATE_ROOT": str(state_root),
        "PROTOCOL_SHA256": protocol_sha256,
    }
    write_json(
        run_root / "run.json",
        render_json_template("run.json", replacements),
    )
    write_json(
        run_root / "setup.json",
        render_json_template("setup.json", replacements),
    )
    write_json(
        run_root / "queue.json",
        render_json_template("queue.json", replacements),
    )
    write_json(
        jobs_root / "index.json",
        render_json_template("jobs-index.json", replacements),
    )
    (protocol_root / "job-protocol.md").write_bytes(protocol_bytes)
    write_json(
        protocol_root / "manifest.json",
        {
            "protocol_version": PROTOCOL_VERSION,
            "file": "job-protocol.md",
            "sha256": protocol_sha256,
            "source": "references/job-protocol.md",
            "snapshotted_at": created_at,
        },
    )
    (run_root / "request.md").write_text(load_request(args), encoding="utf-8")
    (run_root / "events.jsonl").touch()
    (run_root / "decisions.jsonl").touch()

    print(run_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
