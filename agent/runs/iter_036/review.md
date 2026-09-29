# 요약

- **판정:** 유효한 부분 진단이며 `improve / CONTINUE`다. 핵심 수치는 재현됐지만 계획한 진단 완료 요건은 일부 남았다.
- **핵심 근거:** SFT-only GT 중 threshold 제외는 detector17에서75/77개, detector29에서80/87개다. 대응 후보가 없는 잔여량 R은1/589·7/589이고 두 CI 상한 모두5% 미만이다.
- **의미·한계:** 큰 후보 발견 차이라는 설명은 약화된다. 낮은 score 후보의 존재가 실제 검출 개선이나 confidence 교정 성공을 뜻하지는 않는다.
- **다음:** 저장 출력으로 빠진 FP 비용 비교와 출처 검증만 보완한다. 새 loss·ensemble에 자동 투자하지 말고 다음 연구 질문을 선택한다.

# Assessment

리뷰 대상은 `f9bfbc250058ce1785f819dd404b1148998918b9`이다. commit.json·changes.patch·신규 소스3개·결과 JSON·관련 실행 로그를 확인했다. 신규 파일은 해당 SHA와 bytes가 일치하고 unpreserved_paths는 없다. reuse_manifest는 빈 요청이며 별도 반입 승인은 없다.

이번에는 실제 저장 출력의 가설 검증을 수행했다. 새 GPU 추론·학습은0이며 이는 실험 미실행을 뜻하지 않는다. 원시 detector1,600건과 SFT2,400건을 이용한 진단은 유효하다. 조건부 GPU 추적은 사전 기준 미충족으로 적절히 생략했다. Claude 로그는 최종 result success로 끝나지만 보고서의 SELF_CHECK는 FAIL이다. 이를 가설 기각이나 연구 완료로 바꾸지 않는다.

기준 iter_035 plan SHA256은 계획에 적힌 `463b95001116ec77bc64c8a95fa33cf7c948ca3e582f498732a8290ea1cacd15`와 일치한다. 완료된 학습·continuation을 반복하지 않았고 사용자 지시의 RSNA 비교 범위를 유지했다.

# Key Findings

## 독립 수치 검증

리뷰에서 원시 SFT suffix를 별도 JSON 해석하고 detector pixel xyxy를 별도로 정규화했다. 자체 IoU와 열거 matching으로6개 detector×SFT 조합을 재계산했다. 환자 bootstrap10,000회·seed20260929의 비율 CI도 별도로 계산했다.

| 비교 | 대응 경쟁 | threshold 제외 | 인접 위치 오차 | IoU0.1 미만 coverage 부재 | SFT-only |
|---|---:|---:|---:|---:|---:|
| det17–SFT17 | 1 | 75 | 1 | 0 | 77 |
| det17–SFT29 | 1 | 77 | 1 | 0 | 79 |
| det17–SFT43 | 0 | 82 | 1 | 0 | 83 |
| det29–SFT17 | 0 | 80 | 7 | 0 | 87 |
| det29–SFT29 | 0 | 84 | 5 | 0 | 89 |
| det29–SFT43 | 0 | 82 | 6 | 0 | 88 |

全 조합의 범주 수와 저장 CI가 일치했다. 주비교 R의97.5% CI는 det17 `[0, 0.006768]`, det29 `[0.003367, 0.022375]`다. threshold 제외 비율 CI는 각각 `[0.926829, 1]`, `[0.85, 0.977011]`다. GT·prediction 순서를 뒤집어도6개 조합의 검출 GT 집합은 바뀌지 않았다.

기존 detector F1@0.3/0.5도 det17 `0.581643/0.415548`, det29 `0.573917/0.406417`로 재현했다. IoU0.3 전체 FP는236·219개였다. cap100 도달은0건이고 최대 저장 후보 수는28·22개다. R 영향 환자1·7명, CI 상한5% 미만이므로 이번 GPU 미진입 결론은 타당하다.

## 출처와 정상 사용

선택 LOCK의5개 파일 hash, 두 detector checkpoint·raw_preds·shard hash를 확인했다. 추론 source digest와 batch1이 유지되고1,600개 shard record의 provenance·입력 연결 불일치는0이었다. 기존 protocol의 입력 manifest·split hash와 현재 개발800 영상 file hash도 일치했다.

SFT3개 seed의 원시 shard provenance는 iter_035 기록과 동일하다. 2,400개 고유 응답의 JSON 좌표와 EOS를 확인했다. 기존 parser·geometry·metric·평가 의존 소스는 직전 검토 SHA와 동일하므로 정상 사용 검증을 해당 범위에서 재사용한다. 공식 GPU 예제를 다시 실행한 것은 아니다.

저장 fixture는18/18 통과다. 리뷰에서 직접 재실행을 시도했으나 기본 Python에는 torch가 없었고 medgemma Python은 read-only 환경의 임시 디렉터리 초기화에서 실패했다. 이를 현재 분석의 실패로 간주하지 않으며, 독립 수치 재계산 완료와 테스트 재실행 미완료를 구분한다.

인접 위치 오차·대응 경쟁·threshold 제외의 대표 overlay3개를 직접 열었다. 좌표 표시를 확인했지만 낮은 score 후보는 그림에 없어 threshold 분류의 근거는 원시 수치에 둔다. 임상 label이나 GT는 변경하지 않았다.

# Problems / Concerns

현재 제한된 threshold 제외 관찰을 무효화하는 문제는 발견하지 못했다. 다만 다음 이유로 전체 계획 완료와 코드 재사용은 승인하지 않는다.

1. **V400 출력 부재 설명이 틀렸다.** `results/iter_012/train/lr2e-4_s17/epoch_05/val_gen/gen_worker0.jsonl`에는 선택된 SFT17 adapter digest와 일치하는400건이 있고 ID 집합은 validation_ids와 같다. completion도400건·missing0·duplicate0이다. 개발800 D24 대체는 실제 절차 이탈로 기록해야 한다. 이미 개발 자료인800명의 결과를 자동 무효화하지는 않지만 사전 validation 검사를 완료했다고 볼 수 없다.
2. **자동 출처 검증이 부족하다.** loader의 LOCK 검사 주석과 구현이 다르다. 현재 값은 리뷰에서 따로 확인했지만 이후 입력에서는 source·영상·batch·box/score/label 길이·유한성을 강제해야 한다.
3. **FP budget 비교가 미완료다.** 기존 iter_035 표에는 det17의 일부 비용 근거가 있다. validation budget0.25/0.5/1.0에서 개발 FP/환자는0.25375/0.45125/1.0075, 양성 F1@0.3은0.573976/0.622250/0.584433이다. 이번에 요구한 양쪽 detector·두 IoU·category·상보성의 전체 비교를 대신하지는 않는다.
4. **위치 변화의 표현을 정정해야 한다.** 보고된71.5%·56.7%는 IoU0.3에서 검출된 GT가0.5 독립 재매칭에서도 검출되는 비율이다. 동일 prediction–GT 쌍의 통과율과 별도 표로 구분해야 한다. GT별 candidate index·최고 score·원래 대응쌍도 산출물에 보존되지 않았다.
5. **일반 재사용 경로에 결함이 남는다.** cap 존재 시 criterion_b가 GPU 결정에 반영되지 않는다. 독립 검증기는 고정 결과를 덮어쓴다. FP 중복과 경쟁을 합친 변경도 명시해야 한다. 현재 cap0과 검증된 원본에서는 핵심 결론을 바꾸지 않는다.

# Interpretation

사전 음성 기준인 두 detector의 R CI 상한5% 미만과 threshold 제외 비율 CI 하한0.5 초과를 충족했다. 따라서 현재 SFT-only의 큰 부분을 detector 후보 발견 부재로 설명하기는 어렵다. H_selection은 제한된 범위에서 지지되고 큰 H_residual 설명은 약화된다.

R은 IoU0.3 대응 후보 부재다. 더 느슨한 IoU0.1 미만 범주가0이라는 사실과 혼동하면 안 된다. R은 실제로1개·7개이며, 'detector가 사실상 아무것도 놓치지 않는다'는 표현은 과도하다. 낮은 threshold에서 증가하는 FP, 일대일 검출과 다대일 coverage의 차이, post-NMS 관측 한계가 남는다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 기존 실제 출력의 주분해와 CI는 독립 재현됐다. validation 사전 검사와 일부 보조 분석은 미완료다.
- **성능 개선:** 새로운 성능 개선은 없다. 이전 detector 정밀도·속도 관찰은 유지하되 후보 coverage를 실용 성능으로 바꾸어 말하지 않는다.
- **가설 지지:** 선택점의 SFT-only 대부분이 threshold 아래 후보와 연결된다. calibration 오류의 원인이나 해결책까지 검증한 것은 아니다.
- **신규 기여 가능성:** 오류 분해 자체는 새로운 방법이 아니다. 큰 후보 발견 차이를 전제로 하는 새 시각 표현 loss·단순 ensemble의 우선순위를 낮출 근거가 생겼다.

현 bbox 방법 개선은 강한 detector 대비 남는 효용을 먼저 요구한다. 추가 진단은 고정 FP 비용에서 실제 판단을 바꿀 최소 비교에 한정한다. 언어·근거 과제로의 전환은 유효한 정답과 강한 모듈형 대안이 있어야 가치가 있다. 같은800명의 세부 층을 계속 늘리거나 승인 대기를 채우는 학습은 권하지 않는다.

논문 추천은 보류한다. 이번에 직접 필요한 오류 분해 문헌 TIDE는 PAPERS.md에서 이미 추천됐고, 새 선택 방법의 유망성은 아직 검증되지 않았다.

# Recommended Next Experiment

기존 계획을 기준으로 미완료 비교와 실제 사용할 코드의 출처 보호만 보완한다. V400 저장 출력의 존재를 정정하고 필요한 회귀 검사에 활용하되, 사전 실행 순서를 소급해서 바꾸지 않는다. 기존800명 주분해·학습·GPU 추적을 반복할 이유는 없다.

고정 FP budget 비교까지 정리한 뒤 현재 방법 개선·최소 선택 진단·언어와 근거가 필요한 다른 질문을 비교해 다음 투자를 정한다. VinDr 승인 통지가 오면 실제 권한·파일·target 차이를 확인하고 외부 계획을 재검토한다. 승인 통지 전 다운로드·외부 평가나 반복 질문은 하지 않으며 continuation·MRI F139·reserve는 보존한다.