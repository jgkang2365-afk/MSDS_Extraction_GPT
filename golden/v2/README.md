# Golden v2 approval contract

Golden v2 is an independent, review-governed corpus. It is not an import,
copy, or automatic migration path for Golden v1. This directory currently
contains only the contract and its tests: it contains no candidate, human
reviewed, or approved source-PDF case data.

## Case lifecycle and kinds

Every case has a stable `case_id`, one `case_kind`, and exactly one lifecycle
state:

```text
CANDIDATE -> HUMAN_REVIEWED -> APPROVED
```

- `VALUE_TRUTH` records a source-verified expected product and ordered Section
  3 component facts.
- `SAFE_REVIEW` records a safe quality result and one or more expected finding
  codes; it is not silently treated as a value-truth case.
- `FAILURE_BEHAVIOR` records a safe outcome (`REJECT`, `REVIEW_REQUIRED`,
  `NO_OUTPUT`, or `FENCE_BLOCKED`).

History must exactly end at the case lifecycle: CANDIDATE has only its
candidate event, HUMAN_REVIEWED has candidate then human-review events, and
APPROVED has all three events in that order. `select_approved_cases(cases)`
excludes CANDIDATE/HUMAN_REVIEWED and validates the structural approval
contract before admitting an APPROVED case; it never promotes or changes data.

## Source and approval requirements

Cases carry a portable source reference only:

```json
"source": {
  "source_root": "reviewed-pdfs",
  "relative_path": "supplier/example.pdf"
}
```

Absolute paths, extra source-path fields, backslashes, and parent traversal are invalid. The source
SHA-256 is kept in `source_sha256`. A local caller can provide
`validate_dataset(cases, source_roots={"reviewed-pdfs": local_directory})`.
For an APPROVED case, the portable reference must end in `.pdf`, the local file
must start with the `%PDF-` signature, and its SHA-256 must match. An
unavailable file or mismatch is an error.
For CANDIDATE or HUMAN_REVIEWED it is a non-mutating blocker finding, so a
portable review record does not fabricate a local path.

An APPROVED case must contain ordered `HUMAN_REVIEWED` and `APPROVED` history
events. Each of those events records `reviewer_ref` (a non-PII reference is
enough), timezone-bearing timestamp, `DIRECT_SOURCE_PDF_REVIEW`, direct PDF
confirmation, and explicit Section 1 and Section 3 confirmation. `reason` is
optional. The contract never records an agent decision as human-reviewed or
approved.

## Lossless value contract

`product` retains `raw`, `normalized`, `status`, and `provenance`.
`section_provenance` retains both Section 1 and Section 3 evidence. Components
are an ordered list, never a CAS-keyed object: duplicate CAS observations and
their order are material.

Each component retains CAS raw/normalized/status/evidence; content
raw/normalized/status/evidence; `unit_context_raw` and its evidence; pair
status; `block_id`; source relation; and pair evidence. A header-derived unit
keeps the bare raw value unchanged (for example raw `"10"`, context `"%"`). A
direct `"10%"`, `"500 ppm"`, `"500ppm"`, `"10 wt%"`, `"10wt%"`, `"10 vol%"`,
or `"20vol%"` has no header unit context. `NOT_STATED`, `NOT_READABLE`, and `PAIR_AMBIGUOUS` remain distinct.
When `content_status` or `pair_status` is `PAIR_AMBIGUOUS`, final content raw
and normalized values must be empty strings; a synthetic joined value is
prohibited. Candidate raw values belong in evidence, transcription, or finding
structures instead. A non-null header unit context requires non-empty context
evidence; direct-unit raw values retain null context and empty context evidence.

`source_transcription` is a separate, lossless human source notation, never an
automatically generated OCR `raw_reading`. APPROVED transcription records
`transcription_method: HUMAN_DIRECT_SOURCE_PDF_REVIEW` and direct-PDF
confirmation. Its ordered rows must correspond 1:1 in source order to component
`block_id`, CAS raw, content raw, and source locator evidence. At APPROVED, all
product, Section 1/3, CAS, content, row, and transcription evidence is a
meaningful human-source object: `provenance_type:
HUMAN_DIRECT_SOURCE_PDF_REVIEW` and a non-negative `page`. Empty objects,
`null`, and OCR-only `raw_reading` evidence are not provenance. These promotion
requirements do not require a CANDIDATE or HUMAN_REVIEWED case to carry a
transcription.

Evidence `page` values are JSON integers (not booleans), and source-relation
IDs are strings or `null`. Transcription/component correspondence preserves
ordered locator identity: provenance, page, and any supplied `bbox` or
`region` must match. Review notes and other non-locator annotations may differ.

`schema.json` enforces local JSON shape and locally expressible APPROVED
promotion gates: direct human confirmation and method, non-empty human source
evidence, transcription-row field types, and a non-empty transcription row list
when components exist. Its approved human-evidence schema explicitly excludes
OCR `raw_reading`, while leaving valid locator fields (`page`, `bbox`, `region`)
and reviewer annotations available. Draft 2020-12 cannot express arbitrary
cross-array equality, including exact ordered row coverage and raw-value or
locator matching between `source_transcription.component_rows` and
`components`. `validate_case`/`validate_dataset` deliberately remain
authoritative for that semantic cross-row relation; this is not a schema/Python
equivalence claim beyond schema-expressible constraints.

## Review template

Use this template only after a qualified human has directly reviewed the local
source PDF; do not create an APPROVED record from automated extraction:

```json
{
  "action": "HUMAN_REVIEWED",
  "status": "HUMAN_REVIEWED",
  "reviewer_ref": "review-ticket-or-role-reference",
  "timestamp": "2026-09-09T10:30:00+09:00",
  "review_method": "DIRECT_SOURCE_PDF_REVIEW",
  "source_pdf_directly_confirmed": true,
  "section_1_confirmed": true,
  "section_3_confirmed": true,
  "reason": "optional correction or review context"
}
```

Before promotion, verify the source-root mapping, PDF signature/SHA-256,
source transcription, product raw and provenance, every ordered
component/duplicate/shared-content relation, and the required history fields.
`schema.json` declares the local JSON shape; `validation.py` implements the
authoritative semantic cross-row relation as well as dependency-free real-
timestamp, lifecycle, source-file, transcription, and dataset checks without
mutating supplied JSON-compatible inputs. SAFE_REVIEW
requires `quality_status: REVIEW_REQUIRED` and non-empty finding codes; PASS is
not a safe-review expectation.
