# 요약

- **이번에 할 일:** 기존 MSD D6/E48에서 지정한 한 slice의 판정을 단독·복제·다른 slice 추가 조건으로 비교한다. MedGemma와 기존 Qwen을 모두 사용한다.
- **필요한 이유:** iter_063은 영상 정보 부족과 기본 인식을 구분하지 못했다. 이번에는 정답 범위와 target 영상 자체를 고정한다.
- **확인할 기준:** 단독 기본 신호, 복제 입력의 변화, 다른 slice 추가의 추가 손실과 query-index routing의 정확도·비용이다.
- **주의·다음:** mask는 임상적 판독 충분성의 보증이 아니다. 명시적 target 과제의 새 방법 투자는 routing 대안을 고려해 종료하며 결합 능력은 평가하지 않는다.

# Current Understanding

iter_063은 유효한 정보 삭제 진단이다. R_J는 Qwen 0.10, MedGemma 0.15였고 R_T에는 형식 오류·거절이 많았다. 원 판정과 출력은 유지한다. E10의 추가 prompt·표본·모델·학습은 실행하지 않는다.

iter_056~057에서는 MSD FLAIR 구간의 실제 영상 신호가 관찰됐으나 구간 판정 적응 필요성은 입증되지 않았다. iter_059는 네 sequence 전체 volume을 사용하는 HD-GLIO+OR의 대안 채택을 지지했다. 이번은 그 구간 과제를 다시 개선하는 실험이 아니다.

현재 자료는 이미 사용한 MSD D6/E48이다. 54개 raw image·label 쌍의 존재와 저장 schema를 확인했다. 남은 training·공식 test·reserve는 열지 않는다. case가 독립 환자라는 추가 보장은 하지 않는다.

# Strategy Check / 연구 방향 판단

**상위 질문:** 여러 관측 중 질문에 필요한 근거를 유지하는가? 이번에는 인식과 선택을 구분하며 상보적 근거 결합은 다루지 않는다.

**해결된 관찰:** 현재 OmniBrainBench 원문 점수를 영상 기여로 해석할 수 없고 소견 삭제만으로 충분한 영상 신호를 확보하지 못했다. **남은 설명:** 입력 범위와 정답이 맞지 않아서 낮은지, target 단독 인식부터 낮은지, 추가 영상이 target 판정을 바꾸는지다.

**최소 비교:** target의 pixel을 그대로 둔 S/R/C 대조다. mask로 target-local 정답을 만들되 single-image 정답 사례만 선별하지 않는다. S 성능은 새로운 실제 관찰이며 사전 충분성의 대체물이 아니다.

**투자 선택:** 현재 QA 개선은 입력 충분성 문제를 풀지 못한다. 새로운 자료 탐색은 정답 연결 비용이 크다. 기존 mask 자산의 한정 대조가 더 직접적이다. 단, 명시적 index는 단순 routing으로 처리할 수 있으므로 context 손실 발견을 새 학습의 필요성으로 바꾸지 않는다.

**이번에 바꿀 결정 하나:** 현재 모델·입력 경로를 명시적 target MRI 질문에 사용할 때 단독 routing을 채택할지, 기본 적합성 부족으로 이 경로를 보류할지 결정한다. 큰 방법 투자 여부는 이번에 승인하지 않는다.

기존 두 모델 비교는 유지한다. 세 번째 모델 준비는 필요하지 않다. 과거 로그는 구현·검증 재작업이 상당했음을 보여주지만 지배 비용 비율은 측정되지 않았으므로 수치화하지 않는다. 기존 검증은 불변 범위에서 재사용하고 이번 결론과 무관한 평가기 정비는 제외한다.

# Hypothesis

S에서 사용할 수 있는 target 근거가 반대 annotation 상태의 slice를 추가한 C에서 덜 사용될 수 있다. R은 이미지 수·target 위치 변화의 영향을 분리한다. C−R은 추가 영상의 내용·해부학 차이를 포함하는 효과이며 순수 attention 기전으로 해석하지 않는다.

S가 낮으면 기본 인식과 FLAIR에서의 annotation 가시성은 여전히 미분리다. mask 존재만으로 사람이 단일 FLAIR에서 항상 판정할 수 있다고 주장하지 않는다.

# Limitation Evidence / Correct Usage Checks

limitation_ids=[]이며 diagnostic, method_stage=none이다. iter_063은 현재 과제의 모델 한계를 등록하지 않았다. SPIDER의 reference 인터페이스 관찰도 이번 method 근거로 전용하지 않는다.

재사용 근거는 iter_056의 native RAS·FLAIR channel0·비배경 mask 연결 검증과 iter_061~063의 두 모델 공식 backend 실행이다. 새 slice 선택·target 지시·두 영상 tensor는 별도 검사한다. MedGemma revision은 91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b, Qwen2.5-VL-7B-Instruct는 cc594898137f460bfe9f0759e9844b3ce807cfb5를 유지한다.

공식 chat template, bf16, 기존 processor와 greedy 생성을 사용한다. cap512, 비EOS cap 도달만 2048로 한 번 재시도한다. 정답 오류·거절 때문에 prompt나 parser를 바꾸지 않는다. 필요한 공식 사용법은 기존 기록과 실제 설치 revision을 연결해 확인한다.

# Contribution Path / Baselines / Reuse

[MuirBench](https://arxiv.org/abs/2406.09411)는 다중 영상 이해를 이미 평가한다. 이번은 의료 자료에 대한 원인 분리용 제한된 대조이며 새로운 benchmark나 방법 기여로 선언하지 않는다.

강한 단순 대안은 질문의 target index를 읽고 해당 원본 영상만 전달하는 routing이다. 이는 GT mask를 읽지 않는다. S와 모델 입력이 동일하므로 S 출력을 공유하며 routing 코드의 결과 hash 동일성을 검증한다. mask 기반 slice 표본 구성은 diagnostic oracle 선택이고 실용 slice 탐색과 구분한다.

iter_059의 전문 대안은 보존하되 과거 구간 BA를 이번 slice BA와 비교하지 않는다. 명시적 target routing 이후의 잔여 단일 영상 오류는 새로운 선택 방법의 필요성이 아니다. 직접 SFT·전문 모델 학습 비교는 새 방법 투자가 구체화될 때 필요하며 이번에는 학습하지 않는다.

현재 branch를 유지한다. 현재 HEAD는 62e2a5246320458bc09a0d78b6b24a9e212cb835다. q63_run.py의 load_model/build_inputs/env_info와 msd56_run.py의 MedGemma 로딩·parse_answer를 제한적으로 활용한다. 기존 QA manifest/eval은 사용하지 않는다. msd56_data.py는 reuse_assets의 원 SHA에서 반입하고 load_case/render/mask_slice만 사용한다. 원래 select/extract/build를 실행하지 않는다.

# Proposed Experiment

## 1. 자료 연결과 동작 확인

기존 cases.json의 D6/E48 구분을 유지한다. raw image·label을 저장 hash와 대조하고 channel·affine·shape·label 값 및 split 중복을 검사한다. 먼저 D6에서 실제 overlay를 표시해 새 target 연결을 확인한다. 표시 실패를 시각 검사 통과로 기록하지 않는다.

각 case에서 양성 target P는 mask>0 단면적이 최대인 axial slice다. 동률은 작은 z를 택한다. 음성 target N은 mask 합이 0인 slice 중 FLAIR nonzero pixel 수가 최대인 slice이며 동률은 작은 z를 택한다. P의 mask 합은 반드시 양수, N의 합은 반드시 0이어야 한다. 둘 중 하나가 없으면 case를 부적격으로 기록하고 대체 case를 채우지 않는다. 뇌 바깥의 빈 slice를 음성으로 사용하는 shortcut을 피하기 위한 고정 규칙이다. 좌표·크기·case ID·선택 규칙은 모델에 노출하지 않는다.

정답은 해당 slice의 비배경 종양 관련 annotation 유무다. N을 정상 환자·모든 질환 부재로 부르지 않는다. 표본은 GT로 구성한 쉬운 근거 집중 대조이며 자연적 slice 분포의 성능 추정이 아니다.

volume 전체 min/max·동일 RGB·기존 render를 유지한다. 새 PNG·manifest는 results/iter_064에 저장한다. target은 모든 조건에서 동일 파일이다. 모델별 processor가 산출한 target pixel tensor, 해상도, patch/grid 및 시각 token 수를 S/R/C 사이에 검사한다. 위치 token과 전체 문맥 길이 변화는 기록한다. 자동 해상도 변경으로 target 정보량이 달라지면 본생성 전에 동일한 모델별 처리 설정을 고정하고 D를 다시 검사한다. 정보량 변경을 해결하지 못하면 순수 context 대조로 진행하지 않는다.

## 2. 고정 요청

case마다 P/N 각각을 target으로 사용한다.

- S: target 한 장, target index=1.
- R1/R2: target을 두 번 제공하고 각각 첫째/둘째를 질문한다.
- C1/C2: P/N 두 장을 제공하되 target이 첫째/둘째에 오도록 순서를 바꾼다. 질문은 그 target만을 대상으로 한다.

고정 문구는 `The images are axial FLAIR slices from the same brain MRI. Consider only image {k} in the supplied order. Is a glioma-related lesion, including peritumoral edema, visible in that image? Answer with exactly one word: PRESENT or ABSENT.`로 한다. 영상이 한 장일 때도 같은 문구를 사용한다. 다른 영상의 상태·정답·oracle 여부·mask·slice 좌표는 제공하지 않는다.

공식 multi-image template에서 영상 목록 다음에 질문을 전달한다. 모델별 실제 image placeholder와 순서를 검사한다. whole-string PRESENT/ABSENT parser를 고정하고 공백·대소문자·끝 punctuation만 정규화한다. 설명·양쪽 답·선택지 밖 응답은 invalid이며 오답으로 계산한다. 원시 문자열·거절·비EOS는 별도 보고한다.

## 3. 가능성 탐색과 실행 규모

D6는 기술·처리량 확인용 최대120요청이다. 모델 정답률은 E 진입 gate가 아니다. 입력·정답·tensor·실행 검사가 통과하면 기존 E48의 적격 case 전부를 두 모델에서 평가한다. E는 최대960요청이고 case당 10요청이다. E 중간 성능으로 후반 실행·조건·사례를 바꾸지 않는다.

E48은 이미 노출된 개발 자료다. 48개 case는 큰 paired 손실의 분포를 살피는 규모이며 작은 차이의 확증용 power를 갖췄다고 말하지 않는다. 부적격 case로 n이 줄어도 임의 보충하지 않고 실제 n과 불확실성을 보고한다.

## 4. 규모 확대와 독립 확인

이번 반복은 고정 대조를 마치면 종료한다. 학습·새 seed·새 확인 집단은 없다. 긍정 결과도 자동 method pilot로 전환하지 않는다. 독립 재현이 필요하다면 먼저 단순 routing으로 충분하지 않은 실제 사용 조건이 있는지 별도 계획에서 판단한다.

# Implementation Tasks for Claude

1. 위 원 리뷰·reuse_assets를 확인하고 데이터 함수와 현재 두 모델 backend를 연결한다. 새 target manifest·평가기만 추가하며 기존 산출물은 덮어쓰지 않는다.
2. slice 선택 규칙을 출력 전에 잠근다. D 실제 overlay, NIfTI→PNG 독립 비교, target tensor 불변성, image 순서, GT 비노출을 검사한다.
3. 현재 q63 실행 경로에서 사용하는 결함을 수정한다. 중간 JSON 손상은 거부하고 실제 마지막 불완전 행만 원본 보존 후 복구한다. 기록 중 다른 worker 파일을 읽는 경합을 lock 또는 원자적 완료 record로 막고, 완료 확인과 claim 획득을 연결한다. 답변·비용·attempt의 저장 연결을 검증한다.
4. 실제 checkpoint·processor 파일 내용을 hash로 확인한다. blob 이름·과거 fetch 기록만으로 실시간 검증을 대신하지 않는다. 필요한 파일 집합, 환경, 코드, 요청, label, raw source 및 출력 seal을 protocol과 평가 진입점에 연결한다.
5. 합성 case로 P/N·동률·부적격·순서·복제·invalid·paired 통계를 검사한다. 실제 실행 경로의 source/protocol 변조 거부와 저장 경계 중단·재개를 D에서 시험한다. 동시 worker를 선택하면 종료 시점이 겹치는 경합도 검사한다. q63_test.py의 고정 GPU 1 지정은 재사용하지 않는다.
6. D 처리량으로 실행 구성을 고정하고 E를 완료한다. 평가기와 별도 계산으로 confusion matrix·paired 차이·CI를 대조한다. 실제 실행·미실행·수정한 경로와 남은 재사용 문제를 구분해 보고한다.

# Evaluation (성공/실패 기준 포함)

모델별 S/R/C의 BA, sensitivity, specificity, invalid·거절·비EOS 비율을 보고한다. R/C는 두 target 위치의 성적을 먼저 case 안에서 평균한다. case를 공통 재표집하는 seed64·10,000회 paired bootstrap으로 95% CI를 계산한다. P/N·위치별 결과와 unique case 수를 함께 제시한다.

주차이는 L_count=BA(S)−BA(R), L_content=BA(R)−BA(C), L_total=BA(S)−BA(C)다. invalid를 포함한 주분석과 모든 비교 응답이 valid인 조건부 보조 분석을 분리한다. 후자는 선택된 하위집단이므로 전체 결론을 대체하지 않는다. S 정답 사례에서 C가 틀리는 비율도 보조로만 보고하고 이를 사전 충분성 집단이라 부르지 않는다.

**기본 신호:** S BA≥0.75, sensitivity와 specificity 각각≥0.65. 이는 이 쉬운 GT 선택 과제에서 단독 입력을 사용할 수 있는지 판단하는 탐색 기준이다.

**추가 영상 영향 후보:** 기본 신호가 있고 L_content≥0.10, C 악화가 적어도5개 case에 분포하며 두 target 위치에서 R−C 방향이 모두 양수일 때로 한다. 10 pp는 현재 명시적 대상 workflow를 routing으로 바꿀 실용적 손실 기준이지 기여 인증 문턱이 아니다. CI가 0을 포함하면 탐색 후보·정밀도 미확인으로 표시한다.

**양성:** R 대비 C 손실이 있으면 다른 영상 추가의 제한적 영향을 보존한다. R도 S보다 낮으면 입력 수·위치 영향이 함께 있음을 명시한다. query-index routing은 S를 그대로 재현하므로 이 명시적 target 과제는 routing을 채택하고 새 방법 투자를 종료한다. 한 모델만 손실이면 모델 특이 조건으로 제한한다.

**음성:** S가 낮으면 현재 입력·과제 적합성을 보류한다. 다른 모델만 기본 신호가 있으면 그 모델의 routed 경로를 채택한다. S가 충분하고 C 손실이 작으면 현재 두 영상 조건의 대상 유지 한계 근거가 부족하다고 판정한다. 작은 차이는 무효과 확증으로 부르지 않는다.

**불확정:** E 완료 후 정밀도·형식·annotation 충분성 때문에 구분되지 않으면 현재 과제 투자를 보류한다. 추가 prompt·세 번째 모델·표본 확대는 하지 않는다. 기술 오류만 영향 범위를 특정해 한 번의 복구 경로로 처리하며 원 실패 attempt도 보존한다.

결합 능력, 일반적인 다중 영상 인식 결함, 임상 성능, 새로운 방법 우위는 어떤 결과에서도 이번 결론이 아니다.

# Risks / Checks

## 자원·시간·재개

실행 직전 nvidia-smi와 상속 CUDA_VISIBLE_DEVICES의 논리·물리 매핑을 확인한다. 여유가 큰 허용 GPU에 메모리가 큰 Qwen을 우선 배치하고 다른 GPU에 MedGemma를 배치한다. iter_063의 전체 점유 약16.4/9.2 GB는 참고값이며 새 두 영상 입력의 peak를 D에서 측정한다.

D에서 batch1 대 batch2를 먼저 비교한다. 긴 출력 지연·처리량·peak·오류·출력 정합성을 기록한다. MedGemma의 GPU당2 worker도 측정 peak 합과 기존 점유에 worker당2 GiB 여유를 더해 안전할 때 후보로 둔다. Qwen 두 worker를 참고 메모리만으로 올리지 않는다. 선택한 구성은 E 정확도와 무관하게 고정한다.

기존 iter_063의 두 모델 80요청 wall392초를 단순 비례하면 E960요청은 약78분이지만 새 출력 길이·영상 조건의 예측으로 신뢰할 수는 없다. 본실행 전 D의 모델·조건별 처리량으로 다시 산출하고 loading·검증·재시도는 별도로 적는다. 임의 시간 상한을 두지 않는다.

요청별 고유 ID, worker별 출력, 원자적 claim·완료, attempt 비용과 자식 exit code를 기록한다. 재개 시 protocol·입력·완료 결과를 검증한다. OOM은 batch·동시성만 낮추며 영상 수·해상도·질문을 조용히 바꾸지 않는다. 다른 사용자 프로세스와 hf_cache는 수정하지 않는다.

## 해석 경계

GT로 고른 최대 병변 slice와 mask-free slice는 자연 분포가 아니다. N의 정답은 annotation 부재이며 임상 정상의 보증이 아니다. FLAIR 단독에서 일부 annotation이 충분히 드러나지 않을 수 있다. 두 모델의 공통 실패도 VLM 전체의 한계가 아니다. 사전학습 노출·환자 독립성은 미확인이다.

## 대규모 GPU 필요 후보

장기 후보는 질문 조건부 multi-sequence/3D 표현과 언어모델의 공동 적응이다. 현재 대조가 이를 필요하게 만든다는 근거는 없으며, 명시적 index routing을 이기는 용도로 대규모 학습을 정당화하지 않는다.

# 계획의 근거 (GPT 조사 노트)

직전 원본 `agent/runs/iter_063/review.md`와 review.json을 확인했다. 삭제문 영상 정답률은 Qwen 2/20, MedGemma 3/20이며 텍스트 거절·형식 영향 때문에 충분한 영상 신호는 미확정이다. 새 한계 등록도 없으므로 limitation_ids는 비워 둔다.

`iter_056/plan.md`, iter_056/057의 원본 code_assets·reuse_issues, iter_057/059 review.md와 `CODE_ASSETS.md` 관련 항목을 확인했다. MSD D6/E48 원본 image·label 54쌍이 현재 존재한다. 저장 dataset.json은 channel0=FLAIR, 비배경 label=edema/non-enhancing tumor/enhancing tumour, licence=CC-BY-SA 4.0이다. `msd56_data.py`의 보존 원문은 image/mask grid 검사, canonical RAS, volume min-max 정규화와 동일 RGB 렌더 함수를 포함한다. D6_overlay.png를 실제 표시해 영상과 mask overlay가 존재함을 확인했으나 이를 임상 충분성 판정으로 사용하지 않는다.

현재 research HEAD는 `62e2a5246320458bc09a0d78b6b24a9e212cb835`이며 git status는 깨끗하다. q63_run.py와 msd56_run.py는 현재 기반에 있다. q63 실행기의 손상 복구·동시 읽기·모델 hash 문제가 남아 있어 그대로 승인하지 않는다. 원문 QA 평가 경로는 이번에 재사용하지 않아 관련 과거 평가기 정비는 발주하지 않는다.

문헌 확인: [MuirBench 공식 프로젝트](https://muirbench.github.io/)와 [원 논문](https://arxiv.org/abs/2406.09411)은 다중 영상 관계·강건성 평가가 기존 연구임을 보여준다. 이번 진단 자체의 신규성은 없다. 검색에서 나온 [PulseFocus 논문 페이지](https://arxiv.org/abs/2603.04676)는 실험·분석의 큰 수정 필요로 철회됐다고 명시하므로 효과 근거나 강한 비교군으로 채택하지 않는다. [MSD 원 논문](https://www.nature.com/articles/s41467-022-30695-9.pdf)은 brain 자료가 BraTS 2016/2017 사례와 연결됨을 설명한다. 모델 학습 노출과 환자 독립성은 여전히 제한으로 남긴다.

새 GPU 실행·파일 생성·코드 수정은 하지 않았다.
