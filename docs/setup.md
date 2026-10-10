# Setup

From this folder to a first reviewed run. Steps 1-5 are enough for the demo; steps 6-9 connect real data and Azure.

## 1. Create the repository

The submission repository is [amex678/service-change-impact-workflow](https://github.com/amex678/service-change-impact-workflow) (public, owner-authorized on 2026-10-10, synthetic data only). Clone it to use that repository; the creation commands below are for a separate copy.

Start private. Make it public only after checking that no private data was committed; making a repository private again cannot retract copies already downloaded.

```bash
cd service-change-impact-workflow
git init -b main
git add .
git commit -m "Import service-change impact workflow"
gh repo create <owner>/service-change-impact-workflow --private --source . --push
```

## 2. Authenticate the Copilot engine

The workflow explicitly uses `gpt-5.4`, selected by the owner after the first run rejected the implicit model with HTTP 400. If changing models, verify availability for the `agentic-workflows` integration, update `engine.model`, and recompile before running.

For a personal repository, create a fine-grained personal access token owned by your user account with **Account permissions → Copilot Requests: Read** ([prefilled link](https://github.com/settings/personal-access-tokens/new?name=COPILOT_GITHUB_TOKEN&description=GitHub+Agentic+Workflows+-+Copilot+engine+authentication&user_copilot_requests=read)), then store it:

```bash
gh aw secrets set COPILOT_GITHUB_TOKEN --value "<token>"
```

In an organization with centralized Copilot billing you can instead add `copilot-requests: write` under `permissions:` in the workflow and recompile; no token is needed ([reference](https://github.github.com/gh-aw/reference/auth/)).

Optional: pull requests created with the Actions token do not trigger CI. To run CI on the draft pull request automatically, add `GH_AW_CI_TRIGGER_TOKEN` (fine-grained PAT with **Contents: Read & Write** on this repository). gh-aw then pushes an empty commit to the pull request branch ([reference](https://github.github.com/gh-aw/reference/triggering-ci/)).

Enter tokens directly in GitHub Actions secrets or through a secure CLI prompt, never in chat or a committed file.

## 3. Labels, review rules and environment

```bash
gh label create service-change --color D93F0B --description "Created by the service-change impact workflow"
gh label create needs-human-approval --color FBCA04 --description "A person must approve before merge or deploy"
```

- Edit `.github/CODEOWNERS` to name your reviewers.
- In Settings -> Actions -> General, allow GitHub Actions to create pull requests. The agent's own job remains read-only; the separate safe-output job creates draft pull requests.
- Protect `main`: require a pull request, one approval, review from code owners and the `ci` checks.
- Create the environment **azure-verification** with required reviewers (Settings → Environments). `infra-deploy.yml` waits for this approval before deploying.

The October 6 private demo could not use branch protection (HTTP 403). The repository is now public, but branch protection and environment approval have not been configured/tested as part of output validation. Keep Azure authentication and deployment variables unset until those gates are deliberately configured and tested. CODEOWNERS alone is not an approval gate. See [current governance status](governance.md#public-reviewed-demo-2026-10-10).

## 4. First run

Actions → **Service-change impact analysis** → Run workflow, or:

```bash
gh aw run service-change-impact
```

For a dry run first, set `staged: true` under `safe-outputs:` in `.github/workflows/service-change-impact.md`, run `gh aw compile`, and commit both files. Staged runs show the Issues and pull request they would create in the step summary without writing anything.

## 5. Review the result

- **Step summary**: the deterministic pre-match (counts, candidates, evidence hints, warnings).
- **Artifact** `report`: `run/report/impact-report.md`, `index.html` and `candidates.json`. Every candidate must have exactly one valid verdict; `verify-report` must pass, not just the agent/safe-output jobs.
- **Pages**: [reviewed sample report](https://amex678.github.io/service-change-impact-workflow/). Enable Pages with Actions as its source. `pages.yml` renders only `docs/reports/` after sample-only validation. Public Pages never publishes a real-tenant report.
- **Issues** titled `[service-change] Azure <id>: …` or `[service-change] M365 <id>: …`, grouped under a parent Issue.
- **Draft pull request**, if an *Impacted* Azure notice maps to `infra/`.
- Check the first run for the three items the local tests could not cover: engine authentication, the MRC MCP tools, and whether a run with no candidates is skipped before the AI starts (look for the no-op message and no "Execute GitHub Copilot CLI" time).

Use `gh aw logs service-change-impact` and `gh aw audit <run-id>` to inspect runs.

To review already tracked findings without duplicate Issues/PRs, run with `review_tracked=true`:

```bash
gh workflow run service-change-impact.lock.yml -f review_tracked=true
```

The existing Issue link stays in each candidate. The agent re-evaluates it in the report and adds a bounded comment, but must not create a duplicate Issue/PR or overwrite a human decision. Normal runs skip only unchanged, non-expired verified assessments; a changed notice/configuration/policy, missing state or Cannot evaluate verdict triggers reassessment.

To reproduce the fixed input shape offline without API calls, tokens or AI, use
[the reference replay](reproduce.md). For a labelled frozen GitHub manual run,
select `input_mode=reference`. The default `live` mode still fetches current
public notices.

For an existing bot-created draft PR blocked as `action_required`, a repository owner can trigger `ci.yml` manually at its head branch, or push a reviewed empty commit using their own identity to obtain PR-linked checks. On October 10, PR 9 passed the latter path. Do not merge or deploy just to start CI. Automatic triggering for future generated PRs requires the scoped token above; do not repurpose the Copilot engine token.

## 6. Turn on the schedule

After reviewed repeated manual runs and a cost budget, uncomment `schedule: daily`, compile and commit. Revision-aware state reduces repeated work but does not permanently skip updated notices. Verify missing-input failures and visible zero-candidate reports before enabling the schedule.

Generated maintenance is separately disabled by `"maintenance": false` in `.github/workflows/aw.json`; recompiling preserves this setting. Leave it disabled during initial manual validation.

## 7. Use your own Azure inventory

Export read-only listings into the git-ignored `data/raw/` folder, then sanitize:

```powershell
az account set --subscription "<subscription>"
New-Item -ItemType Directory -Force data/raw | Out-Null
az resource list -o json > data/raw/resources.json
az disk list -o json > data/raw/disks.json
# Runtime settings are not in list output; read them per app and key them by the site id.
$apps = az functionapp list -o json | ConvertFrom-Json
@($apps | ForEach-Object {
  [pscustomobject]@{ id = $_.id; properties = @{ siteConfig = (az functionapp config show --ids $_.id -o json | ConvertFrom-Json) } }
}) | ConvertTo-Json -Depth 20 -AsArray | Set-Content data/raw/functionapp-config.json

python scripts/sanitize_azure_inventory.py data/raw/resources.json data/raw/disks.json data/raw/functionapp-config.json `
  --output data/inventory/azure-inventory.json --name-map data/raw/name-map.json
```

The workflow uses `data/inventory/azure-inventory.json` when it exists and the sample otherwise. The sanitized file still describes your environment. This public demo ignores `data/inventory/*.json` and refuses real inputs in public workflow/report publication. Use a separately reviewed private copy for real data; do not force-add exports to this public repository. Keep `data/raw/` (including the pseudonym map) out of git.

## 8. Microsoft 365 data

The workflow reads `data/inventory/m365-message-center.json` and `data/inventory/m365-tenant-profile.json` when present, in the same format as the samples. Record only settings you actually read, and where they came from. An unattended export from Actions needs Microsoft Graph `ServiceMessage.Read.All` as an application permission with admin consent ([reference](https://learn.microsoft.com/graph/api/serviceannouncement-list-messages?view=graph-rest-1.0)); that export is not part of this workflow yet.

## 9. Azure deployment (optional)

1. Create a verification resource group and a Microsoft Entra app registration.
2. Add federated credentials for this repository, one for pull requests and one for the `azure-verification` environment.
3. Grant the app deployment rights on that resource group only (for example Contributor on the resource group). Use a separate identity and environment for production.
4. Set repository variables: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_VERIFY_RESOURCE_GROUP`.

Without these variables `infra-deploy.yml` only builds the Bicep file.

## Run locally without Actions

```bash
mkdir -p run
python scripts/fetch_azure_updates.py --include-active-retirements --output run/azure-updates.json
python scripts/prepare_candidates.py --azure-updates run/azure-updates.json \
  --azure-inventory data/samples/azure-inventory.sample.json \
  --m365-notices data/samples/m365-message-center.sample.json \
  --m365-profile data/samples/m365-tenant-profile.sample.json \
  --output run/candidates.json
python -m unittest discover -s tests
```

Then ask GitHub Copilot in this repository to follow the instructions in `.github/workflows/service-change-impact.md` for `run/candidates.json` and write `run/impact-report.md`, without creating Issues or pull requests. After changing the workflow Markdown, always run `gh aw compile` and commit the regenerated `.lock.yml`.
