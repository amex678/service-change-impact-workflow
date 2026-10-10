# Reproduce the reviewed sample demo

This repository is a **public, synthetic prototype**, not a customer deployment.
The independent submission repository is licensed under [MIT](../LICENSE).
Imported assets retain [their third-party notice](../THIRD-PARTY-NOTICES.md).

## Offline reference replay (no account, token or AI required)

Use Python 3.10 or newer. The code uses the Python standard library; CI tests
the supported minimum, Python 3.10. A newer version is not certified merely
because it can execute the commands.

From the repository root in PowerShell:

```powershell
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed.' }
python .\scripts\demo_replay.py --output-dir .\run\reference-first
if ($LASTEXITCODE -ne 0) { throw 'Reference replay failed.' }
python .\scripts\demo_replay.py --output-dir .\run\reference-second `
  --previous-report .\run\reference-first\report\candidates.json
if ($LASTEXITCODE -ne 0) { throw 'No-op replay failed.' }
```

The first replay evaluates the same 12 keys using the committed reviewed
verdicts and a **frozen paraphrased reference fixture**, not a current Azure API
response. Its result is 2 Impacted, 2 scope-limited Not impacted and 8 Needs
investigation. The second has zero candidates because the notice/configuration
fingerprints match and finding Issues are represented by explicit reference
stubs. It produces a visible no-op report without claiming to create Issues.

Both reports contain `impact-report.md`, `index.html` and `candidates.json`.
Open the HTML locally. No live API, model inference, GitHub write, Azure or
Microsoft 365 change occurs during this replay.

## Manual live workflow

Keep the schedule off. Use the setup and governance boundary in
[setup](setup.md) and [governance](governance.md).

```powershell
gh workflow run service-change-impact.lock.yml -f input_mode=live -f review_tracked=true
```

`live` fetches public Azure notices; inventory and M365 inputs must remain
synthetic in this public repository. `reference` uses the labelled frozen
fixture. A reference run is not evidence of current Microsoft announcements.

The report artifact is delivered by a trusted deterministic post-step, not an
agent upload request. `verify-report` validates delivered files and exact
candidate coverage. For zero candidates, the Copilot harness detects the
pre-written no-op, skips model inference, and the publisher still delivers
the zero-candidate scope report. Missing or incomplete inputs fail explicitly
rather than becoming a healthy no-op.

## Reassessment rather than permanent ID-only skipping

The last successful main-branch report supplies revision state. A SHA-256
fingerprint includes notice content/revision, captured configuration, product
mapping, evidence hints and assessment policy. Capture timestamps and resource
ordering alone do not trigger a change. A new notice, changed configuration,
changed policy, missing state, Cannot evaluate verdict or assessment age of
30 days requires reassessment.

Existing findings are kept: reassessments add bounded comments, not duplicate
Issues, closures, replacement of human decisions, or another remediation PR.
An Impacted/Needs investigation assessment with no corresponding finding is
not silently skipped. Normal no-op runs preserve prior assessment timestamps,
so repeatedly checking unchanged input cannot indefinitely extend freshness.

If an artifact expires, retrieval warns and re-evaluates rather than assuming
no impact. GitHub/authentication errors fail retrieval instead of becoming
success-shaped empty state.

## What automated quality checks do and do not prove

Known-revision guards cover the five corrected cases: SMS primary sign-in,
independent SCM/client TLS, the VM-client preview export, reservation orders,
and explicit subscription cloud. Missing deciding facts cannot pass as
Impacted or Not impacted. Changed notice revisions are not evaluated using
old guard conditions; the guard requires investigation until reviewed.

The resource column is rendered from the inventory. In particular, missing
disk `osType` is shown as an **unknown OS/data role**, not silently classified
as a data disk. These bounded checks are not a general proof of the remaining
prose, costs, usage, owner approval or runtime compatibility.

## Stable evidence

The reviewed [report source](reports/impact-report.md) and
[metadata](reports/review-candidates.json) remain versioned after Actions
artifact retention ends. [Pages](https://amex678.github.io/service-change-impact-workflow/)
is the latest reviewed view, not an immutable version identifier. The sample
demo Release pins a source commit and provides a downloadable reviewed report.
It excludes raw exports, credentials, agent logs and stale video drafts.

For deployment or a real-tenant evaluation, use a separately approved private
copy, explicit input capture, human owners and enforced review gates. No such
deployment or evaluation is authorized by these reproduction instructions.
