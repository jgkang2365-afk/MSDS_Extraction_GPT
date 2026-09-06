# Re-baselined MSDS package

This package is the parallel implementation area for the MSDS re-baselining work.

Initial responsibility map:

- `models.py`, `normalization.py`: structured values, states, evidence, pure normalization
- `pdf_io.py`, `sections.py`: lightweight PDF analysis and Section 1/3 fence isolation
- `collectors.py`, `resolver.py`, `validation.py`: candidate collection, resolution, PASS/REVIEW judgement
- `pipeline.py`, `workers.py`: orchestration, cancellation/budget boundaries, OCR lifecycle
- `store.py`, `review.py`: machine result, user correction, approved result history
- `enrichment.py`, `presentation.py`: KOSHA/MES enrichment and legacy GUI/Excel presentation bridge
- `adapters/`: only external/legacy integrations that are actually needed

No legacy extraction rule should be copied here merely because it exists in `msds_engine_v6.py`. Rules must trace back to PRD v1.1 / TRD v1.1 or validated evidence.
