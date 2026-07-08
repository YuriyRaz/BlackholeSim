Take each proposal and implement each by the schema:
1) run Proposal job
2) run Implementation job
3) run Architect job to make a review of implemented stuff and make any corrections (using sub jobs)
ROLES:
1. Proposal:
the flow:
1) run command openspec explore;
2) if there are some issues ask Architect;
3) run command openspec proposal.

2. Implementation:
the flow:
1) for each task group use new job and run command openspec-apply-change,
2) in new job
2.1) run command /openspec-verify-change
2.2) and fix all findings even minor
2.3) for major issue ask Architect
3) /openspec-sync-specs
4) /openspec-archive-change
5) commit into main and push

3. Architect: use the OpenSpec explore command to investigate any issues / make architecture review / find the solutions for open questions. Always check the documentation. But documentation might be updated/corrected if needed.