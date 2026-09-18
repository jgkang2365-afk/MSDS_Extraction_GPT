# 다형식 MSDS 일반화 가이드라인 v1

**문서 상태:** 구현 보조 가이드라인 — PRD/TRD보다 낮은 권위

이 문서는 승인된 PRD와 TRD를 해석하거나 새 자료군을 평가할 때의 보조 기준이다.
PRD의 제품 정책이나 TRD의 기술 계약과 충돌하면 이 문서는 효력이 없으며, 충돌을
보고하고 상위 문서를 따른다. 코드 주석·과거 pilot 결과·이 가이드라인은 PRD/TRD를
대체하거나 전 세계 MSDS 지원을 선언할 수 없다.

## 계층별 불변식

1. **구조적 경계:** 1항 제품명과 3항 CAS/함유량은 confirmed SectionInput 안에서만
   수집한다. 다른 항, 머리말·꼬리말, 파일명, 외부 데이터로 빈 값을 보완하지 않는다.
2. **문맥:** CAS의 어휘 정규화는 separator, shape, checksum에 한정한다. 날짜와 EC
   번호의 제외는 행·열·라벨 문맥에서 수행하며, 특정 CAS whitelist나 추정 보정은
   허용하지 않는다.
3. **어휘:** label은 지원 근거일 뿐 단독 정답 근거가 아니다. 새 언어의 label을
   추가할 때는 같은 어휘가 metadata에 쓰이는 반례와 explicit CAS field 양쪽을
   함께 검증한다.
4. **레이아웃:** 표의 CAS 열, EC 열, 단위 header, shared content 관계는 좌표와
   source row로 증명한다. 이웃 행·다른 열·다른 페이지의 값을 synthetic join하지
   않는다.
5. **fail-closed:** fence, source relation, content 의미 또는 문맥 배제가 불명확하면
   자동 확정하지 않고 후보/REVIEW로 남긴다. raw와 evidence는 보존한다.

## 현재 증거의 범위

현재 증거는 사용자 제공 `TEST_File`의 Korean digital PDF 3개를 local TEXT core로
실행한 결과뿐이다. 이는 세 파일에서의 구조·문맥 회귀를 막는 근거이지, 다국어,
모든 제조사, 모든 국가 규제 형식, 스캔 PDF 또는 OCR/AI 경로의 완전한 일반화 증거가
아니다. 외부 lookup, OCR, ODL, AI, Vercel을 사용하지 않았고 사람 review/approval도
포함하지 않는다.

## Corpus 확장 매트릭스

| 확장 축 | 최소 추가 사례 | 반드시 포함할 반례 | 통과 기준 |
| --- | --- | --- | --- |
| 언어/용어 | 언어별 최소 3개 제조사·2개 레이아웃 | 날짜·revision·prepared label, EC label, `CAS No` | raw/evidence와 예상 status를 사람이 확인하고 contract test로 고정 |
| 디지털 표 | single/multi-page, split header, shared content | 인접 행/foreign column CAS, CAS-less content | source row/column 관계 외 synthetic join 0 |
| 스캔/OCR | 해상도·회전·noise가 다른 자료군 | digit 혼동, token 누락, image/text mixed | TEXT와 같은 계약을 유지하고 불확실성은 REVIEW |
| 제조사 양식 | template family별 최소 3개 revision | header/footer 반복, logo, revision date | fence가 다른 항/장식물을 값 근거로 쓰지 않음 |
| 함유량 표기 | %, wt%, vol%, ppm, range, comparator | blank, unreadable, multiple values | raw·단위 근거·상태를 잃지 않음 |

각 matrix cell은 독립 원본 SHA-256, confirmed fence, expected machine result,
반례 결과, 회귀 테스트를 갖춰야 한다. 표본 수가 늘어나도 fail-closed 원칙을
완화하지 않으며, 성능·자동 PASS 비율·false positive/negative와 REVIEW 비율을
자료군별로 별도 보고한다.
