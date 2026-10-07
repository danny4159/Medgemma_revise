# 요약

- **핵심 결과:** 자료·기술 검사에서 문제가 확인돼 본학습 전에 중단했습니다.
- **근거:** 기존 시간 비교 규칙이 `degenerative changes` 같은 현재 소견도 제거합니다. 초기 GPU 검사는 19개 중 14개 통과했습니다.
- **미검증·주의:** 결정적 실행에서는 R/G의 λ=0 loss·gradient·update가 일치했지만, 입력 길이를 바꾼 대조와 나머지 필수 검증은 미해결입니다. 연구 가설의 음성 결과가 아닙니다.
- **다음:** 같은 R/G 질문을 유지하며 자료 규칙과 수치 검증 조건을 보완한 뒤 학습을 진행해야 합니다.

# Work Performed

- 계획·관련 리뷰·선별 반입 조건을 확인했습니다.
- T512/V64/E128 ID를 사전 선택하고 D8만 추출했습니다.
- D8 영상 8장을 실제 표시해 문장·box 연결을 점검했습니다.
- 공통 report CE와 선택적 grounding CE를 구현하고 실제 MedGemma 1.5로 검사했습니다.
- 실패 기록을 보존하고 결정적 backend에서 수치 대조를 추가했습니다.

# Files Changed

신규 소스:

- [report89_data.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/report89_data.py)
- [report89_model.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/report89_model.py)
- [report89_tech.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/report89_tech.py)
- [report89_numeric.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/report89_numeric.py)
- [report89_audit.py](/SSD1_1TB/home/milab/daniel/08_medgemma/research/report89_audit.py)

반입된 기존 파일 9개는 수정하지 않았습니다. 과거 결과·기본 환경·캐시도 변경하지 않았으며 Git 변경 작업은 수행하지 않았습니다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

| 명령 | 결과 |
|---|---|
| `python report89_data.py reuse` | blob·import 검사 통과 |
| `python report89_data.py select` | 표본 ID 저장 |
| `python report89_data.py extract --subset D8` | 8명 추출 |
| `python report89_tech.py --gpu 1 --out results/iter_089/tech/a1` | exit 2, 기술 검사 실패 |
| `python report89_audit.py` | 감사 완료, `data_gate_pass=false` |
| `python report89_numeric.py --gpu 1 --out results/iter_089/tech/numeric_control` | 결정적 동일 shape 대조 통과 |
| 신규 5개 소스의 `python -m py_compile` | 통과 |

# Results (수치와 결과 파일 경로)

**자료 검사**

- T512: 위치 정답 보유 비정상 303명, 비정상·위치 정답 없음 27명, 비정상 표기 없음 182명.
- T/V에서 progression이 없으면서 `changes` 계열 정규식으로 제외된 문장: **78+10=88개**.
- 직접 대조한 퇴행성·만성 상태 문장에서는 실제 오제외를 확인했습니다. 88개 전체를 오제외로 판정한 것은 아닙니다.
- 한 사례에서는 spondylosis 문장이 제거돼 `No other significant radiological findings.`만 target으로 남았습니다.

근거: [temporal_audit.json](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_089/data/temporal_audit.json)

**GPU 검사**

- 초기 검사: **14/19 통과**.
- 공식 forward 대비 report/grounding CE 최대 차이: **3.58×10⁻⁷**.
- 같은 길이에서 미래 token 변경 또는 미래 attention 차단: 첫 판독 logits 차이 **0**.
- 결정적 R/G λ=0 대조: loss·gradient 차이 **0**, adapter·optimizer·RNG 일치.
- 짧은 입력 대 다중 턴 입력의 수치 차이는 남았습니다. 최초 실패를 통과로 재분류하지 않았습니다.
- 초기 peak allocated/reserved: **13.82/14.19GiB**. GPU 작업은 모두 종료됐습니다.

근거: [초기 검사](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_089/tech/a1/result.json), [수치 대조](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_089/tech/numeric_control/result.json)

본학습 update **0**, 기술 검사용 optimizer step **2**, 신규 판독 생성 **0**입니다. E 영상 추출·reference 작성·평가는 미실행입니다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

iter_048의 반입 파일 **9/9**, 기존 의존 파일 **8/8**의 blob 일치를 확인했습니다. metadata reader, processor, LoRA, 좌표 변환과 결정적 실행 helper를 재사용했습니다.

위치 학습의 판독 효과는 아직 판단할 수 없습니다. 이번에는 학습 전에 target 누락 문제를 발견했고, 동일 shape의 미래 정보 비간섭과 λ=0 동등성을 확인했습니다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 실험 진입을 막는 문제:** 기존 temporal 규칙의 현재 소견 오제외. 입력 길이 변경 대조도 기술 기준 미달입니다.
- **재사용 전 필수 검증:** 중간·epoch 경계 재개, validation 상태 보존, 전체 pixel 중복, 처리량 비교, 생성기 provenance·재개 검사.
- **추후 개선:** 원 metadata의 위치 표현과 box 불일치 등 annotation 불확실성. 임의 교정하지 않았습니다.

전체 상태와 산출물 digest는 [execution_status.json](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_089/execution_status.json)에 보존했습니다.

# Recommendation to GPT

같은 연구 질문을 유지하면서 **명시적 시간 비교와 현재 상태 표현을 구분하도록 자료 규칙을 보완**하십시오. 원 selection은 보존하고 새 manifest에서 재검증해야 합니다. 동일 shape의 비간섭 통과와 길이 변경의 수치 차이를 구분한 뒤, 남은 필수 검증과 계획된 epoch2 탐색으로 이어가는 것이 적절합니다.

SELF_CHECK: FAIL
SUMMARY: iter_089 D8 자료·GPU 검사에서 현재 소견을 제거하는 temporal 규칙과 길이별 수치 불일치를 확인해 본학습을 보류했으며, 결정적 동일 shape R/G λ=0 대조는 통과했다.