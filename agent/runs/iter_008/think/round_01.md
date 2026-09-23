# 사고 라운드 1

이번 라운드는 파일·코드 읽기와 웹 조사만 수행했다. 파일 생성·수정·실험 실행은 하지 않았다.

1. **Pooling 접근법 종료 유지.** `agent/runs/iter_007/review.md`, `claude_report.md`, `changed_files.txt`를 읽었다. 리뷰가 독립 재계산한 MLP 차이는 +0.000304, 95% CI [−0.001012, +0.001611]이다. 이번 라운드에서 수치를 다시 계산하지는 않았다. 이 결과는 decoder 병목의 증거가 아니다.
2. **재사용 전 수정할 결함을 코드에서 확인했다.** `research/run_pooling_probe_iter007.py:281`의 완료 조건에는 정렬·pooling·linear 검사가 빠져 있다. `research/pooling_probe/features.py`의 `verify_cache`는 현재 target·split·모델/processor digest 연결을 강제하지 않는다. 추출·학습 스크립트 모두 `CUDA_VISIBLE_DEVICES`를 덮어쓴다. 새 실험에 사용하는 경로부터 보완해야 한다.
3. **SCR은 그대로 재사용할 수 없다.** `research/results/iter_005/scr_audit.json`에 따르면 247/247 JPEG에 윤곽선 검출이 기록돼 있다. 영상은 256×256, mask는 1024×1024이며, 단일 mask의 organ 의미도 문서로 확인되지 않았다. 원본 JSRT 접근 문제를 해결하지 않고 이 자료로 anatomy 학습을 시작하면 안 된다.
4. **깨끗한 수동 anatomy 자료의 다른 경로를 찾았다.** NLM 공식 Montgomery 배포에는 개별 `CXR_png`와 좌·우 `ManualMask` 목록이 있다. 원저자 논문은 138장과 수동 lung mask를 설명한다. 실제 pixel 형식·동일 ID 연결·subject 독립성은 아직 확인하지 않았다. 병변 localization 정답이 있는 자료로 간주하지 않는다. [NLM 배포](https://data.lhncbc.nlm.nih.gov/public/Tuberculosis-Chest-X-ray-Datasets/Montgomery-County-CXR-Set/MontgomerySet/index.html), [원저자 논문](https://lhncbc.nlm.nih.gov/LHC-publications/PDF/pub9356.pdf)
5. **동일 NIH 영상에 CheXmask를 연결하는 대안도 있다.** 공식 배포는 HybridGNet이 생성한 anatomy mask와 RCA 품질 점수를 제공한다. 수동 anatomy GT가 아니라 외부 모델의 pseudo-label supervision이다. 전체 배포는 비압축 37.3 GB이므로 필요한 NIH 항목의 선택적 확보 비용을 먼저 확인해야 한다. [CheXmask 공식 배포](https://physionet.org/content/chexmask-cxr-segmentation-data/1.0.0/OriginalResolution/)
6. **단순 anatomy 추가 학습만으로는 contribution이 부족하다.** CURE는 anatomy-grounded task와 curriculum을 이미 사용하며, 논문상 최종 학습은 48 GB A6000 한 장에서 약 45시간이다. 이를 작은 frozen head로 축소하는 것은 완전 재현도 새로운 방법도 아니다. EasyLens 역시 lesion mask로 구성한 anatomy/pathology reference를 사용하므로 정상 reference 대비 feature 증폭도 차별화 근거가 약하다. [CURE 본문·학습 규약](https://arxiv.org/html/2601.15408v1), [EasyLens v3](https://arxiv.org/html/2606.06379v3)
7. **독립 확인 집단은 아직 준비되지 않았다.** `research/results/iter_005/nih_audit.json`에는 bbox 880영상·726명과 현재 선택된 160명이 기록돼 있다. 미사용 patient는 확보 후보지만, 필요한 클래스별 수는 확인해야 한다. 기존 160명은 개발 자료로 유지하며 새 NIH 집단도 외부 데이터셋 검증으로 부르지 않는다.

## 다음에 파고들 질문
- Montgomery 수동 lung mask와 CheXmask NIH pseudo-label 중 어느 경로가 입력 정합성·접근 비용·domain confound를 고려할 때 최소 전이 실험에 적합한가? 공식 schema와 파일 목록으로 다운로드량, 전처리, subject 식별 규칙을 확정할 수 있는가?
- 기존 NIH 160명을 제외하고 현재 네 클래스에서 확보 가능한 patient 수는 각각 얼마인가? 개발용 label-budget 비교와 한 번만 평가할 신규 확인 집단을 분리할 수 있는가?
- 동일 병변 label·공유 head 용량에서 anatomy pretraining 효과를 추가 update, 외부 영상 노출, 공간 prior와 분리하는 최소 대조군은 무엇인가? Anatomy 학습 자체의 성공을 어떤 독립 지표로 확인할 것인가?
- CURE·AnatomiX·EasyLens와 비교했을 때 저예산 anatomy 전이에서 아직 검증할 가치가 있는 기전 질문은 무엇인가? 그 질문을 frozen head로 검증한 뒤 실제 VLM 출력 개선으로 연결할 경로가 있는가?
