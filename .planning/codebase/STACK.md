# Stack Information

## Language
- Python 3.x

## UI Framework
- PyQt5 (Main GUI: `smu_gui.py`)

## Core Libraries
- **requests**: API communication (`kosha_client.py`)
- **re**: Regex-based extraction (`msds_engine_v5.py`, `msds_utils_v3.py`)
- **json**: Data storage and configuration (`patterns.json`, `smu_cache.json`)
- **sqlite3**: Knowledge base storage (`msds_knowledge.db`)
- **hashlib**: File integrity checking (`msds_core.py`)

## External APIs
- **KOSHA Open API**: Chemical substance database and regulation lookup
- **Google Gemini API**: AI-powered extraction and verification (integrated in v6/v7 engines)

## Data Storage
- **Local JSON**: `patterns.json`, `matching_history.json`, `smu_cache.json`
- **CSV**: Regulation data lookup (`화학물질 노출기준_고시자료.csv`)
- **SQLite**: Persistence layer (`msds_knowledge.db`)
