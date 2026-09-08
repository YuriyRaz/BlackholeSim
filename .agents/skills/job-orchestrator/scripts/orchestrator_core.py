"""Shared persistence and validation primitives for the trusted protocol."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    return f"{prefix}-{hashlib.sha256(seed).hexdigest()[:20].upper()}"


def random_id(prefix: str) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,15}", prefix):
        raise OrchestratorError("ID prefix must be 1-16 uppercase ASCII characters")
    return f"{prefix}-{uuid.uuid4().hex[:20]}"


_SLUG_MAX_LENGTH = 50


def slugify(text: str) -> str:
    """Convert free-form text into a filesystem-safe slug."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if len(slug) > _SLUG_MAX_LENGTH:
        slug = slug[:_SLUG_MAX_LENGTH].rstrip("-")
    return slug or "run"


def chronological_run_id(goal: str, name: str | None = None) -> str:
    """Build a timestamp-first run ID: YYYY-MM-DDTHHMMSSZ-<slug>."""
    now = utc_now()
    timestamp = now.replace(":", "").replace("-", "").replace(".", "T")[:18]
    timestamp = (
        f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
        f"T{timestamp[9:15]}Z"
    )
    return f"{timestamp}-{slugify(name if name is not None else goal)}"


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
            if char == "\\":
                escape = True
            elif char == '"':
                in_string = not in_string
            elif not in_string:
                if char in "[{":
                    depth += 1
                elif char in "]}":
                    depth -= 1
                    if depth == 1 and char == "}":
                        count += 1
        partial_info = (
            f"\nBest effort partial read: Found {count} complete top-level "
            "objects before failure."
        )
    return (
        f"JSON truncation or syntax error at line {error_line} "
        f"(col {exc.colno}): {exc.msg}.\n"
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


def _atomic_temporary_prefix(path: Path) -> str:
    return f".{path.name}."


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


SCHEMA_VERSION = 6
V6 = 6
V6_REVISION = "v6-closed"
SCHEMA_ROOT = Path(__file__).resolve().parent.parent / "schemas"
_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}
SCHEMA_REGISTRY = {
    6: frozenset({
        "cancellation-transaction",
        "finding-disposition",
        "goal-gate",
        "goal-gate-result",
        "response-transaction",
        "role-result",
        "campaign-envelope",
        "graph-policy",
        "authority",
        "role",
        "context-snapshot",
        "typed-dependency-edge",
        "dynamic-batch",
        "progress-fingerprint",
        "goal-judgment",
        "finding",
        "finding-group",
        "hypothesis-result",
        "synthesis-result",
        "work-plan",
        "campaign-terminal-claim",
        "strategy-decision",
        "graph-expansion-plan",
        "retained-expansion",
        "expansion-commit",
        "graph-transaction",
        "activation",
        "graph-generation",
        "run",
        "setup",
        "job-definition",
        "job",
        "dispatch",
        "outcome",
        "artifact",
        "completion-claim",
        "condition-result",
        "terminal-commit",
        "recovery",
        "verifier-assignment",
        "repair-gate-history",
    })
}


def load_schema(kind: str, version: int = SCHEMA_VERSION) -> dict[str, Any]:
    if version != SCHEMA_VERSION:
        raise OrchestratorError(f"unsupported schema {kind!r} version {version}; only version {SCHEMA_VERSION} is accepted")
    if kind not in SCHEMA_REGISTRY.get(SCHEMA_VERSION, frozenset()):
        raise OrchestratorError(f"unsupported schema kind {kind!r} for version {version}")
    if kind not in _SCHEMA_CACHE:
        path = SCHEMA_ROOT / f"v{SCHEMA_VERSION}" / f"{kind}.schema.json"
        schema = load_json(path)
        if not isinstance(schema, dict):
            raise OrchestratorError(f"schema {path} must be a JSON object")
        _SCHEMA_CACHE[kind] = schema
    return _SCHEMA_CACHE[kind]


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


def _validate_schema(
    value: Any,
    schema: dict[str, Any],
    location: str,
    root_schema: dict[str, Any] | None = None,
) -> None:
    root_schema = root_schema or schema
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        target = root_schema.get("$defs", {}).get(reference.removeprefix("#/$defs/"))
        if not isinstance(target, dict):
            raise OrchestratorError(
                f"Schema validation error at `{location}`: unresolved schema reference."
            )
        _validate_schema(value, target, location, root_schema)
        return

    def _raise(message: str) -> None:
        raise OrchestratorError(f"Schema validation error at `{location}`: {message}.")

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
        _validate_schema(value, condition, location, root_schema)
    if "if" in schema:
        try:
            _validate_schema(value, schema["if"], location, root_schema)
        except OrchestratorError:
            branch = schema.get("else")
        else:
            branch = schema.get("then")
        if branch is not None:
            _validate_schema(value, branch, location, root_schema)
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
                _validate_schema(value[name], child, f"{location}.{name}", root_schema)
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            _raise(f"must contain at least {schema['minItems']} items")
        if schema.get("uniqueItems"):
            encoded = [canonical_bytes(item) for item in value]
            if len(encoded) != len(set(encoded)):
                _raise("must contain unique items")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_schema(item, schema["items"], f"{location}[{index}]", root_schema)
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            _raise(f"must contain at least {schema['minLength']} characters")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            _raise("has an invalid format")
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
    if version != SCHEMA_VERSION:
        raise OrchestratorError(f"{kind}.schema_version must equal {SCHEMA_VERSION}")
    _validate_schema(value, load_schema(kind), kind)


def classify_run_protocol(run_root: Path) -> dict[str, Any]:
    """Report whether a run satisfies the trusted v6 dynamic protocol contract."""
    run = load_json(Path(run_root) / "run.json")
    version = run.get("schema_version")
    if version == 5:
        return {"version": 5, "trust": "untrusted", "mutable": False,
                "reason": "v5 runs are not supported by the current runtime"}
    if version == V6:
        revision = run.get("protocol_revision")
        if revision != V6_REVISION:
            return {"version": V6, "revision": revision, "trust": "unknown", "mutable": False}
        return {"version": V6, "revision": revision, "trust": "trusted", "mutable": True}
    return {"version": version, "trust": "unknown", "mutable": False}


def reject_v5_or_earlier(run: dict[str, Any]) -> None:
    """Raise if run is version 5 or earlier."""
    version = run.get("schema_version")
    if version is not None and version < V6:
        raise OrchestratorError(
            f"unsupported protocol version {version}; only version {V6} is accepted"
        )


def load_trusted_run(run_root: Path) -> tuple[dict[str, Any], dict[str, Any], Any, dict[str, Any]]:
    """Load a trusted v6 run: run record, setup record, graph state, adapter binding."""
    run_root = Path(run_root)
    run_path = run_root / "run.json"
    setup_path = run_root / "setup.json"
    graph_path = run_root / "graph" / "graph.json"

    run = load_json(run_path)
    setup = load_json(setup_path)

    reject_v5_or_earlier(run)

    graph = None
    if graph_path.exists():
        from graph_v6 import GraphState
        graph = GraphState.load(graph_path)

    adapter = setup.get("adapter_binding", {})

    return run, setup, graph, adapter


def receipt_auth_tag(binding: dict[str, Any], receipt: dict[str, Any]) -> str:
    """Compute authentication tag for a receipt using the adapter binding."""
    adapter_secret = binding.get("adapter_secret", "")
    tag_seed = canonical_bytes({"adapter_secret": adapter_secret, "receipt": receipt})
    return content_hash(tag_seed)


_EXPANSION_ROLE_SCOPES: dict[str, dict[str, Any]] = {
    "work_planner_architect": {
        "allowed_expansion_kinds": ["direct_repair", "implementation_set", "openspec_batch"],
        "allowed_child_roles": [
            "repair_worker", "implementation_worker", "implementation", "verifier",
            "integration_verifier", "proposal_explore", "proposal_architect",
            "proposal_finalizer", "implementation_review_architect",
            "openspec_finalizer", "commit_worker", "push_worker",
            "remote_verifier", "goal_judge",
        ],
        "side_effects": ["none", "repository", "external_idempotent"],
    },
    "goal_judge": {
        "allowed_expansion_kinds": ["continuation_analysis"],
        "allowed_child_roles": [
            "hypothesis_investigator", "synthesis_architect", "work_planner_architect",
        ],
        "side_effects": ["none"],
    },
    "proposal_finalizer": {
        "allowed_expansion_kinds": ["openspec_implementation"],
        "allowed_child_roles": ["implementation_worker", "verifier"],
        "side_effects": ["none", "repository"],
    },
    "implementation_review_architect": {
        "allowed_expansion_kinds": ["repair", "finalization"],
        "allowed_child_roles": [
            "repair_worker", "verifier", "openspec_finalizer", "commit_worker",
            "push_worker", "remote_verifier", "goal_judge",
        ],
        "side_effects": ["none", "repository", "external_idempotent"],
    },
}


def _authority_scope_for_role(role: str, graph) -> dict[str, Any]:
    template = _EXPANSION_ROLE_SCOPES.get(role)
    max_jobs = graph.limits.get("max_jobs_per_expansion")
    if max_jobs is None:
        max_jobs = graph.limits.get("max_jobs_per_cycle", 16)
    if template is None:
        return {
            "allowed_expansion_kinds": [],
            "allowed_child_roles": [],
            "owned_batch_ids": [],
            "side_effects": ["none"],
            "max_child_jobs": 0,
            "max_child_depth": 0,
            "limits": {},
        }
    return {
        "allowed_expansion_kinds": list(template["allowed_expansion_kinds"]),
        "allowed_child_roles": list(template["allowed_child_roles"]),
        "owned_batch_ids": [],
        "side_effects": list(template["side_effects"]),
        "max_child_jobs": max_jobs,
        "max_child_depth": 1,
        "limits": dict(graph.limits),
    }
