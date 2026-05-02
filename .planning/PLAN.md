# Implementation Plan: V17.3.0.0 Precision Extraction - COMPLETED

## Phase 1: Engine Core Repair (msds_engine_v5.py) - ✅ Done
- [x] Version bump to `17.3.0.0`
- [x] Refine `_normalize_single_content` for range assembly and residue filtering
- [x] Update `parse_row_robust_v2` with liberal CAS removal and backward cell scanning
- [x] Add precision test cases to `self_test_regression`

## Phase 2: Verification - ✅ Done
- [x] Run engine self-test with new cases
- [x] Verify fix for "3~98%" and "1.2%" issues
