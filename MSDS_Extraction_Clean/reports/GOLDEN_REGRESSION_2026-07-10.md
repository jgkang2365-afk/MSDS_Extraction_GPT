# Golden Regression Report — 2026-07-10

## Current result

- Approved dataset integrity: **13/13**
- Production extraction after environment recovery: **9/13**
- Passing cases: 005, 008, 010, 020, 022, 035, 036, 043, 046
- Remaining cases: 015, 032, 040, 047

The first full run was 7/13 because scanned cases 005 and 046 could not
construct PPStructureV3. Installing the PaddleX OCR extra and pinning
paddlepaddle==3.2.2 fixed both scanned cases. PaddlePaddle 3.3.1 was affected
by the known CPU oneDNN/PIR conversion regression.

## Remaining regression evidence

### 015 — concatenated false CAS

- Expected: 12 CAS rows.
- Actual: the same 12 rows plus 9884696-21-9(미기재%).
- ODL returns the correct 84696-21-9(54.98%).
- Density clustering joins a preceding 98 token to the real CAS and emits
  9884696-21-9.
- The current merge accepts the density-only candidate even though it is a
  longer suffix-overlap of an already grounded ODL CAS.

Proposed guard: when a density-only CAS has no content and its string ends with
an existing, shorter ODL CAS, discard the longer concatenated candidate.

### 032 — correct ODL range lost in the production path

- Expected: 7697-37-2(70~75%).
- Actual: 7697-37-2(75%).
- Raw table content is >= 70 - < 75 %.
- Direct ODL diagnostics return the correct 70~75%.
- Density clustering returns only 75%.
- The production result therefore demonstrates that the weaker density value
  can still become final despite the correct ODL value being available.

Proposed guard: centralize source arbitration and explicitly rank a grounded
ODL range above a density single-value candidate for the same CAS.

### 040 — concentration header routed to classification column

- Expected Methanol: 67-56-1(45~50%).
- Actual: 67-56-1(0.2~0.3%).
- The header is Component | Classification | Concentration.
- Header detection recognizes conc only at table level, but the column
  selection condition does not recognize Concentration.
- Scanning continues into the data row and selects the Classification cell
  because that cell contains concentration-limit percentages.

Proposed guard: recognize concentration/conc in the header cell itself and
stop header inference after the true header row. The explicit concentration
column must outrank percentages embedded in classification text.

### 047 — multiple CAS and ranges collapsed

- Expected five ordered ranges: 1~10, 25~35, 1~5, 5~15, 45~55.
- Actual: all five CAS rows receive 2~2%.
- ODL provides five CAS values and five ranges in one logical row.
- The current parser normalizes the whole range cell as one value and does not
  map multiple ranges to multiple CAS values.
- A hyphenated name token (2-Propanol) is then accepted as a weak numeric
  range and replicated to every CAS.
- Density clustering already returns all five correct ordered mappings.

Proposed guards:

1. Treat symbolic/range cells as strong content candidates.
2. Parse all concentration tokens from a priority cell.
3. Zip them to CAS values when the counts match.
4. Reject numeric candidates extracted from cells containing chemical-name
   text such as 2-Propanol.
5. Prefer the density mapping when ODL collapses a multi-CAS row to one
   repeated value and density provides distinct grounded ranges.

## Required verification after approval

1. Add focused offline tests for all four failure shapes.
2. Apply the minimal engine changes.
3. Run the existing 14 offline engine checks.
4. Run the 13-file approved golden suite.
5. Accept the change only at **13/13**.
