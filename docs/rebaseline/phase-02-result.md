# Phase 02 — digital PDF Section 1/3 locator and fence result

## Scope and boundary

- Implemented only the digital-PDF Section 1 / Section 3 locator, rectangular fence, and isolated `SectionInput` handoff.
- No product-name selection, CAS/content extraction or pairing was added. OCR, AI, ODL, KOSHA, and all other external calls are zero in this phase.
- The reader uses PyMuPDF 1.27.2 read-only. It does not render pages; `render_calls=0` and `external_calls=0` are reported in read metrics.

## Implemented behavior

- Header confirmation uses section number, matching Korean/English heading text, layout, and document order. Table-of-contents runs, body references, `3.1` / `3.2`, CAS-like numbers, and repeated start headers cannot become a confirmed fence.
- A missing ending header, conflicting repeated start, ambiguous same-page or multi-page reading order, image-reading requirement, cancellation, or deadline produces `FENCE_PARTIAL` with a reason. Start, continuation, and ending pages are never admitted as the whole `page.rect`: only an observed single-column body span is allowed, exact repeated top/bottom lines are excluded except structurally repeated Section 3 table-header rows, and a line crossing a body boundary blocks the fence. A wide aligned three-column Section 3 table is distinct from independent page columns. Section 1 and Section 3 are located independently.
- Heading matching uses an NFKC-and-whitespace-normalized search key only; original layout text, including whitespace and line structure in `SectionInput`, remains unchanged. It accepts `SECTION 1 IDENTIFICATION`, `1 IDENTIFICATION`, and full-width numeral/punctuation variants.
- `PageRegion` and token coordinates are zero-based and unrotated in the CropBox coordinate space. The reader records every actual image placement. A small right-margin image that does not overlap body text is admitted before outside-body-x-span classification when sufficient digital body text is present, including on a header-only boundary page. Central, large, unknown, image-only, or same-region text/image placement blocks an otherwise digital fence. A confirmed `SectionInput` is always `TEXT` capability, and no `terminal_reason` layout can produce one.
- The builder re-runs the locator for the exact layout and rejects a fence whose ID, section, SHA, capability/reasons, or regions do not equal locator output. It validates page bounds and rectangles, and blocks construction when a character bbox intersects but is not wholly inside an allowed/excluded boundary; no boundary-crossing token is silently dropped.
- Synthetic real-PDF tests cover digital Korean/English and NFKC heading keys, exact whitespace-preserving `SectionInput` source strings, same-page and multi-page boundaries, repeated first/middle/last-page header/footer exclusion with structurally retained Korean/alternate Section 3 table headers, wide aligned three-column table admission and independent-column rejection, ToC/noise, four rotations with moved CropBox and adjacent sentinels, right-margin and header-boundary decorative-logo admission plus central/large/body-overlap/unknown-placement/same-region image blocking, bad SHA/section/rect/page/PARTIAL fence, boundary-crossing text, broken/encrypted PDFs, terminal-layout input blocking, cancellation, deadline, and no rendering.

## Verification record

Interpreter: `C:\Users\USER\AppData\Local\Programs\Python\Python313\python.exe`; PyMuPDF: 1.27.2.

| Command | Result |
| --- | --- |
| `python -m pytest tests/rebaseline -q` | 97 passed in 3.80s |
| `python -m pytest tests/test_common_normalization.py -q` | 6 passed in 0.53s |
| `python -m compileall -q src/msds golden/v2` | PASS |
| import smoke for models/pdf_io/sections | PyMuPDF 1.27.2; imports OK |

`tests/rebaseline` uses a dedicated `pdf_tmp` fixture under the worktree. Each test removes its child directory and removes the root when empty. It does not change global temp configuration, production configuration, or ignore rules.

## Field material and limits

No authorized field-sample PDF set was supplied or inspected for this phase; the evidence is synthetic-PDF-only. No original PDF or ACL was modified. Final acceptance evidence is the run above.
