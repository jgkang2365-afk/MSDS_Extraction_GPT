# Phase 04 — Scan/OCR Foundation

## Contract and boundary

- `scan_pdf_sections()` routes Section 1 and Section 3 independently. A target
  with observed digital text, including a partial/missing digital fence,
  retains its `TEXT` route and does not initialize, render, or invoke OCR when
  its target span has no relevant image. For a partial heading, image relevance
  is limited to the observed heading-to-boundary span (or that heading page
  when no end boundary Evidence exists); document-wide unrelated images and small
  top/right decorative logos cannot trigger OCR. A relevant body/boundary image
  or the locator's `SECTION_MIXED_TEXT_AND_IMAGE_REQUIRED` outcome routes that
  target through local OCR. A fully digital no-image document retains the text
  route even when a blank page is present. A confirmed target uses the existing
  Phase 2 `build_section_input()` path. A target with missing digital text uses
  only an explicitly supplied local OCR engine; no engine produces an explicit
  `OCR_ENGINE_NOT_SUPPLIED` route outcome, not a fallback.
- Recon renders/OCRs pages solely to locate the `1 → 2` or `3 → 4` heading
  boundary using the existing NFKC heading rules. Missing/ambiguous boundaries
  remain `FENCE_PARTIAL` / `FENCE_NOT_FOUND`; there is no whole-document or
  fixed-first-pages collector fallback. Section 3 has no multi-page cutoff.
- Recon pages, whole-page PNG data, PDF paths, and fitz handles are private to
  the scan call. A confirmed OCR `SectionInput` holds only bbox-filtered OCR
  tokens and fence-cropped PNG bytes (`IsolatedImage`, with digest). Its
  `input_digest` includes both selected token geometry/text and crop digests.
  OCR pixel boxes map to zero-based, unrotated CropBox PyMuPDF coordinates.
- OCR source does not bypass column safety. Repeated Section 1 label/value rows
  and Section 3 CAS/content table rows are admitted as structured layouts. An
  independent same-page OCR column is bounded to the target heading side only
  when that x-bound is non-crossing; otherwise it is `FENCE_PARTIAL` with an
  explicit reading-order reason. Structured rows are split into individual
  table bands, so two independently plausible S1 label/value or S3 CAS/content
  columns never become one table. Unanchored independent middle-page columns
  are partial. This prevents other-column product/CAS text from entering a
  target `SectionInput`, while ordinary multi-page Section 3 tables remain
  supported.
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
  initialization/invocation/render/release and preserve the engine's observed
  external-call count; the local adapter itself always reports zero.
- Focused tests use an injected in-memory fake engine. No real Paddle OCR smoke
  was run: local model availability was not established and model download or
  external communication is prohibited. Therefore this phase does not claim a
  real-engine OCR PASS.

## Executed verification

- Lead standard validation: `python -m pytest tests/rebaseline/test_scan_ocr.py -q`:
  54 passed. This
  includes P4-FIX-01~05 (partial digital target image relevance and independent
  S1 text/S3 OCR routing) and P4-FIX-06~13 (structured OCR rows, safe/partial
  independent columns, including P4-FIX-13 two-Evidence partial-fence public
  routing for no-image, body-image, decorative-logo, and later-unrelated-image
  cases; actual foreign S1 product exclusion across
  0/90/180/270-degree rotations and S3 CAS exclusion, CropBox geometry, and
  ambiguous-end/later-image and top-left-logo OCR guards).
  The pytest cache-write warning is an existing `.pytest_cache` environment
  permission warning and is separate from the PASS result.
- `python -m pytest tests/rebaseline -q`: 189 passed, with the same one pytest
  cache-write warning. `python -m pytest tests/test_common_normalization.py -q`:
  6 passed. `python -m compileall -q src/msds golden/v2`, import smoke for
  models/normalization/pdf_io/sections/collectors/ocr, and diff check: PASS.
- `git diff --check`: passed. Base-to-HEAD forbidden paths were checked after
  implementation; no forbidden-file diff was introduced by this worktree.

## Execution metadata

| Role | Model | Effort | Execution | Evidence |
| --- | --- | --- | --- | --- |
| Phase 4 P1 WRITE Lead | gpt-5.6-terra | high | direct / serial | Actual TUI runtime observed: `term_45e02732-0c65-469d-919a-50d38b1ad727`, `term_fd82941d-012a-44c3-a67f-65047f0821e7`, `term_c4383c4e-654a-46d8-b6cf-a31f1027facc`, `term_9f6bb9e8-4323-43e4-9974-52247dc838c4`. |
| Fresh Verifier — reopen 1 | gpt-5.6-sol | high | READ_ONLY / direct / serial | FAIL; multi-column leakage finding; reopened (`term_d847db4d-75d8-41b4-8e2e-346513125a34`). |
| Fresh Verifier — reopen 2 | gpt-5.6-sol | high | READ_ONLY / direct / serial | FAIL; Product value-label false positive finding; reopened (`term_ee5ad4a3-de9c-45aa-bb9d-1d2e9c0e8913`). |
| Fresh Verifier — reopen 3 | gpt-5.6-sol | high | READ_ONLY / direct / serial | FAIL; `Evidence.page_index` AttributeError finding; reopened (`term_4cda59d4-50ff-4eb4-90df-96728742f7eb`). |
| Final Fresh Verifier | gpt-5.6-sol | high | READ_ONLY / direct / serial | PASS (`term_efcae3c3-c56c-4af5-bb83-8136848f51b8`): independent focused 54 passed, selected adversarial 13 passed, protected diff 0. |
| Coordinator / Orchestrator | UNVERIFIABLE | UNVERIFIABLE | global AGENTS temporary direct-terminal workaround | Primary-session runtime metadata was not exposed. Supervised Orca DAG/dispatch was not used. |
