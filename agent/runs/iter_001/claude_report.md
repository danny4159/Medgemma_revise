# Work Performed
`legacy/eval_results/scores.json`을 읽어 21개 조합을 한 표로 정리하는 스크립트 `research/summarize_scores.py`를 작성하고 실행했습니다. 표 뒤에는 최저 성능 과제 하나와 그 이유를 docs 근거로 붙였습니다. 최저 성능 과제는 DeepLesion CT의 bbox 추정입니다. 수치는 JSON에서 읽으며, 누락·null 값은 `N/A`로 표시합니다. 재채점, 추론, GPU 사용은 없습니다.

# Files Changed
- 추가: `research/summarize_scores.py`
- 추가: `research/results/scores_summary.md`
- 수정: `research/README.md` (실행 방법과 점수의 평가 조건 추가)
- 삭제하지 못한 임시 파일: `research/_peek.py`. JSON 구조를 확인하려고 만든 파일이며, `rm`이 권한 거부되어 남아 있습니다. orchestrator가 삭제해야 합니다.

# Commands / Experiments
- `python research/summarize_scores.py --output research/results/scores_summary.md`: 성공, 종료 코드 0. 도구 출력에는 종료 코드가 따로 표시되지 않아, 출력이 끝까지 나왔다는 점으로 확인했습니다.
- `python research/_peek.py`: 성공. JSON 구조 확인용입니다.
- `rm research/_peek.py`: 권한 거부되어 우회하지 않았습니다.
- 처음 시도한 heredoc 형태의 `python` 호출과 `awk` 파이프도 권한 거부되어 다른 방법으로 대체했습니다.

# Results
결과 파일은 `research/results/scores_summary.md`입니다. 표는 G1 3행, G2 6행, G3 12행으로 총 21행이며 누락·중복이 없습니다. 출력값은 계획의 대조값과 모두 일치합니다.

| 항목 | 출력값 |
|---|---|
| SLAKE token F1 | 0.6108 |
| CheXpert binary | accuracy 0.7692, n_scored 130/140 |
| NIH binary | n_scored 132/140 |
| DeepLesion bbox | mean_iou 0.0061, n_parsed 10/10, iou@0.3 0.0000, iou@0.5 0.0000, 전체영상 기준선 0.0041 |
| BraTS bbox | 0.1084 |
| VinDr bbox | 0.1276 |

- **최저 성능 과제: DeepLesion bbox.** 같은 bbox metric을 쓰는 3개 데이터셋 중 mean IoU가 가장 낮고 기준선에 가깝습니다. 서로 다른 metric을 섞은 전역 순위는 계산하지 않았습니다.
- **이유(docs 근거).**
  - 전체정리 문서 맨 앞의 중대 정정(14–43행)에 따르면 이 초기 평가는 비공식 xyxy 0–1 형식을 썼고, '좌표 출력 능력이 없다'는 결론은 철회됐습니다.
  - 1.5 평가정리 8장과 12장은 비공식 형식에서 영상과 무관한 템플릿 출력으로 퇴화했다고 기록합니다.
  - 같은 문서는 공식 형식에서도 학습 범주 밖의 CT 병변은 IoU 약 0.007로 낮았다고 적고, 8bit PNG로는 CT 공식 전처리를 못 쓴다는 입력 제약도 적습니다.
- **한계.** 0.007은 별도 재평가(n=20)이며 저장된 0.0061(n=10)을 대체하지 않습니다. 원인별 기여도는 검증되지 않았습니다.

# Problems
- `_peek.py`를 삭제하지 못했습니다.
- DeepLesion name 행에 붙인 '부위명 정답과 진단명 질문 불일치' 주석은 계획의 조사 노트를 그대로 따른 것입니다. 해당 문서 구절은 직접 찾아 확인하지 못했습니다.
- 12장 한계 3 등 일부 줄 번호 인용은 제가 읽은 범위 기준입니다. 13장은 직접 읽지 않았고, 소표본 한계는 n=10이라는 JSON 값에 근거해 적었습니다.

# Recommendation to GPT
- 이번 요약은 완료로 볼 수 있습니다. 다만 DeepLesion name 주석의 docs 근거를 확인하고 `_peek.py`를 삭제해 주세요.
- 이후 실험을 한다면 공식 형식으로 DeepLesion 원본 HU 데이터를 쓰는 재평가가 의미 있습니다. n=10이므로 결론 강도는 제한적입니다.

SELF_CHECK: FAIL
SUMMARY: 21행 과제별 표와 최저 과제(DeepLesion bbox, mean IoU 0.0061) 요약을 생성했으나, docs 주석 근거 미확인과 임시 파일 `_peek.py` 삭제 실패가 남았다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: cd /SSD1_1TB/home/milab/daniel/08_medgemma; python - <<'E'
import json
d=json.load(open('legacy/eval_results/scores.json'))
def strip(o):
    if isinstance(o,dict): return {k:strip(v) for k,v in o.items() if k not in('examples','details')}
    return o
print(json.dumps(strip(d['G3']),ensure_ascii=False)); print(list(d), list(d['G2']['nih_chestxray14']))
print(json.dumps(strip(d['G2']['nih_chestxray14']['B_binary'])))
E
head -20 legacy/docs/MEDGEMMA_평가_전체정리.txt; grep -n "^ *[0-9]*\. \|^=\|^## " legacy/docs/MEDGEMMA_1.5_평가정리.txt | head -60; cat research/README.md
- Bash: python /SSD1_1TB/home/milab/daniel/08_medgemma/research/_peek.py; rm /SSD1_1TB/home/milab/daniel/08_medgemma/research/_peek.py; sed -n 20,45p /SSD1_1TB/home/milab/daniel/08_medgemma/legacy/docs/MEDGEMMA_평가_전체정리.txt; sed -n 389,438p /SSD1_1TB/home/milab/daniel/08_medgemma/legacy/docs/MEDGEMMA_1.5_평가정리.txt
- Bash: grep -n "CT\|단일 슬라이스\|소표본\|n=10" /SSD1_1TB/home/milab/daniel/08_medgemma/legacy/docs/MEDGEMMA_1.5_평가정리.txt | awk -F: '$1>=715 && $1<=852' | head -20
- Bash: rm /SSD1_1TB/home/milab/daniel/08_medgemma/research/_peek.py
- Bash: python /SSD1_1TB/home/milab/daniel/08_medgemma/research/summarize_scores.py --output /SSD1_1TB/home/milab/daniel/08_medgemma/research/results/scores_summary.md; echo EXIT $?
