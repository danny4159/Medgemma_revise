"""iter_087 규약 잠금: 전체 E96 판정 전에 규약·reference 보완·평가기 코드·fixture 결과 hash를 새 파일에 기록한다.
python report87_lock.py   (이미 있으면 덮어쓰지 않고 실패; 이후 변경은 amendment 파일로 남긴다)"""
from report86_common import ROOT, save, sha

R87 = ROOT / 'results/iter_087'


def main():
    files = ['results/iter_087/semantic_protocol_v2.md', 'results/iter_087/reference_amend_E96.json', 'results/iter_087/source_manifest.json',
             'report87_refamend.py', 'report87_eval.py', 'report87_view.py', 'report87_check.py', 'test_report87_eval.py',
             'results/iter_087/tests/fixtures_report87_run2.json']
    save(R87 / 'protocol_lock.json', {'purpose': '전체 E96 의미 판정(judgments_parts) 시작 전 잠금. 이후 변경은 amendment 파일로 이력을 남긴다.',
                                      'files': {f: sha(ROOT / f) for f in files}})
    print('locked', len(files))


if __name__ == '__main__':
    main()
