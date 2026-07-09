from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JOBCTL = ROOT / "scripts" / "jobctl.py"
WORKERCTL = ROOT / "scripts" / "workerctl.py"
INIT_RUN = ROOT / "scripts" / "init_run.py"


class CliSurfaceTest(unittest.TestCase):
    def run_json(self, *arguments: object) -> dict:
        process = subprocess.run(
            [sys.executable, *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
        return json.loads(process.stdout)

    def test_generated_bootstrap_and_execution_commands_are_cli_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            initialized = self.run_json(
                JOBCTL, "init", "--request", "CLI probe", "--goal", "CLI probe",
                "--state-root", base, "--workspace", base,
            )
            run = Path(initialized["run_root"])
            definition = base / "definition.json"
            definition.write_text(json.dumps({"jobs": [{
                "id": "J001",
                "title": "Probe",
                "goal": "Probe the public command surface",
                "role": "Implementation",
                "workspace": str(base),
                "allowed_edit_roots": [str(base)],
                "capabilities": ["edit"],
                "workflow": {"nodes": [{
                    "id": "apply",
                    "position": 1,
                    "run_in": "job_session",
                    "work_units": ["U1"],
                    "acceptance_criteria": ["probe passes"],
                    "required_checks": ["CLI check"],
                    "prohibited_actions": ["later nodes"],
                    "checkpoint_policy": ["after_discovery"],
                    "side_effect_class": "workspace_write",
                    "recovery_check": "inspect workspace",
                }]},
            }]}), encoding="utf-8")
            self.run_json(
                JOBCTL, "compile", "--run", run, "--definition", definition,
            )
            bootstrap = self.run_json(JOBCTL, "next", "--run", run)
            contract_path = run / "jobs" / "J001" / "contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            acknowledgement = self.run_json(
                WORKERCTL,
                "acknowledge",
                "--contract", contract_path,
                "--protocol-version", contract["protocol"]["version"],
                "--protocol-sha256", contract["protocol"]["sha256"],
                "--job-id", contract["job_id"],
                "--contract-revision", contract["revision"],
                "--current-node", "apply",
            )
            acknowledgement["session_id"] = "transport-session-1"
            response = base / "acknowledgement.json"
            response.write_text(json.dumps(acknowledgement), encoding="utf-8")
            self.run_json(
                JOBCTL, "record", "--run", run,
                "--action-id", bootstrap["action_id"], "--response", response,
            )
            execution = self.run_json(JOBCTL, "next", "--run", run)
            dispatch_path = (
                run / "jobs" / "J001" / "dispatches"
                / f"{execution['dispatch_id']}.json"
            )
            dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
            inspected = self.run_json(
                WORKERCTL,
                "inspect",
                "--dispatch", dispatch_path,
                "--nonce", dispatch["nonce"],
                "--session-id", "transport-session-1",
                "--current-node", "apply",
            )
            self.assertTrue(inspected["valid"])
            self.assertIn(str(dispatch_path), execution["prompt"])
            self.assertIn(dispatch["nonce"], execution["prompt"])

    def test_compatibility_wrapper_is_invocable(self) -> None:
        process = subprocess.run(
            [sys.executable, str(INIT_RUN), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("--state-root", process.stdout)


if __name__ == "__main__":
    unittest.main()
