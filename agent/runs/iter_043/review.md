# 요약

- **판정:** 유효한 실험이지만 `inconclusive`다. 원 계획대로 현재 영상 구별 방법 투자를 보류한다.
- **핵심 근거:** 개발 V96에서 C−retrieval F1@0.3은 +0.1488 [0.0755, 0.2257]이다. 동일 문장 21쌍의 B는 0.1667 [0.0147, 0.2917]로 사전 경계 0.10을 가로지른다. 모두 97.5% CI다.
- **의미·한계:** 선택한 문장 retrieval만으로 C의 성능을 설명하기는 어렵다. 중요한 환자별 구별 결함이나 새 방법의 필요성은 확정하지 못했다.
- **다음:** 진단 표본을 늘리지 않고 강한 모듈형 비교군 확보를 우선한다. 코드 전체 재사용은 보류하고 검증된 모듈만 승인한다.

# Assessment

`valid_experiment=true`, `approach_status=inconclusive`, `verdict=CONTINUE`다. 신규 MAIN 출력은 M0/C 각각 text-only 192건과 영상 교환 42건, 총 468건이다. 기존 실제 영상 384건을 재사용했다. 신규 학습과 독립 확인은 미실행이며 계획과 일치한다.

리뷰 대상은 `b50aa230a86c6d5b6c6b280fe718170ce4ecf220`이다. commit.json의 21개 파일 모두 현재 작업 파일과 일치했고 unpreserved_paths는 비어 있다. changes.patch와 신규 코드, 반입 12개 파일의 원본 blob을 대조했다. execution_amendment는 없다.

원 계획의 양성 기준 중 retrieval 경쟁력과 낮은 B 상한이 모두 실패했다. 음성 기준 중 C−P 하한>0.03은 통과했지만 B 하한>0.10은 실패했다. 따라서 `inconclusive_hold`는 올바른 종료 판정이다. 계획된 비교를 완료했다는 사실을 가설 확증이나 method success로 바꾸지 않는다.

# Key Findings

## 원시 수치 검증

리뷰에서 기존·신규 원시 출력 768건을 읽고 별도 matching 구현으로 문장별 F1@0.3/0.5를 재계산했다. parser 보조 함수는 소스를 확인한 뒤 사용했고, 문장별 저장 점수 불일치는 0이었다. retrieval은 별도 TF-IDF 구현으로 확인했다.

| 조건 | 환자 평균 F1@0.3 | F1@0.5 |
|---|---:|---:|
| M0 실제 영상 | 0.09844 | 0.01302 |
| C 실제 영상 | 0.57795 | 0.29115 |
| train-only retrieval P | 0.42917 | 0.17622 |
| M0 text-only | 0.17361 | 0.00868 |
| C text-only | 0.33142 | 0.09896 |

환자 bootstrap 10,000회·seed4302로 C−P=0.1487847, 97.5% CI [0.0755208, 0.2256944]를 재현했다. C의 text-only 감소는 0.24653이며 valid율은 실제 영상 100%, text-only 99.48%다. 단순 invalid 증가만으로 이 차이를 설명할 수는 없지만, modality 제거는 학습 분포 밖 개입이므로 내부 시각 기여의 크기를 직접 분해한 결과는 아니다.

동일 문장 21쌍·17 cluster에서 C의 F1@0.5는 원래 영상 대 recipient GT 0.5000, 교환 영상 대 recipient GT 0.3333, 교환 영상 대 donor GT 0.5000이다. 별도 matching과 cluster bootstrap으로 B=0.1666667, 97.5% CI [0.0147059, 0.2916667]을 재현했다. 교환 출력은 모두 valid·nonempty였지만 사전 음성 기준의 최소 차이 0.10을 하한으로 넘지는 못했다.

## 입력·정상 사용·출처

- MAIN 각 234건에 대해 완료 검증을 다시 실행했다. 요청 집합, record·protocol·config·adapter 및 현재 영상 hash 연결이 통과했다.
- 기존 M0/C I-short 각 192건의 import 검사를 수행하고, helper가 빠뜨린 protocol 파일 digest→completion 및 record config 연결도 별도로 확인했다.
- V96 영상 96개의 현재 file/pixel hash를 확인했다. T305/D24/V96 사이 환자·study·영상·pixel hash 교집합은 모두 0이었다.
- 동일 문장 쌍, donor 영상, recipient 질의와 GT의 분리 및 실제 입력 영상 affine을 사용하는 역변환을 확인했다. GT는 생성 prompt에 들어가지 않는다.
- text-only는 공식 template의 텍스트 경로를 사용하며 image token 0, pixel_values 부재를 기록한다. D8에서 기존 실제 영상 출력과 token 일치, self-swap 일치가 확인됐다.
- greedy와 caps 1000/2000/4000이 유지됐다. MAIN M0는 8건에서 길이 재시도를 했고 C는 재시도가 없었다. invalid와 비EOS를 평가에서 제외하지 않았다.
- report의 source·manifest·selection hash는 현재 파일과 일치했다. 이전 정상 사용 검증은 동일 반입 소스 범위에서 재사용했으며 이번 리뷰가 GPU 공식 예제를 다시 실행한 것은 아니다.

## 자원·완료

C의 공통 D8 40요청에서 2→4 worker 처리량은 15.93→26.55 req/min으로 증가했고 p95 요청 wall은 9.71→9.38초였다. 리뷰에서도 두 구성과 재개 결과의 token 불일치 0을 확인했다.

MAIN은 GPU 두 장에 각 2 worker로 완료됐다. 관측 최대 GPU 점유는 M0 17,860/17,711 MiB, C 17,836/17,765 MiB로 현재 조건에서 GPU당 두 worker의 4 GiB 여유를 충족했다. MAIN wall 합은 약 53.75분이다. D8·재개·부분 실행까지 기록된 launcher wall 합은 약 68.82분이며 CPU 준비 시간과 별개다.

계획 기본 564요청에 self-swap 및 재개 검사가 추가돼 완료 요청은 620건이다. MAIN 468건의 과학적 표본은 유지됐다. M0의 8회 길이 재시도는 추가 생성 비용으로 구분한다.

# Problems / Concerns

현재 수치와 투자 보류 결론을 무효화하는 문제는 발견하지 않았다. 다음 문제는 재사용 전에 수정한다.

1. 평가 소스와 metrics 의존성은 MAIN protocol의 사전 잠금에 포함되지 않았다. report에 사후 hash는 있지만 사전 고정과 같은 보장은 아니다. 도구 기록에서는 평가 코드 작성이 본평가보다 앞섰음을 확인했다.
2. report·per_item은 개별 파일 교체이며 digest로 연결된 최종 completion이 없다. 동시 실행과 중간 실패 보호가 불완전하다. prep·requests의 다중 파일 작성에도 같은 범위의 보완이 필요하다.
3. `pg43_verify.py`의 최종 mean_match 조건은 환자 점수가 다른 시스템을 제외할 수 있다. 현재 결과는 실제로 일치했지만 이 조건을 일반 PASS 판정기로 재사용하면 안 된다.
4. `pg43_gate.py`는 EOS와 parser 상태를 기록하면서 실행 허용 조건에는 포함하지 않는다. 이번 D8은 실제로 통과했으므로 현재 실험 무효 사유는 아니다.
5. 기존 출력 import helper의 protocol/config 연결 일부는 리뷰가 별도로 보완했다. 다음 사용에서는 자동 검증 경로에 넣어야 한다.

보고서 해석도 범위를 줄여야 한다. B@0.3이 작다는 사실은 영상 교환에 출력이 반응하지 않았다는 뜻이 아니다. C의 교환 출력과 원래 출력 텍스트는 42건 모두 달랐다. 또한 cross-F1=1은 GT 좌표의 완전한 동일성을 의미하지 않으며, retrieval 점수는 SFT 성능 중 prior의 인과적 기여 비율이 아니다.

M0 strict parser 실패를 수정한 verify_v2는 기존 pipeline 평가값을 바꾸지 않았고 첫 결과도 보존했다. 다만 parser의 일반적 동등성은 현재 출력 일치만으로 승인하지 않는다. CPU/RAM/I/O 계측과 실제 강제 종료 시험은 미완료다.

# Interpretation

직접 SFT는 이번에 선택한 train-only retrieval보다 분명히 높았다. 이는 해당 단순 baseline으로 C 성능 전체를 설명하기 어렵다는 근거다. 모든 문장 prior를 배제하거나 영상 기반 내부 학습 원리를 증명한 것은 아니다.

환자별 위치 구별은 점추정치가 양수이고 donor 대응도 관찰됐지만, 사전 최소 가치 경계를 넘는 정밀도는 확보하지 못했다. 반대로 영상 구별이 거의 없다는 양성 가설도 충족하지 않았다. 원 contract는 이 경우 추가 환자·문구·seed·reserve로 자동 연장하지 않고 투자를 보류하도록 했다.

기존 한계 주장 중 상태를 바꿀 근거는 없다. 새로운 shortcut 한계를 observed/validated로 추가하지 않는다. 이전 공동 요청 손실과 부재 거부 관찰 및 iter_041 비용 blocker는 그대로 유지한다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 실제 생성과 고정 비교를 완료했고 원시 수치를 재현했다.
- **성능 개선:** C의 retrieval 대비 우위는 확인했다. 이번 반복은 새 방법의 개선 실험이 아니다.
- **가설 지지:** 단순 retrieval 중심 설명은 약화됐지만 중요한 환자별 구별 결함은 미확정이다.
- **신규 기여 가능성:** text-only·영상 교환·retrieval 비교 자체는 contribution이 아니다. 강한 시각적 모듈형 대안 대비 이점과 방법 개입의 추가 가치는 여전히 없다.

`language-conditioned-grounding`의 iter_038 준비, iter_039 진단, iter_040 방법 pilot, iter_041~043 진단을 연결한다. 직접 SFT의 개선, 공동 요청 손실, presence gate의 제한된 작동 범위에 이어 이번에는 특정 문장 retrieval 이상의 성능을 확인했다. 남은 결정적 질문은 강한 모듈형 대안 이후에도 VLM 내부 grounding에 투자할 실용적 이점이 있는가다.

과거 약 4.21시간 생성 wall, 약 2.54 GPU-hours 학습 등은 집계 범위가 달라 이번 68.82분과 단일 GPU 총비용으로 합치지 않는다. 다만 여러 진단을 거친 기회비용은 다음 선택에 반영한다.

사용자 보완에 따른 세 선택을 비교하면 다음과 같다.

1. **iter_041 한정 정정:** 정확도 관찰은 유지되며 비용 판정만 막혀 있다. 26개 worker timing 파일과 V96 C의 세 completion이 남아 있어 재분석 가능성을 확인할 가치는 있다. 그러나 비동기 단회 실행의 interval union·throughput 불확실성이 올바르게 식별되는지 먼저 판단해야 한다. 단순 request latency bootstrap으로 대체하면 안 된다. 정정만으로 공동 직접 SFT의 효과나 새 방법 필요성이 입증되지는 않는다.
2. **강한 모듈형 비교군 확보 — 우선 권고:** 현재 빠진 비교를 직접 해결하고 track 유지 여부를 가장 분명히 바꿀 수 있다. 공식 저장소는 Chest ImaGenome pretrain과 PadChest-GR 적응 checkpoint, inference notebook을 구분해 제공한다. 환경 미설치는 새 사용자 승인 아래에서 반복적인 제외 사유가 아니다. 실제 다운로드·호환성·사용 조건·누수 검사는 다음 실행에서 필요하다. [MedGrounder 공식 저장소](https://github.com/aehrc/MedGrounder)
3. **track 보류·전환:** 공정한 모듈형 비교의 남은 정보 가치보다 구축·적응 비용이 크거나, 비교 후 중요한 잔여 이점이 없으면 선택한다. 현재는 실행 가능한 공식 경로를 실제로 시도하기 전에 주변 진단으로 이동할 근거가 약하다.

따라서 현재 shortcut 교정 방법은 보류하고 모듈형 비교를 위한 한정 보완을 우선한다. 비교군 준비만 계속하는 별도 setup 반복을 목표로 삼지 않고, 동작 확인 후 사전 고정한 실제 비교와 종료 판단까지 연결한다. 이번 방향의 방법 투자 결과가 불확정이므로 논문 추천과 마일스톤 등록은 보류한다.

# Recommended Next Experiment

다음 deep 계획은 강한 문장 조건부 모듈형 baseline과 기존 C의 공정한 비교를 구체화한다. 공식 환경을 git 제외 경로에 격리하고, Python·CUDA·패키지·checkpoint 출처와 학습 중복을 확인한다. PadChest 적응 checkpoint를 비누수·동일 budget 비교군으로 잘못 사용하지 않는다. 비적응 checkpoint의 zero-shot 결과도 C와 적응 예산이 다름을 명시한다.

D 자료에서 입력·좌표·후처리와 처리량을 확인하고 설정을 고정한 뒤, 보호된 reserve를 열지 않는 개발 비교를 수행한다. 정확도·FP·latency·메모리에서 무엇이 다음 투자 선택을 바꿀지와 종료 조건을 먼저 정한다. 비교가 실용적 잔여 이점을 보여줄 때만 최소 방법 시험을 검토한다. 이점이 없거나 한정 비교 뒤에도 중요한 판단이 남으면 track을 보류하고 GOAL 안의 다른 질문으로 전환한다.

iter_041 비용 정정은 원 판정과 blocker를 보존한 별도 결과로 처리한다. 원자료로 충분한지 먼저 확인하고, 필요할 때만 최소 재측정 비용을 비교한다. 이번 21쌍의 추가 진단이나 joint SFT·새 loss를 이미 결정된 후속 과제로 두지 않는다. VinDr 승인 통지 전 다운로드·외부 평가는 하지 않으며 RSNA 자산과 H192/F120/test/MRI reserve를 유지한다.