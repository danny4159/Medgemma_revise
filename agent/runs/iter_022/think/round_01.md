# 사고 라운드 1

## 핵심

현재 동일-grid MRI 진단의 확대보다, 임상 다중 영상에서 실제 정보와 표현상의 반복을 구분하는 질문의 식별성을 확인하는 쪽을 우선한다. 다만 새로운 기여는 아직 확인되지 않았다. 이번 라운드에서는 기존 출력의 오류 형태를 좁혔고, 전환 후보와 겹치는 선행 연구를 추가로 확인했다.

파일 수정·생성, 테스트 실행, 모델 로딩, GPU 실험은 하지 않았다. 기존 JSONL의 read-only 재집계와 코드·문헌 조회만 수행했다.

## 1. 기존 근거와 이번에 새로 확인한 것

`agent/GOAL.md`, `agent/REPORTING_STYLE.md`, `agent/LIMITATIONS.md`, `agent/CODE_ASSETS.md`의 관련 항목, iter_019 계획·조사 기록, iter_021 원본 리뷰·보고서와 현재 소스를 확인했다. 현재 research HEAD는 `933eebaba2689d6eb654808ea177d8625ca2ca4c`이며 `git status --short`와 `git diff --stat`에 변경이 없다. tracked 파일 목록도 확인했다.

iter_021 리뷰의 E48 결과는 O/J_RT/J_TR/A/S2 pair success 각각 0/18/34/32/0명, C/N은 40/7명이다. J_TR wrong-instance가 0/96이므로 O 조건만 사후 제거해도 원래 반복 wrong-instance 가설은 살아나지 않는다. F139 확대와 기존 H 변경은 계속 보류한다.

이번에는 `research/results/iter_021/gen/E__phase1/gen_worker*.jsonl`과 `data/manifest.json`을 직접 읽었다. 응답의 마지막 `Final Answer:` 이후 box를 별도 추출하여 다음을 재집계했다.

- reference bbox의 정수 반올림 값과 완전히 같은 출력: J_RT 57/96, J_TR 79/96, A 63/96. 직전 리뷰와 일치한다.
- O에서 제공한 정수 점이 예측 box의 경계를 포함한 내부에 있는 경우: 74/96. 엄격한 내부에 있는 경우: 51/96.
- O box의 좌상단이 제공한 점과 정확히 같은 경우: 23/96. 직전 리뷰의 단서를 재확인했다.
- O 예측 box 면적이 정답 bbox 면적의 4배 이상인 경우: 66/96. 면적비 중앙값은 약 9.51이다.

마지막 두 면적 지표는 이번에 확인한 사후 기술통계다. 새 성공 기준이나 독립 검증 결과가 아니다. 넓은 box는 내부점을 포함하기 쉬우므로 74/96을 대상 선택 성공으로 해석할 수 없다. 실제 응답에는 한 척추보다 훨씬 넓은 영역을 출력한 사례와 점을 좌상단으로 사용한 사례가 함께 있다. 생성된 설명문은 모델 내부 원인의 증명이 아니다.

`rsna_diag/mi19_spec.py`의 O는 텍스트 내부점에서 posterior elements까지 포함한 전체 vertebra를 요구한다. 따라서 점 해석, 해부학적 대상 범위, 경계 localization이 함께 측정된다. `overlays/61_T_overlay.png`를 직접 확인했으나 한 영상의 육안 확인으로 전체 mask·물리좌표 검증을 대신하지 않는다.

**의미:** O 저점을 일반적인 point grounding 결함으로 승격할 수 없다. O prompt를 보정해도 같은-grid 과제에서 좌표 복사가 유리하다는 식별성 문제는 그대로다. 별도 임상적 필요가 없는 O 문구 탐색을 다음 GPU 반복으로 자동 예약할 근거가 약하다.

## 2. 정상 사용 확인의 범위

`generate.build_inputs_multi`는 user content에 image들을 순서대로 넣고 마지막에 text를 배치한다. 이는 이번에 다시 조회한 [공식 longitudinal notebook](https://raw.githubusercontent.com/Google-Health/medgemma/main/notebooks/cxr_longitudinal_comparison_with_hugging_face.ipynb)의 message 구조와 일치한다. 이전 검증과 모순되는 입력 구조 오류는 발견하지 못했다.

다만 소스 구조 대조는 실제 D 영상에 대한 공식 경로와 wrapper의 input_ids·pixel_values 동등성 검사가 아니다. 이 runtime 근거는 여전히 미완료다. 현재 관찰은 observed로 유지하고, RSNA에서 validated인 lesion-grounding-generalization을 MRI나 새 임상 QA로 확장하지 않는다.

## 3. 전환 후보에서 확인한 선행 연구와 남은 차이

iter_019 조사 내용을 반복 수집하기보다, 당시 충분히 확인하지 않았던 MedGemma 1.5의 image-ratio 수치와 새 후보의 중복 범위를 확인했다.

[MedThinkVQA 논문 Appendix D](https://arxiv.org/html/2604.16506v1)는 MedGemma 1.5 4B의 720-case 정확도를 전체 영상에서 213/720, 영상 비율 0/20/40/60/80%에서 각각 167/188/185/187/187명으로 보고한다. 전체 영상은 text-only보다 낫지만 중간 비율의 점수는 단조 증가하지 않는다. 집계치만으로 특정 영상 추가가 같은 환자의 답을 악화시켰다고 판단할 수 없으며, 우리 고정 revision·정상 사용에서 재현한 수치도 아니다. 논문은 전문가 소견과 모델 생성 소견, 단계별 오류를 이미 비교한다. 따라서 일반적인 인식→통합 오류 분해나 설명 생성 파이프라인 자체는 새 기여가 아니다.

[공식 데이터 카드](https://huggingface.co/datasets/bio-nlp-umass/MedThinkVQA)에는 7,347 train/720 test case, case별 영상 경로·caption·modality 정보가 있다. 기존 접근성 판단은 유지한다. 다만 개별 영상 또는 부분집합만으로 진단 정답이 충분히 보장되는지는 별도 문제다. caption·IMAGING_FINDINGS를 실용 입력에 섞어서는 안 된다. 공개 case 분할을 환자 독립성이나 사전학습 미노출의 증거로 자동 취급하지 않는다.

새로 확인한 [MedMultiBench, ACL 2026](https://aclanthology.org/2026.acl-long.1263/)는 11,392개 표본에서 Joint Reasoning, Comparative Analysis, Comprehensive Perception, In-Context Learning을 평가하며 visual load 증가에 따른 성능 저하를 이미 다룬다. 이번에는 공식 초록까지 확인했다. 전체 방법·배포 자료·정답 근거·원천 중복은 아직 확인하지 않았다. 이 연구 때문에 '영상이 많으면 성능이 떨어진다'는 관찰만으로 방향을 선정할 수 없다.

추가 근접 문헌으로 [CVPR 2025 position-bias 연구](https://openaccess.thecvf.com/content/CVPR2025/papers/Tian_Identifying_and_Mitigating_Position_Bias_of_Multi-image_Vision-Language_Models_CVPR_2025_paper.pdf)와 [ViewDiag 관련 CVPR 2026 workshop 연구](https://openaccess.thecvf.com/content/CVPR2026W/MULA2026/html/Bhat_Consistent_Yet_Wrong_Evidence_Insensitivity_in_Spatial_Vision-Language_Models_CVPRW_2026_paper.html)를 검색에서 찾았다. HTML 직접 조회는 403으로 실패했다. 세부 방법이나 우리 후보와의 차별성을 확인했다고 주장하지 않는다. 다음 라운드에서는 이 두 문헌의 필요한 실험·baseline 부분을 확인한다.

검토할 좁은 질문은 **같은 임상 근거가 반복 제시되는 효과와 실제 상보적 근거가 추가되는 효과를 구분할 수 있는가**이다. 정확한 복제 영상은 정답 보존 대조를 만들 수 있지만, 단순 중복 제거로 해결되는 현상에 머물면 투자 가치가 낮다. 자연적인 유사 view는 새 정보를 포함할 수 있으므로 임의로 중복이라고 정의해서도 안 된다. 두 조건을 구분할 주석과 실용 baseline을 확보해야 한다.

## 4. Strategy Check / 연구 방향 판단

중요한 능력은 여러 영상의 근거를 합쳐 판단하면서 반복·순서에 과도하게 좌우되지 않는 것이다. 이것을 현재 모델의 검증된 한계나 확정된 최종 연구 주제로 부르지 않는다.

1. **임상 다중 영상 근거 결합으로 전환:** 실제 진단과 연결되고 학습·평가 자료의 후보가 있다. 그러나 선행 연구 중복과 부분집합 정답의 불확실성이 크다. 좁은 read-only 조사가 GPU 투자 여부를 바꿀 수 있어 우선한다.
2. **현재 MRI 과제의 최소 보정:** 자료와 출력이 있어 비용은 낮다. 하지만 O 보정이 성공해도 좌표 복사 confound를 해결하지 못한다. 중요한 reference 의존 과제를 추가로 식별하지 못하면 현재 설계의 확대 투자를 종료하는 쪽이 타당하다.
3. **비정렬 reference 대응으로 전환:** 단순 좌표 복사와 구별할 가능성은 있다. registration·MedSAM2 등 모듈형 대안이 강하고 새 관계 GT 검증 비용이 크다. VLM을 쓸 이점이 명확해질 때 재검토한다.
4. **기존 grounding 개선:** 강한 직접 SFT와 checkpoint는 보존한다. 두 추가 loss의 음성·불확정 결과 이후 새 학습을 지지할 근거는 이번에도 없다.

이는 iter_021의 inconclusive 판정을 abandon으로 소급 변경하는 결정이 아니다. 유효한 실험 횟수나 복구 반복 횟수 때문에 포기하는 것도 아니다. 새로 확인한 과제 식별성과 예상 정보 이득에 따른 다음 투자 판단이다.

## 5. 재사용과 자원

현재 브랜치에 `generate.py`, `mi19_gen.py`, `mi19_run.py`, `mi19_requests.py`, `mi19_protocol.py`, `mi19_eval.py`, `geometry.py`, `parse.py`, `metrics.py`가 실제 존재한다. 소스가 없는 것으로 보고 재구현하지 않는다. evaluator의 승인 범위는 외부에서 완전성과 provenance를 보장한 입력에 한정된다.

새 GPU 경로를 선택하면 완료 재사용의 성공 상태·자식 종료 코드 검사, 필수 source 검증 연결, 예상 요청 집합과 단계 decision 검증, 실제 입력 대조·통제 재개 검사를 우선 보완해야 한다. S2를 사용하지 않는 진단에는 S1→S2 전용 정비를 자동 편입하지 않는다. 기존 archive를 재사용하면 downloader 전체 수정도 선행 의무로 만들지 않는다.

`reuse_assets=[]`는 조사 단계의 미확정 값이다. 새 브랜치 구현 계획을 확정할 때 승인 기반과 필요한 파일·의존성을 대조해 선별 반입 SHA와 required_checks를 명시해야 한다.

iter_021 리뷰의 실제 E 생성 wall-clock 약 78.6분과 GPU 전체 점유 peak 약 8,747–8,939 MiB는 기존 두 영상 과제의 참고값이다. 새 다중 영상 입력의 비용으로 그대로 외삽하지 않는다. 구현을 선택하면 두 GPU에서 batch 확대 또는 GPU당 2 worker를 development 입력으로 비교하고, 긴 출력 peak·worker당 최소 2GiB 여유·출력 정합성·전체 처리량으로 배치를 정한다. 이번에는 실행 규모가 미확정이므로 임의 시간 상한이나 본실험 표본 수를 만들지 않는다.

## 6. 유지·보류·다음 판단

기존 결과·checkpoint, MRI F139, RSNA 및 CheXpert reserve를 유지한다. iter_008의 anatomy 전이를 재개하지 않고 정상 사용 후 한계 검증이라는 지속 기준을 적용한다. MRI SFT, F 개방, O 제거에 따른 H 변경, 광범위한 prompt 탐색은 보류한다.

다음 조사에서 정답 보존·자료 연결·강한 단순 baseline과 구별할 실패 조건이 확보되면 단계별 GPU diagnostic을 확정한다. 정확한 복제의 효과만 남거나 기존 방법으로 질문이 이미 해결되면 이 전환 후보도 보류한다. 영상 수별 평균 점수만 재현하기 위해 큰 benchmark를 시작하지 않는다. 현재 신규 방향의 긍정적 실험 근거가 없어 사용자 논문 추천도 보류한다.

## 대규모 GPU 필요 후보

중복·상보성·영상 간 관계를 포함한 vision encoder–언어 모델 공동 post-training과 일반 능력 보존 혼합 학습을 후보로 남긴다. 현재 근거는 그 필요성을 입증하지 않는다. 작은 adapter·LoRA와 모듈형 근거 집계로 가능한 범위를 먼저 비교한다.

## 다음에 파고들 질문
- MedThinkVQA와 MedMultiBench의 실제 배포에서 case·원천·영상 bytes·정답을 연결하고, 정답을 보존하는 반복 대조와 상보적인 영상 조건을 구분할 수 있는가? 부분집합의 진단 충분성을 보장하지 못할 때 어떤 주장까지 가능한가?
- MedMultiBench의 visual-load 분석, CVPR 2025 position-bias 방법, ViewDiag의 evidence-insensitivity 대조는 후보 질문을 어디까지 이미 다루는가? 중복 제거·순서 평균·고유 영상별 예측 집계 이후에도 검증할 중요한 차이가 남는가?
- 가장 식별력 있는 한 과제에서 direct·분리 실행·단순 aggregation·oracle을 어떻게 구분하고, 개발 자료만으로 입력 형식·비용·확대 기준을 고정할 수 있는가? 잔여 질문이 없다면 MRI 보정으로 회귀하지 않고 어떤 대안을 우선할 것인가?
