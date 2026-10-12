# 사고 라운드 1

## 새로 확인한 것

- `agent/GOAL.md`, `agent/runs/iter_124/review.md`와 `review.json`, `agent/runs/iter_064/review.md`, `agent/MR_RATE_DATA_NOTES.md`, `agent/CODE_ASSETS.md`의 관련 항목 및 현재 연구 파일을 읽었다. iter_124의 23명 전원 PRESENT·BA 0.50은 유효한 음성 결과이며 현재 FLAIR 후보 종료를 유지한다. iter_064의 context 손실도 단순 routing 이후의 방법 필요성을 입증하지 못했다.
- 현재 `research/` 작업 트리는 깨끗하다. `mr123_data.py`, `mr123_run.py`, `mr124_*.py`가 있다. 전체 실행기 재사용은 승인되지 않았다. 특히 `mr123_data.py`의 추출 캐시는 study 중심 경로이므로 다중 series에 그대로 확장하면 안 된다. 새 접근법을 확정하기 전 선별 반입은 지정하지 않았다.
- 로컬 metadata는 `/home/test/.local/share/medgemma/mr_rate/meta/metadata/batch04_metadata.csv` 33,260행과 `batch23_metadata.csv` 38,526행이다. `study_uid`, `series_id`, `classified_modality`, `sequence_family`, `dwi_sub_type`, `classification_rule`, shape·spacing 및 획득 정보가 있다. 두 파일의 `dwi_sub_type`은 모두 결측이었다. batch04의 modality 분포는 T1w 12,047, T2w 9,718, FLAIR 7,789, SWI 3,694, MRA 12다. 이 사실만으로 ZIP 내부 DWI 부재를 확정하지 않는다.
- 로컬 보고서는 batch04 4,723행, batch23 3,770행이다. findings의 단순 문자열 검색에서 diffusion restriction은 각각 851·352건, hydrocephal은 74·36건, mass effect는 56·104건, midline shift는 94·14건이다. 이 수치는 부정문·반복 환자·공식 test를 포함할 수 있는 검색 hit이며 적격 양성 수가 아니다.
- 실제 원문에는 `No diffusion restriction ... diffusion-weighted images`와 SWI 정상 기술이 함께 있는 사례가 있다. 다른 사례에는 종양·부종·수두증이 함께 기술된다. 따라서 보고서 전체를 배포된 일부 영상의 정답으로 놓는 위험이 구체적으로 확인됐다. 수두증과 뇌실 확장·위축도 같은 정답으로 합칠 수 없다.

## 문헌과 대안

- [MR-RATE 공식 안내](https://github.com/forithmus/MR-RATE/blob/main/data-preprocessing/docs/dataset_guide.md)는 series 단위 metadata와 study 연결을 설명한다. [공식 저장소](https://github.com/forithmus/MR-RATE)는 MRI–report contrastive 학습을 제공하지만 조회한 안내의 모델 가중치는 coming soon이다. 이를 실행 가능한 진단 대조군으로 가정하지 않는다.
- [ReMIND 원 논문](https://www.medrxiv.org/content/10.64898/2026.03.30.26349106v1.full)과 [저자 페이지](https://dlteif.github.io/publication/remind/)는 multi-sequence MRI의 unsupported modality claims를 줄이는 modality-aware reranking/correction을 명시한다. 따라서 '없는 sequence의 소견을 말한다' 자체를 새 기여로 제안할 수 없다. 공개 구현·정확한 검증 규칙·유보와 정보 보존 평가 범위는 추가 확인이 필요하다. PMC 본문 직접 조회는 reCAPTCHA로 막혔지만 medRxiv 원문 경로는 검색에서 확보했다.
- [SynthSeg 공식 코드](https://github.com/BBillot/SynthSeg)는 contrast·resolution이 다른 MRI의 해부학 segmentation 대안이다. 뇌실 segmentation이 곧 수두증 진단이라는 뜻은 아니다. 구조적 소견 후보를 택하려면 이 차이를 명시해야 한다.

## Strategy Check / 연구 방향 판단

1. 중요한 문제: MRI에서 관측한 범위와 답변의 주장 범위를 연결할 수 있는가? 상위 MRI 근거 활용 질문을 유지한다.
2. 현재 근거: 기존 FLAIR 고정 응답은 실제 관찰이다. 새 후보에서는 metadata와 보고서 범위 차이만 확인했으며 모델 한계는 아직 관찰하지 않았다.
3. 쉬운 해결책: sequence 목록·규칙 및 ReMIND가 직접 대안이다. 구조적 소견은 segmentation+규칙을 검토해야 한다.
4. 남은 설명: 관측 범위 추적 실패와 단순 입력 안내 부족, 보고서와 배포 영상 범위 차이를 구분해야 한다.
5. 다음 결정: 새 GPU 실행 전에 가까운 대안 이후 남는 질문과 실제 적격 사례를 확인한다. 단순 문장 삭제로 소진되는 후보라면 투자하지 않는다.

## 다음 라운드가 필요한 이유

유력 후보의 가까운 선행 ReMIND가 발견됐고, 로컬 보고서의 diffusion 기술에 대응하는 배포 영상이 아직 연결되지 않았다. 이 두 조건은 실험의 정답 정의와 투자 선택을 직접 바꾼다. 다음 라운드는 전체 이력을 다시 읽지 않고 아래 질문에 한정한다. 신규 다운로드·학습·모델 실행은 하지 않았다.

## 대규모 GPU 필요 후보

전체 3D 다중 sequence와 보고서의 관측 범위를 함께 학습하는 대규모 적응은 장기 후보로 남긴다. 현재 잔여 문제가 검증되지 않았으므로 발주하지 않으며, 필요한 자원량도 아직 산정하지 않았다.

## 다음에 파고들 질문
- ReMIND 원문·공개 코드에서 modality 누락 판정과 문장 삭제가 실제로 지원하는 범위는 무엇이며, 정확한 sequence 목록을 제공한 단순 규칙 이후에도 평가할 잔여 문제가 있는가?
- 현재 보유 ZIP의 member 목록과 metadata·공식 필터 규칙을 대조하면 보고서에 언급된 DWI/ADC가 실제로 배포되지 않은 사례를 결정적으로 구성할 수 있는가? 그 경우 임상 진단 정답 대신 어떤 관측 범위 주장만 평가할 수 있는가?
- 구조적 소견 대안은 공식 train/validation의 환자 분리·명시적 양음성·관련 series가 성립하는가? SynthSeg+규칙 이후 기술적 질문이 남지 않으면 두 후보 중 무엇을 보류할 것인가?
