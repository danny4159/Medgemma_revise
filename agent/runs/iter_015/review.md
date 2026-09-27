# 요약

- **판정:** CONTINUE / inconclusive. 실제 생성은 수행됐지만 형식 gate에서 멈춰 본 QA 가설 검증은 미실행이다.
- **핵심 근거:** D36 QA 432건을 재집계했다. plain Q_A valid는 M0/B0/C에서 35/36, 29/36, 26/36이며 JSON도 gate를 통과하지 못했다.
- **의미·한계:** 형식 문제는 관찰됐다. 의미 구분 능력 저하, 형식만으로 저하가 설명된다는 가설, 새로운 방법의 기여는 아직 검증하지 않았다.
- **다음:** 제한된 형식 보정을 고정해 진단을 이어갈 가치를 검토한다. 재사용 결함을 필요한 범위에서 수정하고 새 loss 학습은 예약하지 않는다.

# Assessment

원 계획은 두 형식 모두 실패하면 target 의미 손실을 판정하거나 E600으로 확대하지 않도록 정했다. 이번 보류는 그 규칙에 부합하며 실행 실패나 가설 기각으로 취급하지 않는다. 다만 도달 단계가 동작·형식 확인이고 H1–H4 본 검증이 미실행이므로 valid_experiment=false, approach_status=inconclusive로 판단한다. E180 bbox 보조 비교만으로 QA 진단 완료를 대신할 수 없다.

계획·구조화 계획·보고서·changes.patch·reuse_manifest와 실제 소스를 검토했다. commit.json의 SHA `3265f117bf3f4de99ba084f2c9b4e476568f24bd`에 있는 28개 대상 파일은 현재 내용과 모두 일치했고 unpreserved_paths는 없다. 현재 git status와 diff도 비어 있다. execution_amendment.md는 없으며 재잠금과 추가 bbox 실행 이유는 보고서·protocol note·도구 호출 기록에서 확인했다.

리뷰에서는 파일 수정, 테스트 파일 실행, GPU 실험을 하지 않았다. 저장 원시 출력의 읽기 전용 재집계와 hash 대조를 수행했다. 현재 리뷰 Python에 torch가 없어 adapter tensor digest의 독립 재계산은 완료하지 못했다. 실제 worker의 adapter 로드·digest 검사 코드와 저장 연결 기록은 확인했다.

# Key Findings

1. **실제 실행:** 정식 gen 경로에 D36 QA 432건, D12 bbox 24건, D12 evidence 72건, E180 C bbox 180건, 총 708건이 있다. 각 요청 집합과 실제 고유 record 집합이 일치한다. pilot·중단 재개 출력은 이 수와 구분했다.
2. **형식 결과:** plain Q_O는 세 모델 모두 36/36 valid다. plain Q_A의 B0/C 실패 7/10건은 모두 `Normal` 응답이다. JSON Q_O valid는 M0/B0/C에서 19/36, 7/36, 6/36이고 Q_A는 35/36, 1/36, 3/36이다. JSON 지시에도 bare yes/no가 많이 출력됐다. 별도 parser 집계가 format_decision.json과 일치했다.
3. **잘림과 입력:** QA 432건은 모두 EOS 종료다. 정식 708건의 저장 EOS·출력 token 수 및 요청의 주요 provenance 필드를 대조해 불일치가 없었다. 현재 영상 636개의 file/pixel hash, labels의 category·patient·boxes도 원본 manifest와 일치했다. D36/E600 환자 수는 각각 36/600명이며 대상 환자와 train 환자의 교집합은 0이다.
4. **bbox 보조 결과:** E180 양성 60명에서 F1@0.3은 M0 0.07222, B0 0.71944, C 0.69000이다. F1@0.5는 0.00833, 0.40556, 0.41111이다. 기존 bbox parser를 사용하고 matching·F1·bootstrap을 별도 구현해 재확인했다. B0−M0는 +0.64722, 95% CI [0.53889, 0.75000], C−B0는 −0.02944, CI [−0.09056, 0.03056]이다. 재사용 M0/B0 각각 600건의 원문·request ID·adapter 연결도 iter_012 원본과 일치했다.
5. **자원:** 48개 pilot 요청의 1/2 worker 구성 간 request 집합과 greedy token이 일치한다. 전체 wall-clock 합은 104.27→96.46초로 약 1.08배 개선이다. 보고서의 1.45배는 생성 구간 합 48.8→33.7초 기준이다. 4 worker 구성의 기록상 GPU별 최대 점유는 17,836/17,765 MiB로, 이번 짧은 출력에서 메모리 여유는 확인된다.

# Problems / Concerns

현재의 좁은 결론인 ‘고정 형식 gate 실패’를 무효화하는 문제는 발견하지 못했다. 전체 스냅샷 재사용 승인은 보류한다.

- **동시 복구:** qa_gen은 자기 worker lock만 잡고 모든 결과 파일에 repair-tail을 적용할 수 있다. 살아 있는 다른 worker의 부분 쓰기를 수정할 위험이 있다. qa_run은 부모 중단 시 자식을 회수하지 않고 run lock을 해제한다. 단일 worker SIGKILL 검사는 이 경로를 검증하지 않는다.
- **검사 과장:** GPU 테스트의 기존 record 유지 검사는 재개 후 같은 목록을 자기 자신과 비교한다. 로그 총 done 수 검사도 재개 전후를 분리하지 않는다. 따라서 7/7은 보고서가 말한 모든 재개 불변성의 증명이 아니다.
- **완료·평가 입력:** 완료 skip 경로는 현재 원본 file hash를 다시 계산하지 않는다. labels.json·qa_report.py의 잠금, D36 평가 코드 잠금도 빠져 있다. bbox_records는 여러 경로의 결과를 조용히 덮어쓸 수 있다. 이번 실제 입력과 결과는 별도 대조로 확인했지만 다음 실행 전에 코드로 강제해야 한다.
- **pilot 대표성:** M0 QA 24건은 opacity 16건과 normal 8건으로 구성되어 NoOpacity/NotNormal이 없다. 코드의 category 균형 설명과 다르다. 전체 실행 시간 개선과 생성 구간 개선도 구분해야 한다.
- **해석 표현:** 보고서의 NoOpacity/NotNormal coverage 0.283은 비어 있지 않은 bbox를 낸 17/60명에서 Q_A=yes를 내리는 coverage다. ‘box 없이 판단’하는 coverage가 아니다. 해당 category에서 Q_O=yes는 오답이므로 target 구분 성공의 근거가 되지 않는다.

기존 d36/pilot protocol은 qa_run의 poll-s 추가로 hash가 달라졌고 v2는 현재 파일과 일치한다. stage2의 잠긴 파일도 현재 내용과 일치한다. 이전 산출물을 삭제하지 않고 구분한 점은 적절하다.

# Interpretation

이번 결과는 답변 형식이 target 의미 진단을 가린다는 측정상의 문제를 보여준다. 특히 Q_A의 `Normal`은 엄격 yes/no 계약 위반이지만 의미를 읽을 수 없는 응답은 아니다. 이를 곧바로 시각적 forgetting이나 의미 손실로 해석하면 안 된다. 반대로 형식만 고치면 의미 성능 저하가 사라진다는 H2도 아직 검증되지 않았다.

D36의 사후 lenient accuracy는 개발 관찰이며 새로운 primary 결과가 아니다. E180 bbox는 기존 직접 SFT 이득의 개발 자료 재확인이다. C가 추가 이득을 입증했다는 결과도 아니다. D12 evidence 72건의 valid 출력은 연결 동작 확인에 해당하며 모듈형 효과의 증거가 아니다.

사용자 보완에 따라 anatomy 전이나 새 loss를 자동 실행하지 않았고 실제 모델 출력·질문·parser를 대조했다. 기존 정상 사용 grounding 주장은 유지하며 새 형식 관찰만 observed로 기록한다. 독립 표본 재현이 없으므로 validated로 올리지 않는다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 생성과 사전 gate 판정은 확인됐다. 본 target 의미 가설을 검증하는 QA 비교는 미실행이다.
- **성능 개선:** 이번에 새 방법의 개선은 없다. bbox 수치는 기존 SFT baseline의 알려진 이득을 다시 보여준다.
- **가설 지지:** 특정 질문과 적응 checkpoint의 형식 준수 저하는 제한적으로 관찰됐다. H1/H3/H4와 ‘형식만으로 설명된다’는 H2는 미확인이다.
- **신규 기여 가능성:** 형식 보정 뒤에도 target별 차이가 남고 강한 단순 대조로 설명되지 않아야 다음 방법 질문이 생긴다. 형식 실패 자체를 contribution으로 삼을 근거는 부족하다.

iter_015의 세 방향 비교는 여전히 유효하다. 현재 grounding 방법 개선은 새 원인 근거가 없어 우선순위가 낮다. 기존 checkpoint의 제한된 형식 보정 진단은 추가 학습 없이 다음 선택을 구분할 수 있어 우선 후보다. 보정 후 차이가 사라지거나 작은 형식 현상만 남으면 다른 의료 VLM 질문으로 전환하는 편이 낫다. 이는 같은 접근법의 자동 연장이 아니라 제한된 정보 획득 투자다.

논문 추천은 보류한다. 이번 후속 방향은 아직 형식 확인 단계이며, 의미 보존이나 모듈형 활용을 더 탐구할 긍정적 비교 근거가 확보되지 않았다.

# Recommended Next Experiment

다음 계획에서 D36을 개발 자료로 사용해 질문별 의미가 명확한 최소 형식 보정을 고정한다. Q_A에 한정한 정확한 `Normal→no`, `Abnormal→yes` 대응은 우선 검토할 수 있다. 기존 strict 지표를 함께 유지하고, 설명문·모순·bbox를 정답에 유리하게 해석하지 않는다. 강제 첫-token scoring은 생성 평가와 다른 조건이므로 자동 대체하지 않는다.

실제로 사용할 실행·평가 경로의 결함만 수정한 후 E180 QA 및 계획된 형식·evidence 대조로 의미 차이를 검사한다. 형식 보정 후 차이가 남으면 사전 기준에 따라 E600·seed 재현의 정보 이득을 판단한다. 차이가 사라지면 새 의미 보존 loss를 시작하지 않고 다른 질문과 비교한다. 과거 confirm인 E600은 개발 자산이며, 남은 부분을 새 독립 test라고 부르지 않는다. reserve와 기존 결과는 보존한다.