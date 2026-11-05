# Local research data

This directory is intentionally empty in the GitHub release.

Create these local-only subdirectories as needed:

```text
data/raw/          immutable platform exports
data/interim/      crawler state and intermediate files
data/processed/    normalized platform CSV files
data/annotations/  human annotations
data/edge-profile/ browser login state; highly sensitive
```

All of these subdirectories are excluded by `.gitignore`. Do not remove those exclusions unless a separate, fully anonymized and legally redistributable dataset has passed a new ethics and copyright review.

