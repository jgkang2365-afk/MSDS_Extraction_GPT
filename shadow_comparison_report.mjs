import fs from "node:fs/promises";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { SpreadsheetFile, Workbook } = require("@oai/artifact-tool");

const [, , inputPath, outputPath, verifyDir] = process.argv;
if (!inputPath || !outputPath) throw new Error("input/output path required");
const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
const results = payload.results || [];
const summary = payload.summary || {};
const workbook = Workbook.create();

const headerFormat = { fill: "#1F4E78", font: { bold: true, color: "#FFFFFF" } };
const titleFormat = { fill: "#D9EAF7", font: { bold: true, color: "#17365D", size: 14 } };
const borderFormat = { borders: { top: { style: "continuous", color: "#B4C6E7" }, bottom: { style: "continuous", color: "#B4C6E7" }, left: { style: "continuous", color: "#B4C6E7" }, right: { style: "continuous", color: "#B4C6E7" } } };

function writeTable(sheet, startRow, headers, rows) {
  const endCol = String.fromCharCode(64 + headers.length);
  sheet.getRange(`A${startRow}:${endCol}${startRow}`).values = [headers];
  sheet.getRange(`A${startRow}:${endCol}${startRow}`).format = headerFormat;
  if (rows.length) {
    sheet.getRange(`A${startRow + 1}:${endCol}${startRow + rows.length}`).values = rows;
    sheet.getRange(`A${startRow}:${endCol}${startRow + rows.length}`).format.wrapText = true;
    sheet.getRange(`A${startRow}:${endCol}${startRow + rows.length}`).format = borderFormat;
  }
  sheet.getRange(`A${startRow}:${endCol}${Math.max(startRow, startRow + rows.length)}`).format.autofitColumns();
  sheet.getRange(`A${startRow}:${endCol}${Math.max(startRow, startRow + rows.length)}`).format.autofitRows();
}

const summarySheet = workbook.worksheets.add("요약");
summarySheet.getRange("A1:B1").merge();
summarySheet.getRange("A1").values = [["V6/V7 백그라운드 비교 요약"]];
summarySheet.getRange("A1:B1").format = titleFormat;
const summaryRows = [
  ["전체 문서", summary.total_documents || 0], ["동일", summary.same || 0],
  ["차이", summary.different || 0], ["부분 비교", summary.partial_comparison || 0],
  ["비교 실패", summary.comparison_failed || 0], ["V7 개선 추정", summary.v7_improvement_candidate || 0],
  ["V7 오류 가능", summary.v7_error_candidate || 0], ["수동 확인 필요", summary.manual_review_required || 0],
  ["중복 OCR 호출", summary.duplicate_ocr_calls || 0], ["중복 AI 호출", summary.duplicate_ai_calls || 0],
];
writeTable(summarySheet, 3, ["항목", "건수"], summaryRows);

const docSheet = workbook.worksheets.add("문서별 비교");
const docHeaders = ["문서명", "판정", "비교 수준", "제품명 V6", "제품명 V7", "성분 수 V6", "성분 수 V7", "추가", "제거", "함유량 변경", "Section 1", "Section 3", "V7 fallback", "차이 요약"];
const docRows = results.filter(r => r.comparison_status !== "SAME" || r.comparison_completeness !== "FULL").map(r => [
  r.file_name || "", r.auto_judgment || "", r.comparison_completeness || "", r.v6_product_name || "", r.v7_product_name || "",
  r.v6_component_count || 0, r.v7_component_count || 0, (r.added_in_v7 || []).length, (r.removed_in_v7 || []).length,
  (r.changed_in_v7 || []).filter(d => (d.status || "").includes("함유량 변경")).length,
  (r.section_1_meta || {}).confidence || "", (r.section_3_meta || {}).confidence || "", r.v7_fallback_used ? "예" : "아니오", r.difference_summary || "",
]);
writeTable(docSheet, 1, docHeaders, docRows);

const detailSheet = workbook.worksheets.add("성분 상세 비교");
const detailRows = [];
for (const r of results) {
  for (const d of [...(r.added_in_v7 || []), ...(r.removed_in_v7 || []), ...(r.changed_in_v7 || []), ...(r.unchanged_components || [])]) {
    detailRows.push([r.file_name || "", d.cas || "", d.v6_name || "", d.v7_name || "", d.v6_content || "", d.v7_content || "", d.status || "", d.reason_code || "", d.reason_text || ""]);
  }
}
writeTable(detailSheet, 1, ["파일명", "CAS", "성분명 V6", "성분명 V7", "함유량 V6", "함유량 V7", "상태", "reason_code", "reason_text"], detailRows);

const partialSheet = workbook.worksheets.add("부분 비교·실패");
const partialRows = results.filter(r => r.comparison_completeness !== "FULL").map(r => [r.file_name || "", r.comparison_completeness || "", r.limitation_reason || r.auto_judgment_reason || "", r.v6_result_saved === false ? "아니오" : "예", r.error || ""]);
writeTable(partialSheet, 1, ["파일명", "비교 수준", "실패 또는 제한 사유", "V6 결과 정상 저장", "오류 메시지"], partialRows);

if (verifyDir) {
  await fs.mkdir(verifyDir, { recursive: true });
  const inspection = await workbook.inspect({ kind: "workbook,sheet,table", maxChars: 8000, tableMaxRows: 8, tableMaxCols: 16 });
  await fs.writeFile(`${verifyDir}/inspection.txt`, inspection.ndjson || String(inspection), "utf8");
  for (const sheetName of ["요약", "문서별 비교", "성분 상세 비교", "부분 비교·실패"]) {
    const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
    await fs.writeFile(`${verifyDir}/${sheetName}.png`, new Uint8Array(await preview.arrayBuffer()));
  }
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
