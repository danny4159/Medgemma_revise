These are only the leftover wait-loop notifications from the full-stage pipeline. They carry no new results, so nothing changes.

The final report above stands: G did not beat C or U (full-train G−C −0.041, G−U +0.001), and C_compute was not run. SELF_CHECK stays FAIL because the GPU loss check A missed its preset tolerance.

SELF_CHECK: FAIL
SUMMARY: GIoU 가중 pseudo-box 학습(G)이 실제 생성 bbox에서 직접 SFT(C)와 균등 대조(U)를 넘지 못했다(full G−C −0.041, G−U +0.001, C_compute·독립 확인 미실행). GPU 검사 A가 사전 허용 오차 기준으로 FAIL이라 SELF_CHECK는 FAIL이다.