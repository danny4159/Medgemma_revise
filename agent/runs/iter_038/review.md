# 요약

- **판정:** metadata 우선 setup은 success다. 모델 실험은 미실행이므로 valid_experiment=false다.
- **핵심 근거:** train 다중 소견 1,163영상에서 exact label 중복은 20영상, label+location 중복은 0영상으로 독립 재현됐다.
- **의미·한계:** 현재 잔여 결합 후보의 우선순위를 낮출 근거다. 실제 grounding이 단순 규칙으로 해결된다는 증거는 아니다.
- **다음:** 같은 자료 집계를 반복하지 말고 다음 실제 출력 질문을 선택한다. 코드의 오류 차단·결과 보존과 test 노출 기록은 실제 재사용 전에 보완한다.

# Assessment

검토 대상은 commit.json의 SHA `1c295feb3a2ed3bac76a95fe7ff1566ccfe71955`와 구현 전후 changes.patch다. 신규 소스는 padchest_audit038.py 한 파일이며 작업 파일과 SHA의 내용이 일치했다. unpreserved_paths는 없고 작업 트리도 깨끗했다. reuse_manifest는 반입 파일이 없는 상태다.

plan.md·plan.json과 data_access_handoff.md·human_to_claude.md를 함께 읽었다. 사용자 인계는 접근 승인 확보와 metadata 우선 감사를 명시하며, metadata로 질문의 식별력 부족을 판단할 수 있으면 본 영상을 받지 않도록 허용한다. 따라서 영상 다운로드·GPU 실행을 하지 않은 것은 실행 실패가 아니다. 원 계획의 영상까지 포함한 전체 검증은 완료되지 않았지만, 인계로 허용된 조기 자료 판정은 완료했다.

Claude 도구 기록에서 감사 실행의 정상 결과와 fixture 성공을 확인했다. 모델 추론·학습은 없었다. 이 setup을 유효한 모델 가설 실험으로 계수하거나 한계를 validated로 갱신하지 않는다.

# Key Findings

원본 두 파일을 읽어 SHA256과 ZIP CRC를 확인했다. SHA는 handoff·source_manifest·audit_checks와 일치한다. 제공자 공식 checksum 검증을 뜻하지 않는다. 리뷰에서는 감사 스크립트의 main을 실행하지 않고 별도 표준 라이브러리 코드로 원시 집계를 재계산했다.

- 전체 report 4,555개, metadata 8,787행이다. 영상 split은 train/validation/test 각각 3,185/455/915개, 환자는 3,123/443/893명이다. 환자 split 교집합은 0이었다.
- 현재 JSON의 중복 key, ImageID별 환자·study·split 연결 충돌, 필수 연결 필드 공백은 모두 0이었다.
- train finding 7,315개 중 음성 2,401개, box 없는 양성 573개, box 있는 양성 4,341개를 재현했다.
- 다중 소견 1,163영상의 3,408 finding에서 broad category-set 중복은 477 finding/213영상, exact label-set 중복은 41 finding/20영상, label+location-set 중복은 0이었다.
- 4,100 finding 쌍의 관계는 broad category 비공유 3,773쌍, broad category 공유·label 차이 305쌍, 동일 label·location 차이 22쌍이었다.
- official–extra annotation의 finding별 평균 최대 IoU는 3,684 finding에서 0.4881282359785596으로 저장값과 일치했다.

근거는 `research/results/iter_038/audit/audit_checks.json`, `source_manifest.json`, 빈 `residual_pairs_private.json`과 연결된 원본 JSON·CSV다. 순수 함수 검사 4건도 메모리에서 통과했다. 파일 생성·수정이나 GPU 실험은 하지 않았다.

# Problems / Concerns

현재 고정 입력의 제한된 집계를 무효화하는 문제는 발견하지 못했다. 그러나 보고서의 '재사용 전 수정 없음'과 포괄적인 SELF_CHECK: PASS는 승인할 수 없다.

감사기는 JSON duplicate key를 실제 검사하지 않는다. split·schema·잘못된 box를 발견해도 대부분 결과에 숫자만 남기고 계속 진행한다. ImageID별 환자·study 연결도 drop_duplicates 전에 검증하지 않는다. 현재 입력의 관련 무결성은 리뷰에서 별도로 확인했지만 다른 입력을 안전하게 거부한다는 보장은 없다.

최종 결과 파일은 덮어쓰기가 가능하고 단일 소유권이나 묶음 완료 검증이 없다. 계획의 입력 변조·중복 key·missing split 회귀 검사도 미실행이다. source_manifest는 별도 작성됐고 실행 코드와 config digest를 자동 연결하지 않는다. 이 문제들은 현재 집계보다 후속 재사용에 적용된다.

schema 탐색 명령이 test 첫 report와 CSV 앞부분을 출력했다. 원시 도구 결과에 문장·box·식별 필드가 포함됐음을 확인했으며 이 리뷰에서는 재출력하지 않았다. 보고서 앞부분의 노출 고백은 맞지만 뒤의 'validation/test 내용은 열지 않았다'는 표현은 틀리다. 집계는 train에 한정돼 현재 수치를 무효화하지 않는다. 다만 노출 사례의 독립 평가 지위와 비공개 로그 보존·공유 범위는 관리해야 한다.

별도 eligibility_report와 baseline_requirements 파일은 없고 관련 설명은 보고서·audit_checks에 분산돼 있다. 이를 위해 별도 반복을 만들 필요는 없지만 다음 계획에서는 집계가 답한 범위와 미완료 영상 검증을 명시해야 한다.

# Interpretation

확인된 것은 **같은 영상 안에서 annotation label/location 조합이 모두 서로 다르다**는 사실이다. annotation에서 얻은 조합은 oracle 정보이며 실제 문장 파서나 detector의 출력이 아니다. 태그가 다르다는 것만으로 문장을 올바른 영상 영역에 연결할 수 있다고 결론 내릴 수 없다.

따라서 H_data의 좁은 조작적 조건에 맞는 잔여 후보가 없다는 자료 판단은 타당하다. 하지만 모든 문장–영역 연구가 불필요하다거나 broad category 공유 213영상이 언어 추출 문제만 남긴다는 주장은 미검증이다. 213영상은 다른 질문의 후보일 수 있으나 자동으로 유일한 후속 선택이 되지는 않는다.

영상 없는 상태에서 평균 IoU를 경계 모호성의 확정 증거로 표현하는 것도 피해야 한다. 현재 수치는 주석 집합 간 불일치를 요약하며 원인은 분리하지 않았다.

# Strategy Check / 연구 방향 판단

**실행 유효성:** 사용자 승인 인계에 따른 metadata 감사는 실행됐고 주요 수치가 독립 재현됐다. 실제 모델 실험은 없었다. GPU 0 사용은 이번 자료 gate와 일치하며 자원 정책 위반이 아니다.

**성능 개선:** 새 모델 출력·학습·baseline 성능 비교가 없으므로 개선 근거가 없다.

**가설 지지:** exact label+location 이후 잔여 사례를 요구한 현재 자료 가설에는 음성 근거다. 모델의 결합 능력·언어 추출 난도·시각 grounding 원인에는 결론이 없다.

**신규 기여 가능성:** 아직 확인되지 않았다. iter_037 원본 리뷰가 권고한 언어–근거 질문 탐색에는 부합하지만, 이번 metadata 조합 분석 자체가 새로운 방법이나 일반적 원리를 입증하지 않는다.

같은 질문의 확대는 적격 잔여 사례가 없어 정보 이득이 낮다. broad category 공유 집단의 실제 출력 진단은 새로운 사용 목적과 강한 baseline 이후에 구분할 실패 조건이 있을 때만 가치가 있다. 다른 연구 질문으로 전환하는 선택도 함께 비교해야 한다. 성공한 setup을 같은 접근법의 자동 연장 명령으로 해석하지 않는다.

실제 긍정적 모델 실험 근거가 없어 이번 논문 추천은 보류한다. 준비 단계 자료 판단이므로 milestone도 부여하지 않는다.

# Recommended Next Experiment

다음 deep 계획에서 현재 exact 조합 잔여 진단은 종료 대상으로 두고, 실제 영상 출력으로 판단을 바꿀 질문을 선택한다. 기존 metadata는 재집계하지 않는다. PadChest-GR을 계속 사용할 경우 문장별 독립 처리·공동 처리·적절한 모듈형 비교군이 각각 어떤 경쟁 설명을 구분하는지 먼저 명시한다. annotation oracle의 유일성과 실용적 대응 성공을 구분하고, 실제 영상 확인이 필요한 근거가 성립한 뒤 승인 범위의 영상 확보·좌표 검증·GPU diagnostic으로 진행한다.

후속 과제가 성립하지 않으면 GOAL 안에서 다른 질문을 선택한다. 새 loss·합성 benchmark·광범위 수집으로 자동 확대하지 않는다. 이번 코드 보완은 실제 재사용 경로에 한정한다. VinDr 승인 대기와 기존 RSNA 성과·checkpoint, continuation 투자 종료, MRI·reserve 보존은 유지한다.