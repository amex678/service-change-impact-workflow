---
description: >-
  Match Azure Updates and Microsoft 365 Message Center notices against the
  organization's inventory, then open evidence-based Issues and, when an Azure
  change can be expressed in infra/, a draft pull request for human approval.
  Goal: shorten the time from a Microsoft service-change notice to a reviewed,
  evidence-backed response, without applying any change automatically.
labels: ["service-change", "azure", "microsoft-365", "governance"]

on:
  workflow_dispatch:
    inputs:
      lookback_days:
        description: "Days of recently modified Azure Updates to include (retirements are always included)"
        required: false
        default: "14"
      include_m365:
        description: "Include Microsoft 365 Message Center notices from data/ (synthetic sample by default)"
        type: boolean
        required: false
        default: true
      review_tracked:
        description: "Re-evaluate tracked notices in the report without creating duplicate Issues or pull requests"
        type: boolean
        required: false
        default: false
      input_mode:
        description: "Live public Azure notices, or the labelled frozen synthetic reference demo"
        type: choice
        options: [live, reference]
        required: false
        default: live
  # Enable only after reviewed manual runs (docs/setup.md, step 6):
  # schedule: daily

permissions:
  contents: read
  actions: read
  issues: read
  pull-requests: read

engine:
  id: copilot
  model: gpt-5.4
timeout-minutes: 30

network:
  allowed:
    - defaults
    - "www.microsoft.com"
    - "azure.microsoft.com"
    - "learn.microsoft.com"

tools:
  github:
    toolsets: [default]
  edit:
  web-fetch:
  bash: ["cat", "head", "tail", "grep", "jq", "ls", "wc"]

mcp-servers:
  microsoft-release-communications:
    url: "https://www.microsoft.com/releasecommunications/mcp"
    allowed: ["get_azure_update_by_id", "get_recent_azure_updates"]

steps:
  - name: Fetch Azure Updates (public, read-only)
    env:
      LOOKBACK_DAYS: ${{ github.event.inputs.lookback_days }}
      INPUT_MODE: ${{ github.event.inputs.input_mode }}
    run: |
      mkdir -p run
      case "${INPUT_MODE:-live}" in
        live) python3 scripts/fetch_azure_updates.py --lookback-days "${LOOKBACK_DAYS:-14}" \
          --include-active-retirements --output run/azure-updates.json ;;
        reference) cp data/samples/azure-updates.reference.json run/azure-updates.json ;;
        *) echo "Unknown input mode; refusing to fetch." >&2; exit 1 ;;
      esac
  - name: Restore the previous verified assessment revisions
    env:
      GH_TOKEN: ${{ github.token }}
    run: python3 scripts/restore_assessment.py --output run/previous-candidates.json
  - name: List Issues that already track notices
    env:
      GH_TOKEN: ${{ github.token }}
    run: |
      gh issue list --label service-change --state all --limit 500 --json number,title,state \
        > run/existing-issues.json
  - name: Pre-match notices against the inventory (deterministic)
    env:
      INCLUDE_M365: ${{ github.event.inputs.include_m365 }}
      REVIEW_TRACKED: ${{ github.event.inputs.review_tracked }}
      INPUT_MODE: ${{ github.event.inputs.input_mode }}
      REPOSITORY_VISIBILITY: ${{ github.event.repository.visibility }}
      # A noop written here lets the harness skip the AI run when nothing needs evaluation.
      GH_AW_SAFE_OUTPUTS: ${{ steps.set-runtime-paths.outputs.GH_AW_SAFE_OUTPUTS }}
    run: |
      pick() { if [ -f "data/inventory/$1" ]; then echo "data/inventory/$1"; else echo "data/samples/$2"; fi; }
      if [ "${INPUT_MODE:-live}" = "reference" ] && find data/inventory -maxdepth 1 -name '*.json' | grep -q .; then
        echo "The frozen reference demo must not mix in environment exports." >&2
        exit 1
      fi
      previous_args=()
      if [ -f run/previous-candidates.json ]; then previous_args=(--previous-report run/previous-candidates.json); fi
      public_args=()
      case "$REPOSITORY_VISIBILITY" in
        public) public_args=(--public-output) ;;
        private) ;;
        *) echo "Repository visibility is unavailable; refusing to publish inputs." >&2; exit 1 ;;
      esac
      python3 scripts/prepare_candidates.py \
        --azure-updates run/azure-updates.json \
        --azure-inventory "$(pick azure-inventory.json azure-inventory.sample.json)" \
        --m365-notices "$(pick m365-message-center.json m365-message-center.sample.json)" \
        --m365-profile "$(pick m365-tenant-profile.json m365-tenant-profile.sample.json)" \
        --include-m365 "${INCLUDE_M365:-true}" \
        --existing-issues run/existing-issues.json \
        --review-tracked "${REVIEW_TRACKED:-false}" \
        "${public_args[@]}" "${previous_args[@]}" \
        --output run/candidates.json \
        --summary "$GITHUB_STEP_SUMMARY" \
        --noop-file "$GH_AW_SAFE_OUTPUTS"
  - name: Preserve the trusted report publisher and candidate snapshot
    run: |
      mkdir -p run/report
      mkdir -p "$RUNNER_TEMP/gh-aw/report-publisher/scripts" "$RUNNER_TEMP/gh-aw/report-publisher/templates"
      cp scripts/publish_report.py "$RUNNER_TEMP/gh-aw/report-publisher/scripts/"
      cp scripts/assessment.py "$RUNNER_TEMP/gh-aw/report-publisher/scripts/"
      cp templates/impact-report.html "$RUNNER_TEMP/gh-aw/report-publisher/templates/"
      cp run/candidates.json "$RUNNER_TEMP/gh-aw/report-publisher/candidates.json"

post-steps:
  - name: Validate every verdict and stage the complete report
    env:
      RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
      REPOSITORY_VISIBILITY: ${{ github.event.repository.visibility }}
    run: |
      public_args=()
      case "$REPOSITORY_VISIBILITY" in
        public) public_args=(--public-output) ;;
        private) ;;
        *) echo "Repository visibility is unavailable; refusing to publish inputs." >&2; exit 1 ;;
      esac
      python3 "$RUNNER_TEMP/gh-aw/report-publisher/scripts/publish_report.py" \
        --candidates "$RUNNER_TEMP/gh-aw/report-publisher/candidates.json" \
        --report run/impact-report.md --output-dir run/report \
        --stage-dir "$RUNNER_TEMP/gh-aw/safeoutputs/upload-artifacts/run/report" \
        --run-url "$RUN_URL" "${public_args[@]}"
      if [ "$(jq '.counts.candidates' "$RUNNER_TEMP/gh-aw/report-publisher/candidates.json")" -eq 0 ]; then
        echo "Deterministic no-op: report prepared without AI execution." >> "$GITHUB_STEP_SUMMARY"
      fi
  - name: Deliver the validated report (including zero-candidate runs)
    uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
    with:
      name: report
      path: ${{ runner.temp }}/gh-aw/safeoutputs/upload-artifacts/
      retention-days: 30
      if-no-files-found: error
      overwrite: true
jobs:
  verify-report:
    needs: [agent, safe_outputs]
    if: ${{ !cancelled() && needs.agent.result != 'skipped' }}
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      actions: read
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
        with:
          persist-credentials: false
      - name: Download the required report (missing artifact fails the run)
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1
        with:
          name: report
          path: report-artifact
      - name: Verify delivered files and every candidate verdict
        env:
          REPOSITORY_VISIBILITY: ${{ github.event.repository.visibility }}
        run: |
          public_args=()
          case "$REPOSITORY_VISIBILITY" in
            public) public_args=(--public-output) ;;
            private) ;;
            *) echo "Repository visibility is unavailable; refusing to publish inputs." >&2; exit 1 ;;
          esac
          python3 scripts/publish_report.py --verify-directory report-artifact/run/report "${public_args[@]}"

safe-outputs:
  allowed-domains: [default-safe-outputs, "azure.microsoft.com", "learn.microsoft.com", "www.microsoft.com"]
  create-issue:
    title-prefix: "[service-change] "
    labels: [service-change]
    max: 6
    group: true
    deduplicate-by-title: true
    expires: false
  add-comment:
    target: "*"
    max: 15
    issues: true
    pull-requests: false
    required-labels: [service-change]
    required-title-prefix: "[service-change] "
  create-pull-request:
    title-prefix: "[service-change] "
    labels: [service-change, needs-human-approval]
    draft: true
    max: 1
---

# Service-change impact analysis

You help an operations team decide which Microsoft service changes need action in **their** environment. You propose; people decide. Nothing you do may change Azure, Microsoft 365, or the default branch directly.

## Inputs prepared for you

Deterministic steps have already run. Read these files first:

- `run/candidates.json`: notices pre-matched to the inventory. Each entry in `candidates` has the notice (`notice`), why it was ranked (`signal`, `evidence_hints`), and the matching resources (`matched_resources`, Azure) or the tenant settings (`tenant_settings`, Microsoft 365). `deferred`, `already_tracked`, `counts`, `coverage` and `warnings` describe everything you were **not** asked to evaluate.
- `run/azure-updates.json`: every Azure Updates notice that was fetched, with the fetch completeness.
- `templates/impact-report.md`: the report format.
- `infra/`: the Infrastructure as Code that this repository controls.

Evidence hints only explain the ranking. They are never proof: confirm every condition yourself.
`evidence_requirements`, when present, defines the known-revision guard's allowed verdicts and missing deciding facts. Stay within those verdicts; do not invent a configuration capture to bypass a gap. Changing the inventory or reviewing a new notice revision is a separate human-controlled input change.

## Verdicts

Give each candidate exactly one verdict:

- **Impacted**: the notice's conditions match configuration that the inventory confirms. Cite the notice text and the matching values.
- **Not impacted**: the relevant configuration was captured and it does not meet the notice's conditions. Cite the values that rule it out.
- **Needs investigation**: a candidate exists but a deciding fact is missing (for example a runtime version, a feature flag, or usage that the inventory does not capture). Say exactly what to check and where.
- **Cannot evaluate**: inputs are missing or incomplete (fetch errors, an incomplete fetch, a notice you could not read). Never turn this into "not impacted".

Rules:

1. Separate the notice's publication or update date from the date the change takes effect. Treat a deadline as confirmed only when the notice states it.
2. A resource type or product match alone is not impact. A notice that only says "review your usage" is at most "needs investigation" unless the inventory settles it.
3. For more detail, use the notice `links`, `web-fetch` on learn.microsoft.com, or the `microsoft-release-communications` tools (`get_azure_update_by_id`). Do not guess costs, usage or billing impact.
4. Report `deferred` and `already_tracked` items as "not evaluated in this run" with their reason. Never describe them as not impacted.
5. Respect the data boundary: refer to resources only by the names in the inventory (they are pseudonyms), and never output subscription, tenant or resource identifiers. For Microsoft 365, quote at most one short sentence from a notice; do not paste notice bodies.
6. If `inputs.azure_inventory.sample` or `inputs.m365.sample` is true, say clearly in every output that the environment is a synthetic sample.
7. Do not equate an enabled SMS authentication policy with SMS primary sign-in: `includeTargets[].isUsableForSignIn` is a separate deciding fact. A Disk Encryption Set is not evidence that Azure Disk Encryption is enabled.
8. Scope a Not impacted verdict to captured facts. An application's `minTlsVersion` does not capture the SCM site's TLS setting or client compatibility. A region alone is not an explicit subscription cloud identifier. Missing deciding facts require Needs investigation, not an assumed default.
9. A candidate with `tracking_issue` is a re-review of an existing finding. Evaluate it in the report, link that Issue and add a bounded re-assessment comment with the current verdict, changed facts, remaining gaps and run link. Do not create another Issue or pull request, overwrite a human review, or close the finding.
10. Do not label a disk as a data disk just because `osType` is missing. Keep its OS/data role unknown until captured. Reservations require reservation-order evidence: a current VM series can be excluded without proving that the account has no other affected reservations.

## What to produce

1. **Report.** Write `run/impact-report.md` following `templates/impact-report.md`. Section 2 must contain exactly one six-column row per candidate, with the exact candidate key, matched configuration or explicitly limited scope, deciding evidence, one of the four verdicts and a next step. Section 3 must include a heading with the exact key for every Impacted or Needs investigation row. Use actual newlines, never literal `\n` sequences, and retain the notice's original source URL.

   The trusted post-step validates your rows and the known-revision evidence guards, replaces scope/counts and captured-resource labels from the deterministic snapshot, generates HTML and delivers artifact `report`. Do not request an upload tool or execute a publisher yourself. Missing or invalid output fails publication and `verify-report`. Detail headings must begin with `### Azure <id>:` or `### M365 <id>:` without formatting around the key.

2. **Issues.** Create one Issue per candidate whose verdict is **Impacted** or **Needs investigation**, highest urgency first. Use this exact title, so later runs can recognize it:
   - Azure: `Azure <notice id>: <notice title>`
   - Microsoft 365: `M365 <message id>: <message title>`

   Issue body sections: **Verdict**, **Why** (notice conditions next to the matching configuration), **Affected resources or settings**, **Deadline** (as stated by the notice), **Recommended next step**, **What a person must decide** (a short checklist), **Confidence and gaps**, **Source** (notice URL). For Microsoft 365, the recommended step is an admin action to review. Never propose a configuration change as code.

   For candidates with `tracking_issue`, use `add_comment` on that Issue instead, even if the updated verdict is Not impacted; retain the historical finding for human disposition. If no new Issue or comment is required, call `noop` after completing the report; the trusted publisher still delivers it.

3. **Draft pull request (Azure only, at most one).** When an **Impacted** Azure notice maps to a resource declared in `infra/` and the fix is a small, well-defined change (for example a runtime version bump the notice recommends):
   - Edit only files under `infra/`, keeping the change minimal.
   - Title it `Azure <notice id>: <what changes>`.
   - In the body, show the change as before → after, why it resolves the notice, the risks, how a reviewer should validate it (for example `az bicep build` and a what-if on a verification resource group), and how to roll back. State that it must be deployed only after human approval.
   - If the fix needs a decision you cannot make (such as a new SKU with cost impact, or data migration), do not open a pull request; explain the options in the Issue instead.

4. **Nothing to do.** If no candidate is Impacted or Needs investigation, still write and upload the report, then call `noop` with a one-line summary. If you create nothing at all, you MUST call `noop`.

Write all outputs in English, concisely, for an operations reviewer.
