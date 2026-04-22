# Coding Conventions

## Naming
- **Files**: Snake case (e.g., `msds_engine_v5.py`).
- **Classes**: Pascal case (e.g., `MSDSCore`, `KoshaAPIClient`).
- **Functions/Variables**: Snake case (e.g., `clean_product_name`).

## Coding Style
- **Regex-centric**: Heavy use of compiled regex patterns for performance.
- **Defensive Programming**: Extensive try-except blocks with fallback values.
- **Logging**: Use of `log_callback` patterns for UI integration.

## UI (PyQt5)
- **Object Names**: Unique IDs for interactive elements (e.g., `btn_extract`).
- **Threading**: Use of `QThread` and `QObject` (via `ExtractionWorker`) to keep UI responsive.
