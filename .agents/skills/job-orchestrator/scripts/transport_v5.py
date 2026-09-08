"""Transport receipt contracts for the authenticated v5 orchestrator."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Any


class TransportVerificationError(ValueError):
    """A receipt cannot be authenticated by the configured adapter."""


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _signature(value: dict[str, Any], secret: bytes) -> str:
    unsigned = {key: item for key, item in value.items() if key != "signature"}
    proof = unsigned.get("proof")
    if isinstance(proof, dict) and "signature" in proof:
        unsigned["proof"] = {key: item for key, item in proof.items() if key != "signature"}
    return hmac.new(secret, _canonical(unsigned), hashlib.sha256).hexdigest()


class TransportAdapter:
    """Minimal adapter boundary used by jobctl and fake transports."""

    name = "unknown"

    def capability_profile(self) -> dict[str, Any]:
        return {
            "transport": self.name,
            "launch_receipts": False,
            "response_receipts": False,
            "session_status": False,
            "transcript_access": False,
        }

    def verify_launch_receipt(self, receipt: dict[str, Any]) -> None:
        raise TransportVerificationError("transport cannot verify launch receipts")

    def verify_response_receipt(self, receipt: dict[str, Any]) -> None:
        raise TransportVerificationError("transport cannot verify response receipts")


@dataclass(frozen=True)
class HmacTransportAdapter(TransportAdapter):
    """Adapter helper for transports that expose an adapter-owned secret."""

    secret: bytes
    name: str = "task"

    def capability_profile(self) -> dict[str, Any]:
        return {
            "transport": self.name,
            "launch_receipts": True,
            "response_receipts": True,
            "session_status": True,
            "transcript_access": True,
        }

    def _verify(self, receipt: dict[str, Any], kind: str) -> None:
        proof = receipt.get("proof")
        if not isinstance(proof, dict) or proof.get("kind") != f"hmac-{kind}":
            raise TransportVerificationError("receipt lacks an adapter-authenticated proof")
        signature = proof.get("signature")
        if not isinstance(signature, str) or not hmac.compare_digest(
            signature, _signature(receipt, self.secret)
        ):
            raise TransportVerificationError("adapter receipt proof is invalid")

    def verify_launch_receipt(self, receipt: dict[str, Any]) -> None:
        self._verify(receipt, "launch")

    def verify_response_receipt(self, receipt: dict[str, Any]) -> None:
        self._verify(receipt, "response")

    def sign_launch(self, **fields: Any) -> dict[str, Any]:
        receipt = dict(fields)
        receipt["proof"] = {"kind": "hmac-launch"}
        receipt["proof"]["signature"] = _signature(receipt, self.secret)
        return receipt

    def sign_response(self, **fields: Any) -> dict[str, Any]:
        receipt = dict(fields)
        receipt["proof"] = {"kind": "hmac-response"}
        receipt["proof"]["signature"] = _signature(receipt, self.secret)
        return receipt


class FakeTransportAdapter(HmacTransportAdapter):
    """Deterministic adapter for tests and local protocol simulations."""

    name = "fake"

    def __init__(self, secret: bytes = b"fake-job-orchestrator-adapter") -> None:
        super().__init__(secret=secret, name="fake")

    def launch_receipt(
        self,
        *,
        dispatch_id: str,
        native_session_ref: str,
        run_id: str,
        job_id: str,
        prompt_sha256: str,
        created_at: str,
    ) -> dict[str, Any]:
        return self.sign_launch(
            schema_version=5,
            transport=self.name,
            dispatch_id=dispatch_id,
            native_session_ref=native_session_ref,
            run_id=run_id,
            job_id=job_id,
            prompt_sha256=prompt_sha256,
            created_at=created_at,
        )

    def response_receipt(
        self,
        *,
        attempt_id: str,
        native_session_ref: str,
        run_id: str,
        job_id: str,
        response_id: str,
        raw_response: str,
        received_at: str,
        status: str = "returned",
        session_liveness: str = "live",
    ) -> dict[str, Any]:
        response_sha256 = hashlib.sha256(raw_response.encode("utf-8")).hexdigest()
        return self.sign_response(
            schema_version=5,
            transport=self.name,
            attempt_id=attempt_id,
            native_session_ref=native_session_ref,
            run_id=run_id,
            job_id=job_id,
            response_id=response_id,
            response_sha256=response_sha256,
            raw_response=raw_response,
            received_at=received_at,
            status=status,
            session_liveness=session_liveness,
        )


def configured_adapter() -> TransportAdapter:
    """Load the configured receipt verifier without granting it root semantics."""
    secret = os.environ.get("JOB_ORCHESTRATOR_TRANSPORT_SECRET")
    if not secret:
        return TransportAdapter()
    return HmacTransportAdapter(secret.encode("utf-8"))
