# Testing Strategy

## Manual Testing
- **GUI Verification**: Running `smu_gui.py` and checking PDF rendering and table output.
- **Extraction Check**: Comparing extracted values with actual PDF content.

## Automated Testing
- **Unit Tests**: `test_v5.py` (basic engine tests).
- **Validation Tests**: CAS checksum tests in `msds_utils_v3.py`.

## Verification Loop
- Integration of `log_callback` allows for real-time monitoring of the extraction process.
