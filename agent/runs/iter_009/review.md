# 요약

- **판정:** CONTINUE / success. 실제 출력 diagnostic은 유효하며, RSNA 조건의 한계를 validated로 갱신한다.
- **핵심 근거:** 원시 응답에서 공통 위치 불일치 134/200명, 67.0%를 재확인했다. Wilson 95% CI는 60.2–73.1%다.
- **의미·한계:** 방법 개발의 근거를 확보했다. 다른 병변의 일반화 실패·내부 원인·새 방법의 효과는 아직 검증하지 않았다. 전체 코드 재사용은 보류한다.
- **다음:** 실행기 재사용 결함을 필요한 범위에서 고치고, 강한 baseline과 새로운 평가 분할을 갖춘 방법 개발로 진행한다.

# Assessment

계획의 주가설을 실제로 검증했다. 공식·간결 prompt의 양성 유효 출력률은 각각 100%, 96.5%이며 공통 위치 불일치율 CI 하한이 사전 기준 20%를 넘는다. 따라서 valid_experiment=true, approach_status=success다. 이는 diagnostic의 성공이며 최종 연구 목표 달성은 아니다.

사용자 보완에 따라 anatomy→lesion 학습을 자동 재개하지 않고 실제 생성 출력을 검증했다. 변경 diff는 새 rsna_diag 모듈과 노트·테스트 추가이며, 기존 소스 삭제는 없다. execution_amendment.md는 발견하지 못했고, 전체 ZIP 다운로드와 큐 전환은 보고서·노트·호출 기록으로 확인했다.

# Key Findings

1. **체크포인트와 입력 연결:** commit.json의 SHA 39aa49a6fa5943ca0d3e0327a7874e68a2c878cb와 검토 파일이 모두 일치한다. unpreserved_paths는 비어 있다. locked_protocol.json의 모든 파일 hash도 현재 내용과 일치한다.
2. **실제 실행량:** 독립 평가 900건, development 240건을 원시 JSONL에서 확인했다. 각각 고유 요청 수가 기대값과 같고 중복은 0이다. 380개 현재 영상의 file/pixel hash와 1,140개 요청의 입력 pixel/config digest에 불일치가 없다.
3. **독립 집계:** 평가 모듈을 실행하지 않고 원시 최종 JSON과 GT에서 IoU를 별도로 계산해 공통 오류 134/200을 재확인했다. 코드 수정·파일 생성·GPU 실험 재실행은 하지 않았다.
4. **사용법:** 보존된 공식 notebook은 MedGemma 1.5와 yxyx 0–1000 출력을 명시한다. sanity 기록의 4건에서 pipeline/runner 입력 일치를 확인했다. 공식 전처리는 numpy emulation이며 skimage 원문 재현이라고 부를 수 없다. uint8 밝기 보존과 RGBA 처리의 차이를 명시한 점은 적절하다.
5. **성능:** 공식·간결 F1@0.3은 0.147·0.066으로 development에서 선택한 단일 box prior 0.269보다 낮다. 공식−prior 차이의 paired CI는 약 −0.185~−0.060이다. swap 대비 유의한 개선 근거는 없지만 이는 동등성이나 영상 미사용의 증명은 아니다.
6. **자원:** 두 GPU의 worker가 정상 종료했고 본평가 wall은 11,095초다. 기존 iter_009에 새로운 다중 worker 비교를 소급 요구하지 않는다. 다음 본실험부터 처리량 비교와 worker당 메모리 여유 검증을 적용한다.

# Problems / Concerns

현재 결과를 무효화할 결함은 발견하지 못했다. 다만 보고서의 재사용 전 수정 없음에는 동의하지 않는다.

- generate.py는 큐에서 모든 prompt가 완료된 환자를 현재 이미지 hash 검사 전에 건너뛴다. 이번에는 리뷰의 전체 hash 대조가 이를 보완했지만 재개 코드의 검증은 부족하다.
- run_shards.py는 기존 claim을 무조건 삭제한다. 동일 큐의 실행 중 여부를 보장하는 lock이 없으므로 일반적인 재사용에 안전하지 않다.
- evaluate.load_gen은 중복 키를 조용히 덮어쓰고 protocol 연결을 검증하지 않는다. 현재 자료에는 중복이 없지만 다음 실행의 완료 판정에는 강제 검사가 필요하다.
- 데이터 adapter는 ZIP 충돌·mapping 중복을 보고만 한다. DICOM gate와 다운로드 부분 파일 provenance도 새 입력에 적용하기 전에 보완해야 한다.
- legacy 익명 NIH 10장의 환자 중복은 미확인이다. 기록된 167명과의 비중복은 확인됐지만 모든 과거 자료와 완전히 독립이라고 표현하면 안 된다.

58개 fixture 통과 기록은 확인했으나, 이 기록만으로 위 미검증 실행 경로까지 승인하지 않는다. reuse_manifest의 요청 파일은 비어 있어 선별 반입 검증 누락은 없다.

# Interpretation

이번 결과는 공식 anatomy 예제의 성공이나 frozen head 점수를 병변 능력으로 대체하지 않고 실제 생성 bbox의 오류를 보여준다. 양성 잘림과 빈 목록을 위치 오류 분자에서 제외했는데도 오류가 빈번해, 형식 문제만으로 낮은 성능을 설명하기 어렵다.

다만 간결 prompt의 x/y 교환에서 일부 개선 신호가 있으므로 좌표 혼동의 기여가 전혀 없다고 단정해서는 안 된다. GT와의 낮은 IoU는 위치뿐 아니라 box 크기·경계 차이도 포함한다. 직접 본 overlay에서도 큰 예측 box와 중앙부 예측이 확인되지만 임상 재판독은 아니다.

공식·legacy prompt의 음성 100% box 출력은 존재를 전제하는 질문 형식의 영향을 받는다. 이를 일반적인 병변 부재 판별 실패로 확대하지 않는다. RSNA는 NIH 유래 한 과제이며 사전학습 노출·외부 기관 일반화·모델 내부 원인은 미확인이다.

# Recommended Next Experiment

validated limitation을 명시하고, 오류와 연결되는 방법 후보를 가까운 선행 방법 및 직접 병변 경량 적응과 비교해 선택한다. anatomy 전이는 별도 근거가 있을 때만 포함한다. 생성 bbox의 동일 지표에서 공식 prompt·prior·강한 학습 baseline과 비교하고, 실제 방법 contribution과 단순 fine-tuning 효과를 구분해야 한다.

현재 평가 300명은 이후 개발 자료로 표시한다. 새 환자 분할과 추가 데이터셋의 확인 조건을 결과를 보기 전에 고정한다. 다음 본실험 전 development 입력으로 batch 확대 또는 GPU당 복수 worker 중 유망한 구성을 비교하고 처리량·전체 peak VRAM·긴 출력 지연·정합성을 기록한다. CPU 보완만으로 반복을 끝내지 말고, 입력·실행 gate를 통과하면 사전 정의한 GPU 본실험으로 이어간다.