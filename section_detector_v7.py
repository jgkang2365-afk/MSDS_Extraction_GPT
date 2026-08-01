"""GHS SDS Section 1/3 탐지 전용 계층.

원문은 보존하고 제목 비교에만 NFKC/공백/구분자 정규화를 적용한다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import re
import unicodedata


class SectionConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SectionRange:
    section: int
    start: int = -1
    end: int = -1
    page_start: int = -1
    page_end: int = -1
    title: str = ""
    confidence: SectionConfidence = SectionConfidence.FAILED
    score: float = 0.0
    end_reason: str = "not_found"
    toc_rejected: bool = False

    @property
    def found(self) -> bool:
        return self.start >= 0 and self.end > self.start

    @property
    def usable(self) -> bool:
        return self.found and self.confidence in {
            SectionConfidence.HIGH,
            SectionConfidence.MEDIUM,
        }

    def to_dict(self) -> dict:
        data = asdict(self)
        data["confidence"] = self.confidence.value
        data["found"] = self.found
        data["usable"] = self.usable
        return data


SECTION1_TITLES = (
    "화학제품과회사에관한정보", "화학제품과회사에대한정보", "제품및회사에관한정보",
    "제품과회사에관한정보", "화학물질및제조자정보", "화학물질과회사에관한정보",
    "identificationofthesubstancemixtureandofthecompanyundertaking",
    "identificationofthesubstanceormixtureandofthesupplier",
    "chemicalproductandcompanyidentification", "productandcompanyidentification",
    "substancemixtureandcompanyidentification", "productidentification",
)
SECTION1_SHORT = ("identification", "productidentifier")
SECTION1_LABELS = (
    "제품명", "제품의명칭", "화학제품명", "상품명", "물질명", "제품식별자", "제품코드", "품명",
    "productname", "productidentifier", "tradename", "commercialproductname", "materialname",
    "chemicalname", "substancename", "productcode", "productnumber", "sdsproductname",
)
COMPANY_LABELS = ("회사", "공급자", "제조자", "주소", "company", "supplier", "manufacturer", "address")

SECTION3_TITLES = (
    "구성성분의명칭및함유량", "구성성분및함유량", "구성성분의명칭과함유량",
    "구성성분에관한정보", "성분및함유량", "조성및성분정보", "조성성분정보",
    "compositioninformationoningredients", "compositionandinformationoningredients",
    "compositionandingredientinformation", "compositioninformation", "ingredientsinformation",
    "informationoningredients", "compositionofingredients", "chemicalcomposition",
    "chemicalcompositionandingredientinformation", "compositioninformationofingredients",
)
SECTION3_WEAK = (
    "ingredients", "composition", "components", "hazardousingredients",
    "hazardouscomponents", "ingredientdisclosure", "substances", "mixtures",
)
NAME_COLUMNS = (
    "화학물질명", "성분명", "물질명", "관용명", "이명", "chemicalname", "ingredientname",
    "commonname", "synonym", "component", "substance",
)
CAS_COLUMNS = ("cas번호", "casno", "casnumber", "casrn", "casregistrynumber", "식별번호")
CONTENT_COLUMNS = (
    "함유량", "함량", "농도", "농도범위", "concentration", "concentrationrange", "content",
    "content%", "weight%", "%byweight", "wt%", "percentage", "exactpercentage",
)

SECTION_END_TITLES = {
    1: ("유해성위험성", "위험유해성", "hazardsidentification", "hazardidentification"),
    3: ("응급조치요령", "응급조치에관한사항", "응급처치요령", "firstaidmeasures", "firstaid", "emergencyandfirstaidprocedures"),
}
MAX_SECTION_CHARS = {1: 1800, 3: 7000}
MIN_SECTION_CHARS = {1: 30, 3: 45}


def normalize_detection_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = re.sub(r"[\t\r\n]+", " ", text)
    text = re.sub(r"[/／:：·•\-–—_()（）\[\].,]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", normalize_detection_text(value))


def _section_number(line: str, number: int) -> bool:
    normalized = normalize_detection_text(line)
    roman = "i" if number == 1 else "iii" if number == 3 else str(number)
    patterns = (
        rf"(?:^|\s)section\s*(?:{number}|{roman})(?:\s|$)",
        rf"^\s*{number}\s*(?:[.:항]|\s)",
        rf"^\s*제\s*{number}\s*항",
        rf"^\s*항\s*{number}(?:\s|[.:]|$)",
        rf"^\s*{roman}\s*(?:[.:]|\s)",
    )
    return any(re.search(pattern, normalized, re.I) for pattern in patterns)


def _next_numbered_section(line: str, after: int) -> bool:
    raw = unicodedata.normalize("NFKC", str(line or "")).casefold().strip()
    match = re.search(
        r"^(?:(?:section|항)\s*)?(\d{1,2})\s*(?:[.:항]|$)", raw, re.I
    )
    return bool(match and after < int(match.group(1)) <= 16)


def _contains_any(text: str, values: tuple[str, ...]) -> bool:
    compact = _compact(text)
    return any(value in compact for value in values)


class SectionDetectorV7:
    """제목·번호·내부 필드·다음 Section을 함께 평가한다."""

    def detect(self, text: str, section: int) -> SectionRange:
        original = str(text or "")
        if not original.strip() or section not in (1, 3):
            return SectionRange(section=section)

        lines = []
        for match in re.finditer(r"[^\r\n]+", original):
            raw = match.group(0).strip()
            if raw:
                lines.append((match.start(), match.end(), raw))

        candidates = []
        for index, (start, _line_end, raw) in enumerate(lines):
            compact = _compact(raw)
            numbered = _section_number(raw, section)
            if section == 1:
                strong = any(title in compact for title in SECTION1_TITLES)
                weak = any(title == compact or title in compact for title in SECTION1_SHORT)
            else:
                strong = any(title in compact for title in SECTION3_TITLES)
                weak = any(title == compact or title in compact for title in SECTION3_WEAK)
            if not strong and not weak:
                continue

            nearby = "\n".join(item[2] for item in lines[index + 1:index + 14])
            nearby_compact = _compact(nearby)
            if section == 1:
                internal_count = int(any(v in nearby_compact for v in SECTION1_LABELS))
                internal_count += int(any(v in nearby_compact for v in COMPANY_LABELS))
            else:
                internal_count = sum(
                    any(value in nearby_compact for value in group)
                    for group in (NAME_COLUMNS, CAS_COLUMNS, CONTENT_COLUMNS)
                )

            end_number = 2 if section == 1 else 4
            next_heading = any(
                _section_number(item[2], end_number)
                and _contains_any(item[2], SECTION_END_TITLES[section])
                for item in lines[index + 1:index + 35]
            )
            heading_burst = sum(
                bool(re.search(r"^(?:section\s*)?\d{1,2}\s*(?:[.:항]|\s)", normalize_detection_text(item[2])))
                for item in lines[max(0, index - 2):index + 12]
            )
            toc_like = heading_burst >= 5 and internal_count == 0

            if strong and numbered:
                score = 0.92
            elif strong and (internal_count >= 1 or next_heading):
                score = 0.74
            elif section == 3 and weak and numbered and internal_count >= 2:
                score = 0.68
            elif section == 1 and weak and start < max(1200, len(original) // 4) and internal_count >= 2:
                score = 0.63
            else:
                score = 0.35
            score += min(internal_count, 3) * 0.04 + (0.03 if next_heading else 0.0)
            if toc_like:
                score -= 0.45
            candidates.append((score, start, index, raw, toc_like))

        viable = [item for item in candidates if item[0] >= 0.55 and not item[4]]
        if not viable:
            return SectionRange(
                section=section,
                confidence=SectionConfidence.LOW if candidates else SectionConfidence.FAILED,
                score=max((item[0] for item in candidates), default=0.0),
                toc_rejected=any(item[4] for item in candidates),
            )

        score, start, line_index, title, _ = max(viable, key=lambda item: (item[0], item[1]))
        end = -1
        end_reason = "not_found"
        end_number = 2 if section == 1 else 4
        for _idx, (line_start, _line_end, raw) in enumerate(lines[line_index + 1:], line_index + 1):
            if _section_number(raw, end_number) and _contains_any(raw, SECTION_END_TITLES[section]):
                end, end_reason = line_start, f"section_{end_number}"
                break
        if end < 0:
            for line_start, _line_end, raw in lines[line_index + 1:]:
                if _next_numbered_section(raw, section):
                    end, end_reason = line_start, "next_numbered_section"
                    break
        if end < 0:
            end = min(len(original), start + MAX_SECTION_CHARS[section])
            end_reason = "max_chars"

        if end - start < MIN_SECTION_CHARS[section]:
            return SectionRange(section=section, title=title, score=score, confidence=SectionConfidence.LOW)

        confidence = SectionConfidence.HIGH if score >= 0.9 else SectionConfidence.MEDIUM
        page_start = original.count("\f", 0, start)
        page_end = original.count("\f", 0, max(start, end - 1))
        return SectionRange(
            section=section,
            start=start,
            end=end,
            page_start=page_start,
            page_end=page_end,
            title=title,
            confidence=confidence,
            score=min(score, 1.0),
            end_reason=end_reason,
        )

    def extract(self, text: str, detected: SectionRange) -> str:
        if not detected.usable:
            return ""
        return str(text or "")[detected.start:detected.end].strip()

    def detect_document(self, page_texts: list[str]) -> tuple[str, dict[int, SectionRange]]:
        document_text = "\f".join(str(value or "") for value in page_texts)
        return document_text, {
            1: self.detect(document_text, 1),
            3: self.detect(document_text, 3),
        }
