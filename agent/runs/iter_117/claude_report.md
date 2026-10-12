# 요약

- 고정 174명·696요청 본비교를 완료했습니다.
- R의 교정은 0/40명, 확정 오답 손상은 0/47명, 미해결은 43/87건입니다. 원 판정은 **불확정**입니다.
- 수치 검산은 통과했지만 worker의 GT 파일 hash 접근이 계획의 읽기 분리 조건과 달라 **SELF_CHECK: FAIL**로 전달합니다.

# Work Performed

기존 TECH와 원 표본·prompt·parser·성공 기준을 재사용했습니다. 평가 verifier를 보완하고 사전 잠금 후 두 GPU에서 실행했습니다. 기존 결과는 변경하지 않았습니다.

# Files Changed

새 소스 5개: `ed117_run.py`, `ed117_processor.py`, `ed117_analyze.py`, `ed117_verify.py`, `test_ed117.py`.

상세 기록: [RESULTS.md](/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_117/RESULTS.md)

# Commands / Experiments

- `python ed117_run.py prepare`, `lock`, `launch`, `seal`: 모두 exit 0.
- 기존 fixture 32/32, 보완 fixture 35/35, processor 4입력 대조 통과.
- `python ed117_analyze.py ...`, `python ed117_verify.py`: exit 0, 독립 검사 **458/458 통과**.

# Results

불일치 87명의 보수적 정답 수는 R **26명**, 초안 유지 **47명**, 다수결 **54명**, 단순 합의 S **53명**입니다. R의 미해결 배정에 따른 정답 범위는 **26–69명**으로, 성공을 확정할 수 없습니다.

본생성은 **14.56분**, GPU당 2 worker로 완료했습니다. OOM은 없었습니다. 결과는 `results/iter_117/eval/`과 `gen/MAIN/`에 보존했습니다.

# Goal Progress / Reused Assets

미실행 본비교가 실제 출력으로 완료됐습니다. 불일치 집단의 resolved R **44/44건이 초안을 유지**했습니다. 응답 유보·기초 수행·초안 영향은 완전히 분리되지 않았으며, 일반적 한계나 신규 기여는 입증하지 못했습니다.

# Problems

잠금 목록에 평가 파일까지 포함해 worker가 GT/labels의 바이트 hash를 읽었습니다. GT를 모델 입력으로 사용하지는 않았지만, 계획의 worker 읽기 금지 조건과 엄밀히 다릅니다. 이 운영 불일치를 수치 검산 통과와 분리해 리뷰해야 합니다.

# Recommendation to GPT

원 불확정 판정과 운영 불일치를 독립 full review에서 판단하십시오. 현재 frozen R 설정의 확대는 권하지 않습니다. 추가 실험은 시작하지 않았으며, 다음 반복은 사용자 승인 대상입니다.

SELF_CHECK: FAIL
SUMMARY: 174명·696요청과 독립 검산을 완료했으나 R 교정 0/40명·미해결 43/87건으로 불확정이며, worker의 GT hash 접근 조건 불일치를 리뷰에 전달한다.