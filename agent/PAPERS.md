# 읽어볼 논문

읽은 논문은 [ ]를 [x]로 바꿔 두세요.

## [ ] Why Does Grounding Hurt Medical VQA? Benchmarking, Diagnosis, and Fine-Tuning of Vision-Language Models (Chen et al., 2026)

- 링크: https://arxiv.org/html/2604.27720v2
- 추천: iter_016, 2026-09-27
- 지금 하고 있는 것: RSNA E600에서 B0−M0의 strict S_scope 차이 −0.255가 semantic_v1 적용 후 −0.0317로 줄었다. P180의 예측 bbox reader는 unavailable보다 +0.1278 [0.0556, 0.2000], 동일 환자 direct M0보다 +0.0778 [0.0278, 0.1333] 높았다. 근거는 research/results/iter_016/e600/report.json과 연결된 원시 QA 출력이며 리뷰에서 독립 재계산했다.
- 추천 이유: 이번 진단은 형식과 실제 답변 성능을 분리했고, 모듈형 구성의 제한된 개선도 확인했다. 논문의 형식 rehearsal·실제 grounding supervision 대조와 인터페이스 비교는 다음 원인 진단에 도움이 된다. 논문의 crop 결과를 원본 영상+bbox text 결과에 그대로 적용할 수 없고, 이번 연구의 독립 일반화·좌표 활용·신규 기여는 미검증이다.
- 읽어볼 부분: IV-C와 Table III에서 direct·self·oracle의 공정한 비교 조건을, IV-D와 Table IV에서 형식 복구와 실제 위치 능력을 나누는 대조를 먼저 본다. V Limitations에서는 인터페이스 효과의 관찰과 원인 해석을 구분하는 범위를 확인한다.
