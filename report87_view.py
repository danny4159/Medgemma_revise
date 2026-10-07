"""iter_087 판정용 눈가림 view(읽기 전용). python report87_view.py <start> <end>   (환자 index 범위, end 제외)
C-H는 영역 묶음에 L<k> 번호를 붙여 보여 준다(@L<k>로 주장에 연결). bbox 좌표 표기와 퇴행 반복은 view에서만 접는다(원문은 readings.jsonl)."""
import re
import sys

from report86_view import blind_order, clean, load
from report87_eval import ch_groups, load_amend


def main(a, b):
    rows, reads, _ = load('E96')
    amend = load_amend()
    for pi in range(a, b):
        img = rows[pi]['ImageID']
        print(f"==== P{pi:03d} {img[:8]} {rows[pi]['stratum']} ====")
        for f in amend[img]['facts']:
            if f['v2_class'] == 'generic_normal':
                print(f"  ({f['fact_id']} generic_normal: {f['sentence_en']})")
                continue
            extra = ''
            if f['loc_req'] or f['attr_req']:
                extra = f" [loc_req={f['loc_req']}; attr_req={f['attr_req']}]"
            if f['targets']:
                extra += f" [targets={f['targets']}{' weak' if f['weak'] else ''}]"
            print(f"  {f['fact_id']} [{f['v1_class']}{'->' + f['v2_class'] if f['v2_class'] != f['v1_class'] else ''}] {f['sentence_en']}{extra}")
        for i, c in enumerate(blind_order(img), 1):
            r = reads[(img, c)]
            print(f'--- O{i} ---')
            if c == 'C-H':
                groups, gidx, srcs = ch_groups(r)
                for k, g in enumerate(groups, 1):
                    t = clean(r['segments'][g[0]]['text'])
                    t = re.sub(r'^Location of the [^:]*:\s*\.?\s*', '', t)
                    t = re.sub(r'^Description:\s*', '', t).replace('Description:', '').strip()
                    print(f"L{k} [{', '.join(srcs[i] for i in g)}] {t}")
                print('G ' + clean(r['segments'][gidx]['text']))
            else:
                print(clean(r['text']))


if __name__ == '__main__':
    main(int(sys.argv[1]), int(sys.argv[2]))
