"""iter_079 LUMIERE 자료 gate: expert CSV의 새 병변 정답·비교 검사 연결의 literal 검사 (CPU).

계획 gate: (2) 명시적 양성/음성, (4) 원 행/공식 설명으로 기준 검사 특정, (6) 불가 시 자료 부적합 종료.
"""
import csv, re, json, collections, sys, os

ROOT = 'results/iter_079/data'
CSV = f'{ROOT}/raw/LUMIERE-ExpertRating-v202211.csv'
COMP = f'{ROOT}/raw/LUMIERE-datacompleteness.csv'


def main():
    R = list(csv.reader(open(CSV, encoding='utf-8')))[1:]
    byp = collections.defaultdict(list)
    for r in R:
        byp[r[0]].append(r)
    new_re = re.compile(r'\bnew\b', re.I)
    neg_re = re.compile(r'\b(no|without|absence of)\b[^,.;]*\b(new|lesion|enhanc)', re.I)
    pos = [r for r in R if new_re.search(r[5])]
    neg_explicit = [r for r in R if neg_re.search(r[5])]
    consec, first = [], []
    for p, rs in byp.items():
        for i, r in enumerate(rs):
            if new_re.search(r[5]):
                if i > 0 and new_re.search(rs[i - 1][5]):
                    consec.append([p, rs[i - 1][1], r[1], r[5]])
                else:
                    first.append([p, r[1], r[4], r[5]])
    dates = collections.Counter((r[0], r[1]) for r in R)
    dup = [k for k, v in dates.items() if v > 1]
    # 평가 가능한 SD/PR/CR 중 rationale이 비어 있거나 None인 행(= 새 병변 부재의 명시적 문구 없음)
    quiet = [r for r in R if r[4] in ('SD', 'PR', 'CR') and not new_re.search(r[5])]
    quiet_text = collections.Counter(r[5] for r in quiet)
    c = list(csv.reader(open(COMP)))
    out = {
        'n_rows': len(R), 'n_patients': len(byp),
        'rows_with_new_text': len(pos),
        'new_text_by_rating': dict(collections.Counter(r[4] for r in pos)),
        'rows_explicit_no_new_or_no_lesion_phrase': len(neg_explicit),
        'explicit_phrase_examples': neg_explicit[:5],
        'sd_pr_cr_rows_without_new_text': len(quiet),
        'sd_pr_cr_rationale_texts_top': quiet_text.most_common(8),
        'new_rows_whose_previous_rated_row_also_says_new': len(consec),
        'consecutive_examples': consec[:5],
        'new_rows_first_mention': len(first),
        'patients_with_first_new_mention': len({f[0] for f in first}),
        'duplicate_patient_date_rows': len(dup),
        'readme_specifies_reference_scan': False,
        'csv_has_reference_scan_column': False,
        'csv_columns': list(csv.reader(open(CSV, encoding='utf-8')))[0][:4] + ['Rating', 'Rating rationale'],
        'completeness_header': c[0],
    }
    json.dump(out, open(f'{ROOT}/gate_audit.json', 'w'), indent=1, ensure_ascii=False)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
