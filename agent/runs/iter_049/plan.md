# 요약

- **이번에 할 일:** MedThinkVQA 공식 train 자료를 확보하고 전체 X-ray·비longitudinal 다중 영상 사례의 적격성과 규모를 감사한다.
- **필요한 이유:** 공개 집계에는 X-ray-only 433건이 있지만 필요한 교집합과 영상 연결은 미확인이다. 계획 세션에서는 DNS·전송 오류로 원본을 읽지 못했다.
- **확인할 기준:** 전체 영상·정답 연결, case 중복, 추론 입력의 정답 누출 차단, 가능한 비교 정밀도와 입력 규모를 확인한다.
- **주의·다음:** 이번은 setup이다. 실제 한계 검증·방법 개발·학습은 하지 않는다. 감사 후 diagnostic 계획 진입 가능 또는 이 범위의 보류를 결정한다.

# Current Understanding

`agent/runs/iter_049/think/round_01.json`의 전략 판단과 iter_048 보류 판단을 유지한다. 이전 노트의 공개 수치 해석은 정정한다. MedThinkVQA 213/720은 전체 영상이며 187/720은 60%·80% 영상 조건이다. backend 차이에 따른 충돌 근거가 아니다.

공식 train의 X-ray-only 433건은 가능성을 보여주는 집계다. 비longitudinal·고유 영상 둘 이상 조건을 만족하는 수는 모른다. 이를 환자 433명 또는 chest X-ray 433건으로 부르지 않는다. 이번 대상은 X-ray modality 전체이며 subtype·해부 부위 분포를 명시한다.

# Strategy Check / 연구 방향 판단

큰 전략 판단은 round_01을 참조한다. 직접 joint SFT 이후 현재 두 양성 문장 grounding의 추가 투자는 보류한다. 그 관찰을 일반적인 의료 VLM 결함이나 다중 영상 종합의 근거로 옮기지 않는다.

이번에 새로 확인한 자료 집계는 제한된 감사의 가치를 높인다. 반면 원본 자료·정밀도가 없는 diagnostic 실행은 iter_047의 자료 부족 문제를 반복할 위험이 있다. 따라서 추가 문헌 라운드 대신 공식 자료 확보와 감사만 구현한다. 이것은 자료 준비를 성공한 과학 실험으로 포장하는 결정이 아니다.

해결된 질문은 공개 점수의 표 해석이다. 남은 핵심 질문은 해당 모집단에서 전체 영상을 보존한 paired 비교가 가능한가다. 선택지는 감사 후 diagnostic 계획 진입 또는 현재 후보 보류이며, 같은 setup의 자동 연장은 없다. research_track과 과거 반복 연결은 유지한다.

# Hypothesis

향후 가설은 공동 판독의 정보 누락과 생성 소견으로 압축할 때의 손실을 구분할 수 있다는 것이다. 이번에는 이를 검증하지 않는다. 준비 질문은 정답·전체 영상·임상 문맥을 보존하면서 그 비교를 실행할 수 있는가다.

# Limitation Evidence / Correct Usage Checks

새 대상의 로컬 실제 출력 근거가 없으므로 limitation_ids는 비워 둔다. 기존 observed/validated grounding 주장을 새 데이터에 적용하지 않는다.

추론용 필드는 향후 CLINICAL_HISTORY, 원래 options, 모든 적격 원본 영상으로 제한한다. title/case ID는 추적용으로만 사용하고 caption, IMAGING_FINDINGS, discussion, correct_answer, correct_answer_text, ICD 필드는 평가·감사 영역으로 분리한다. 임상 이력에 정답명·명백한 동의어가 포함되는 경우를 별도 표시한다. 자동 문자열 일치만으로 누출 부재를 확정하지 않는다.

# Contribution Path / Baselines / Reuse

가장 가까운 선행은 MedThinkVQA의 Think-with-Images 및 self-generated findings를 영상에 추가하는 비교다. 단계별 읽기와 원본 재접근 자체는 신규 기여가 아니다. 이번에는 다음 비교의 정확한 입력·출력·호출 수 명세만 작성한다.

1. 전체 영상 직접 판단.
2. 영상별 생성 소견→통합 소견→진단.
3. 동일 생성 소견과 원본 전체 영상을 함께 제공한 진단.
4. 추가 호출 또는 출력 예산을 제공한 직접 판단 대조.
5. 동일 질문에서 image content만 제거한 text-only.

후속 성능 주장은 실제 device-seconds·latency·token과 정확도를 함께 비교해야 한다. 같은 max_new_tokens만으로 계산량이 같다고 부르지 않는다. 생성 소견은 조건 간 공유 여부와 비용 배분을 명시한다. 학습을 택하는 후속 계획에서는 동일 annotation 직접 SFT가 필요하다.

코드는 `agent/CODE_ASSETS.md`, iter_021·043·048 원본 code_assets를 확인했다. 과거 다중 영상 코드는 보존돼 있으나 전체 실행 승인이 아니다. 이번에는 추론 파이프라인을 실행·수정·반입하지 않는다. 자료 감사는 표준 라이브러리 및 기존 환경의 검증된 이미지 읽기로 구현한다. 현재 브랜치의 기존 다운로드·manifest 도구를 먼저 확인하고 실제 사용할 경로가 있으면 원 리뷰의 결함을 해결하거나 사용하지 않는 이유를 적는다. 새 파일이 필요한 범위는 이 데이터의 schema·적격성 감사로 한정한다.

# Proposed Experiment

## 1. 공식 자료 확보

공식 GitHub 저장소와 HF 데이터 저장소의 revision을 고정하고 라이선스·파일 목록·원문을 보존한다. metadata는 train만 읽는다. 공식 train.jsonl LFS pointer의 SHA256은 `7b38ceddc9cb1cf3a8dc0f9179c694caf826cd5716bb1b326e71d36e9e7d9b3a`, 크기는 84,240,662 bytes로 확인했다. 실제 다운로드 revision이 다르면 새 pointer와 변경 사실을 기록하고 과거 객체와 동일하다고 주장하지 않는다.

허용된 공식 HF resolve/API와 GitHub 경로를 사용한다. LFS pointer를 metadata로 오인하지 않는다. 정상 전송 경로와 공식 대체 경로를 확인한 뒤에도 DNS·접근 오류가 지속되면 오류와 시도를 기록하고 종료한다. 시스템 DNS·드라이버·기본 환경을 변경하거나 비공식 mirror로 우회하지 않는다.

## 2. metadata 전수 감사

7,347 train 행 전체에 대해 고유 case ID, image_count와 실제 nonempty slot 수, image ID/path 중복, modality/sub_modality, longitudinal 필드, options A–E, 정답 letter/text의 대응을 검사한다. 예상 행 수와 다르면 revision 차이인지 결함인지 먼저 설명한다.

적격 기본 규칙은 모든 제공 영상의 modality가 X-ray, is_longitudinal=false, timepoint_count=1, 고유 영상 둘 이상이다. 누락·상충 값은 자동 보정하지 않고 별도 집계한다. 다른 modality를 삭제해 적격 사례를 만들지 않는다. 영상 수 상한이나 모델 정오답으로 사례를 고르지 않는다.

고정 규칙을 순서대로 적용한 제외 수, 최종 case 수, 영상 수 분포, subtype·해부 부위·진단 범주 분포를 보고한다. case와 환자가 동의어라는 보장이 없으면 case를 분석 단위로 표시한다.

## 3. 적격 영상과 누출·중복 검사

metadata를 통과한 사례의 모든 영상을 확보한다. 선택 다운로드가 불가능하면 공식 archive를 받을 수 있지만 적격 train 경로만 추출한다. path traversal·symlink를 거부하고 원 파일과 decode pixel hash, 크기, decode 성공을 기록한다. case 간 동일 영상 및 문맥·선택지 중복 후보를 cluster로 보존한다. 보호 reserve·MRI F139·VinDr 자료는 열지 않는다.

caption과 정답은 추론 manifest에 포함하지 않는다. 임상 이력의 진단명 일치, 영상 내 정답성 주석 및 figure 구성 문제를 감사한다. 의심 사례는 사유를 남기며, 성능 결과가 없을 때 규칙으로 처리한다. 이를 완전한 사전학습 오염 검사로 부르지 않는다.

## 4. 후속 실행 가능성 산출

공식 model 디렉터리에서 실제 MedGemma wrapper·prompt·영상 선택·출력 parser 경로를 찾아 revision과 함께 기록한다. 추정 파일명을 공식 경로처럼 쓰지 않는다. 구현을 확보하지 못하면 그 사실을 명시하고 성능 재현 가능을 선언하지 않는다.

적격 case 수 N, 전체 영상 수 S, 중복 cluster 수를 산출한다. 후속 후보의 요청량은 직접 판단 N, 영상별 읽기 S, 통합 N, 단계별 최종 판단 N, 원본 재접근 N, text-only N 및 계산량 대조의 추가량으로 분해한다. 이는 실행 허가량이 아니라 다음 계획의 비용 산식이다.

paired accuracy 차이에 대해 가능한 discordance 비율별 정밀도와 검출 가능한 효과를 계산한다. 예를 들어 독립 case 근사에서 표준오차는 sqrt((q−delta²)/N)이며 cluster가 있으면 유효 표본 감소를 반영한다. 관찰하지 않은 q를 실측값처럼 쓰지 않는다. 적격 수가 적다는 이유만으로 임의 표본 문턱을 도입하지 말고, 어떤 크기의 차이까지 판단 가능한지 제시한다.

## 단계와 자원

이번은 동작·자료 타당성 확인 단계다. GPU inference·학습은 0이며 가능성 탐색·규모 확대·독립 확인은 미실행이다. CPU-only의 이유는 자료 적격성과 누출 없는 입력이 아직 확인되지 않은 실제 blocker이기 때문이다.

metadata는 약84.2 MB, 전체 archive는 기존 공식 목록상 약6.13 GB다. 설치·다운로드 전에 실제 디스크와 필요 압축 해제 공간을 확인한다. 전송 시작 후 처리량으로 ETA를 갱신하고 임의 시간 상한을 두지 않는다. 파일별 checksum·완료 상태로 재개하고 불완전 다운로드를 완성본으로 쓰지 않는다.

후속 GPU 진입은 자료 감사와 별도 diagnostic 계획 고정 이후다. 그 계획에서 실제 최대 영상 수 입력의 peak와 token 수를 확인하고, 두 GPU의 1 worker씩과 batch 확대 또는 2 worker씩을 development 입력에서 비교한다. 다중 영상 KV cache를 포함해 worker당 2GB 여유를 확인한다. 현재 8–10GB 단일 모델 참고값으로 동시성을 승인하지 않는다.

# Implementation Tasks for Claude

1. 기준 기록과 현재 파일·보존 자산을 확인하고, 공식 자료 확보 경로·revision·라이선스를 기록한다.
2. `research/results/iter_049/`에 원본 metadata, acquisition 로그, 객체 hash, schema 감사와 적격/제외 manifest를 보존한다. 대용량 자산은 git에 넣지 않는다.
3. 적격 train 영상 연결과 case·pixel 중복, 입력 누출 분리를 검사한다.
4. 공식 baseline 대응 문서, 요청량 산식, 정밀도 표, 실제 확보·검사 비용을 작성한다.
5. malformed row, slot 수 불일치, 정답/options 불일치, 혼합 modality, longitudinal 상충, 중복 영상, 누출 필드 혼입을 거부하는 회귀 검사를 수행한다. 원본 hash 변경 시 기존 감사 완료를 재사용하지 못하게 한다.
6. 보고서에 diagnostic 계획 진입 가능 또는 현재 범위 보류를 명시한다. source 변경은 orchestrator의 기존 보존 절차에 맡긴다.

# Evaluation (성공/실패 기준 포함)

**준비 성공:** 원본 revision과 hash가 고정되고, 전체 train 감사 및 적격 영상 연결이 끝나며, 입력/정답 분리·중복 cluster·정밀도·baseline 대응을 검토할 수 있다. 이는 연구 가설 지지나 valid_experiment=true를 뜻하지 않는다. 후속 계획에서 실제 출력 diagnostic을 승인할지 판단한다.

**준비 실패:** 공식 원본을 확보하지 못하거나 정답·전체 영상 연결을 검증하지 못한다. 현재 자료 범위의 후보를 보류하며 실패의 원인을 접근·schema·자료 부족으로 구분한다. 의료 VLM 능력을 기각하지 않는다.

**불확정:** 적격 자료는 있으나 정답 누출·중복·정밀도로 유용한 비교가 성립하는지 결정하지 못한다. 이번 감사 안에서 원문 확인으로 해결 가능한 부분만 처리한다. 끝내 미해결이면 보류하고 같은 setup을 다시 자동 실행하지 않는다.

이번에는 정확도 개선 문턱을 임의로 고정하지 않는다. 실제 출력 비교를 승인할 다음 계획에서 사용 목적에 맞는 최소 가치 있는 효과와 비용 기준을 사전 고정해야 한다. 자료 준비를 이유로 method gate를 건너뛰지 않는다.

# Risks / Checks

- X-ray-only는 chest X-ray-only가 아니다. subtype·해부 부위 범위를 보고서 첫 해석에 반영한다.
- 공식 train은 탐색 자료다. expert annotation도 오류·진단 정보 누출이 가능하며 자동 gold로 신뢰하지 않는다.
- 공개 사례의 사전학습 중복은 완전히 배제할 수 없다. 파일 중복 검사를 오염 부재 증명으로 쓰지 않는다.
- 기존 generate.load_image의 square padding과 단일 영상 schema를 새 데이터에 자동 적용하지 않는다.
- 공개 213/720과 187/720의 정정은 이번 기록에 남기고 이전 노트를 덮어쓰지 않는다.
- 자료·실행기 준비가 연구 목표 완료나 새 contribution이 아니다. 후속 실제 출력이 없으면 limitation 상태를 올리지 않는다.
- **대규모 GPU 필요 후보:** 다양한 modality의 다중 영상 인코더·근거 종합 모듈 공동 학습은 장기 후보로 보존하되 현재 필요성·차별성은 미확정이다.

# 계획의 근거 (GPT 조사 노트)

## 새로 확인한 것

직전 `agent/runs/iter_049/think/round_01.json` 원문과 GOAL·GPT_USAGE_POLICY·iter_048 리뷰를 읽고 남은 질문을 확인했다. 현재 research 작업 트리의 `git status --short`는 비어 있었다. 파일 수정·다운로드 저장·모델 호출·GPU 실험은 수행하지 않았다.

### 1. 공개 수치의 불일치는 이전 노트의 표 해석 오류였다

MedThinkVQA Appendix D의 Table 5는 전체 영상에서 MedGemma 1.5 4B 213/720을 보고한다. Table 6의 열은 0/20/40/60/80%이며, 187/720은 60%와 80% 값이다. D.2는 100%를 Table 5와 같다고 명시한다. 따라서 직전 노트의 ‘187/720 full-image’ 해석을 정정한다. 이를 backend 차이의 증거로 쓰지 않는다. 정확한 실행 prompt·revision은 여전히 확보하지 못했다. [논문 Appendix D](https://arxiv.org/html/2604.16506v1#A4)

### 2. 자료 후보는 있으나 실제 적격 수는 아직 모른다

Appendix M.6은 train에서 modality 집합이 X-ray인 사례 433건을 보고한다. 이는 비longitudinal·다중 영상 교집합의 수가 아니다. X-ray에는 plain radiograph 외 angiography·fluoroscopy·mammography 등이 포함되므로 chest X-ray 사례 수로 해석해서도 안 된다. 이번에는 이 subtype 차이를 기록하고, 전체 X-ray 범위에서 정답과 모든 영상을 보존한다. [논문 Appendix M](https://arxiv.org/html/2604.16506v1#A13)

### 3. 원본 접근 장애의 범위를 확인했다

공식 raw train.jsonl은 실제 metadata가 아닌 Git LFS pointer를 반환했다. 객체 SHA256은 `7b38ceddc9cb1cf3a8dc0f9179c694caf826cd5716bb1b326e71d36e9e7d9b3a`, 크기는 84,240,662 bytes다. resolve 경로는 브라우저에서 CDN redirect 오류를 반환했고 datasets-server도 읽지 못했다. 로컬 urllib의 공식 HF API 읽기는 `Temporary failure in name resolution`로 실패했다. GitHub model 디렉터리는 브라우저 오류였고 추정 파일명 medgemma.py는 404였으므로 공식 wrapper 경로를 확인했다고 주장하지 않는다. 이는 공개 데이터의 이용 권한 부족을 입증하지 않는다. [공식 LFS pointer](https://huggingface.co/datasets/bio-nlp-umass/MedThinkVQA/raw/main/train.jsonl), [공식 저장소](https://github.com/benluwang/MedThinkVQA)

### 4. 선행 대비 구별은 더 엄격히 제한해야 한다

논문 Figure 5는 expert/self 생성 Image Hint 및 Integrated Imaging Summary를 영상에 추가하는 조건을 이미 비교한다. 생성 소견과 원본 재접근 자체도 새로운 아이디어가 아니다. caption 기반 oracle은 진단 정보를 포함할 수 있어 이번 후보에서 제외한다. 후속 진단은 공정한 대조로 잔여 문제를 찾는 단계이며, 단순한 benchmark 재현이나 기존 분해 방식의 개선을 곧바로 기여라고 부를 수 없다. [논문 Figure 5](https://arxiv.org/html/2604.16506v1)

### 5. 코드 재사용 판단

`agent/CODE_ASSETS.md`와 iter_021·043·048의 원본 review.json/code_assets를 확인했다. iter_021 다중 영상 wrapper는 보존돼 있으나 gate·provenance·재개 문제가 남아 있다. iter_043 실행기의 제한적 승인은 iter_048의 worker mapping·attempt 비용 결함을 해소하지 않는다. 현재 `rsna_diag/generate.py`의 load_model은 고정 revision을 사용하지만 load_image는 square padding을 수행하고 build_inputs는 단일 영상이다. 새 자료에 이 전처리와 schema를 자동 적용하지 않는다. 이번 metadata 감사에는 추론 모듈 반입이나 수정이 필요하지 않다.

## 결정과 한계

적격 수가 없는 상태에서 임의 E96과 요청량을 만들어 diagnostic을 승인하지 않는다. 추가 사고 라운드 대신, 승인된 구현 환경의 공식 자료 확보와 전수 감사만 수행하는 setup으로 범위를 명시적으로 변경한다. 이는 직전 라운드의 diagnostic 구현 예상보다 좁은 실행이며 실제 출력 근거를 대신하지 않는다. 한 번의 감사 후 자료가 충분하면 diagnostic을 별도 고정하고, 부족하거나 접근이 계속 막히면 이 후보를 보류한다.

## 대규모 GPU 필요 후보

다중 영상 인코더와 근거 종합 모듈의 공동 post-training은 장기 후보로 유지한다. 현재 필요성·차별성은 미확정이며 이번 반복에서 학습하지 않는다.

이전 사고 라운드 노트: agent/runs/iter_049/think/
