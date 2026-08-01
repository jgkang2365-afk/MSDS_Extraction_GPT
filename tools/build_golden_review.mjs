import fs from "node:fs/promises";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { SpreadsheetFile, Workbook } = require("@oai/artifact-tool");
const [, , inputPath, outputPath, verifyDir] = process.argv;
if (!inputPath || !outputPath) throw new Error("input/output path required");
const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const columns = payload.columns || [];
const rows = payload.rows || [];
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("골든 분류 검토");
sheet.showGridLines = false;
const matrix = [columns, ...rows.map(row => columns.map(column => row[column] ?? ""))];
const endColumn = (() => {
  let value = columns.length;
  let output = "";
  while (value > 0) { value -= 1; output = String.fromCharCode(65 + (value % 26)) + output; value = Math.floor(value / 26); }
  return output;
})();
sheet.getRange(`A1:${endColumn}${matrix.length}`).values = matrix;
sheet.getRange(`A1:${endColumn}1`).format = { fill: "#1F4E78", font: { bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center" };
sheet.getRange(`A2:${endColumn}${matrix.length}`).format = { wrapText: true, verticalAlignment: "top" };
sheet.freezePanes.freezeRows(1);
const table = sheet.tables.add(`A1:${endColumn}${matrix.length}`, true, "GoldenClassificationReview");
table.style = "TableStyleMedium2";
table.showFilterButton = true;
const reviewIndex = columns.indexOf("검토 필요 여부");
const tierIndex = columns.indexOf("regression_tier");
const approvalIndex = columns.indexOf("사용자 승인 상태");
for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
  const excelRow = rowIndex + 2;
  if (rows[rowIndex]["검토 필요 여부"] === "예") sheet.getRange(`A${excelRow}:${endColumn}${excelRow}`).format.fill = "#FFF2CC";
  if (rows[rowIndex].regression_tier === "core") sheet.getCell(rowIndex + 1, tierIndex).format = { fill: "#DDEBF7", font: { bold: true, color: "#1F4E78" } };
}
if (approvalIndex >= 0 && rows.length) sheet.getRangeByIndexes(1, approvalIndex, rows.length, 1).dataValidation = { rule: { type: "list", values: ["", "승인", "보류", "수정 필요"] } };
const widths = [9, 44, 12, 15, 10, 20, 12, 15, 15, 12, 15, 9, 24, 24, 34, 24, 15, 12, 14, 42, 30, 16];
widths.forEach((width, index) => { sheet.getRangeByIndexes(0, index, matrix.length, 1).format.columnWidth = width; });
sheet.getRange("A1:A1").format.rowHeight = 34;
if (verifyDir) {
  await fs.mkdir(verifyDir, { recursive: true });
  const inspection = await workbook.inspect({ kind: "workbook,sheet,table", maxChars: 6000, tableMaxRows: 8, tableMaxCols: 22 });
  await fs.writeFile(`${verifyDir}/inspection.txt`, inspection.ndjson || String(inspection), "utf8");
  const preview = await workbook.render({ sheetName: "골든 분류 검토", range: `A1:${endColumn}${Math.min(matrix.length, 18)}`, scale: 1, format: "png" });
  await fs.writeFile(`${verifyDir}/golden-review.png`, new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
