# Service-change impact workflow

Turn Microsoft service-change notices into evidence-based, human-approved actions in GitHub.

> **Status (2026-10-06): prototype, preparing its first GitHub run.** The private submission repository is [amex678/service-change-impact-workflow](https://github.com/amex678/service-change-impact-workflow). All 33 unit tests and workflow compilation passed again locally on October 6. The agentic workflow has not yet run on GitHub Actions, so the verdicts in the demo below are the expected outcome, not a recorded result.

## Why

Azure Updates published 1,822 notices between October 2024 and September 2026, and 195 announced retirements fall in 2026 or later (measured on 2026-10-01 from the public Release Communications API). Microsoft 365 Message Center adds tenant-specific notices. Reading a notice does not tell an operations team whether **their** environment is affected, what the evidence is, or who must act by when. This workflow does that triage continuously and hands every decision to a person.

## How it works

```mermaid
flowchart LR
  AU["Azure Updates<br/>(public API)"] --> PM
  MC["Microsoft 365 Message Center<br/>(sanitized export or sample)"] --> PM
  INV["Inventory<br/>(sanitized, pseudonymized)"] --> PM
  PM["Deterministic pre-match<br/>fetch · map products · rank · skip tracked"] -->|candidates.json| AG
  PM -->|nothing new| NOOP["No-op run record<br/>(AI run skipped)"]
  AG["Copilot agent (read-only)<br/>firewall · MRC MCP · Microsoft Learn"] --> TD["Threat detection"]
  TD --> ISS["Issues<br/>Impacted / Needs investigation"]
  TD --> PR["Draft pull request<br/>infra/ change (Azure only)"]
  TD --> REP["Run report artifact"]
  PR --> REV{"Human review<br/>CODEOWNERS + branch protection"}
  REV --> CI["CI: tests · Bicep build · what-if"]
  CI --> ENV{"Environment approval"}
  ENV --> DEP["Deploy to verification<br/>resource group"]
```

1. **Deterministic steps** (`scripts/`) fetch Azure Updates, including still-relevant retirements, map inventory resource types to Azure Updates product names, rank candidates, and skip notices already tracked by an Issue. When nothing needs evaluation they record a no-op and the AI run is skipped.
2. **The agent** ([`.github/workflows/service-change-impact.md`](.github/workflows/service-change-impact.md)) reads only the prepared candidates, checks each notice's conditions against the configuration, and gives one of four verdicts: *Impacted*, *Not impacted*, *Needs investigation* or *Cannot evaluate*.
3. **Safe outputs** turn verdicts into Issues and, for Azure changes that are declared in `infra/`, at most one **draft** pull request. Microsoft 365 notices stop at an Issue; the workflow never changes tenant settings.
4. **People decide.** An Azure change reaches the verification environment only after pull request approval and a second environment approval ([`infra-deploy.yml`](.github/workflows/infra-deploy.yml)).

## Demo golden path (about 3 minutes)

| Step | What the audience sees |
|---|---|
| 1. Run `service-change-impact` manually | Step summary: live Azure notices plus 4 sample Microsoft 365 notices reduced to a short ranked candidate list (on 2026-10-01: 206 Azure notices → 12 candidates), with coverage gaps and warnings |
| 2. Verdicts (expected) | Azure 572770 (PowerShell 7.4 support ends 2026-11-10): *Impacted*, because `sites-01` runs PowerShell 7.4. Azure 500157 (OS disks on Standard HDD retire 2028-09-08): *Impacted* for `disks-01` only. TLS 1.0/1.1 retirement: *Not impacted*, because the app enforces TLS 1.2. Sample SMS sign-in notice: *Impacted*, Issue only |
| 3. Draft pull request (expected) | `infra/main.bicep`: `powerShellVersion` 7.4 → 7.6, with risks, validation and rollback |
| 4. Human gates | Review with CODEOWNERS, CI, then environment approval before the verification deployment |

The inventory and Microsoft 365 data in this repository are synthetic samples (`"sample": true`), and every output says so.

## Roles

| Role | Responsibility |
|---|---|
| Operations reviewer | Triages the Issues, confirms or corrects verdicts, sets owners and dates |
| IaC owner (CODEOWNERS) | Reviews and approves draft pull requests under `infra/` |
| Microsoft 365 administrator | Acts on Microsoft 365 Issues; no automated tenant change exists |
| Environment approver | Approves each deployment to the verification (later, production) environment |
| Workflow maintainer | Edits the workflow Markdown, recompiles it, maintains the product map, secrets and schedule |

## Prerequisites

- A GitHub repository with Actions enabled, and the [GitHub Agentic Workflows](https://github.github.com/gh-aw/) CLI extension to compile workflows (`gh extension install github/gh-aw`; compiled with v0.81.6).
- Copilot engine authentication: the `COPILOT_GITHUB_TOKEN` secret (fine-grained PAT with **Copilot Requests: Read**) for personal repositories, or `permissions: copilot-requests: write` where the organization has centralized Copilot billing.
- Python 3.10 or later for local runs (standard library only).
- Optional: an Azure subscription and a Microsoft Entra app with a federated credential for `infra-deploy.yml`, and read access for exporting your own inventory.

Step-by-step instructions: [docs/setup.md](docs/setup.md).

## Governance and human-in-the-loop

- **Least privilege.** The agent job can only read `contents`, `issues` and `pull-requests`. Writes happen in a separate job through safe outputs with limits: at most 6 Issues and 1 draft pull request per run, titles de-duplicated across runs, protected files enforced.
- **Threat detection** reviews the agent's output for prompt injection, secret leaks and malicious patches before anything is written.
- **Network and tools allowlists.** The firewall allows only default infrastructure plus `www.microsoft.com`, `azure.microsoft.com` and `learn.microsoft.com`. The MCP server exposes two read-only tools.
- **Data boundary.** The inventory is sanitized: no subscription, tenant or resource IDs, no tags, and pseudonymous names. Raw exports stay in the git-ignored `data/raw/`. Microsoft 365 quotes are limited to one sentence.
- **Truthfulness.** An incomplete fetch never produces a no-op. Deferred or unmapped items are reported as *not evaluated*, never as *not impacted*.
- **Two human gates for Azure changes.** Pull request approval, then environment approval. Microsoft 365 changes stay manual.
- **Audit trail.** Issues and pull requests carry a workflow marker. Each run leaves a report artifact (30 days), a step summary, and a comment on the no-op runs Issue when nothing was found.

Details and the threat model: [docs/governance.md](docs/governance.md).

## Success measures

| Measure | Target | How it is measured |
|---|---|---|
| Notices a person must read per run | 12 or fewer candidates instead of every new notice plus all open retirements | `counts` in `run/candidates.json` |
| Time from notice to triaged Issue | Less than 1 day once the daily schedule is on | Issue `created_at` minus notice `created` |
| Evidence completeness | Every *Impacted* Issue cites the notice condition and the matching value | Reviewer checklist |
| False "no impact" | None: incomplete inputs are never reported as *not impacted* | Unit tests and the report's warnings |
| Controlled change | Every `infra/` change goes through an approved pull request and environment approval | Branch protection and deployment history |

The manual baseline (time and steps to triage the same notices by hand) is still to be measured for the submission.

## Repository layout

```text
.github/workflows/service-change-impact.md        Agentic workflow (source, edit this)
.github/workflows/service-change-impact.lock.yml  Compiled GitHub Actions workflow (generated)
.github/workflows/ci.yml                          Unit tests, Bicep build, actionlint
.github/workflows/infra-deploy.yml                Human-approved deployment of infra/
.github/copilot-instructions.md                   Guidance for GitHub Copilot in this repository
scripts/                                          Deterministic fetch, sanitize and pre-match steps
config/                                           Product map, evidence hints, property whitelist
data/samples/                                     Synthetic inventory and Microsoft 365 data
templates/impact-report.md                        Report format used by the agent
infra/main.bicep                                  Demo environment the draft pull request edits
tests/                                            Unit tests (python -m unittest)
docs/                                             Setup and governance
```

## Starting assets and original contributions

- **Generated by GitHub Agentic Workflows (MIT)** with `gh aw init` and `gh aw compile`: `.github/agents/agentic-workflows.md`, `.github/skills/agentic-workflow*/`, `.github/workflows/copilot-setup-steps.yml`, `.github/mcp.json`, `.github/aw/actions-lock.json`, `.gitattributes`, and every `*.lock.yml`.
- **Data**: Azure Updates from Microsoft's public Release Communications API (read at run time; `config/azure-updates-products.json` is a snapshot of its product names).
- **Original work in this repository**: the workflow instructions and configuration, all scripts and tests, configuration maps, synthetic samples, the report template, the demo Bicep, the CI and deployment workflows, and the documentation. The four-verdict rubric comes from the author's earlier manual impact assessments.

## Status and limitations

Verified locally on 2026-10-01:

- Live fetch from the public API. Paging is explicit because the API omits `@odata.nextLink` when `$top` is set, and results are de-duplicated. With a stable sort, 57 recent and 195 retirement notices were retrieved completely.
- The pre-match against the samples ranks the demo notices first.
- 33 unit tests pass.
- `gh aw compile` (v0.81.6) reports 0 errors and 0 warnings.
- `az bicep build` succeeds.

Not yet verified:

- A run on GitHub Actions, including Copilot engine authentication and the MRC MCP server behind the gateway.
- The no-op skip before the AI run.
- The quality of the agent's Issues and pull request.
- `infra-deploy.yml` against Azure.
- actionlint, which runs in CI because Docker was unavailable locally.

Known limitations:

- **Microsoft 365 uses samples.** An unattended export needs Microsoft Graph `ServiceMessage.Read.All` (application permission) with admin consent ([reference](https://learn.microsoft.com/graph/api/serviceannouncement-list-messages?view=graph-rest-1.0)).
- **Verdicts depend on captured configuration.** The agent can only judge what the inventory records; missing facts lead to *Needs investigation*.
- **Coverage is limited to mapped types.** The product map covers common resource types; unmapped types are listed in every report.
