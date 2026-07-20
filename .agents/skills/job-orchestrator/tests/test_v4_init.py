from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import load_v4_state  # noqa: E402


JOBCTL = ROOT / "scripts" / "jobctl.py"


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class Version4InitTest(unittest.TestCase):
    def run_jobctl(self, *arguments: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(JOBCTL), *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_init_creates_exact_empty_v4_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            state_root = base / "state"
            workspace = base / "workspace"
            workspace.mkdir()
            request = base / "request.md"
            request_bytes = b"Implement only initialization.\nPreserve this request exactly.\n"
            request.write_bytes(request_bytes)

            process = self.run_jobctl(
                "init",
                "--request-file", request,
                "--goal", "Create a version-4 run",
                "--run-id", "RUN-INIT",
                "--state-root", state_root,
                "--workspace", workspace,
            )

            self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
            response = json.loads(process.stdout)
            run_root = state_root / "RUN-INIT"
            self.assertEqual(response, {
                "run_root": str(run_root),
                "run_id": "RUN-INIT",
            })
            self.assertEqual(set(tree_bytes(run_root)), {
                "jobs/index.json",
                "request.md",
                "run.json",
                "setup.json",
            })
            self.assertEqual((run_root / "request.md").read_bytes(), request_bytes)
            self.assertEqual(
                json.loads((run_root / "jobs" / "index.json").read_text(encoding="utf-8")),
                {"jobs": []},
            )
            run = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["schema_version"], 4)
            self.assertEqual(run["protocol_version"], 4)
            self.assertEqual(run["status"], "active")
            self.assertEqual(run["job_ids"], [])
            self.assertEqual(run["revision"], 1)
            state = load_v4_state(run_root)
            self.assertEqual(state["jobs"], {})
            self.assertEqual(state["ready_job_ids"], [])
            self.assertEqual(
                json.loads((run_root / "setup.json").read_text(encoding="utf-8")),
                {
                    "schema_version": 4,
                    "request_path": "request.md",
                    "workspace": str(workspace.resolve()),
                    "execution_mode": "sequential",
                    "jobs": [],
                },
            )
            self.assertFalse((run_root / "protocol").exists())
            self.assertFalse((run_root / "events.jsonl").exists())
            self.assertFalse((run_root / "orchestrator.lock").exists())

    def test_init_refuses_existing_run_root_without_modifying_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            run_root = base / "RUN-EXISTING"
            run_root.mkdir()
            (run_root / "run.json").write_bytes(
                b'{"schema_version":4,"protocol_version":4}\n'
            )
            before = tree_bytes(run_root)
            request = base / "request.md"
            request.write_text("new request\n", encoding="utf-8")

            process = self.run_jobctl(
                "init",
                "--request-file", request,
                "--goal", "Do not replace existing state",
                "--run-id", "RUN-EXISTING",
                "--state-root", base,
                "--workspace", base,
            )

            self.assertEqual(process.returncode, 2)
            self.assertIn("run already exists", json.loads(process.stdout)["error"])
            self.assertEqual(tree_bytes(run_root), before)


if __name__ == "__main__":
    unittest.main()
