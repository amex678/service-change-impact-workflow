# Owner-only configuration still required

Pushing code does not configure credentials, approval enforcement, ownership,
or a customer deployment. This prototype deliberately leaves them separate.

| Item | Current boundary | Owner action before enabling it |
|---|---|---|
| Generated PR CI | PR 9 passed after an owner-origin empty commit | Create a repository-scoped `GH_AW_CI_TRIGGER_TOKEN` with Contents Read/Write through GitHub's secure UI; do not reuse the Copilot token |
| Branch review | `main` has no enforced review rule | Require PR review, CODEOWNERS and the actual check names `unit-tests`, `bicep`, `actionlint`, `workflow-compile`; test rejected unapproved changes |
| Azure environment | No Azure authentication/deployment variables; no approved deployment | Configure and test required reviewers on `azure-verification` before providing Azure identity or variables |
| Finding ownership | Findings have proposed next checks, not confirmed assignees | Assign human owners and decision dates; do not invent assignees or infer deadline compliance |
| Real inputs | This public demo accepts samples only | Use an approved private copy and explicit read-only captures, not force-added public exports |
| Daily run | Disabled | Enable only after reviewed repeated manual runs, verified no-op/error behavior and a cost budget |
| App demo | The App is the designed entry point; screen slots remain placeholders | Record the actual GitHub Copilot App interaction. Actions/Pages screens are not substitute App evidence |
| Video | Updated source; voice/HTML/VTT/MP4 regeneration is pending | Use a policy-approved environment to regenerate narration; verify manifest hash, timing and full decode before publishing |

No token value belongs in chat, source, an Issue or a Release. No configuration
in this checklist authorizes an automatic merge, tenant setting change or
deployment. Final approval is a human decision, not an AI-generated review.

## Measurement plan, not invented results

Run the same fixed notices, inventory and expected artifacts through the manual
baseline and the Copilot workflow. Record elapsed investigation time, handoff
steps, corrections, model credits, setup effort and unresolved facts. A
Claude Code comparison needs the same inputs and artifact expectations.
Do not claim measured savings, customer adoption or comparative superiority
until the actual results are captured.
