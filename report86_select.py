"""iter_086 E 표본 후보 열거(CPU). 모델 출력을 읽지 않고 metadata만 사용한다.

규칙(원 계획 유지): PadChest-GR validation split에서 보호 환자(iter_039 H192/F120 manifest 환자)를 제외하고,
환자당 대표 영상 = sha256('84017|PatientID|ImageID') 최소, 층 = 대표 영상에 abnormal==True 문장이 있는가.
층별 hash 순서로 E96은 앞 48, E192x는 다음 48. '평가 가능한 현재 비정상 소견' 적격성은 report86_facts.py가 정한다.
python report86_select.py enumerate   # results/iter_086/E/enumeration.json 작성
"""
import collections
import hashlib
import json
import sys

from report86_common import ROOT, R86, R85, save, sha
import pg39_data as D

PROTECTED = ['results/iter_039/data/manifest_private.jsonl', 'results/iter_040/data/manifest_eval_private.jsonl']


def hh(p, i):
    return hashlib.sha256(f'84017|{p}|{i}'.encode()).hexdigest()


def protected_patients():
    s = set()
    for p in PROTECTED:
        for ln in open(ROOT / p):
            s.add(json.loads(ln)['PatientID'])
    return s


def enumerate_candidates():
    reports, m, links = D.load_inputs()
    prot = protected_patients()
    cands = [r for r in reports if links['img2split'][r['ImageID']] == 'validation' and links['img2patient'][r['ImageID']] not in prot]
    by = collections.defaultdict(list)
    for r in cands:
        by[links['img2patient'][r['ImageID']]].append(r)
    reps = {k: min(v, key=lambda r: hh(k, r['ImageID'])) for k, v in by.items()}
    out = []
    for pid, r in reps.items():
        out.append({'PatientID': pid, 'ImageID': r['ImageID'], 'StudyID': r['StudyID'], 'hash': hh(pid, r['ImageID']),
                    'has_abnormal_flag': any(f.get('abnormal') is True for f in r['findings']),
                    'n_images_patient_pool': len(by[pid]), 'PreviousImageID': r.get('PreviousImageID'), 'findings': r['findings']})
    out.sort(key=lambda c: c['hash'])
    return out, {'protected_patients': len(prot), 'candidate_images': len(cands), 'candidate_patients': len(by),
                 'inputs_sha256': links['inputs_sha256']}


def main():
    cmd = sys.argv[1]
    assert cmd == 'enumerate'
    out, info = enumerate_candidates()
    ab = [c for c in out if c['has_abnormal_flag']]
    no = [c for c in out if not c['has_abnormal_flag']]
    old = json.loads((R85 / 'selection_candidates_private.json').read_text())
    oa = [o['ImageID'] for o in old if o['stratum'] == 'abnormal']
    on = [o['ImageID'] for o in old if o['stratum'] == 'no_abnormal']
    info.update({'n_abnormal_flag': len(ab), 'n_no_abnormal_flag': len(no),
                 'reproduces_iter085_first96_abnormal_order': [c['ImageID'] for c in ab[:96]] == oa,
                 'reproduces_iter085_first96_noabn_order': [c['ImageID'] for c in no[:96]] == on})
    save(R86 / 'E/enumeration.json', {'info': info, 'ordered_candidates': out})
    print(json.dumps(info, indent=1))


if __name__ == '__main__':
    main()
