"""Shared version-3 job-orchestrator persistence and validation primitives."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

PROTOCOL_VERSION = 3
SCHEMA_VERSION = 3
TERMINAL_JOBS = {"completed", "completed_with_concerns", "failed", "canceled"}
ACTIVE_DISPATCHES = {"recorded", "sent", "running", "status_requested"}
DEFAULT_POLICY = {
    "dispatch_bounds": {
        "max_work_units": 8,
        "max_edit_roots": 4,
        "max_estimated_minutes": 90,
        "require_override_when_exceeded": True,
    },
    "liveness": {
        "stale_after_seconds": 900,
        "status_timeout_seconds": 300,
        "lease_seconds": 30,
    },
}


class OrchestratorError(RuntimeError):
    """A deterministic validation or transition error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise OrchestratorError("timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OrchestratorError(f"invalid RFC 3339 timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OrchestratorError(f"timestamp must include a UTC offset: {value!r}")
    return parsed.astimezone(timezone.utc)


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise OrchestratorError(f"value is not canonical JSON: {exc}") from exc


def content_hash(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(data).hexdigest()


def stable_id(prefix: str, *parts: Any) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,15}", prefix):
        raise OrchestratorError("ID prefix must be 1-16 uppercase ASCII characters")
    if not parts:
        raise OrchestratorError("stable ID requires at least one identity part")
    seed = b"\0".join(
        part if isinstance(part, bytes) else canonical_bytes(part) for part in parts
    )
    return f"{prefix}-{hashlib.sha256(seed).hexdigest()[:20]}"


def random_id(prefix: str) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,15}", prefix):
        raise OrchestratorError("ID prefix must be 1-16 uppercase ASCII characters")
    return f"{prefix}-{uuid.uuid4().hex[:20]}"


def _analyze_json_failure(text: str, exc: json.JSONDecodeError) -> str:
    lines = text.splitlines()
    error_line = exc.lineno
    context = lines[error_line - 1].strip() if 0 < error_line <= len(lines) else ""
    
    partial_info = ""
    text_stripped = text.lstrip()
    if text_stripped.startswith("["):
        depth = 0
        count = 0
        in_string = False
        escape = False
        for char in text_stripped:
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
            elif char == '"':
                in_string = not in_string
            elif not in_string:
                if char in '[{':
                    depth += 1
                elif char in ']}':
                    depth -= 1
                    if depth == 1 and char == '}':
                        count += 1
        partial_info = f"\nBest effort partial read: Found {count} complete top-level objects before failure."

    return (
        f"JSON truncation or syntax error at line {error_line} (col {exc.colno}): {exc.msg}.\n"
        f"Context: `{context}`{partial_info}\n"
        f"Please append missing data or use targeted edits instead of rewriting the entire file."
    )


def load_json(path: Path) -> Any:
    text = ""
    try:
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"^\s*```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
        return json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        if isinstance(exc, json.JSONDecodeError):
            message = _analyze_json_failure(text, exc)
            raise OrchestratorError(f"cannot read valid JSON from {path}:\n{message}") from exc
        raise OrchestratorError(f"cannot read valid JSON from {path}: {exc}") from exc


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.01 * (attempt + 1))
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def write_json(path: Path, value: Any) -> None:
    try:
        rendered = json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise OrchestratorError(f"cannot persist non-JSON value to {path}: {exc}") from exc
    atomic_write(path, rendered.encode("utf-8") + b"\n")


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(canonical_bytes(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise OrchestratorError(f"invalid JSONL at {path}:{number}: {exc}") from exc
    return records


class Lease:
    def __init__(self, path: Path, controller: str, seconds: int = 30):
        if seconds <= 0:
            raise OrchestratorError("lease duration must be positive")
        self.path, self.controller, self.seconds = path, controller, seconds
        self.lease_id: str | None = None

    def acquire(self, *, handoff_from: str | None = None) -> None:
        with _lease_guard(self.path):
            now = datetime.now(timezone.utc)
            current = load_json(self.path) if self.path.exists() else None
            if current and parse_time(current["expires_at"]) > now:
                owner = current.get("controller_id")
                handoff = current.get("handoff")
                allowed_handoff = (
                    handoff
                    and handoff.get("from_controller_id") == owner
                    and handoff.get("to_controller_id") == self.controller
                    and handoff_from in {None, owner}
                )
                if not allowed_handoff:
                    raise OrchestratorError(
                        f"lease held by {owner} until {current['expires_at']}"
                    )
            self.lease_id = random_id("LEASE")
            self._write(now, acquired_at=utc_now())

    def _write(
        self, now: datetime, *, acquired_at: str, handoff: dict[str, Any] | None = None
    ) -> None:
        write_json(
            self.path,
            {
                "schema_version": SCHEMA_VERSION,
                "lease_id": self.lease_id,
                "controller_id": self.controller,
                "acquired_at": acquired_at,
                "expires_at": (now + timedelta(seconds=self.seconds))
                .isoformat()
                .replace("+00:00", "Z"),
                "heartbeat": time.time_ns(),
                "handoff": handoff,
            },
        )

    def renew(self) -> None:
        with _lease_guard(self.path):
            current = load_json(self.path)
            now = datetime.now(timezone.utc)
            if (
                current.get("controller_id") != self.controller
                or current.get("lease_id") != self.lease_id
            ):
                raise OrchestratorError("cannot renew a lease owned by another controller")
            if parse_time(current["expires_at"]) <= now:
                raise OrchestratorError("cannot renew an expired lease")
            self._write(
                now,
                acquired_at=current["acquired_at"],
                handoff=current.get("handoff"),
            )

    def handoff(self, to_controller: str) -> None:
        if not to_controller or to_controller == self.controller:
            raise OrchestratorError("handoff requires a different target controller")
        with _lease_guard(self.path):
            current = load_json(self.path)
            now = datetime.now(timezone.utc)
            if (
                current.get("controller_id") != self.controller
                or current.get("lease_id") != self.lease_id
            ):
                raise OrchestratorError("cannot hand off a lease owned by another controller")
            if parse_time(current["expires_at"]) <= now:
                raise OrchestratorError("cannot hand off an expired lease")
            current["handoff"] = {
                "from_controller_id": self.controller,
                "to_controller_id": to_controller,
                "recorded_at": utc_now(),
            }
            write_json(self.path, current)

    def release(self) -> None:
        with _lease_guard(self.path):
            if not self.path.exists():
                return
            current = load_json(self.path)
            if (
                current.get("controller_id") == self.controller
                and current.get("lease_id") == self.lease_id
                and not current.get("handoff")
            ):
                self.path.unlink()

    def __enter__(self) -> "Lease":
        self.acquire()
        return self

    def __exit__(self, *_: Any) -> None:
        self.release()


@contextmanager
def _lease_guard(path: Path, timeout: float = 10.0) -> Iterator[None]:
    """Serialize lease compare-and-replace operations with an OS file lock."""
    guard = path.with_name(f".{path.name}.guard")
    guard.parent.mkdir(parents=True, exist_ok=True)
    stream = guard.open("a+b")
    deadline = time.monotonic() + timeout
    locked = False
    try:
        while not locked:
            try:
                if os.name == "nt":
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise OrchestratorError(f"timed out acquiring lease guard {guard}")
                time.sleep(0.01)
        yield
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


@contextmanager
def run_lease(run_root: Path, controller: str) -> Iterator[Lease]:
    policy = effective_policy(run_root)
    lease = Lease(
        run_root / "orchestrator.lock",
        controller,
        policy["liveness"]["lease_seconds"],
    )
    with lease:
        yield lease


def effective_policy(run_root: Path) -> dict[str, Any]:
    policy = json.loads(json.dumps(DEFAULT_POLICY))
    setup_path = run_root / "setup.json"
    if setup_path.exists():
        configured = load_json(setup_path).get("policies", {})
        for section in ("dispatch_bounds", "liveness"):
            policy[section].update(configured.get(section, {}))
    return policy


SCHEMA_ROOT = Path(__file__).resolve().parent.parent / "schemas"
_SCHEMA_CACHE: dict[tuple[int, str], dict[str, Any]] = {}


def load_schema(kind: str, version: int = SCHEMA_VERSION) -> dict[str, Any]:
    key = (version, kind)
    if key not in _SCHEMA_CACHE:
        path = SCHEMA_ROOT / f"v{version}" / f"{kind}.schema.json"
        if not path.is_file():
            raise OrchestratorError(f"unsupported schema {kind!r} version {version}")
        schema = load_json(path)
        if not isinstance(schema, dict):
            raise OrchestratorError(f"schema {path} must be a JSON object")
        _SCHEMA_CACHE[key] = schema
    return _SCHEMA_CACHE[key]


def _matches_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and not (isinstance(value, float) and not math.isfinite(value))
        ),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _validate_schema(value: Any, schema: dict[str, Any], location: str) -> None:
    def _raise(msg: str) -> None:
        raise OrchestratorError(f"Schema validation error at `{location}`: {msg}. Please cross-reference `schemas/v3/` and apply targeted edits to fix.")

    expected = schema.get("type")
    if expected is not None:
        choices = [expected] if isinstance(expected, str) else expected
        if not any(_matches_type(value, choice) for choice in choices):
            _raise(f"must have type {' or '.join(choices)}")
    if "const" in schema and value != schema["const"]:
        _raise(f"must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        _raise(f"must be one of {schema['enum']!r}")
    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [name for name in required if name not in value]
        if missing:
            _raise(f"missing fields: {', '.join(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                _raise(f"has unexpected fields: {', '.join(extra)}")
        for name, child in properties.items():
            if name in value:
                _validate_schema(value[name], child, f"{location}.{name}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            _raise(f"must contain at least {schema['minItems']} items")
        if schema.get("uniqueItems"):
            encoded = [canonical_bytes(item) for item in value]
            if len(encoded) != len(set(encoded)):
                _raise(f"must contain unique items")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_schema(item, schema["items"], f"{location}[{index}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            _raise(f"must contain at least {schema['minLength']} characters")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            _raise(f"has an invalid format")
        if schema.get("format") == "date-time":
            parse_time(value)
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and "minimum" in schema
        and value < schema["minimum"]
    ):
        _raise(f"must be at least {schema['minimum']}")


def validate_record(kind: str, value: dict[str, Any]) -> None:
    if not isinstance(value, dict):
        raise OrchestratorError(f"{kind} must be a JSON object")
    version = value.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise OrchestratorError(f"{kind}.schema_version must be an integer")
    _validate_schema(value, load_schema(kind, version), kind)
    if kind == "lifecycle-event":
        _validate_lifecycle_data(value)


_EVENT_DATA_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "run_status": ({"status"}, set()),
    "job_compiled": ({"job", "workflow", "steps"}, set()),
    "session_acknowledged": (
        {
            "schema_version", "protocol_version", "protocol_sha256", "job_id",
            "contract_revision", "current_workflow_node_id", "acknowledged_at",
        },
        {"session_id"},
    ),
    "action_created": ({"action"}, set()),
    "action_response_received": ({"action_id", "response_hash"}, set()),
    "action_resolved": ({"action_id", "response_hash"}, set()),
    "dispatch_created": ({"dispatch"}, set()),
    "dispatch_updated": ({"dispatch_id", "changes"}, set()),
    "worker_result": ({"dispatch_id", "result"}, {"child_job_ids"}),
    "session_lost": ({"job_id"}, {"checkpoint_sha256", "reason"}),
    "resolution_recorded": ({"job_id", "response"}, set()),
    "user_answered": ({"job_id", "response"}, set()),
    "child_job_requested": ({"request"}, set()),
    "child_job_validated": ({"request_id", "child_job_id"}, set()),
    "child_job_materialized": (
        {"request_id", "child_job_id", "report_path"},
        set(),
    ),
    "child_job_acknowledged": ({"request_id"}, {"job_id"}),
    "protocol_migrated": (
        {
            "from", "to", "authorized_by", "reason", "protocol_sha256",
            "protocol_text", "manifest", "contracts", "contract_hashes",
        },
        set(),
    ),
}


def _validate_lifecycle_data(event: dict[str, Any]) -> None:
    event_type = event["type"]
    required, optional = _EVENT_DATA_FIELDS[event_type]
    data = event["data"]
    missing = sorted(required - set(data))
    extra = sorted(set(data) - required - optional)
    if missing:
        raise OrchestratorError(
            f"lifecycle-event.data missing fields for {event_type}: "
            + ", ".join(missing)
        )
    if extra:
        raise OrchestratorError(
            f"lifecycle-event.data has unexpected fields for {event_type}: "
            + ", ".join(extra)
        )
    nested_kind = {
        "session_acknowledged": ("acknowledgement", data),
        "action_created": ("action", data.get("action")),
        "dispatch_created": ("dispatch", data.get("dispatch")),
        "worker_result": ("result", data.get("result")),
    }.get(event_type)
    if nested_kind:
        validate_record(*nested_kind)


def validate_schema(kind: str, value: dict[str, Any]) -> None:
    """Public schema-validation name used by both control-plane CLIs."""
    validate_record(kind, value)


def validate_dispatch(dispatch: dict[str, Any], policy: dict[str, Any]) -> None:
    validate_record("dispatch", dispatch)
    for field in (
        "work_units", "acceptance_criteria", "required_checks",
        "prohibited_actions", "checkpoint_policy",
    ):
        if not dispatch[field]:
            raise OrchestratorError(f"dispatch {field} must not be empty")
    if dispatch["side_effect_class"] != "read_only" and not dispatch["recovery_check"]:
        raise OrchestratorError("write-capable dispatch requires recovery_check")
    bounds = policy["dispatch_bounds"]
    exceeded = (
        len(dispatch["work_units"]) > bounds["max_work_units"]
        or len(dispatch.get("allowed_edit_roots", [])) > bounds["max_edit_roots"]
        or dispatch.get("estimated_minutes", 0) > bounds["max_estimated_minutes"]
    )
    override = dispatch.get("unbounded_override")
    if exceeded and bounds["require_override_when_exceeded"]:
        if not override or not all(
            override.get(key) for key in ("reason", "authorized_by", "recovery_policy")
        ):
            raise OrchestratorError("dispatch exceeds bounds without explicit override")


def append_event(run_root: Path, event: dict[str, Any]) -> bool:
    validate_record("lifecycle-event", event)
    journal = run_root / "events.jsonl"
    events = read_jsonl(journal)
    by_id = {item["event_id"]: item for item in events}
    if event["event_id"] in by_id:
        if content_hash(by_id[event["event_id"]]) != content_hash(event):
            raise OrchestratorError("event ID collision with different content")
        return False
    if events:
        expected = events[-1]["revision"] + 1
        if event["revision"] != expected:
            raise OrchestratorError(
                f"stale revision {event['revision']}; expected {expected}"
            )
    elif event["revision"] != 1:
        raise OrchestratorError("first event revision must be 1")
    correlation = event["correlation_id"]
    for existing in events:
        if (
            existing["correlation_id"] == correlation
            and existing["type"] == event["type"]
            and content_hash(existing["data"]) != content_hash(event["data"])
        ):
            raise OrchestratorError("correlation reused with conflicting event data")
    append_jsonl(journal, event)
    return True


def make_event(
    run_root: Path, event_type: str, correlation_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    run = load_json(run_root / "run.json")
    revision = len(read_jsonl(run_root / "events.jsonl")) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": stable_id("EV", run["run_id"], event_type, correlation_id, data),
        "type": event_type,
        "run_id": run["run_id"],
        "revision": revision,
        "correlation_id": correlation_id,
        "created_at": utc_now(),
        "data": data,
    }


def replay(run_root: Path) -> dict[str, Any]:
    """Project lifecycle events into deterministic, rebuildable snapshots."""
    base = load_json(run_root / "run.json")
    state: dict[str, Any] = {
        "run": {**base, "active_job_id": None, "active_dispatch_id": None},
        "jobs": {},
        "workflows": {},
        "steps": {},
        "sessions": {},
        "actions": {},
        "dispatches": {},
        "child_requests": {},
        "record_responses": {},
    }
    previous_revision = 0
    previous_created_at: datetime | None = None
    for event in read_jsonl(run_root / "events.jsonl"):
        validate_record("lifecycle-event", event)
        if event["run_id"] != state["run"]["run_id"]:
            raise OrchestratorError(
                f"event {event['event_id']} belongs to a different run"
            )
        if event["revision"] != previous_revision + 1:
            raise OrchestratorError(
                f"event {event['event_id']} has non-sequential revision "
                f"{event['revision']}; expected {previous_revision + 1}"
            )
        created_at = parse_time(event["created_at"])
        if previous_created_at is not None and created_at < previous_created_at:
            raise OrchestratorError("event timestamps move backwards")
        previous_revision = event["revision"]
        previous_created_at = created_at
        data, kind = event["data"], event["type"]
        if kind == "run_status":
            state["run"]["status"] = data["status"]
        elif kind == "job_compiled":
            if data["job"]["id"] in state["jobs"]:
                raise OrchestratorError(f"job {data['job']['id']} compiled twice")
            state["jobs"][data["job"]["id"]] = data["job"]
            state["workflows"][data["job"]["id"]] = data["workflow"]
            state["steps"][data["job"]["id"]] = data["steps"]
        elif kind == "session_acknowledged":
            validate_record("acknowledgement", data)
            if data["job_id"] not in state["jobs"]:
                raise OrchestratorError("session acknowledgement references unknown job")
            state["sessions"][data["job_id"]] = data
            state["jobs"][data["job_id"]]["session"] = data
        elif kind == "action_created":
            validate_record("action", data["action"])
            if data["action"]["action_id"] in state["actions"]:
                raise OrchestratorError("action created twice")
            state["actions"][data["action"]["action_id"]] = data["action"]
        elif kind == "action_response_received":
            action_id = data["action_id"]
            if action_id not in state["actions"]:
                raise OrchestratorError("recorded response references unknown action")
            existing = state["record_responses"].get(action_id)
            if existing and existing != data["response_hash"]:
                raise OrchestratorError("action response identity changed")
            state["record_responses"][action_id] = data["response_hash"]
        elif kind == "action_resolved":
            if data["action_id"] not in state["actions"]:
                raise OrchestratorError("resolved action does not exist")
            action = state["actions"][data["action_id"]]
            if action["status"] != "unresolved":
                raise OrchestratorError("action resolved more than once")
            action.update(status="resolved", response_hash=data["response_hash"])
        elif kind == "dispatch_created":
            dispatch = data["dispatch"]
            validate_record("dispatch", dispatch)
            if dispatch["dispatch_id"] in state["dispatches"]:
                raise OrchestratorError("dispatch created twice")
            if dispatch["job_id"] not in state["jobs"]:
                raise OrchestratorError("dispatch references unknown job")
            workflow = state["workflows"][dispatch["job_id"]]
            nodes = {node["id"]: node for node in workflow["nodes"]}
            if dispatch["workflow_node_id"] not in nodes:
                raise OrchestratorError("dispatch references unknown workflow node")
            if not set(dispatch["work_units"]).issubset(nodes[dispatch["workflow_node_id"]]["work_units"]):
                raise OrchestratorError("dispatch contains work outside its workflow node")
            state["dispatches"][dispatch["dispatch_id"]] = dispatch
            state["run"]["active_dispatch_id"] = dispatch["dispatch_id"]
            state["run"]["active_job_id"] = dispatch["job_id"]
        elif kind == "dispatch_updated":
            if data["dispatch_id"] not in state["dispatches"]:
                raise OrchestratorError("dispatch update references unknown dispatch")
            dispatch = state["dispatches"][data["dispatch_id"]]
            updated_dispatch = {**dispatch, **data["changes"]}
            validate_record("dispatch", updated_dispatch)
            dispatch.update(data["changes"])
            if dispatch.get("status") in ACTIVE_DISPATCHES | {"interrupted"}:
                state["run"]["active_dispatch_id"] = dispatch["dispatch_id"]
                state["run"]["active_job_id"] = dispatch["job_id"]
            elif state["run"].get("active_dispatch_id") == dispatch["dispatch_id"]:
                state["run"]["active_dispatch_id"] = None
                state["run"]["active_job_id"] = None
        elif kind == "worker_result":
            validate_record("result", data["result"])
            if data["dispatch_id"] not in state["dispatches"]:
                raise OrchestratorError("worker result references unknown dispatch")
            dispatch = state["dispatches"][data["dispatch_id"]]
            if dispatch.get("status") not in ACTIVE_DISPATCHES:
                raise OrchestratorError("worker result references an inactive dispatch")
            if (
                data["result"]["dispatch_id"] != dispatch["dispatch_id"]
                or data["result"]["nonce"] != dispatch["nonce"]
            ):
                raise OrchestratorError("worker result identity does not match dispatch")
            dispatch.update(status="resolved", result=data["result"])
            state["run"]["active_dispatch_id"] = None
            state["run"]["active_job_id"] = None
            _apply_result(state, dispatch, data["result"])
        elif kind == "session_lost":
            if data["job_id"] not in state["jobs"]:
                raise OrchestratorError("lost session references unknown job")
            state["sessions"].pop(data["job_id"], None)
            state["jobs"][data["job_id"]]["session"] = None
        elif kind == "child_job_requested":
            request = dict(data["request"])
            request["status"] = "proposed"
            if request["request_id"] in state["child_requests"]:
                raise OrchestratorError("child job request proposed twice")
            if request["parent_job_id"] not in state["jobs"]:
                raise OrchestratorError("child job request references unknown parent")
            state["child_requests"][request["request_id"]] = request
        elif kind == "child_job_validated":
            request = state["child_requests"].get(data["request_id"])
            if not request or request["status"] != "proposed":
                raise OrchestratorError("child job validation lacks proposed request")
            request["status"] = "validated"
            request["child_job_id"] = data["child_job_id"]
        elif kind == "child_job_materialized":
            request = state["child_requests"].get(data["request_id"])
            if not request or request["status"] != "validated":
                raise OrchestratorError("child job materialization lacks validation")
            if data["child_job_id"] not in state["jobs"]:
                raise OrchestratorError("materialized child job does not exist")
            request["status"] = "materialized"
            request["child_job_id"] = data["child_job_id"]
            request["report_path"] = data["report_path"]
        elif kind == "child_job_acknowledged":
            request = state["child_requests"].get(data["request_id"])
            if not request or request["status"] != "materialized":
                raise OrchestratorError("child job acknowledgement is not pending")
            request["status"] = "acknowledged"
            request["acknowledged_at"] = event["created_at"]
        elif kind == "protocol_migrated":
            state["run"]["schema_version"] = SCHEMA_VERSION
            state["run"].setdefault("mode", "sequential")
            state["run"]["protocol"].update(
                version=data["to"], sha256=data["protocol_sha256"]
            )
            for job_id, contract_hash in data.get("contract_hashes", {}).items():
                if job_id in state["jobs"]:
                    state["jobs"][job_id]["contract_sha256"] = contract_hash
                    state["jobs"][job_id]["session"] = None
                    state["sessions"].pop(job_id, None)
            for dispatch in state["dispatches"].values():
                if dispatch.get("status") in ACTIVE_DISPATCHES:
                    dispatch.update(
                        status="interrupted",
                        interruption_class="protocol_migration",
                        interrupted_at=event["created_at"],
                    )
            for action in state["actions"].values():
                if action["status"] == "unresolved":
                    action.update(
                        status="resolved",
                        response_hash=content_hash({
                            "invalidated_by": event["event_id"],
                            "reason": "protocol_migration",
                        }),
                    )
            interrupted = [
                dispatch for dispatch in state["dispatches"].values()
                if dispatch.get("status") == "interrupted"
            ]
            state["run"]["active_dispatch_id"] = (
                interrupted[0]["dispatch_id"] if interrupted else None
            )
            state["run"]["active_job_id"] = (
                interrupted[0]["job_id"] if interrupted else None
            )
        elif kind in {"resolution_recorded", "user_answered"}:
            job = state["jobs"][data["job_id"]]
            job["status"] = "queued"
            node = next(item for item in state["workflows"][data["job_id"]]["nodes"]
                        if item["id"] == job["current_workflow_node_id"])
            node["status"] = "ready"
        state["run"]["revision"] = event["revision"]
        state["run"]["updated_at"] = event["created_at"]
    validate_state(state)
    return state


def _apply_result(state: dict[str, Any], dispatch: dict[str, Any], result: dict[str, Any]) -> None:
    job_id, node_id = dispatch["job_id"], dispatch["workflow_node_id"]
    workflow = state["workflows"][job_id]
    node = next(item for item in workflow["nodes"] if item["id"] == node_id)
    complete = set(node.get("completed_work_units", []))
    complete.update(result.get("completed_work_units", dispatch["work_units"]))
    node["completed_work_units"] = sorted(complete)
    remaining = [unit for unit in node["work_units"] if unit not in complete]
    if result["status"] == "completed" and not remaining and not result.get("blocking_issues"):
        node["status"] = "completed"
        later = sorted(workflow["nodes"], key=lambda item: item["position"])
        following = next((item for item in later if item["position"] > node["position"]), None)
        if following:
            following["status"] = "ready"
            state["jobs"][job_id]["current_workflow_node_id"] = following["id"]
        else:
            state["jobs"][job_id]["status"] = "completed"
            state["jobs"][job_id]["current_workflow_node_id"] = None
    elif result["status"] == "blocked":
        node["status"] = "blocked"
        state["jobs"][job_id]["status"] = "blocked"
    else:
        node["status"] = "ready"


def validate_state(state: dict[str, Any]) -> None:
    active = [
        item for item in state["dispatches"].values()
        if item.get("status") in ACTIVE_DISPATCHES
    ]
    owned = [
        item for item in state["dispatches"].values()
        if item.get("status") in ACTIVE_DISPATCHES | {"interrupted"}
    ]
    if state["run"].get("mode", "sequential") == "sequential" and len(owned) > 1:
        raise OrchestratorError("sequential run has multiple active dispatches")
    active_id = owned[0]["dispatch_id"] if owned else None
    active_job_id = owned[0]["job_id"] if owned else None
    if state["run"].get("active_dispatch_id") != active_id:
        raise OrchestratorError("run active dispatch pointer disagrees with dispatch state")
    if state["run"].get("active_job_id") != active_job_id:
        raise OrchestratorError("run active job pointer disagrees with dispatch state")
    for job_id, job in state["jobs"].items():
        if job.get("status") == "running" and job_id not in state["sessions"]:
            raise OrchestratorError(f"running job {job_id} lacks acknowledged session")
        for dependency in job.get("depends_on", []):
            if dependency not in state["jobs"]:
                raise OrchestratorError(f"job {job_id} has unknown dependency {dependency}")
        workflow = state["workflows"].get(job_id)
        steps = state["steps"].get(job_id)
        if workflow is None or steps is None:
            raise OrchestratorError(f"job {job_id} lacks workflow or step projection")
        nodes = sorted(workflow["nodes"], key=lambda item: item["position"])
        if len({node["id"] for node in nodes}) != len(nodes):
            raise OrchestratorError(f"job {job_id} has duplicate workflow node IDs")
        completed_seen = True
        for node in nodes:
            completed = set(node.get("completed_work_units", []))
            if not completed.issubset(set(node["work_units"])):
                raise OrchestratorError(f"workflow node {node['id']} has unknown completed work")
            if node["status"] == "completed" and completed != set(node["work_units"]):
                raise OrchestratorError(f"workflow node {node['id']} completed prematurely")
            if node["status"] in {"ready", "running", "blocked"} and not completed_seen:
                raise OrchestratorError(f"workflow node {node['id']} advanced before its predecessor")
            completed_seen = completed_seen and node["status"] == "completed"
        if job.get("current_workflow_node_id") is not None:
            current = [node for node in nodes if node["id"] == job["current_workflow_node_id"]]
            if len(current) != 1 or current[0]["status"] not in {"ready", "running", "blocked"}:
                raise OrchestratorError(f"job {job_id} has invalid current workflow node")
    for dispatch in active:
        job_id = dispatch["job_id"]
        if job_id not in state["sessions"]:
            raise OrchestratorError(f"active dispatch {dispatch['dispatch_id']} lacks session")
        if state["sessions"][job_id].get("contract_revision") != dispatch["contract_revision"]:
            raise OrchestratorError("dispatch/session contract revision mismatch")
        if state["sessions"][job_id].get("protocol_sha256") != dispatch["protocol_sha256"]:
            raise OrchestratorError("dispatch/session protocol hash mismatch")
        if state["jobs"][job_id].get("current_workflow_node_id") != dispatch["workflow_node_id"]:
            raise OrchestratorError("active dispatch is not on the current workflow node")
    for request in state["child_requests"].values():
        parent_id = request["parent_job_id"]
        if request["status"] in {"materialized", "acknowledged"}:
            child_id = request.get("child_job_id")
            child = state["jobs"].get(child_id)
            if not child or child.get("parent_job_id") != parent_id:
                raise OrchestratorError("child request/job parent linkage mismatch")


def snapshot_documents(state: dict[str, Any]) -> dict[Path, Any]:
    """Return every journal-derived document keyed by its run-relative path."""
    documents: dict[Path, Any] = {Path("run.json"): state["run"]}
    entries = []
    for job_id, job in sorted(state["jobs"].items()):
        job_root = Path("jobs") / job_id
        documents[job_root / "job.json"] = job
        documents[job_root / "workflow.json"] = state["workflows"][job_id]
        documents[job_root / "steps.json"] = state["steps"][job_id]
        entries.append({
            "job_id": job_id,
            "priority": job.get("priority", 50),
            "sequence": job.get("sequence", 0),
            "depends_on": job.get("depends_on", []),
        })
    documents[Path("queue.json")] = {
        "mode": state["run"].get("mode", "sequential"),
        "entries": entries,
    }
    documents[Path("jobs") / "index.json"] = {"jobs": sorted(state["jobs"])}
    for action in state["actions"].values():
        documents[Path("actions") / f"{action['action_id']}.json"] = action
    for dispatch in state["dispatches"].values():
        documents[
            Path("jobs") / dispatch["job_id"] / "dispatches"
            / f"{dispatch['dispatch_id']}.json"
        ] = dispatch
    return documents


def snapshot_differences(run_root: Path, state: dict[str, Any]) -> list[str]:
    """Compare every expected derived document to the replay projection."""
    differences = []
    for relative, expected in sorted(
        snapshot_documents(state).items(), key=lambda item: str(item[0])
    ):
        path = run_root / relative
        if not path.is_file():
            differences.append(f"{relative} snapshot missing")
            continue
        try:
            actual = load_json(path)
        except OrchestratorError as exc:
            differences.append(f"{relative} snapshot invalid: {exc}")
            continue
        if content_hash(actual) != content_hash(expected):
            differences.append(f"{relative} snapshot disagrees with journal")
    return differences


def write_snapshots(run_root: Path, state: dict[str, Any]) -> None:
    for relative, value in snapshot_documents(state).items():
        write_json(run_root / relative, value)


def mutate(run_root: Path, controller: str, event: dict[str, Any]) -> dict[str, Any]:
    with run_lease(run_root, controller):
        append_event(run_root, event)
        state = replay(run_root)
        write_snapshots(run_root, state)
        return state
