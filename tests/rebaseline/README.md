# Re-baselining tests

Tests for the new pipeline are grouped by purpose rather than by implementation class:

1. Fast contract/regression tests: normalization, resolver, validator, persistence, saved fixtures.
2. Real document/integration tests: real PDFs and only the OCR/ODL/AI/KOSHA paths relevant to the change.
3. Business acceptance/final evaluation: GUI/Excel, restart/correction, delayed enrichment, recovery, and held-out field samples.

Passing mocks must not be reported as OCR/AI accuracy evidence.
