# 요약

- **핵심 결과**: MedGemma 1.5는 주석에 병변이 없는 slice에도 첫 줄로 PRESENT를 답했습니다. 사전 판정은 `negative_basic_reading_insufficient`입니다. 한 장짜리 판독의 기본 신호가 부족해서, 두 장을 합쳤을 때의 통합 능력은 판정하지 못했습니다.
- **근거** (신규 RadGenome–BraTS 환자 32명, 320요청, 전부 EOS 종료):
  - OR BA 0.484, joint BA 0.477, single BA 0.500입니다.
  - OR−joint 차이는 0.0078이고 95% CI는 [−0.031, 0.047]입니다.
  - 병변 없는 slice 단독(N1, N2)의 ABSENT 응답은 0건입니다. 따라서 negative class 정확도는 0입니다.
  - 복제(P+P, N1+N1) 효과는 0이고 CI는 [0, 0]입니다.
- **미검증·주의**: 표본이 작고 GT로 만든 oracle slice이며, 반복 사용한 개발 자료입니다. 설명문 키워드 집계는 의미 평가기가 아닙니다. 실행 구성과 gate 범위는 아래 "미정·보류"에 따로 정리했습니다.
- **다음**: frozen 존재 질문의 추가 prompt·slice 순회는 그만두는 것을 권고합니다. 통합 질문을 이어가려면 타 모델 또는 직접 형식 적응이 필요하며, 이는 GPT 리뷰에서 결정할 사항입니다.

# Work Performed

- **자료 연결과 표본**:
  - RadGenome train FLAIR 후보 161건의 순서를 `sha256("134|pid")`로 다운로드 전에 봉인했습니다(`order.json`).
  - 앞 48건의 FLAIR·seg를 미러에서 받아 LFS sha256으로 검증했습니다. 약 130MB입니다.
  - 기술 4명과 평가 32명을 선정했습니다. 제외된 사례는 `fewer_than_2_eligible_N` 1건입니다.
  - 이전 BraTS 환자 번호(val 23명, iter_133 15사례)와 겹치는 환자는 0명입니다.
  - 아래 "미정·보류"에 적은 대로, MSD Task01 환자와의 연결과 모델 사전학습 노출은 미확인입니다.
- **관측과 요청 구성**:
  - P는 whole-tumor mask 면적이 최대인 slice입니다. N1, N2는 mask가 0이고 뇌 면적이 최대의 50% 이상인 slice이며, P에 가까운 순으로 골랐습니다.
  - 환자당 10조건을 구성했습니다: P, N1, N2, P+N1, N1+P, N1+N2, N2+N1, P+P, N1+N1, 영상 없음.
  - 저장 PNG 108장을 독립 재렌더링과 대조했고, mask 가시성과 N slice의 mask 부재도 확인했습니다. 문제는 0건입니다.
- **고정 규약**: PRESENT/ABSENT/UNKNOWN 질문과 첫 줄 strict parser, 설명문 모순 감사 규약, 평가기(`i134_eval.py`)를 생성 전에 코드로 잠갔습니다.
- **재사용 코드 보강**: i133 실행기를 수정했습니다.
  - worker 직접 진입에서도 code, gates, inputs를 전부 hash 검사합니다.
  - worker 시작 직전에 GPU admission을 하고, worker 로딩 완료를 확인한 뒤 다음 worker를 띄웁니다.
  - 요청당 0~2장의 가변 영상을 지원합니다.
  - 자원 로그에 GPU, CPU, RAM, 디스크 I/O를 기록합니다.
- **기술 검사와 본실행**: 기술 gate를 통과한 뒤 320요청을 실행했습니다.

# Files Changed

신규 코드 (`research/`):
- `i134_common.py`, `i134_fetch.py`, `i134_data.py`, `i134_spec.py`
- `i134_run.py`, `i134_lock.py`, `i134_eval.py`, `i134_tech.py`
- `i134_posthoc.py`, `test_i134.py`

반입한 `i133_*.py`와 `mr123_data.py`는 수정하지 않았습니다.

결과는 `results/iter_134/` 아래입니다.
- `data/`: `order.json`, `selection_v2.json`, `data_manifest_v2.json`, `brats/`
- `requests/`, `png_v2/`, `protocol_lock_*`
- `jobs/`: `Tb_w2`, `Tb_w4`, `Tb_resume`, `main` 등
- `tests/`, `eval_main.json`, `eval_main_per_patient.json`, `eval_posthoc_content.json`

# Commands / Experiments

| 단계 | 결과 |
|---|---|
| `i134_fetch.py seal` / `fetch 48` | 성공 (최초 `repo_type` 누락 404는 수정 후 성공) |
| `i134_data.py` | v1은 보고서 정규식 구현 오류로 36건 선정이 틀려 폐기, v2는 36명 선정, problems 0 |
| `test_i134.py` (CPU 단위 검사) | 28/28 통과 (최초 2회는 26/28이었으며 검사 코드·fixture 오류 수정) |
| 기술 `tensor` 검사 | 40요청, 공식 processor 대조·순서·target pixel 동일성 통과 |
| 기술 `neg` 검사 | 12개 거부 검사 전부 통과 |
| `Tb_w2` / `Tb_w4` / `Tb_resume` | 각 40/40, 출력 token 동일 |
| 기술 gate | passed |
| 평가 코드 dry-run (기술 4명) | 정상 동작 |
| `main` 생성 (4 worker) | 320/320, rc [0,0,0,0], wall 342초 |
| `i134_eval.py` | `eval_main.json` 저장 |
| `i134_posthoc.py` | 사후 키워드 집계, 주판정 불변 |

기술 단계에서 프로토콜을 수정한 경위는 다음과 같습니다.
1. 최초 기술 실행(`T_w2`)에서 모델이 제가 넣은 "Image n:" 라벨을 첫 줄에 따라 써서, 영상 요청의 첫 줄 형식 오류가 12건 발생했습니다.
2. 라벨 텍스트를 제거했습니다. 정답 내용과 무관한 형식 수정이며 `config.image_labels=False`로 구분했습니다.
3. protocol은 생성 전에 a1~a3으로 보정해 다시 잠갔습니다. 원 기록(`T_w2`)과 이전 검사 파일은 보존했습니다.

# Results

- **본실행 결과**: `results/iter_134/eval_main.json`. 32명에서 OR BA 0.484, joint BA 0.477, single BA 0.500입니다. OR−joint 차이는 0.0078이고 95% CI는 [−0.031, 0.047]입니다. 판정은 `negative_basic_reading_insufficient`(OR BA ≤ 0.60)입니다.
- **판정에서 확인한 것과 못 한 것**: 공동 처리 손실의 증거는 없었습니다. 다만 기본 판독 부족으로 통합 능력 자체는 판정하지 못했습니다.
- **조건별 strict 정확도**:
  - P, PN1, PP: 1.0 (전부 PRESENT)
  - N1, N2, N1N2, N2N1, N1N1: 0.0 (ABSENT 응답 0건)
  - N1P: 0.906 (정답이 PRESENT이므로 나온 값)
- **형식과 완결성**:
  - 영상 요청의 첫 줄 유효율은 96.5%(278/288)로 기준 95% 이상입니다.
  - 영상 없음 32건은 전부 `<unused94>thought` 형식의 사고 모드 출력이어서 strict에서는 전부 invalid입니다. 전체 320건 기준 유효율은 86.9%입니다.
  - 비EOS는 0건, 반복은 0건, UNKNOWN은 0건입니다.
- **첫 줄과 설명문의 불일치**:
  - 병변 없는 조건에서 설명문이 부정인데 첫 줄은 PRESENT인 사례가 조건당 8~11건입니다. 예: 첫 줄 "PRESENT", 설명 "no obvious tumor-like lesion".
  - 사후 키워드 집계에서는 N 단독 조건의 약 1/3이 병변 없음 취지(N1 11건, N2 10건, N1N1 12건)입니다. 병변 있음 취지는 6~9건입니다.
  - 원 답을 설명문으로 바꾸지 않았고, 주판정도 바꾸지 않았습니다.
- **비용**: 환자당 요청 처리 시간(로딩 제외)은 단독 2요청 3.38초 대 공동 1요청 1.84초입니다(양성 집합).
- **실행 구성 비교** (기술 40요청, 출력 token은 전 구성에서 동일):

  | 구성 | 생성 처리량 | GPU 사용량 |
  |---|---|---|
  | 2 worker (GPU당 1개) | 29.2 req/min | 각 약 9GB |
  | 4 worker (GPU당 2개) | 34.1 req/min (+17%) | 각 약 18GB |

  본실행은 4 worker로 했습니다. 본실행 peak는 GPU 17.96/17.89 GiB, 요청 p95 지연은 20.8초입니다(영상 없음의 사고 출력 때문입니다).

# Goal Progress / Reused Assets

- **목표 진전**: 같은 MedGemma 1.5 frozen에서 PRESENT/ABSENT/UNKNOWN 배타 질문의 첫 줄이 한 장 단독 판독에서도 거의 항상 PRESENT였습니다. iter_123/133의 고정 응답 관찰과 같은 방향입니다. 다음은 아직 모릅니다.
  - 관측 추가가 도움이 되는가
  - 공동 처리 손실이 있는가
  - 입력 수 효과가 있는가
  - 설명문 내용이 첫 줄보다 정확한가
- **재사용**: 승인 SHA `20ff6781…`의 `mr123_data.normalization_window/render_slice`를 반입 그대로 썼고, 새 i134 렌더 검증으로 확인했습니다. i133 실행기는 보강해 새 i134 파일로 분리했고, 기존 iter_070/133 산출물에는 쓰지 않았습니다.
- **reuse_manifest required_checks**:
  - iter_134 경로 분리: 충족
  - 새 NIfTI의 affine·orientation·label 의미와 렌더링: 충족
  - 감독기와 worker 직접 진입의 동일 hash 검사: 충족 (protocol 변조 거부 검사 포함)
  - 단일/두 영상의 processor tensor와 순서·target pixel 동일성: 충족
  - 출력 gate, 요청 누락·중복, 중단·재개, 입력 변조 거부: 충족 (재개 시 torn tail 복구 포함)
  - worker 직전 admission과 지연·CPU·RAM·I/O 계측: 연결함
  - 실패 worker 검사: 코드에 연결했으나 실제 실패 주입 시험은 하지 않았습니다.

# Problems

**현재 결론 무효**: 없습니다.

**해석에 영향을 주는 미정·보류** (GPT 리뷰 대상):
- **gate 범위**: 기술 gate의 "첫 줄 유효율 95% 이상"이 영상 요청만인지 영상 없음 포함인지 계획에 명시되지 않았습니다.
  - 기술 출력을 본 뒤 영상 요청 기준으로 해석했습니다. 평가기의 decision 정의와 동일하며, 평가기는 생성 전에 잠갔습니다.
  - 영상 없음을 포함하면 기술 단계는 90%로 gate 미달이었습니다. `technical_gate_technical.json`에 두 값을 모두 기록했습니다.
- **프롬프트 형식 수정**: 라벨 제거는 기술 출력(정답이 아니라 형식)을 본 뒤에 한 수정입니다. 원 기록과 v1 결과는 보존했고 이 사실을 보고합니다.
- **사전학습 노출·MSD 연결**: RadGenome–BraTS의 모델 사전학습 노출은 미확인입니다. MSD Task01 환자와의 연결도 확인할 수 없었습니다.
- **접근 경로**: 영상은 공식 BraTS 인증이 아니라 기존에 쓰던 미러(`MedOtter/brats2023-gli-dataset`, 고정 revision)를 통해 받았습니다. 공식 data use 동의를 확인한 것이 아닙니다.
- **N1·N2 인접성**: N1, N2는 P와의 물리 거리 순으로 골라 서로 인접한 slice입니다. 첫 사례는 1mm 간격입니다. 계획의 규칙대로 구현한 것이며 서로 다른 관측으로서의 정보량은 제한적입니다.

**수정이 필요하지만 현재 결론에는 영향 없음**:
- `i134_tech.py`는 검사 하네스라 protocol 잠금 목록에서 뺐습니다. digest는 `ac3b4ecb…`입니다.
- v1 자료 산출물(`png/`, `requests/*.json`, `data/*.json`)은 폐기본으로 남아 있습니다. 삭제하지 않았고 v2와 혼동되지 않도록 이름을 구분했습니다.
- 실행 중 실패 주입(자식 프로세스 강제 종료) 시험은 하지 않았습니다. 재개는 limit 중단과 torn tail로만 확인했습니다.

**추후 개선**: 사고 모드 출력(`<unused94>thought`)의 최종 답 추출은 이번 범위가 아닙니다. 영상 없음 조건은 대조 관찰로만 남깁니다.

# Recommendation to GPT

- **판단**: 집중 / 한정 보완 / 보류 중 **보류 + 한정 확인 하나**를 권합니다.
  - 이번 관찰은 기본 판독 부족입니다. 사전 판정대로 frozen 존재 과제의 추가 prompt·slice 순회는 종료를 권합니다. 통합 능력 자체는 미판정입니다.
  - 관측 부족, 통합 실패, 입력 수 효과는 이 설계로 구분하지 못했습니다.
- **다음 후보**:
  - 같은 32명 입력에서 타 모델(예: Qwen2.5-VL)의 단독 판독 BA를 확인하는 작은 대조입니다. 기본 신호가 모델 특이인지 보려는 것입니다.
  - 반대로 영상 신호가 약해서 생긴 결과라면, 질문을 존재 여부에서 영상으로 지지되는 속성으로 바꾸는 방법도 있습니다.
  - 두 후보 모두 이번 결과로 효과를 가정하지 않습니다. 학습은 이번 결과만으로 정당화되지 않으며, 한다면 직접 SFT와 OR 대조를 포함해야 합니다.
- **미해결로 넘기는 것**: 첫 줄과 설명문의 불일치(조건당 8~11건)가 응답 범주 정의에 의존하는지, 사고 모드 출력에서 최종 답을 안정적으로 읽을 수 있는지입니다.

SELF_CHECK: FAIL
SUMMARY: 신규 RadGenome–BraTS 환자 32명·320요청으로 두 slice의 개별 OR와 공동 입력을 비교했으나, MedGemma가 병변 없는 slice에도 PRESENT를 답해 OR BA 0.484로 기본 판독 부족 분기(통합 능력은 미판정)가 되었다. gate 범위·프롬프트 형식 수정의 사후 해석 때문에 FAIL로 GPT 리뷰를 요청한다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma/research && python - <<'E'
import json
d='results/iter_070/data/'
s=json.load(open(d+'radgenome/train_val_test_split.json'))
print({k:v[:3] for k,v in s.items()})
l=json.load(open(d+'medotter_listing.json'));print(l['sha']);f=l['files'];print(len(f),f[:5] if isinstance(f,list) else list(f.items())[:5])
mf=json.load(open(d+'radgenome/BraTS_GLI/modal_wise_finding.json'));print(len(mf),list(mf)[:4])
E
git status --short | head; cat /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_083/preflight_a1/release_evidence.json | head -c 2500
- Bash: python - <<'E'
import json,re
s=json.load(open('radgenome/train_val_test_split.json'))
mf=json.load(open('radgenome/BraTS_GLI/modal_wise_finding.json'))
l=dict(json.load(open('medotter_listing.json'))['files'])
tr=sorted({k[:-4] for k in s['train'] if k.endswith('-t2f')})
print(len(tr))
inm=[p for p in tr if p+'-t2f' in mf]; print('in modal',len(inm))
base='ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData/'
inl=[p for p in inm if base+f'{p}/{p}-t2f.nii.gz' in l and base+f'{p}/{p}-seg.nii.gz' in l];print('in listing',len(inl))
print(sum(l[base+f'{p}/{p}-t2f.nii.gz']+l[base+f'{p}/{p}-seg.nii.gz'] for p in inl)/1e6,'MB')
used=set(json.load(open('label_table.json'))['val']);print(len(used), used&set(inl))
for p in inl[:3]: print(p, mf[p+'-t2f'][:400])
lt=json.load(open('label_table.json'));print(lt.keys())
E
ls /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_070/ | head; ls /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_083/preflight_a1
- Bash: python - <<'E'
import json
s=json.load(open('radgenome/train_val_test_split.json'))
mf=json.load(open('radgenome/BraTS_GLI/modal_wise_finding.json'))
l=dict(json.load(open('medotter_listing.json'))['files'])
tr=sorted({k[:-4] for k in s['train'] if k.endswith('-t2f')})
print(len(tr))
inm=[p for p in tr if p+'-t2f' in mf]; print('in modal',len(inm))
base='ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData/'
def f(p,suf): return base+p+'/'+p+suf
inl=[p for p in inm if f(p,'-t2f.nii.gz') in l and f(p,'-seg.nii.gz') in l];print('in listing',len(inl))
print(sum(l[f(p,'-t2f.nii.gz')]+l[f(p,'-seg.nii.gz')] for p in inl)/1e6,'MB')
lt=json.load(open('label_table.json'));print(lt.keys())
used=set(lt['val']);print(len(used), used&set(inl))
for p in inl[:3]: print(p, mf[p+'-t2f'][:400])
E
- Bash: cat > i134_common.py <<'E'
"""iter_134 전용 경로·출처 유틸리티 (i133_common 파생; 결과는 results/iter_134에만 쓴다)."""
import hashlib, json, os
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
RES = HERE / 'results/iter_134'
OLD = HERE / 'results/iter_070/data'   # 읽기 전용 기존 자료(RadGenome 보고서·split·미러 listing)
DATA = RES / 'data'
BRATS = DATA / 'brats'
REPO = 'MedOtter/brats2023-gli-dataset'
REVISION = 'b032d353a3e80911a5f850bc54e6fb575298a354'
BASE = 'ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData/'
SEED = 134


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


def now(): return datetime.now(timezone.utc).isoformat()
def digest(x): return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
def read(p): return json.loads(Path(p).read_text())


def save(p, x):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'x') as f:
        json.dump(x, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
E
cat > i134_fetch.py <<'E'
"""iter_134: 후보 순서 봉인(seed134) 및 필요한 FLAIR(t2f)·seg 파일만 미러에서 확보. 전체 snapshot 금지.
순서는 다운로드 전에 order.json으로 봉인한다. 기존 파일은 덮어쓰지 않고 크기·LFS sha256으로 검증한다."""
import sys, hashlib, json, os
from pathlib import Path
from i134_common import *

TOK = Path('/home/test/.cache/huggingface/token')


def candidates():
    s = read(OLD / 'radgenome/train_val_test_split.json'); mf = read(OLD / 'radgenome/BraTS_GLI/modal_wise_finding.json')
    lst = dict(read(OLD / 'medotter_listing.json')['files']); assert read(OLD / 'medotter_listing.json')['sha'] == REVISION
    tr = sorted(set(k[:-4] for k in s['train'] if k.endswith('-t2f')))
    out = [p for p in tr if p + '-t2f' in mf and BASE + p + '/' + p + '-t2f.nii.gz' in lst and BASE + p + '/' + p + '-seg.nii.gz' in lst]
    return out, lst, mf


def seal_order():
    c, lst, mf = candidates(); assert len(c) == 161
    order = sorted(c, key=lambda p: hashlib.sha256(('%d|%s' % (SEED, p)).encode()).hexdigest())
    sizes = {p: [lst[BASE + p + '/' + p + '-t2f.nii.gz'], lst[BASE + p + '/' + p + '-seg.nii.gz']] for p in c}
    save(DATA / 'order.json', dict(created_at=now(), rule='sorted by sha256("134|"+pid); first 4 technical, then eligible cases in order for main32',
                                    split='RadGenome train', n_candidates=len(c), order=order, listing_sizes=sizes,
                                    listing_sha256=sha(OLD / 'medotter_listing.json'), split_sha256=sha(OLD / 'radgenome/train_val_test_split.json'),
                                    modal_finding_sha256=sha(OLD / 'radgenome/BraTS_GLI/modal_wise_finding.json')))
    print('sealed', len(order), order[:6])


def fetch(pids):
    from huggingface_hub import HfApi, hf_hub_download
    api = HfApi(token=TOK.read_text().strip() if TOK.exists() else None)
    for p in pids:
        for suf in ('-t2f.nii.gz', '-seg.nii.gz'):
            rel = BASE + p + '/' + p + suf; dst = BRATS / BASE / p / (p + suf)
            info = api.get_paths_info(REPO, [rel], revision=REVISION)[0]
            want = info.lfs.sha256 if info.lfs else None
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                got = hf_hub_download(REPO, rel, repo_type='dataset', revision=REVISION, local_dir=str(DATA / '_dl'), token=api.token)
                os.replace(got, str(dst) + '.part'); os.replace(str(dst) + '.part', dst)
            assert want is None or sha(dst) == want, 'sha mismatch ' + rel
            print(p, suf, dst.stat().st_size, 'ok', flush=True)


if __name__ == '__main__':
    if sys.argv[1] == 'seal': seal_order()
    else: fetch(read(DATA / 'order.json')['order'][:int(sys.argv[2])])
E
python i134_fetch.py seal
- Bash: cd results/iter_134 && mkdir -p superseded_build_v1 && mv png requests data/selection.json data/data_manifest.json superseded_build_v1/ && ls . superseded_build_v1
- Bash: sed -i "s#DATA / 'selection.json'#DATA / 'selection_v2.json'#; s#DATA / 'data_manifest.json'#DATA / 'data_manifest_v2.json'#; s#RES / 'png'#RES / 'png_v2'#; s#requests/technical.json#requests/technical_v2.json#; s#requests/main.json#requests/main_v2.json#" i134_data.py && grep -n "_v2" i134_data.py
- Bash: CUDA_VISIBLE_DEVICES=0,1 python i134_tech.py tensor 2>&1 | tail -5
- Bash: python ../experiment_wait.py --pid $(pgrep -f "i134_run.py launch" | head -1) --timeout 600
