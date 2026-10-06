# Your inventory

Put **sanitized** files here to replace the samples in `data/samples/`:

- `azure-inventory.json`: output of `scripts/sanitize_azure_inventory.py`
- `m365-message-center.json` and `m365-tenant-profile.json`: same format as the samples

The workflow uses these files when they exist. Raw exports and the pseudonym map belong in `data/raw/`, which git ignores. See [docs/setup.md](../../docs/setup.md), steps 7 and 8.
