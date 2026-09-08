#!/usr/bin/env python3
"""Standalone orchestrator script for job-orchestrator using opencode-ai SDK."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from orchestrator_core import OrchestratorError

try:
    from opencode_ai import AsyncOpencode
    HAS_SDK = True
except ImportError:
    HAS_SDK = False
    print("Warning: opencode-ai package not installed.", file=sys.stderr)
    print("Install with: pip install --pre opencode-ai", file=sys.stderr)


class JobOrchestrator:
    """Standalone orchestrator for managing jobs via jobctl.py."""

    def __init__(
        self,
        run_root: Path,
        opencode_server: str,
        opencode_session_id: str,
        poll_interval: float = 1.0,
    ):
        self.run_root = run_root
        self.opencode_server = opencode_server
        self.opencode_session_id = opencode_session_id
        self.poll_interval = poll_interval
        self.client: Optional[AsyncOpencode] = None
        self.short_hash = self._compute_short_hash()

    def _compute_short_hash(self) -> str:
        import hashlib
        run_id = str(self.run_root)
        return hashlib.sha256(run_id.encode()).hexdigest()[:8]

    def _session_tag(self, job_id: str, purpose: str) -> str:
        return f"[RUN-{self.short_hash}][JOB-{job_id}] {purpose}"

    def _recovery_tag(self, summary: str) -> str:
        return f"[RUN-{self.short_hash}][RECOVERY] {summary}"

    async def connect(self) -> None:
        if not HAS_SDK:
            raise OrchestratorError("opencode-ai package is required")
        self.client = AsyncOpencode(base_url=self.opencode_server)

    async def create_worker_session(self, job_id: str, purpose: str) -> str:
        if not self.client:
            raise OrchestratorError("client not connected")
        tag = self._session_tag(job_id, purpose)
        session = await self.client.session.create()
        await self.client.session.chat(
            id=session.id,
            parts=[{"type": "text", "text": f"Session tag: {tag}"}],
            noReply=True,
        )
        return session.id

    async def send_to_ui(self, message: str) -> None:
        if not self.client:
            raise OrchestratorError("client not connected")
        await self.client.session.chat(
            id=self.opencode_session_id,
            parts=[{"type": "text", "text": message}],
        )

    def _run_jobctl(self, *args: str) -> dict[str, Any]:
        script_dir = Path(__file__).parent
        cmd = [sys.executable, str(script_dir / "jobctl.py"), *args]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(script_dir)
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            raise OrchestratorError(f"jobctl failed: {result.stderr}")
        return json.loads(result.stdout)

    def _check_existing_run(self) -> bool:
        run_path = self.run_root / "run.json"
        return run_path.exists()

    def _init_resume(self) -> dict[str, Any]:
        return self._run_jobctl(
            "init",
            "--run", str(self.run_root),
            "--mode", "resume",
        )

    async def ask_user(self, job_id: str, question: str, context: str = "") -> str:
        result = self._run_jobctl(
            "ask",
            "--run", str(self.run_root),
            "--job", job_id,
            "--question", question,
            "--context", context,
        )
        question_id = result.get("question_id", "")

        ui_message = (
            f"[WORKER QUESTION]\n"
            f"Question ID: {question_id}\n"
            f"Job ID: {job_id}\n"
            f"Run: {self.run_root}\n"
            f"---\n"
            f"{question}\n"
        )
        if context:
            ui_message += f"---\nContext: {context}\n"

        await self.send_to_ui(ui_message)
        return question_id

    async def poll_for_answer(self, question_id: str, timeout: float = 300.0) -> str:
        start = time.time()
        while time.time() - start < timeout:
            queue_dir = self.run_root / "queue"
            question_path = queue_dir / f"{question_id}.json"
            if question_path.exists():
                data = json.loads(question_path.read_text())
                if data.get("status") == "answered":
                    return data.get("answer", "")
            await asyncio.sleep(self.poll_interval)
        raise OrchestratorError(f"timeout waiting for answer to {question_id}")

    async def spawn_recovery(self, error_summary: str, error_context: dict[str, Any]) -> dict[str, Any]:
        tag = self._recovery_tag(error_summary)
        session = await self.client.session.create()
        await self.client.session.chat(
            id=session.id,
            parts=[{"type": "text", "text": f"Recovery session: {tag}"}],
            noReply=True,
        )

        recovery_prompt = (
            f"Recovery required for run at {self.run_root}.\n"
            f"Error: {error_summary}\n"
            f"Context: {json.dumps(error_context, indent=2)}\n\n"
            f"Provide a recovery plan as JSON with actions to execute."
        )
        response = await self.client.session.chat(
            id=session.id,
            parts=[{"type": "text", "text": recovery_prompt}],
        )
        dump = response.model_dump()
        parts = dump.get("parts", [])
        text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        plan_text = "".join(text_parts)

        try:
            plan = json.loads(plan_text)
        except json.JSONDecodeError:
            plan = {"action": "retry", "reason": plan_text}

        return plan

    async def run(self) -> dict[str, Any]:
        if self._check_existing_run():
            print(f"Resuming existing run at {self.run_root}", file=sys.stderr)
            self._init_resume()
        else:
            raise OrchestratorError(f"no run found at {self.run_root}")

        await self.connect()

        consecutive_errors = 0
        max_consecutive_errors = 5

        while True:
            try:
                result = self._run_jobctl("next", "--run", str(self.run_root))
                operation = result.get("operation")

                if operation == "run_complete":
                    return {
                        "status": "completed",
                        "run_status": result.get("run_status"),
                        "successful": result.get("successful", False),
                    }

                if operation == "wait":
                    await asyncio.sleep(self.poll_interval)
                    consecutive_errors = 0
                    continue

                if operation == "recover":
                    error_summary = result.get("reason", "unknown error")
                    recovery_plan = await self.spawn_recovery(error_summary, result)
                    action = recovery_plan.get("action", "retry")
                    if action == "retry":
                        continue
                    elif action == "abort":
                        return {"status": "aborted", "reason": error_summary}
                    else:
                        continue

                if operation == "prepare_dispatch":
                    job_id = result.get("job_id", "")
                    dispatch = self._run_jobctl(
                        "prepare-dispatch",
                        "--run", str(self.run_root),
                        "--job", job_id,
                        "--expected-revision", str(result.get("expected_revision", 0)),
                        "--expected-graph-revision", str(result.get("expected_graph_revision", 0)),
                        "--expected-graph-digest", result.get("expected_graph_digest", ""),
                        "--dependency-evidence-digest", result.get("dependency_evidence_digest", ""),
                    )
                    session_id = await self.create_worker_session(job_id, f"worker-{job_id}")
                    purpose = f"Execute job {job_id}"
                    prompt = f"Execute job {job_id} for run {self.run_root}"
                    await self.client.session.chat(
                        id=session_id,
                        parts=[{"type": "text", "text": prompt}],
                    )
                    consecutive_errors = 0
                    continue

                if operation == "ask_user":
                    job_id = result.get("job_id", "")
                    question = result.get("question", "")
                    question_id = await self.ask_user(job_id, question)
                    await self.poll_for_answer(question_id)
                    consecutive_errors = 0
                    continue

                await asyncio.sleep(self.poll_interval)
                consecutive_errors = 0

            except OrchestratorError as e:
                consecutive_errors += 1
                print(f"Error: {e}", file=sys.stderr)
                if consecutive_errors >= max_consecutive_errors:
                    recovery_plan = await self.spawn_recovery(str(e), {"error": str(e)})
                    if recovery_plan.get("action") == "abort":
                        return {"status": "aborted", "reason": str(e)}
                    consecutive_errors = 0
                await asyncio.sleep(self.poll_interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone orchestrator for job-orchestrator"
    )
    parser.add_argument(
        "--run",
        type=Path,
        required=True,
        help="Path to the run directory",
    )
    parser.add_argument(
        "--opencode-server",
        default="http://localhost:4096",
        help="opencode server URL (default: http://localhost:4096)",
    )
    parser.add_argument(
        "--opencode-session-id",
        required=True,
        help="Session ID for UI interaction",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds (default: 1.0)",
    )
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    orchestrator = JobOrchestrator(
        run_root=args.run,
        opencode_server=args.opencode_server,
        opencode_session_id=args.opencode_session_id,
        poll_interval=args.poll_interval,
    )

    try:
        result = await orchestrator.run()
        print(json.dumps(result, indent=2))
        return 0 if result.get("successful", False) else 1
    except OrchestratorError as e:
        print(f"Orchestrator error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1


def main() -> int:
    if not HAS_SDK:
        print("Error: opencode-ai package is required.", file=sys.stderr)
        print("Install with: pip install --pre opencode-ai", file=sys.stderr)
        return 1

    args = parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
