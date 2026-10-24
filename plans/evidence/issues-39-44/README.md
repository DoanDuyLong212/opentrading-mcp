# Issues 39/44 evidence

`review_repros.py`, `repro44.py`, `repro44_noop.py`, `results39.json`, `results44.json` and `report44.txt` are historical review evidence against main `2260f48`; their old behavior is not a claim about this branch.

[first-wave-validation.md](first-wave-validation.md) records implementation validation, source hashes and exact test scopes. The 646-test baseline preceded the signed-margin repair; `post-repair-focused.log` records 127 affected tests afterward and `final-docs-prompts.log` records 12 final consumer checks. Fresh CI must establish full-suite results on the final head.

[annual-source-validation.md](annual-source-validation.md) records public annual source facts and limits; sanitized source fixtures live under `tests/fixtures/financeinfo_*_annual_20261024.json`. Complete mathematical proof uses synthetic independent oracles rather than claiming complete upstream fields.

Run the two relocated oracles from the repository root with `PYTHONPATH=src python plans/evidence/issues-39-44/independent_oracle.py` and `PYTHONPATH=src python plans/evidence/issues-39-44/negative-margin-oracle.py`. Historical acquisition commands in source notes refer to temporary review processes; they are not self-contained source acquisition tooling. No private configuration is included.
