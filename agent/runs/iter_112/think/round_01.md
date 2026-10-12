# 사고 라운드 1

# 새로 확인한 것

**전역 존재 확인 후보는 종료하고, 공식 영역 입력 경로를 사용하는 후보만 남긴다. 아직 구현을 발주할 만큼 모델 출력과 평가의 연결이 확정되지 않았다.**

## 이어받는 실제 근거

`agent/GOAL.md`, `agent/runs/iter_111/review.md`, 해당 `review.json`, `agent/LIMITATIONS.md`의 `rsna-global-presence-location-verification`, `agent/CODE_ASSETS.md`의 관련 항목을 확인했다. iter_111은 유효한 음성 결과다. RSNA detector nonempty 226명에서 같은 41명 검토 시 오류 포착은 전역 존재 규칙 30건, confidence 38건이며 양성 위치·coverage 오류는 4 대 15였다. unresolved 네 응답의 16개 배정에서도 음성 방향이 유지됐다. 같은 E600의 순위·검토율·threshold 최적화는 선택하지 않는다.

이번 질문은 같은 track 안의 **새 영역 검증 후보**다. 전역 존재 규칙의 개선이나 iter_108 crop 판독의 재개가 아니다. 시험 설정은 미선정, 연구 관찰은 iter_111 음성 유지, 연구 질문은 영역 조건화가 추가 정보를 주는지 미검증으로 분리한다.

## 공식 지원 범위 확인

1. **CURE:** 공식 README의 지원 과제는 phrase grounding, grounded report generation, 해부구조 이름에 대한 locate/describe다. `Describe the {location}`는 임의 예측 box를 입력받는 검증 인터페이스와 다르다. 따라서 기존 CURE 자산에 좌표를 덧붙여 box 검증기로 사용하는 계획은 선택하지 않는다. base가 `google/medgemma-4b-it`이라는 점도 다시 확인했다. [CURE 공식 저장소](https://github.com/PabloMessina/CURE)
2. **MAIRA-2:** 공식 카드에서 보고서 생성과 phrase grounding을 지원하고 임의 prompt 변화의 성능 저하 가능성을 명시한다. 현재 확인한 범위로는 제시 box 검증기로 채택할 근거가 없다. [MAIRA-2 모델 카드](https://huggingface.co/microsoft/maira-2)
3. **MedRegA:** Region-to-Text Identification은 주어진 box의 구조·병변 이름을 출력하는 실제 학습 과제다. 따라서 임의 좌표 질의를 새로 만드는 것보다 이번 질문에 직접 연결된다. 그러나 소견명 식별은 IoU 경계 오류 판별과 같지 않다. 잘못된 위치에서도 동일 소견을 기술할 수 있고, 부분 중첩 영역에서 소견을 맞혀도 box 전체가 정확하다는 뜻은 아니다. [공식 프로젝트](https://medrega.github.io/), [공식 저장소](https://github.com/xmed-lab/MedRegA)
4. MedRegA 공식 `src/demo.py`는 기본 checkpoint `Luxuriant16/medrega`, InternVL 로더, 동적 전처리 선택, 8-bit 옵션을 제공한다. 파일 누락 시 무작위 영상으로 대체하는 경로가 있으므로 실제 채택 시 반드시 오류로 중단하도록 해야 한다. 공개 코드가 있다는 사실과 두 RTX 3090에서 안전하게 실행 가능하다는 판단은 별개다. checkpoint config 조회는 web 도구에서 Internal Error였으며 이를 가중치 부재나 접근 권한 부재로 해석하지 않는다. [공식 demo.py](https://raw.githubusercontent.com/xmed-lab/MedRegA/main/src/demo.py)
5. **MedP-CLIP:** 논문은 box·point·mask 입력과 영역별 텍스트 정합을 다룬다. 생성문 의미 평가를 피할 수 있는 모듈형 대안 후보지만, 공개 checkpoint·추론 코드·현재 자료의 학습 노출은 아직 확인하지 않았다. 논문 주장만으로 실행 가능한 비교군이라고 쓰지 않는다. [논문 v3](https://arxiv.org/abs/2604.11197v3)

## 현재 선택과 남은 경쟁 설명

후보는 두 계열로 좁힌다. 우선은 **지원되는 영역 입력의 직접 정합 신호**, 대안은 **독립 grounding과 후보 box의 일치**다. 후자는 경계 오류에 더 직접적이지만 영역의 내용 검증과 다르며, 사용자가 요구한 단순 재-grounding 대조에 해당한다. CURE의 해부구조 설명을 임의 box 검증으로 변형하거나 MedGemma에 생소한 좌표 yes/no 질의를 반복하는 선택은 피한다.

기술 질문 → 예측 후보가 실제 소견과 다른 위치를 가리키는 조건 → 공개 box와의 불일치 및 동일 검토량의 추가 오류 포착 → 해당 자료·후보 생성기·영역 인터페이스의 검토 가치라는 범위로 연결한다. 공개 주석과의 불일치는 임상적 소견 부재가 아니다. coverage 누락은 후보 box 하나의 내용 검증으로 직접 해결할 수 없으므로 환자 단위 오류와 box 단위 오류를 섞지 않아야 한다.

현재 미확정인 핵심은 **지원 모델의 출력으로 무엇을 오류 위험 신호라고 정의할 수 있는가**다. 자유 문장의 임상 의미를 다시 판정해야만 성립한다면 이번 범위에 적합하지 않다. 반대로 고정된 소견명 또는 영역–텍스트 score를 사용할 수 있으면 confidence와 비교할 수 있다. 이 선택이 모델·자료·평가·비용을 함께 바꾸므로 구현자에게 넘기지 않고 다음 계획 라운드에서 결정한다.

## 자료·코드 확인과 재사용 경계

현재 research branch의 `git status --short`는 변경을 표시하지 않았다. `git ls-files`로 `ev111_*`, `ev108_spec.py`, `ev109_extract.py`, 일부 `rsna_diag` 순수 함수가 있음을 확인했다. CURE 생성 관련 파일은 현재 branch에 없으며 보관된 다른 commit을 확인해 선별 반입해야 한다. 새 구현으로 대체하지 않는다.

`ev108_spec.py` 원문에서 crop 단독도 원본 영상에 관한 질문을 하는 기존 설정임을 확인했다. 이를 현재 영역 자체의 정합성 검증 출력으로 재해석하지 않는다. `ev111_link.py`의 실제 소스 경로를 확인했으며 detector는 `results/iter_035/confirm800/det17`, 선택은 epoch18·threshold0.70이다. 기존 E600 외에 쓸 환자·노출 여부는 아직 확인하지 않았다. `results/iter_012`와 `results/iter_016/manifests/sets.json`의 존재만 확인했으며 미사용 표본이 확보됐다고 주장하지 않는다.

iter_111 순수 함수 승인은 한정 범위다. gate 적용 후 F1/hit 오류, unresolved 판정 분기, protocol·pixel provenance, 비정사각 축, EOS·응답 독립 검증, 부분 재개 결함을 보존한다. 실제 선택될 경로만 보완한다. 이번 라운드에는 반입 파일·SHA를 확정하지 않았으므로 `reuse_assets=[]`는 코드 재사용 승인이나 누락 파일 재구현 허가가 아니다.

## 다음 라운드에서 결정할 것

MedRegA의 공식 demo 입력·checkpoint 구성·학습 자료를 확인하고, MedP-CLIP의 공식 공개 자산을 한정 확인한다. 그 결과로 하나의 경로를 선택한다. 이어 기존 RSNA manifest에서 E600 및 학습·선택 노출을 구분하고 사용 가능한 개발 표본을 확인한다. 새 도메인 확보나 전수 모델 순회는 하지 않는다.

지원 경로가 성립하면 대표 입력 확인과 작은 실제 비교를 같은 구현 계획에 넣는다. 검토 단위·검토량·confidence 집계·동률·오류 정의·신호 추출·추가 비용·결과별 종료를 사전 고정한다. 양성이면 독립 확인 제안, 음성이면 해당 경로 종료, 불확정이면 판별력 있는 보완의 조건 또는 보류를 명시한다. 현재는 표본 수와 시간을 근거 없이 정하지 않는다.

## 대규모 GPU 필요 후보

영역–텍스트 정합과 위치 오류를 함께 학습하는 대규모 사전학습은 장기 후보로만 기록한다. 기존 region-aware 모델과 단순 대안 이후의 잔여 가치가 확인되지 않았으므로 새 사전학습·방법 개발을 발주하지 않는다.

파일 변경·생성·설치·실험 실행은 하지 않았다. 이번 결과는 지원 인터페이스에 관한 조사이며 새로운 모델 가설 검증이 아니다.

## 다음에 파고들 질문
- MedRegA 공식 demo의 box 표현·출력 규약과 checkpoint config는 무엇이며, 두 24GB GPU에서 지원 경로를 유지해 실행할 수 있는가? 공식 demo_data와 checkpoint metadata를 확인해 채택 여부를 결정한다.
- MedP-CLIP에 공개된 공식 checkpoint·영역 score 추론 경로가 있는가? 있다면 생성문 의미 판정 없이 같은 질문을 검증할 더 적합한 단순 대안인지 판단한다.
- 소견명 식별 또는 영역–텍스트 score를 공개 위치 오류와 어떻게 연결해야 경계 오류와 임상 부재를 혼동하지 않는가? box 단위 주 endpoint와 재-grounding 대조를 확정한다.
- 기존 RSNA manifest에서 E600 밖의 개발 환자와 학습·선택 노출은 어떻게 구분되는가? 실제 사용 가능한 표본에 맞춰 검토량·탐색 규모·양성/음성/불확정 종료 기준과 재사용 파일을 고정한다.
