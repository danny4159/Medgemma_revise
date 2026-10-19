# RSNA box SFT 뒤 판독문 소견 언급의 변화

## 요약

- 사용자 요청: 기존 RSNA LoRA를 그대로 적용한 모델이 자유 판독문에서 병변을 덜 누락하는지 확인한다.
- 새 학습 없음. original MedGemma 1.5 4B vs iter_012 seed17 epoch5 adapter.
- E600 개발 자료에서 세 category 각 20명(총 60명), 같은 영상/질문으로 120개 판독문을 생성한다.
- 정답 판독문은 없다. 표적 소견 언급·음성 라벨과의 불일치·출력 형식을 평가하는 pilot이다.
  판독문 전체의 정확성·다른 질병·진단 능력 향상을 주장하지 않는다.

## 사전 고정한 설계

환자 선택은 category 내 `sha256(report-transfer-20261006|id)` 순서의 첫 20명이다.
학습 환자와 pixel hash 중복을 검사한다. E600은 과거 개발에 사용됐으며 새 독립 test가 아니다.
대상 category는 opacity / normal / not_normal_no_opacity다. 세 집단의 실제 유병률을 대표하지 않는다.

질문은 질병·box·라벨을 알려주지 않고 Findings와 Impression의 짧은 영어 판독문을 요청한다.
prompt 전문은 `run.py` 및 결과 `protocol.json`에 저장한다. 같은 greedy generation,
원본 값 보존 RGB+square padding, pan-and-scan off, 초기 cap512·EOS 미도달 시1024를 적용한다.
JSON이나 좌표만 반환하면 자연어 판독 성공으로 바꾸어 세지 않는다. model/adapter/source/pixel/token 원문을 보존한다.

## 판독문 평가 규약 — 결과 열람 전 고정

모델명·환자 정답을 제거하고 원문 순서를 섞어 assistant가 수동으로 문장을 분류한다.
이는 영상의학과 전문의 평가나 독립 평가자가 아니며, 문장의 의미 분류다. 각 판단에 근거 구절을 남긴다.

1. `report_valid`: 영상 소견을 서술하는 자연어가 있는가. 순수 box JSON/빈 목록은 실패.
2. `target`: present / possible / absent / unmentioned / invalid.
   표적은 폐렴 의심 음영과 연결 가능한 폐실질 opacity, airspace disease, consolidation,
   infiltrate 또는 pneumonia의 긍정 언급이다. 확정 표현과 가능성·감별 표현을 나눈다.
   전형적 문구가 아닌 경우도 의미로 읽으며, 단어 존재만 세지 않는다.
   단독 atelectasis·흉수·심비대·섬유화·혈관 음영 증가는 표적 양성으로 세지 않는다.
   이와 pneumonia/infiltrate가 감별로 함께 서술되면 possible로 분류한다.
   일반적인 interstitial markings만으로 감염성 airspace opacity를 추정하지 않는다.
3. `contradiction`: 같은 표적을 긍정/부정하는 모순이 있는 경우 별도 표시한다.
4. `laterality`: 긍정/가능성 표적에 명시한 right / left / bilateral / unspecified를 기록한다.
   bbox에는 폐엽 정답이 없으므로 upper/lower lobe 정확도를 평가하지 않는다.
   좌우 mapping 검증 전에는 laterality 일치율을 계산하지 않는다.

주지표는 양성 라벨에서 present+possible 언급률과 음성 두 집단 각각의 present+possible 언급률이다.
present만의 결과, 자연어 출력 성공률·절단·모순도 따로 보고한다. 표적이 있다는 GT에서도
표적 대신 다른 이상만 기술하면 표적 누락이다. 음성 라벨과 다른 언급은 label-discordance이며
GT 불완전성 때문에 곧바로 임상적 hallucination이라고 단정하지 않는다.
전체 원문과 분류 근거를 공개하며 애매한 표현은 해석을 숨기지 않는다.

pair별 새로 언급 / 언급 소실 / 유지와 환자 paired bootstrap CI를 함께 계산한다.
개선이 표적 무차별 언급 증가로 설명되는지 반드시 본다. 60명 단일 seed·단일 prompt pilot으로
작은 차이·무효과·일반적 망각을 확정하지 않는다. 보고서 어휘 개선이 영상 사용 개선이라는
증명도 아니므로 긍정 결과면 더 큰 독립 집단·영상 교환 대조·전문가 검토를 후속으로 검토한다.

## 실행·원본

프로젝트 root에서 medgemma Python으로 실행:

```bash
python -m manual_experiments.rsna_report_transfer.run prepare
python -m manual_experiments.rsna_report_transfer.run worker --model base --gpu 1
python -m manual_experiments.rsna_report_transfer.run worker --model sft --gpu 0
python -m manual_experiments.rsna_report_transfer.run blind
```

결과는 `research/results/manual_rsna_report_transfer_20261006/`에 보존한다.
오케스트레이터 재개·GOAL 변경·새 학습·보호 reserve 개방은 하지 않는다.
