# Copilot instructions

This repository triages Microsoft service-change notices (Azure Updates, Microsoft 365 Message Center) against an organization's inventory and hands every decision to a person.

## Working rules

- Deterministic logic belongs in `scripts/` (Python standard library only) with tests in `tests/`. Run `python -m unittest discover -s tests` after changing scripts or `config/`.
- The agentic workflow source is `.github/workflows/service-change-impact.md`. After editing it, run `gh aw compile` and commit the regenerated `.lock.yml`. Never edit `*.lock.yml` by hand.
- Product names in `config/product-map.json` must exist in `config/azure-updates-products.json`; the tests enforce this.
- Use the four verdicts from the workflow (*Impacted*, *Not impacted*, *Needs investigation*, *Cannot evaluate*). Never report missing or incomplete data as *Not impacted*.
- Never commit raw exports, identifiers, tenant data or secrets. Raw files go to `data/raw/` (git-ignored); only sanitized output from `scripts/sanitize_azure_inventory.py` may go to `data/inventory/`.
- Changes to `infra/` must stay minimal and reviewable, and they reach Azure only through `infra-deploy.yml` after human approval.
- Keep synthetic samples labelled with `"sample": true`.
