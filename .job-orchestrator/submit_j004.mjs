import { execSync } from 'child_process';
import { copyFileSync, mkdirSync } from 'fs';
import { dirname } from 'path';

const pyExe = 'C:\\Projects\\AkitoBlogBot\\.venv\\Scripts\\python.exe';
const runRoot = '.job-orchestrator/runs/RUN-tde-completion-20260723';

execSync(
  `"${pyExe}" ".agents/skills/job-orchestrator/scripts/jobctl.py" session --run "${runRoot}" --job J004 --session-ref ses_j004_final_repair`,
  { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
);

const dest = `${runRoot}/jobs/J004/report.md`;
mkdirSync(dirname(dest), { recursive: true });
copyFileSync('jobs/J004/report.md', dest);

const result = execSync(
  `"${pyExe}" ".agents/skills/job-orchestrator/scripts/jobctl.py" outcome --run "${runRoot}" --job J004 --session ses_j004_final_repair --outcome "jobs/J004/outcome.json"`,
  { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
);
console.log(result);
