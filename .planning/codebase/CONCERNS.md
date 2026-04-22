# Project Concerns & Technical Debt

## High Priority
- **Dependency Merging**: Files from two different versions (v24 and GUI integrated) have been merged. Potential import conflicts (e.g., `msds_engine_v5` vs `v6/v7`).
- **Path Issues**: Hardcoded paths or relative path assumptions after moving files.
- **API Rate Limiting**: 429 errors from Gemini/KOSHA APIs (need robust backoff).

## Technical Debt
- **Version Proliferation**: Multiple versions of engines (`v5`, `v6`, `v7`) and utils (`v3`) existing simultaneously.
- **Error Handling**: Some API failures might not be gracefully handled in the UI, causing hangs.
- **Large Files**: `smu_gui.py` is very large (~156KB), making it hard to maintain.
