"""Shared job-orchestrator persistence and validation primitives."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import socket
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

CURRENT_RUN_VERSION = 4
WORKER_CONTRACT_PATH = (
    Path(__file__).resolve().parent.parent / "references" / "job-protocol.md"
)


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
        "Preserve the malformed input as evidence and use the owning command's "
        "recovery path."
    )


def load_json(path: Path) -> Any:
    text = ""
    try:
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"^\s*```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
        return json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        if isinstance(exc, json.JSONDecodeError):
            message = _analyze_json_failure(text, exc)
            raise OrchestratorError(f"cannot read valid JSON from {path}:\n{message}") from exc
        raise OrchestratorError(f"cannot read valid JSON from {path}: {exc}") from exc


def require_run_version(run_root: Path, expected_version: int = CURRENT_RUN_VERSION) -> int:
    """Ensure this v4-only control plane owns the persisted run."""
    run_path = run_root / "run.json"
    document = load_json(run_path)
    if not isinstance(document, dict):
        raise OrchestratorError(f"persisted run document must be an object: {run_path}")

    markers: list[tuple[str, Any]] = []
    if "schema_version" in document:
        markers.append(("schema_version", document["schema_version"]))
    if "protocol_version" in document:
        markers.append(("protocol_version", document["protocol_version"]))
    protocol = document.get("protocol")
    if isinstance(protocol, dict) and "version" in protocol:
        markers.append(("protocol.version", protocol["version"]))
    if not markers:
        raise OrchestratorError(
            f"cannot determine the schema or protocol version of run {run_root}; "
            "refusing mutation until run.json contains an explicit version"
        )

    invalid = [
        name
        for name, value in markers
        if not isinstance(value, int) or isinstance(value, bool)
    ]
    if invalid:
        raise OrchestratorError(
            f"run {run_root} has non-integer version markers: {', '.join(invalid)}; "
            "refusing mutation"
        )
    versions = {value for _, value in markers}
    if len(versions) != 1:
        rendered = ", ".join(f"{name}={value}" for name, value in markers)
        raise OrchestratorError(
            f"run {run_root} has conflicting version markers ({rendered}); "
            "refusing mutation until the inconsistency is resolved"
        )
    actual_version = versions.pop()
    if actual_version == expected_version:
        return actual_version
    raise OrchestratorError(
        f"run {run_root} uses unsupported version {actual_version}; only version "
        f"{expected_version} is supported"
    )


def guard_v4_run_mutation(run_root: Path) -> None:
    """Guard the central version-4 mutation boundary."""
    require_run_version(run_root, CURRENT_RUN_VERSION)


def _atomic_temporary_prefix(path: Path) -> str:
    return f".{path.name}."


def _v4_previous_job_path(path: Path) -> Path:
    return path.with_name("job.previous.json")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=_atomic_temporary_prefix(path), dir=path.parent)
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


def find_v4_temporary_files(run_root: Path) -> list[Path]:
    """Return atomic-write artifacts that a version-4 audit should report."""
    targets = [run_root / "run.json"]
    jobs_root = run_root / "jobs"
    if jobs_root.is_dir():
        targets.extend(path / "job.json" for path in jobs_root.iterdir() if path.is_dir())
    temporary_files = (
        candidate
        for target in targets
        for candidate in target.parent.glob(f"{_atomic_temporary_prefix(target)}*")
        if candidate.is_file()
    )
    return sorted(temporary_files, key=lambda path: path.as_posix())


def _process_is_running(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        raise OrchestratorError(
            f"cannot determine whether lock owner process {process_id} is running: {exc}"
        ) from exc
    return True


class RunLock:
    """Non-renewable exclusive lock for one local version-4 controller."""

    def __init__(self, path: Path, controller: str):
        if not controller:
            raise OrchestratorError("run lock controller must not be empty")
        self.path = path
        self.controller = controller
        self.lock_id: str | None = None

    def _stale_reason(self, current: dict[str, Any]) -> str | None:
        required = {
            "schema_version", "lock_id", "controller_id", "owner_pid",
            "owner_host", "acquired_at",
        }
        missing = sorted(required - set(current))
        if missing:
            raise OrchestratorError(
                "cannot determine whether run lock is stale; missing fields: "
                + ", ".join(missing)
            )
        if current["schema_version"] != CURRENT_RUN_VERSION:
            raise OrchestratorError(
                "cannot use a non-version-4 record as a version-4 run lock"
            )
        if not isinstance(current["owner_pid"], int) or isinstance(
            current["owner_pid"], bool
        ) or current["owner_pid"] <= 0:
            raise OrchestratorError(
                "cannot determine whether run lock is stale; owner_pid is invalid"
            )
        if not isinstance(current["owner_host"], str) or not current["owner_host"]:
            raise OrchestratorError(
                "cannot determine whether run lock is stale; owner_host is invalid"
            )
        parse_time(current["acquired_at"])
        if current["owner_host"] != socket.gethostname():
            return None
        if _process_is_running(current["owner_pid"]):
            return None
        return (
            f"owner process {current['owner_pid']} is no longer running on "
            f"{current['owner_host']}"
        )

    def acquire(self, *, takeover: bool = False) -> None:
        with _lease_guard(self.path):
            current = load_json(self.path) if self.path.exists() else None
            if current is not None:
                if not isinstance(current, dict):
                    raise OrchestratorError("run lock record must be a JSON object")
                stale_reason = self._stale_reason(current)
                owner = current.get("controller_id")
                if stale_reason is None:
                    raise OrchestratorError(
                        f"run lock held by active controller {owner}"
                    )
                if not takeover:
                    raise OrchestratorError(
                        f"stale run lock held by controller {owner}: {stale_reason}; "
                        "explicit takeover is required"
                    )

            self.lock_id = random_id("LOCK")
            write_json(
                self.path,
                {
                    "schema_version": CURRENT_RUN_VERSION,
                    "lock_id": self.lock_id,
                    "controller_id": self.controller,
                    "owner_pid": os.getpid(),
                    "owner_host": socket.gethostname(),
                    "acquired_at": utc_now(),
                },
            )

    def release(self) -> None:
        with _lease_guard(self.path):
            if not self.path.exists():
                return
            current = load_json(self.path)
            if (
                isinstance(current, dict)
                and current.get("controller_id") == self.controller
                and current.get("lock_id") == self.lock_id
            ):
                self.path.unlink()

    def __enter__(self) -> "RunLock":
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
def run_lock(
    run_root: Path,
    controller: str,
    *,
    takeover: bool = False,
) -> Iterator[RunLock]:
    guard_v4_run_mutation(run_root)
    lock = RunLock(run_root / "orchestrator.lock", controller)
    lock.acquire(takeover=takeover)
    try:
        yield lock
    finally:
        lock.release()


SCHEMA_ROOT = Path(__file__).resolve().parent.parent / "schemas"
_SCHEMA_CACHE: dict[tuple[int, str], dict[str, Any]] = {}
JOB_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"starting", "canceled"}),
    "starting": frozenset({"running", "recovering", "canceled"}),
    "running": frozenset({
        "waiting_for_input", "recovering", "completed", "failed", "canceled",
    }),
    "waiting_for_input": frozenset({
        "running", "waiting_for_job", "recovering", "canceled",
    }),
    "waiting_for_job": frozenset({
        "waiting_for_input", "running", "recovering", "failed", "canceled",
    }),
    "recovering": frozenset({
        "running", "waiting_for_input", "completed", "failed", "canceled",
    }),
    "completed": frozenset(),
    "failed": frozenset(),
    "canceled": frozenset(),
}
ADVISORY_FAILURE_DECISIONS = (
    "keep_waiting",
    "ask_user",
    "select_another",
    "fail_origin",
)
JOB_STATUSES = frozenset(JOB_STATUS_TRANSITIONS)
_SESSION_REQUIRED_STATUSES = frozenset({
    "running", "waiting_for_input", "waiting_for_job", "completed",
})
_SESSION_FORBIDDEN_STATUSES = frozenset({"queued", "starting"})
_DEPENDENCIES_REQUIRED_STATUSES = frozenset({
    "starting", "running", "waiting_for_input", "waiting_for_job",
    "recovering", "completed", "failed",
})
_TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "canceled"})
_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "canceled"})
_V4_FACT_PRECEDENCE = (
    "transport_response",
    "external_system",
    "repository_filesystem",
    "report_checkpoint",
    "persisted_job_status",
)
_V4_FACT_SOURCE_RANK = {
    "transport_response": 0,
    "external_system": 1,
    "repository_filesystem": 2,
    "report": 3,
    "checkpoint": 4,
    "persisted_job_status": 5,
}
SCHEMA_REGISTRY: dict[int, frozenset[str]] = {
    4: frozenset({
        "job", "job-definition", "outcome", "pending-question",
        "recovery-evidence", "recovery-policy", "run", "setup",
    }),
}
_UNVERSIONED_SCHEMA_DEFAULTS = {
    "outcome": 4,
    "pending-question": 4,
    "recovery-policy": 4,
}


def load_schema(kind: str, version: int = CURRENT_RUN_VERSION) -> dict[str, Any]:
    key = (version, kind)
    if key not in _SCHEMA_CACHE:
        path = SCHEMA_ROOT / f"v{version}" / f"{kind}.schema.json"
        if not path.is_file():
            if kind not in SCHEMA_REGISTRY.get(version, frozenset()):
                raise OrchestratorError(f"unsupported schema {kind!r} version {version}")
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
        raise OrchestratorError(f"Schema validation error at `{location}`: {msg}.")

    expected = schema.get("type")
    if expected is not None:
        choices = [expected] if isinstance(expected, str) else expected
        if not any(_matches_type(value, choice) for choice in choices):
            _raise(f"must have type {' or '.join(choices)}")
    if "const" in schema and value != schema["const"]:
        _raise(f"must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        _raise(f"must be one of {schema['enum']!r}")
    for condition in schema.get("allOf", []):
        _validate_schema(value, condition, location)
    if "if" in schema:
        try:
            _validate_schema(value, schema["if"], location)
        except OrchestratorError:
            branch = schema.get("else")
        else:
            branch = schema.get("then")
        if branch is not None:
            _validate_schema(value, branch, location)
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
    version = value.get("schema_version", _UNVERSIONED_SCHEMA_DEFAULTS.get(kind))
    if not isinstance(version, int) or isinstance(version, bool):
        raise OrchestratorError(f"{kind}.schema_version must be an integer")
    _validate_schema(value, load_schema(kind, version), kind)


def write_v4_document(
    path: Path,
    kind: str,
    value: dict[str, Any],
    *,
    transition_path: list[str] | None = None,
) -> None:
    """Validate and atomically replace an authoritative version-4 document."""
    expected_name = {"run": "run.json", "job": "job.json"}.get(kind)
    if expected_name is None:
        raise OrchestratorError(
            f"version-4 authoritative document kind must be 'run' or 'job', not {kind!r}"
        )
    if path.name != expected_name:
        raise OrchestratorError(
            f"authoritative version-4 {kind} document must be named {expected_name}"
        )
    if value.get("schema_version") != CURRENT_RUN_VERSION:
        raise OrchestratorError(
            f"authoritative version-4 {kind} document must use schema_version "
            f"{CURRENT_RUN_VERSION}"
        )
    if transition_path is not None and kind != "job":
        raise OrchestratorError(
            "a version-4 transition path applies only to an authoritative job"
        )
    validate_record(kind, value)
    if (
        kind == "job"
        and path.is_file()
        and path.parent.parent.name == "jobs"
        and (path.parent.parent.parent / "run.json").is_file()
    ):
        run_root = path.parent.parent.parent
        state = load_v4_state(run_root)
        current = state["jobs"].get(value["id"])
        if current is None or path.parent.name != value["id"]:
            raise OrchestratorError(
                f"cannot replace authoritative job {value['id']!r} at {path}"
            )
        _validate_v4_job_paths(value)
        if current["status"] != value["status"]:
            validate_v4_job_transition_path(
                current,
                value,
                state["jobs"],
                transition_path=(
                    [value["status"]]
                    if transition_path is None
                    else transition_path
                ),
                run_root=run_root,
            )
        else:
            if transition_path is not None:
                raise OrchestratorError(
                    "a transition path cannot end at the current job status"
                )
            candidate_jobs = dict(state["jobs"])
            candidate_jobs[value["id"]] = value
            _validate_v4_job_graph(candidate_jobs)
            validate_v4_state_coherence(candidate_jobs, run_root=run_root)
    previous_bytes: bytes | None = None
    if kind == "job" and path.is_file():
        try:
            previous = load_json(path)
            validate_record("job", previous)
            _validate_v4_job_paths(previous)
            if previous["id"] != path.parent.name:
                raise OrchestratorError(
                    f"authoritative job path {path} contains identity "
                    f"{previous['id']!r}"
                )
            previous_bytes = path.read_bytes()
        except (OSError, UnicodeError) as exc:
            raise OrchestratorError(
                f"cannot preserve the complete previous job record at {path}: {exc}"
            ) from exc
    if previous_bytes is not None:
        # Keep exactly one complete predecessor for atomic corruption recovery.
        atomic_write(_v4_previous_job_path(path), previous_bytes)
    write_json(path, value)


def _validate_v4_job_id(job_id: str) -> None:
    invalid_characters = '<>:"/\\|?*'
    if (
        not job_id
        or job_id in {".", ".."}
        or job_id[-1] in {".", " "}
        or any(
            character in invalid_characters or ord(character) < 32
            for character in job_id
        )
    ):
        raise OrchestratorError(
            f"job ID {job_id!r} is not a safe authoritative directory name"
        )


def _validate_v4_job_paths(job: dict[str, Any]) -> None:
    job_id = job["id"]
    job_root = f"jobs/{job_id}"
    expected_paths = {
        "prompt_path": f"{job_root}/prompt.md",
        "report_path": f"{job_root}/report.md",
    }
    for field, expected in expected_paths.items():
        if job[field] != expected:
            raise OrchestratorError(
                f"job {job_id} {field} must be the authoritative path {expected!r}"
            )

    checkpoint_path = job["checkpoint_path"]
    expected_checkpoint = f"{job_root}/checkpoint.md"
    if checkpoint_path is not None and checkpoint_path != expected_checkpoint:
        raise OrchestratorError(
            f"job {job_id} checkpoint_path must be null or the authoritative path "
            f"{expected_checkpoint!r}"
        )

    outcome = job["outcome"]
    if outcome is not None and "report_path" in outcome:
        if outcome["report_path"] != job["report_path"]:
            raise OrchestratorError(
                f"job {job_id} outcome report_path must match its authoritative report_path"
            )

    for related_path in job["related_reports"]:
        parts = related_path.split("/")
        if (
            len(parts) != 3
            or parts[0] != "jobs"
            or parts[2] != "report.md"
        ):
            raise OrchestratorError(
                f"job {job_id} related report path {related_path!r} is not authoritative"
            )
        _validate_v4_job_id(parts[1])


def _validate_acyclic_job_links(
    links: dict[str, set[str]], *, description: str
) -> None:
    remaining = {job_id: set(targets) for job_id, targets in links.items()}
    ready = [job_id for job_id, targets in remaining.items() if not targets]
    while ready:
        resolved = ready.pop()
        remaining.pop(resolved)
        for job_id, targets in remaining.items():
            if resolved in targets:
                targets.remove(resolved)
                if not targets:
                    ready.append(job_id)
    if remaining:
        involved = ", ".join(sorted(remaining))
        raise OrchestratorError(
            f"job {description} cycle detected involving: {involved}"
        )


def _validate_v4_job_graph(jobs: dict[str, dict[str, Any]]) -> None:
    known_ids = set(jobs)
    dependency_links: dict[str, set[str]] = {}
    parent_links: dict[str, set[str]] = {}
    waiting_links: dict[str, set[str]] = {}
    for job_id, job in jobs.items():
        unknown_dependencies = sorted(set(job["depends_on"]) - known_ids)
        if unknown_dependencies:
            raise OrchestratorError(
                f"job {job_id} has unknown dependencies: "
                + ", ".join(unknown_dependencies)
            )
        dependency_links[job_id] = set(job["depends_on"])

        parent_id = job["parent_job_id"]
        if parent_id is not None and parent_id not in known_ids:
            raise OrchestratorError(f"job {job_id} has unknown parent {parent_id}")
        parent_links[job_id] = {parent_id} if parent_id is not None else set()

        unknown_waiting = sorted(set(job["waiting_on"]) - known_ids)
        if unknown_waiting:
            raise OrchestratorError(
                f"job {job_id} is waiting on unknown jobs: "
                + ", ".join(unknown_waiting)
            )
        if job_id in job["waiting_on"]:
            raise OrchestratorError(f"job {job_id} cannot wait on itself")
        waiting_links[job_id] = set(job["waiting_on"])

    _validate_acyclic_job_links(dependency_links, description="dependency")
    _validate_acyclic_job_links(parent_links, description="parent")
    _validate_acyclic_job_links(waiting_links, description="waiting")
    blocking_links = {
        job_id: dependency_links[job_id] | waiting_links[job_id]
        for job_id in jobs
    }
    _validate_acyclic_job_links(blocking_links, description="dependency/waiting")


def _v4_report_is_accessible(run_root: Path, path: str) -> bool:
    report = run_root / Path(path)
    try:
        return report.is_file() and report.stat().st_size > 0
    except OSError:
        return False


def _require_accessible_v4_report(run_root: Path, path: str, *, owner: str) -> None:
    if not _v4_report_is_accessible(run_root, path):
        raise OrchestratorError(
            f"{owner} requires an accessible non-empty report at {path}"
        )


def _reconcile_v4_advisory_reports(
    run_root: Path, jobs: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Attach awaited reports only after every advisory completed successfully."""
    reconciled = dict(jobs)
    waiting_origins = sorted(
        (
            job
            for job in jobs.values()
            if job["status"] == "waiting_for_job"
        ),
        key=lambda job: (job["creation_sequence"], job["id"]),
    )
    for current in waiting_origins:
        awaited = [reconciled[job_id] for job_id in current["waiting_on"]]
        report_paths = [job["report_path"] for job in awaited]
        if not all(
            job["status"] == "completed"
            and job["outcome"] is not None
            and job["outcome"]["status"] == "completed"
            and job["outcome"].get("report_path") == job["report_path"]
            and _v4_report_is_accessible(run_root, job["report_path"])
            for job in awaited
        ):
            continue

        related_reports = list(current["related_reports"])
        related_reports.extend(
            path for path in report_paths if path not in related_reports
        )
        if related_reports == current["related_reports"]:
            continue

        proposed = {
            **current,
            "related_reports": related_reports,
            "updated_at": utc_now(),
            "revision": current["revision"] + 1,
        }
        write_v4_document(
            run_root / "jobs" / current["id"] / "job.json", "job", proposed
        )
        reconciled[current["id"]] = proposed
    return reconciled


def _validate_v4_completion_coherence(
    job: dict[str, Any],
    jobs: dict[str, dict[str, Any]],
    *,
    run_root: Path,
) -> None:
    job_id = job["id"]
    outcome = job["outcome"]
    if outcome is None or outcome["status"] != "completed":
        raise OrchestratorError(
            f"job {job_id} completion requires a coherent completed outcome"
        )
    if "question" in outcome:
        raise OrchestratorError(
            f"job {job_id} completed outcome must not contain a question"
        )

    unfinished_related = [
        related_id
        for related_id in job["waiting_on"]
        if jobs[related_id]["status"] not in _TERMINAL_JOB_STATUSES
    ]
    if unfinished_related:
        raise OrchestratorError(
            f"job {job_id} completion requires terminal related jobs: "
            + ", ".join(unfinished_related)
        )
    if job["pending_question"] is not None:
        raise OrchestratorError(
            f"job {job_id} completion requires no pending question"
        )

    if job["report_required"]:
        if outcome.get("report_path") != job["report_path"]:
            raise OrchestratorError(
                f"job {job_id} completed outcome must include required report_path "
                f"{job['report_path']!r}"
            )
        _require_accessible_v4_report(
            run_root, job["report_path"], owner=f"job {job_id} completion"
        )
    elif "report_path" in outcome:
        _require_accessible_v4_report(
            run_root, outcome["report_path"], owner=f"job {job_id} outcome"
        )


def validate_v4_state_coherence(
    jobs: dict[str, dict[str, Any]], *, run_root: Path
) -> None:
    """Validate lifecycle facts that schemas and graph topology cannot express."""
    for job_id, job in jobs.items():
        status = job["status"]
        session_ref = job["session_ref"]
        pending_question = job["pending_question"]
        waiting_on = job["waiting_on"]
        outcome = job["outcome"]

        if status == "completed":
            _validate_v4_completion_coherence(job, jobs, run_root=run_root)

        if status in _SESSION_REQUIRED_STATUSES and session_ref is None:
            raise OrchestratorError(
                f"job {job_id} status {status!r} requires a session_ref"
            )
        if status in _SESSION_FORBIDDEN_STATUSES and session_ref is not None:
            raise OrchestratorError(
                f"job {job_id} status {status!r} must not have a session_ref"
            )

        waiting_status = status in {"waiting_for_input", "waiting_for_job"}
        recovering_question = status == "recovering" and pending_question is not None
        if waiting_status or recovering_question:
            if pending_question is None:
                raise OrchestratorError(
                    f"job {job_id} status {status!r} requires a pending_question"
                )
            if outcome is None or outcome["status"] != "needs_input":
                raise OrchestratorError(
                    f"job {job_id} with a pending question requires a needs_input outcome"
                )
            if outcome["question"] != pending_question["text"]:
                raise OrchestratorError(
                    f"job {job_id} pending question must match its needs_input outcome"
                )
        elif pending_question is not None:
            raise OrchestratorError(
                f"job {job_id} status {status!r} must not have a pending_question"
            )

        if status == "waiting_for_job" and not waiting_on:
            raise OrchestratorError(
                f"job {job_id} status 'waiting_for_job' requires waiting_on jobs"
            )
        if status not in {"waiting_for_job", "recovering"} and waiting_on:
            raise OrchestratorError(
                f"job {job_id} status {status!r} must not have waiting_on jobs"
            )
        if waiting_on and pending_question is None:
            raise OrchestratorError(
                f"job {job_id} waiting_on jobs requires a pending_question"
            )

        expected_outcome = {
            "completed": "completed",
            "failed": "failed",
        }.get(status)
        if expected_outcome is not None:
            if outcome is None or outcome["status"] != expected_outcome:
                raise OrchestratorError(
                    f"job {job_id} status {status!r} requires a coherent "
                    f"{expected_outcome} outcome"
                )
        elif status == "canceled":
            if outcome is not None:
                raise OrchestratorError(
                    f"canceled job {job_id} must not claim a worker outcome"
                )
        elif not (waiting_status or recovering_question) and outcome is not None:
            raise OrchestratorError(
                f"job {job_id} status {status!r} must not have a worker outcome"
            )

        if status in _DEPENDENCIES_REQUIRED_STATUSES:
            incomplete = [
                dependency
                for dependency in job["depends_on"]
                if jobs[dependency]["status"] != "completed"
            ]
            if incomplete:
                raise OrchestratorError(
                    f"job {job_id} status {status!r} requires completed dependencies: "
                    + ", ".join(incomplete)
                )

        if outcome is not None and "report_path" in outcome:
            _require_accessible_v4_report(
                run_root, outcome["report_path"], owner=f"job {job_id} outcome"
            )

        for report_path in job["related_reports"]:
            related_id = report_path.split("/")[1]
            if related_id not in jobs:
                raise OrchestratorError(
                    f"job {job_id} has a related report for unknown job {related_id}"
                )
            if jobs[related_id]["status"] != "completed":
                raise OrchestratorError(
                    f"job {job_id} related report {report_path!r} belongs to a "
                    "job that is not completed"
                )
            _require_accessible_v4_report(
                run_root, report_path, owner=f"job {job_id} related report"
            )


def derive_v4_ready_job_ids(jobs: dict[str, dict[str, Any]]) -> list[str]:
    """Derive the deterministic ready queue from authoritative job records."""
    ready = (
        job
        for job in jobs.values()
        if job["status"] == "queued"
        and all(
            jobs[dependency]["status"] == "completed"
            for dependency in job["depends_on"]
        )
    )
    return [
        job["id"]
        for job in sorted(
            ready,
            key=lambda job: (-job["priority"], job["creation_sequence"], job["id"]),
        )
    ]


def derive_v4_run_status(jobs: dict[str, dict[str, Any]]) -> str:
    """Derive aggregate run status from required authoritative jobs."""
    if not jobs:
        return "active"
    if any(
        job["status"] not in _TERMINAL_JOB_STATUSES
        or job["pending_question"] is not None
        or job["waiting_on"]
        for job in jobs.values()
    ):
        return "active"
    if any(job["status"] == "failed" for job in jobs.values()):
        return "failed"
    if any(job["status"] == "canceled" for job in jobs.values()):
        return "canceled"
    return "completed"


def _validate_v4_run_coherence(
    run: dict[str, Any], jobs: dict[str, dict[str, Any]]
) -> None:
    derived_status = derive_v4_run_status(jobs)
    if (
        run["status"] in _TERMINAL_RUN_STATUSES
        and run["status"] != derived_status
    ):
        raise OrchestratorError(
            f"terminal run status {run['status']!r} disagrees with required job "
            f"state, which derives {derived_status!r}"
        )


def _persist_v4_run_completion(
    run_root: Path,
    run: dict[str, Any],
    jobs: dict[str, dict[str, Any]],
) -> str:
    derived_status = derive_v4_run_status(jobs)
    if derived_status == "active" or run["status"] == derived_status:
        return run["status"]
    if run["status"] != "active":
        raise OrchestratorError(
            f"cannot change terminal run status {run['status']!r} to "
            f"{derived_status!r}"
        )
    now = utc_now()
    write_v4_document(
        run_root / "run.json",
        "run",
        {
            **run,
            "status": derived_status,
            "updated_at": now,
            "revision": run["revision"] + 1,
        },
    )
    return derived_status


def select_v4_next_operation(
    state: dict[str, Any], *, run_root: Path
) -> dict[str, Any]:
    """Select one operation without mutating or consulting derived persisted state."""
    run = state["run"]
    jobs = state["jobs"]
    order = lambda job: (-job["priority"], job["creation_sequence"], job["id"])
    derived_run_status = derive_v4_run_status(jobs)

    if run["status"] in _TERMINAL_RUN_STATUSES and run["status"] != derived_run_status:
        raise OrchestratorError(
            f"terminal run status {run['status']!r} disagrees with required job "
            f"state, which derives {derived_run_status!r}"
        )
    if derived_run_status in _TERMINAL_RUN_STATUSES:
        return {"operation": "run_complete"}

    questions = sorted(
        (job for job in jobs.values() if job["status"] == "waiting_for_input"),
        key=order,
    )
    if questions:
        job = questions[0]
        return {
            "operation": "ask_user",
            "job_id": job["id"],
            "question": dict(job["pending_question"]),
        }

    advisory_failures = []
    for job in sorted(jobs.values(), key=order):
        if job["status"] != "waiting_for_job":
            continue
        failed = [
            {
                "job_id": advisory_id,
                "status": jobs[advisory_id]["status"],
            }
            for advisory_id in job["waiting_on"]
            if jobs[advisory_id]["status"] in {"failed", "canceled"}
        ]
        if failed:
            advisory_failures.append((job, failed))
    if advisory_failures:
        job, failed = advisory_failures[0]
        return {
            "operation": "wait",
            "reason": "advisory_decision_required",
            "origin_job_id": job["id"],
            "advisory_jobs": failed,
            "allowed_decisions": list(ADVISORY_FAILURE_DECISIONS),
        }

    resumable = []
    for job in jobs.values():
        if job["status"] != "waiting_for_job":
            continue
        awaited = [jobs[job_id] for job_id in job["waiting_on"]]
        required_reports = {awaited_job["report_path"] for awaited_job in awaited}
        if (
            all(awaited_job["status"] == "completed" for awaited_job in awaited)
            and required_reports.issubset(set(job["related_reports"]))
        ):
            resumable.append(job)
    if resumable:
        job = min(resumable, key=order)
        awaited_reports = [
            jobs[awaited_id]["report_path"] for awaited_id in job["waiting_on"]
        ]
        continuation_prompt = render_v4_continuation_prompt(
            job,
            _load_v4_job_definition(run_root, job["id"]),
            answers=list(job.get("answers", [])),
            advisory_reports=awaited_reports,
        )
        return {
            "operation": "resume_job",
            "job_id": job["id"],
            "session_ref": job["session_ref"],
            "prompt": continuation_prompt,
        }

    ready_job_ids = derive_v4_ready_job_ids(jobs)
    if ready_job_ids:
        job = jobs[ready_job_ids[0]]
        prompt_path = Path(run_root) / job["prompt_path"]
        try:
            prompt = prompt_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise OrchestratorError(
                f"cannot read initial prompt for job {job['id']} from "
                f"{job['prompt_path']}: {exc}"
            ) from exc
        if not prompt.strip():
            raise OrchestratorError(
                f"initial prompt for job {job['id']} is empty: {job['prompt_path']}"
            )
        return {
            "operation": "start_job",
            "job_id": job["id"],
            "title": job["title"],
            "prompt": prompt,
            "correlation": {
                "run_id": run["run_id"],
                "job_id": job["id"],
            },
        }

    return {"operation": "wait"}


def _load_v4_state(
    run_root: Path,
    *,
    job_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Load and structurally validate authoritative version-4 run state."""
    run_root = Path(run_root)
    job_overrides = job_overrides or {}
    require_run_version(run_root, CURRENT_RUN_VERSION)
    run = load_json(run_root / "run.json")
    validate_record("run", run)
    for job_id in run["job_ids"]:
        _validate_v4_job_id(job_id)

    jobs_root = run_root / "jobs"
    if not jobs_root.is_dir():
        raise OrchestratorError(f"version-4 run lacks authoritative jobs directory: {jobs_root}")

    documents_by_directory: dict[str, dict[str, Any]] = {}
    identity_paths: dict[str, Path] = {}
    for job_directory in sorted(
        (path for path in jobs_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    ):
        directory_id = job_directory.name
        _validate_v4_job_id(directory_id)
        if job_directory.resolve().parent != jobs_root.resolve():
            raise OrchestratorError(
                f"authoritative job directory must not escape jobs/: {job_directory}"
            )
        document_path = job_directory / "job.json"
        if not document_path.is_file():
            raise OrchestratorError(
                f"authoritative job directory lacks job.json: {job_directory}"
            )
        document = job_overrides.get(directory_id)
        if document is None:
            document = load_json(document_path)
        validate_record("job", document)
        _validate_v4_job_id(document["id"])

        previous_path = identity_paths.get(document["id"])
        if previous_path is not None:
            raise OrchestratorError(
                f"duplicate authoritative job identity {document['id']!r} in "
                f"{previous_path} and {document_path}"
            )
        identity_paths[document["id"]] = document_path
        documents_by_directory[directory_id] = document

    listed_ids = set(run["job_ids"])
    directory_ids = set(documents_by_directory)
    missing = sorted(listed_ids - directory_ids)
    unlisted = sorted(directory_ids - listed_ids)
    if missing or unlisted:
        details = []
        if missing:
            details.append("missing job directories: " + ", ".join(missing))
        if unlisted:
            details.append("unlisted job directories: " + ", ".join(unlisted))
        raise OrchestratorError(
            "run job_ids disagree with authoritative job directories ("
            + "; ".join(details)
            + ")"
        )

    jobs: dict[str, dict[str, Any]] = {}
    for job_id in run["job_ids"]:
        document = documents_by_directory[job_id]
        if document["id"] != job_id:
            raise OrchestratorError(
                f"authoritative job path jobs/{job_id}/job.json contains identity "
                f"{document['id']!r}"
            )
        _validate_v4_job_paths(document)
        jobs[job_id] = document

    _validate_v4_job_graph(jobs)
    validate_v4_state_coherence(jobs, run_root=run_root)
    _validate_v4_run_coherence(run, jobs)
    return {
        "run": run,
        "jobs": jobs,
        "ready_job_ids": derive_v4_ready_job_ids(jobs),
    }


def load_v4_state(run_root: Path) -> dict[str, Any]:
    return _load_v4_state(run_root)


def inspect_v4_job_record_recovery(
    run_root: Path, job_id: str
) -> dict[str, Any]:
    """Inspect a malformed job and its bounded predecessor without mutating state."""
    run_root = Path(run_root).resolve()
    require_run_version(run_root, CURRENT_RUN_VERSION)
    _validate_v4_job_id(job_id)
    run = load_json(run_root / "run.json")
    validate_record("run", run)
    if job_id not in run["job_ids"]:
        raise OrchestratorError(f"unknown job {job_id!r}")
    job_path = run_root / "jobs" / job_id / "job.json"
    previous_path = _v4_previous_job_path(job_path)

    malformed_bytes: bytes | None = None
    malformed_error: str | None = None
    try:
        malformed_bytes = job_path.read_bytes()
        current = load_json(job_path)
        validate_record("job", current)
        _validate_v4_job_paths(current)
        if current["id"] != job_id:
            raise OrchestratorError(
                f"authoritative job path {job_path} contains identity {current['id']!r}"
            )
    except (KeyError, OSError, OrchestratorError, TypeError, UnicodeError) as exc:
        malformed_error = str(exc)

    if malformed_error is None:
        return {
            "job_id": job_id,
            "malformed": False,
            "path": job_path.relative_to(run_root).as_posix(),
        }

    previous: dict[str, Any] | None = None
    previous_bytes: bytes | None = None
    previous_error: str | None = None
    if previous_path.is_file():
        try:
            previous_bytes = previous_path.read_bytes()
            previous = load_json(previous_path)
            validate_record("job", previous)
            _validate_v4_job_paths(previous)
            if previous["id"] != job_id:
                raise OrchestratorError(
                    f"previous job record contains identity {previous['id']!r}"
                )
            _load_v4_state(run_root, job_overrides={job_id: previous})
        except (
            KeyError,
            OSError,
            OrchestratorError,
            RuntimeError,
            TypeError,
            UnicodeError,
            ValueError,
        ) as exc:
            previous_error = str(exc)
            previous = None
            previous_bytes = None

    malformed_sha256 = (
        hashlib.sha256(malformed_bytes).hexdigest()
        if malformed_bytes is not None
        else None
    )
    quarantine_path = (
        job_path.with_name(f"job.quarantine.{malformed_sha256}.json")
        if malformed_sha256 is not None
        else None
    )
    return {
        "job_id": job_id,
        "malformed": True,
        "path": job_path.relative_to(run_root).as_posix(),
        "error": malformed_error,
        "sha256": malformed_sha256,
        "quarantine_path": (
            quarantine_path.relative_to(run_root).as_posix()
            if quarantine_path is not None
            else None
        ),
        "previous_version": {
            "path": previous_path.relative_to(run_root).as_posix(),
            "available": previous_path.is_file(),
            "restorable": previous is not None,
            "revision": previous.get("revision") if previous is not None else None,
            "session_ref": (
                previous.get("session_ref") if previous is not None else None
            ),
            "error": previous_error,
        },
        "_malformed_bytes": malformed_bytes,
        "_previous_bytes": previous_bytes,
    }


def recover_v4_job_record(
    run_root: Path,
    job_id: str,
    *,
    controller: str,
    apply: bool = False,
) -> dict[str, Any]:
    """Quarantine a malformed job and restore its last coherent atomic version."""
    run_root = Path(run_root).resolve()
    inspection = inspect_v4_job_record_recovery(run_root, job_id)
    if not inspection["malformed"]:
        raise OrchestratorError(
            f"job {job_id} record is structurally valid; recover it from supplied facts"
        )

    malformed_bytes = inspection.pop("_malformed_bytes")
    previous_bytes = inspection.pop("_previous_bytes")
    restorable = inspection["previous_version"]["restorable"]
    result = {
        **inspection,
        "classification": "malformed_job_record",
        "apply": apply,
        "state_changed": False,
        "record_restored": False,
        "reconciliation": {
            "required": True,
            "fact_sources": [
                "transport_response",
                "external_system",
                "repository_filesystem",
                "report_checkpoint",
                "persisted_job_status",
            ],
        },
        "recommended_action": (
            "restore_previous_atomic_version_and_reconcile_facts"
            if restorable
            else "collect_facts_for_recovery_investigation"
        ),
    }
    if not apply:
        return result

    with run_lock(run_root, controller):
        current = inspect_v4_job_record_recovery(run_root, job_id)
        if not current["malformed"]:
            raise OrchestratorError(
                f"job {job_id} record changed while corruption recovery was pending"
            )
        if current["sha256"] != inspection["sha256"]:
            raise OrchestratorError(
                f"job {job_id} malformed record changed while recovery was pending"
            )

        quarantine_relative = current["quarantine_path"]
        if malformed_bytes is not None and quarantine_relative is not None:
            quarantine_path = run_root / quarantine_relative
            if quarantine_path.is_file():
                if quarantine_path.read_bytes() != malformed_bytes:
                    raise OrchestratorError(
                        f"quarantine evidence collision at {quarantine_relative}"
                    )
            else:
                atomic_write(quarantine_path, malformed_bytes)
            result["quarantined"] = True
            result["state_changed"] = True
        else:
            result["quarantined"] = False

        if restorable and previous_bytes is not None:
            job_path = run_root / inspection["path"]
            atomic_write(job_path, previous_bytes)
            load_v4_state(run_root)
            result.update({
                "classification": "recovered_previous_atomic_version",
                "record_restored": True,
                "state_changed": True,
                "recommended_action": "reconcile_recovered_state_from_facts",
            })
        else:
            result["recommended_action"] = "collect_facts_for_recovery_investigation"
    return result


def rebuild_v4_job_index(run_root: Path) -> dict[str, list[str]]:
    """Atomically rebuild the derived discovery index from authoritative jobs."""
    run_root = Path(run_root)
    state = load_v4_state(run_root)
    index = {"jobs": sorted(state["jobs"])}
    write_json(run_root / "jobs" / "index.json", index)
    return index


def _audit_v4_transport_evidence(
    evidence: dict[str, Any], job: dict[str, Any]
) -> dict[str, Any]:
    transport = evidence.get("transport")
    report: dict[str, Any] = {
        "supplied": True,
        "job_id": evidence["job_id"],
        "session_ref": evidence.get("session_ref"),
        "observed_at": evidence["observed_at"],
        "persisted_status": job["status"],
        "persisted_session_ref": job["session_ref"],
        "reconciliation_required": False,
        "recommended_action": "none",
        "contradictions": [],
    }
    if transport is None:
        report.update({
            "observation": None,
            "status": None,
            "classification": "no_transport_observation",
        })
        return report

    observation = transport["observation"]
    status = transport["status"]
    response = transport.get("response")
    report.update({
        "observation": observation,
        "status": status,
        "turn_state": "completed" if status == "returned" else status,
        "cancellation_requested": transport.get("cancellation_requested", False),
    })
    if "transcript_ref" in transport:
        report["transcript_ref"] = transport["transcript_ref"]
    if response is not None:
        report["response_status"] = response["status"]

    if observation != "direct" or status == "unknown":
        report.update({
            "classification": "insufficient_transport_evidence",
            "reconciliation_required": True,
            "recommended_action": (
                "confirm_cancellation_or_liveness"
                if transport.get("cancellation_requested")
                else "obtain_direct_transport_evidence"
            ),
        })
        return report

    if status == "active":
        report["classification"] = "active_session"
        if job["status"] not in {"running", "recovering"}:
            report["contradictions"].append(
                f"transport reports an active turn while persisted job status is "
                f"{job['status']!r}"
            )
    elif status == "available":
        report["classification"] = "available_session"
        if job["session_ref"] is None:
            report.update({
                "reconciliation_required": True,
                "recommended_action": "record_transport_session",
            })
    elif status == "returned":
        if response is None:
            report["classification"] = "returned_session"
            if job["outcome"] is None:
                report.update({
                    "reconciliation_required": True,
                    "recommended_action": "retrieve_transport_response",
                })
        else:
            normalized_response = normalize_v4_outcome(response)
            if job["outcome"] is None:
                report.update({
                    "classification": "unrecorded_transport_response",
                    "reconciliation_required": True,
                    "recommended_action": "record_response_with_jobctl_outcome",
                })
            elif job["outcome"] == normalized_response:
                report["classification"] = "recorded_transport_response"
            else:
                report["classification"] = "conflicting_transport_response"
                report["contradictions"].append(
                    "transport response status or execution fields disagree with "
                    "the persisted job outcome"
                )
    elif status == "canceled":
        report["classification"] = "confirmed_cancellation"
        if job["status"] != "canceled":
            if job["status"] == "completed":
                report["contradictions"].append(
                    "transport reports cancellation while the persisted job is completed"
                )
            else:
                report.update({
                    "reconciliation_required": True,
                    "recommended_action": "recover_canceled_job",
                })
    else:
        report["classification"] = "confirmed_session_unavailable"
        if job["status"] not in _TERMINAL_JOB_STATUSES:
            report.update({
                "reconciliation_required": True,
                "recommended_action": "recover_unavailable_job",
            })

    if report["contradictions"]:
        report.update({
            "reconciliation_required": True,
            "recommended_action": "resolve_transport_state_contradiction",
        })
    return report


def audit_v4_state(
    run_root: Path,
    *,
    evidence: dict[str, Any] | None = None,
    rebuild_index: bool = False,
) -> dict[str, Any]:
    """Audit authoritative version-4 state without repairing it."""
    run_root = Path(run_root).resolve()
    temporary_files = [
        path.relative_to(run_root).as_posix()
        for path in find_v4_temporary_files(run_root)
    ]
    issues = [
        f"abandoned atomic-write temporary file: {path}"
        for path in temporary_files
    ]
    result: dict[str, Any] = {
        "ok": False,
        "schema_version": CURRENT_RUN_VERSION,
        "issues": issues,
        "job_ids": [],
        "abandoned_temporary_files": temporary_files,
        "checkpoints": [],
        "transport_evidence": {"supplied": False},
        "fact_reconciliation": {"supplied": False},
        "job_record_recovery": [],
        "index": {
            "path": "jobs/index.json",
            "expected": None,
            "actual": None,
            "agrees": None,
            "rebuilt": False,
        },
    }

    try:
        state = load_v4_state(run_root)
    except (
        OrchestratorError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        issues.append(f"authoritative version-4 state is invalid: {exc}")
        jobs_root = run_root / "jobs"
        if jobs_root.is_dir():
            for job_directory in sorted(
                (path for path in jobs_root.iterdir() if path.is_dir()),
                key=lambda path: path.name,
            ):
                try:
                    recovery = inspect_v4_job_record_recovery(
                        run_root, job_directory.name
                    )
                except (OSError, OrchestratorError, UnicodeError, ValueError):
                    continue
                if not recovery["malformed"]:
                    continue
                recovery.pop("_malformed_bytes", None)
                recovery.pop("_previous_bytes", None)
                recovery["recommended_action"] = (
                    "jobctl_recover_previous_atomic_version"
                    if recovery["previous_version"]["restorable"]
                    else "collect_facts_for_recovery_investigation"
                )
                result["job_record_recovery"].append(recovery)
        return result

    jobs = state["jobs"]
    result["job_ids"] = sorted(jobs)
    resolved_root = run_root.resolve()

    if evidence is not None:
        validate_v4_recovery_evidence(evidence)
        evidence_job = jobs.get(evidence["job_id"])
        if evidence_job is None:
            raise OrchestratorError(
                f"transport evidence identifies unknown job {evidence['job_id']!r}"
            )
        validate_v4_recovery_evidence(
            evidence,
            job_id=evidence_job["id"],
            session_ref=evidence_job["session_ref"],
        )
        evidence_report = _audit_v4_transport_evidence(evidence, evidence_job)
        result["transport_evidence"] = evidence_report
        issues.extend(
            f"job {evidence_job['id']} transport evidence contradiction: {detail}"
            for detail in evidence_report["contradictions"]
        )
        fact_report = _reconcile_v4_recovery_facts(evidence, evidence_job)
        result["fact_reconciliation"] = {"supplied": True, **fact_report}
        issues.extend(
            f"job {evidence_job['id']} recovery evidence contradiction for "
            f"{item['subject']!r}: {item['preferred_source']} reports "
            f"{item['preferred_value']!r}, but {item['conflicting_source']} reports "
            f"{item['conflicting_value']!r}"
            for item in fact_report["material_contradictions"]
        )

    def validate_artifact_path(
        job_id: str, field: str, relative: str, *, required: bool = False
    ) -> Path:
        artifact = run_root / relative
        try:
            artifact.resolve().relative_to(resolved_root)
        except (OSError, RuntimeError, ValueError):
            issues.append(
                f"job {job_id} {field} escapes the run root: {relative}"
            )
            return artifact
        if required:
            try:
                if not artifact.is_file() or artifact.stat().st_size == 0:
                    issues.append(
                        f"job {job_id} requires an accessible non-empty {field} at "
                        f"{relative}"
                    )
            except OSError as exc:
                issues.append(f"job {job_id} cannot inspect {field} {relative}: {exc}")
        return artifact

    checkpoints = []
    for job_id, job in jobs.items():
        validate_artifact_path(
            job_id, "prompt", job["prompt_path"], required=True
        )
        validate_artifact_path(job_id, "report", job["report_path"])
        for related_report in job["related_reports"]:
            validate_artifact_path(job_id, "related report", related_report)

        checkpoint_path = job["checkpoint_path"]
        checkpoint = {
            "job_id": job_id,
            "path": checkpoint_path,
            "present": False,
        }
        if checkpoint_path is not None:
            artifact = validate_artifact_path(
                job_id, "checkpoint", checkpoint_path
            )
            try:
                checkpoint["present"] = artifact.is_file()
                if artifact.exists() and not checkpoint["present"]:
                    issues.append(
                        f"job {job_id} checkpoint is not a regular file: "
                        f"{checkpoint_path}"
                    )
            except OSError as exc:
                issues.append(
                    f"job {job_id} cannot inspect checkpoint {checkpoint_path}: {exc}"
                )
        checkpoints.append(checkpoint)
    result["checkpoints"] = checkpoints

    expected_index = {"jobs": sorted(jobs)}
    index_path = run_root / "jobs" / "index.json"
    actual_index: Any = None
    index_error: str | None = None
    try:
        actual_index = load_json(index_path)
    except (OrchestratorError, UnicodeError) as exc:
        index_error = str(exc)
    index_agrees = actual_index == expected_index

    if not index_agrees and rebuild_index:
        actual_index = rebuild_v4_job_index(run_root)
        index_agrees = True
        result["index"]["rebuilt"] = True
        index_error = None
    elif not index_agrees:
        detail = f": {index_error}" if index_error is not None else ""
        issues.append(
            "jobs/index.json disagrees with authoritative job records" + detail
        )

    result["index"].update({
        "expected": expected_index,
        "actual": actual_index,
        "agrees": index_agrees,
    })
    result["ok"] = not issues
    return result


def _load_worker_contract() -> str:
    """Load the canonical worker-only contract for prompt generation."""
    try:
        contract = WORKER_CONTRACT_PATH.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise OrchestratorError(
            f"cannot load canonical worker contract {WORKER_CONTRACT_PATH}: {exc}"
        ) from exc
    heading = "# Worker Contract"
    if not contract.startswith(heading):
        raise OrchestratorError(
            f"canonical worker contract must start with {heading!r}: "
            f"{WORKER_CONTRACT_PATH}"
        )
    body = contract[len(heading):].strip()
    if not body:
        raise OrchestratorError("canonical worker contract must not be empty")
    return body


def render_v4_initial_prompt(
    job_definition: dict[str, Any], *, workspace: str, report_path: str
) -> str:
    """Render one deterministic, self-contained initial job prompt."""
    job_id = job_definition["id"]
    sections = [
        f"# {job_definition['title']}",
        f"Job ID: `{job_id}`",
        "## Worker Contract\n" + _load_worker_contract(),
        "## Goal\n" + job_definition["goal"],
    ]

    workflow = job_definition.get("workflow")
    sections.append(
        "## Workflow\n"
        + (
            workflow
            if workflow is not None
            else (
                "Choose an appropriate workflow and methods to achieve the goal "
                "within the stated constraints."
            )
        )
    )

    requirements = job_definition.get("requirements", [])
    if requirements:
        sections.append(
            "## Requirements\n" + "\n".join(f"- {item}" for item in requirements)
        )

    constraints = [
        *job_definition.get("constraints", []),
        (
            "Do not mutate orchestrator-owned run, queue, dependency, parent, "
            "or job-status state."
        ),
    ]
    sections.append(
        "## Constraints\n" + "\n".join(f"- {item}" for item in constraints)
    )
    sections.append(
        "## Completion Conditions\n"
        + "\n".join(
            f"- {item}" for item in job_definition["completion_conditions"]
        )
    )

    context = [f"Workspace: `{workspace}`", *job_definition.get("context", [])]
    sections.append("## Context\n" + "\n".join(f"- {item}" for item in context))

    related_reports = job_definition.get("related_reports", [])
    if related_reports:
        sections.append(
            "## Related Reports\n"
            + "\n".join(f"- `{path}`" for path in related_reports)
        )

    escalation = job_definition.get("escalation") or (
        "If blocked by missing information, authority, a decision, or separately "
        "managed work, return `needs_input` with a precise question and relevant "
        "context."
    )
    sections.append("## Escalation\n" + escalation)

    if job_definition["report_required"]:
        report_expectation = (
            f"Write the final report to `{report_path}` before returning `completed`. "
            "The completed outcome must include that report path and a non-empty "
            "summary."
        )
    else:
        report_expectation = (
            f"A durable report is optional. If you create one, write it to "
            f"`{report_path}`. Return a non-empty summary with the final outcome."
        )
    sections.append("## Report Expectation\n" + report_expectation)

    recovery_policy = job_definition.get("recovery_policy")
    if recovery_policy is not None:
        recovery_requirements = [
            f"Effect: `{recovery_policy['effect']}`",
            f"Required recovery check before retry: {recovery_policy['check']}",
        ]
        if "idempotency_key" in recovery_policy:
            recovery_requirements.append(
                f"Idempotency key: `{recovery_policy['idempotency_key']}`"
            )
        sections.append(
            "## Recovery Requirements\n"
            + "\n".join(f"- {item}" for item in recovery_requirements)
        )

    sections.append("Begin the domain work immediately.")
    return "\n\n".join(sections) + "\n"


def _load_v4_job_definition(run_root: Path, job_id: str) -> dict[str, Any]:
    setup = load_json(Path(run_root) / "setup.json")
    validate_record("setup", setup)
    matches = [job for job in setup["jobs"] if job["id"] == job_id]
    if len(matches) != 1:
        raise OrchestratorError(
            f"setup must contain exactly one definition for job {job_id}"
        )
    return matches[0]


def render_v4_continuation_prompt(
    job: dict[str, Any],
    job_definition: dict[str, Any],
    *,
    answers: list[dict[str, str]],
    advisory_reports: list[str],
) -> str:
    """Render focused same-session input without importing other job scopes."""
    sections = [
        f"# Continue Job {job['id']}",
        "Continue the original job in this same session using the information below.",
        "## Original Job Goal\n" + job_definition["goal"],
    ]
    pending_question = job["pending_question"]
    if pending_question is not None:
        sections.append("## Pending Question\n" + pending_question["text"])
        if "context" in pending_question:
            sections.append("## Question Context\n" + pending_question["context"])

    for answer in answers:
        heading = (
            "Authoritative Answer"
            if answer["source"] == "authoritative"
            else "User Answer"
        )
        answer_details = [answer["text"], f"Answer to: {answer['question']}"]
        if "context" in answer:
            answer_details.append("Question context: " + answer["context"])
        sections.append(f"## {heading}\n" + "\n\n".join(answer_details))

    if advisory_reports:
        sections.append(
            "## Advisory Reports\n"
            + "\n".join(f"- `{path}`" for path in advisory_reports)
        )

    sections.append(
        "Continue from the current progress. Keep the original job goal, workflow, "
        "requirements, constraints, and completion conditions unchanged. Treat the "
        "answers and advisory reports only as input to that job; do not adopt or "
        "combine the advisory jobs' responsibilities. Do not begin unrelated work. "
        "Return `completed`, `needs_input`, or `failed` when control returns to the "
        "orchestrator."
    )
    return "\n\n".join(sections) + "\n"


def register_v4_jobs(
    run_root: Path,
    definition: dict[str, Any],
    *,
    controller: str,
    advisory_for: str | None = None,
) -> dict[str, Any]:
    """Atomically register validated definitions and authoritative queued jobs."""
    validate_record("job-definition", definition)
    requested = json.loads(json.dumps(definition["jobs"]))
    if advisory_for is not None:
        if not isinstance(advisory_for, str) or not advisory_for.strip():
            raise OrchestratorError("advisory origin job ID must be a non-empty string")
        _validate_v4_job_id(advisory_for)
        for job in requested:
            parent_id = job.get("parent_job_id")
            if parent_id is None:
                job["parent_job_id"] = advisory_for
            elif parent_id != advisory_for:
                raise OrchestratorError(
                    f"advisory job {job['id']} parent_job_id must be the origin job "
                    f"{advisory_for!r}"
                )
            if not job["report_required"]:
                raise OrchestratorError(
                    f"advisory job {job['id']} must require a durable report"
                )
    for job in requested:
        if not job["goal"].strip():
            raise OrchestratorError(f"job {job['id']} is missing a non-empty goal")
        recovery_policy = job.get("recovery_policy")
        if (
            recovery_policy is not None
            and recovery_policy["effect"] == "external_non_idempotent"
            and not recovery_policy["check"].strip()
        ):
            raise OrchestratorError(
                f"job {job['id']} external non-idempotent effect requires a "
                "non-empty recovery check"
            )
    requested_ids = [job["id"] for job in requested]
    if len(requested_ids) != len(set(requested_ids)):
        raise OrchestratorError("job definition IDs must be unique")
    for job_id in requested_ids:
        _validate_v4_job_id(job_id)

    run_root = Path(run_root)
    preflight_state = load_v4_state(run_root)
    preflight_collisions = sorted(set(requested_ids) & set(preflight_state["jobs"]))
    if preflight_collisions:
        raise OrchestratorError(
            "jobs are already registered: " + ", ".join(preflight_collisions)
        )
    preflight_origin = None
    if advisory_for is not None:
        preflight_origin = preflight_state["jobs"].get(advisory_for)
        if preflight_origin is None:
            raise OrchestratorError(f"unknown advisory origin job {advisory_for!r}")
        if preflight_origin["status"] != "waiting_for_input":
            raise OrchestratorError(
                f"advisory origin job {advisory_for} status "
                f"{preflight_origin['status']!r} is not waiting for input"
            )
    preflight_jobs = {
        **preflight_state["jobs"],
        **{
            job["id"]: {
                "depends_on": job.get("depends_on", []),
                "parent_job_id": job.get("parent_job_id"),
                "waiting_on": [],
            }
            for job in requested
        },
    }
    if preflight_origin is not None:
        preflight_jobs[advisory_for] = {
            **preflight_origin,
            "status": "waiting_for_job",
            "waiting_on": requested_ids,
        }
    _validate_v4_job_graph(preflight_jobs)

    with run_lock(run_root, controller):
        state = load_v4_state(run_root)
        setup_path = run_root / "setup.json"
        setup = load_json(setup_path)
        validate_record("setup", setup)

        configured_ids = [job["id"] for job in setup["jobs"]]
        if len(configured_ids) != len(set(configured_ids)):
            raise OrchestratorError("persisted setup job IDs must be unique")
        if set(configured_ids) != set(state["jobs"]):
            raise OrchestratorError(
                "persisted setup job definitions disagree with authoritative jobs"
            )

        collisions = sorted(set(requested_ids) & set(state["jobs"]))
        if collisions:
            raise OrchestratorError(
                "jobs are already registered: " + ", ".join(collisions)
            )

        origin = None
        if advisory_for is not None:
            origin = state["jobs"].get(advisory_for)
            if origin is None:
                raise OrchestratorError(f"unknown advisory origin job {advisory_for!r}")
            if origin["status"] != "waiting_for_input":
                raise OrchestratorError(
                    f"advisory origin job {advisory_for} status "
                    f"{origin['status']!r} is not waiting for input"
                )

        now = utc_now()
        next_sequence = max(
            (job["creation_sequence"] for job in state["jobs"].values()),
            default=0,
        )
        new_jobs: dict[str, dict[str, Any]] = {}
        for offset, job_definition in enumerate(requested, 1):
            job_id = job_definition["id"]
            new_jobs[job_id] = {
                "schema_version": CURRENT_RUN_VERSION,
                "id": job_id,
                "title": job_definition["title"],
                "status": "queued",
                "prompt_path": f"jobs/{job_id}/prompt.md",
                "session_ref": None,
                "priority": job_definition.get("priority", 0),
                "creation_sequence": next_sequence + offset,
                "depends_on": list(job_definition.get("depends_on", [])),
                "parent_job_id": job_definition.get("parent_job_id"),
                "waiting_on": [],
                "pending_question": None,
                "answers": [],
                "related_reports": list(job_definition.get("related_reports", [])),
                "report_required": job_definition["report_required"],
                "report_path": f"jobs/{job_id}/report.md",
                "checkpoint_path": None,
                "outcome": None,
                "recovery_policy": job_definition.get("recovery_policy"),
                "created_at": now,
                "updated_at": now,
                "revision": 1,
            }

        next_origin = None
        if origin is not None:
            next_origin = {
                **origin,
                "status": "waiting_for_job",
                "waiting_on": requested_ids,
                "updated_at": now,
                "revision": origin["revision"] + 1,
            }
        candidate_jobs = {**state["jobs"], **new_jobs}
        if next_origin is not None:
            candidate_jobs[advisory_for] = next_origin
        for job in new_jobs.values():
            validate_record("job", job)
            _validate_v4_job_paths(job)
        _validate_v4_job_graph(candidate_jobs)
        validate_v4_state_coherence(candidate_jobs, run_root=run_root)
        if next_origin is not None:
            validate_v4_job_transition_path(
                origin,
                next_origin,
                {**state["jobs"], **new_jobs},
                transition_path=["waiting_for_job"],
                run_root=run_root,
            )

        next_setup = {
            **setup,
            "jobs": [*setup["jobs"], *json.loads(json.dumps(requested))],
        }
        validate_record("setup", next_setup)
        next_run = {
            **state["run"],
            "job_ids": [*state["run"]["job_ids"], *requested_ids],
            "updated_at": now,
            "revision": state["run"]["revision"] + 1,
        }
        validate_record("run", next_run)

        staging_root = Path(tempfile.mkdtemp(prefix=".register.", dir=run_root))
        moved_job_roots: list[Path] = []
        run_path = run_root / "run.json"
        index_path = run_root / "jobs" / "index.json"
        original_run = run_path.read_bytes()
        original_setup = setup_path.read_bytes()
        original_index = index_path.read_bytes() if index_path.is_file() else None
        origin_path = (
            run_root / "jobs" / advisory_for / "job.json"
            if advisory_for is not None
            else None
        )
        original_origin = origin_path.read_bytes() if origin_path is not None else None
        origin_previous_path = (
            _v4_previous_job_path(origin_path) if origin_path is not None else None
        )
        original_origin_previous = (
            origin_previous_path.read_bytes()
            if origin_previous_path is not None and origin_previous_path.is_file()
            else None
        )
        try:
            for job_definition in requested:
                job_id = job_definition["id"]
                staged_job_root = staging_root / job_id
                write_v4_document(
                    staged_job_root / "job.json", "job", new_jobs[job_id]
                )
                prompt = render_v4_initial_prompt(
                    job_definition,
                    workspace=setup["workspace"],
                    report_path=new_jobs[job_id]["report_path"],
                )
                atomic_write(staged_job_root / "prompt.md", prompt.encode("utf-8"))
                atomic_write(staged_job_root / "report.md", b"")

            for job_id in requested_ids:
                target = run_root / "jobs" / job_id
                os.replace(staging_root / job_id, target)
                moved_job_roots.append(target)

            write_json(setup_path, next_setup)
            write_v4_document(run_path, "run", next_run)
            write_json(index_path, {"jobs": sorted(candidate_jobs)})
            if next_origin is not None and origin_path is not None:
                write_v4_document(
                    origin_path,
                    "job",
                    next_origin,
                    transition_path=["waiting_for_job"],
                )
            load_v4_state(run_root)
        except Exception as exc:
            rollback_error: Exception | None = None
            try:
                atomic_write(run_path, original_run)
                atomic_write(setup_path, original_setup)
                if original_index is None:
                    index_path.unlink(missing_ok=True)
                else:
                    atomic_write(index_path, original_index)
                if origin_path is not None and original_origin is not None:
                    atomic_write(origin_path, original_origin)
                if origin_previous_path is not None:
                    if original_origin_previous is None:
                        origin_previous_path.unlink(missing_ok=True)
                    else:
                        atomic_write(origin_previous_path, original_origin_previous)
                for job_root in moved_job_roots:
                    shutil.rmtree(job_root, ignore_errors=True)
            except Exception as rollback_exc:  # pragma: no cover - catastrophic I/O
                rollback_error = rollback_exc
            if rollback_error is not None:
                raise OrchestratorError(
                    f"job registration failed ({exc}) and rollback failed "
                    f"({rollback_error})"
                ) from exc
            raise OrchestratorError(f"job registration failed: {exc}") from exc
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)

    result: dict[str, Any] = {"registered": requested_ids}
    if advisory_for is not None:
        result["advisory_for"] = advisory_for
    return result


def validate_job_transition(current_status: str, next_status: str) -> None:
    if current_status not in JOB_STATUSES:
        raise OrchestratorError(f"unknown current job status {current_status!r}")
    if next_status not in JOB_STATUSES:
        raise OrchestratorError(f"unknown next job status {next_status!r}")
    if next_status not in JOB_STATUS_TRANSITIONS[current_status]:
        raise OrchestratorError(
            f"invalid job status transition {current_status!r} -> {next_status!r}"
        )


def validate_v4_job_transition(
    current: dict[str, Any],
    proposed: dict[str, Any],
    jobs: dict[str, dict[str, Any]],
    *,
    run_root: Path,
) -> None:
    """Validate one proposed status transition against the complete v4 state."""
    validate_v4_job_transition_path(
        current,
        proposed,
        jobs,
        transition_path=[proposed["status"]],
        run_root=run_root,
    )


def validate_v4_job_transition_path(
    current: dict[str, Any],
    proposed: dict[str, Any],
    jobs: dict[str, dict[str, Any]],
    *,
    transition_path: list[str],
    run_root: Path,
) -> None:
    """Validate a status path whose final coherent document is written once."""
    validate_record("job", proposed)
    if current["id"] != proposed["id"]:
        raise OrchestratorError("a job transition cannot change the job identity")
    job_id = current["id"]
    if jobs.get(job_id) != current:
        raise OrchestratorError(
            f"current job {job_id} does not match authoritative loaded state"
        )
    _validate_v4_job_paths(proposed)
    if not transition_path:
        raise OrchestratorError("a job transition path must not be empty")
    if transition_path[-1] != proposed["status"]:
        raise OrchestratorError(
            "a job transition path must end at the proposed status"
        )
    previous_status = current["status"]
    for next_status in transition_path:
        validate_job_transition(previous_status, next_status)
        previous_status = next_status

    candidate_jobs = dict(jobs)
    candidate_jobs[job_id] = proposed
    _validate_v4_job_graph(candidate_jobs)
    validate_v4_state_coherence(candidate_jobs, run_root=run_root)


def record_v4_session(
    run_root: Path,
    job_id: str,
    session_ref: str,
    *,
    controller: str,
) -> dict[str, Any]:
    """Atomically bind one transport session to a newly started job."""
    if not isinstance(session_ref, str) or not session_ref.strip():
        raise OrchestratorError("session reference must be a non-empty string")

    run_root = Path(run_root)
    with run_lock(run_root, controller):
        state = load_v4_state(run_root)
        current = state["jobs"].get(job_id)
        if current is None:
            raise OrchestratorError(f"unknown job {job_id!r}")

        existing = current["session_ref"]
        if existing is not None:
            if existing != session_ref:
                raise OrchestratorError(
                    f"job {job_id} already has a different session reference"
                )
            return {
                "job_id": job_id,
                "session_ref": existing,
                "status": current["status"],
                "recorded": False,
            }

        if current["status"] == "queued":
            transition_path = ["starting", "running"]
        elif current["status"] == "starting":
            transition_path = ["running"]
        else:
            raise OrchestratorError(
                f"job {job_id} status {current['status']!r} cannot accept an "
                "initial session reference"
            )

        proposed = {
            **current,
            "status": "running",
            "session_ref": session_ref,
            "updated_at": utc_now(),
            "revision": current["revision"] + 1,
        }
        write_v4_document(
            run_root / "jobs" / job_id / "job.json",
            "job",
            proposed,
            transition_path=transition_path,
        )

    return {
        "job_id": job_id,
        "session_ref": session_ref,
        "status": "running",
        "recorded": True,
    }


def record_v4_answer(
    run_root: Path,
    job_id: str,
    answer: str,
    *,
    source: str,
    controller: str,
) -> dict[str, Any]:
    """Record requested input and return a same-session continuation operation."""
    if not isinstance(answer, str) or not answer.strip():
        raise OrchestratorError("answer must be a non-empty string")
    if source not in {"authoritative", "user"}:
        raise OrchestratorError("answer source must be 'authoritative' or 'user'")
    normalized_answer = answer.strip()

    run_root = Path(run_root)
    with run_lock(run_root, controller):
        state = load_v4_state(run_root)
        current = state["jobs"].get(job_id)
        if current is None:
            raise OrchestratorError(f"unknown job {job_id!r}")
        if current["status"] != "waiting_for_input":
            raise OrchestratorError(
                f"job {job_id} status {current['status']!r} cannot accept an answer"
            )

        pending_question = current["pending_question"]
        if pending_question is None:  # Protected by state coherence; keep the API explicit.
            raise OrchestratorError(f"job {job_id} has no pending question")
        session_ref = current["session_ref"]
        if session_ref is None:
            raise OrchestratorError(f"job {job_id} has no stored session reference")

        answer_record = {
            "source": source,
            "question": pending_question["text"],
            **(
                {"context": pending_question["context"]}
                if "context" in pending_question
                else {}
            ),
            "text": normalized_answer,
        }
        continuation_prompt = render_v4_continuation_prompt(
            current,
            _load_v4_job_definition(run_root, job_id),
            answers=[*current.get("answers", []), answer_record],
            advisory_reports=[],
        )

        proposed = {
            **current,
            "status": "running",
            "pending_question": None,
            "outcome": None,
            "answers": [*current.get("answers", []), answer_record],
            "updated_at": utc_now(),
            "revision": current["revision"] + 1,
        }
        write_v4_document(
            run_root / "jobs" / job_id / "job.json",
            "job",
            proposed,
            transition_path=["running"],
        )

    return {
        "operation": "resume_job",
        "job_id": job_id,
        "session_ref": session_ref,
        "prompt": continuation_prompt,
        "status": "running",
        "answer": answer_record,
        "recorded": True,
    }


def record_v4_advisory_decision(
    run_root: Path,
    origin_job_id: str,
    advisory_job_id: str,
    decision: str,
    *,
    controller: str,
    replacement_job_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Apply an explicit decision for one failed or canceled advisory job."""
    if decision not in ADVISORY_FAILURE_DECISIONS:
        raise OrchestratorError(
            "advisory decision must be one of: "
            + ", ".join(ADVISORY_FAILURE_DECISIONS)
        )
    if decision == "select_another" and not replacement_job_id:
        raise OrchestratorError(
            "select_another requires a replacement advisory job ID"
        )
    if decision != "select_another" and replacement_job_id is not None:
        raise OrchestratorError(
            "a replacement advisory job applies only to select_another"
        )
    normalized_reason = reason.strip() if isinstance(reason, str) else ""
    if decision == "fail_origin" and not normalized_reason:
        raise OrchestratorError("fail_origin requires a non-empty reason")

    run_root = Path(run_root)
    with run_lock(run_root, controller):
        state = load_v4_state(run_root)
        origin = state["jobs"].get(origin_job_id)
        if origin is None:
            raise OrchestratorError(f"unknown origin job {origin_job_id!r}")
        if origin["status"] != "waiting_for_job":
            raise OrchestratorError(
                f"origin job {origin_job_id} status {origin['status']!r} is not "
                "waiting for an advisory job"
            )
        if advisory_job_id not in origin["waiting_on"]:
            raise OrchestratorError(
                f"origin job {origin_job_id} is not waiting on advisory job "
                f"{advisory_job_id}"
            )

        advisory = state["jobs"][advisory_job_id]
        if (
            advisory["parent_job_id"] != origin_job_id
            or not advisory["report_required"]
        ):
            raise OrchestratorError(
                f"job {advisory_job_id} is not a report-producing advisory job "
                f"for origin {origin_job_id}"
            )
        if advisory["status"] not in {"failed", "canceled"}:
            raise OrchestratorError(
                f"advisory job {advisory_job_id} status {advisory['status']!r} "
                "does not require a failure decision"
            )

        if decision == "keep_waiting":
            return {
                "decision": decision,
                "origin_job_id": origin_job_id,
                "advisory_job_id": advisory_job_id,
                "status": origin["status"],
                "waiting_on": list(origin["waiting_on"]),
                "run_status": state["run"]["status"],
                "recorded": False,
            }

        now = utc_now()
        transition_path: list[str] | None = None
        replacement = None
        if decision == "ask_user":
            pending_question = dict(origin["pending_question"])
            prior_context = pending_question.get("context")
            failure_context = (
                f"Advisory job {advisory_job_id} {advisory['status']} before "
                "providing its required report."
            )
            pending_question["context"] = (
                failure_context
                if prior_context is None
                else f"{failure_context} Original context: {prior_context}"
            )
            proposed = {
                **origin,
                "status": "waiting_for_input",
                "waiting_on": [],
                "pending_question": pending_question,
                "updated_at": now,
                "revision": origin["revision"] + 1,
            }
            transition_path = ["waiting_for_input"]
        elif decision == "select_another":
            replacement = state["jobs"].get(replacement_job_id)
            if replacement is None:
                raise OrchestratorError(
                    f"unknown replacement advisory job {replacement_job_id!r}"
                )
            if replacement_job_id == advisory_job_id:
                raise OrchestratorError(
                    "replacement advisory job must differ from the failed advisory job"
                )
            if (
                replacement["parent_job_id"] != origin_job_id
                or not replacement["report_required"]
            ):
                raise OrchestratorError(
                    f"job {replacement_job_id} is not a report-producing advisory "
                    f"job for origin {origin_job_id}"
                )
            if replacement["status"] in {"failed", "canceled"}:
                raise OrchestratorError(
                    f"replacement advisory job {replacement_job_id} status "
                    f"{replacement['status']!r} cannot replace another failed advisory"
                )
            waiting_on = []
            for awaited_id in origin["waiting_on"]:
                selected_id = (
                    replacement_job_id
                    if awaited_id == advisory_job_id
                    else awaited_id
                )
                if selected_id not in waiting_on:
                    waiting_on.append(selected_id)
            proposed = {
                **origin,
                "waiting_on": waiting_on,
                "updated_at": now,
                "revision": origin["revision"] + 1,
            }
        else:
            proposed = {
                **origin,
                "status": "failed",
                "waiting_on": [],
                "pending_question": None,
                "outcome": {
                    "status": "failed",
                    "summary": normalized_reason,
                    "context": (
                        f"Origin failed by explicit decision after advisory job "
                        f"{advisory_job_id} {advisory['status']}."
                    ),
                },
                "updated_at": now,
                "revision": origin["revision"] + 1,
            }
            transition_path = ["failed"]

        write_v4_document(
            run_root / "jobs" / origin_job_id / "job.json",
            "job",
            proposed,
            transition_path=transition_path,
        )
        updated_jobs = {**state["jobs"], origin_job_id: proposed}
        if decision == "select_another":
            updated_jobs = _reconcile_v4_advisory_reports(run_root, updated_jobs)
        run_status = _persist_v4_run_completion(
            run_root, state["run"], updated_jobs
        )
        recorded_origin = updated_jobs[origin_job_id]

    result = {
        "decision": decision,
        "origin_job_id": origin_job_id,
        "advisory_job_id": advisory_job_id,
        "status": recorded_origin["status"],
        "waiting_on": list(recorded_origin["waiting_on"]),
        "run_status": run_status,
        "recorded": True,
    }
    if replacement is not None:
        result["replacement_job_id"] = replacement_job_id
    return result


def normalize_v4_outcome(outcome: dict[str, Any]) -> dict[str, str]:
    """Return the strict minimal worker outcome with normalized text fields."""
    validate_record("outcome", outcome)
    normalized = {
        field: value.strip()
        for field, value in outcome.items()
    }
    validate_record("outcome", normalized)
    return normalized


def validate_v4_recovery_evidence(
    evidence: dict[str, Any],
    *,
    job_id: str | None = None,
    session_ref: str | None = None,
) -> None:
    """Validate supplied evidence without making it authoritative run state."""
    validate_record("recovery-evidence", evidence)
    if job_id is not None and evidence["job_id"] != job_id:
        raise OrchestratorError(
            f"transport evidence job_id {evidence['job_id']!r} does not match "
            f"{job_id!r}"
        )
    evidence_session = evidence.get("session_ref")
    if (
        session_ref is not None
        and evidence_session is not None
        and evidence_session != session_ref
    ):
        raise OrchestratorError(
            "transport evidence session_ref does not match the job session reference"
        )

    transport = evidence.get("transport")
    if transport is not None:
        observation = transport["observation"]
        status = transport["status"]
        response = transport.get("response")
        if observation != "direct" and status != "unknown":
            raise OrchestratorError(
                "unknown or unsupported transport observations must use status 'unknown'"
            )
        if response is not None and (
            observation != "direct" or status != "returned"
        ):
            raise OrchestratorError(
                "a transport response requires a direct 'returned' observation"
            )

    facts = evidence.get("facts", [])
    fact_keys: set[tuple[str, str]] = set()
    for fact in facts:
        source = fact["source"]
        subject = fact["subject"].strip()
        key = (source, subject)
        if key in fact_keys:
            raise OrchestratorError(
                f"recovery evidence repeats fact {subject!r} from source {source!r}"
            )
        fact_keys.add(key)

        source_is_direct = {
            "transport_response": (
                transport is not None
                and transport["observation"] == "direct"
                and transport["status"] == "returned"
                and transport.get("response") is not None
            ),
            "external_system": any(
                item["observation"] == "direct"
                for item in evidence.get("external_system", [])
            ),
            "repository_filesystem": (
                evidence.get("workspace") is not None
                and evidence["workspace"]["observation"] == "direct"
            ),
            "report": (
                evidence.get("report") is not None
                and evidence["report"]["observation"] == "direct"
            ),
            "checkpoint": (
                evidence.get("checkpoint") is not None
                and evidence["checkpoint"]["observation"] == "direct"
            ),
        }[source]
        if not source_is_direct:
            raise OrchestratorError(
                f"recovery fact source {source!r} requires a direct source observation"
            )
        if source == "transport_response" and subject == "job.outcome":
            response_status = transport["response"]["status"]
            if fact["value"].strip() != response_status:
                raise OrchestratorError(
                    "transport_response fact 'job.outcome' must match the returned "
                    "response status"
                )


def _reconcile_v4_recovery_facts(
    evidence: dict[str, Any], job: dict[str, Any]
) -> dict[str, Any]:
    """Resolve comparable direct facts by source precedence without hiding conflicts."""
    facts: list[dict[str, str]] = []

    transport = evidence.get("transport")
    transport_has_outcome_fact = any(
        fact["source"] == "transport_response"
        and fact["subject"].strip() == "job.outcome"
        for fact in evidence.get("facts", [])
    )
    if (
        transport is not None
        and transport["observation"] == "direct"
        and transport["status"] == "returned"
        and transport.get("response") is not None
        and not transport_has_outcome_fact
    ):
        facts.append({
            "source": "transport_response",
            "subject": "job.outcome",
            "value": transport["response"]["status"],
            "summary": "Outcome returned directly by the transport.",
        })

    facts.extend({
        "source": fact["source"],
        "subject": fact["subject"].strip(),
        "value": fact["value"].strip(),
        **(
            {"summary": fact["summary"].strip()}
            if "summary" in fact
            else {}
        ),
    } for fact in evidence.get("facts", []))

    persisted_outcome = job["outcome"]
    persisted_value = (
        persisted_outcome["status"]
        if persisted_outcome is not None
        else {
            "completed": "completed",
            "failed": "failed",
            "canceled": "canceled",
            "waiting_for_input": "needs_input",
        }.get(job["status"], "nonterminal")
    )
    facts.append({
        "source": "persisted_job_status",
        "subject": "job.outcome",
        "value": persisted_value,
        "summary": f"Persisted job status is {job['status']!r}.",
    })
    facts.sort(key=lambda fact: (
        fact["subject"], _V4_FACT_SOURCE_RANK[fact["source"]],
        fact["source"], fact["value"]
    ))

    resolutions = []
    contradictions = []
    for subject in sorted({fact["subject"] for fact in facts}):
        subject_facts = [fact for fact in facts if fact["subject"] == subject]
        preferred = subject_facts[0]
        resolutions.append({
            "subject": subject,
            "source": preferred["source"],
            "value": preferred["value"],
        })
        for conflicting in subject_facts[1:]:
            if conflicting["value"] == preferred["value"]:
                continue
            stale_nonterminal_status = (
                subject == "job.outcome"
                and conflicting["source"] == "persisted_job_status"
                and conflicting["value"] == "nonterminal"
            )
            contradictions.append({
                "subject": subject,
                "preferred_source": preferred["source"],
                "preferred_value": preferred["value"],
                "conflicting_source": conflicting["source"],
                "conflicting_value": conflicting["value"],
                "material": not stale_nonterminal_status,
                "reason": (
                    "lower-precedence persisted nonterminal state may lag direct facts"
                    if stale_nonterminal_status
                    else "direct sources report different material facts"
                ),
            })

    material = [item for item in contradictions if item["material"]]
    return {
        "fact_precedence": list(_V4_FACT_PRECEDENCE),
        "fact_resolution": resolutions,
        "contradictions": contradictions,
        "material_contradictions": material,
        "mutation_allowed": not material,
    }


def _validate_v4_completion_evidence(
    evidence: dict[str, Any] | None,
    *,
    job_id: str,
    session_ref: str,
) -> None:
    if evidence is None:
        return
    validate_v4_recovery_evidence(
        evidence, job_id=job_id, session_ref=session_ref
    )
    transport = evidence.get("transport")
    if transport is not None and transport["status"] == "active":
        raise OrchestratorError(
            f"job {job_id} cannot complete while supplied transport evidence "
            "shows an active turn"
        )


def _validate_v4_outcome_recording(
    run_root: Path,
    state: dict[str, Any],
    job_id: str,
    normalized: dict[str, str],
    *,
    session_ref: str | None,
    evidence: dict[str, Any] | None,
) -> tuple[dict[str, Any], str, list[str] | None, bool]:
    """Validate an outcome against current state without mutating it."""
    current = state["jobs"].get(job_id)
    if current is None:
        raise OrchestratorError(f"unknown job {job_id!r}")

    existing_session = current["session_ref"]
    if (
        session_ref is not None
        and existing_session is not None
        and existing_session != session_ref
    ):
        raise OrchestratorError(
            f"job {job_id} already has a different session reference"
        )
    effective_session = existing_session or session_ref
    if effective_session is None:
        raise OrchestratorError(
            f"job {job_id} outcome requires an existing or supplied session reference"
        )

    if evidence is not None:
        validate_v4_recovery_evidence(
            evidence,
            job_id=job_id,
            session_ref=effective_session,
        )
        fact_report = _reconcile_v4_recovery_facts(evidence, current)
        if fact_report["material_contradictions"]:
            raise OrchestratorError(
                f"job {job_id} outcome mutation is blocked by material recovery "
                "evidence contradictions"
            )
    if normalized["status"] == "completed":
        _validate_v4_completion_evidence(
            evidence,
            job_id=job_id,
            session_ref=effective_session,
        )

    existing_outcome = current["outcome"]
    if existing_outcome == normalized:
        return current, effective_session, None, True

    initial_path = {
        "queued": ["starting", "running"],
        "starting": ["running"],
        "running": [],
        "recovering": [],
    }.get(current["status"])

    if normalized["status"] == "completed" and initial_path is not None:
        completion_candidate = {
            **current,
            "status": "completed",
            "session_ref": effective_session,
            "outcome": normalized,
        }
        _validate_v4_completion_coherence(
            completion_candidate, state["jobs"], run_root=run_root
        )

    if existing_outcome is not None:
        raise OrchestratorError(
            f"job {job_id} already has a different worker outcome"
        )
    if initial_path is None:
        raise OrchestratorError(
            f"job {job_id} status {current['status']!r} cannot accept a worker outcome"
        )
    return current, effective_session, initial_path, False


def record_v4_outcome(
    run_root: Path,
    job_id: str,
    outcome: dict[str, Any],
    *,
    controller: str,
    session_ref: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize and atomically record one worker outcome and optional session."""
    normalized = normalize_v4_outcome(outcome)
    if session_ref is not None and (
        not isinstance(session_ref, str) or not session_ref.strip()
    ):
        raise OrchestratorError("session reference must be a non-empty string")

    run_root = Path(run_root)
    with run_lock(run_root, controller):
        state = load_v4_state(run_root)
        current, effective_session, initial_path, identical = (
            _validate_v4_outcome_recording(
                run_root,
                state,
                job_id,
                normalized,
                session_ref=session_ref,
                evidence=evidence,
            )
        )
        if identical:
            reconciled_jobs = _reconcile_v4_advisory_reports(
                run_root, state["jobs"]
            )
            run_status = _persist_v4_run_completion(
                run_root, state["run"], reconciled_jobs
            )
            return {
                "job_id": job_id,
                "session_ref": effective_session,
                "status": current["status"],
                "run_status": run_status,
                "outcome": normalized,
                "ready_job_ids": derive_v4_ready_job_ids(reconciled_jobs),
                "recorded": False,
            }

        next_status = {
            "completed": "completed",
            "needs_input": "waiting_for_input",
            "failed": "failed",
        }[normalized["status"]]
        pending_question = (
            {
                "text": normalized["question"],
                "context": normalized.get("context", normalized["summary"]),
            }
            if normalized["status"] == "needs_input"
            else None
        )
        proposed = {
            **current,
            "status": next_status,
            "session_ref": effective_session,
            "pending_question": pending_question,
            "outcome": normalized,
            "updated_at": utc_now(),
            "revision": current["revision"] + 1,
        }
        write_v4_document(
            run_root / "jobs" / job_id / "job.json",
            "job",
            proposed,
            transition_path=[*initial_path, next_status],
        )
        post_mutation_jobs = {**state["jobs"], job_id: proposed}
        post_mutation_jobs = _reconcile_v4_advisory_reports(
            run_root, post_mutation_jobs
        )
        run_status = _persist_v4_run_completion(
            run_root, state["run"], post_mutation_jobs
        )

    return {
        "job_id": job_id,
        "session_ref": effective_session,
        "status": next_status,
        "run_status": run_status,
        "outcome": normalized,
        "ready_job_ids": derive_v4_ready_job_ids(post_mutation_jobs),
        "recorded": True,
    }


def repair_v4_job(
    run_root: Path,
    job_id: str,
    disposition: str,
    reason: str,
    *,
    controller: str,
) -> dict[str, Any]:
    """Atomically resolve one nonterminal version-4 job by operator disposition."""
    if disposition == "completed":
        raise OrchestratorError(
            "repair cannot claim completion; record a coherent completed outcome and "
            "required report with outcome, or reconcile them with recover"
        )
    if disposition not in {"failed", "canceled"}:
        raise OrchestratorError(
            "repair disposition must be either 'failed' or 'canceled'"
        )
    if not isinstance(reason, str) or not reason.strip():
        raise OrchestratorError("repair reason must be a non-empty string")
    normalized_reason = reason.strip()

    run_root = Path(run_root)
    with run_lock(run_root, controller):
        state = load_v4_state(run_root)
        current = state["jobs"].get(job_id)
        if current is None:
            raise OrchestratorError(f"unknown job {job_id!r}")
        if current["status"] in _TERMINAL_JOB_STATUSES:
            raise OrchestratorError(
                f"job {job_id} is already terminal with status "
                f"{current['status']!r}; cannot repair it to {disposition!r}"
            )

        if disposition == "failed":
            transition_path = {
                "queued": ["starting", "running", "failed"],
                "starting": ["running", "failed"],
                "running": ["failed"],
                "waiting_for_input": ["running", "failed"],
                "waiting_for_job": ["failed"],
                "recovering": ["failed"],
            }.get(current["status"], ["failed"])
            outcome: dict[str, Any] | None = {
                "status": "failed",
                "summary": normalized_reason,
            }
        else:
            transition_path = ["canceled"]
            outcome = None

        repaired_at = utc_now()
        proposed = {
            **current,
            "status": disposition,
            "waiting_on": [],
            "pending_question": None,
            "outcome": outcome,
            "repair": {
                "disposition": disposition,
                "reason": normalized_reason,
                "repaired_at": repaired_at,
                "previous_status": current["status"],
                "previous_outcome": current["outcome"],
                "previous_pending_question": current["pending_question"],
                "previous_waiting_on": list(current["waiting_on"]),
            },
            "updated_at": repaired_at,
            "revision": current["revision"] + 1,
        }
        write_v4_document(
            run_root / "jobs" / job_id / "job.json",
            "job",
            proposed,
            transition_path=transition_path,
        )
        post_mutation_jobs = {**state["jobs"], job_id: proposed}
        run_status = _persist_v4_run_completion(
            run_root, state["run"], post_mutation_jobs
        )
        verified_state = load_v4_state(run_root)

    return {
        "repaired": True,
        "job_id": job_id,
        "disposition": disposition,
        "reason": normalized_reason,
        "run_status": run_status,
        "ready_job_ids": verified_state["ready_job_ids"],
    }


def _render_v4_recovery_continuation(job_id: str) -> str:
    return (
        f"# Recovery Status for Job {job_id}\n\n"
        "Continue in this same session; do not restart the job or repeat completed "
        "work. Inspect the current progress and return the job's current precise "
        "blocking question, failure, or final result as `completed`, `needs_input`, "
        "or `failed`.\n"
    )


def _read_v4_recovery_text(path: Path, *, description: str) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as exc:
        raise OrchestratorError(f"cannot read {description} from {path}: {exc}") from exc
    return text.strip() or None


def render_v4_replacement_prompt(
    run_root: Path,
    job: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    """Render a replacement prompt from available durable and transport facts."""
    run_root = Path(run_root)
    original_prompt = _read_v4_recovery_text(
        run_root / job["prompt_path"], description=f"original prompt for job {job['id']}"
    )
    if original_prompt is None:
        raise OrchestratorError(
            f"original prompt for job {job['id']} is missing or empty: "
            f"{job['prompt_path']}"
        )

    sections = [
        f"# Recover Job {job['id']} in a Replacement Session",
        "## Original Job Prompt\n" + original_prompt,
    ]

    transport = evidence.get("transport")
    if transport is not None and transport["observation"] == "direct":
        transcript = []
        if "transcript_ref" in transport:
            transcript.append(f"Reference: `{transport['transcript_ref']}`")
        if "transcript_content" in transport:
            transcript.append(transport["transcript_content"].strip())
        if transcript:
            sections.append("## Available Transport Transcript\n" + "\n\n".join(transcript))

    for heading, field, authoritative_path in (
        ("Current Report", "report", job["report_path"]),
        ("Current Checkpoint", "checkpoint", job["checkpoint_path"]),
    ):
        observation = evidence.get(field)
        direct_observation = (
            observation
            if observation is not None and observation["observation"] == "direct"
            else None
        )
        content = (
            _read_v4_recovery_text(
                run_root / authoritative_path,
                description=f"{field} for job {job['id']}",
            )
            if authoritative_path is not None
            else None
        )
        if content is None and direct_observation is None:
            continue
        details = []
        path = (
            direct_observation["path"]
            if direct_observation is not None
            else authoritative_path
        )
        details.append(f"Path: `{path}`")
        if direct_observation is not None and "summary" in direct_observation:
            details.append("Observation: " + direct_observation["summary"].strip())
        if content is not None:
            details.append(content)
        sections.append(f"## {heading}\n" + "\n\n".join(details))

    if job["related_reports"]:
        reports = []
        for report_path in job["related_reports"]:
            content = _read_v4_recovery_text(
                run_root / report_path,
                description=f"related report for job {job['id']}",
            )
            if content is not None:
                reports.append(f"### `{report_path}`\n{content}")
        if reports:
            sections.append("## Related Reports\n" + "\n\n".join(reports))

    workspace = evidence.get("workspace")
    if workspace is not None and workspace["observation"] == "direct":
        sections.append(
            "## Workspace Observation\n"
            f"Path: `{workspace['path']}`\n\n{workspace['summary'].strip()}"
        )

    recovery_check = evidence.get("recovery_check")
    if recovery_check is not None:
        details = [
            f"Configured check: {recovery_check['check'].strip()}",
            f"Result: `{recovery_check['result']}`",
            recovery_check["summary"].strip(),
        ]
        if "reference" in recovery_check:
            details.append(f"Reference: `{recovery_check['reference']}`")
        sections.append("## Recovery Check Result\n" + "\n\n".join(details))

    pending_question = job["pending_question"]
    if pending_question is not None:
        details = [pending_question["text"]]
        if "context" in pending_question:
            details.append(pending_question["context"])
        sections.append("## Pending Question\n" + "\n\n".join(details))

    findings = evidence.get("recovery_findings", [])
    if findings:
        sections.append(
            "## Recovery Findings\n"
            + "\n".join(f"- {finding.strip()}" for finding in findings)
        )

    sections.append(
        "Inspect the supplied recovery facts before acting. Continue the same job from "
        "the durable progress without repeating completed work or uncertain side "
        "effects. If the completion conditions are already satisfied, return a normal "
        "`completed` outcome and report. If evidence materially conflicts or safe "
        "continuation is unclear, return `needs_input` or `failed` with the precise "
        "issue instead of guessing."
    )
    return "\n\n".join(sections) + "\n"


def _reconcile_v4_active_session(
    run_root: Path,
    job_id: str,
    evidence: dict[str, Any],
    *,
    controller: str,
) -> bool:
    """Restore recovering state only after transport directly confirms activity."""
    with run_lock(run_root, controller):
        state = load_v4_state(run_root)
        current = state["jobs"].get(job_id)
        if current is None:
            raise OrchestratorError(f"unknown job {job_id!r}")
        validate_v4_recovery_evidence(
            evidence,
            job_id=job_id,
            session_ref=current["session_ref"],
        )
        transport = evidence.get("transport")
        if (
            transport is None
            or transport["observation"] != "direct"
            or transport["status"] != "active"
        ):
            raise OrchestratorError(
                "active-session recovery requires direct active transport evidence"
            )
        if current["status"] == "running":
            return False
        if current["status"] != "recovering":
            raise OrchestratorError(
                f"job {job_id} status {current['status']!r} cannot be restored from "
                "active-session evidence"
            )

        proposed = {
            **current,
            "status": "running",
            "updated_at": utc_now(),
            "revision": current["revision"] + 1,
        }
        write_v4_document(
            run_root / "jobs" / job_id / "job.json",
            "job",
            proposed,
            transition_path=["running"],
        )
        return True


def _mark_v4_replacement_recovering(
    run_root: Path,
    job_id: str,
    evidence: dict[str, Any],
    *,
    controller: str,
) -> bool:
    """Record only that an unavailable-session replacement is being recovered."""
    with run_lock(run_root, controller):
        state = load_v4_state(run_root)
        current = state["jobs"].get(job_id)
        if current is None:
            raise OrchestratorError(f"unknown job {job_id!r}")
        validate_v4_recovery_evidence(
            evidence,
            job_id=job_id,
            session_ref=current["session_ref"],
        )
        transport = evidence.get("transport")
        if (
            transport is None
            or transport["observation"] != "direct"
            or transport["status"] not in {"canceled", "lost", "unavailable"}
        ):
            raise OrchestratorError(
                "replacement recovery requires direct unavailable transport evidence"
            )
        _require_v4_safe_external_retry(current, evidence)
        if current["status"] == "recovering":
            return False
        if current["status"] not in {
            "starting", "running", "waiting_for_input", "waiting_for_job",
        }:
            raise OrchestratorError(
                f"job {job_id} status {current['status']!r} cannot start replacement "
                "recovery"
            )

        proposed = {
            **current,
            "status": "recovering",
            "updated_at": utc_now(),
            "revision": current["revision"] + 1,
        }
        write_v4_document(
            run_root / "jobs" / job_id / "job.json",
            "job",
            proposed,
            transition_path=["recovering"],
        )
        return True


def _v4_safe_external_retry_basis(
    job: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any] | None:
    """Return the evidence that makes external-effect retry safe, if any."""
    policy = job["recovery_policy"]
    if policy is None or policy["effect"] != "external_non_idempotent":
        return None

    recovery_check = evidence.get("recovery_check")
    if (
        recovery_check is not None
        and recovery_check["check"].strip() != policy["check"].strip()
    ):
        raise OrchestratorError(
            f"job {job['id']} supplied recovery check does not match its configured "
            "job-level check"
        )
    if recovery_check is not None and recovery_check["result"] == "negative":
        return {
            "kind": "configured_recovery_check",
            "check": policy["check"],
            "result": "negative",
            "summary": recovery_check["summary"],
        }

    external_states = {
        item["effect_state"]
        for item in evidence.get("external_system", [])
        if item["observation"] == "direct"
    }
    if external_states == {"absent"}:
        return {
            "kind": "external_system_state",
            "result": "absent",
            "systems": sorted(
                item["system"]
                for item in evidence["external_system"]
                if item["observation"] == "direct"
            ),
        }

    durable_sources = [
        source
        for source in ("workspace", "report", "checkpoint")
        if evidence.get(source) is not None
        and evidence[source]["observation"] == "direct"
        and evidence[source].get("effect_state") == "absent"
    ]
    durable_confirmed = any(
        evidence.get(source) is not None
        and evidence[source]["observation"] == "direct"
        and evidence[source].get("effect_state") == "confirmed"
        for source in ("workspace", "report", "checkpoint")
    )
    if durable_sources and not durable_confirmed:
        return {
            "kind": "durable_local_effect_evidence",
            "result": "absent",
            "sources": durable_sources,
        }

    if "idempotency_key" in policy:
        return {
            "kind": "idempotency_key",
            "idempotency_key": policy["idempotency_key"],
        }

    return None


def _require_v4_safe_external_retry(
    job: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any] | None:
    """Return the evidence that makes external-effect retry safe or reject it."""
    policy = job["recovery_policy"]
    if policy is None or policy["effect"] != "external_non_idempotent":
        return None
    basis = _v4_safe_external_retry_basis(job, evidence)
    if basis is not None:
        return basis

    raise OrchestratorError(
        f"job {job['id']} has no evidence establishing safe external-effect retry"
    )


def reconcile_v4_transport_response(
    run_root: Path,
    job_id: str,
    evidence: dict[str, Any],
    *,
    controller: str,
    apply: bool = False,
) -> dict[str, Any]:
    """Plan or apply recovery from direct transport session evidence."""
    run_root = Path(run_root)
    validate_v4_recovery_evidence(evidence)
    state = load_v4_state(run_root)
    current = state["jobs"].get(job_id)
    if current is None:
        raise OrchestratorError(f"unknown job {job_id!r}")
    validate_v4_recovery_evidence(
        evidence,
        job_id=job_id,
        session_ref=current["session_ref"],
    )
    fact_report = _reconcile_v4_recovery_facts(evidence, current)
    if fact_report["material_contradictions"]:
        return {
            "job_id": job_id,
            "session_ref": current["session_ref"],
            "classification": "contradictory_recovery_evidence",
            "apply": apply,
            "status": current["status"],
            "recommended_action": "resolve_material_contradictions",
            "replacement_allowed": False,
            "state_changed": False,
            **fact_report,
        }

    transport = evidence.get("transport")
    if transport is None or transport["observation"] != "direct":
        raise OrchestratorError(
            "session recovery requires direct transport evidence"
        )

    transport_status = transport["status"]
    if transport_status in {"active", "available"}:
        if current["status"] not in {"running", "recovering"}:
            raise OrchestratorError(
                f"job {job_id} status {current['status']!r} cannot use active or "
                "available session recovery"
            )
        if current["session_ref"] is None:
            raise OrchestratorError(
                f"job {job_id} must record its transport session before session "
                "recovery"
            )

        active = transport_status == "active"
        instruction: dict[str, Any] = {
            "kind": "keep_running" if active else "continue_session",
            "session_ref": current["session_ref"],
            "instruction": (
                "Keep the existing turn running and use the transport's native status "
                "facility to observe it. Do not create replacement execution."
                if active
                else "Use the transport's native continuation facility for this existing "
                "session. Do not create replacement execution."
            ),
        }
        if not active:
            instruction["prompt"] = _render_v4_recovery_continuation(job_id)

        result: dict[str, Any] = {
            "job_id": job_id,
            "session_ref": current["session_ref"],
            "classification": "active_session" if active else "available_session",
            "apply": apply,
            "status": "running" if active else current["status"],
            "recommended_action": (
                "keep_existing_session_running"
                if active
                else "continue_existing_session_for_outcome"
            ),
            "replacement_allowed": False,
            "transport_instruction": instruction,
            "state_changed": False,
            **fact_report,
        }
        if active and current["status"] == "recovering":
            result["state_transition"] = {
                "from": "recovering",
                "to": "running",
            }
        if apply and active:
            result["state_changed"] = _reconcile_v4_active_session(
                run_root,
                job_id,
                evidence,
                controller=controller,
            )
        return result

    if transport_status in {"canceled", "lost", "unavailable"}:
        if current["status"] not in {
            "starting", "running", "waiting_for_input", "waiting_for_job", "recovering",
        }:
            raise OrchestratorError(
                f"job {job_id} status {current['status']!r} cannot use replacement "
                "session recovery"
            )
        if current["session_ref"] is None:
            raise OrchestratorError(
                f"job {job_id} must have a stored unavailable session before replacement"
            )
        local_sources = [
            source
            for source in ("workspace", "report", "checkpoint")
            if evidence.get(source) is not None
            and evidence[source]["observation"] == "direct"
        ]
        ordinary_local_recovery = (
            current["recovery_policy"] is None and bool(local_sources)
        )
        recovery_policy = current["recovery_policy"]
        external_effect_policy = (
            recovery_policy is not None
            and recovery_policy["effect"] == "external_non_idempotent"
        )
        recovery_check = evidence.get("recovery_check")
        if external_effect_policy:
            check_instruction = {
                "check": recovery_policy["check"],
                "accepted_results": ["positive", "negative", "unknown"],
                **(
                    {"idempotency_key": recovery_policy["idempotency_key"]}
                    if "idempotency_key" in recovery_policy
                    else {}
                ),
            }
            if (
                recovery_check is not None
                and recovery_check["check"].strip() != recovery_policy["check"].strip()
            ):
                raise OrchestratorError(
                    f"job {job_id} supplied recovery check does not match its "
                    "configured job-level check"
                )

            external_observations = evidence.get("external_system", [])
            external_states = {
                item["effect_state"]
                for item in external_observations
                if item["observation"] == "direct"
            }
            durable_states = {
                evidence[source]["effect_state"]
                for source in ("workspace", "report", "checkpoint")
                if evidence.get(source) is not None
                and evidence[source]["observation"] == "direct"
                and "effect_state" in evidence[source]
            }
            effect_confirmed = (
                recovery_check is not None
                and recovery_check["result"] == "positive"
            ) or "confirmed" in external_states or "confirmed" in durable_states
            if effect_confirmed:
                confirmed_result = {
                    "job_id": job_id,
                    "session_ref": current["session_ref"],
                    "classification": "external_effect_confirmed",
                    "transport_status": transport_status,
                    "apply": apply,
                    "status": current["status"],
                    "recommended_action": "reconcile_confirmed_external_effect",
                    "replacement_allowed": False,
                    "automatic_retry_allowed": False,
                    "state_changed": False,
                    **fact_report,
                }
                if recovery_check is not None and recovery_check["result"] == "positive":
                    confirmed_result["recovery_check_result"] = dict(recovery_check)
                else:
                    confirmed_result["external_effect_evidence"] = {
                        "external_system_states": sorted(external_states),
                        "durable_local_states": sorted(durable_states),
                    }
                return confirmed_result

            safe_retry_basis = _v4_safe_external_retry_basis(current, evidence)

            external_query_attempted = (
                recovery_check is not None or bool(external_observations)
            )
            if safe_retry_basis is None and not external_query_attempted:
                return {
                    "job_id": job_id,
                    "session_ref": current["session_ref"],
                    "classification": "recovery_check_required",
                    "transport_status": transport_status,
                    "apply": apply,
                    "status": current["status"],
                    "recommended_action": "perform_configured_recovery_check",
                    "replacement_allowed": False,
                    "recovery_check_instruction": check_instruction,
                    "state_changed": False,
                    **fact_report,
                }
            if safe_retry_basis is None:
                return {
                    "job_id": job_id,
                    "session_ref": current["session_ref"],
                    "classification": "external_outcome_undecidable",
                    "transport_status": transport_status,
                    "apply": apply,
                    "status": current["status"],
                    "recommended_action": (
                        "request_user_authority_or_recovery_investigation"
                    ),
                    "replacement_allowed": False,
                    "automatic_retry_allowed": False,
                    "safe_action_evidence": {
                        "transport_outcome": False,
                        "idempotency_key": "idempotency_key" in recovery_policy,
                        "external_query": bool(
                            recovery_check is not None
                            and recovery_check["result"] != "unknown"
                            or external_states & {"confirmed", "absent"}
                        ),
                        "durable_local_effect": bool(
                            durable_states & {"confirmed", "absent"}
                        ),
                    },
                    "uncertainty": (
                        "The unavailable transport, configured external query, "
                        "idempotency policy, and durable local evidence cannot establish "
                        "whether the external effect occurred or whether retry is safe."
                    ),
                    "state_changed": False,
                    **fact_report,
                }
        prompt = render_v4_replacement_prompt(run_root, current, evidence)
        result = {
            "job_id": job_id,
            "session_ref": current["session_ref"],
            "classification": "unavailable_session",
            "transport_status": transport_status,
            "apply": apply,
            "status": "recovering" if apply else current["status"],
            "recommended_action": "start_replacement_session",
            "replacement_allowed": True,
            "transport_instruction": {
                "kind": "start_replacement_session",
                "prior_session_ref": current["session_ref"],
                "correlation": {
                    "run_id": state["run"]["run_id"],
                    "job_id": job_id,
                },
                "prompt": prompt,
            },
            "state_changed": False,
            **fact_report,
        }
        if ordinary_local_recovery:
            result["reconciliation_basis"] = {
                "kind": "inspectable_local_state",
                "sources": local_sources,
                "recovery_policy_required": False,
            }
        elif external_effect_policy:
            result["reconciliation_basis"] = safe_retry_basis
        if current["status"] != "recovering":
            result["state_transition"] = {
                "from": current["status"],
                "to": "recovering",
            }
        if apply:
            result["state_changed"] = _mark_v4_replacement_recovering(
                run_root,
                job_id,
                evidence,
                controller=controller,
            )
        return result

    if transport_status != "returned" or transport.get("response") is None:
        raise OrchestratorError(
            "completed response reconciliation requires direct returned transport "
            "evidence with a response"
        )
    normalized = normalize_v4_outcome(transport["response"])
    if normalized["status"] != "completed":
        raise OrchestratorError(
            "completed response reconciliation requires outcome status 'completed'"
        )

    _, effective_session, _, identical = _validate_v4_outcome_recording(
        run_root,
        state,
        job_id,
        normalized,
        session_ref=evidence.get("session_ref"),
        evidence=evidence,
    )
    result: dict[str, Any] = {
        "job_id": job_id,
        "session_ref": effective_session,
        "classification": (
            "recorded_transport_response"
            if identical
            else "unrecorded_transport_response"
        ),
        "response_status": "completed",
        "apply": apply,
        "recommended_action": "none" if identical else "record_transport_response",
        **fact_report,
    }
    if not apply:
        return result

    recorded = record_v4_outcome(
        run_root,
        job_id,
        normalized,
        controller=controller,
        session_ref=evidence.get("session_ref"),
        evidence=evidence,
    )
    result.update({
        "recorded": recorded["recorded"],
        "status": recorded["status"],
        "run_status": recorded["run_status"],
        "outcome": recorded["outcome"],
        "ready_job_ids": recorded["ready_job_ids"],
        "recommended_action": "continue_normal_control_loop",
    })
    return result
