# Governance

How the workflow keeps people in control, limits what automation can touch, and avoids overstating impact.

## Current demo deployment (2026-10-06)

**Superseded for visibility and output validation by the October 10 update below.** The historical approval/deployment limitations still apply unless explicitly verified.

The submission repository is private. GitHub rejected branch protection with HTTP 403 because the current account plan does not support it for private repositories. The owner chose to continue with sample-only demo validation, not to make the repository public.

The approval gates below describe the intended deployment, not enforced controls in this demo. CODEOWNERS is present, but it does not enforce approval without branch protection. Azure credentials and deployment variables are not configured; no Azure deployment or automatic merge is authorized. Environment approval has not been configured or demonstrated.

The owner registered the Copilot secret on October 6. The first run passed secret validation and deterministic preparation but failed on an unavailable model; the framework opened a failure Issue, not an impact finding. The retry with owner-selected `gpt-5.4` created six finding Issues, one grouping Issue and draft PR #9. Despite a successful Actions conclusion, report upload failed non-fatally because its staging artifact was missing. Generated Issue formatting and source links require correction, and the draft PR has no automatically triggered CI checks. Output validation is therefore incomplete. The service-change schedule remains off, and `.github/workflows/aw.json` disables generated maintenance. Do not claim end-to-end approval enforcement until the repository plan and review gates have been configured and tested.

## Public reviewed demo (2026-10-10)

The owner explicitly authorized making the existing repository public. Tracked history contains public Azure notices and synthetic data, not environment exports or credential values. `data/inventory/*.json` is ignored and public preparation/publication rejects non-sample inventory, Message Center and tenant-profile inputs. GitHub Pages publishes only the committed reviewed sample snapshot, not raw data, agent logs or unreviewed live reports.

All 12 selected candidates were reviewed against public source conditions and the synthetic configuration. The six original findings and four new investigation Issues were reviewed; SMS primary sign-in was corrected from Impacted to Needs investigation, and disk/ADE scope and the malformed PowerShell finding were corrected. The final report has 2 Impacted, 2 scope-limited Not impacted and 8 Needs investigation. Its Not impacted verdicts are limited to the captured Windows app and sample SCOM-resource inventory; current VM series alone does not settle reservation orders.

Draft PR 9 has passing PR-linked CI and offline Bicep validation after an owner-origin empty commit. Its deployment job was skipped. Manual CI alone does not configure automatic CI for future bot-created pull requests; the scoped trigger-token option remains documented in setup.

Report publication is deterministic and validates exact candidate coverage. The publisher and evidence guards are copied before the agent runs, so post-steps do not execute agent-modified source. The follow-up directly uploads the validated report, including complete zero-candidate reports, rather than relying on a model-requested artifact upload. `verify-report` fails if required files are missing or inconsistent. An Actions green status without this check is insufficient.

[Live run 38012531004](https://github.com/amex678/service-change-impact-workflow/actions/runs/38012531004) passed all six jobs and delivered all three report files with 12/12 verdicts. Factual review still corrected a claim that the unclassified `disks-02` was a data disk. Passing delivery/shape checks does not mean all generated statements are correct or approved.

Approval enforcement is not demonstrated merely by changing visibility to public. Branch protection/environment approval has not been configured or tested in this task. No merge, Azure authentication, what-if, deployment or M365 setting change is authorized. Analysis schedules and generated maintenance remain off.

## Human decision points

| Decision | Who | Where |
|---|---|---|
| Is the verdict right? Who owns it, and by when? | Operations reviewer | The Issue created per notice |
| Should this `infra/` change be made? | IaC owner (CODEOWNERS) | Draft pull request review; branch protection requires approval |
| May it be deployed now? | Environment approver | `azure-verification` environment approval in `infra-deploy.yml` |
| Should a Microsoft 365 setting change? | Microsoft 365 administrator | Manual action outside this workflow |
| Should the workflow's scope or schedule change? | Workflow maintainer | Pull request to the workflow Markdown and the compiled lock file |

The agent proposes. It never merges, deploys, or changes Azure or Microsoft 365.

Reassessment state fingerprints notice/configuration/policy and expires after
30 days without evaluation. Missing state or changing evidence triggers review;
it is never inferred from an Issue's ID alone. Existing findings receive bounded
comments, not duplicate Issues or replacement of a human verdict. Known notice
revisions reject five historical unsupported verdicts, and resource labels are
derived from the captured inventory. These checks do not prove every sentence
or replace human approval. See [reproduction and limits](reproduce.md).

The first reference run 38016574401 created duplicate draft PR 14 despite
instructions to reuse PR 9. PR 14 was closed without merging. The follow-up
adds a native pre-handler safe-output gate: selected-candidate verdicts and
existing finding/PR context must support any creation request. The exact
historical duplicate request fails this guard. This is an enforced validation
step, not merely another prompt instruction.

Final reference run 38018026348 passed the native pre-handler guard and all
six jobs, delivered 12/12 verdicts, and created no additional remediation PR.
Final unchanged run 38019824433 passed all six jobs, delivered a visible
zero-candidate report, skipped the main analysis model, and preserved all 12
assessment timestamps. Final CI 38018024059 passed 104 tests on Python 3.10
and strict compiler/lock, Bicep and actionlint checks. Threat detection remains
separate and enabled, including on the no-op path.

## Permissions and boundaries

| Component | Access |
|---|---|
| Deterministic steps (`scripts/`) | Read the public Azure Updates API; list this repository's Issues with the run token; read files in the repository |
| Agent job | `contents: read`, `issues: read`, `pull-requests: read`; network limited by the firewall to default infrastructure, `www.microsoft.com`, `azure.microsoft.com` and `learn.microsoft.com` |
| MCP server | Microsoft Release Communications, limited to `get_azure_update_by_id` and `get_recent_azure_updates` |
| Shell | `cat`, `head`, `tail`, `grep`, `jq`, `ls`, `wc` plus compiler defaults; git commands only for preparing a pull request patch |
| Safe outputs (separate job) | At most 6 new Issues, 15 reassessment comments on labelled finding Issues, 1 draft pull request; no merge, closure or replacement of human review |
| Report publisher | Deterministic read/validate/render/upload of required report files, with captured-resource labels and revision state; no AI execution outside the firewall |
| `infra-deploy.yml` | OIDC to Azure (no stored credentials); deploys only after an approved merge and an environment approval |

Threat detection is on by default with safe outputs: the agent output is checked for prompt injection, secret leaks and malicious patches before the safe-output job applies it. URLs outside the allowed domains are redacted in outputs.

## Data boundary

- **Inventory**: `scripts/sanitize_azure_inventory.py` keeps type, kind, location, SKU and whitelisted properties only. Subscription, tenant and resource IDs, real names, resource group names and tags are removed. Names become stable pseudonyms such as `sites-01`. The mapping back to real names is written only on request, to the git-ignored `data/raw/`.
- **Notices**: Azure Updates are public. Microsoft 365 Message Center content is tenant information. Outputs quote at most one sentence and link to the source.
- **Samples**: synthetic files carry `"sample": true`; the pre-match warns and the agent must say so in every output.
- **Repository visibility**: keep the repository private while it contains a real sanitized inventory. Samples are safe to publish.

## Truthfulness rules

- Four verdicts only: *Impacted*, *Not impacted*, *Needs investigation*, *Cannot evaluate*. A product or type match alone is never *Impacted*.
- An incomplete or failed fetch never produces a no-op, and missing notices are never counted as *Not impacted*.
- Items deferred by rank or by the per-run limit, items already tracked, and unmapped resource types are listed as *not evaluated* with the reason.
- Evidence hints only order the candidates; the agent must confirm each condition from the notice and the configuration.
- Publication dates and effective dates are kept separate; only dates stated in a notice count as deadlines.

## Cost and reliability controls

- Complete runs with nothing requiring reassessment skip the main analysis agent's inference, publish a visible scope report and retain unchanged assessment timestamps. Separate threat detection remains enabled and can incur cost.
- Per-run limits: 10 Azure and 5 Microsoft 365 candidates; the agent job times out after 30 minutes.
- Scheduled runs stay off until reviewed manual runs succeed. GitHub may delay scheduled runs; the no-op runs Issue shows when the last successful check happened, so a missing check is visible rather than silently treated as all clear.
- CI runs unit tests, builds the Bicep file and lints every workflow, including the compiled agentic workflow.
- With gh-aw v0.81.6, the compiled safe-output job uses `concurrency.queue`. actionlint 1.7.12 does not recognize that key. `.github/actionlint.yaml` suppresses only that exact diagnostic in the compiled workflow; all other checks remain enabled. Remove the exception when actionlint supports the key.

## Threat model (summary)

| Threat | Mitigation |
|---|---|
| A notice or web page contains instructions aimed at the agent | Read-only agent job, firewall allowlist, threat detection, capped and typed safe outputs, human review of every output |
| The agent proposes a harmful infrastructure change | Draft pull request only, protected files, CODEOWNERS review, CI, what-if, environment approval, verification environment before production |
| Private environment data leaks into Issues | Sanitized pseudonymous inventory, no identifiers, quote limits, private repository for real data |
| Over-reporting or under-reporting impact | Four-verdict rubric, evidence required, incomplete inputs never "not impacted", coverage gaps listed |
| Silent failures | Warnings in the step summary and report, failed runs reported as Issues (gh-aw default), no-op runs Issue as a heartbeat |
