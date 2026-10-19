"""실제 보존 MRI·원시 응답·평가 JSON으로 단일 요약 figure를 생성한다.

실행: /home/milab/anaconda3/bin/python plot_mri_multislice_observations.py
그림용 기존 환경을 사용하며 연구 환경·모델·실험 결과는 수정하지 않는다.
"""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch
import nibabel as nib
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
RES = ROOT / 'research/results'
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
font_manager.fontManager.addfont(FONT)
plt.rcParams.update({'font.family': font_manager.FontProperties(fname=FONT).get_name(),
                     'axes.unicode_minus': False, 'pdf.fonttype': 42})
NAVY, MUTED, TEAL, RED = '#172E46', '#536779', '#167E87', '#C34248'
BG, BORDER = '#F2F5F8', '#D8E2EB'

def read(p):
    return json.loads(p.read_text())

manifest = read(RES / 'iter_136/data/manifest.json')
case = next(c for c in manifest['cases']['E'] if c['case'] == 'BRATS_334')
mask_path = RES / 'iter_056/data/raw/BRATS_334_lbl.nii.gz'
assert hashlib.sha256(mask_path.read_bytes()).hexdigest() == case['lbl_sha256']
mask = np.asarray(nib.as_closest_canonical(nib.load(mask_path)).dataobj)
rows = [json.loads(line) for p in sorted((RES / 'iter_136/jobs/main').glob('worker*.jsonl'))
        for line in p.read_text().splitlines() if line.strip()]
assert len(rows) == len({r['id'] for r in rows}) == 450
example = next(r for r in rows if r['id'] == 'BRATS_334__N1')
assert example['final_text'].strip() == (
    'PRESENT\nThe image shows a normal brain structure with no visible tumor-like lesion.')
assert sum(r['final_text'].strip().splitlines()[0] == 'PRESENT'
           for r in rows if r['kind'] != 'none') == 403
r136 = read(RES / 'iter_136/eval/report.json')
old = {name: read(RES / f'iter_064/E/report_{name}.json')['primary_invalid_as_wrong']
       for name in ('medgemma', 'qwen')}

fig = plt.figure(figsize=(20, 13), facecolor=BG)

def txt(x, y, s, size=14, color=NAVY, weight='normal', **kwargs):
    return fig.text(x, y, s, fontsize=size, color=color, weight=weight,
                    va='top', **kwargs)

def box(x, y, w, h, color='white', edge=BORDER):
    fig.add_artist(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.008,rounding_size=0.012',
                                transform=fig.transFigure, facecolor=color,
                                edgecolor=edge, linewidth=1, zorder=0))

txt(.035, .969, 'MRI 여러 슬라이스 입력: 무엇이 관찰됐고, 무엇은 아직 모르는가?', 26, weight='bold')
txt(.035, .921, '실제 보존 실험 요약  |  MedGemma 1.5 4B · 추가 학습 없음  |  iter_064 + iter_136', 14, MUTED)
box(.035, .487, .447, .39)
box(.516, .487, .447, .39)
box(.035, .115, .447, .344)
box(.516, .115, .447, .344)

# A: 연구자가 GT로 선택한 실제 입력. GT contour는 설명용이며 모델 입력 아님.
txt(.049, .859, 'A  데이터와 실제 입력 예시', 19, weight='bold')
txt(.049, .824, 'MSD Task01 BrainTumour · 3D 뇌종양 MRI의 FLAIR 채널', 13)
txt(.049, .798, '종양·부종 계열 segmentation으로 슬라이스를 선택 · BRATS_334', 12, MUTED)
for x, role, title in [(0.049, 'P', '병변 주석 있음'), (.193, 'N1', '병변 주석 없음'), (.337, 'N2', '병변 주석 없음')]:
    info = case['images'][role]
    p = Path(info['path'])
    assert hashlib.sha256(p.read_bytes()).hexdigest() == info['sha256']
    a = fig.add_axes([x, .604, .129, .172])
    a.imshow(np.asarray(Image.open(p)), interpolation='nearest')
    z = case['z'][role]
    plane = mask[::-1, :, z].T[::-1] > 0
    assert int(plane.sum()) == case['area'][role]
    if plane.any():
        a.contour(plane.astype(float), levels=[.5], colors=['#FFBE45'], linewidths=1.35)
    a.axis('off')
    txt(x+.0645, .596, f'{role} · z={z} (0-based)\n{title}', 12, ha='center')
txt(.049, .548, '노란선 = 정답 병변 영역(설명용). 모델에는 원본 MRI만 입력.', 11.5, MUTED)
txt(.049, .523, '“주석 없음” ≠ 정상 환자. 전체 판독문 정확도를 평가한 실험은 아님.', 11.5, RED)

# B: 최신 실험의 비교 구조와 정량 결과.
txt(.531, .859, 'B  최근 비교: “제공된 영상 중 병변이 있는가?”', 18, weight='bold')
txt(.531, .820, 'iter_136 · 반복 개발 45사례 · 1장 또는 2장 입력', 13, MUTED)
txt(.943, .790, '균형 정확도 (BA)', 11, MUTED, ha='right')
labels = [('한 장씩', 'P / N1 / N2를 각각 질문', .5),
          ('개별 결과 합침', '같은 두 장을 따로 판단 → 하나라도 있으면 양성', r136['or_BA']),
          ('두 장 공동 입력', 'P+N1 또는 N1+N2 → 한 번에 판단', r136['joint_BA'])]
for y, (name, detail, val) in zip([.757, .685, .613], labels):
    txt(.533, y, name, 15, weight='bold')
    txt(.533, y-.030, detail, 11.5, MUTED)
    txt(.943, y, f'{100*val:.1f}%', 24, TEAL, 'bold', ha='right')
txt(.531, .554, '두 장의 순서 교환·같은 장 복제·무영상 대조도 포함', 11.5, MUTED)
txt(.531, .526, '관찰: 영상 405요청 중 403건이 “PRESENT”; 2건 형식 오류', 13, RED, 'bold')

# C: 이전 과제는 지정한 slice만 판단. 최신 점수와 직접 비교하지 않는다.
txt(.049, .440, 'C  과거 관찰: 다른 장이 추가되자 판단이 악화', 18, weight='bold')
txt(.049, .405, 'iter_064 · 48사례 · “지정한 한 장에 병변이 있는가?”', 12.5, MUTED)
ax = fig.add_axes([.082, .212, .370, .164], facecolor='white')
x = np.arange(3)
for dx, model, color, label in [(-.17, 'medgemma', TEAL, 'MedGemma 1.5'),
                              (.17, 'qwen', '#A6B5C4', 'Qwen2.5-VL-7B')]:
    vals = [100*old[model]['groups'][k]['BA'] for k in ('S', 'R', 'C')]
    bars = ax.bar(x+dx, vals, width=.31, color=color, label=label, zorder=3)
    for b, v in zip(bars, vals):
        ax.text(b.get_x()+b.get_width()/2, v+1.6, f'{v:.1f}', ha='center', fontsize=11, color=NAVY)
ax.set_ylim(0, 102)
ax.set_yticks([0, 50, 100])
ax.set_ylabel('균형 정확도 (%)', fontsize=11, color=MUTED)
ax.set_xticks(x, ['한 장', '같은 장 × 2', '다른 장 추가'])
ax.tick_params(axis='both', labelsize=11, length=0)
ax.grid(axis='y', color='#E6EDF2', zorder=0)
for spine in ax.spines.values():
    spine.set_visible(False)
ax.legend(loc='upper center', bbox_to_anchor=(.5, 1.16), ncol=2, frameon=False, fontsize=10)
txt(.049, .171, 'MedGemma: 복제 대비 −27.1%p · Qwen은 같은 하락 없음', 13, TEAL, 'bold')
txt(.049, .143, '지정 장의 판단 문제이며, 여러 장의 전체 판독 이득을 검증한 것은 아님.', 11.5, MUTED)

# D: 동 일 데이터 예시의 실제 원문. 임상적 해석을 추가하지 않는다.
txt(.531, .440, 'D  최근 핵심 이상: 첫 답과 설명이 서로 모순', 18, weight='bold')
txt(.531, .405, 'iter_136 · 위 예시의 N1 한 장 · 실제 출력 그대로', 12.5, MUTED)
box(.533, .324, .414, .045, '#FFF0EF', '#F0CCCB')
txt(.544, .360, '첫 답   PRESENT', 18, RED, 'bold')
txt(.933, .352, '“병변 있음”', 14, RED, ha='right')
box(.533, .222, .414, .080, '#EFF6F8', '#CDDFE5')
txt(.544, .290, '설명   “The image shows a normal brain structure\n            with no visible tumor-like lesion.”', 14)
txt(.544, .241, '번역: 정상 뇌 구조이며 눈에 보이는 종양 같은 병변은 없다.', 11.5, MUTED)
txt(.531, .191, '이 때문에 “첫 답이 틀림 = 영상을 전혀 인식 못함”은 성립하지 않음.', 12, RED)
txt(.531, .162, '설명 자체의 정확성·원인은 미확정. 450요청은 모두 EOS로 완결.', 11.5, MUTED)
txt(.531, .138, '예시는 모순을 보여주기 위해 선택했으며 빈도 추정용 표본이 아님.', 10.5, MUTED)

txt(.035, .083, '해석 범위  |  2장 비교의 제한된 관찰. “3D가 더 낫다/나쁘다” 또는 “MRI 판독 불가능”을 입증하지 않음.', 14, NAVY, 'bold')
txt(.035, .052, 'BA(균형 정확도) = 양성·음성 정답률의 평균. B와 C는 질문·평가 조건이 달라 직접 성능 비교 불가. '
    'GT 선택은 원인 분석용이며 실제 자동 slice 선택과 다름.', 10.5, MUTED)
txt(.035, .030, '출처: agent/runs/iter_064/review.md · iter_136/review.md | research/results/iter_064/E · iter_136/data, jobs/main, eval '
    '| MSD: CC-BY-SA 4.0 | 2026-10-13', 9, MUTED)

for ext in ('png', 'pdf'):
    out = ROOT / f'mri_multislice_observations.{ext}'
    fig.savefig(out, dpi=180, facecolor=BG)
    print(out)
plt.close(fig)
