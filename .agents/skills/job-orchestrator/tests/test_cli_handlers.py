"""Tests for jobctl CLI handlers (ask, answer, pending)."""

import argparse
import json
import pytest
import sys
from pathlib import Path
from io import StringIO
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


@pytest.fixture
def run_root(tmp_path):
    """Create a minimal run directory."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "jobs").mkdir()
    (run_dir / "queue").mkdir()
    (run_dir / "graph").mkdir()

    from orchestrator_core import write_json
    run_record = {
        "schema_version": 6,
        "run_id": "RUN-TEST",
        "status": "active",
        "protocol_revision": "v6-closed",
    }
    write_json(run_dir / "run.json", run_record)

    from graph_v6 import GraphState
    graph = GraphState(envelope={"campaign_id": "TEST"})
    graph.save(run_dir / "graph" / "graph.json")

    return run_dir


class TestAskCommand:
    """Tests for the ask command."""

    def test_ask_creates_question(self, run_root):
        from jobctl import ask_user

        args = argparse.Namespace(
            run=str(run_root),
            job="JOB-001",
            question="What should we do?",
            context="testing",
        )
        result = ask_user(args)

        assert result["operation"] == "ask_user"
        assert result["job_id"] == "JOB-001"
        assert result["question_id"].startswith("Q-")
        assert result["question"] == "What should we do?"

    def test_ask_prints_to_stdout(self, run_root, capsys):
        from jobctl import ask_user

        args = argparse.Namespace(
            run=str(run_root),
            job="JOB-001",
            question="What is the answer?",
            context="ctx",
        )
        ask_user(args)

        captured = capsys.readouterr()
        assert "[WORKER QUESTION]" in captured.out
        assert "Question ID: Q-001" in captured.out
        assert "Job ID: JOB-001" in captured.out
        assert "What is the answer?" in captured.out
        assert "Context: ctx" in captured.out

    def test_ask_fails_for_inactive_run(self, run_root):
        from jobctl import ask_user
        from orchestrator_core import write_json, OrchestratorError

        run_record = json.loads((run_root / "run.json").read_text())
        run_record["status"] = "completed"
        write_json(run_root / "run.json", run_record)

        args = argparse.Namespace(
            run=str(run_root),
            job="JOB-001",
            question="Q?",
            context="",
        )
        with pytest.raises(OrchestratorError, match="not active"):
            ask_user(args)

    def test_ask_fails_for_missing_run(self, tmp_path):
        from jobctl import ask_user
        from orchestrator_core import OrchestratorError

        args = argparse.Namespace(
            run=str(tmp_path / "nonexistent"),
            job="JOB-001",
            question="Q?",
            context="",
        )
        with pytest.raises(OrchestratorError, match="run not found"):
            ask_user(args)


class TestAnswerCommand:
    """Tests for the answer command."""

    def test_answer_with_question_id(self, run_root):
        from jobctl import ask_user, record_answer

        ask_args = argparse.Namespace(
            run=str(run_root),
            job="JOB-001",
            question="What?",
            context="",
        )
        ask_user(ask_args)

        answer_args = argparse.Namespace(
            run=str(run_root),
            job="",
            question_id="Q-001",
            answer="42",
        )
        result = record_answer(answer_args)

        assert result["operation"] == "resume_job"
        assert result["job_id"] == "JOB-001"
        assert result["question_id"] == "Q-001"
        assert result["answer"] == "42"

    def test_answer_with_job_id(self, run_root):
        from jobctl import record_answer

        job_dir = run_root / "jobs" / "JOB-002"
        job_dir.mkdir()
        from orchestrator_core import write_json
        write_json(job_dir / "job.json", {
            "schema_version": 6,
            "job_id": "JOB-002",
            "status": "waiting",
            "revision": 1,
            "question": "test question",
        })

        answer_args = argparse.Namespace(
            run=str(run_root),
            job="JOB-002",
            question_id="",
            answer="yes",
        )
        result = record_answer(answer_args)

        assert result["operation"] == "resume_job"
        assert result["job_id"] == "JOB-002"
        assert result["answer"] == "yes"

    def test_answer_fails_without_job_or_question_id(self, run_root):
        from jobctl import record_answer
        from orchestrator_core import OrchestratorError

        answer_args = argparse.Namespace(
            run=str(run_root),
            job="",
            question_id="",
            answer="yes",
        )
        with pytest.raises(OrchestratorError, match="must specify"):
            record_answer(answer_args)


class TestPendingCommand:
    """Tests for the pending command."""

    def test_pending_empty_queue(self, run_root):
        from jobctl import list_pending

        args = argparse.Namespace(run=str(run_root))
        result = list_pending(args)

        assert result["count"] == 0
        assert result["pending"] == []

    def test_pending_returns_unanswered(self, run_root):
        from jobctl import ask_user, list_pending

        ask_args = argparse.Namespace(
            run=str(run_root),
            job="JOB-001",
            question="Q1?",
            context="",
        )
        ask_user(ask_args)

        ask_args = argparse.Namespace(
            run=str(run_root),
            job="JOB-002",
            question="Q2?",
            context="",
        )
        ask_user(ask_args)

        args = argparse.Namespace(run=str(run_root))
        result = list_pending(args)

        assert result["count"] == 2
        assert len(result["pending"]) == 2

    def test_pending_excludes_answered(self, run_root):
        from jobctl import ask_user, record_answer, list_pending

        ask_args = argparse.Namespace(
            run=str(run_root),
            job="JOB-001",
            question="Q1?",
            context="",
        )
        ask_user(ask_args)

        answer_args = argparse.Namespace(
            run=str(run_root),
            job="",
            question_id="Q-001",
            answer="done",
        )
        record_answer(answer_args)

        args = argparse.Namespace(run=str(run_root))
        result = list_pending(args)

        assert result["count"] == 0
        assert result["pending"] == []
