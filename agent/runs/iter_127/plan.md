# 요약

- 이번에 할 일: 원 보고서 기준과 hash 순서로 표본 선정을 수정하고, 성립하면 T2 관측 선택 비교를 완료한다.
- 필요한 이유: iter_126은 음성3명과 누락 제외 기록을 발견해 모델 실행 전에 중단했다.
- 확인할 기준: 전체 선정 근거·공식 SynthSeg 2.0·실행 검증을 통과한 뒤 원 BA·비용 기준을 적용한다.
- 주의·다음: 일반 normal을 명시적 정상 크기로 인정하지 않는다. 자료 또는 전문 비교군 복구가 안 되면 현재 설계를 보류한다.

## 알림 맥락

- 연구: MRI 관측과 근거 활용
- 데이터: 뇌 MRI MR-RATE의 axial T2와 측뇌실 크기 보고서
- 모델: frozen MedGemma 1.5, 전문 대조 SynthSeg
- 과제: T2 영상8장을 받아 양측 측뇌실 확장 여부를 출력한다
- 가설: 같은 영상 예산에서 관측할 위치를 바꾸면 판별이 달라질 수 있다
- 질문: 필요한 구조가 보이도록 영상을 고르면 답이 나아지며 전문 모델보다 남는 가치가 있는가?
- 변경: 실행 복구
- 연결: iter_126의 선정 결함으로 비교 미실행 → 원 의미 기준과 순서를 유지해 표본을 다시 확정한다
- 작업: 선정 수정과 공식 전문 비교군 검증 후 실제 비교를 완료하거나 현재 설계를 보류한다

# Current Understanding

기준은 `agent/runs/iter_125/plan.md`(SHA256 `477a1c817abfe198e25c14f64a487fbd6f53d5ab0c4a7e5fab91e36f2b705a47`)와 `agent/runs/iter_126/plan.md`(SHA256 `632a6090c0246dde0e0d8d80c18fee007d3f0625bae6d4320ffe1d67972e4070`)다. 구현 담당은 두 원문과 iter_125/126 review.json을 읽는다. 충돌 시 이번 amendment의 선정·예산·결과 경로 변경만 우선하며 나머지 실험 조건은 상속한다.

유지: 원 정답 의미, 두 batch 공식 train, seed125, 이전 iter_123/124 환자 제외, 한 환자 한 study, 기술8/calibration12/탐색40, T2 선택 규칙, U/A·prompt·metric·판정 기준.

변경: 고정60명 불변 조건을 이번 출력 전 재선정에 한해 해제한다. 원 후보·순서에서 전체 적격성 판단을 완결하고 층별 첫15명으로 새 manifest를 만든다. 환자와 역할 변경에 따른 비용도 다시 잠근다.

미완료: 전체 적격성, 공식2.0 ICV·QC, runtime·실제 processor 검사, 기술 생성·처리량, calibration 및 탐색 비교다. 원 기록·60명 manifest·v1 임시 결과·중단 판정은 보존한다. 기존 FLAIR 및 위치 연구의 보류도 유지한다.

# Strategy Check / 연구 방향 판단

직전 카드 출처는 iter_126/review.json이다. 같은 질문의 실행 복구이며 신규 방향 선정이 아니다.

1. 중요한 문제: 제한된 MRI 관측에서 관련 해부학 선택이 판단을 회복하는가?
2. 현재 근거: T2 모델 비교는 없다. 새 근거는 선정 기준과 실제 문구의 불일치이며 추가 후보의 명시적 크기 문장은 확인됐다.
3. 쉬운 해결책: 자동 slice 선택과 공식 부피+threshold를 직접 비교한다. 충분한 단순 대안이 있으면 방법 투자를 보류한다.
4. 남은 설명: 자료 의미·segmentation·native slice 부족·기본 인식·sampling의 기여다.
5. 다음 결정: 한정 수정으로 실제 비교를 완료하거나 자료/실행 근거 부족으로 현재 설계를 보류한다. 감사만 반복하지 않는다.

# Hypothesis

원 가설을 유지한다. 관측 sampling이 중요하면 A가 U보다 높다. S만 높으면 단순 선택 이후의 모델·입력 문제가 남는다. S까지 낮으면 보고서·자료·전문 모델 적합성이 남는다. A의 개선은 관측 분포 변화의 효과이며 내부 선택 능력의 순수 인과 증명이 아니다.

# Limitation Evidence / Correct Usage Checks

새 T2 과제에는 실제 observed limitation이 없어 limitation_ids는 비운다. 기존 FLAIR 한계는 배경이며 method 진입 근거로 사용하지 않는다.

음성은 양측 또는 명시적 복수 측뇌실의 정상 크기·폭, 또는 확장 부재다. 일반 normal, 위치 정상, 제3/4뇌실만 정상, 미표기, 자동 라벨0은 충분하지 않다. 양성은 같은 대상의 명시적 확장이며 mild·위축 관련 확장도 포함한다. 편측만 기술하거나 대상·극성이 모호하고 상충하면 unknown이다. 전문가 판독이나 새 LLM 합의로 의미를 보충하지 않는다.

공식 processor·chat template·model revision·pixel tensor·영상 순서·생성 설정을 실제 기술 입력에서 검증한다. 보고서·정답·환자ID·selector 성공 여부는 messages에 넣지 않는다.

# Contribution Path / Baselines / Reuse

신규 기여는 미확정이다. U/A는 동일8장 예산, S는 같은 T2 전체 volume의 공식 좌우 측뇌실 부피/ICV다. S의 정보량 이점과 A의 segmentation 비용을 함께 보고한다. 직접 SFT는 후속 방법 검토 때 같은 supervision으로 비교할 대안이며 이번에는 학습하지 않는다.

현재 `approach/mri-anatomy-observation`, HEAD `8c64058b193a9de4a594a3f371c9dba790fc2561`를 이어간다. 필요한 파일이 현재 브랜치에 있어 반입은 없다. CODE_ASSETS 및 원 review의 needs_fix 판정을 유지한다.

- `mr125_select.py`, `mr125_order.py`, `mr125_lock.py`: 원 후보·hash 순서를 재사용하되 새 결과 경로와 완결된 사례별 판단·선정 기록을 연결한다. 기존 경로에 쓰는 스크립트를 그대로 실행하지 않는다.
- `mr126_preflight.py`: 하드코딩 사례 부재를 전체 통과로 해석하지 않도록 수정한다. 모든 선정자와 선행 제외자의 명시적 검토 상태를 요구한다. HEAD 동일성 대신 원 소스 blob·입력 hash와 현재 변경 manifest를 검증한다.
- `mr125_fetch.py`, `mr123_fetch.py`: 기존 ZIP 실제 bytes·revision·size·SHA, 누적 합집합 예산과 재개 ledger를 검증한다.
- `mr125_seg.py`: 공식2.0 vol/QC, 가중치·설정별 캐시, GPU 매핑과 실패 반환을 보완한다.
- `mr125_build.py`, `mr123_data.py`: hard-mask ICV를 공식 CSV로 대체하고 원 격자 변환·불변 U/A·새 PNG 경로를 검증한다.
- `mr123_run.py`, `mr125_handoff_audit.py`: strict JSONL, 실제 설정·완료 수·재개·stage lock 및 현재 검사 결과 연결을 완결한다.

iter_125/reuse_manifest.json의 필수 검사를 실제 사용 경로에 적용한다. 미사용 코드의 전수 정비는 하지 않는다.

# Proposed Experiment

## 1. 출력 전 선정 수정

원 CSV·candidate·ordered_candidates·selection_lock의 hash를 확인하고 새 protocol을 `research/results/iter_127/`에 저장한다. 후보 검색 규칙과 seed125를 바꾸지 않는다. 기존 네 batch×후보 label 목록을 hash 순서대로 처음부터 검토한다. 각 층 첫15 적격자를 얻기까지 모든 후보의 findings·impression·report 전체를 확인하고, 기존60명 및 이전에 건너뛴20명의 판단도 모두 기록한다. 전체 후보 목록의 기계적 provenance를 확인하되 미검토 후순위를 의미 검토 완료로 표시하지 않는다.

각 판단에는 원 CSV 행·source hash·인용 위치·대상·크기/확장 극성·상충 여부·include/exclude/unknown·구체적 사유를 둔다. 과거 제외 사유가 없는70101·69242·70410은 원 기록에서 복원 가능한 경우만 복원으로 표시한다. 그렇지 않으면 이번 원문 검토의 새 판단이라고 기록한다. 원래 제외됐다는 이유만으로 다시 제외하지 않는다.

일반 normal만 있는16714·16713·17856은 명시적 크기 근거가 없는 한 부적격이다. 나머지57명도 자동 승인하지 않는다. 애매한 연결·수식 범위는 unknown으로 처리한다. 후보의 극성이 기존 후보 label과 맞지 않으면 이번 층에서 제외하고 다른 층으로 임의 이동시키지 않는다.

각 층의 첫15 적격자를 다시 선정하여 앞2명 기술, 다음3명 calibration, 나머지10명 탐색으로 배정한다. 세 빈자리만 임의로 채우지 않는다. 적격 순서 복원으로 생기는 역할 이동도 허용하되 원→신규 환자·역할·사유 diff를 저장한다. 이전 segmentation·fallback·비용이나 모델 예측은 선정 근거로 사용하지 않는다.

환자 중복·공식 train·이전 환자 제외·series 선택을 검증한다. axial T2는 작은 slice spacing→작은 in-plane voxel area→series_id 순서를 유지한다. 선정 후 발견한 실제 파일의 입력 무결성 결함만 원 계획의 다음 hash 후보 대체를 허용하며, 새 후보의 원문 검토와 manifest 재봉인을 모델 출력 전에 끝낸다. segmentation 실패·높은 fallback·낮은 정확도는 교체 이유가 아니다.

각 층15명이 성립하지 않으면 표본 수·정답 기준·batch를 임의 변경하지 않고 현재 설계를 보류한다. 성립하면 새60명 manifest와 평가 조건을 잠근다.

## 2. 공식 비교군과 동작 확인

새 기술8명에 해당하는 ZIP만 먼저 확보한다. 기존 자산은 실제 hash·revision·series·설정 일치 시 재사용한다. 공식 SynthSeg2.0 기본 모드의 `--vol`·`--qc`를 사용하며 v1·robust·fast 순회는 하지 않는다. 공식 UCL 배포, 실패 시 공식 FreeSurfer 대응 배포와 격리 호환 환경의 한정 복구는 iter_126 계획을 따른다.

좌우 측뇌실 부피와 total intracranial을 공식 이름·단위로 연결하고 QC의 실제 출력·의미를 기록한다. hard-mask 비배경 합을 ICV로 쓰지 않는다. zero/nonfinite/누락 출력을 유효한 전문 점수로 인정하지 않는다. 기술8명의 공식 출력 결함이 해결되지 않으면 본실행을 중단한다.

기존 zero mask 원인은 입력·affine·가중치·공식 직접 실행과 wrapper 연결로 구분한다. 고유 slice 부족은 native spacing과 1mm→원 격자 변환을 검사한다. selector를 바꾸거나 slice 복제·재보간으로8장을 채우지 않는다. QC는 실패 설명에 사용하며 결과에 따른 cutoff·환자 제외를 만들지 않는다.

기술 MedGemma16건은 bf16·greedy·max_new_tokens512다. cap 도달 시에만 기술 전체16건을1024로 한 번 재검사하고 최종 cap을 잠근다. 낮은 기술 정확도만으로 탐색을 중단하지 않는다.

## 3. 입력·calibration·가능성 탐색

U는 brain-mask 유효 axial 구간5–95%의 등간격 고유8장이다. A는 공식 segmentation의 좌우 측뇌실 합집합에서 slice 면적이 최대의5% 이상인 최소–최대 구간의 등간격 고유8장이다. 실패 또는8장 미만이면 U로 fallback한다. 두 조건의 원본 T2·RAS·brain percentile1–99 window·896 canvas·영상 순서를 유지한다. mask overlay는 제공하지 않는다.

고정 prompt:
`You are shown 8 axial T2-weighted slices from one brain MRI examination, ordered from inferior to superior. Is there evidence of enlargement of both lateral ventricles in the images shown? Answer on the first line with exactly one word: PRESENT, ABSENT, or UNCERTAIN. Then give a brief justification in at most two sentences.`

S는 공식 좌우 측뇌실 부피 합/공식 ICV다. calibration12에서 BA 최대 threshold를 선택하고 동률이면 specificity, 이어서 큰 threshold 순으로 고정한다. calibration VLM 생성은 없다. 입력·평가기·threshold를 봉인한 뒤 탐색40명의 U/A80건을 생성한다.

fallback을 포함한 모든 환자를 primary 분모에 유지한다. 전문 출력 누락 시 available-case 결과만으로 S 충분성을 주장하지 않는다. 기술 단계 이후에는 환자 교체나 표본 재선정을 하지 않는다.

## 4. 규모 확대·독립 확인

이번 반복은 탐색40명까지다. 학습·추가 seed·공식 test·신규 독립 집단은 실행하지 않는다. 양성 관측과 전문 대안 이후의 가치가 함께 남을 때만 다음 계획에서 독립 확인 또는 최소 method pilot을 판단한다.

## 데이터 예산·GPU·시간·재개

기존 예정114 ZIP·15,274,018,253 bytes와 남은52 ZIP·6,881,748,362 bytes는 이전60명 기준이다. 이번에는 그대로 복사하지 않는다. 기존 보유 파일은 보존하되 탈락한 미다운로드 study는 받지 않는다. 보유 ZIP과 새60명 필요 ZIP의 합집합을 실제 공식 객체 크기로 합산하고, 이전 예산 대비 증가·감소와 원인을 실행 전에 봉인한다. 이번 조정은 결정적 대체에 필요한 study에만 적용하며 전체 snapshot 다운로드는 금지한다.

기술8명의 공식 비교군 통과 전에는 나머지 자료를 받지 않는다. 큰 데이터·cache·중간 결과는 `/home/test/.local/share/medgemma/mr_rate`의 iter127 전용 경로에 둔다. ZIP member 추출 크기·환경·가중치·기술 단계 임시파일 peak를 합산해 파일시스템별 여유를 확인한다. 토큰은 HF_TOKEN_PATH로만 참조하며 hf_cache와 기존 자산은 변경·삭제하지 않는다.

매 실행 직전 nvidia-smi와 상속된 허용 GPU의 논리/물리 매핑을 확인한다. 두 GPU에 독립 환자를 분배하고 TensorFlow 메모리 선점을 제한한다. MedGemma8–10GB는 참고값이며 실제 peak와 worker당2GiB 여유로 배치를 결정한다.

기술16요청의 GPU당 worker1을 기준으로 batch2를 추가16요청 안에서 비교한다. batch2가 부적합하면 같은 비교 예산에서 메모리가 허용하는 GPU당 worker2를 검토한다. 요청/분·GPU 전체 peak·긴 출력 지연·정합성·OOM·CPU/I/O 경합을 기록하고 더 빠르고 안전한 구성을 선택한다. worker1 유지 시 실측 이유를 적는다.

총시간은 아직 미측정이다. 기술 단계의 다운로드 bytes/초와 추출·공식 segmentation·render·VLM·저장 처리량으로 남은 volume·80요청의 wall-clock을 계산한다. 과거 v1의588.91초를 v2 비용으로 대입하지 않는다. 임의 시간 상한은 없다. cold-start, warm NIfTI→답 저장, A/S 공유 전처리와 독립 실행 비용, 설치·선정·복구 시간을 구분한다.

고유 request ID·stage lock·원자적 할당·worker별 출력·설정 hash·완료 수 검사를 적용한다. 실행 중 claim을 삭제하지 않고 정상 종료 확인 후 미완료만 재개한다. 학습 checkpoint 대신 단계별 manifest·원시 출력·완료 seal을 보존한다.

# Implementation Tasks for Claude

현재 구현 담당 Codex에 적용한다.

1. 원 계획 hash·소스 blob·원 결과 불변을 확인하고 이번 amendment와 선정 규칙을 저장한다.
2. 전체 선정자와 선행 제외 후보의 원문 검토를 완결한다. 새60명·역할 diff·예산을 모델 출력 전에 잠근다.
3. 자료가 성립할 때 공식2.0 기술8명 실행과 ICV·QC·좌표 연결을 검증한다. 실패하면 남은 다운로드와 전체 실행기 정비를 중단한다.
4. 실제 사용할 fetch/seg/build/run 경로의 캐시 provenance·strict JSONL·완료 수·GPU 매핑·안전 재개를 보완한다.
5. 기술 입력·출력·처리량 검사를 거쳐 calibration12와 탐색40 비교를 수행한다.
6. 별도 계산 경로로 환자별 정오·BA·AUROC·paired CI·fallback·비용·최종 분기를 검산하고 원시 근거를 보고한다.

# Evaluation (성공/실패 기준 포함)

Primary는 탐색40명의 report-agreement BA다. UNCERTAIN·INVALID·거부는 오답으로 집계하고 비율을 따로 보고한다. sensitivity·specificity·paired 전환·S AUROC/BA와 batch×label 층화 환자 bootstrap10,000회95% CI를 유지한다.

- 양성 관측: A−U BA≥0.15, paired CI 하한>0, A BA≥0.75, sensitivity·specificity 각각≥0.65. 제한된 sampling 효과를 보존한다.
- 단순 대안 충분성: S BA≥0.80이고 A가 S를0.05 이상 개선하지 못하며 더 비싸면 현재 이진 구조 과제의 VLM 방법 투자를 보류한다.
- 음성: U/A 모두 BA≤0.60이면 현재 frozen 설계를 종료한다. S만 높으면 sampling만으로 회복되지 않았다는 범위로 한정한다.
- 불확정: 나머지 성능·높은 fallback·상충·넓은 CI는 근거 부족으로 보류한다. selector 성공 부분집단은 보조 결과다.
- 실행 실패: 적격60명·공식 비교군·필수 무결성 검사가 성립하지 않으면 valid_experiment=false다. MRI 능력이나 관측 선택 가설을 기각하지 않는다.

관측 양성과 투자 판단은 별개다. 선택 효과가 있어도 전문 대안 이후 가치가 없으면 방법을 개발하지 않는다. 모든 분기에서 이번 한정 비교를 종료하며 같은 환자의 prompt·threshold·selector 변경, 세 번째 모델, 추가 감사 반복은 자동 발주하지 않는다.

# Risks / Checks

보고서는 약한 정답이며 실제 영상 진단 정확도를 보증하지 않는다. 일반 normal의 임상 의미를 논쟁해 원 기준을 넓히지 않는다. 새 선정 판단은 과거 기록 복원과 구분한다. mild·위축 관련 확장은 유지하며 수두증 진단으로 재명명하지 않는다.

선정 이후 역할 이동 때문에 모든 파생 요청·calibration 연결·캐시 키를 새 manifest에 연결한다. 원 hash 순서·역할 수·환자 분리·누락 제외 사유를 독립 검산한다. 소스 checkpoint 변경 자체는 실패가 아니며 예상 소스 변경과 실제 입력 변조를 구분한다.

A와 S는 같은 예측 segmentation을 공유한다. 이를 정답 mask로 취급하지 않는다. 공식 출력 실패와 native slice 부족을 구분하고, 실패 환자를 없애 성능을 높이지 않는다. stale-cache 거부, 좌표 왕복, parser의 명시 답/unknown 구분, calibration 외 threshold 선택 금지, 중복·누락·손상·동시 실행의 실패 반환을 검사한다.

## 대규모 GPU 필요 후보

전체3D 다중 sequence 표현과 질문별 관측의 공동 적응을 장기 후보로 보존한다. 현재 단순 대안 이후 잔여 문제와 신규성이 확인되기 전에는 실행하지 않는다. 필요한 자원량은 미산정이다.

# 계획의 근거 (GPT 조사 노트)

원문 agent/runs/iter_125/plan.md, iter_126/plan.md·review.json, GOAL.md, CODE_ASSETS의 관련 항목, LIMITATIONS의 MR-RATE 항목, iter_125/reuse_manifest.json 및 현재 선정·segmentation·build·preflight 코드를 확인했다. 기준 plan SHA256은 iter_125=477a1c817abfe198e25c14f64a487fbd6f53d5ab0c4a7e5fab91e36f2b705a47, iter_126=632a6090c0246dde0e0d8d80c18fee007d3f0625bae6d4320ffe1d67972e4070이다. 현재 research HEAD는 8c64058b193a9de4a594a3f371c9dba790fc2561이며 작업 트리는 깨끗하다. 필요한 mr123/mr125/mr126 파일은 현재 브랜치에 존재하지만 모두 이번 경로의 보완 검증이 필요하다.

저장 ordered_candidates의 후보 수는 batch04 음성2510·양성372, batch23 음성1252·양성209다. 이는 적격 환자 수가 아니며 iter_125 조사 노트의 더 엄격한 문구 검색 수와 다른 검색 단계다. batch04 후보17327의 'Lateral ventricles, third and fourth ventricle sizes are normal.', 16748의 명시적 normal size, batch23 후보70194의 bilateral lateral ventricles normal width 등을 확인했다. 전체 보고서·상충·환자 연결 확인 전에는 선정 승인으로 쓰지 않는다.

mr125_lock.py는 층별 첫15명의 앞2/다음3/나머지10을 기술/calibration/탐색으로 배정한다. 따라서 단순 세 빈자리 채우기보다 동일 hash 순서의 첫15 적격자를 재계산하고 역할 이동까지 기록해야 한다. mr126_preflight.py는 세 사례 하드코딩 및 구현 전 HEAD 동일성 검사를 사용하므로 완결된 적격성 검증을 대신하지 못한다. mr125_build.py의 hard-mask ICV, mr125_seg.py의 v1·study 단위 캐시도 그대로 사용할 수 없다.

현재 읽기 전용 df 실측 여유는 외부 경로2,567,944,515,584 bytes, SSD13,215,531,008 bytes다. 실행 직전 다시 확인한다. 공식 SynthSeg 경로와 지원 조건은 iter_126의 원 조사·계획을 계승하며 새 문헌 주장을 추가하지 않았다. 이번에는 다운로드·파일 생성·모델 실행을 하지 않았다.
