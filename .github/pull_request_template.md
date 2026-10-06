## What changes

<!-- For service-change pull requests, the agentic workflow fills this in: notice, before → after, why it resolves the notice. -->

## Reviewer checklist

- [ ] The linked notice and Issue justify this change, and the verdict evidence is correct
- [ ] The change is minimal and limited to what the notice requires
- [ ] CI passed (unit tests, Bicep build, actionlint) and the what-if output was reviewed
- [ ] Risks, validation steps and rollback are stated and acceptable
- [ ] No identifiers, secrets or tenant data were added
- [ ] Deployment will go to the verification environment first; production is promoted separately
