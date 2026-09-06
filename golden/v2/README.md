# Golden v2

Golden v2 is a new, independently reviewed dataset; it is not copied from v1.
Each case follows `schema.json` and is checked by `validation.py` without a
third-party schema dependency.

Required lossless facts are the source SHA-256, raw product value, Section 1/3
provenance, and an *ordered list* of component rows. A component row contains
`cas_raw`/`cas_normalized`/`cas_status` and
`content_raw`/`content_normalized`/`content_status`, plus pair status, block
identity, and source evidence. List order and duplicate CAS rows are material: validators must never
convert rows into a CAS-keyed dictionary.

Section 3 represents CAS-to-content relationships only. A CAS with no stated
content is retained as `NOT_STATED`; a content-only observation creates no row.
One explicit content shared by several CAS values produces one row per CAS.
`NOT_READABLE`, `PAIR_AMBIGUOUS`, and `REVIEW` remain explicit statuses rather
than being collapsed into a missing value.

Do not promote a case until a reviewer has checked the source PDF's Section 1
and Section 3 and confirmed its SHA-256.
