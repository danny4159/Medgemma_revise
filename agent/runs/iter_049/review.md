# 요약

- **판정:** 준비 결과는 부분 확인됐으나 전체 진입 판단은 `inconclusive`다. 실제 모델 실험은 미실행이므로 `valid_experiment=false`다.
- **핵심 근거:** 원본 7,347행에서 적격 254 case·896장을 독립 재계산했다. 모든 영상의 파일 hash와 지정 환경의 pixel hash가 일치했다.
- **의미·한계:** 자료 확보 장애는 해소됐다. 이력·영상의 정답성 정보 통제가 끝나지 않아 다중 영상 능력이나 새 방법의 필요성은 판단할 수 없다.
- **다음:** 재다운로드 없이 남은 감사를 실제 출력 진단의 진입 gate에 묶는다. 통제할 수 없으면 현재 자료 범위를 보류한다.

# Assessment

계획은 setup이며 GPU 추론·학습 0을 명시했다. 따라서 GPU 미사용은 자원 회피가 아니다. `engineer_backend.json`, `claude_meta.json`, 실제 도구 로그에서 Claude Sonnet/medium의 자료 확보·감사·검사 실행과 종료를 확인했다. 리뷰에서는 파일을 수정하거나 실험을 실행하지 않고 원본을 읽어 검증했다.

리뷰 대상은 `05bd6b0b543ae786a7e250f7502b70db7a6dc7f8`이다. changes.patch의 신규 소스 5개는 현재 파일과 일치했고 unpreserved_paths는 없다. reuse_manifest의 반입 파일도 없다. 저장된 42/42 PASS는 확인했지만 쓰기를 수행하는 테스트 전체를 리뷰에서 재실행하지는 않았다.

# Key Findings

1. `raw/train.jsonl`은 84,240,662 bytes이며 계획의 SHA256 `7b38ceddc9cb1cf3a8dc0f9179c694caf826cd5716bb1b326e71d36e9e7d9b3a`와 일치한다. production 감사 함수를 호출하지 않은 별도 집계에서 N=254, S=896을 재현했다.
2. `image_manifest.json`의 896장 file SHA256은 모두 현재 파일과 일치한다. `/home/test/.conda/envs/medgemma/bin/python`의 Pillow 12.3.0으로 재계산한 pixel hash도 모두 일치한다. 기본 Python의 Pillow 10.2.0에서는 76장이 달랐지만 파일 bytes는 동일했다. 따라서 파일 변조로 볼 근거는 없으며 decoder 환경을 고정해야 한다.
3. case 간 동일 pixel은 없고, 모든 case에 고유 pixel 영상이 둘 이상 있다. RGBA 364장의 alpha는 모두 255였다. 현재 자료에서 투명도 손실 우려는 확인되지 않았지만 후속 RGB 변환 규칙은 기록해야 한다.
4. 영상 subtype은 Plain radiograph 396장, Fluoroscopy 235장, Catheter angiography/DSA 233장, Mammography 31장, 기타 1장이다. chest X-ray 전용 집단으로 해석할 수 없다.
5. 확보한 GitHub 파일은 보존한 tree의 git blob SHA와 일치했다. 공식 wrapper의 MedGemma placeholder는 확인되지만 정확한 평가 prompt·parser·Think-with-Images 실행 조건은 확보되지 않았다.
6. 첫 audit의 zero-padding 오류와 잘못된 N=58 결과는 보존됐고 audit_v2에서 수정됐다. 이번 집계에는 audit_v2만 사용했다.

# Problems / Concerns

현재 자료 집계와 전체 진단 준비 완료를 구분해야 한다. 계획은 영상 내 정답성 주석과 figure 구성을 감사하도록 요구했지만 실제 로그에는 영상 1장 확인만 있다. ICD chapter와 modality 집계는 해부 부위·figure 구성 검사를 대신하지 않는다.

이력의 정답 텍스트 11건·핵심 토큰 3건은 주의가 필요한 실제 사례다. 다만 14건 모두 같은 수준의 확정 누출이라고 쓰면 과장이다. 예를 들어 Case 6456은 정답의 질병 계열을 명시하지만 세부 type까지 직접 쓰지는 않는다. 문자열 미탐지 사례 역시 누출이 없다고 확정할 수 없다. 모델 결과를 보기 전에 정답성 문맥의 범위와 처리 기준을 고정해야 한다.

추론 view 함수는 평가 필드를 제외하지만 저장된 eligible manifest에는 `_eval`과 `_audit`가 같이 있다. 후속 실행기가 이를 통째로 직렬화하지 않도록 물리적 입력 분리와 schema 검증이 필요하다.

재사용 결함은 code_assets와 reuse_issues에 정리했다. 특히 audit 완료 재사용은 raw hash만 비교하고, fetch 경합 경로의 검증이 약하다. 현재 파일은 독립 확인됐으므로 이 결함을 현재 N/S 집계의 무효 사유로 확대하지 않는다.

입력 token 최대 추정 코드에는 options가 빠져 있다. 약 3.6k를 완전한 입력 길이나 메모리 승인 근거로 쓰면 안 된다. MDE 약 0.055–0.110은 미관측 discordance와 독립 case를 가정한 계획용 근사이며, 누출 제외·개발 분리 후 다시 계산해야 한다.

# Interpretation

이번 결과는 공식 자료를 확보하고 제한한 후보 집단을 구성할 수 있음을 보여준다. 모델의 정보 누락, 생성 소견 압축 손실, 원본 재접근 효과는 검증하지 않았다. 새 limitation 등록이나 기존 주장 승격은 하지 않는다.

R2의 중복 선택지 6건 제외는 구현에서 추가된 규칙이다. 모델 성능 확인 전의 자료 정합성 처리이고 현재 주요 집계를 뒤집는 근거는 없지만, 후속 protocol에는 명시해야 한다. 정확한 baseline 실행 조건이 없으므로 후속 실험은 자체 고정 진단으로 보고해야 한다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 자료 확보·CPU 집계는 확인됐다. 과학적 가설의 실제 출력 검증은 없다.
- **성능 개선:** 측정하지 않았다.
- **가설 지지:** 공동 판독과 소견 압축의 서로 다른 손실이라는 가설은 미검증이다.
- **신규 기여 가능성:** 원본 재접근·생성 소견 자체는 기존 비교와 가까우므로 개선이 관찰돼도 곧바로 contribution이 되지 않는다.

iter_048의 공동 SFT 회복 관찰과 현재 공동 grounding 투자 보류를 유지한다. 이번 자료 감사는 그 관찰을 설명하거나 반박하지 않는다. RSNA detector 비교의 유효 자산과 VinDr 승인 대기도 유지한다.

같은 language-conditioned-grounding track에서 진단·setup이 누적됐다는 사실은 후속의 정보 가치를 엄격히 볼 이유다. 다만 횟수만으로 기각하지 않는다. 이번 비용은 영상 확보 157.6초·약 65.8MB와 metadata/CPU 감사이며 GPU 비용은 0이다. 전체 track의 누적 비용을 이번 자료만으로 정확히 산출하지는 않았다.

현재 선택은 새 학습보다 확보 자료의 한정 진입 통제와 한 번의 실제 출력 대조가 타당하다. 남은 누출 통제가 불가능하거나 유용한 정밀도가 확보되지 않으면 이 후보를 보류한다. 같은 자료 확보 setup을 자동 반복하지 않는다.

# Recommended Next Experiment

다음 계획에서 기존 자료의 누출·figure 감사, 순수 추론 manifest, decoder/processor 검증을 선행 gate로 고정한다. 통과하면 직접 전체 영상과 text-only를 포함해 소견 압축·원본 재접근·추가 계산량의 경쟁 설명을 구분할 최소 실제 출력 비교를 수행한다. 개발 자료에서 prompt·parser·출력 길이를 고정하고 평가 자료를 보고 변경하지 않는다.

최대 14장 입력에서 메모리와 처리량을 실측하고 두 GPU 배치 및 worker당 여유를 확인한다. 호출 수 비율 5.53을 비용 비율로 오인하지 않고 device-seconds·latency·token을 측정한다. 실제 정밀도와 최소 가치 있는 효과에 따라 규모와 종료 행동을 사전 고정한다. 단순 대조가 충분하면 보류하고, 중요한 잔여 문제가 확인될 때만 최소 방법 시험을 검토한다.

실제 출력의 긍정적 연구 근거가 없는 setup이므로 논문 추천과 milestone은 보류한다.