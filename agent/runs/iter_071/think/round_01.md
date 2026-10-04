# 사고 라운드 1

## 핵심 판단

새 frozen 모델을 추가하거나 iter_064의 context 손실에 곧바로 새 방법을 붙이는 선택은 보류한다. 다음 검토는 **기존 RadGenome의 직접 적응 비교가 실제로 판단을 바꾸는가**로 좁힌다. 아직 중요한 사용 과제와 강한 단순 대조 이후의 가치가 충분히 구체화되지 않아 학습을 발주하지 않는다.

## 원문에서 확인한 사실과 투자 판단

`agent/GOAL.md`, `agent/INDEX.md`, 관련 `LIMITATIONS.md`·`CODE_ASSETS.md`, iter_059·062·063·064·068·070 리뷰, iter_067·068·070 계획과 이전 조사 노트를 확인했다. 관련 자산의 승인 범위와 현재 소스도 읽었다.

- iter_070은 유효한 제한적 비교다. AutoRG의 P/G 모두 15 case에서 BA 0.6136이고 mask Dice 평균은 0.9204다. 낮은 판독 성능은 관찰됐지만 높은 mask 중첩 때문에 영역 지원의 일반적 무효를 판정할 수 없다. 새 limitation은 등록되지 않았다.
- iter_064의 MedGemma S/R/C BA는 0.8021/0.7708/0.5000이다. Qwen에는 같은 손실이 없고, 명시적 target은 routing으로 처리할 수 있다. observed 근거와 사용법 검사는 존재하지만 단순 대안 이후의 방법 필요성은 부족하다. 해당 한계를 다른 MRI 과제의 method gate로 사용하지 않는다.
- iter_059의 전문 segmentation+OR는 해당 개발 조건에서 BA 0.950, U8 대비 전체 비용 0.601배였다. 이 구간 판정에 직접 SFT를 추가할 이유는 여전히 부족하다.
- iter_068의 Modic 순위 신호는 D 고정 보정 성능으로 연결되지 않았다. 기존 iter_067 조사에는 전체 SPIDER의 I형 3명·III형 6명 및 F139 보존 이유가 이미 기록돼 있다. 이를 다시 미확인으로 돌리거나 같은 보정 탐색을 재개하지 않는다.
- iter_046은 기존 강한 baseline의 직접 적응으로 경쟁 설명을 검증한 diagnostic이었다. 따라서 학습 자체가 금지되는 것은 아니다. 다만 새로운 해결책 개발을 diagnostic으로 이름만 바꾸는 것은 허용되지 않는다.

## Strategy Check / 연구 방향 판단

상위 질문은 여러 관측에서 필요한 근거를 선택·결합하는 능력이다. 현재 확인된 사실은 일부 고정 조건의 context 손실과 여러 과제에서의 기본 신호 부족이다. 이들을 공통 인식 결함이나 결합 실패로 합칠 수 없다.

1. **직접 적응의 한정 검토:** 우선한다. 기존 자료에서 정상적인 supervised baseline을 확보하면 frozen 성능만으로 남겨 둔 설명을 구분할 수 있다. 그러나 단순 이진 분류의 점수 상승만 남는 설계라면 투자하지 않는다.
2. **현재 세부 가설의 투자 보류:** 적응 후에도 상위 질문으로 연결할 중요한 사용 조건이 없다면 이 선택이 타당하다. 최종 GOAL 또는 MRI 전체를 포기하는 결정과 구분한다.
3. **기존 context 손실의 최소 개입:** routing과 타 계열 대안 이후의 잔여 가치가 없어 우선순위가 낮다. 관찰은 보존한다.

이번에 바꿀 결정은 적응 baseline 비교에 투자할지 하나다. 다음 라운드에 모든 MRI 후보를 다시 비교하지 않는다. iter_070은 구현 세션 약 32분, 본실행 약 3.5분이었고 iter_064의 본실행도 약 3.3분이었다. 준비·검증이 상당한 비용이었던 근거이며 track 전체 비용 비율이나 낭비율을 계산한 것은 아니다.

## 새로 확인한 학습 자료와 정답의 성격

로컬 `research/results/iter_070/data/radgenome/`의 split과 보고서를 읽었다. BraTS_GLI FLAIR train은 **161 case ID, subject 문자열 기준 159명**이다. case 수를 독립 환자 수로 사용할 수 없다. 기존 `label_table.json`의 자동 추출 기록은 HIGH 36·MIXED_HIGH_LOW 92·제외 33이다. 이 수는 새 수동 검증 결과가 아니며 `ar70_labels.py`의 train regex는 승인된 범용 label 추출기가 아니다.

train의 네 사례 `00291-000`, `00106-000`, `01013-000`, `01439-000`에서 global finding과 FLAIR 문장을 직접 대조했다. 표시된 신호 기술은 서로 대응했다. 첫 사례는 두 병변을 함께 기술하므로 하나의 mask와 하나의 표적 소견이 항상 같은 단위라는 가정은 여전히 금물이다. 네 사례의 일치로 전체 정답을 승인하지 않는다.

공식 논문 §4.1.4는 radiologist가 작성한 case 보고서를 GPT-4로 sequence별 보고서로 분해했다고 명시한다. 따라서 `modal_wise_finding.json`을 각 sequence에서 독립 판독한 원문 정답으로 부르면 안 된다. Appendix B.2.2의 예시에는 T2W·FLAIR·T1C 설명에도 T1W라는 문자열이 반복된다. 이는 확인할 주의점이며 실제 배포 label이 틀렸다는 증명은 아니다. [AutoRG 원논문](https://arxiv.org/html/2407.16684v3)

공식 저장소는 RGv2가 RadGenome으로 학습됐다고 설명한다. RGv2의 추가 학습을 미적응 모델의 최초 target 적응으로 표현할 수 없다. checkpoint별 train·validation 사용과 비교군의 노출 차이를 먼저 정해야 한다. [AutoRG 공식 저장소](https://github.com/ljy19970415/AutoRG-Brain)

### 이번 조회의 평가 노출 기록

schema 확인 과정에서 split을 먼저 제한하지 않고 보고서 dictionary의 첫 12개 항목을 표시했다. 사후 membership 확인 결과 `BraTS-GLI-00006-000`과 `BraTS-GLI-00014-001`은 공식 test였으며 두 case의 네 sequence 보고서가 계획 문맥에 노출됐다. 영상이나 모델 출력은 평가하지 않았다. 이후에는 train만 지정해 읽었다. 향후 이 두 case를 계획자에게 완전히 미노출인 확인 자료로 주장하지 않아야 한다. 전체 test를 개발 집단으로 전환하거나 결과에 따라 임의 제외하라는 뜻은 아니다. 확인 집단을 사용할 계획에서는 이 노출 이력과 분리 방식을 사전에 명시해야 한다. 기존 파일·split은 수정하지 않았다.

## 가까운 선행이 제한하는 주장

ReMIND는 다중 sequence MRI의 instruction tuning·보고서 SFT와 누락 modality에 관한 발화를 줄이는 reranking/correction을 이미 다룬다. 따라서 'MRI를 적응한다', '여러 sequence를 사용한다', '없는 sequence를 언급하지 않는다'는 설명만으로 새 contribution을 만들 수 없다. 이 논문의 모델·데이터를 이번에 확보하거나 실행하기로 선택한 것은 아니다. [ReMIND 원문](https://www.medrxiv.org/content/10.64898/2026.03.30.26349106v1.full)

MedSG도 순차 영상 grounding과 직접 instruction tuning을 다룬다. 기존 iter_019가 이미 조사한 선행이므로 새로운 연구 방향처럼 재제안하지 않는다. [MedSG 공식 논문 페이지](https://proceedings.neurips.cc/paper_files/paper/2025/hash/6c22b0280d0d7d9e0c3126b1e92df1a0-Abstract-Datasets_and_Benchmarks_Track.html)

이번 문헌은 설계 검토용이다. 긍정적인 새 실험 근거가 없어 사용자 논문 추천으로 등록하지 않는다.

## 재사용·실행 경계

현재 research HEAD는 `02a8adade58f7cea84638f9e96bf963a0fb64d55`이며 작업 트리는 깨끗하다. 현재 브랜치에는 AutoRG wrapper와 label 코드가 있고, 과거 MedGemma·Qwen 실행기는 다른 보존 커밋에 있다. 코드 부재를 소실로 해석하지 않는다.

iter_070의 `ar70_labels.py` 승인은 현재 val 수동 기록에 한정된다. runner의 재개·동시 launcher·실제 입력 hash 검증, evaluator의 provenance·parser, 공식 경로 대비 tensor 대조와 비용 경계에는 needs_fix가 남아 있다. 실험 선택 전 전체 정비나 선별 반입을 발주하지 않는다. `reuse_assets=[]`는 재사용 승인이나 새 구현 지시가 아니다.

이번에는 코드 수정·파일 생성·설치·실험 실행을 하지 않았다. 직접 적응을 채택하면 두 RTX 3090에서 학습 peak와 처리량을 측정하고, 비교군 병렬 배치 및 batch 확대를 실제 정보량에 맞춰 설계해야 한다. 추론 메모리 수치를 학습 예산으로 전용하지 않는다.

## 다음 확인과 종료점

남은 일은 새 자료 목록 검색이 아니다. 기존 train의 정답 생성 경로·환자 분리·관측 범위를 바탕으로, 직접 SFT와 단순 영상 대조가 서로 다른 설명을 판별하는 최소 실험을 만들 수 있는지 확인한다. 학습할 수 있다는 사실만 확인되고 중요한 잔여 사용 문제가 구체화되지 않으면 이 후보를 보류한다. 기존 15건의 frozen 비교나 prompt 탐색은 이어가지 않는다.

## 대규모 GPU 필요 후보

다기관 MRI volume–report 자료로 vision encoder·connector·언어 모델을 공동 적응하는 방향은 장기 후보로 보존한다. 현재의 128개 자동 추출 후보나 제한된 frozen 실패만으로 대규모 학습의 필요성을 주장하지 않는다.

## 다음에 파고들 질문
- RadGenome의 train global finding과 modal-wise 기술, 원 저자의 데이터 생성·학습 경로를 기준으로, 동일한 표적·관측 범위의 직접 적응 정답을 만들 수 있는가? case가 아닌 subject 단위 분리와 이번 test 텍스트 노출을 반영한 개발·확인 구성을 정할 수 있는가?
- 현재 보존된 AutoRG 공식 학습·입력 경로에서 직접 생성 SFT와 동일 영상 정보의 단순 분류 대조를 어떻게 구성해야 기본 인식 부족과 출력 연결 부족을 구분할 수 있는가? 구현 전에는 관련 소스·checkpoint 노출과 재사용 결함만 확인한다.
- 이 비교가 성공했을 때 단순 분류기 또는 기존 영역 보고서 방식 이후에도 연구할 중요한 근거 사용 조건이 남는가? 남지 않으면 적응을 발주하지 않고 이 후보를 보류하며, 남으면 실제 생성 metric·최소 가치 폭·학습 규모·종료점을 고정할 수 있는가?
