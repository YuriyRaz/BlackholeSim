import { execSync } from 'child_process';
import { copyFileSync, mkdirSync, existsSync } from 'fs';
import { dirname } from 'path';

const pyExe = 'C:\\Projects\\AkitoBlogBot\\.venv\\Scripts\\python.exe';

// Record session
execSync(
  `"${pyExe}" ".agents/skills/job-orchestrator/scripts/jobctl.py" session --run ".job-orchestrator/runs/RUN-8b4feb8194fcab2d553e" --job J005 --session-ref ses_iteration1_architect_review`,
  { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
);

// Copy report to run root
const dest = '.job-orchestrator/runs/RUN-8b4feb8194fcab2d553e/jobs/J005/report.md';
mkdirSync(dirname(dest), { recursive: true });
copyFileSync('jobs/J005/report.md', dest);

// Submit outcome
const result = execSync(
  `"${pyExe}" ".agents/skills/job-orchestrator/scripts/jobctl.py" outcome --run ".job-orchestrator/runs/RUN-8b4feb8194fcab2d553e" --job J005 --session ses_iteration1_architect_review --outcome "jobs/J005/outcome.json"`,
  { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
);
console.log(result);
