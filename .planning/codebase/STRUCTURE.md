# Project Structure

## Root Directory
- **smu_gui.py**: Main application entry point and UI logic.
- **msds_core.py**: Central orchestrator for extraction and validation.
- **msds_engine_v5.py**: Regex-based extraction engine (Stable version).
- **kosha_client.py**: KOSHA Open API client implementation.
- **msds_utils_v3.py**: Shared utility functions (CAS validation, cleaning).
- **exposure_lookup.py**: Local lookup for chemical exposure limits.
- **patterns.json**: Configuration for regex extraction patterns.

## Data & Configuration
- **MES_MASTER_LOOKUP.json**: Master lookup data.
- **matching_history.json**: Historical matching results.
- **substance_whitelist.json**: Whitelist of chemical substances.
- **msds_knowledge.db**: Persistent knowledge storage.

## Subdirectories
- **opendataloader/**: PDF processing tools and dependencies.
- **Docs/**: Documentation and reference materials.
- **SUM_GUI 관련자료/**: GUI related assets and resources.
- **temp_odl/**: Temporary directory for ODL processing.
