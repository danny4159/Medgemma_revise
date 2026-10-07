# 요약

- **핵심 결과:** 선택된 epoch1의 V32 판독 64건을 생성했고(R/G 각 32건, 전부 EOS 종료), 저장된 epoch2/6·base와 비교했다. 사전 기준상 **불확정**이다. 원 계획의 규칙대로 현재 recipe의 선택 보완 투자는 보류하는 쪽이다. 선택 보완 시험 제안은 하지 않는다.
- **근거:**
  - 환자 평균 strict recall(recall 적격 20명)은 R epoch1 0.125, epoch2 0.167, epoch6 0.200이다. G는 0.100, 0.167, 0.167이고 base는 0.167이다.
  - R epoch6−1은 +0.075(95% CI [-0.10, 0.25])이다. 증가 3명·감소 1명이다. 한 환자를 제거하면 +0.026~+0.132이고, 두 모호성 민감도에서도 양의 방향이다. 기준 (a), (b)는 충족한다.
  - 기준 (c)(오류 비증가)는 해석에 따라 판정이 갈린다. 저장된 규약으로는 R epoch1의 명시 모순 0명이 epoch6에서 3명(모호 2건 제외 시 2명)이 된다. 이 중 우측 경유 중심정맥관 대 reference의 subclavian vein, 좌우 반대인 humeral prosthesis는 유효한 충돌이다.
  - epoch1은 "No significant radiological findings." 위주(R 25/32, G 27/32)이다. 확정 양성 소견이 있는 환자의 일반 정상문 단독 출력까지 모순으로 세는 해석에서는 R epoch1이 13명, epoch6이 9명이라 (c)가 통과한다. 사전에 정한 대로 이는 불확정이다.
  - R epoch2−1은 한 환자를 제거하면 평균이 음수가 되어(-0.009) (b)를 충족하지 못한다.
  - 후반 R도 base 대비 R epoch6−base는 +0.033(CI [-0.075, 0.175])에 그친다. R epoch1은 base보다 낮다(-0.042). G는 R과 구분되는 회복이 없고(G6−R6 -0.033), G 단독 회복 근거도 없다.
- **미검증·주의:**
  - V32는 반복 사용한 개발 자료이며 독립 확인이 아니다. 판정은 assistant 검토(모델명을 가린 상태)이며 전문의 판독이 아니다.
  - R epoch6−1의 3명 증가 중 1명(V27A01)은 모호한 reference에 의존한다.
  - 별도 집계 검증(recall·차이·한 환자 제거·누락/중복·원문 anchor·completion hash)은 일치했다. 의미 판정 자체의 독립 검증은 아니다.
  - 기존 결과 파일은 덮어쓰지 않았다.
- **다음:** 이 recipe의 추가 epoch·seed·위치 loss 투자는 보류한다. 후반 R의 +0.075와 오류 해석 의존성은 관찰로 보존한다. 선택 보완을 다시 열려면 일반 정상문 처리와 모순 판정 규약을 먼저 고정한 독립 환자 집단이 필요하다.

# Work Performed

- 계획의 확정 사항을 확인했다. R/G checkpoint_000064.pt의 SHA256을 재계산해 `selection/final.json` 기록과 일치함을 봤고, V32 requests·reference v3·저장 판정 hash를 `results/iter_094/input_manifest.json`에 기록했다.
- 기존 생성 연산(`report90_recovery_gen` 경로)은 그대로 두고 출력·runtime cache 경로만 iter_094로 바꾸는 wrapper `report94_gen.py`를 만들었다. parent와 worker가 같은 진입점을 쓴다. 기존 queue·trainer·config는 수정하지 않았다.
- GPU1에 R, GPU0에 G를 각 1 worker로 배정해 64건을 생성했다. 각 launch wall은 143~147초다. 실행 직전 두 GPU 모두 24GB 중 약 24.0GB가 비어 있었다.
- 신규 출력을 모델명을 가려 블라인드 파일로 만들고 reference 원문과 비교해 판정했다. 저장 판정과 같은 문장(Pacemaker, Tracheostomy tube 등)의 규약 일치를 대조했다.
- 사전 기준 (a)(b)(c)를 코드화해 평가하고, 변경된 strict 사례와 모든 명시 모순 후보(14건)를 reference와 대조했다. (c)의 해석 민감도를 계산했다. 별도 집계 검증도 수행했다.

# Files Changed

신규 소스(`research/`): `report94_gen.py`, `report94_launch.py`, `report94_check.py`, `report94_blind.py`, `report94_judgments.py`, `report94_analyze.py`, `report94_sens.py`, `report94_verify.py`. 보조 출력 스크립트는 `report94_texts.py`, `report94_show.py`, `report94_cases.py`, `report94_precedent.py`, `report94_precedent2.py`다. 기존 파일은 수정하지 않았다. 결과는 `results/iter_094/`에만 저장했다(`gen/`, `semantic/epoch1/`, `analysis/`, `input_manifest.json`).

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python report94_launch.py`(background): 성공, exit 0. R·G 모두 코드 0, `completion.json` 생성. 도중 supervisor 대기는 `../experiment_wait.py --pid 514441`로 했고 135초에 종료를 확인했다.
- `python report94_check.py`: 성공. 64건 모두 EOS 종료, cap 확장 0, 빈 출력 0, record/request/protocol digest와 입력 ID가 일치하고 이미지 hash도 일치했다.
- `python report94_blind.py`, `python report94_judgments.py`, `python report90_semantic_eval.py --stage ...`: 성공.
- `python report94_analyze.py`: 성공. `python report94_sens.py`: 성공. `python report94_verify.py`: 성공(13/13 PASS).
- 실패와 차단: 처음의 heredoc `python -`, `$(...)` 형식 명령 몇 개는 권한 검사로 거부되어 스크립트 파일 방식으로 바꿨다. `ps`는 승인이 필요해 쓰지 않았다. 도중 `sleep`은 차단되어 `experiment_wait.py`를 썼다.

# Results (수치와 결과 파일 경로)

환자 평균 strict recall(전체 32명, 비정상 21명, recall 적격 20명):

| 조건 | strict recall | 확정 소견이 있는 환자의 일반 정상문 단독 출력 | 명시 모순 환자 |
|---|---|---|---|
| base | 0.1667 | 12 | 7 |
| R epoch1 / 2 / 6 | 0.125 / 0.1667 / 0.200 | 14 / 7 / 8 | 0 / 1 / 3 |
| G epoch1 / 2 / 6 | 0.100 / 0.1667 / 0.1667 | 16 / 8 / 5 | 0 / 1 / 2 |

- 모순 환자 수는 저장 규약 기준이다. 세 가지 해석(저장 규약, 모호 제외, 일반 정상문을 모순으로 계산)별 수치는 `analysis/sensitivity.json`에 있다.
- 사전 판정 (paired bootstrap 10,000회, seed94017):

| 비교 | 평균 차이 | 증가/감소 | 한 환자 제거 최소 | (a) | (b) | (c) |
|---|---|---|---|---|---|---|
| R epoch6−1 | +0.075 | 3/1 | +0.026 | 충족 | 충족 | 저장 규약은 미충족, 일반 정상문 해석은 충족 |
| R epoch2−1 | +0.042 | 3/1 | -0.009 | 충족 | 미충족 | 저장 규약은 미충족 |
| G epoch6−1 | +0.067 | 4/1 | +0.018 | 충족 | 충족 | 저장 규약은 미충족 |
| G epoch2−1 | +0.067 | 4/1 | +0.018 | 충족 | 충족 | 저장 규약은 미충족 |

- 위 표는 일반 정상문 해석(모순 계산 규약 (3))에서는 R/G epoch6−1 모두 (c)가 충족되고, 저장 규약과 모호 제외에서는 미충족임을 뜻한다. R epoch6−1의 CI는 [-0.10, 0.25], G epoch6−1은 [-0.092, 0.225]다.
- 확정 양성 소견이 없다고 판정한 이유 중 하나로, epoch1 #13(우측 중심정맥관)은 reference의 tip 위치 부재로 모호 표시했다. 이를 type_only로 바꾸면 R epoch6−1은 평균 +0.125, 증가 3명·감소 0명이 된다. 결론은 같다.
- 해석: 사전 정한 대로 (a)(b)는 R epoch6에서 충족되고 (c)는 해석에 따라 판정이 뒤집히므로 **불확정**이다.
- 결과 파일: `results/iter_094/analysis/{summary,sensitivity,verify}.json`, `results/iter_094/semantic/epoch1/eval/{report,per_output}.json`, `results/iter_094/gen/{R,G}_epoch1/`, `results/iter_094/input_manifest.json`.
- 비용: 두 GPU 병렬 생성 wall은 약 147초다. 실제 지배 비용은 사례별 의미 검토였다. 시간·GPU 상한은 적용하지 않았다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- 진전: 선택된 epoch1 checkpoint의 동일 V32 판독이 없어 판단하지 못하던 결측을 채웠다. epoch1은 정상문으로 거의 수렴해 있고, 후반 checkpoint의 소견 회복이 오류 비용 해석에 의존한다는 관찰을 확보했다.
- 미검증: 독립 환자 집단 재현, 전문의·독립 평가자 판정, 일반 정상문 처리 규약의 고정, 위치 supervision의 인과 효과, 다른 seed·LR1e-4. 이번 결과를 독립 확인으로 부르지 않는다.
- 재사용(검증 범위): `report90_recovery_gen`/`report90_gen_safe`/`report90_gen`의 생성 연산을 재사용했다. 입력 tensor와 공식 chat template 동일성은 worker 안의 기존 검사로 확인되고, `input_ids`가 저장된 epoch6 출력과 64건 모두 같다. `report90_semantic_eval`의 집계기는 그대로 사용했고, `report93_sens`와 `report92_autojudge`의 자동 판정은 쓰지 않았다. 기존 queue와 trainer는 실행하지 않았다.
- 새 wrapper의 실제 중단·재개와 변조 거부는 이번에 별도로 시험하지 않았다. 기존 경로의 재개 검사에 의존했으며 이번 64건은 단일 launch로 완료됐다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- 현재 결론 무효: 없음.
- 한계(결론 해석 관련): 일반 정상문 처리 규약이 저장 판정 안에서 불일치한다. base의 "Normal chest X-ray."는 모순으로, epoch1·2·6의 "No significant (radiological) findings."는 unknown으로 계산돼 있다. 이 불일치가 (c) 판정의 해석 의존성을 만든다. 기존 판정은 소급 변경하지 않았다.
- 재사용 전 수정: `report94_gen.py`는 `report90_gen.OUT`을 모듈 전역으로 덮어쓰는 방식이라 다른 경로에 재사용할 때 같은 방식으로 지정해야 한다. 판정 스크립트 `report94_judgments.py`는 이번 32명 전용 표이며 범용 의미 평가기가 아니다.
- 추후 개선: 모순 후보 7건의 검토 기록이 사례 단위이고 독립 평가자 합의는 없다.

# Recommendation to GPT

- 현재 recipe(NLL 선택 epoch1 + 위치 보조 CE 포함 report SFT)의 추가 epoch·seed·위치 loss 투자는 보류한다. 후반 R의 소견 회복은 +0.075 수준이며 base 대비 +0.033으로 작고 오류 해석에 의존한다.
- 이 연구 묶음을 이어가려면 새 학습이 아니라 먼저 일반 정상문·모순 판정 규약을 고정하고 독립 환자 집단에서 판독 baseline 자체의 약함(정상문 수렴)을 다룰지 결정하는 것이 우선이다. 그 결정 없이 선택 보완 시험을 추가하지 않는 것을 권고한다.

SELF_CHECK: PASS
SUMMARY: 선택 epoch1 R/G의 V32 판독 64건을 생성해 저장 출력과 비교한 결과, R epoch6−1 recall +0.075(CI [-0.10, 0.25])이나 오류 비용(c)이 일반 정상문 해석에 따라 갈려 사전 기준상 불확정이며 현재 recipe 선택 보완 투자는 보류한다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: mkdir -p results/iter_094/gen && cat > report94_gen.py <<'EOF'
"""iter_094: 기존 recovery 생성 연산(report90_recovery_gen)을 유지하고 출력·cache 경로만 iter_094로 격리한다.
parent와 worker subprocess 모두 이 파일을 진입점으로 쓰므로 OUT이 일관된다."""
import argparse
from pathlib import Path
import report90_gen as C
import report90_gen_safe as S
import report90_recovery_gen as RG  # load_model·SOURCES 패치 적용
from report86_common import sha

OUT=Path(__file__).resolve().parent/'results/iter_094'
C.OUT=OUT
C.SOURCES=C.SOURCES+['report94_gen.py']
C.__file__=__file__

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['worker','launch']);p.add_argument('--requests',required=True);p.add_argument('--out',required=True)
    p.add_argument('--checkpoint');p.add_argument('--workers',type=int,default=2);p.add_argument('--shard',type=int,default=0);p.add_argument('--gpu');p.add_argument('--limit',type=int,default=0);p.add_argument('--peak-mib',type=int,default=12000)
    a=p.parse_args();raise SystemExit(C.worker(a) if a.command=='worker' else S.launch(a))
EOF
python -c "
import report94_gen as W
print(W.C.OUT, W.C.__file__, W.C.SOURCES[-4:])
p=W.C.protocol('results/iter_090/data/V32/requests.json','results/iter_090/recovery/train/R_lr0.0002/checkpoint_000064.pt');print(p['checkpoint_sha'][:8],list(p['code']))"
- Bash: python ../experiment_wait.py --pid $(pgrep -f "report94_launch.py" | head -1) --timeout 600
- Bash: ps -o pid,ppid,etime,cmd -p 514439,514441,514673
- Bash: python - <<'EOF'
import json
from pathlib import Path
R=Path('results')
def rows(p):return [json.loads(l) for l in Path(p).read_text().splitlines()]
old={r['id']:r for r in rows(R/'iter_090/recovery/validation/epoch6/R_lr0.0002_report/worker_0.jsonl')}
for m in 'RG':
    new=rows(R/f'iter_094/gen/{m}_epoch1/worker_0.jsonl')
    print(m,len(new),len({r['id'] for r in new}),'eos',sum(r['attempts'][-1]['ended_eos'] for r in new),'multi-attempt',sum(len(r['attempts'])>1 for r in new),
      'ids_match',all(r['input_ids']==old[r['id']]['input_ids'] for r in new),'empty',sum(not r['text'].strip() for r in new),'gpu',{r['gpu'] for r in new},
      'words',sum(len(r['text'].split()) for r in new)/len(new))
EOF
