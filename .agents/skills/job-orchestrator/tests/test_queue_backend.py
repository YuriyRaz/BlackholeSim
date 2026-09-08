"""Tests for queue_backend module."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


@pytest.fixture
def queue_backend():
    from queue_backend import FileQueueBackend
    return FileQueueBackend()


@pytest.fixture
def run_root(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "queue").mkdir()
    return run_dir


class TestFileQueueBackend:
    """Tests for FileQueueBackend."""

    def test_enqueue_question_creates_file(self, queue_backend, run_root):
        qid = queue_backend.enqueue_question(
            run_root, "JOB-001", "What is the answer?", context="test"
        )
        assert qid.startswith("Q-")
        queue_file = run_root / "queue" / f"{qid}.json"
        assert queue_file.exists()

    def test_enqueue_question_returns_sequential_ids(self, queue_backend, run_root):
        qid1 = queue_backend.enqueue_question(run_root, "JOB-001", "Q1")
        qid2 = queue_backend.enqueue_question(run_root, "JOB-002", "Q2")
        assert qid1 == "Q-001"
        assert qid2 == "Q-002"

    def test_enqueue_question_records_metadata(self, queue_backend, run_root):
        qid = queue_backend.enqueue_question(
            run_root, "JOB-001", "What?", context="ctx"
        )
        queue_file = run_root / "queue" / f"{qid}.json"
        import json
        record = json.loads(queue_file.read_text())
        assert record["question_id"] == qid
        assert record["job_id"] == "JOB-001"
        assert record["question"] == "What?"
        assert record["context"] == "ctx"
        assert record["status"] == "pending"
        assert "asked_at" in record

    def test_check_answer_returns_none_when_pending(self, queue_backend, run_root):
        qid = queue_backend.enqueue_question(run_root, "JOB-001", "Q1")
        result = queue_backend.check_answer(run_root, qid)
        assert result is None

    def test_check_answer_returns_answer_when_answered(self, queue_backend, run_root):
        qid = queue_backend.enqueue_question(run_root, "JOB-001", "Q1")
        queue_backend.record_answer(run_root, qid, "42")
        result = queue_backend.check_answer(run_root, qid)
        assert result is not None
        assert result["answer"] == "42"

    def test_check_answer_returns_none_for_nonexistent(self, queue_backend, run_root):
        result = queue_backend.check_answer(run_root, "Q-999")
        assert result is None

    def test_get_pending_questions_returns_empty_when_no_queue(self, queue_backend, tmp_path):
        run_root = tmp_path / "empty"
        run_root.mkdir()
        result = queue_backend.get_pending_questions(run_root)
        assert result == []

    def test_get_pending_questions_returns_pending_only(self, queue_backend, run_root):
        qid1 = queue_backend.enqueue_question(run_root, "JOB-001", "Q1")
        qid2 = queue_backend.enqueue_question(run_root, "JOB-002", "Q2")
        queue_backend.record_answer(run_root, qid1, "answer1")
        pending = queue_backend.get_pending_questions(run_root)
        assert len(pending) == 1
        assert pending[0]["question_id"] == qid2

    def test_get_pending_questions_sorted_by_id(self, queue_backend, run_root):
        queue_backend.enqueue_question(run_root, "JOB-002", "Q2")
        queue_backend.enqueue_question(run_root, "JOB-001", "Q1")
        pending = queue_backend.get_pending_questions(run_root)
        assert pending[0]["question_id"] == "Q-001"
        assert pending[1]["question_id"] == "Q-002"

    def test_record_answer_succeeds(self, queue_backend, run_root):
        qid = queue_backend.enqueue_question(run_root, "JOB-001", "Q1")
        record = queue_backend.record_answer(run_root, qid, "yes")
        assert record["status"] == "answered"
        assert record["answer"] == "yes"
        assert "answered_at" in record

    def test_record_answer_fails_for_nonexistent(self, queue_backend, run_root):
        from orchestrator_core import OrchestratorError
        with pytest.raises(OrchestratorError, match="not found"):
            queue_backend.record_answer(run_root, "Q-999", "answer")

    def test_record_answer_fails_for_already_answered(self, queue_backend, run_root):
        from orchestrator_core import OrchestratorError
        qid = queue_backend.enqueue_question(run_root, "JOB-001", "Q1")
        queue_backend.record_answer(run_root, qid, "first")
        with pytest.raises(OrchestratorError, match="already answered"):
            queue_backend.record_answer(run_root, qid, "second")
