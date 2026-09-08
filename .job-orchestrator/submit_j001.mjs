import { execSync } from 'child_process';
import { copyFileSync, mkdirSync } from 'fs';
import { dirname } from 'path';

const pyExe = 'C:\\Projects\\AkitoBlogBot\\.venv\\Scripts\\python.exe';
const runRoot = '.job-orchestrator/runs/RUN-tde-completion-20260723';

// Record session
execSync(
  `"${pyExe}" ".agents/skills/job-orchestrator/scripts/jobctl.py" session --run "${runRoot}" --job J001 --session-ref ses_j001_evidence_audit`,
  { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
);

// Copy report to run root
const dest = `${runRoot}/jobs/J001/report.md`;
mkdirSync(dirname(dest), { recursive: true });
copyFileSync('jobs/J001/report.md', dest);

// Submit outcome
const result = execSync(
  `"${pyExe}" ".agents/skills/job-orchestrator/scripts/jobctl.py" outcome --run "${runRoot}" --job J001 --session ses_j001_evidence_audit --outcome "jobs/J001/outcome.json"`,
  { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
);
console.log(result);
