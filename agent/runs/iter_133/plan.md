# 요약

- 이번에 할 일: 기존 RadGenome–BraTS FLAIR 15사례에서 무표시 영상, 위치 표시 영상, 표시-only 입력의 실제 MedGemma 출력을 비교한다.
- 필요한 이유: iter_070의 예측/정답 mask 중첩이 높아 위치 지원의 효과를 구분하지 못했다. 이번에는 표시 개입과 영상 기여를 직접 나눈다.
- 확인할 기준: 명시적 mixed-high-low 기술이 표시 후 늘고, 표시-only보다도 늘어나는지 확인한다.
- 주의·다음: HIGH-only 보고서를 low 부재 정답으로 해석하지 않는다. 결과는 제한된 설명 일치 관찰이며 다음 반복은 사용자 승인을 기다린다.

## 알림 맥락

- 연구: MRI 병변 근거와 설명 연결
- 데이터: RadGenome–BraTS 뇌종양 FLAIR MRI 기존 15사례
- 모델: MedGemma 1.5 frozen; 기존 AutoRG 출력 참고
- 과제: 같은 MRI에서 병변의 보이는 신호 특성을 짧게 기술한다
- 가설: 위치 지정이 도움이 된다면 표시 후 설명이 달라지고, 그 변화에 실제 영상이 필요할 것이다
- 질문: 병변 주변을 알려주면 영상에 근거한 설명이 더 잘 연결되는가?
- 변경: 구체화
- 연결: MR-ART 품질 비교는 종료하고, iter_070에서 구분하지 못한 위치 지원 효과를 사용자 승인에 따라 검토한다
- 작업: 자료 연결 확인 후 세 조건 45요청으로 후속 독립 확인의 투자 가치를 판단한다

# Current Understanding

iter_070의 AutoRG P/G BA 0.613636과 후보 종료 판정은 유지한다. P/G Dice 평균 0.920396은 두 조건이 위치 지원 유무를 강하게 구분하지 않았음을 뜻한다. 새 비교는 그 결과를 뒤집는 재평가가 아니다.

RadGenome FLAIR 원문은 병변과 edema를 구분하지만 BraTS subregion과 정확히 대응한다고 보장하지 않는다. HIGH 4건은 low를 명시하지 않은 보고서이며 명시적 low 부재 4건이 아니다. 따라서 임상 이진 BA를 주지표로 사용하지 않는다. 15사례는 이미 개발에 사용된 자료이고 독립 확인 집단이 아니다.

MR-RATE의 고정 양성 관찰은 유지한다. 다른 자료의 이번 결과로 그 원인이 해결됐다고 주장하지 않는다. 현재 속성의 MedGemma 한계는 아직 관찰하지 않았으므로 limitation_ids는 비워 두며 학습하지 않는다.

# Strategy Check / 연구 방향 판단

1. 중요한 문제: 병변 위치를 제공하는 도구와 영상 설명 모델 사이에서 어떤 정보가 실제 설명에 쓰이는지 알아야 적절한 개입을 선택할 수 있다.
2. 현재 근거: 라운드 01과 iter_070 원 리뷰를 계승한다. 이번 변경 근거는 HIGH-only의 비배타적 의미와 BTReport의 mask 기반 특징 지원 범위다.
3. 쉬운 해결책: 기존 AutoRG 영역 판독과 정량 규칙이 있다. 단순한 모든 항목 high+low 응답도 양성 기술 recall을 높일 수 있으므로 recall만으로 방법 가치를 주장하지 않는다.
4. 남은 설명: 위치 지정, 표시 prior, 영상 내용, 부분 관측, 보고서 대상 불일치다. 이번에는 앞의 세 요소만 제한적으로 구분한다.
5. 다음 결정: 영상에 의존하는 표시 효과가 있으면 정확한 정답 연결을 갖춘 독립 확인 하나를 제안한다. 없거나 불확정이면 같은 15사례 조건 순회를 중단한다.

# Hypothesis

U와 L의 관측을 고정한다. 위치 지정이 현재 설명에 도움이 되면 L에서 명시적 mixed 기술 재현이 U보다 증가한다. MRI 없이 동일 표시만 제공한 M에서도 증가가 같으면 영상에 근거한 회복으로 해석할 수 없다.

L의 무개선은 인식 결함을 확정하지 않는다. 표시의 부정확성, 8장 관측의 부족, 보고서의 대상 의미가 남는다. L의 개선도 정확한 병변 검출 능력이나 임상 판독 개선의 증명은 아니다.

# Limitation Evidence / Correct Usage Checks

기존 근거는 `agent/runs/iter_070/review.json`, `agent/runs/iter_133/think/round_01.json`, `research/results/iter_070/data/label_table.json`이다. 기존 MR-RATE observed 주장은 배경이며 이번 자료에 자동 전이하지 않는다.

실행 전에 15쌍의 현재 SHA256, shape, affine, 방향, spacing, segmentation label, 환자 ID를 manifest와 대조한다. 보고서 key와 영상 ID의 개별 연결 근거 및 자산 이용 조건을 확인한다. release 수준 설명만으로 개별 파일을 인증하지 않는다. 연결 또는 이용 근거가 확보되지 않으면 관련 사례를 임의 대체하지 않고 자료 blocker로 종료한다.

새 출력의 공식 chat template, image token 수, tensor, 방향과 intensity rendering을 검사한다. report·질병명·파일명·정답 범주는 입력에 넣지 않는다. 위치 표시는 명시적인 oracle 지원이며 실용 입력으로 표시하지 않는다.

# Contribution Path / Baselines / Reuse

기여는 미확정이다. AutoRG의 given_mask 기능을 새 방법으로 주장하지 않는다. BTReport의 확인한 VASARI 구현은 segmentation·anatomy 기반 특징 추출이며 이번 FLAIR 신호의 직접 판독 대조로 사용하지 않는다.

필수 대조는 U/L/M이다. 기존 train majority MIXED_HIGH_LOW와 무조건 high+low 기술을 함께 집계한다. 이 단순 대조는 양성 기술 재현의 상한적 쉬운 해법이며 유효 임상 판독기가 아니다.

기존 AutoRG P/G 출력은 15사례의 원문을 보존하고 새 공통 기술 집계만 `results/iter_133/`에 작성한다. 원 수치·parser·판정을 덮어쓰지 않는다. 전체 volume, 예측 anatomy, 학습 노출과 입력 차이를 표시하며 MedGemma와 공정한 모델 순위로 쓰지 않는다. ar70 실행·평가 코드를 재실행하지 않으므로 관련 needs_fix 전체 복구도 하지 않는다.

현재 HEAD의 mr123_data와 mr132_run/common/spec을 필요한 부분만 재사용한다. 자동 기반에 없다면 reuse_assets로 반입한다. mr132_run의 과제별 schema·경로·감독기 의존 검사를 iter_133에 맞춰 연결한다. 원본 파일과 기존 결과를 유지하고 파생 구현의 출처 SHA를 기록한다.

# Proposed Experiment

## 1. 자료 확인과 동작 확인

기존 적격 15사례 전수를 대상으로 한다. 00012와 00456 두 기술 사례에서 방향·표시·출력 인터페이스를 검사한다. 기술 결과로 prompt나 판정 문턱을 최적화하지 않는다.

whole-abnormality는 seg>0으로 정의하되 정확한 신호 ROI라고 부르지 않는다. canonical orientation에서 양성 mask가 존재하는 axial 범위의 8개 등간격 위치를 사용한다. 반올림 동률은 낮은 index를 택한다. 각 위치의 실제 mask 포함 여부와 전체 양성 voxel 중 선택 slice가 차지하는 비율을 기록한다. 모든 조건에 같은 slice를 사용하므로 U 역시 GT로 선택한 관측이며 실용적 무지원 baseline이 아니다.

MRI는 고정 volume min–max로 렌더링한다. 세 조건의 canvas는 896×896이며 해부학적 종횡비와 방향을 유지한다. L에는 각 slice의 seg>0 enclosing rectangle을 가는 선으로 표시한다. 내부 픽셀을 채우거나 crop·확대하지 않는다. 표시가 없는 slice는 그대로 둔다. M은 동일 canvas의 중립 회색 배경에 동일 rectangle만 남긴다. 표시 색·두께·좌표 변환은 기술 검사 전에 config에 고정한다.

U/L의 MRI 부분 hash 및 표시 외 픽셀 동일성을 검증한다. M은 임상 입력이 아닌 prior 대조임을 기록한다. 보고서의 임상적 정확성이나 8장 관측 충분성을 기술 검사 통과로 인증하지 않는다.

## 2. 가능성 탐색

15명×U/L/M=45요청을 실행한다. 한 환자의 조건은 같은 generation 설정을 사용한다. seed133, greedy, bf16, SDPA, revision `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`, max_new_tokens512를 고정한다.

공통 질문은 FLAIR 영상에서 주 병변의 보이는 신호를 기술하도록 하며 첫 줄을 HIGH / MIXED_HIGH_LOW / OTHER / UNKNOWN 중 하나로, 이후 짧은 근거를 요구한다. HIGH는 high가 보인다는 뜻이며 low 부재를 뜻하지 않는다고 명시한다. MIXED_HIGH_LOW는 high와 low 모두 보일 때 사용한다. L/M에는 rectangle이 병변 주변의 거친 안내이며 안의 모든 조직이 병변은 아니라는 동일 문장을 추가한다. M에는 영상 픽셀이 제공되지 않았다는 사실을 숨기지 않는다. 정확한 영어 prompt와 parser는 GPU 출력 전 config로 봉인한다.

공식 입력 대조와 동일 요청 재현 6건, 처리량 비교 최대12건은 성능 집계와 분리한다. 기술 결함 수정은 변경·영향 범위를 기록하고 영향받은 비교를 같은 최종 설정으로 다시 완결한다.

## 3. 규모 확대

이번 반복에서 새 환자·새 MRI·새 prompt·추가 mask 범위로 확대하지 않는다. 기존 15사례 전수는 보유 자산을 이용한 투자 선별 규모이며 효과를 확증할 충분한 표본이라는 뜻은 아니다. 양성 기준을 충족하면 독립 환자와 더 정확한 영역–설명 연결을 확보하는 다음 계획을 제안한다.

## 4. 독립 확인

이번에는 수행하지 않는다. 학습·LoRA·추가 seed도 없다. 방법 개발은 현재 결과의 독립 리뷰와 method gate를 별도로 거쳐야 한다.

## 자원과 재개

시작 직전 nvidia-smi로 허용 GPU0,1의 실제 여유와 논리/물리 대응을 확인한다. 독립 요청을 두 GPU에 배분한다. bf16 8~10GB는 참고이며 실제 peak에 worker당 최소2GB 여유를 둔다.

기술 요청으로 GPU당1 worker와 메모리가 허용하는 GPU당2 worker를 비교한다. 총 요청/분, 실제 요청 지연, peak, 오류, CPU/RAM/I/O 경합과 출력 정합성을 기록한다. 작은 전체 workload에서 추가 loading 비용이 절약보다 크면 1 worker를 유지하고 실측 근거를 남긴다. 과거 batch2 불일치 때문에 batch2를 자동 사용하지 않는다.

wall-clock 추정은 `loading + 렌더링 + 남은 요청/실측 총 처리량 + 평가`로 갱신한다. 단계별 실제 시간을 기록한다. 원자 claim, worker별 출력, protocol/input hash와 성공 상태가 일치하는 결과만 재사용하고 completion에서 45개 고유 ID를 검사한다.

# Implementation Tasks for Claude

1. 기존 결과·코드·자료의 provenance와 이용 조건을 확인하고 iter_133 manifest를 작성한다. 기존 mirror 접근 가능성을 이용 허가로 대체하지 않는다.
2. label_table의 15건과 원 modal_wise_finding의 기술을 대조한다. HIGH-only와 명시적 mixed를 구분하되 새로운 임상 음성을 만들지 않는다.
3. 동일 slice의 U/L/M 렌더링을 만들고 좌표·픽셀 동일성·정보 누설 검사를 실행한다.
4. 재사용 추론 경로의 고정 MR-ART 가정을 제거한 파생 실행기를 연결하고 모든 진입점의 gate·안전 재개를 검사한다.
5. 기술 검증과 처리량 선택 후 설정을 봉인하고 45요청을 완결한다.
6. 원출력·첫 줄·EOS·unknown·invalid를 보존한다. 기존 AutoRG 출력의 새 기술 집계는 원 평가와 분리한다.
7. 환자별 전환표·기술 재현·비용·남은 불확실성을 보고하고 종료한다. 다음 iteration이나 학습을 시작하지 않는다.

# Evaluation (성공/실패 기준 포함)

주집계는 명시적 mixed 보고서 11건에서 각 조건의 MIXED_HIGH_LOW 출력 수 및 paired 전환이다. HIGH-only 4건에서는 HIGH 또는 MIXED_HIGH_LOW를 모두 high 기술 보존으로 집계한다. 이 네 건의 mixed 출력을 임상 false positive로 세지 않는다. OTHER/UNKNOWN/invalid를 구분하며 비EOS는 invalid다.

세 조건의 전체 범주 분포, U→L·M→L 전환표, 보고서 범주와의 기술적 exact agreement를 함께 보고한다. exact agreement는 임상 정확도가 아니다. 모든 high+low 출력이 recall을 높이는 단순 대조와 구분되지 않으면 연구상 성공으로 해석하지 않는다. 환자 bootstrap95% 구간은 불확실성 기술용이며 작은 표본의 확증 근거로 쓰지 않는다.

양성 투자 신호는 다음을 모두 만족해야 한다: L이 U와 M 각각보다 mixed 기술을 순3사례 이상 더 재현하고, HIGH-only의 high 보존이 최소3/4이며, 각 조건에서 EOS를 갖춘 유효 범주 출력이 최소14/15다. 이는 임상 성능 gate가 아니라 후속 확인의 최소 정보 가치 문턱이다. 양성이어도 정확한 영역 의미·독립 환자·단순 대안 이후의 가치가 남는다.

L−U 순증가≤0이면 현재 표시 개입 투자를 보류한다. L과 M이 구분되지 않으면 영상 활용 회복 주장을 보류한다. 중간 효과·평가 불확실성은 불확정으로 종료하며 같은 자료의 조건 탐색을 추가하지 않는다. 자료 gate 실패는 execution_failed 범위로 보고하고 MRI 가설의 음성 결과로 바꾸지 않는다.

# Risks / Checks

- 선택 slice는 GT를 사용한다. 병변 검출이나 실용적 관측 선택 성능은 평가하지 않는다.
- rectangle은 거친 위치 지원이다. tumor core와 edema의 신호를 정확히 분리했다고 주장하지 않는다.
- HIGH-only는 음성 정답이 아니다. 자유 보고서의 미언급을 부재로 바꾸지 않는다.
- M에서 UNKNOWN이 나오는 것은 정상적일 수 있다. L−M만으로 좋은 임상 판독이나 위치 개입 효과를 증명하지 않으며 U−L을 함께 본다.
- 기존 AutoRG는 다른 정보와 학습 노출을 사용한다. 모델 간 우열·미노출 일반화를 주장하지 않는다.
- 자료 연결을 새 임상 해석이나 LLM 합의로 보충하지 않는다. 성립하지 않으면 구체적 원인과 재개 조건을 보고한다.
- 대규모 GPU 필요 후보인 3D encoder–언어 공동 적응은 노트로만 보존한다. 이번에는 학습하지 않는다.
- MR-ART·MR-RATE·iter_070의 원 기록을 보존한다. 운영은 Claude, 자동 fallback 없음, full review와 다음 반복 사용자 승인 대기를 유지한다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

라운드 01 원문 `agent/runs/iter_133/think/round_01.json`을 읽고 남은 세 질문에 집중했다. 파일 생성·다운로드·모델 실행은 하지 않았다.

1. `research/results/iter_070/data/label_table.json`의 val 23개 원문을 확인했다. 적격 15건은 명시적 high+low 11건과 high 기술 4건이다. 후자의 원문은 low 부재를 명시하지 않는다. 따라서 이들을 임상적으로 상호 배타적인 양성/음성으로 평가하면 안 된다. 새 비교는 명시된 기술의 재현과 출력 변화에 한정한다. 원 iter_070 평가·판정은 수정하지 않는다.
2. 보고서는 병변과 주변 edema를 자주 분리하지만 특정 BraTS subregion을 지칭한다고 보장하지 않는다. 따라서 tumor core를 정답 ROI로 새로 선언하지 않는다. seg>0의 rectangle은 병변 주변을 가리키는 거친 위치 지원이며 정확한 신호 측정 영역이 아니다. 같은 slice를 쓰는 U/L 차이는 이 표시 개입의 효과이지 전체 병변 검출 능력이나 순수 인식 원인이 아니다.
3. [BTReport VASARI 구현](https://github.com/KurtLabUW/BTReport/blob/main/btreport/vasari_features/vasari_auto_v2.py)은 segmentation label과 anatomy mask에서 위치·부피·관계를 계산한다. 기본 ET label이 4인 점도 확인했다. 이 경로를 BraTS2023에 적용할 때는 label 매핑 검사가 필요하다. 확인한 코드에 이번 FLAIR high/low 판독을 직접 측정하는 기능은 없었다. 이는 BTReport 전체의 한계를 판정한 것은 아니다.
4. [BTReport README](https://github.com/KurtLabUW/BTReport)는 최소 T1n과 tumor segmentation 입력, 정량 특징 이후 문장 생성을 설명한다. 현재 속성 비교에 전체 생성 파이프라인 설치는 필요하지 않다. 합성 보고서를 새 정답으로 사용하지 않는다.
5. `research/results/iter_083/preflight_a1/release_evidence.json`은 release 수준의 2021/2023 연결과 ET 4→3 변경을 지지하지만 개별 mirror 파일·이용 권한의 인증은 아니라는 범위를 유지한다. 구현의 첫 단계에서 현재 자산의 이용 근거와 환자 연결을 확인한다.
6. 현재 research HEAD는 `c1c5af0729627b009bff39abcdd69d2b7cf8da67`이고 작업 트리는 깨끗하다. mr132_run/common/spec 및 mr123_data를 직접 읽고 iter_132 review.json의 승인 범위를 확인했다. ar70_labels는 기존 정답표 생성 이력으로만 참고하며 새 범용 임상 정답 추출기로 사용하지 않는다.

## 의미와 설계 결정

정답 대상 불확실성을 숨긴 HIGH/MIXED 임상 BA 비교는 선택하지 않는다. 기존 자산에서 위치 표시가 명시적 설명을 바꾸는지를 45개 출력으로 확인하는 한정 진단을 선택한다. 표시-only를 포함해 단순 위치 prior와 영상 기여를 구분한다. 이 실험은 방법 gate의 근거를 자동 생성하지 않으며, 양성 기술 recall이 높다는 이유만으로 새 방법 투자도 승인하지 않는다.

## 대규모 GPU 필요 후보

3D encoder·connector·언어 모델을 영역별 MRI 신호 설명과 공동 적응하는 후보는 유지한다. 정확한 영역–속성 정답과 단순 대안 이후의 잔여 필요성이 먼저 확인돼야 하므로 이번에는 학습하지 않는다.

이전 사고 라운드 노트: agent/runs/iter_133/think/
