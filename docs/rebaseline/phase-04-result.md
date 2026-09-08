# Phase 04 — Scan/OCR Foundation

## Contract and boundary

- `scan_pdf_sections()` routes Section 1 and Section 3 independently. A target
  with observed digital text, including a partial/missing digital fence,
  retains its `TEXT` route and does not initialize, render, or invoke OCR when
  its target span has no relevant image. For a partial heading, image relevance
  is limited to the observed heading-to-boundary span; when no end boundary
  Evidence exists, it continues from the observed start through the next
  explicit digital heading for a different section (or document end when none
  is observed). That next heading is selected in physical page/y/x order, not
  raw PDF line storage order. Images after that boundary and small
  header/footer/side-margin decoration cannot trigger OCR. A relevant body/boundary image
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
  supported. A single exact `Product` / `Product name` / `Product identifier`
  / Korean-equivalent label (with no terminal separator or a terminal `:` or
  `|`) plus its same-row right value is admitted only as a proven label/value
  band. Product-like raw values are retained; an unproven far-right/foreign
  column remains partial rather than silently dropping the value.
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
  79 passed. This
  includes P4-FIX-01~05 (partial digital target image relevance and independent
  S1 text/S3 OCR routing) and P4-FIX-06~13 (structured OCR rows, safe/partial
  independent columns, including P4-FIX-13 two-Evidence partial-fence public
  routing for no-image, body-image, decorative-logo, and later-unrelated-image
  cases; P4-FIX-14~24 add the no-end-Evidence multi-page S3 continuation
  route, next-explicit-section, unknown-placement, and header/footer/side-margin counterfactuals,
  independent S1 TEXT/S3 OCR routing, safe single Product label/value spans,
  Product/Korean/Model/Grade/concentration raw preservation, partial
  handling for an unproven far-right column, and P4-FIX-25~26 colonless and
  terminal-pipe strong Product labels with same-row raw/evidence preservation;
  P4-FIX-27 verifies that reversed raw line storage cannot extend a partial
  target past a visually earlier next-section heading.
  Existing foreign S1 product exclusion across
  0/90/180/270-degree rotations and S3 CAS exclusion, CropBox geometry, and
  ambiguous-end/later-image and top-left-logo OCR guards).
  The pytest cache-write warning is an existing `.pytest_cache` environment
  permission warning and is separate from the PASS result.
- `python -m pytest tests/rebaseline -q`: 214 passed, with the same one pytest
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
| Phase 4 v1.1 Final Fresh Verifier (historical) | gpt-5.6-sol | high | Coordinator-owned | Not recorded by this Lead update. |
| Coordinator / Orchestrator | UNVERIFIABLE | UNVERIFIABLE | global AGENTS temporary direct-terminal workaround | Primary-session runtime metadata was not exposed. Supervised Orca DAG/dispatch was not used. |

### Phase 4 v1.2 direct-terminal record

| Role | Model | Effort | Execution | Evidence |
| --- | --- | --- | --- | --- |
| Implementation Lead | gpt-5.6-terra | high | direct / serial | Initial implement `term_172da499-9ffa-428a-9ec1-1ded9a1105c6`; P1-B reopen `term_6ec51298-61f2-41e7-adf5-4510d5db68fa`; P1-A order reopen `term_1e46ae25-e94c-408f-8b25-c7f226bbc4a8`. Runtime TUI header observed. |
| Fresh Verifier attempt 1 | gpt-5.6-sol | high | READ_ONLY / direct / serial | `term_969bdd1d-9fad-4043-9542-4bb86e1b6d6a`; FAIL: P1-B colonless strong label silently drops right value; Lead reopened. |
| Fresh Verifier attempt 2 | gpt-5.6-sol | high | READ_ONLY / direct / serial | `term_c588267d-0f7d-4160-ac01-c1f3fb7a747b`; FAIL: P1-A physical boundary order; Lead reopened. |
| Final Fresh Verifier | gpt-5.6-sol | high | READ_ONLY / direct / serial | `term_2b274e72-a0a2-4812-a0a6-842f346ad67c`; PASS focused 79, rebaseline 214, diff check and protected diff 0; observed TUI header. |
| Coordinator/Orchestrator | UNVERIFIABLE | UNVERIFIABLE | direct / serial | Primary runtime metadata unavailable. No supervised Orca DAG/dispatch used. Direct-terminal workaround used. All actual workers started and results recovered; no interrupted/unrecovered worker remains. |
| Documentation sync | gpt-5.6-luna | low | direct / serial | Current terminal `term_cba7b425-0870-4ede-ad9f-9e5a31ce53a1`. Runtime TUI header observed. |

Fresh verifier new findings = 2 (P1-B colonless value drop, P1-A physical heading order); reopen count = 2; final Fresh PASS = after both reopens. No supervised DAG/dispatch; no direct terminal workaround beyond the documented temporary direct-terminal lifecycle.
