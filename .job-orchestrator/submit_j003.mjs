import { execSync } from 'child_process';
import { copyFileSync, mkdirSync } from 'fs';
import { dirname } from 'path';

const pyExe = 'C:\\Projects\\AkitoBlogBot\\.venv\\Scripts\\python.exe';
const runRoot = '.job-orchestrator/runs/RUN-tde-completion-20260723';

execSync(
  `"${pyExe}" ".agents/skills/job-orchestrator/scripts/jobctl.py" session --run "${runRoot}" --job J003 --session-ref ses_j003_independent_verify`,
  { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
);

const dest = `${runRoot}/jobs/J003/report.md`;
mkdirSync(dirname(dest), { recursive: true });
copyFileSync('jobs/J003/report.md', dest);

const result = execSync(
  `"${pyExe}" ".agents/skills/job-orchestrator/scripts/jobctl.py" outcome --run "${runRoot}" --job J003 --session ses_j003_independent_verify --outcome "jobs/J003/outcome.json"`,
  { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
);
console.log(result);
