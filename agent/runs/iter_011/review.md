# 요약

- **판정:** CONTINUE / execution_failed. 학습·부분 평가는 수행했지만 계획한 가설 검증은 미완료다.
- **핵심 근거:** CPU 검사 기록은 59/59·70/70·54/54 PASS, 실제 GPU 복구 검사는 25/30 PASS다. 두 LR 모두 step 300까지 기록됐지만 epoch 2 validation은 미완료다.
- **의미·한계:** epoch 1 실제 생성은 확인했다. 같은 평가 집단의 baseline 비교와 3개 seed 독립 확인이 없어 SFT 개선을 주장할 수 없다.
- **다음:** 실행 상태와 복구 정확성을 확인하고 선택·완료 검증을 보완한 뒤 원래 규모를 끝낸다. 보고서의 LR별 수치도 정정한다.

# Assessment

리뷰 대상은 `8b030717b813bcbff85a2ffc5f52c9561a73f452`다. plan.md·plan.json·changes.patch·commit.json, 구현 소스, 실제 결과와 실패 관련 stream 구간을 읽었다. execution_amendment.md는 발견하지 못했다. 변경 소스 16개는 해당 SHA의 blob과 현재 파일이 일치했고, main_protocol.json에 기록된 파일 hash도 모두 일치했다. `reuse_manifest.json`에는 반입 요청이 없다.

이번 계획은 SFT의 실제 생성 개선을 검증하는 method다. 복구 검사와 첫 epoch validation만으로 그 가설을 완료했다고 볼 수 없다. 계획 자체도 실행 미완료를 execution_failed로 정한다. 접근법의 유효 실험 횟수는 증가시키지 않는다. read-only 리뷰에서 파일 수정, 테스트 재실행, GPU 실험은 하지 않았다. 기존 산출물을 읽고 hash·요청 수·metric을 별도로 대조했다.

# Key Findings

1. **복구 기능은 일부 확인됐다.** `fixtures_iter011_gpu.json`에서 같은 run-dir 중복 실행 거부, ID 변경·중복 거부, 마지막 epoch validation 복구가 통과했다. 중간에 끊긴 epoch 2 validation은 기존 3건을 유지하고 남은 5건만 생성했다. 부모 checkpoint는 두 LR 모두 step 100이며 이후 부모 로그 21/7 steps를 유효 이관 경로와 구분했다.

2. **epoch 1 결과는 원시 응답으로 재확인했다.** 각 LR의 JSONL은 고정 validation 집합과 정확히 일치하는 400개 고유 요청이다. 현재 400개 영상의 file/pixel hash 불일치는 0이었다. 별도 JSON 파싱과 IoU matching 집계에서 다음 수치를 얻었다.

| LR | 양성 200명 F1@0.3 | utility | 전체 유효 출력 |
|---|---:|---:|---:|
| 1e-4 | 0.474000 | 0.589500 | 400/400 |
| 2e-4 | 0.493167 | 0.599083 | 400/400 |

두 run 모두 Normal의 valid_empty는 93/100, NoOpacity/NotNormal은 48/100이다. 후자의 52/100 추가 box는 후속 비교에서 살펴볼 관찰이지만, 아직 같은 집단의 concise base 대비 악화 여부는 판단할 수 없다. STATUS.md와 stream 상세 보고서의 LR별 점수·loss는 서로 뒤바뀌어 있다. 원시 결과와 metric 파일 사이에는 이 교환이 없다.

3. **본실험은 미완료다.** 저장된 두 train log의 마지막 optimizer step은 300이다. epoch 2 생성은 LR 1e-4가 29건, LR 2e-4가 4건이며 completion과 metric이 없다. seed29/43, comparator, confirm_result도 없다. 따라서 ‘epoch 2까지 학습 진행’과 ‘epoch 2 평가 완료’를 구분해야 한다.

4. **두 GPU를 실제 활용했다.** launch_children.json은 GPU0/1에 각각 학습 프로세스 하나를 연결한다. resource_log의 sampled 전체 점유 최대는 12,019/11,947 MiB로, 기록된 구성에서는 프로세스당 2GiB 여유가 있다. 학습과 validation을 섞은 추가 프로세스를 피한 선택은 타당하다. 수정 후 4 worker 생성 정합성 검사는 아직 없으므로 추론 단계 진입 전에 확인해야 한다.

# Problems / Concerns

**현재 결론을 막는 문제:** 본학습과 독립 확인이 미완료이며, 복구 수치 gate 5건이 실패했다. 재개 대조의 loss 최대 상대차는 1.951%, adapter 최대 절대차는 0.001670, utility 최대 차이는 0.25다. 부모 이관 loss 차이는 두 LR에서 0.346%/0.609%다.

같은 설정의 추가 무중단 반복에서도 loss 2.471%, adapter 0.002010 차이가 나타났다. 이는 실행 변동 가능성을 뒷받침하지만 재개 동등성의 증명은 아니다. 특히 무중단 반복의 epoch별 utility 최대 차이는 0.125로 재개 대조의 0.25보다 작다. LR 2e-4 부모 이관에는 동등한 추가 통제도 없다. 실패를 유지한 점은 맞지만 ‘모두 GPU 노이즈 범위’라는 원인 단정과 gate 통과 전 본학습 확대는 인정할 수 없다.

**재사용 전 보완:** GPU 검사는 실제 batch ID와 optimizer/RNG 상태를 직접 비교하지 않는다. 중간 optimizer step에서 중단한 동일 시작점 대조를 추가해야 한다. 현재 DataLoader iterator 생성은 별도 generator 없이 수행되므로 CPU RNG 소비까지 포함한 재개 검증이 필요하다. 이것이 CUDA 학습 차이의 원인이라고 확정한 것은 아니다.

`pipeline.py`는 단일 실행 lock이 없고 기존 extend/pick/comparator/final 파일을 존재 여부로 재사용한다. `select.py`의 개별 epoch gate는 개선됐지만 선택 결과에는 protocol 경로만 기록된다. `final_eval.py`는 seed와 adapter digest를 확인하면서도 선택 결과가 현재 protocol 아래 예정 epoch 전체에서 만들어졌는지 재검증하지 않는다. 선택 파일과 comparator를 재사용할 때의 연결 검증을 독립 확인 전에 보완해야 한다. pipeline.py 자체도 protocol 잠금 목록에 없다.

`run_shards.py`는 실패 시 기존 completion을 무효화하지 않고 완료 파일을 직접 쓴다. 최종 evaluator가 여러 오류를 막더라도 pipeline의 존재 여부 기반 건너뛰기와 결합하면 복구를 방해할 수 있다.

`commit.json`에는 `test_rsna_iter010_gpu.py`가 unpreserved_paths로 남는다. 전체 스냅샷 재사용은 승인하지 않는다. 현재 claude_report.md는 짧은 종료 통지로 덮인 상태이며 상세 근거는 stream에 있다. 후속 보고서는 실제 상태와 결과를 자체적으로 담아야 한다.

실시간 ps 조회에서는 해당 프로세스가 보이지 않았지만, 이것만으로 실행 호스트 작업의 종료를 확정하지 않는다. 저장된 마지막 resource log에는 학습 PID가 남고 launch_result.json은 없다. 다음 실행은 소유권과 생존 상태부터 확인해야 한다.

# Interpretation

사용자 보완 지시의 정상 사용 진단은 iter_009에서 충족된 범위를 유지한다. anatomy 전이를 자동 선택하지 않았고 기존 기록·부모 결과도 보존했다. 이번 결과로 기존 한계 주장의 상태를 바꿀 근거는 없다.

실제 SFT 출력과 부분 validation은 확보했지만 직접 적응의 일반화 개선, seed 재현성, 새로운 방법의 contribution은 미검증이다. iter_009와 이번 validation은 서로 다른 집단이므로 점수를 직접 비교해 개선량으로 보고하지 않는다. 재개 실패도 현재 구현·검증 범위에 한정하며 LoRA나 grounding 접근법 전체를 기각하지 않는다.

이번은 iter_010 미완료 계획의 연속이다. 단계별 규모 정책을 소급해 매 epoch validation·3개 seed·확인 800명을 축소하지 않는다. 낮은 utilization이나 장시간 실행을 실패 사유로 삼지 않는다.

# Recommended Next Experiment

실행 호스트에서 train·launcher·pipeline의 PID/starttime, lock, checkpoint와 종료 코드를 확인한다. 살아 있는 작업은 중복 실행하지 않고, 수정이 필요한 경우 소유권을 확인한 안전한 경계에서 전환한다. 기존 결과는 보존한다.

동일 checkpoint에서 무중단·중간-step 재개를 비교하고 batch ID·LR·optimizer·RNG·adapter를 기록해 복구 결함과 실행 변동을 분리한다. 추가 검사의 허용오차와 판정은 실행 전에 정하며 기존 FAIL은 소급 변경하지 않는다. 영향 범위가 확인된 trajectory만 필요한 만큼 재실행한다.

선택 provenance, pipeline 소유권, completion 처리를 보완하고 새 protocol과 기존 결과의 호환 범위를 연결한다. 이후 원래 두 LR 5→8 epoch 규칙과 seed29/43을 완료한다. 수정된 다중 worker 실행기의 development 정합성과 메모리를 확인한 뒤 baseline·checkpoint를 고정하고 confirm 800명을 평가한다. 모든 자식 종료 코드와 최종 산출물을 확보한 후 리뷰를 제출한다.