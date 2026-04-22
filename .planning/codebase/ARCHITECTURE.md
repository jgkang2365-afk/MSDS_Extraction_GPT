# System Architecture

## Overview
The system is a hybrid MSDS (Material Safety Data Sheet) extraction and validation platform. It combines traditional regex-based parsing with modern AI verification.

## Core Flow
1. **User Input**: PDF files are loaded via `smu_gui.py`.
2. **Extraction Engine**: 
   - **Regex Tier (v5)**: Uses `msds_engine_v5.py` and `patterns.json` for fast, local extraction.
   - **AI Tier (v6/v7)**: Uses Gemini API for complex reasoning and verification of results.
3. **Validation**: 
   - **CAS Check**: Validates CAS numbers using checksums (`msds_utils_v3.py`).
   - **KOSHA Sync**: Looks up official data via `kosha_client.py`.
   - **Regulation Mapping**: Maps extracted data to local exposure limits (`exposure_lookup.py`).
4. **Data Management**: Results are cached and stored for consistency and performance.

## Hybrid Approach
- **Green (🟢)**: Confirmed by both regex and AI/KOSHA.
- **Yellow (🟡)**: Partially verified or inferred.
- **Red (🔴)**: Integrity failure, requires manual review.
