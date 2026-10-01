# 읽어볼 논문

읽은 논문은 [ ]를 [x]로 바꿔 두세요.

## [ ] Why Does Grounding Hurt Medical VQA? Benchmarking, Diagnosis, and Fine-Tuning of Vision-Language Models (Chen et al., 2026)

- 링크: https://arxiv.org/html/2604.27720v2
- 추천: iter_016, 2026-09-27
- 지금 하고 있는 것: RSNA E600에서 B0−M0의 strict S_scope 차이 −0.255가 semantic_v1 적용 후 −0.0317로 줄었다. P180의 예측 bbox reader는 unavailable보다 +0.1278 [0.0556, 0.2000], 동일 환자 direct M0보다 +0.0778 [0.0278, 0.1333] 높았다. 근거는 research/results/iter_016/e600/report.json과 연결된 원시 QA 출력이며 리뷰에서 독립 재계산했다.
- 추천 이유: 이번 진단은 형식과 실제 답변 성능을 분리했고, 모듈형 구성의 제한된 개선도 확인했다. 논문의 형식 rehearsal·실제 grounding supervision 대조와 인터페이스 비교는 다음 원인 진단에 도움이 된다. 논문의 crop 결과를 원본 영상+bbox text 결과에 그대로 적용할 수 없고, 이번 연구의 독립 일반화·좌표 활용·신규 기여는 미검증이다.
- 읽어볼 부분: IV-C와 Table III에서 direct·self·oracle의 공정한 비교 조건을, IV-D와 Table IV에서 형식 복구와 실제 위치 능력을 나누는 대조를 먼저 본다. V Limitations에서는 인터페이스 효과의 관찰과 원인 해석을 구분하는 범위를 확인한다.

## [ ] TIDE: A General Toolbox for Identifying Object Detection Errors (Bolya, Foley, Hays and Hoffman, 2020)

- 링크: https://www.ecva.net/papers/eccv_2020/papers_ECCV/papers/123480562.pdf
- 추천: iter_035, 2026-09-29
- 지금 하고 있는 것: RSNA 개발 양성400명에서 detector17−SFT17의 F1@0.5 차이 +0.06688와 97.5% CI [0.01221, 0.12197]를 독립 재현했다. IoU0.3의 detector-only/SFT-only GT는 71/589·77/589개였다. 근거는 research/results/iter_035/confirm800/analysis.json과 연결된 원시 예측이다.
- 추천 이유: 실제 비교에서 위치 정밀도 차이와 양방향 오류가 확인돼 오류 원인을 분리할 가치가 생겼다. 이 논문은 위치 오차·중복·background·미검출을 구분하고 oracle 분석의 혼동을 피하는 데 도움이 된다. 단일 opacity와 confidence 없는 SFT 출력에 대한 적용, 외부 일반화와 새로운 방법의 이득은 아직 미검증이다.
- 읽어볼 부분: §2.2와 Fig.1의 오류 정의, §2.3과 Fig.2의 순차 oracle 보정 편향을 먼저 읽는다. 현재 SFT-only 병변을 위치 오차와 실제 미검출로 어떻게 나누고, GT 상한을 실용 성능과 어떻게 구분할지 확인한다.

## [ ] Generalised Medical Phrase Grounding (Zhang, Chandra and Nicolson, 2025)

- 링크: https://arxiv.org/html/2512.01085v1
- 추천: iter_046, 2026-10-01
- 지금 하고 있는 것: 동일 T305 annotation으로 MedGrounder-P를 적응시켰다. 개발 V96 96명·192문장에서 고정 threshold F1@0.3이 0.395313→0.578646으로 개선됐고 차이의 97.5% CI는 [0.113366, 0.254863]이다. A/P device-seconds 비율은 1.009 [0.984, 1.035]였다. 근거는 research/results/iter_046/eval/report.json과 원시 출력·timing이며 리뷰에서 독립 재계산했다.
- 추천 이유: 복합 비교는 불확정이지만 모듈형 baseline의 직접 적응 효과는 사전 양성 기준을 충족했다. 논문은 이 긍정적 결과를 해석하고 다음 VLM 비교에서 적응·후처리·모듈형 대안을 공정하게 다루는 데 직접 도움이 된다. 현재 결과는 독립 일반화, C 대비 비열등성, 공동 요청·보고서 과제의 이점을 증명하지 않는다.
- 읽어볼 부분: V-C1과 Table VII에서 사전학습과 target 적응을 구분한 대조를 먼저 보고, V-C2와 Table VIII에서 threshold·WBF의 효과를 확인한다. III-B의 집합 예측 구조를 함께 읽되 논문 지표와 현재 F1@0.3/0.5를 직접 동일시하지 않는다.
