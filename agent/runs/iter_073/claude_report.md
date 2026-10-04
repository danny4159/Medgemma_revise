# 요약

- **핵심 결과:** 3DReasonKnee의 공개 train/val annotation만으로 연골 size grade 점검을 끝냈다. 모델 호출, 학습, GPU 사용은 0이다.
- **근거:** 환자 split은 서로 겹치지 않는다. 배포 size 정답은 원 MOAKS 점수와 약 95% 일치한다. 결측 일부는 0으로 채워져 있다. train-only prior는 val 정확도 0.72~0.73이다.
- **미검증·주의:** 영상이 없어 원 임상 정답과의 일치, 좌표 정합, 관측 충분성은 미확인이다. 이번 결과는 준비이며 모델 한계 관찰이나 method gate 통과가 아니다.
- **다음:** 사용자가 OAI 자료를 주면 `handoff_design.md`의 순서대로 진행한다. 그 전에는 같은 점검을 반복하지 않는다.

# Work Performed

- 기준 revision `7a611f92fd3ad3954e8b62feef49ee12bfef725a`에서 필요한 파일만 내려받았다. 질문 mapping, split CSV, MOAKS 원 label CSV, `train.json`, `val.json`이다. 총 약 849MB, SHA256과 URL은 `source_manifest.json`에 있다.
- 공식 test 답변(`test.json`, `test_balanced.json`)은 받지도 읽지도 않았다. `test_split.csv`는 ID 열만 있음을 확인하고 환자 교집합 검사에만 썼다. 영상과 mask archive도 받지 않았다.
- 연골 14개 질문의 size와 depth를 환자, 시점, 좌우, 영상에 연결했다. 결측과 실제 0, 범위 밖 코드를 구분해 보존했다. 원 MOAKS 중복 행은 첫 행을 고르지 않고 후보를 모두 남겼다.
- train-only global majority와 subregion majority(동률은 낮은 grade)를 val에 적용했다.
- 사용자 지시대로 영상이 없으면 확인할 수 없는 항목은 미확인으로 남겼다.

# Files Changed

- 새 코드: `rk73_fetch.py`, `rk73_audit.py`, `test_rk73.py`. 기존 파일 수정은 없다.
- `results/iter_073/`: `source_manifest.json`, `annotation_audit.json`, `cartilage_long_train.csv`, `cartilage_long_val.csv`, `tests/fixtures.json`, `handoff_design.md`, `raw/`(내려받은 원자료).
- `claude_report.md`는 만들지 않았고 이 최종 응답이 보고를 대신한다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `python rk73_fetch.py`: 성공, 20개 파일 다운로드. 처음 heredoc으로 쓰려던 시도는 권한 검사에 막혀 Write 도구로 바꿨다.
- `python rk73_audit.py`: 성공, 약 16~19초. 첫 실행은 FNIH BICL06 파일이 없어 실패했다. 해당 파일은 원래 없는 것이어서 존재하는 파일만 읽도록 고쳤다. 원 MOAKS 중복 처리도 "첫 행 선택"에서 "후보 전체 보존"으로 고쳐 다시 돌렸다.
- `python test_rk73.py`: **33/33 통과.**
  - fixture는 null 대 0, 잘못된 grade, 중복·충돌 join, test 답변 거부, 환자 누수 감지, 동률 규칙, 빈 class의 recall 미정의 처리를 검사한다.
  - raw JSON/CSV를 audit 코드와 별도 구현으로 다시 집계해 subregion별 count, prior 정확도, 환자 교집합을 대조했다.
  - fixture는 코드 검증이며 환자 성능이 아니다.

# Results (수치와 결과 파일 경로)

모두 `results/iter_073/annotation_audit.json` 기준이다.

- **split:** train 5,903 영상(2,000명), val 837(267명), test 1,280(399명, ID만). 환자와 영상 교집합은 모두 0이다.
- **JSON 구조:** 영상당 질문 62개, 연골 14개이며 중복과 prompt-subregion 불일치는 0이다. train 영상 2개(9792220/24M, 9993362/48M)는 JSON에 없어 제외 후보로 기록했다.
- **결측 치환:** 배포 size는 train/val 모두 100% 정수 0–3이다. 원 MOAKS size가 결측인 31(train)/4(val) 행은 배포에서 0(30/4) 또는 2(1)로 채워졌다. 원 depth의 범위 밖 코드 '5'(train 14행 중 10행)도 0이나 3으로 바뀌어 있다.
- **원 MOAKS 중복:** 8,046 key 중 2,909개가 여러 행이고 1,160개는 연골 값이 충돌한다. 판독 VERSION이 달라서다.
- **배포 size와 원 MOAKS 일치:** 단일 후보 행 기준 train 95.2%(76,878/80,755), val 94.7%(10,837/11,446)다.
  - 불일치는 00M/12M/24M에 몰려 있고 48M은 98.9~99.8% 일치한다.
  - 무릎 단위로 몰려 있다. val 837 영상 중 136개에 불일치가 있다.
  - 판독 VERSION별로 다르다(train 단일 행 key 기준 SQ:65는 7.6%, SQ:61은 0.7%).
  - 원인은 공개 파일만으로 결정되지 않는다.
- **size 분포 (grade 0/1/2/3):** train 59,994/4,399/16,244/1,977, val 8,476/651/2,381/210. grade 1과 3은 희소하고 subregion별 편차가 크다(예: tibia_lateral_anterior에는 grade 1이 0개).
- **같은 무릎 내 grade 차이:** train 5,901 영상 중 5,412개(92%)는 14개 subregion 사이에 서로 다른 grade가 있다. subregion을 지정한 질문이 의미를 가지는 label 구조다. 모델의 선택 실패나 결합 필요성의 증거는 아니다.
- **train-only prior를 val에 적용 (11,718행 풀링):**

| 규칙 | accuracy | MAE | 정의된 class 평균 recall |
|---|---|---|---|
| global majority(전부 0) | 0.7233 | 0.516 | 0.25 |
| subregion majority | 0.7339 | 0.490 | 0.286 |

  환자 단위 평균 accuracy는 각각 0.7305, 0.7371이다. 모델이 이 값과 비슷하면 영상 판독 증거로 보지 않는다.
- **시점과 MOAKS 파일 대응:** 00M→BICL00, 12M→01, 24M→03, 48M→06 대응은 각 방문에서 대각 일치율이 가장 높다(0.938/0.958/0.944/0.990). 다만 교차 일치율도 0.86~0.93이라 변별력은 약하다.
- 자료 인수 기준, 선행과 구별할 질문, 최초 실행 순서는 `results/iter_073/handoff_design.md`에 정리했다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

- **목표 진전:** 공개 annotation은 부위별 size grade 비교를 지탱한다. 같은 무릎 안에서 subregion마다 grade가 다르다. 동시에 두 가지 데이터 결함이 확인됐다. 원 MOAKS 결측이 정답 0으로 치환됐고, 원 label과의 불일치 구조가 해소되지 않았다. 이 때문에 배포 label을 그대로 쓰기 전에 사례 단위 확인이 필요하다.
- **미검증:** 원 임상 정답과의 일치, 영상-box 좌표와 방향 정합, 관측 충분성, 모델·segmentation 학습 노출, 공식 test 답변(열지 않음)이다.
- **재사용:** `reuse_assets=[]`였고 코드 반입은 없다. 3DReasonKnee 공식 README 설명과 신규 점검 결과는 일치한다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없음.
- **재사용 전 수정 필요:** 원 MOAKS 불일치(방문 및 VERSION 구조)와 결측 치환 행의 처리 규칙을 영상 도착 후 사례 확인으로 확정해야 한다. 규칙은 영상을 보기 전에 정한다.
- **추후 개선:** 시점-파일 대응은 변별력이 약하다. 코드는 이 자료 전용 점검 스크립트이며 범용 로더가 아니다. 학습·생성 코드(iter_071 계열)의 알려진 needs_fix는 건드리지 않았다. 학습 경로가 확정될 때 수정한다.

# Recommendation to GPT

- 준비 결과를 한 번 보고했고, 후속 작업은 영상 도착 후 `handoff_design.md`의 (라) 순서 1~3부터 시작한다.
- 자료 도착 전에는 같은 annotation 점검, 새 데이터셋 탐색, 모델 실행을 반복하지 않는다.
- 배포 label과 원 MOAKS의 불일치가 사례 확인에서도 풀리지 않으면 정답을 원 MOAKS 규칙으로 재구성하거나 해당 부위·방문만 쓴다. 이 경우 학습은 보류한다.

SELF_CHECK: PASS
SUMMARY: 공개 train/val annotation 점검 완료(환자 교집합 0, 원 MOAKS 결측의 0 치환 확인, 배포 size와 원 MOAKS 일치 약 95%, train-only prior val 정확도 0.72~0.73). 모델·GPU 사용 0이며 영상 정합과 임상 정답 일치는 미검증이다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: mkdir -p /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_073 && cat > /SSD1_1TB/home/milab/daniel/08_medgemma/research/rk73_fetch.py <<'EOF'
"""iter_073: 3DReasonKnee 공개 annotation 파일 고정 revision 다운로드 + manifest. test 답변(generate_data/test*.json)은 받지 않는다."""
import hashlib, json, os, sys, time
from huggingface_hub import HfApi, hf_hub_download

REPO = 'rajpurkarlab/3DReasonKnee'
REV = '7a611f92fd3ad3954e8b62feef49ee12bfef725a'
OUT = 'results/iter_073/raw'
FILES = [
    'README.md',
    'data/question_files/questions.json', 'data/question_files/cot_question_mapping.json',
    'data/question_files/grade_dict.json', 'data/question_files/labels.json',
    'data/question_files/question_subregion_mapping.json',
    'data/split_files/all_studies.csv', 'data/split_files/train_split.csv',
    'data/split_files/val_split.csv', 'data/split_files/test_split.csv',
    'data/labels/manual_annotated_kMRI_18M.csv',
    'data/labels/taxonomymatch_kMRI_FNIH_SQ_MOAKS_BICL00.csv',
    'data/labels/taxonomymatch_kMRI_FNIH_SQ_MOAKS_BICL01.csv',
    'data/labels/taxonomymatch_kMRI_FNIH_SQ_MOAKS_BICL03.csv',
    'data/labels/taxonomymatch_kMRI_SQ_MOAKS_BICL00.csv',
    'data/labels/taxonomymatch_kMRI_SQ_MOAKS_BICL01.csv',
    'data/labels/taxonomymatch_kMRI_SQ_MOAKS_BICL03.csv',
    'data/labels/taxonomymatch_kMRI_SQ_MOAKS_BICL06.csv',
    'data/generate_data/val.json', 'data/generate_data/train.json',
]
FORBIDDEN = ('generate_data/test',)

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 24), b''):
            h.update(b)
    return h.hexdigest()

def main():
    assert not any(any(x in f for x in FORBIDDEN) for f in FILES)
    api = HfApi()
    sizes = {t.path: t.size for p in sorted({os.path.dirname(f) for f in FILES})
             for t in api.list_repo_tree(REPO, path_in_repo=p, repo_type='dataset', revision=REV)
             if hasattr(t, 'size')}
    man = {'repo': REPO, 'revision': REV, 'files': {}}
    t0 = time.time()
    for f in FILES:
        dst = os.path.join(OUT, f)
        if not (os.path.exists(dst) and os.path.getsize(dst) == sizes[f]):
            hf_hub_download(REPO, f, repo_type='dataset', revision=REV, local_dir=OUT)
        assert os.path.getsize(dst) == sizes[f], f
        man['files'][f] = {'bytes': sizes[f], 'sha256': sha(dst),
                           'url': f'https://huggingface.co/datasets/{REPO}/resolve/{REV}/{f}'}
        print(f, sizes[f], flush=True)
    man['wall_s'] = round(time.time() - t0, 1)
    man['total_bytes'] = sum(v['bytes'] for v in man['files'].values())
    man['not_downloaded'] = ['data/generate_data/test.json', 'data/generate_data/test_balanced.json', 'images/masks/OAI/segmentations archives']
    json.dump(man, open('results/iter_073/source_manifest.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
EOF
cd /SSD1_1TB/home/milab/daniel/08_medgemma/research && python rk73_fetch.py 2>&1 | tail -30
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_073/raw/data && python -c "
import pandas as pd,glob,collections
for f in sorted(glob.glob('labels/*.csv')):
    d=pd.read_csv(f,dtype=str,keep_default_na=False)
    pre=collections.Counter(c[:3] for c in d.columns if c.startswith('V'))
    print(f.split('/')[-1],d.shape,dict(pre),'SIDE',dict(d['SIDE'].value_counts()) if 'SIDE' in d else None)
    if 'V00MCMPM' in d: print('  vals PM',dict(d['V00MCMPM'].value_counts()),'.1',dict(d['V00MCMPM.1'].value_counts()))
    for p in pre:
        c=p+'MCMPM'
        if c in d: print('  ',c,dict(d[c].value_counts()),dict(d[c+'.1'].value_counts()))
print(pd.read_csv('labels/taxonomymatch_kMRI_SQ_MOAKS_BICL00.csv',dtype=str,keep_default_na=False).iloc[:3,:6])
"
for f in splits; do :; done; python -c "
import pandas as pd
b='/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_073/raw/data/split_files/'
for s in ['train','val','test']:
    d=pd.read_csv(b+s+'_split.csv',dtype=str); print(s,d.shape,d.patient_id.nunique(),d.time.value_counts().to_dict(),d.knee_side.value_counts().to_dict())
a=pd.read_csv(b+'all_studies.csv',dtype=str);print(a.shape,list(a.columns));print(a.head(2).T)
"
- Bash: python -c "
import pandas as pd, rk73_audit as A, collections
df=pd.read_csv('results/iter_073/cartilage_long_train.csv',dtype={'patient_id':str,'knee_side':str})
tab,_=A.moaks_lookup(A.load_moaks())
u=df[(df.orig_size_status=='unique')&(~df.size_in_cands)]
print(len(u), u.groupby('time').size().to_dict())
res=collections.defaultdict(lambda:collections.Counter())
for r in u.itertuples():
    for tag in A.TIME_FILE.values():
        rows=tab.get((tag,r.patient_id,r.knee_side))
        if rows is None: res[r.time][tag+'_norow']+=1; continue
        st,c,*_=A.orig_candidates(rows,r.subregion,0)
        if c and r.size in c: res[r.time][tag+'_match']+=1
for t in res: print(t,dict(res[t]))
# disagreement concentrated by patient/knee?
k=u.groupby(['patient_id','knee_side','time']).size()
print('knee-visits with disagreements',len(k),'of',df.groupby(['patient_id','knee_side','time']).ngroups, 'rows/knee-visit hist',k.value_counts().sort_index().head(15).to_dict())
print('VERSION of unique disagreeing orig row', collections.Counter(tab[(A.TIME_FILE[r.time],r.patient_id,r.knee_side)][0][:2] for r in u.itertuples()).most_common(8))
allv=collections.Counter((tab[(A.TIME_FILE[r.time],r.patient_id,r.knee_side)][0][0],tab[(A.TIME_FILE[r.time],r.patient_id,r.knee_side)][0][1]) for r in df[df.orig_size_status=='unique'].drop_duplicates(['img']).itertuples())
dv=collections.Counter((tab[(A.TIME_FILE[r.time],r.patient_id,r.knee_side)][0][0],tab[(A.TIME_FILE[r.time],r.patient_id,r.knee_side)][0][1]) for r in u.drop_duplicates(['img']).itertuples())
print({k:(dv.get(k,0),v) for k,v in allv.most_common(10)})
"
