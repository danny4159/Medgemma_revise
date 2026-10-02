# 요약

- **핵심 결과:** 준비된 CheXpert 교정·보존 진단은 D 기술 gate의 oracle(정답 상태를 직접 주고 복사만 시키는 검사)에서 183/192로 멈췄다. 계획한 규칙대로 E48/F105는 실행하지 않았다. 모델 비교 결과는 없다.
- **근거:** 자료 gate는 통과했고 D 448요청은 모두 완료했다. 독립 verifier도 107개 검사를 통과했다(불일치 0). oracle 오류 9건은 형식이 아니라 내용 오류다.
- **미검증·주의:** 오류 9건은 모두 한 칸(정답=(present, absent), 초안=01)에서 나왔다. 모델이 초안을 복사하거나 (absent, absent)를 냈다. 이는 iter_047의 oracle 실패와 같은 양상이고, 계획상 prompt를 고쳐 다시 시도하지 않는다. 교정·보존 trade-off와 단순 대안의 충분성은 판단할 수 없다. 이번 결과는 기존 진단 계획 중 해당 oracle 방식의 한계일 뿐이다.
- **다음:** 이 교정 설계의 모델 비교 투자는 보류하는 것을 권고한다. 재개는 GPT 리뷰에서 oracle 내용 오류를 별도 원인 진단으로 다룰지 정한 뒤에 한다.

# Work Performed

- 반입 3파일(`cx18_data.py`, `cx18_spec.py`, `qa_spec.py`)의 git blob이 manifest와 일치함을 확인했다.
- iter_018 CheXpert 자산을 읽기 전용으로 재검증하는 `rr53_data.py`를 만들었다. `cx18_data.build`와 과거 CLI는 호출하지 않았다.
- 새 모듈을 만들었다. 기존 rr47 파일은 수정하지 않았다.
  - `rr53_spec.py`: T는 R2와 byte-identical, BT는 BJ와 byte-identical이다. oracle O2는 기존 O에 출처 우선순위 문장만 더했다.
  - `rr53_build.py`, `rr53_run.py`: 요청 생성과 실행·검증 wrapper다. 요청 집합은 manifest에서 다시 만들어 byte 단위로 대조한다.
  - `rr53_eval.py`, `rr53_verify.py`: 네 truth 조합을 동일 가중하는 macro 평가, 동시 보정 구간, 퇴화 경우의 exact 경계, 공통 valid 보조 분석과 독립 재계산이다.
  - `rr53_gate.py`, `rr53_decide.py`: D 기술 gate와 E→F 판정이다. 입력 파일 sha256을 재계산해 stale·잘못된 stage를 거부한다.
  - `rr53_sanity.py`, `rr53_gen_test.py`, `test_rr53.py`: 입력 tensor 검사, 2/4 worker·재개·변조 검사, CPU fixture다.
- 자료 gate, pilot 48요청(2/4 worker, 재개, 변조), 입력 tensor 검사를 수행했다.
- D 448요청을 4 worker로 완료하고 평가·verifier·gate를 실행했다.

# Files Changed

- 신규 코드는 모두 `research/`의 미추적 파일이다. `rr53_{spec,data,build,run,eval,verify,gate,decide,sanity,gen_test}.py`, `test_rr53.py`, 그리고 반입된 `rsna_diag/{cx18_data,cx18_spec,qa_spec}.py`다.
- 결과는 `results/iter_053/{data,requests,protocol,gen,eval,tests,REPORT.md}`에 새로 저장했다. 기존 결과·hf_cache·RETRACTION은 건드리지 않았다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `git hash-object` 반입 3파일 blob 대조: 성공.
- `python rr53_data.py check`: 성공. `python rr53_data.py build`: 성공 (manifest D16/E48/F105).
- `python rr53_build.py requests D|E|F`: 성공 (448/768/1680). `python rr53_run.py write-pilot-requests`: 성공 (48).
- `python test_rr53.py`: 최종 92/92 통과. 중간 시도에서 4건이 실패했다. 모두 테스트의 합성 설정 오류였고 production 로직이 아니었다. 실패 시도는 `fixtures_rr53_try1~4.json`에 보존했다.
- `python rr53_sanity.py --stages D,E,F`: 2,008개 입력 모두 통과. 첫 시도는 manual 경로의 `<bos>` 중복과 image token id 오류로 실패했고(`input_tensor_D.json`), 수정 후 통과했다(`input_tensor.json`).
- pilot: `P_2w`, `P_4w`, `P_resume`(SIGKILL 후 재개), tamper 모두 성공했다.
- `rr53_eval.py` 첫 실행은 `eval/` 디렉터리가 없어 실패했다. 디렉터리를 만든 뒤 성공했다. 락 대상 코드는 수정하지 않았다.
- `python rr53_run.py protocol --stage E --gate D_gate.json`: **의도대로 거부됨**(RunError). gate 강제를 확인했다.
- GPU 실행: 모두 허용 집합 0,1에서 했다.

# Results (수치와 결과 파일 경로)

- **자료:** `results/iter_053/data/data_check.json`
  - D16/E48/F의 환자·study·file/pixel 교집합은 모두 0이다.
  - legacy 정확 중복은 0이다. F는 과거 출력에 노출되지 않았다.
  - F105는 56/17/20/12명이다.
  - 사전학습 노출은 미확인이다.
- **처리량·정합성** (`tests/cmp_2w_4w.json`, `resume_result.json`, `tamper_result.json`)
  - pilot 48요청의 2w와 4w는 token 불일치 0이다.
  - wall은 2w 90.4초, 4w 75.3초다.
  - SIGKILL 20건 시점 후 재개해 48건을 완료했고 불일치는 0이다.
  - 변조 16/16을 거부했다.
  - pilot과 D의 공통 48건도 불일치 0이다(`tests/cmp_P2w_vs_D4w.json`).
- **D 실행** (`gen/D`, `eval/D_report.json`, `D_verify.json`, `D_gate.json`)
  - 4 worker, 종료 코드 [0,0,0,0], wall 437초.
  - 최종 비EOS 0, 본조건 valid 100%.
  - GPU 점유 최대 17,668/17,597 MiB, 프로세스 peak reserved 8.27 GB.
  - 4 worker를 채택한 근거는 pilot의 wall 단축과 출력 일치다.
- **oracle:** 183/192
  - CheXpert image 63/64, text 60/64.
  - PadChest image 30/32, text 30/32.
  - 틀린 9건은 모두 truth=(present, absent), draft=01에서 나왔다. 응답은 정상 JSON이고 EOS로 끝났다.
- **gate:** `run=false`. 실패한 항목은 `oracle_all_correct` 하나뿐이다. 나머지는 모두 통과했다.
- **회귀:** iter_047 D8 환자별 지표를 새 코드로 재현했다(최대 차이 0, 336값). oracle 29/32도 그대로 재현했다.
- **D16 본조건 점추정** (n=16 개발자료, 가설 판정 아님)
  - 수정률 r: R1 0.42, R2 0.41, T 0.13, BJ 0.81, BT 0.50, BI 0.84.
  - 보존 실패율 h_fail: R1 0.11, R2 0.08, T 0.25, BJ 0.19, BT 0.50, BI 0.16.
  - 이 수치로 문턱·prompt·진입 여부를 바꾸지 않았다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **재사용 검증:** blob 일치, import 연결, HF Path 고유성과 고정 digest 강제(`checked_sources`), 234행 대응, 169명 manifest 연결, 분할 재현이 모두 통과했다. 과거 build CLI는 호출하지 않았다. RSNA 정답 규약과 yes/no parser는 쓰지 않았다.
- **새로 알게 된 것:** 정답을 명시한 oracle 조건에서도 draft와 정답이 완전히 반대인 칸에서만 내용 오류가 반복됐다. image·text 모두, 그리고 CheXpert·PadChest 모두 같은 칸이다. 출처 우선순위 문장을 추가해도 해소되지 않았다.
- **미검증:**
  - 수정–보존 trade-off, 영상 기여(BJ−BT), 단순 대안의 충분성은 E를 실행하지 않아 미검증이다.
  - 원인은 확정하지 못했다. draft 복사 prior일 가능성은 있지만 내용 오류의 인과는 확인하지 않았다.
  - 이 결과는 해당 oracle 방식의 한계다. 의료 VLM 전체나 교정 과제 전체의 기각으로 확대하지 않는다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없다. D 실행은 유효하고 verifier를 통과했다.
- **재사용 전 수정:**
  - `rr53_eval/verify/gate/decide`는 `results/iter_053/eval/`이 이미 있어야 쓴다. 코드에 `makedirs`를 넣으면 protocol 잠금이 깨져서 디렉터리를 먼저 만들었다.
  - 일반 재사용에는 별도 항목이 필요하다. 변조 fixture 중 일부는 rr53_run 고유 분기까지만 검증한다. 평가 산출물 묶음의 완료 봉인(seal)은 없다.
- **추후 개선:**
  - `rr53_gate`의 tensor 입력은 D,E,F 전체 검사 파일을 쓴다.
  - E가 실행되지 않아 F용 `decide_e`, `decide_f`, 정밀도 규칙은 합성 fixture로만 검증됐다. 실제 E 데이터에서는 미실행이다.

# Recommendation to GPT

- 이 oracle 방식의 교정 진단은 계획대로 execution_failed(내용 오류)로 종료하고 보류하는 것을 권고한다. E/F는 사전 gate 위반이라 소급해 실행하지 않았다.
- 같은 한 칸(진짜=(present, absent), draft=(absent, present))에서만 오류가 났다. 후속은 "정답이 draft와 완전히 반대일 때 지시 복사 실패" 한 가지만 구분하는 최소 진단이 결정에 도움이 되는지 검토할 만하다.
  - 단순 반복이나 prompt 탐색은 정보 가치가 낮다.
  - 이 칸에서 정답 기준과 draft 기준 중 모델이 어느 쪽을 따르는지는 이번 raw 출력으로 재분석할 수 있다. 새 GPU 실행 없이 가능하다.
- 대안으로는 교정 방향을 보류하고 grounding·공동 처리 비용 쪽 투자 판단으로 돌아가는 선택도 있다.

SELF_CHECK: FAIL
SUMMARY: CheXpert 교정 진단의 자료·실행·검증 기반을 완성하고 D 448요청을 완료했으나 oracle 183/192(draft와 정답이 반대인 칸의 내용 오류 9건)로 사전 gate가 실패해 E/F를 실행하지 않았다. 모델 비교 결과는 없다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'EOF'
p='rr53_eval.py'
s=open(p).read()
a=s.index('    main_rows = [r for r in rows if not r["cond"].startswith(("O_", "OT_"))]')
b=s.index("    h = hashlib.sha256()")
body=s[a:b]
func='def make_report(stage, manifest, rows, recs):\n    """manifest·요청 행·verify를 통과한 record -> report(수치 부분)."""\n'+body.replace("a.stage","stage")+"    return rep\n\n\n"
func=func.replace("    main_rows","    main_rows",1)
mi=s.index("def main():")
s=s[:mi]+func+s[mi:]
# now replace body in main
a2=s.index('    main_rows = [r for r in rows if not r["cond"].startswith(("O_", "OT_"))]', s.index("def main():"))
b2=s.index("    h = hashlib.sha256()", a2)
s=s[:a2]+"    rep = make_report(a.stage, manifest, rows, recs)\n"+s[b2:]
open(p,'w').write(s)
EOF
python -c "import rr53_eval" && sed -n '/^def make_report/,/^def main/p' rr53_eval.py
- Bash: python - <<'EOF'
import os
os.environ["HF_HOME"]="/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache";os.environ["HF_HUB_OFFLINE"]="1"
import transformers,json
from rsna_diag import generate as G
proc=transformers.AutoProcessor.from_pretrained(G.MODEL_ID,revision=G.MODEL_REVISION)
print(getattr(proc,'image_token',None),getattr(proc,'boi_token',None),getattr(proc,'full_image_sequence',None) and len(proc.full_image_sequence))
r=[json.loads(l) for l in open('results/iter_053/requests/requests_D.jsonl')][0]
print(r['modality'],r['cond'])
img,_,_=G.load_image(r['image'])
prod=G.build_inputs(proc,img,r['prompt'])
msgs=[{"role":"user","content":[{"type":"image"},{"type":"text","text":r["prompt"]}]}]
txt=proc.apply_chat_template(msgs,add_generation_prompt=True,tokenize=False)
print(repr(txt[:200]))
man=proc(text=txt,images=[img],return_tensors="pt")
import torch
print(prod['input_ids'].shape,man['input_ids'].shape,torch.equal(prod['input_ids'],man['input_ids']))
print(proc.tokenizer.convert_tokens_to_ids('<image_soft_token>'))
ids=prod['input_ids'][0]
print((ids==proc.tokenizer.convert_tokens_to_ids('<image_soft_token>')).sum())
d=proc.apply_chat_template([{"role":"user","content":[{"type":"text","text":"hi"}]}],add_generation_prompt=True,tokenize=False)
print(repr(d)); 
print(proc.tokenizer.convert_ids_to_tokens(prod['input_ids'][0][:6]))
print(proc.tokenizer.convert_ids_to_tokens(man['input_ids'][0][:6]))
EOF
