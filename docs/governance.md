# Governance

How the workflow keeps people in control, limits what automation can touch, and avoids overstating impact.

## Current demo deployment (2026-10-06)

**Superseded for visibility and output validation by the October 10 update below.** The historical approval/deployment limitations still apply unless explicitly verified.

The submission repository is private. GitHub rejected branch protection with HTTP 403 because the current account plan does not support it for private repositories. The owner chose to continue with sample-only demo validation, not to make the repository public.

The approval gates below describe the intended deployment, not enforced controls in this demo. CODEOWNERS is present, but it does not enforce approval without branch protection. Azure credentials and deployment variables are not configured; no Azure deployment or automatic merge is authorized. Environment approval has not been configured or demonstrated.

The owner registered the Copilot secret on October 6. The first run passed secret validation and deterministic preparation but failed on an unavailable model; the framework opened a failure Issue, not an impact finding. The retry with owner-selected `gpt-5.4` created six finding Issues, one grouping Issue and draft PR #9. Despite a successful Actions conclusion, report upload failed non-fatally because its staging artifact was missing. Generated Issue formatting and source links require correction, and the draft PR has no automatically triggered CI checks. Output validation is therefore incomplete. The service-change schedule remains off, and `.github/workflows/aw.json` disables generated maintenance. Do not claim end-to-end approval enforcement until the repository plan and review gates have been configured and tested.

## Public reviewed demo (2026-10-10)

The owner explicitly authorized making the existing repository public. Tracked history contains public Azure notices and synthetic data, not environment exports or credential values. `data/inventory/*.json` is ignored and public preparation/publication rejects non-sample inventory, Message Center and tenant-profile inputs. GitHub Pages publishes only the committed reviewed sample snapshot, not raw data, agent logs or unreviewed live reports.

All 12 selected candidates were reviewed against public source conditions and the synthetic configuration. The six original finding Issues were reviewed; SMS primary sign-in was corrected from Impacted to Needs investigation, and the disk/ADE scope and malformed PowerShell finding were corrected. The report retains missing facts and coverage gaps rather than inventing safe defaults. Three Not impacted verdicts are explicitly limited to the captured VM series, Windows app or sample-resource inventory.

Draft PR 9 has passing PR-linked CI and offline Bicep validation after an owner-origin empty commit. Its deployment job was skipped. Manual CI alone does not configure automatic CI for future bot-created pull requests; the scoped trigger-token option remains documented in setup.

Report publication is deterministic and validates exact candidate coverage. The trusted publisher is copied before the agent runs, so post-steps do not execute agent-modified source. With gh-aw v0.81.6, its built-in staging upload precedes post-steps; the validated staging upload replaces that artifact afterward. `verify-report` fails if Markdown, HTML or candidate metadata was not delivered or does not match validation. An Actions green status without this check is insufficient.

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

## Permissions and boundaries

| Component | Access |
|---|---|
| Deterministic steps (`scripts/`) | Read the public Azure Updates API; list this repository's Issues with the run token; read files in the repository |
| Agent job | `contents: read`, `issues: read`, `pull-requests: read`; network limited by the firewall to default infrastructure, `www.microsoft.com`, `azure.microsoft.com` and `learn.microsoft.com` |
| MCP server | Microsoft Release Communications, limited to `get_azure_update_by_id` and `get_recent_azure_updates` |
| Shell | `cat`, `head`, `tail`, `grep`, `jq`, `ls`, `wc` plus compiler defaults; git commands only for preparing a pull request patch |
| Safe outputs (separate job) | At most 6 Issues (titles de-duplicated across runs), 1 draft pull request (protected files enforced), 1 artifact under `run/` |
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

- Runs with nothing new write a no-op before the engine starts, so no AI credits are used, and the no-op is recorded on the no-op runs Issue.
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
