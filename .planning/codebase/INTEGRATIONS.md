# External Integrations

## KOSHA (Korea Occupational Safety and Health Agency)
- **API**: `https://msds.kosha.or.kr` (implied by client logic)
- **Functions**: `get_chem_id`, `get_item_detail`
- **Auth**: Service key via `.env`

## Google Gemini API
- **Models**: Gemini 1.5/2.0 Flash
- **Usage**: Extraction verification, complex PDF parsing where regex fails.
- **Auth**: API key via `.env`

## OpenDataLoader (ODL)
- **Role**: Backend tool for PDF text and structure extraction.
- **Execution**: CLI-based integration.
