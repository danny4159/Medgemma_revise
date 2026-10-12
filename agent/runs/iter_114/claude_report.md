# 요약

- **핵심 결과:** 새 환자 68명·87개 소견에서 CURE 불일치가 놓치지 않은 오류는 16개, 의료 적응 MSPC 불일치는 15개, MG confidence는 13개였다(검토 22개). A(confidence 대비 재현)와 B(MSPC 대비 추가 가치)는 모두 사전 기준 미달이어서 **불확정**이다.
- **근거:** ΔA=+3/87(+3.4pp), 98.75% 구간 [−6.0, +12.1]pp이고 ΔB=+1/87(+1.1pp), 구간 [−8.7, +8.0]pp다. 둘 다 최소 유용 효과 5pp에 못 미치고, 구간 하한이 0 아래이며, 주석·동률 보수 범위도 0 이하(A [−3,+12], B [−7,+9])다.
- **미검증·주의:**
  - 최대 규모에서도 5pp 효과를 정밀하게 판정하지 못했다(반폭 9.0pp, 8.4pp).
  - 87개 중 42개는 주석 상태가 미확정이다.
  - MSPC의 학습 이력은 논문과 코드 수준의 근거만 있다.
  - 새 학습은 하지 않았다.
- **다음:** 방법 개발은 제안하지 않고, 신규 근거 없는 추가 표본·모델 발주도 하지 않는다. 사용자 승인을 기다린다.

# Work Performed

- 계획의 원 기준(표본 규칙·운영점 0.8·K=ceil(N/4)·ΔA/ΔB·확대 규칙)은 바꾸지 않고 구현해 실행했다.
- 자료 적합성: pinned metadata에 기존 `image_pool('test')` 규칙을 그대로 적용해 80명·100개를 얻었다.
  - results/ 전체 json/csv/txt/md/jsonl 내용과 파일명, 영상 hash 스캔으로 과거 사용 11명을 제외했다.
  - 최종 69명·88개, 초기 36명·47개로 모델 출력 전에 잠갔다.
  - 이는 계획의 예상과 정확히 일치한다.
- MSPC 확보: 공식 Drive 폴더에서 `medgrounder_finetune_mspc.pth`(sha256 `ec33f4a6…95c2`)를 받았다.
  - 저장소 스냅샷에 LICENSE 파일이 없어, 가중치 이용 조건은 확인되지 않았다고 기록한다.
- 개발 47개 점검(결과 비공개 전):
  - 대상 MG A_U_e5를 새 경로로 재실행하면 저장된 iter_046 출력과 박스 차이 최대 7.7e-6이다.
  - MSPC의 union IoU≥0.3 항목은 40/47(A는 32/47)이어서 하한 28/47을 넘는다.
  - 단, 이 47개는 PadChest-GR train split이라 MSPC가 학습에 썼을 수 있다. 자산·좌표 연결과 하한 확인일 뿐 비편향 성능이 아니다.
- CURE는 T4 4개 요청에서 입력 token, pixel hash, 생성 token, parser 결과가 iter_107과 전부 일치했다.
- 실행기 신규 작성:
  - `nr114_mg.py`는 MG 공식 소스를 그대로 호출하는 worker와 launcher다.
  - `nr114_cure.py`는 nr107 실행기를 새 입력·경로에 맞춰 분리한 판본이다.
  - 둘 다 정적 분할, flock, record digest, 손상 tail 복구, 정확한 요청 집합 검사, protocol 잠금을 갖췄다.
- 분석 코드: `nr114_core.py`가 세 순위와 ΔA/ΔB, 보수적 범위, 환자 bootstrap 20,000회(seed 113)를 계산한다.
  - `nr114_run.py`는 단계 잠금, 부분 산출물 방지, digest 연결 seal을 담당한다.
  - `nr114_verify.py`는 독립 재계산이다(포함-배제 면적, 원 float 순위, 같은 bootstrap 절차).
- 실행 순서와 확대 결정:
  1. 코드·규칙을 잠근다.
  2. 초기 36명을 생성한다.
  3. 초기 분석을 한다.
  4. 사전 확대 규칙으로 확대를 결정한다.
  5. 나머지 33명을 생성한다.
  6. 누적 분석을 하고 독립 검증, 비용 집계, 판정, seal을 마친다.
  - 초기 분석에서 A는 상한 0.143, B는 상한 0.109이고 반폭이 모두 0.05를 넘어, 규칙대로 최대 집단까지 한 번 확대했다.

# Files Changed

- 반입: `mg45_mg.py`, `nr107_run.py`, `nr107_data.py`, `report86_common.py`, `pg39_data.py`, `pg39_spec.py`, `pg43_run.py`, `rsna_diag/*`
  - 14개 파일의 blob이 manifest와 일치함을 `git hash-object`로 확인했다.
  - `mg45_mg.py`, `nr107_data.py`는 수정하지 않았다. `nr107_data.py`의 모집단 생성은 실행하지 않았다.
- 신규(`research/`):
  - 자료·자산: `nr114_data.py`, `nr114_weights.py`
  - 실행: `nr114_mg.py`, `nr114_cure.py`
  - 분석: `nr114_core.py`, `nr114_run.py`, `nr114_verify.py`, `nr114_cost.py`
  - 점검: `nr114_devcheck.py`, `nr114_mgcompare.py`, `nr114_curecheck.py`, `nr114_mgtests.py`, `nr114_curetests.py`, `nr114_tests.py`
- 결과: `results/iter_114/` 아래.
  - `data/`, `external/weights/`, `protocol/`, `dev/`, `mg/`, `cure/`, `tests/`
  - `analysis/`(r0, 대체된 기록)
  - `analysis_r1/`(최종 판정과 seal)

# Commands / Experiments

모두 성공했다. 실패와 정정은 "Problems"에 따로 적는다.

- **MG 실행 경로 검사 (`nr114_mgtests.py`):**
  - 중단 후 재개와 손상 tail 복구(처음 10행 보존, 비중단 대비 최대 차이 1.1e-5)
  - 동시 launcher 거부
  - 변조 6종 거부
  - 허용 GPU 밖 배치 거부
- **CURE 실행 경로 검사 (`nr114_curetests.py`):**
  - 같은 항목에 대해 재개 후 생성 token이 일치했다.
  - 위와 같은 거부 검사를 통과했다.
- **분석 fixture:** 43개 전부 통과(`fixtures_core_r1.json`). 소형 무작위 60건에서 보수적 범위를 전수 열거와 대조한 검사를 포함한다.
- **본 실행:**
  - MG A와 MSPC는 INIT 47개·EXPAND 41개를 각 2 worker×batch 4로 생성했다.
  - CURE는 INIT 262초, EXPAND는 약 35분 이내에 생성했다. 비EOS 재시도는 0건이다.
- **자원 구성 비교:**
  - MG는 worker 1개와 2개, batch 4와 8을 비교했다. 개발 47개에서 박스 최대 차이는 2e-5 이하다. 처리량은 4.3→4.7(batch 8)→5.7(2 worker) items/s이다.
  - MG의 peak는 batch 4에서 1.3GiB, batch 8에서 1.8GiB로 모두 작아, 전체 비용에서 MG는 지배 비용이 아니다.
  - CURE는 GPU당 1 worker로 고정했다. 실측 점유가 약 10.07GB여서, 2 worker/GPU는 2×(10,100+2,048)=24,296MiB로 free 24,039MiB를 넘는다.
- **비용 (실측, 적재 포함/제외):**

| 모델 | warm | cold |
|---|---|---|
| CURE | 901.6s | 986.8s |
| MSPC | 31.0s | 59.6s |
| A(공통) | 31.5s | 61.2s |

  - 세 번째 열은 적재 시간을 더한 값이며, A의 비용은 두 조합에 공통이다.
  - 영상 입력부터 순위까지의 전체 서비스 비용이 아니라 모델 처리 구간만 포함한다.

# Results

- 초기 평가(`analysis_r1/result_init/report.json`): N=46, K=12, 환자 35명, 포착은 CURE/MSPC/confidence 모두 7로 같다. ΔA=ΔB=0이다.
  - 98.75% 구간은 A [−15.6, +14.3]pp, B [−17.0, +10.9]pp.
- 최종 누적(`result_final/report.json`): N=87, K=22, 환자 68명, 공식 주석 오류 37.

| 순위 | 포착 | precision |
|---|---|---|
| CURE 불일치 | 16 | 72.7% |
| MSPC 불일치 | 15 | 68.2% |
| confidence | 13 | 59.1% |

- 최종 구간(98.75%, 설명용 95% 병기):

| 비교 | Δ | 98.75% 구간 | 95% 구간 | 반폭 |
|---|---|---|---|---|
| ΔA | +3.4pp | [−6.0, +12.1] | [−3.7, +10.3] | 9.0pp |
| ΔB | +1.1pp | [−8.7, +8.0] | [−6.8, +6.3] | 8.4pp |

- 보수적 범위(동률+주석 모호성): A [−3,+12]개, B [−7,+9]개. 환자 제거에서 음수로 바뀌는 경우는 없었다(A 최소 +2, B 최소 +1).
- 상보성(A): CURE만 잡은 오류 9개(9명), confidence만 잡은 오류 6개(6명), 공통 7개, 둘 다 놓침 15개.
- 상보성(B): CURE만 7개, MSPC만 6개, 공통 9개, 둘 다 놓침 15개.
- 독립 verifier: 21개 검사 전부 PASS(init, final 각각). 위험 값의 최대 차이는 8.9e-16이고, bootstrap 배열이 동일하다.
- 판정(`analysis_r1/judge.json`): A는 불확정, B는 불확정이다. MSPC 비용이 CURE보다 낮지만 B 상한(0.080)이 0.05 이상이어서 "일반 대조 충분"은 성립하지 않는다. seal(`completion.json`) 완료.

# Goal Progress / Reused Assets

- **시험 설정:** iter_113의 12/47(포착 9 대 6)에서 출발한 신호가 새 환자 87개로 늘리자 3개 차이(+3.4pp)로 줄었다. 최소 유용 효과에 이르지 못했고 정밀도도 부족하다. 이 설정은 더 확대하지 않고 보류하는 쪽이 합리적이다.
- **연구 관찰:**
  - iter_113의 양성 신호는 이번 표본에서 재현 방향(양)이지만 크기가 작고 구간이 0을 포함한다.
  - MSPC 조합은 CURE 조합과 거의 같았다(15 대 16). 일반 grounder 조합이 같은 정보를 대부분 설명할 가능성을 배제하지 못했고, CURE 특수 이득도 확인하지 못했다.
- **연구 질문:** 불일치 정보 전체의 가치는 기각하지 않는다. 같은 설정의 추가 표본·점수·모델 순회는 정보 가치가 낮아 권하지 않는다.
- **미검증:**
  - 공개 정답 위치 주석에 대한 오류 검토이며 임상 오진이나 자유 판독 정확성이 아니다.
  - MSPC와 대상 MG는 구조와 사전학습을 공유한다.
  - CURE와 MSPC의 학습 이력은 같은 수준의 증거로 확인되지 않았다.
  - 새 환자는 "우리 파이프라인 미사용"일 뿐 공개 모델 미노출이 아니다.
- **재사용 검증:**
  - 반입 14개 blob 일치, 실제 import, CURE 공식 chat template 일치(token 일치)
  - uint16→uint8 영상 변환, 환자·study·영상·pixel 중복 제외(스캔 일치 0)
  - 변조·재개·동시 실행 검사
  - 새 protocol digest에 실행 소스, 가중치, 요청 hash 연결
  - 비정사각 좌표는 개발 입력의 MG 회귀로 확인했다.

# Problems

- **현재 결론 무효:** 없음.
- **정정 (구현 오류, 투명하게 기록):**
  - 첫 분석(r0)의 link가 대상 MG 박스의 범위 검사를 빠뜨렸다. iter_113의 `check_boxes("mg")` 규칙에서 누락된 것이다. 독립 verifier가 initial에서 y 범위를 벗어난 A 박스 1개(item 5cc1e30b95c41696, y∈[−0.0088, 1.078])를 발견했다.
  - 원 규칙 구현 오류 수정이며 새로운 과학적 기준이 아니다. r0 INIT 결과(N=47, ΔA=0, ΔB=−1/47)는 `results/iter_114/analysis/`에 보존하고, 판정·확대에는 쓰지 않았다.
  - r1을 INIT 출력 이후, r0 점추정을 본 뒤에 잠갔다(`protocol.json`의 `amendment`에 기록). EXPAND 출력은 r1 잠금 이후에 생성했다. 확대 결정은 두 버전(r0, r1) 모두에서 같다.
- **재사용 전 수정:**
  - `nr114_cure.py`의 PEAK_MIB를 T4 이후 10100으로 바꿨다. T4 검사는 이전 상수의 코드로 수행했고, 생성 로직과는 무관하다.
  - nr107 실행기에서 이어받은 일반화 결함은 이번 경로에서만 보완했다.
- **추후 개선:** CURE 비용은 모델 처리 구간 한정이며 영상 입력부터 순위까지의 서비스 비용은 미측정이다. MG HF 캐시는 iter_045 경로를 읽기 전용으로 사용했다.

# Recommendation to GPT

- **다음 투자:** 이번 한정 확인에서는 A와 B 모두 불확정이다. 새 학습·방법 pilot은 제안하지 않는다. 같은 설정에서 표본을 더 늘리지 않는다(최대 집단이 소진됐다).
- **보류 범위:** CURE 불일치 순위의 오류 검토 투자만 보류한다. 불일치 정보 전체나 일반 grounder ensemble의 가치는 기각하지 않는다.
- **대안:** (a) 이 묶음 종료·보존 후 다른 잔여 질문으로 이동. (b) 서로 다른 계열 grounder 쌍의 불일치를 보는 후속은 새 모델 도입이 필요하므로 사용자 결정 대상이다.

SELF_CHECK: PASS
SUMMARY: 새 환자 68명·87개에서 CURE 불일치 포착 16, MSPC 불일치 15, confidence 13(검토 22개); ΔA +3.4pp[−6.0,+12.1], ΔB +1.1pp[−8.7,+8.0]로 A·B 모두 불확정이며, 구현 오류 정정(r0→r1)·독립 검증·seal을 마쳤다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: cat results/iter_113/protocol.json | head -c 5000; echo; cat results/iter_113/ledger.json | head -c 1500; ls results/environments/; ls -d results/iter_045/env/* ; grep -rl medgrounder_iter045 results/iter_045/logs 2>/dev/null | head -3; ls ~/.conda/envs 2>/dev/null; which python
- Bash: git show bab147379dde1bcd68550e298cc596ee15091e99:mg45_vrun.py; cd results/iter_045/external/MedGrounder/conf; cat conf_finetune_mspc.yaml conf_pretrain_imagenome.yaml; diff conf_finetune_ms.yaml conf_finetune_mspc.yaml; cat datasets.yaml | head -50
- Bash: python -c "import gdown;print(gdown.__version__)"; ls results/environments/medgrounder_iter045/bin | head -5; results/environments/medgrounder_iter045/bin/python -c "import torch;print(torch.__version__, torch.cuda.is_available())"; df -h results | tail -1; head -30 results/iter_045/external/weights/download.log | cut -c1-200
- Bash: results/environments/medgrounder_iter045/bin/python -c "import torch;print(torch.__version__, torch.cuda.is_available())"
- Bash: python nr114_mg.py launch --stage DEV4 --model A --workers 1 --batch 4; echo rc=$?
- Bash: python - <<'EOF'
import json, math
from pathlib import Path
R=Path('results/iter_114')
runs=json.load(open(R/'analysis/runs_init.json'))
items=[it for it in json.load(open(R/'data/items.json')) if it['stage']=='init']
def rd(d,pat):
    rows=[]
    for p in sorted(Path(d).glob(pat)):
        rows+= [json.loads(l) for l in open(p) if l.strip()]
    return rows
A={r['item_key']:r for r in rd(runs['A'],'raw_worker*.jsonl')}
P={r['item_key']:r for r in rd(runs['MSPC'],'raw_worker*.jsonl')}
def good(b): return len(b)==4 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in b) and 0<=b[0]<b[2]<=1 and 0<=b[1]<b[3]<=1
for it in items:
    for nm,D in (('A',A),('P',P)):
        d=D[it['item_key']]['detection']
        for b,s in zip(d['boxes_orig_xyxy'],d['scores']):
            if not good(b) or s<0.8: print(nm,it['item_key'],b,s)
EOF
