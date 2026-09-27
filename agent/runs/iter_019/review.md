# 요약

- **판정:** execution_failed, valid_experiment=false. 실제 환자 실험은 미실행이다.
- **핵심 근거:** images.zip 다운로드가 종료됐고 파일은 불완전하다. 실제 D8/E48 출력은 없으며 방향·NCC 좌표 결함도 확인했다.
- **의미·한계:** 합성 fixture와 메모리 측정은 준비 근거다. 대상 선택 한계·baseline 성능·새 방법의 필요성은 아직 판단할 수 없다.
- **다음:** 원본과 checkpoint를 보존하고 자료·실행 경로를 보완한 뒤 원 계획의 D8→E48→조건부 F를 이어간다.

# Assessment

계획·plan.json·보고서·changes.patch·reuse_manifest와 관련 소스 및 결과를 직접 확인했다. execution_amendment.md는 검토 목록에 없었다. 리뷰에서는 파일 수정·테스트 재실행·GPU 실험을 하지 않았다. 저장 fixture와 호출 로그를 검토하고, SHA·checksum·ZIP 구조·원본 header를 읽기 전용으로 대조했다.

리뷰 대상은 ff16f12f6fca43e62c5e3ff795456db9200220b2다. commit.json의 32개 소스 파일 모두 작업 폴더와 SHA 내용이 일치했고 unpreserved_paths는 비어 있다. git status와 현재 diff도 비어 있었다. before_sha가 iter_006 기반이므로 changes.patch에는 선별 반입 코드도 추가로 나타난다. 반입 16개 중 generate.py만 출처 blob과 달랐으며 다중 영상 함수 추가를 확인했다. 저장됐다는 사실은 재사용 승인이 아니다.

# Key Findings

1. **자료 확보가 중단됐다.** overview.csv, masks.zip, radiological_gradings.csv의 현재 MD5는 download_check_small.json과 일치한다. masks.zip에는 447개 항목이 있다. images.zip은 1,707,524,096 bytes이며 ZIP 중앙 디렉터리를 읽을 수 없다. 다운로드 완료 checksum 파일도 없다. 보고서는 약 46% 다운로드 중이라고 끝나지만 로그 말미에는 다운로드 task bwv3hm6cq가 killed/stopped 처리됐다. 다음 구현은 완료 알림만 기다려서는 진행되지 않는다.
2. **실제 환자 실험은 없다.** 결과 경로에는 gate, source, 합성 tests만 있다. manifest·split·protocol·환자 gen_worker 결과와 D/E/F 보고서는 없다. D8 96회, E48 576회 및 조건부 F는 모두 미실행이다.
3. **준비 검사는 일부 수행됐다.** 저장 fixture는 MHA 15/15, render 11/11, baseline 6/6, evaluator 13/13이다. chat 검사는 두 영상 tensor 순서 교환과 수동 구성 일치를 보였다. 다만 MHA 물리 방향과 NCC 비영 padding을 검사하지 않아 아래 결함을 놓쳤다.
4. **GPU 실행 자체는 있었다.** 합성 두-image pilot은 48 token, EOS 종료, allocator peak 8.233 GiB, 약 7.14초다. 강제 4000-token stress는 allocator peak 8.241 GiB, reserved 8.313 GiB, 약 305.27초다. 이는 실제 환자 출력이나 다중 worker 처리량 비교가 아니다. GPU 전체 점유·S2 긴 입력·동시 worker 안전성을 인증하지 않는다.

# Problems / Concerns

## 자료 방향과 적격 판정

mi19_data와 mi19_render는 모든 volume을 arr[:,:,x]로 자르고 spacing_x로 간격을 계산한다. 방향 행렬은 기록하지만 slice 선택에 사용하지 않는다. 실제 masks/107_t2.mha는 ASL 방향, DimSize 512×512×17이다. 그런데 gate는 x index 273/285를 선택해 두께 방향의 원본 sagittal slice 쌍이 아닌 단면을 구성한다. 저장 gate의 210개 중 22개에서 첫 축의 좌우 성분 절댓값이 0.5 미만이었다. 따라서 210명 적격·제외 0명은 잠정 mask 계산일 뿐이다.

mi19_mha는 TransformMatrix를 row-major로 반환한다고 명시한다. 공식 MetaIO 문서는 column-major 직렬화를 명시하므로 index→physical 해석을 독립 검증해야 한다. AnatomicalOrientation 문자열만 바꿔도 배열이 재정렬되는 것은 아니다. [MetaIO 공식 규약](https://docs.itk.org/en/latest/learn/metaio.html)

또한 실제 image/mask 정합성, 전체 instance 연결성, 방향별 overlay, 영상 중복 연결요소 및 기관 정보 활용 검증이 없다. pair 선택도 계획의 고정 salt별 SHA 순서와 다르다. 실제 출력 전에 바로잡고 이전 gate를 보존해야 한다.

## NCC baseline 좌표

condition_N은 padded PNG를 읽는다. 그러나 norm_to_canvas는 padding offset을 빼서 원본 좌표를 반환한다. 이 좌표를 padded 배열 crop에 쓰므로 reference template이 이동한다. 검색 결과에는 canvas_to_norm으로 padding을 다시 더해 예측 위치도 이동한다. 기존 fixture는 모두 top=left=0이어서 통과했다. 이 결함은 비교군의 성능과 F 확대 판단을 왜곡할 수 있어 실제 평가 전에 수정해야 한다.

## provenance·재개·평가

mi19_protocol의 extra는 선택사항이므로 필수 자료 잠금을 보장하지 않는다. mi19_pipeline도 REQUIRED_CODE에 없고 S2 protocol에는 S1 completion과 원시 출력 파일이 연결되지 않는다. 요청 로더는 request_id·prompt hash를 재계산하지 않으며 pipeline은 기존 요청을 새로 구성한 기대 집합과 비교하지 않는다. 파일 내부 일관성만으로 전체 계획의 조건 완전성을 보장할 수 없다.

SIGTERM handler는 mi19_run.main에서만 설치된다. pipeline은 main_run으로 직접 호출하므로 해당 보호를 받지 않는다. phase1 실패 후에도 S2 구성·실행을 시도할 수 있다. 실제 부모 종료·worker 강제 중단·tail 복구·greedy suffix 대조 근거도 없다. D gate와 E→F 확대 판정의 강제·저장 경로를 마련해야 한다. paired_diff에는 discordance=0 이항 구간이 빠져 있다.

이 문제들은 과거의 유효한 실험을 무효화하지 않는다. 현재 스냅샷을 다음 실험에 그대로 사용하지 못하게 하는 결함이다.

# Interpretation

이번 중단은 표본 정밀도가 부족한 유효한 실험이 아니라 자료 확보 및 실행 준비 미완료다. 따라서 inconclusive나 가설 기각으로 판정하지 않는다. 합성 GPU 검사로 모델을 불러올 수 있다는 근거는 얻었지만 정상 MRI 사용 조건의 성능 문제는 관찰하지 못했다.

사용자 보완의 핵심인 정상 사용 검증 우선 원칙은 유지해야 한다. 현재 결함을 먼저 고치고 실제 출력으로 검증해야 하며 context-sensitivity 또는 새로운 reference 한계를 validated로 올릴 근거는 없다. limitation_updates는 비워 둔다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 실제 환자 가설 검증 미완료. 준비 검사의 일부만 유효하다.
- **성능 개선:** J/S/A/O/C/N 비교 결과가 없어 미확인이다.
- **가설 지지:** H1과 MRI localization·위치 shortcut·언어 매개 해결이라는 경쟁 설명은 모두 미판정이다.
- **신규 기여 가능성:** reference 정체성 유지의 진단 가치는 계획상 남아 있지만 새 방법의 필요성·차별성은 증명되지 않았다.

iter_019 계획의 전략 비교를 유지한다. 새 loss로 기존 grounding을 개선하거나 다른 임상 질문으로 즉시 전환하는 것보다, 확인된 결함을 해결해 이미 설계한 진단을 완료하는 편이 현재 정보 이득이 크다. 유효한 새 결과가 없으므로 광범위한 전략 재조사를 반복할 이유는 없다. 정상 자료 구성 후 N<56이거나 D gate가 해결되지 않으면 자료·입력 식별성 관점에서 재평가한다. E/F의 음성·양성·불확정 결과에 따른 행동은 원 계획을 유지한다.

실제 긍정적 reference 진단 근거가 없어 논문 추천은 보류한다. 준비 단계이므로 milestone도 부여하지 않는다.

# Recommended Next Experiment

먼저 실행 호스트에서 다운로드와 worker의 PID·소유권·종료 상태를 확인한다. 부분 파일을 보존하고 checksum 검증 가능한 별도 복구 산출물을 만든다. 방향 행렬·sagittal 축·NCC padding·자료 잠금·pipeline 종료와 완전성 검사를 보완한다. 기존 gate와 테스트 결과를 덮어쓰지 않는다.

실제 image/mask 방향·overlay·중복·좌표 왕복 검증 후 표본을 고정한다. 적격 N≥56이면 원래 D8 96회, 24개 고정 요청의 재개 검사와 처리량 비교를 수행한다. GPU 실행 직전 여유 메모리를 확인하고 실제 peak에 worker당 2GiB 여유를 포함해 두 GPU의 2-worker와 안전한 4-worker 또는 batch 후보를 선택한다.

D 통과 후 E48 576회를 수행하고, F는 사전 O 성공률·단순 baseline·H·독립 표본 수·정밀도 조건으로만 연다. 임의 시간 상한이나 새 학습을 추가하지 않는다. 최종 보고서는 다운로드 대기 상태 대신 실제 도달 단계·호출 수·종료 상태·미검증 항목을 명시해야 한다.