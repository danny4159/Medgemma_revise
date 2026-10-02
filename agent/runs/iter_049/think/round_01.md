# 사고 라운드 1

## 이번 판단

현재 PadChest 두 양성 문장 공동 grounding의 추가 방법 투자는 보류한다. 다음 후보는 실제 사례의 다중 영상 근거 종합으로 좁혔다. 다만 자료와 대조군의 식별성을 확인하지 못했으므로 구현 계획이나 method pilot을 승인하지 않는다. 다음 라운드는 이 후보의 실행 가능성을 확인하는 medium 범위다.

## 원문에서 확인한 사실과 의미

- `agent/GOAL.md`, `agent/GPT_USAGE_POLICY.md`, `agent/REPORTING_STYLE.md`, `agent/LIMITATIONS.md` 관련 항목, 직전 `iter_048/review.md`와 `review.json/code_assets`를 읽었다. 관련 대안 판단을 위해 iter_003·004·018·029·042·046·047 리뷰와 iter_018·022·047 계획의 관련 구간도 확인했다. 아래 수치는 해당 리뷰의 검증 결과를 인용한 것이며 이번 라운드의 신규 실험 결과가 아니다.
- iter_048에서 공동 F1@0.3은 E 0.333116에서 J 0.523251로 회복됐다. J의 독립 대비 공동 손실은 0.067225이고, 적응 MedGrounder A는 0.594444였다. J/E device-seconds 비율은 0.963408 [0.922054, 1.006618]이다. 선택적 회복은 유효하지만 정확도·비용의 실용 근거가 부족하므로 잔여 손실만을 이유로 새 loss를 추가하지 않는다.
- iter_046의 모듈형 적응 효과는 유지한다. 대안의 모든 비열등성 기준이 확증된 것은 아니지만, 적응 차이가 기존 정확도 격차의 중요한 설명이었다.
- iter_042에서는 presence gate가 음성 오출력을 크게 줄였고 양성 보존은 불확정이었다. 이것은 새 부재 거부 방법의 필요성이 확인됐다는 뜻이 아니다.
- iter_047은 혼합 환자 34/52명, D8 oracle 29/32로 본 E96이 미실행이다. 교정 연구 가치의 기각은 아니지만, 표본 축소만으로 재개할 근거도 없다. text-only의 추가 지시문 confound를 새 설계에 복사하지 않는다.
- iter_018의 범위 안내 후 손실은 6.25 pp, CI [-6.25, 18.75] pp였다. 무관 evidence를 제외하면 해결되는 단일 질문을 다시 만들어 방법 개발을 정당화하지 않는다.
- iter_029에서 빈 출력 위험의 entropy AUROC는 0.8225였고 presence 재질의의 큰 추가 이득은 없었다. 일반적인 confidence 측정으로 이동하는 것만으로 새로운 질문이나 기여가 생기지 않는다.

## 전략 대안 비교

1. **다중 영상 근거 종합 대조 — 조건부 1순위.** 실제 사용에서 여러 영상의 정보를 함께 판단해야 하는 과제이며, 공개 benchmark에 최종 진단과 중간 소견이 있다. 과거 oracle·정답 구성 문제를 줄일 가능성이 있다. 그러나 단계별 읽기는 이미 기존 방법이고, 단순 baseline을 넘어설 실패 조건은 아직 확인되지 않았다.
2. **현재 공동 grounding 개선 — 보류 유지.** 직접 joint SFT가 큰 손실을 설명했고, 빠른 적응 모듈형 대안 대비 필요한 이점이 없다. 추가 학습의 정보 가치보다 기회비용이 크다.
3. **confidence·선택적 위임 — 후순위.** 실제 사용 가치는 크지만 기존 로컬 결과에 강한 token baseline이 있으며, 최근 연구도 의료 VQA의 여러 confidence 추정기와 selective prediction을 직접 비교한다. 새 데이터에 같은 AUROC 비교를 반복할 이유는 부족하다. [Calibrated Triage 원문](https://arxiv.org/html/2606.15910v1)
4. **초안 교정·문맥 편향 재개 — 보류 유지.** iter_047의 자료·oracle 문제와 iter_018의 인터페이스 대안을 해결할 새 근거가 없다. 이번 조사에서 주변 prompt 진단을 추가하지 않는다.

## 새 후보의 공개 근거와 중요한 제한

MedThinkVQA 공식 자료는 7,347 train/720 test, 영상별 소견·통합 소견·최종 진단 구조를 제공한다. 연구·교육용 CC BY-NC-SA 4.0이며 일부 longitudinal 사례를 포함한다. 데이터 형식에는 영상별 modality, caption과 사례별 시간 정보가 있다. 이 정보는 적격성 검토에 쓸 수 있으나 원본 행의 분포는 아직 확인하지 못했다. [공식 저장소](https://github.com/benluwang/MedThinkVQA), [데이터 카드](https://huggingface.co/datasets/bio-nlp-umass/MedThinkVQA/blob/main/README.md)

논문 Table 5는 MedGemma 1.5 4B의 213/720 정답을, 별도 image-ratio 표는 full-image에서 187/720을 보고한다. 같은 결과로 합치거나 낮은 수치를 골라 한계로 주장하지 않는다. 실행 조건 차이의 확인이 필요하다. 논문은 단계별 읽기와 text-only filtering을 이미 다룬다. 따라서 낮은 정확도·분해·영상 의존성 자체는 차별점이 아니다. [MedThinkVQA 논문 및 Appendix D](https://arxiv.org/html/2604.16506v1)

공개 예시 caption에는 질환 해석과 임상 문맥이 포함된다. expert caption을 그대로 제공한 성능 상승은 순수한 시각 인식 상한이 아니다. 원본 영상과 생성 소견을 함께 쓰는 실용 대조가 우선이며, 누출 없는 oracle을 만들 수 없다면 oracle 기반 원인 주장을 제외해야 한다.

이번 선택은 MRI·longitudinal로의 자동 전환 승인이 아니다. 우선 비longitudinal X-ray 사례로 실제 질문이 성립하는지 확인한다. X-ray만 남기기 위해 복합 사례의 다른 영상을 제거하고 원래 진단 정답을 그대로 적용해서는 안 된다. 해당 범위가 부족하면 modality를 조용히 넓히지 않고 후보를 재판단한다. VinDr 승인 대기, MRI F139 및 기존 보호 reserve는 유지한다.

## 아직 해결되지 않은 실행 문제

공식 HF 파일 목록에서 train.jsonl 84.2 MB, images.zip 6.13 GB를 확인했다. 그러나 로컬 Python의 공개 API 읽기는 DNS 오류 `Temporary failure in name resolution`로 실패했다. 브라우저에서는 데이터 카드와 파일 목록을 읽었지만 API/raw 일부 및 GitHub 하위 코드 경로는 열리지 않았다. 이를 데이터 접근 권한 부족이나 설치 불가로 해석하지 않는다. 원본 metadata·공식 실행 코드와 전체 revision은 아직 확인하지 못했다. [공식 파일 목록](https://huggingface.co/datasets/bio-nlp-umass/MedThinkVQA/tree/main)

따라서 적격 환자/사례 수, 영상 수 분포, 입력 token 규모와 요청량에 근거한 비용은 아직 산출할 수 없다. 이 항목을 임의의 E96·1시간 상한으로 대신하지 않는다. 다음 라운드에서는 공개 train metadata와 공식 inference 경로만 집중 확인한다. 동일 접근 오류의 재시도만으로 사고 라운드를 늘리지 않는다.

## 코드·재사용 확인

현재 research HEAD는 `54607a22c7046d0ab75fde09b2a5616edf0e2344`이며 `git status --short`는 비어 있었다. `agent/CODE_ASSETS.md`, iter_043 및 iter_048의 원본 code_assets를 확인했다. iter_043 commit `b50aa230a86c6d5b6c6b280fe718170ce4ecf220`의 존재도 확인했다.

현재 `pg43_run.py`와 관련 `rsna_diag` 파일은 실제로 존재한다. 소스의 요청 schema는 단일 `image` 또는 text 입력이므로 다중 영상을 그대로 지원한다고 가정할 수 없다. iter_048에서 확인된 재개 worker mapping과 attempt별 비용 집계 결함도 남아 있다. `rsna_diag/generate.py`의 모델·processor 로딩은 재사용 후보지만, 다중 영상의 순서·tensor·image token 검증이 추가로 필요하다. 실행 경로가 확정되지 않아 이번에는 선별 반입 목록을 만들지 않았다. 과거 전체 스냅샷을 승인한 것으로 간주하지 않는다.

## track의 누적 판단과 종료점

iter_040~048은 직접 SFT, 모듈형 적응, 공동 형식 학습이라는 중요한 경쟁 설명에 답했다. 진단·setup 연속 기록에는 실행 실패가 섞여 있으므로 유효 실험 수와 동일시하지 않는다. 다만 기회비용은 유지한다. 예를 들어 iter_046은 12,200문장 학습 노출, iter_048은 9,760문장 노출과 신규 생성·반복 timing을 수행했다. 정의가 다른 비용 장부를 임의로 합산하지 않는다.

새 후보도 영상 근거와 언어 판단의 연결이라는 같은 큰 질문에 속하므로 research_track을 유지한다. 다음 결정은 공정한 실제 출력 diagnostic의 구현 또는 후보 보류다. 낮은 benchmark 점수만으로 method gate를 통과시키지 않는다. 새로운 대상의 유효한 로컬 관찰이 없으므로 limitation_ids는 비웠다.

## 대규모 GPU 필요 후보

다양한 modality·기관의 다중 영상과 전문가 중간 소견으로 시각 인코더 및 근거 종합 모듈을 함께 학습하는 방향은 장기 후보로 남긴다. 현재는 필요성과 신규성이 미확정이며, 두 3090에서 가능한 inference 대조와 향후 경량 적응의 판별력이 먼저다.

파일 생성·수정, 모델 호출, GPU 실험은 수행하지 않았다. 인용 문헌은 조사 근거이며 사용자 논문 추천으로 등록하는 제안이 아니다.

## 다음에 파고들 질문
- MedThinkVQA 공식 train metadata에서 모든 제공 영상이 X-ray이고 비longitudinal인 사례는 얼마나 있으며, 사례별 영상 수·정답·caption 연결이 유효한가? 일부 modality를 제거하지 않고 필요한 정밀도의 비교가 가능한지 공식 train.jsonl과 데이터 처리 코드를 확인한다.
- MedGemma 1.5의 공개 213/720과 image-ratio 표의 187/720은 어떤 prompt·backend·영상 선택·출력 처리 차이에서 나왔는가? 공식 model 코드와 Appendix D를 대조해 정상 사용 조건과 재현할 baseline 하나를 고정한다.
- 기존 Think-with-Images, 직접 판단, 생성 소견+원본 재접근을 어떤 계산량 대조로 비교해야 정보 추출·압축 손실과 추가 호출 효과를 구분할 수 있는가? caption 누출 없이 가능한 주지표와 최소 가치 있는 정확도–비용 차이, 결과별 종료 행동을 확정한다.
- 현재 단일 영상 실행기와 과거 다중 영상 보관본 중 어느 경로를 재사용하는 것이 최소 변경인가? 실제 import 의존성과 원 리뷰를 확인해 필요한 수정·전체 SHA·필수 검증만 지정하고, 적격 자료가 없으면 구현 대신 후보 보류로 종료한다.
