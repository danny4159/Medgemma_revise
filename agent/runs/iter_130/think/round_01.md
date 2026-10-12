# 사고 라운드 1

## 핵심 판단

현재 측뇌실 확장 이진 과제에 LoRA를 바로 추가할 근거는 부족하다. 같은40명의 frozen 조건 순회는 종료한다. 새로 확인한 MR-RATE 기반 BrainTRACE에서 다중 sequence 신호 질문의 실제 연결을 한정 확인한 뒤, 다음 실제 비교를 확정할 가치가 있다. 아직 실행 계획이나 유망한 한계를 확정한 것은 아니다.

## 원 기록에서 확인한 것

- `agent/GOAL.md`, `agent/runs/iter_129/review.md`, 해당 `review.json/code_assets`, `agent/LIMITATIONS.md`의 관련 항목을 직접 읽었다. P/M 모두40명 전원 PRESENT, BA0.50이다. 정규화만 바꾸는 경로의 종료를 유지한다. 전문 부피 대조 BA0.941176은 이전 완료35명에 한정되며 전체 표본의 충분성을 뜻하지 않는다.
- `agent/runs/iter_077/review.md`: SPIDER 적응 ROI 판독 MAE0.77690과 공유 분류기0.77619의 차이는 불확정이다. 적응 후 영상 대응 신호는 있었지만 VLM 추가 가치는 확보하지 못했다. 따라서 새 T2 SFT의 점수 회복 자체를 방법 필요성으로 삼을 수 없다.
- `agent/runs/iter_064/review.md`: MedGemma의 복제 대비 다른 slice 추가 손실은 유지되지만 Qwen에서 같은 손실은 없었다. 명시적 target index는 단순 routing으로 처리할 수 있으므로 그 조건을 반복하지 않는다.

## 새로 확인한 자료 사실

로컬 `/home/test/.local/share/medgemma/mr_rate/meta/` CSV를 읽기 전용으로 집계했다.

- batch04 metadata는33,260행·4,723 study, batch23은38,526행·3,780 study다.
- batch04의 modality 행 수는 T1w12,047 / T2w9,718 / FLAIR7,789 / SWI3,694 / MRA12다. batch23은 T1w16,928 / T2w4,070 / FLAIR11,447 / SWI6,081이다. 이는 적격 뇌 영상 수나 독립 환자 수가 아니다.
- `classification_rule`, `sequence_family`, `TE_ms`, `TR_ms`, `TI_ms`, `anon_study_date` 등이 실제 header에 있다. modality는 규칙 기반 분류 결과이며 독립 임상 정답으로 승격하지 않는다.
- 로컬 splits98,334행에서 study가2개 이상인 patient_uid는8,475개,3개 이상은2,579개다. longitudinal 임상 관계·같은 병변·비교 가능성이 보장된 수는 아니다.

## 가까운 공식 선행과 새 후보

1. [MR-RATE 공식 저장소](https://github.com/forithmus/MR-RATE)는 multi-volume fusion과 contrastive 학습 코드를 제공하지만 조회한 README의 가중치는 coming soon이다. 이를 즉시 실행 가능한 pretrained 진단 대조군으로 적지 않는다. 관련 NV-Generate-MR-Brain은 생성 모델이며 진단 대조군과 구분한다.
2. [BrainTRACE 논문](https://arxiv.org/html/2610.06571v1)은 MR-RATE에서 보고서·측정값과 영상 근거를 연결한 질문을 구성한다. 보고서 기반 reference이며 독립 영상 재판독 정답과는 다르다. 문헌의 낮은 성능을 우리 모델의 유효 관찰로 대신하지 않는다.
3. [공식 배포 카드](https://huggingface.co/datasets/lanqz7766/BrainTRACE)에서 실제 viewer schema를 확인했다. `study_uids`, `patient_id_anon`, `input_modalities`, `input_planes`, `slice_selection_rule`, `gt_value`, `rubric_json`이 있다. 배포는6,923 source rows이고 test만 존재한다. 영상·원 보고서는 포함하지 않는다. 문헌의7,273 scored instances와 차이는70개 chain을420개 step으로 펼치는 단위 차이다. 새 실험에서 공식 test를 개발 자료로 무심코 사용하는 문제를 먼저 해결해야 한다.
4. [공식 taxonomy](https://raw.githubusercontent.com/lanqz7766/BrainTRACE/main/docs/TAXONOMY.md)의 L2.4는 sequence 간 signal pattern의 closed-form 질문이다. 현재 선택 후보는 이 유형 하나다. acquisition 이름 맞히기는 metadata 규칙으로 해결되는 사용 조건이 많고, 해부학 부피 문제는 전문 segmentation+규칙이 강하므로 자동 대안으로 확대하지 않는다.
5. [렌더링 안내](https://github.com/lanqz7766/BrainTRACE/blob/main/reproduction/README.md)는 coregistered 입력 경로와 item별 slice 규칙을 요구한다. 현재 보유 native-space ZIP과 그대로 동일하지 않다. [실제 렌더러](https://raw.githubusercontent.com/lanqz7766/BrainTRACE/main/reproduction/render_images.py)의 공개 접근을 확인했지만 L2.4의 실제 행부터 출력 영상까지 연결하는 검토는 미완료다. 전체 coreg 반입을 발주할 근거가 아니다.

## 아직 확인하지 못한 것과 접근 기록

L2.4 실제 행의 질문·선택지·reference가 sequence별 독립 정답과 동일 대상을 보장하는지 확인하지 못했다. HF 기본 viewer에서는 L1.1 행만 확인했다. datasets-server의 L2.4 filter 조회는 web 도구에서 접근 실패했고, 셸의 읽기 요청도 DNS 오류였다. 데이터를 내려받거나 로컬에 생성하지 않았다. 다음에는 공식 Data Studio의 해당 행과 배포 파일 목록·렌더러를 연결해 확인한다. 같은 실패 URL 반복은 하지 않는다.

## Strategy Check / 연구 방향 판단

출처: iter_129 리뷰의 질문 카드. 변경 근거는 공개된 MR-RATE 연계 QA 자산의 확인이다.

1. 중요한 문제: 여러 MRI 근거를 각각 읽는 능력과 함께 사용할 때 보존하는 능력을 구분할 수 있는가?
2. 현재 근거: T2·FLAIR 고정 응답과 과거 조건별 context 손실은 실제 관찰이다. 새로운 다중 sequence 연결 실패는 아직 가설이다.
3. 쉬운 해결책: sequence별 판독+고정 결합, 적절한 전문 모델, 직접 SFT가 우선 대조다. 단순 규칙으로 충분한 과제에 새 VLM 방법을 추가하지 않는다.
4. 남은 설명: 개별 인식 부족, 동일 대상 연결 실패, 관측 부족, 약한 reference, 공동 응답 손실이다. 실제 행이 이 구분을 지원해야 한다.
5. 다음 결정: L2.4 자료 적합성을 한 번 확인해 단일 diagnostic을 확정하거나 후보를 보류한다. T2 학습으로 자동 복귀하지 않는다.

## 재사용 판단

현재 브랜치의 `mr123_data.py`, `mr128_gen.py`와 iter_129의 모듈 판정을 확인했다. 렌더링의 제한적 승인은 있지만 생성기는8장·고정 경로·기존 manifest 계약에 묶여 있다. 새 다중 sequence 실행기로 포괄 승인하지 않는다. `mr129_control.py` 기본 eval의 scalar JSON 저장 문제도 유지한다. 실제 과제가 정해지기 전 선별 반입이나 미사용 SynthSeg 복구를 요청하지 않는다.

## 대규모 GPU 필요 후보

MRI volume encoder와 언어 모델의 multi-sequence 공동 정렬·재학습은 장기 후보로 남긴다. 현재 개별 인식과 공동 응답 손실도 분리되지 않았으므로 이를 필요한 해결책으로 단정하거나 대규모 학습을 발주하지 않는다.

## 추가 라운드의 가치와 종료점

남은 확인은 새 자료를 더 많이 찾는 일이 아니라, 확인한 단일 질문 유형에서 비교가 성립하는지를 결정하는 일이다. 성립하면 개발/test 분리와 관측·대조를 고정한 실제 출력 계획으로 내려간다. 성립하지 않으면 이 후보를 보류하고 준비 반복을 종료한다. 이번 조사 문헌은 실험의 긍정 근거에 따른 사용자 논문 추천이 아니다.

## 다음에 파고들 질문
- BrainTRACE L2.4 실제 행의 rubric·study·sequence·slice 규칙은 동일 대상과 sequence별 신호 정답을 보장하는가? 공식 Data Studio와 renderer를 대조해 공동/독립 비교의 성립 여부를 결정한다.
- BrainTRACE는 test만 제공한다. 해당 환자를 개발에 사용하지 않으면서 MR-RATE train/validation에서 같은 질문을 결정적으로 구성할 수 있는가? 불가능하면 평가 집단의 개발 전환을 명시할 가치가 있는지, 후보를 보류할지 결정한다.
- 같은 정보를 받는 sequence별 판독+고정 결합 또는 가까운 전문 모델 이후에 어떤 잔여 정확도·비용 문제가 남을 수 있는가? 연결이 명확하지 않으면 새 방법이나 학습을 발주하지 않고 후보를 보류한다.
