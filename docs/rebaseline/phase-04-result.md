# Phase 04 — Scan/OCR Foundation

## Contract and boundary

- `scan_pdf_sections()` routes Section 1 and Section 3 independently. A target
  already confirmed as `TEXT` uses the existing Phase 2 `build_section_input()`
  path and does not initialize, render, or invoke OCR. A target with missing
  digital text uses only an explicitly supplied local OCR engine; no engine
  produces an explicit `OCR_ENGINE_NOT_SUPPLIED` route outcome, not a fallback.
- Recon renders/OCRs pages solely to locate the `1 → 2` or `3 → 4` heading
  boundary using the existing NFKC heading rules. Missing/ambiguous boundaries
  remain `FENCE_PARTIAL` / `FENCE_NOT_FOUND`; there is no whole-document or
  fixed-first-pages collector fallback. Section 3 has no multi-page cutoff.
- Recon pages, whole-page PNG data, PDF paths, and fitz handles are private to
  the scan call. A confirmed OCR `SectionInput` holds only bbox-filtered OCR
  tokens and fence-cropped PNG bytes (`IsolatedImage`, with digest). Its
  `input_digest` includes both selected token geometry/text and crop digests.
  OCR pixel boxes map to zero-based, unrotated CropBox PyMuPDF coordinates.
- Collectors accept confirmed `TEXT` or `OCR` inputs and emit the existing
  candidate/evidence structures only. OCR evidence is `EvidenceSourceType.OCR`.
  No resolver, validator, final pairing, final status, chemistry correction,
  filename, other-section, database, network, Vision AI, or ODL route was added.

## Engine inventory and selected adapter

- `paddleocr` and `pytesseract` are importable in this environment.
- The `tesseract` executable is not available on `PATH`.
- `LazyPaddleOcrEngine` has no default `PaddleOCR()` construction path. It
  requires an explicit injected, already-local/preconfigured factory; otherwise
  it fails with `LOCAL_PADDLE_FACTORY_REQUIRED`. A supplied engine is reused for
  a scan batch and released after it. The adapter passes only image bytes to
  `engine.ocr(image_bytes)`; it deliberately does **not** use legacy `cls=False`,
  automatic model download, remote fallback, or external calls. Metrics expose
  initialization/invocation/render/release and a fixed zero external-call count.
- Focused tests use an injected in-memory fake engine. No real Paddle OCR smoke
  was run: local model availability was not established and model download or
  external communication is prohibited. Therefore this phase does not claim a
  real-engine OCR PASS.

## Executed verification

- `python -m pytest tests/rebaseline/test_scan_ocr.py -q`: 27 passed (fake
  engine, image-only/digital/mixed routing, S1/S3 fences, no S3 cap, isolation,
  rotation/CropBox/columns, and raw candidate/evidence regressions).
- `python -m pytest tests/rebaseline -q`: 162 passed. `compileall` for
  `src/msds` and `golden/v2`, import smoke for models/normalization/pdf_io/
  sections/collectors/ocr, and `git diff --check`: passed.
- `python -m pytest tests/test_common_normalization.py -q`: Coordinator direct
  final environment result: 6 passed in 0.17s. The Lead managed terminal denies
  `TemporaryDirectory` child access, so its equivalent one-shot workspace-temp
  shim plus `--basetemp` run passed 6 in 0.25s; no common test or legacy source
  was changed for that terminal-only restriction.
