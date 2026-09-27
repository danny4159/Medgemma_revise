# 요약

- **판정:** execution_failed, valid_experiment=false. 실제 환자 실험은 미실행이다.
- **핵심 근거:** 회귀 검사 27/27 통과 기록은 있지만 images.zip은 유효한 ZIP이 아니며 D8/E48/F 출력이 없다.
- **의미·한계:** 좌표 처리의 부분 수정은 보존할 가치가 있다. 모델 한계·성능 개선·신규 기여는 판정할 수 없다.
- **다음:** 다운로드와 필수 검증을 완성하고 기존 D8→E48→조건부 F 계획을 이어간다.

# Assessment

계획·구조화된 계획·보고서·changes.patch·commit.json·reuse_manifest.json과 관련 소스·결과·실행 로그를 직접 확인했다. 리뷰 대상은 `5720d0c82da88c67af5843554afd1791308c6007`이다. HEAD가 이 SHA와 같고 변경된 13개 파일의 작업 트리 내용도 커밋과 일치했다. git status와 현재 diff는 비어 있으며 unpreserved_paths는 없다. 변경 검토에는 저장된 구현 전후 diff를 사용했다.

이번 호출은 구현과 다운로드 준비에서 끝났다. Claude stream의 result는 subtype=success지만 이는 호출 종료 상태다. 마지막 응답은 background 다운로드 알림을 기다리겠다는 내용이며, 연구 실행 완료를 의미하지 않는다. 별도 execution_amendment.md는 결과 목록에 없다. 선별 반입 요청도 없어 reuse_manifest의 추가 필수 검사는 없다.

# Key Findings

1. `results/iter_020/tests/fixtures_mri.json`에는 27/27 통과가 저장돼 있다. identity·축 순열, 실제 `107_t2.mha` mask의 sagittal 축, slice 추출, 렌더링 shape와 NCC padding 검사가 포함된다. 실행 로그에서 해당 테스트 호출도 확인했다. 리뷰 중 테스트나 GPU 실험을 대신 실행하지 않았다.
2. NCC 수정은 padded PNG에 비padded 좌표를 적용하던 문제를 바로잡는다. top=35인 fixture에서 예측 원본 위치 row=10, col=150과 scale=1.0이 저장된 정답과 일치했다. 이 범위의 모듈 재사용은 승인한다.
3. `gate.json`의 210명은 mask 기반 후보 수다. 최종 image/mask 검증과 manifest·split이 없으므로 적격 N 또는 독립 평가 표본 수로 보고하면 안 된다.
4. 리뷰 시점 images.zip은 3,700,562,886 bytes지만 `zipfile.is_zipfile`은 false였다. progress에는 40개 범위, 2,684,354,560 bytes가 완료로 기록돼 있다. downloader가 먼저 전체 길이를 할당하므로 파일 크기는 완료 증거가 아니다. 기록되지 않은 최근 진행이나 background 프로세스의 생존 여부는 이번 리뷰에서 확정하지 않았다.
5. 작은 파일 세 개의 MD5 일치 기록은 `download_check_small.json`에 있다. images.zip의 최종 checksum·CRC 완료 기록과 환자 입력·생성·평가 산출물은 없다.

# Problems / Concerns

현재 과학적 결론을 막는 문제는 환자 실험 미실행과 자료 미완성이다. 다음 결함은 재사용 전에 해결해야 한다.

- **다운로드:** `_fetch_chunk`는 Content-Range와 객체 validator를 확인하지 않는다. progress는 크기와 완료 범위만 저장한다. `download`는 최종 checksum을 강제하지 않고 pwrite 반환 길이도 검사하지 않는다. 실행 로그의 후속 hash 출력 예정만으로 검증 완료를 인정할 수 없다.
- **자료·방향:** sagittal 축 선택은 개선됐지만 비등방 spacing·origin을 포함한 독립 index→physical 검증과 실제 image/mask overlay가 없다. 연결성·중복 검사도 없다. `select_patient_pair`는 계획의 후보별 SHA 순서 대신 여전히 hash modulo를 사용한다.
- **표본 처리:** manifest가 build 성공 환자로 split을 만드는 수정은 유용하다. 그러나 모든 예외를 errors로 모은 뒤 나머지 환자로 진행할 수 있어 구현 오류에 따른 표본 변경을 차단하지 못한다.
- **provenance:** protocol은 필수 코드를 늘렸지만 source·gate 등 필수 자료를 강제하지 않는다. 요청 로더는 ID와 prompt hash를 재계산하지 않으며 pipeline은 기존 요청 파일을 존재만으로 재사용한다. S2 protocol은 S1 원시 파일과 선택 record를 잠그지 않는다.
- **실행·평가:** phase1 실패 시 S2 중단과 직접 호출 경로의 SIGTERM handler는 추가됐다. 그러나 E/F의 선행 gate를 강제하는 코드가 없고 completion 내용의 성공 상태를 확인하지 않는 재사용 경로가 남는다. 24개 재개 검사와 변경된 evaluator의 독립 수치 검증도 미실행이다.
- **보고:** 보고서가 영어 대기 안내와 권한 거부 목록으로 끝난다. 실제 미완료 상태·후속 작업·종료 코드가 담긴 한국어 보고가 필요하다. 권한 거부의 정확한 운영 원인은 기록 범위에서 확정할 수 없으며, 금지된 동작을 다른 수단으로 우회해서는 안 된다.

# Interpretation

정상 사용 조건을 검증한 뒤 한계를 주장하라는 사용자 보완은 계속 유효하다. 이번에 실제 모델 출력을 확보하지 못했으므로 LIMITATIONS의 상태를 바꾸지 않는다. mask 후보 210명과 테스트 통과는 모델 능력의 증거가 아니다.

CPU 준비에서 끝난 실제 blocker는 미완성 영상 archive와 남은 자료·실행 검증이다. 두 GPU의 낮은 활용 자체를 기각 사유로 삼지 않는다. 다만 준비가 끝나면 실제 D 요청의 처리량·메모리·출력 정합성을 비교하고 계획된 환자 평가로 진행해야 한다. 이전 합성 메모리 수치만으로 4 worker를 승인할 수 없다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 해석 가능한 환자 실험 0회다. 이번 반복을 유효 실험 재평가 횟수에 더하지 않는다.
- **성능 개선:** 비교할 실제 출력이 없어 미확인이다.
- **가설 지지:** 동일한 다른 인스턴스로 반복 오인하는 H 사건은 측정되지 않았다. 가설을 지지하거나 약화하지 않는다.
- **신규 기여 가능성:** 미확인이다. 구현 수정은 연구 방법의 contribution이 아니다.

iter_019/020의 전략 판단을 유지한다. 현재 grounding에 새 loss를 투입할 근거는 부족하고, 다른 임상 질문은 자료·설계 비용이 추가된다. 이미 정한 reference 진단을 복구하는 것이 우선이다. 두 번의 실행 실패만으로 설계를 포기하지 않되, 자료 접근·정상 사용 gate를 확보할 수 없다는 구체적 근거가 생기면 질문 전환의 정보 이득을 다시 비교한다. 같은 CPU 준비만 반복하는 계획은 피한다.

이번 방향에는 실제 출력의 긍정적 근거가 없으므로 논문 추천을 보류한다. 연구 마일스톤으로도 기록하지 않는다.

# Recommended Next Experiment

실행 호스트에서 기존 작업의 소유권·생존·종료 상태부터 확인한다. 원본 부분 archive와 checkpoint를 보존하고 최종 checksum·SHA256·ZIP CRC가 확인되는 자료 복구를 완료한다. 위 재사용 결함을 실제 사용할 경로에 한정해 해결한다.

그 뒤 실제 overlay·중복·연결성 검증을 마친 적격 N과 D8/E48/F를 고정한다. N<56이면 모델 능력 판정 없이 자료 식별성 부족으로 종료한다. 충분하면 D8 공식 입력 대조·출력 길이와 형식 gate·24개 재개 검사·두 GPU 처리량 비교를 통과한 뒤 E48을 실행한다. F는 원래 확대 조건을 만족할 때만 실행하며 가설·metric·성공 기준을 바꾸지 않는다.