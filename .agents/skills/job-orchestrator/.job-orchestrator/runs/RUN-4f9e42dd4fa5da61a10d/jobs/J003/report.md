# J003 Report: Missing Tests for v5 Response Recovery

## Summary
Wrote 10 new tests covering 6 response recovery scenarios in `tests/test_v5_response_recovery.py`. All tests pass.

## Tests Written

### 1. Malformed Response → Format-Repair (2 tests)
- `test_malformed_json_triggers_format_repair` — Non-JSON response from a live session returns `operation: resume_job` with repair reason.
- `test_repair_prompt_includes_the_reason` — The appended prompt section contains "malformed JSON" and "Transport Response Repair".

### 2. Empty Response → Response-Retrieval (1 test)
- `test_empty_response_triggers_retrieval` — Empty response with `status=empty, session_liveness=live` returns `operation: resume_job`.

### 3. Root-Authored Outcome Rejection (2 tests)
- `test_invalid_artifact_digest_rejects_outcome` — Artifact with mismatched `content_sha256` raises `OrchestratorError("digest does not match")`.
- `test_rejected_outcome_does_not_change_job_status` — After rejection, job status and revision remain unchanged.

### 4. Cancellation Recovery (2 tests)
- `test_canceled_receipt_moves_to_recovering` — Canceled receipt sets job status to `recovering` with `recovery_required: True`.
- `test_next_returns_wait_when_job_is_recovering` — `select_v5_next_operation` returns `operation: wait` when job is recovering.

### 5. Replacement-Attempt History (2 tests)
- `test_recovery_authorized_replacement_appends_attempt` — After lost classification + recovery, old attempt retained, new dispatch created, job re-queued.
- `test_normal_scheduling_does_not_create_replacement_attempt` — Normal start dispatch has no prior attempts, `active_attempt_id` is None.

### 6. Interrupted Non-Idempotent Effect (1 test)
- `test_non_idempotent_job_requires_recovery_check` — `external_non_idempotent` job moves to `recovering` on canceled receipt; `next()` returns `wait`.

## Verification
```
tests/test_v5_response_recovery.py::MalformedResponseFormatRepairTest::test_malformed_json_triggers_format_repair PASSED
tests/test_v5_response_recovery.py::MalformedResponseFormatRepairTest::test_repair_prompt_includes_the_reason PASSED
tests/test_v5_response_recovery.py::EmptyResponseRetrievalTest::test_empty_response_triggers_retrieval PASSED
tests/test_v5_response_recovery.py::RootAuthoredOutcomeRejectionTest::test_invalid_artifact_digest_rejects_outcome PASSED
tests/test_v5_response_recovery.py::RootAuthoredOutcomeRejectionTest::test_rejected_outcome_does_not_change_job_status PASSED
tests/test_v5_response_recovery.py::CancellationRecoveryTest::test_canceled_receipt_moves_to_recovering PASSED
tests/test_v5_response_recovery.py::CancellationRecoveryTest::test_next_returns_wait_when_job_is_recovering PASSED
tests/test_v5_response_recovery.py::ReplacementAttemptHistoryTest::test_normal_scheduling_does_not_create_replacement_attempt PASSED
tests/test_v5_response_recovery.py::ReplacementAttemptHistoryTest::test_recovery_authorized_replacement_appends_attempt PASSED
tests/test_v5_response_recovery.py::InterruptedNonIdempotentEffectTest::test_non_idempotent_job_requires_recovery_check PASSED

10 passed in 3.15s
```
