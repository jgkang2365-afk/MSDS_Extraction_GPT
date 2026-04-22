# TRD: v3_하이브리드 기술 설계서

## 1. 시스템 아키텍처: [수집(Python) -> 추론(LLM) -> 검증(Python)]
### Context Aggregator
- `fitz.get_text("dict")`를 통해 텍스트의 절대 좌표를 추출하고, 이를 기반으로 LLM이 이해하기 쉬운 '시각적 텍스트 맵'을 생성합니다.

### Confidence Engine
- 다음 항목을 체크하여 최종 태그를 결정합니다.
  - **CAS 체크디지트 유효성**: (Pass/Fail)
  - **함유량 수치 타당성**: (0 < Value <= 100)
  - **제품명 내 금지어**: (예: '제품명', '목차') 포함 여부

## 2. GUI 로그 인터페이스 규격
| 항목 | 내용 |
| :--- | :--- |
| **태그** | [PASS] (녹색) / [REVIEW] (황색/적색) |
| **추출 근거** | Ollama가 정답을 선택한 논리적 이유 (한글) |
| **검증 결과** | `utils` 함수 통과 여부 및 오류 원인 메시지 |

## 3. 새로고침(Hot-Reload) 로직
- `importlib.reload()`를 사용하여 `msds_engine_v3` 모듈을 동적으로 재로드하고, `json.load()`를 통해 `patterns.json`의 변경사항을 실시간으로 반영합니다.
