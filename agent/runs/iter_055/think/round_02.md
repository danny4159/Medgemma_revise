# 사고 라운드 2

# 핵심 판단

**정량 측정의 위치–산술 오류 분해 후보는 보류한다.** round_01에서 남긴 핵심 질문에 답하는 선행 근거를 확인했다. 제안한 분해는 MedVision이 이미 수행하며, mask 기반 결정적 계산 대안도 공식 구현에 있다. 이를 MedGemma 1.5에 적용하는 것만으로는 이번 프로젝트의 방법 개발 방향을 정하기 어렵다.

보류 이유는 자료 접근 실패나 GPU 비용이 아니다. 현재 제안에서 선행과 구별할 주장을 확보하지 못했기 때문이다. 정량 측정 전체의 연구 가치나 MedGemma 1.5의 능력을 기각한 결과는 아니다.

# 원문 확인 범위

`agent/runs/iter_055/think/round_01.json` 원문을 읽고 이번 확인 범위를 이어받았다. `agent/GOAL.md`, `agent/GPT_USAGE_POLICY.md`, `agent/runs/iter_054/review.md`도 확인했다. 다른 과거 실험의 해석은 round_01에 기록된 원 리뷰 확인 범위에서 유지하며 새로 검증했다고 표현하지 않는다.

# 직전 질문에 대한 답

## 1. 직접 출력과 geometry+계산이 같은 수량을 평가할 수 있는가?

원리상 가능하다. T/L의 대상은 fitted ellipse의 축 길이이며 bbox 폭이나 최대 직경을 대신 사용하면 안 된다. 예측한 축 끝점에 좌표계와 축별 spacing을 일관되게 적용하면 같은 정의의 길이를 계산할 수 있다. 다만 최신 annotation과 실행 코드가 완전히 동일한 정답 규약을 구현하는지는 이번에 인증하지 않았다.

공식 `eval_tl.py`는 연결 성분의 contour를 물리 좌표로 옮겨 ellipse를 fitting하고, landmark 좌표와 voxel size로 거리를 계산한다. GT는 `biometric_profile`의 major/minor 값을 조회한다. 따라서 단순 bbox 계산을 T/L의 강한 대조군으로 삼는 설계는 제외해야 한다. 이 파일은 inference용 fitting이 annotation planner와 일부 다르다고 명시하므로 무검증 재사용 대상도 아니다. [공식 T/L 평가 코드](https://raw.githubusercontent.com/YongchengYAO/MedVision/master/script/ablation/biomedparse/src/eval_tl.py)

이 확인은 계산 대조를 구성할 가능성을 보여준다. 새로운 과학적 질문이 남는다는 증거는 아니다.

## 2. 선행이 이미 제안한 오류 분해를 포함하는가?

**포함한다.** MedVision v2 §4.1은 localization error와 arithmetic error를 분리한다. 모델이 예측한 landmark에 같은 수식을 Python으로 적용하고, 그 결과와 모델의 최종 수치를 비교한다. 또한 intermediate estimate를 감독하는 process reward를 사용한다. Table 2의 T/L arithmetic MRE는 3.4%, measurement MRE는 26.0%로 보고돼 있다. 이는 해당 논문의 모델·자료 결과이며 MedGemma 1.5의 측정값이 아니다. [MedVision v2 §3–4](https://arxiv.org/html/2511.18676v2)

공식 BiomedParse 비교는 pretrained와 detection 적응 모델의 mask를 ellipse 축 길이로 변환해 T/L에서 평가한다. 적응 모델은 V0의 detection 학습 영상과 맞추지만 T/L 전용 supervision까지 동등하다는 뜻은 아니다. 따라서 모듈형 대안의 충분성을 단정할 수는 없어도, segmentation+계산이라는 비교 자체는 이미 존재한다. [공식 비교 설명](https://raw.githubusercontent.com/YongchengYAO/MedVision/master/script/ablation/biomedparse/README.md)

결론적으로 '위치와 산술을 분리해 보자' 또는 '외부 계산으로 수치를 보정하자'는 현재 제안을 별도 진단으로 발주할 근거는 부족하다. 선행의 존재만으로 모든 후속 연구를 금지하는 것이 아니라, 이번 제안의 중심 비교가 중복된다는 판단이다.

## 3. 자료·분할·이용 조건은 실행 가능한 수준으로 확인됐는가?

**부분 확인이며 실행 승인은 아니다.** 논문은 subject 단위 train/test 분할을 설명한다. 공식 코드의 lookup은 dataset, 원본 image filename, slice dimension/index, label을 연결하므로 slice를 독립 환자로 세지 않을 출처 구조는 있다. 그러나 filename이 실제 환자 독립성을 보장하는지는 원천별 확인이 필요하다.

공식 README는 annotation의 CC-BY 4.0과 원천 영상의 별도 이용 조건을 구분한다. 일부 자료에는 token이 필요하며, T/L annotation에는 spacing·orientation·cache 관련 버전 변경도 기록돼 있다. 공개 annotation만으로 모든 영상의 즉시 사용 가능성이나 최신 split 정합성을 확정할 수 없다. [공식 자료·버전·이용 안내](https://raw.githubusercontent.com/YongchengYAO/MedVision/master/README.md)

Hugging Face README의 raw URL 조회는 도구 오류로 내용을 받지 못했다. 이를 자료 이용 불가능으로 해석하지 않는다. 다만 2번에서 현재 후보의 투자 근거가 부족해졌으므로 원천별 다운로드·이용 조건의 전수 확인은 중단했다. 이 미완료 확인을 별도 CPU 준비 반복으로 넘기지 않는다.

# Strategy Check / 연구 방향 판단

round_01은 기존 실제 결과를 유지하면서 인접 측정 질문의 진입 가능성을 검토했다. 이번에는 그 후보를 보류할 근거가 생겼다. 해결된 질문은 현재 제안의 오류 분해가 선행과 구별되는지이며, 답은 구별 근거 부족이다.

이제 남은 판단은 다른 성격이다. 기존 직접 SFT와 공동 형식 학습은 실제 개선을 보여줬다. 그러나 추가 loss와 현재 과제의 실용 이점은 확보하지 못했다. 이것은 현재 설계의 보류 근거이지만, 데이터 효율·적응 비용·능력 보존 같은 다른 기여 축의 부재를 증명하지 않는다. 반대로 평가하지 않은 축을 나열하는 것만으로 새 방법을 발주해서도 안 된다.

다음 전략 판단에서는 다음 두 선택을 비교한다.

- 기존 적응 자산을 이용해, 강한 직접 SFT 이후에도 남는 **데이터 효율 또는 능력 보존의 구체적 문제**를 최소 방법 시험으로 다룰 수 있는지 확인한다. 기존 형식 효과·단순 gate로 설명된 현상을 일반적 forgetting으로 재포장하지 않는다.
- 그러한 문제가 실제 관찰과 가까운 선행의 차별성으로 연결되지 않으면, 현재 연구 묶음의 투자를 보류하고 GOAL 안의 다른 중요한 질문을 선택한다. 새 benchmark에서 낮은 점수만 확인하는 진단을 다시 기본 경로로 삼지 않는다.

다음 판단에는 `iter_012/014`의 실제 학습 조건과 비교, `iter_016/042/048`의 보존·형식 효과 원 리뷰가 직접 관련된다. 이 원문과 가까운 adaptation 선행을 대조해 방법 시험의 근거 또는 전환 근거를 명시해야 한다. 내부 원인이나 논문 수준의 일반화를 pilot 전에 요구하지 않되, 중요한 실제 문제와 단순 대안의 부족함은 필요하다.

이번 후보의 종료 결정은 완료했다. 추가 라운드를 요청하는 이유는 같은 측정 정의를 더 조사하기 위해서가 아니라, 핵심 기여와 후속 학습 투자 방향을 선택해야 하기 때문이다.

# 보존·실행 경계

새 limitation을 등록하거나 기존 상태를 바꾸지 않는다. 코드 반입·수정·설치·자료 다운로드·GPU 실행은 수행하지 않았다. 기존 checkpoint의 보존과 재사용 승인은 구분한다. 실행 경로가 선택되지 않았으므로 무관한 gate·비용 집계 코드를 정비하는 반복도 만들지 않는다.

iter_050의 일시적 담당 전환과 감사 인계는 round_01 및 직전 리뷰에서 확인한 완료 범위를 유지한다. 이를 새로운 재개 작업으로 발주하지 않는다. 현재 구현 담당은 Claude다.

# 대규모 GPU 필요 후보

다양한 modality의 segmentation·landmark·물리량을 함께 감독하는 encoder–projector–decoder 공동 적응은 장기 후보로 보존한다. 이번 검토는 그 필요성이나 우위를 입증하지 않았다. 두 RTX 3090에서 가능한 경량 적응 연구보다 우선할 근거도 아직 없다.

이번 문헌 확인은 조사 근거이며 사용자 논문 추천이 아니다.

## 다음에 파고들 질문
- iter_012/014의 직접 SFT 학습 조건과 iter_016/042/048의 원 리뷰를 대조했을 때, 형식 적응·단순 gate·직접 공동 SFT로 설명되지 않은 데이터 효율 또는 능력 보존 문제가 실제로 남는가? 없다면 기존 자산 기반 방법 시험을 선택하지 않는다.
- 남는 실제 문제에 대해 가장 가까운 적응 방법과 강한 직접 SFT를 구별할 최소 개입·동일 비용 비교·외부 평가가 가능한가? 관련 공식 논문·코드와 현재 checkpoint 자산을 확인해, 방법 pilot 또는 현재 연구 묶음 보류 중 하나를 결정한다.
- 기존 자산 기반 방법 시험의 근거가 부족하다면 GOAL 안에서 어떤 다른 사용 과제가 더 높은 정보 가치를 갖는가? 새 모델의 낮은 benchmark 점수보다 방법 개발로 연결되는 실패 조건·단순 대안·접근 가능한 자료를 기준으로 하나를 선택한다.
