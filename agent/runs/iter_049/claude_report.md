# 요약

- **핵심 결과:** MedThinkVQA 공식 train을 확보해 전수 감사했고, 전체 X-ray·비longitudinal·고유 영상 2장 이상 case는 **N=254, 영상 S=896**입니다. 영상 896장은 모두 받아 hash 검증과 decode에 성공했습니다.
- **근거:** train.jsonl의 sha256과 크기는 계획에서 확인한 값과 같습니다(7,347행). X-ray-only 433건도 논문 집계와 일치합니다. 회귀 검사는 42/42 PASS입니다.
- **미검증·주의:**
  - 공식 repo에서 평가 prompt와 parser를 찾지 못해 MedGemma 213/720 재현 조건은 확보하지 못했습니다.
  - 영상은 chest X-ray 전용이 아닙니다.
  - 정답 누출 의심 14건이 있습니다.
  - 영상에 burned-in 글자가 있습니다.
- **다음:** 자료 조건은 diagnostic 계획에 진입할 수 있는 수준입니다. 다만 진입 전에 prompt·평가 규칙을 고정해야 합니다.

# Work Performed

- GitHub `benluwang/MedThinkVQA`를 `efa12d09…`로, HF `bio-nlp-umass/MedThinkVQA`를 `5555b80e…`로 고정했습니다. 라이선스는 cc-by-nc-sa-4.0이고 비게이트입니다.
- 계획 세션의 DNS 오류는 재현되지 않았고, Python urllib 경로로 모두 접근했습니다.
- `train.jsonl`만 받았습니다. test 파일과 test 영상은 열거하거나 받지 않았습니다.
- 7,347행에 고정 규칙을 순서대로 적용했습니다. 순서는 R1 schema·slot, R2 정답·선택지, R3 전부 X-ray, R4 비longitudinal, R5 영상 2장 이상입니다.
- 적격 case의 영상 896장을 공식 listing과 대조해 선택 다운로드했습니다.
- 추론 입력(이력·선택지·영상)과 평가·감사 전용 필드(caption, IMAGING_FINDINGS, discussion, 정답, ICD)를 분리했습니다. 누출 필드가 섞이면 거부하는 검사도 넣었습니다.
- 후속 요청량 산식, 정밀도(MDE) 표, 입력 token 규모를 산출했습니다.
- 첫 감사에서 제 규칙 오류가 있었습니다. title `Case number 68`과 경로 `case00068`을 문자열로 비교해 3,365행이 잘못 R1 제외됐고 적격이 58건으로 나왔습니다. 정수 비교로 고쳐 다시 실행했습니다. 첫 결과는 오류 기록으로 `audit/`에 남겼고 새 결과는 `audit_v2/`에 저장했습니다.

# Files Changed

새 파일만 만들었고, 모두 git에는 아직 untracked입니다.

- `research/mt49_fetch.py`: revision 고정, sha256 검증, 원자적 저장, 덮어쓰기 방지.
- `research/mt49_audit.py`: 분류 규칙, 추론 view와 누출 가드, 원본 hash 변경 시 재사용 거부.
- `research/mt49_images.py`: 선택 다운로드, listing·git blob sha1 검증, decode·pixel hash, 경로 이탈 거부.
- `research/mt49_report.py`: 비용 산식, MDE 표, token 계산.
- `research/test_mt49.py`: 회귀 검사.
- `research/results/iter_049/`는 대용량 자산이라 git에서 제외됩니다.

# Commands / Experiments

모두 성공했습니다.

- `python mt49_fetch.py`: 파일 22개 확보.
- `python mt49_audit.py`: 1차는 규칙 오류로 무효, 2차(`audit_v2`)는 정상.
- `python mt49_images.py`: 896장, 실패 0, 157.6초, 65.8MB. 8 thread의 CPU·네트워크 작업이며 GPU는 쓰지 않았습니다.
- `python mt49_report.py`
- `python test_mt49.py`: 42/42 PASS.

# Results

- 제외 건수는 R3 6,908, R4 120, R5 59, R2 6, R1 0이고 적격은 254입니다.
- R2의 6건은 동일한 선택지가 둘 있고 정답이 그중 하나인 실제 자료 결함입니다.
- 적격 영상 수 분포는 2장 100, 3장 54, 4장 43, 5장 22, 6장 18, 7장 7, 8장 4, 9장 3, 11장 2, 14장 1입니다.
- subtype별 영상 수는 Plain radiograph 396, Fluoroscopy 235, Catheter angiography/DSA 233, Mammography 31, Other_Xray 1입니다.
- 영상은 모두 480×480이며 RGBA 364장, RGB 532장입니다.
- case 간 영상 id 공유, pixel 동일, 선택지 집합 중복은 모두 0입니다. 같은 case 안에서 pixel이 같은 hash는 4개 있습니다.
- 이력에 정답 텍스트가 있는 사례가 11건, 정답 핵심 토큰이 있는 사례가 3건입니다. 예는 case 486 "Iliac aneurysm", case 1465 "Pyknodysostosis"입니다. 이 사례들은 실제 누출입니다.
- 입력 규모는 텍스트(이력+선택지) 평균 101 token, 최대 199 token입니다. 영상은 장당 256 token이고, 14장 case의 추정 입력은 약 3.6k token입니다(지시문 제외).
- 요청 호출 수는 단계별 전체 S+2N=1,404로 직접 판단(254)의 5.53배입니다.
- 검출 가능한 최소 효과(MDE, 80% power, α=0.05): N=254에서 불일치 비율 q=0.1/0.2/0.3/0.4일 때 0.055/0.077/0.095/0.110입니다. 유효 N이 50%면 0.076~0.153입니다. q는 미관측 가정값입니다.
- 공식 baseline 대응: `model/vllmModels.py`에 MedGemma placeholder(`<start_of_image><image_soft_token><end_of_image>`×n)와 기본 max_tokens 8192, temperature 0.6(vLLM 경로)이 있습니다.
- 평가 prompt, Think-with-Images 실행기, parser는 repo에 없습니다.
- 결과 파일은 `results/iter_049/` 아래의 `audit_v2/audit_summary.json`, `image_manifest.json`, `report/feasibility.json`, `report/summary.md`, `tests/fixtures_mt49.json`입니다.

# Goal Progress / Reused Assets

- 이번은 setup 단계입니다. 준비 성공 기준(원본 revision·hash 고정, 전수 감사, 영상 연결, 입력/정답 분리, 중복, 정밀도, baseline 대응)은 충족했습니다. 가설 지지나 `valid_experiment` 근거는 아닙니다.
- **진입 판단:** 자료 조건상 diagnostic 계획 진입이 가능합니다. 단 아래 세 가지를 계획에서 먼저 정해야 합니다.
  - 정답 누출 의심 14건의 처리.
  - 비교 prompt와 parser의 고정.
  - 정밀도: MDE 0.06~0.11은 N=254의 독립 근사입니다. 효과가 작으면 불확정이 될 수 있습니다.
- **재사용한 코드:** 없습니다(반입 0). 과거 추론 코드는 실행·수정하지 않았습니다. `iter_038`의 `padchest_fetch039.py` 등 기존 fetch 결함(ETag·재개 연결)은 쓰지 않고 새 fetch를 작성했습니다. 이 fetch는 파일 단위로 전체를 다시 받고 `.part` 재개는 없습니다.
- 학습 데이터 중복·사전학습 노출은 파일 hash 수준으로만 확인했습니다. 오염 부재의 증거가 아닙니다.

# Problems

- **현재 결론 무효:** 없습니다.
- **재사용 전 수정:**
  - 이력 누출 의심은 정규화 문자열 일치 기준이어서 동의어 누출은 놓칠 수 있습니다.
  - 영상 안의 burned-in 글자에 대한 OCR 감사는 하지 않았습니다(1장을 눈으로 확인했을 뿐입니다).
  - RGBA 364장의 alpha 처리 규칙이 필요합니다.
  - 공식 prompt가 없어 후속 prompt와 parser는 개발 자료에서 새로 고정해야 합니다.
  - 공식 repo의 `data_processing/leakage.py`는 확보만 했고 실행하지 않았습니다.
- **추후 개선:**
  - `test_mt49.py`의 "train 이외 split 미포함" 검사는 약합니다. title에서 case 번호를 도출하는 방식이라 거의 동어반복입니다.
  - R2 "동일 선택지" 제외는 계획 문구에 없던 제 추가 규칙입니다. 결과를 보기 전에 정했고 6건뿐입니다.

# Recommendation to GPT

diagnostic 계획 진입을 권고합니다. 계획에서 아래를 고정하는 것이 좋습니다.

- 누출 의심 14건과 R2 제외 6건을 포함할지 여부.
- prompt·parser는 train 일부를 development로 쓰되 평가 집단과 분리합니다.
- 지표는 정확도와 device-seconds를 함께 둡니다. N=254에서 MDE가 약 0.06~0.11이어서, 기대 효과가 그 안에 들면 불확정이 될 수 있으니 사전에 판단 기준을 정합니다.
- 영상 14장 case의 peak 메모리를 먼저 측정합니다.

setup을 같은 범위로 반복할 필요는 없습니다.

SELF_CHECK: PASS
SUMMARY: MedThinkVQA 공식 train을 고정 revision으로 확보·전수 감사해 적격 X-ray 다중 영상 254 case(896장, 전부 검증)를 확정했고, 누출 의심 14건·평가 prompt 부재·MDE 약 0.06~0.11을 확인해 diagnostic 계획 진입 가능으로 판단했다.