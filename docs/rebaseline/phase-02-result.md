# Phase 02 — digital PDF Section 1/3 locator and fence result

## Scope and boundary

- Implemented only the digital-PDF Section 1 / Section 3 locator, rectangular fence, and isolated `SectionInput` handoff.
- No product-name selection, CAS/content extraction or pairing was added. OCR, AI, ODL, KOSHA, and all other external calls are zero in this phase.
- The reader uses PyMuPDF 1.27.2 read-only. It does not render pages; `render_calls=0` and `external_calls=0` are reported in read metrics.

## Implemented behavior

- Header confirmation uses section number, matching Korean/English heading text, layout, and document order. Table-of-contents runs, body references, `3.1` / `3.2`, CAS-like numbers, and repeated start headers cannot become a confirmed fence.
- A missing ending header, conflicting repeated start, ambiguous multi-column same-page boundary, image-reading requirement, cancellation, or deadline produces `FENCE_PARTIAL` with a reason. Section 1 and Section 3 are located independently.
- `PageRegion` and token coordinates are zero-based and unrotated in the CropBox coordinate space. The reader derotates `Page.rect`; the builder validates SHA-256, fence identity, ordered regions, page bounds, and rectangles, then filters character tokens against actual rectangles.
- Synthetic real-PDF tests cover digital Korean/English headings, same-page and multi-page boundaries, ToC/noise, four rotations, CropBox-origin movement, image/mixed input, bad SHA/rect/page/PARTIAL fence, broken/encrypted PDFs, cancellation, deadline, and no rendering.

## Verification record

Interpreter: `C:\Users\USER\AppData\Local\Programs\Python\Python313\python.exe`; PyMuPDF: 1.27.2.

| Command | Result |
| --- | --- |
| `python -m pytest tests/rebaseline -q` | 63 passed in the sandbox; pytest cache write emitted one WinError 5 warning, with no test impact. |
| `python -m pytest tests/test_common_normalization.py -q` | 1 failed, 5 passed. Existing `tempfile.TemporaryDirectory()` outside the worktree cannot create/read/clean its trace file (`WinError 5` / `FileNotFoundError`). `normalization.py` was not modified. |
| `python -m compileall -q src/msds golden/v2` | passed |
| import smoke for models/pdf_io/sections | passed |

`tests/rebaseline` uses a dedicated `pdf_tmp` fixture under the worktree. Each test removes its child directory and removes the root when empty. It does not change global temp configuration, production configuration, or ignore rules.

## Field material and limits

No authorized field-sample PDF set was supplied or inspected for this phase; the evidence is synthetic-PDF-only. No original PDF or ACL was modified. An initial focused local run (14 passed, external calls 0) was used once to confirm the temporary-directory environmental failure, but is not final acceptance evidence. Final acceptance evidence is the sandbox run above. The sandbox's Windows temporary/cache ACL restrictions remain an environmental constraint; no ACL change was made.
