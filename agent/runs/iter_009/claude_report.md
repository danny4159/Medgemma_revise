# 요약

- **핵심 결과:** RSNA 독립 환자 양성 200명에서 공식 긴 prompt와 간결 prompt가 모두 명백한 위치 불일치를 낸 환자는 134명, 67.0%였다(Wilson 95% CI 60.2–73.1%). 사전 기준(하한 >20%, 두 prompt 유효 출력률 ≥95%)을 충족해 이 조건에서는 사전 가설이 지지된다. 위치 불일치는 모든 예측–GT IoU가 0.3 미만인 경우다.
- **근거:** 공식 사용법 sanity가 통과했다. 형식 실패는 낮고(간결 prompt 잘림 7/200), x/y 교환·좌우/상하 반전으로도 개선되지 않아 사용법·좌표 오류로는 설명되지 않는다. F1@0.3은 공식 0.147, 간결 0.066이다. 영상 무관 단일 box prior(0.269)보다 낮고, 다른 환자 예측을 옮긴 swap과는 유의한 차이가 없다.
- **주의:** RSNA(NIH 유래) 폐렴 의심 opacity 한 과제와 MedGemma 1.5 한 revision에 한정된 결과이며 내부 원인은 모른다. `validated` 승격은 GPT review 판단이고, 방법 개발과 다중 데이터셋 증명은 아직이다.
- **다음:** 오류 양상(크기 과대, 종격동·중앙 편향, 좌우 일치율)을 근거로 training-free 재질의·증거 선택과 직접 병변 경량 적응을 같은 지표로 비교한다. anatomy 전이는 오류와의 연결 근거가 있을 때만 재검토한다.

# Work Performed

1. **공식 자료 확보.** RSNA 공식 S3에서 adjudicated ZIP(3.98GB), annotation JSON, mapping JSON을 전부 받아 sha256·ETag를 기록했다. 다운로드 예산 상한은 없다. Range cache 결함을 피하려고 전체 파일을 받았다.
2. **annotation/UID/patient 감사.**
   - labelGroup `Calculated`(Normal 9,790, NoOpacity/NotNormal 12,788, Lung Opacity 7,106장·bbox 11,390개)를 최종 라벨로 확인했다.
   - 316장(라벨 없음)과 106장(Exclude)은 제외했고, 주석 누락은 음성으로 취급하지 않았다.
   - DICOM 30,000개는 모두 1024², 8-bit MONOCHROME2, slope/VOI 없음이라 pixel array를 그대로 썼다.
   - ZIP basename 충돌 0, mapping 중복 0.
3. **결정적 split.** seed 20260924로 development 80명(40/20/20)과 독립 평가 300명(200/50/50)을 나눴다. 이전 NIH 환자 167명을 제외했고 환자 교집합 0, decoded pixel 중복 0이다.
4. **좌표 검사.** GT overlay 16장(양성 12, 음성 4)으로 x/y·canvas 연결을 눈으로 확인했다. 임상 재판독은 아니다.
5. **공식 사용법 sanity.**
   - 공식 notebook 원문과 예제 영상을 보존했다(commit `7d9e43f9`, MedGemma 1.5 release).
   - notebook의 `*255`는 uint8 L/RGB 입력에서 wrap(예: 100→156)이 된다. 예제는 RGBA라 원문 emulation과 값 보존 경로의 입력이 동일했다(max diff 0).
   - HF pipeline과 runner의 input_ids가 동일하고, pixel_values는 bf16 캐스팅 후 동일하며, 생성 텍스트가 4건 모두 일치했다.
6. **구현.** 새 모듈 `rsna_diag/`에 다운로드, DICOM 리더, 전처리·좌표 변환, 데이터 adapter, 생성 runner, parser, metric, 평가, 진단, 2-GPU orchestrator, protocol lock을 만들었다.
7. **fixture.** 58개를 실행했고 모두 통과했다.
8. **실제 생성.** pilot 36, development 240(pilot 36 이월), 독립 평가 900 요청. 모두 batch=1, bf16, greedy, cap 1000→2000→4000 규칙이다.
9. **평가.** 주지표, F1@0.3/0.5, union IoU, 음성 층, prior·swap baseline, paired bootstrap 10,000회, 사례 overlay, 탐색적 진단.

# Files Changed

- 새로 만든 코드:
  - `rsna_diag/` — `download.py`, `dicom_min.py`, `geometry.py`, `rsna_data.py`, `build_data.py`, `prompts.py`, `generate.py`, `run_shards.py`, `parse.py`, `metrics.py`, `evaluate.py`, `diagnostics.py`, `sanity.py`, `overlay.py`, `lock_protocol.py`, `__init__.py`
  - `test_rsna_iter009.py`
- 노트: `notes/iter_009_notes.md`
- 결과: `results/iter_009/` (하위 구조는 Results 참조)
- `grounding_data/*`와 이전 결과는 수정·삭제하지 않았다. git 명령으로 변경한 것은 없다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

| 명령 | 결과 |
|---|---|
| `python rsna_diag/download.py results/iter_009/source/raw` | 성공 |
| `python -m rsna_diag.build_data` | 성공, 380명, 교집합 0 |
| `python test_rsna_iter009.py` | 1차 실패: 테스트 코드 오류 2건(FakeZip 속성, emulation 인덱스). 수정 후 58/58 통과 |
| `python -m rsna_diag.generate ... --max-requests 2` | 성공(스모크) |
| `python -m rsna_diag.sanity` | 1차 실패: `import transformers`가 offline 설정보다 앞서 401. 순서 수정 후 성공 |
| 〃 재실행 | 통과, `pipe.preprocess` 입력 대조 추가 후 최종 결과 저장 |
| `run_shards` pilot (`pilot12_ids.json`) | 성공, 36/36, 331초 |
| `run_shards` development (`dev80_ids.json`) | 성공, 204 신규 + 36 이월 |
| `run_shards --queue` (dev 재개 검증) | 성공, 0건 재생성, 30초 |
| `python -m rsna_diag.lock_protocol` | 성공, 생성 후 `lock verified` |
| `run_shards --queue` (독립 평가, `eval300_ids.json`) | 성공, 900/900, wall 11,095초(3.08h) |
| `python -m rsna_diag.evaluate` (dev·eval) | 성공 |
| `python -m rsna_diag.diagnostics` (dev·eval) | 성공 |

**pip 실행은 권한이 거부됐다.** pydicom·skimage 없이 진행하려고 최소 DICOM 리더를 직접 구현했고, notebook 전처리는 numpy로 emulation했다. 우회는 하지 않았다.

**자원.**
- GPU 배정은 상속된 CUDA_VISIBLE_DEVICES=0,1 안에서 shard k→물리 GPU k로 했다(UUID는 resource log 기록).
- 프로세스당 peak 8.17–8.23 GB(torch), nvidia-smi 최대 9,039 MiB. OOM은 없었다.
- 요청당 시간: 공식 ~36–46초, 간결·legacy ~4–7초. 4000 cap까지 간 요청은 ~550–650초.
- 독립 평가 900요청 wall 3.08h, GPU당 프로세스 1개(계획대로).

**스케줄링 변경(출력 규약 불변).** dev는 정적 shard, 독립 평가는 환자 단위 claim 큐다. runaway 요청 때문에 GPU0이 유휴가 되어 바꿨다. 최종 코드는 lock 전에 고정했고, dev 재개 검증도 마쳤다. dev 초기 실행의 wall 기록은 큐 재개 검증이 `dev/run/last_run.json`을 덮어써 잃었다. `resource_log.jsonl`에는 t≈3,217초까지 남아 있다.

# Results (수치와 결과 파일 경로)

**Gate 통과**
- 사용법 gate: pipeline과 runner의 input_ids 동일, 생성 텍스트 일치.
- 데이터 gate: 전 영상 표준 DICOM 태그, 환자·픽셀 중복 0.
- 생성 gate: pilot 36/36 유효, 모든 출력이 EOS까지 완결(잘림은 4000 cap에서만 발생).

**주지표: 독립 양성 200명** (`eval/eval/metrics.json`)

| 지표 | 값 |
|---|---|
| 공통 위치 불일치 | 134/200 = 67.0%, Wilson 95% CI [60.2, 73.1] |
| 유효 출력률(양성 / 전체 300) | 공식 100% / 100%, 간결 96.5% / 97.7% |
| 사전 기준 | 하한 >20%, 유효 ≥95% 충족 → `supported` (이 RSNA 조건 한정) |

**prompt별 결과**

| | 공식 긴 prompt | 간결 prompt | legacy |
|---|---|---|---|
| 위치 불일치(양성 200 기준) | 163/200 (81.5%) | 155/200 (77.5%) | 172/200 (86.0%) |
| 잘림 (4000 cap) | 0 | 7 | 5 |
| 빈 목록(양성) | 0 | 13 | 0 |
| F1@0.3 | 0.147 | 0.066 | 0.071 |
| F1@0.5 | 0.008 | 0.000 | 0.009 |
| recall@0.3 | 0.128 | 0.078 | 0.075 |
| precision@0.3 | 0.185 | 0.061 | 0.078 |
| union IoU | 0.207 | 0.146 | 0.160 |

**baseline** (F1@0.3)

| baseline | F1@0.3 |
|---|---|
| prior(단일 box, dev 양성에서 선택) | 0.269 (F1@0.5 0.060) |
| swap: 공식 | 0.113 |
| swap: 간결 | 0.062 |
| swap: legacy | 0.074 |

**paired bootstrap** (양성 환자 단위, 차이 [95% CI])
- 공식 − 간결 +0.081 [0.040, 0.124]
- 공식 − legacy +0.076 [0.031, 0.124]
- 공식 − prior −0.123 [−0.185, −0.060]
- 간결 − prior −0.203 [−0.258, −0.150]
- 공식 − swap_공식 +0.033 [−0.010, 0.080], 간결 − swap_간결 +0.003 [−0.029, 0.035] (CI가 0을 포함)

**음성 층** (각 50명, 추가 box는 임상 오탐이 아니라 annotation 대비 불일치)

| | Normal 추가 box | NoOpacity/NotNormal 추가 box |
|---|---|---|
| 공식 | 100% | 100% |
| legacy | 100% | 100% |
| 간결 | 24% (빈 목록 76%) | 78% (빈 목록 22%) |

**생성 안정성.** 간결 prompt에서 등차수열처럼 box를 반복 생성하는 loop가 잘림 7건이다. 이 잘림 7건은 cap 4000에서도 종결되지 않았다. cap 연장 재실행에서 prefix 불일치는 0건이었다.

**오류 양상** (`eval/diagnostics.json`, 탐색적)
- 예측 union 면적이 GT의 약 2.5배(0.22 vs 0.089).
- 공식 prompt의 단일 box는 좌우 반쪽 일치가 86/110이다.
- 좌표 규약 대안 중 공식 prompt에서 개선되는 것은 없었다.
- 간결·legacy는 x/y를 바꿔 읽을 때 IoU≥0.3 비율이 더 높다(간결 24.4% vs 13.9%). 그래도 주지표의 민감도 분석에서 간결 prompt를 x/y 어느 순서로 읽어도 불일치인 환자는 116/200 = 58.0% [51.1, 64.6]이다(사후 탐색).
- 사례 overlay(`eval/eval/cases/`)에서는 GT가 한쪽 폐야인데 큰 box가 종격동·중앙을 덮는 패턴이 보인다.

**Development(개발 자료, 80명)** (`dev/eval/`): 공통 위치 불일치 30/40 = 75%, 공식 F1@0.3 0.092, 간결 0.050(간결 유효 출력률 0.925). dev prior는 같은 자료에서 골랐으므로 in-sample이다.

**결과 파일** (`results/iter_009/`)
- `source/`(raw, official, notebook_commit.json)
- `data_audit/`(`audit_summary.json`, `split_checks.json`)
- `manifests/`(infer/gt/id/exclusion)
- `overlays/dev_gt_coord_check.png`
- `sanity/`
- `pilot/`, `dev/`, `eval/`(run, eval, diagnostics.json)
- `tests/fixtures.json`
- `locked_protocol.json`
- `completion.json`

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

**목표 진전:** 사용법·좌표·잘림·parser 오류를 통제해도 RSNA opacity 위치 오류가 다수 환자에서 남는다는 관찰이 독립 표본으로 재현됐다. 다음이 확정됐다.
- 오류 빈도(공통 67%, 공식 prompt 단독 81.5%)
- 오류 크기(박스 과대, 종격동·중앙 쏠림)
- 단순 baseline과의 관계(prior에 미달, swap과 유의차 없음)
- prompt 의존 현상(간결 prompt에서만 음성 판별이 부분적으로 나타남, 잘림 loop)

**미검증:**
- 다른 병변·모달리티·데이터셋.
- 내부 원인(모델 표현 vs decoder vs 학습 분포).
- 이 오류에 대응하는 해결책의 효과.
- skimage 원문 그대로의 notebook 재현(numpy emulation).
- 전문가 GT 재판독.
- 사전학습 노출.
- legacy NIH 10장의 환자 중복.

**재사용:** `reuse_assets`는 비어 있다. `grounding_data/nih.py`·`net.py`는 전체 ZIP 다운로드 방식이라 사용하지 않았고, 대신 새 모듈을 만들었다. 따라서 재사용 검증 대상은 없다. iter_008 보관본은 건드리지 않았다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론을 무효화하는 문제:** 발견하지 못했다.
- **재사용 전 수정:** 없음. 다만 `rsna_diag/generate.py`의 `--carry`와 claim 큐는 이번 실행에서만 검증됐다.
- **해석 주의(결론 무효 아님)**
  - 음성 층은 공식·legacy prompt가 "Where is the X?" 형식이라 존재를 전제하고, 100% box를 낸다. 이를 "병변 부재 판별 실패"로 일반화하지 말고, prompt 형식 의존으로 해석해야 한다.
  - 다중 category 환자 배정으로 Normal/NLONN 풀이 편향돼 있다.
  - 간결·legacy의 x/y 교환 시 개선 신호는 탐색적이다. 축 순서 혼동이 부분적으로 있을 가능성은 배제하지 못했다.
- **추후 개선(선택)**
  - 좌우 불일치와 크기 과대의 정량 분해.
  - 간결 prompt의 loop 완화(repetition penalty 등)는 별도 실험으로 다룬다.
  - dev 초기 wall time 기록 손실은 resource_log로 대체했다.

# Recommendation to GPT

1. `lesion-grounding-generalization`을 "RSNA 폐렴 의심 opacity, MedGemma 1.5 revision `91850547…`, 공식 긴 prompt와 간결 prompt 두 조건"으로 좁혀 `validated`로 올리는 것을 검토해 달라. 근거는 독립 200명, 유효 출력률 ≥95%, 사용법 sanity 통과, 축·좌우 규약으로 해소되지 않음이다. 광범위한 일반화나 내부 원인 주장은 넣지 않기를 권한다.
2. 다음 iteration은 method 단계 진입이다. 같은 RSNA 분할·지표·baseline(prior/swap)에서 training-free(재질의, 다중 crop 증거 선택), 직접 병변 LoRA/adapter, 근거가 있을 때 anatomy 보조 신호를 비교하는 것이 좋다.
3. 대조 기준은 prior F1@0.3 0.269와 공식 prompt 0.147이다. 방법의 이득은 이 baseline과 paired bootstrap으로 보여야 한다. RSNA 밖 데이터셋 1개 이상의 독립 확인이 다음 병목이다.
4. RSNA 독립 평가 300명은 이제 개발 자료다. 이후 조건 조정에는 새 분할이 필요하다.

SELF_CHECK: PASS
SUMMARY: RSNA 독립 환자 양성 200명에서 두 정상 prompt 공통 위치 불일치가 67.0%(Wilson 95% CI 60.2–73.1%)로 사전 기준을 충족했고, 사용법·전처리·잘림·좌표 규약으로는 설명되지 않았다(단일 box prior와 swap 대비 이득은 없거나 미달). 이 특정 opacity 과제와 모델 revision에 한정되며 원인과 해결책 효과는 미검증이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python -c "
import json,collections
a=json.load(open('results/iter_009/source/raw/pneumonia-challenge-annotations-adjudicated-kaggle_2018.json'))
L={}
for g in a['labelGroups']:
    for l in g['labels']: L[l['id']]=(g['name'],l['name'].strip(),l['type'])
d=a['datasets'][0]
by=collections.defaultdict(list)
for x in d['annotations']: by[x['SOPInstanceUID']].append(x)
print('images with any ann',len(by))
cat=collections.Counter(); comb=collections.Counter()
for sop,xs in by.items():
    cs=sorted(set(L[x['labelId']][1] for x in xs if L[x['labelId']][0]=='Calculated'))
    comb[tuple(cs)]+=1
print(comb)
ex=[sop for sop,xs in by.items() if any(L[x['labelId']][1]=='Exclude' for x in xs)]
print('exclude imgs',len(ex), 'of which have calculated', sum(1 for s in ex if any(L[x['labelId']][0]=='Calculated' for x in by[s])))
# calc bbox geometry
bad=0;sizes=collections.Counter()
for x in d['annotations']:
    if L[x['labelId']][0]=='Calculated' and L[x['labelId']][2]=='local':
        dd=x['data'];sizes[(x['width'],x['height'])]+=1
        if dd['x']<0 or dd['y']<0 or dd['x']+dd['width']>x['width']+1e-3 or dd['y']+dd['height']>x['height']+1e-3 or dd['width']<=0 or dd['height']<=0: bad+=1
print('bad',bad,sizes.most_common(5))
print(collections.Counter(len([x for x in xs if L[x['labelId']][0]=='Calculated' and L[x['labelId']][2]=='local']) for xs in by.values()))
"
- Bash: pip download pydicom --no-deps -d /tmp/pd -q
- Bash: CUDA_VISIBLE_DEVICES=0 python -m rsna_diag.sanity 2>&1 | grep -v "Loading weights"
- Bash: ps -eo pid,stat,etime,cmd --sort=start_time
- Bash: python -c "
import json
from rsna_diag import parse as PA, metrics as M
from rsna_diag.evaluate import load_gen,gt_boxes
gt=json.load(open('results/iter_009/manifests/gt_manifest.json'))
recs=load_gen('results/iter_009/eval/run/gen_shard*.jsonl')
pos=sorted(i for i,g in gt.items() if g['split']=='independent_eval' and g['category']=='opacity')
def st(i,p): return PA.parse_response(recs[(i,p)]['suffix_text_raw'],recs[(i,p)]['ended_eos'])
def hard(pr,g,sw=False):
    if pr['status']!='valid_nonempty': return None
    bs=[[b[1],b[0],b[3],b[2]] for b in pr['boxes']] if sw else pr['boxes']
    return M.max_iou_all(bs,g)<0.3
k=n=0;k2=0;o_only=0
for i in pos:
    g=gt_boxes(gt[i]);o=st(i,'official_long');c=st(i,'concise')
    ho=hard(o,g);hc=hard(c,g);hcs=hard(c,g,True)
    if ho and hc and hcs: k+=1
    if ho and hc: k2+=1
print('common(as-is)',k2,'common(concise hard under both as-is and swapped)',k,'of',len(pos))
lo,hi=M.wilson(k,len(pos));print('wilson',lo,hi)
# among concise valid nonempty: fraction where swapped is not hard but as-is hard etc
a=b=c2=d=0
for i in pos:
    g=gt_boxes(gt[i]);cc=st(i,'concise')
    if cc['status']!='valid_nonempty': continue
    x=hard(cc,g);y=hard(cc,g,True)
    a+= (x and y); b+= (x and not y); c2+= ((not x) and y); d+= ((not x) and (not y))
print('concise: both hard',a,'asis hard only',b,'swap hard only',c2,'neither',d)
"
