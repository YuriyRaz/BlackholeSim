"""Queue backend for orchestrator user interaction."""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from orchestrator_core import OrchestratorError, utc_now, write_json, load_json


class QueueBackend(ABC):
    """Abstract base class for question queue backends."""

    @abstractmethod
    def enqueue_question(
        self,
        run_root: Path,
        job_id: str,
        question: str,
        context: str = "",
    ) -> str:
        """Enqueue a user question and return a question_id."""

    @abstractmethod
    def check_answer(
        self,
        run_root: Path,
        question_id: str,
    ) -> dict[str, Any] | None:
        """Check if a question has been answered. Returns answer dict or None."""

    @abstractmethod
    def get_pending_questions(
        self,
        run_root: Path,
    ) -> list[dict[str, Any]]:
        """Get all unanswered questions for a run."""

    @abstractmethod
    def record_answer(
        self,
        run_root: Path,
        question_id: str,
        answer: str,
    ) -> dict[str, Any]:
        """Record an answer to a pending question."""


class FileQueueBackend(QueueBackend):
    """File-based queue backend managing .job-orchestrator/queue directory."""

    def _queue_dir(self, run_root: Path) -> Path:
        return run_root / "queue"

    def _question_path(self, run_root: Path, question_id: str) -> Path:
        return self._queue_dir(run_root) / f"{question_id}.json"

    def _generate_question_id(self, run_root: Path) -> str:
        queue_dir = self._queue_dir(run_root)
        existing = set()
        if queue_dir.exists():
            for f in queue_dir.glob("Q-*.json"):
                match = re.match(r"Q-(\d+)\.json", f.name)
                if match:
                    existing.add(int(match.group(1)))
        seq = 1
        while seq in existing:
            seq += 1
        return f"Q-{seq:03d}"

    def enqueue_question(
        self,
        run_root: Path,
        job_id: str,
        question: str,
        context: str = "",
    ) -> str:
        queue_dir = self._queue_dir(run_root)
        queue_dir.mkdir(parents=True, exist_ok=True)

        question_id = self._generate_question_id(run_root)
        record = {
            "question_id": question_id,
            "job_id": job_id,
            "question": question,
            "context": context,
            "status": "pending",
            "asked_at": utc_now(),
        }
        write_json(self._question_path(run_root, question_id), record)
        return question_id

    def check_answer(
        self,
        run_root: Path,
        question_id: str,
    ) -> dict[str, Any] | None:
        path = self._question_path(run_root, question_id)
        if not path.exists():
            return None
        record = load_json(path)
        if record.get("status") == "answered":
            return {
                "question_id": question_id,
                "answer": record.get("answer", ""),
                "answered_at": record.get("answered_at", ""),
            }
        return None

    def get_pending_questions(
        self,
        run_root: Path,
    ) -> list[dict[str, Any]]:
        queue_dir = self._queue_dir(run_root)
        if not queue_dir.exists():
            return []

        pending = []
        for path in sorted(queue_dir.glob("Q-*.json")):
            record = load_json(path)
            if record.get("status") == "pending":
                pending.append({
                    "question_id": record["question_id"],
                    "job_id": record["job_id"],
                    "question": record["question"],
                    "context": record.get("context", ""),
                    "asked_at": record["asked_at"],
                })
        return pending

    def record_answer(
        self,
        run_root: Path,
        question_id: str,
        answer: str,
    ) -> dict[str, Any]:
        path = self._question_path(run_root, question_id)
        if not path.exists():
            raise OrchestratorError(f"question {question_id!r} not found")

        record = load_json(path)
        if record.get("status") == "answered":
            raise OrchestratorError(f"question {question_id!r} already answered")

        record["status"] = "answered"
        record["answer"] = answer
        record["answered_at"] = utc_now()
        write_json(path, record)
        return record
