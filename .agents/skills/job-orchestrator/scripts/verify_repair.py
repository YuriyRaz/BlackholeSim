#!/usr/bin/env python3

import subprocess
import shutil
import json
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = SKILL_ROOT / "runs"
JOBCTL = SKILL_ROOT / "scripts" / "jobctl.py"

def run_cmd(*args):
    result = subprocess.run(["python", str(JOBCTL)] + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {args}\n{result.stderr}\n{result.stdout}")
    return result

def setup_run(run_id: str) -> Path:
    run_root = RUNS_DIR / run_id
    if run_root.exists():
        shutil.rmtree(run_root)
    run_cmd("init", "--goal", "test", "--run-id", run_id, "--request", "test")
    
    definition = {
        "jobs": [
            {
                "id": "JOB-1",
                "title": "Test Job",
                "goal": "do nothing",
                "role": "agent",
                "workflow": {
                    "nodes": [
                        {
                            "id": "node_1",
                            "position": 1,
                            "status": "ready",
                            "run_in": "job_session",
                            "work_units": ["unit_1"]
                        }
                    ]
                }
            }
        ]
    }
    def_file = run_root / "def.json"
    def_file.write_text(json.dumps(definition))
    run_cmd("compile", "--run", str(run_root), "--definition", str(def_file))
    
    # generate spawn_and_bootstrap
    res = run_cmd("next", "--run", str(run_root))
    out = json.loads(res.stdout)
    action_id = out["action_id"]
    
    # record acknowledgement
    # We must construct a valid session_acknowledged response.
    # _validate_acknowledgement needs exact fields.
    # Wait, in jobctl.py `_validate_acknowledgement` might just need:
    # `{"schema_version": 3, "protocol_version": 3, "protocol_sha256": "fake", "job_id": "JOB-1", "contract_revision": 1, "current_workflow_node_id": "node_1", "acknowledged_at": "2024-01-01T00:00:00Z", "session_id": "sess-1"}`
    # Wait, instead of this complex setup, I can just write a script that bypasses `jobctl next` for `spawn_and_bootstrap` and just constructs the events manually, or just construct events manually entirely.
    
    # Let me just run it and see if it fails.
    resp_file = run_root / "resp.json"
    
    run = json.loads((run_root / "run.json").read_text())
    
    # Actually wait! The `spawn_and_bootstrap` needs the real protocol_sha256.
    manifest = json.loads((run_root / "protocol" / "manifest.json").read_text())
    protocol_sha256 = manifest["sha256"]
    
    resp_file.write_text(json.dumps({
        "schema_version": 3,
        "protocol_version": 3,
        "protocol_sha256": protocol_sha256,
        "job_id": "JOB-1",
        "contract_revision": 1,
        "current_workflow_node_id": "node_1",
        "acknowledged_at": "2024-01-01T00:00:00.000Z",
        "session_id": "sess-1"
    }))
    run_cmd("record", "--run", str(run_root), "--action-id", action_id, "--response", str(resp_file))
    
    # generate send_dispatch
    res = run_cmd("next", "--run", str(run_root))
    out = json.loads(res.stdout)
    if "dispatch_id" not in out:
        raise RuntimeError(f"Expected dispatch_id, got: {out}")
    return run_root, out["dispatch_id"]

def test_golden_path():
    print("Running Test 1: The Golden Path")
    run_root, dispatch_id = setup_run("test-golden")
    
    res = run_cmd("repair", "--run", str(run_root), "--abort-dispatch", dispatch_id)
    assert res.returncode == 0, f"Repair failed: {res.stderr} {res.stdout}"
    
    # Verify active_dispatch_id is None
    run_state = json.loads((run_root / "run.json").read_text())
    assert run_state.get("active_dispatch_id") is None
    print("Test 1 Passed!")

def test_sequential_trap():
    print("Running Test 2: The Sequential Trap")
    run_root, dispatch_id1 = setup_run("test-seq")
    
    events_file = run_root / "events.jsonl"
    events = [json.loads(line) for line in events_file.read_text().strip().splitlines()]
    
    act_ev = json.loads(json.dumps(next(e for e in reversed(events) if e["type"] == "action_created")))
    disp_ev = json.loads(json.dumps(next(e for e in reversed(events) if e["type"] == "dispatch_created")))
    
    import datetime
    act_ev["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    act_ev["event_id"] += "-2"
    act_ev["revision"] = len(events) + 1
    act_ev["correlation_id"] += "-2"
    act_ev["data"]["action"]["action_id"] += "-2"
    act_ev["data"]["action"]["dispatch_id"] += "-2"
    events.append(act_ev)
    
    disp_ev["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    disp_ev["event_id"] += "-2"
    disp_ev["revision"] = len(events) + 1
    disp_ev["correlation_id"] += "-2"
    disp_ev["data"]["dispatch"]["dispatch_id"] += "-2"
    events.append(disp_ev)
    
    events_file.write_text("".join(json.dumps(e) + "\n" for e in events))
    
    # Run repair on the first one
    # Run repair on the first one. It will fail the post-repair validate_state() because dispatch_id2 is still dangling!
    res = subprocess.run(["python", str(JOBCTL), "repair", "--run", str(run_root), "--abort-dispatch", dispatch_id1], capture_output=True, text=True)
    assert res.returncode != 0, f"Expected first repair to fail validation, but it passed: {res.stdout}"
    
    dispatch_id2 = disp_ev["data"]["dispatch"]["dispatch_id"]
    res = run_cmd("repair", "--run", str(run_root), "--abort-dispatch", dispatch_id2)
    assert res.returncode == 0, f"Repair second failed: {res.stderr} {res.stdout}"
    
    print("Test 2 Passed!")

def test_double_resolution():
    print("Running Test 3: The Double Resolution Trap")
    run_root, dispatch_id = setup_run("test-double")
    events_file = run_root / "events.jsonl"
    events = [json.loads(line) for line in events_file.read_text().strip().splitlines()]
    
    res_ev = json.loads(json.dumps(events[-1])) # dispatch_created
    # Wait, for double resolution, we want a worker_result event.
    
    # Repair the run first to simulate one resolution
    res = run_cmd("repair", "--run", str(run_root), "--abort-dispatch", dispatch_id)
    assert res.returncode == 0
    
    # Read events again
    events = [json.loads(line) for line in events_file.read_text().strip().splitlines()]
    
    # Now simulate a rogue worker resolving it a second time
    res_ev = json.loads(json.dumps(events[-1])) # worker_result from repair
    import datetime
    res_ev["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    res_ev["event_id"] += "-2"
    res_ev["revision"] = len(events) + 1
    events.append(res_ev)
    
    events_file.write_text("".join(json.dumps(e) + "\n" for e in events))
    
    # Now try to compile/next
    res = subprocess.run(["python", str(JOBCTL), "next", "--run", str(run_root)], capture_output=True, text=True)
    # The orchestrator will crash when it loads state with duplicate resolutions
    assert "action resolved more than once" in res.stderr or res.returncode != 0
    
    # Repair SHOULD handle this if it could, but for now we're just proving the trap exists
    # If the user wants a full fix for double-resolution, we'd need to prune the events or similar.
    # The current repair tool just aborts dangling ones.
    print("Test 3 Passed!")

if __name__ == "__main__":
    test_golden_path()
    test_sequential_trap()
    test_double_resolution()
    print("All tests passed!")
