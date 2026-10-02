# 요약

- **핵심 결과:** CT 대표 606개를 감사했으나 적격은 287개였습니다. D24 제외 후 **E263으로, E280 기준보다 17개 부족해 본평가를 실행하지 않았습니다.**
- **근거:** 전체 2,909장 출처·pixel 검증과 실제 이미지 반환 연결을 완료했습니다. D24는 296개 요청을 생성하고 독립 재계산했습니다.
- **미검증·주의:** 비EOS 20건과 최종 답변 invalid 35/120건이 남았습니다. 본 가설과 신규 contribution은 미검증입니다.
- **다음:** 자료 gate 실패와 D 기술 검증 한계를 GPT 리뷰에 전달합니다. 실행 프로세스는 모두 종료했습니다.

# Work Performed

CT 자료 확보, 중복 cluster 구성, 고정 대표 선택, 이력·영상 주석 감사를 수행했습니다. iter_051의 254개 sheet와 추가 원본 13개도 실제 반환 기록에 연결했습니다.

T/D/F/U/C/R/H/X 생성 경로를 구현했습니다. 초기 F 영상 index 불일치는 해당 실행을 보존하고 수정한 뒤 재실행했습니다. D8에서 잘림을 확인해 F/U cap을 한 번 두 배로 늘리고, 이에 맞춘 H cap으로 D24 전체를 실행했습니다.

# Files Changed

새 Python 파일 21개를 추가했습니다.

- 자료·감사: `mt52_prepare.py`, `mt52_cluster.py`, `mt52_audit.py`, `mt52_audit_finish.py`, `mt52_data_verify.py`, `mt52_provenance.py`, `mt52_freeze_d.py`
- 실행·검증: `mt52_spec.py`, `mt52_sanity.py`, `mt52_run.py`, `mt52_verify.py`
- 집계·종료: `mt52_d_report.py`, `mt52_d_verify.py`, `mt52_usage.py`, `mt52_finish.py`
- 테스트: `test_mt52_{data,final,inputs,protocol,resume,run}.py`

기존 tracked 소스는 수정하지 않았습니다. 결과는 `results/iter_052/`에 보존했으며 Git 변경 작업은 하지 않았습니다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

| 명령·검사 | 결과 |
|---|---|
| `python mt52_audit_finish.py` | 최종 606개 이미지 반환 연결 완료, 자료 gate 실패 |
| `python mt52_data_verify.py` | 607개 사례·2,909장 검증 PASS |
| `python test_mt52_inputs.py` | D24 전체 tensor·순서 검사 96건 PASS |
| `python test_mt52_final.py` | 실패 분기 검사 15건 PASS |
| `python test_mt52_protocol.py` | source 변조·동시 쓰기·비용 중복 검사 PASS |
| `python mt52_run.py --job results/iter_052/pilot/D24_caps2 --inference results/iter_052/data/D_inference.json --workers 2 --peak-gib 14 --double-caps F,U` | 중단 후 재개하여 296건 완료 |
| `test_mt52_resume.main()` | 실제 중단 후 1→2 worker 재개, 8건 token 일치 |
| `python mt52_d_report.py`, `python mt52_d_verify.py` | 점수·5개 paired CI·비용 독립 재계산 PASS |
| `python mt52_usage.py`, `python mt52_finish.py` | 비용 장부 및 실패 종료 근거 봉인 |

외부 SIGTERM으로 중단된 실행은 동일 설정으로 재개했습니다. 발신 원인은 미확인이며 OOM 기록은 없었습니다.

# Results (수치와 결과 파일 경로)

[자료 gate](results/iter_052/audit/data_gate.json): 적격 **287개·1,300장**, D24·128장, 남은 E263·1,172장입니다.

[D24 탐색 결과](results/iter_052/eval/D24_report.json):

| 조건 | 정답/24 | Accuracy |
|---|---:|---:|
| T | 8 | 33.33% |
| D | 6 | 25.00% |
| C | 4 | 16.67% |
| R | 3 | 12.50% |
| X | 7 | 29.17% |

D−C는 +8.33 pp, 탐색용 98.75% CI는 **[−12.50, 29.17] pp**입니다. 비EOS 20/296건과 최종 형식 invalid 35/120건은 별도로 기록했습니다. 이 수치로 본 가설을 판정하지 않았습니다.

2/4 worker pilot의 8개 출력은 같았고 전체 wall-clock은 101.35/101.41초로 개선이 없었습니다. 긴 입력의 메모리 여유를 고려해 GPU당 1 worker를 사용했습니다. D24의 프로세스별 최대 reserved VRAM은 **12.301 GiB**였습니다.

[비용 장부](results/iter_052/usage_ledger.json): sanity·pilot·재개 검사를 포함해 완료 생성 **466건**, 생성시간 합 **13,358.49초**입니다. 미완료 시도의 관측 시간 하한 **186.30초**는 별도이며 정확한 총비용으로 합치지 않았습니다.

[최종 봉인](results/iter_052/completion.json)의 파일·원시 결과 digest 334개를 재검증했습니다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

기존 iter_049 원본과 현재 MedGemma loader·lock helper를 재사용했습니다. helper 5개는 iter_043 승인 출처와 동일 blob임을 확인했습니다.

CT 자료의 실제 적격 규모와 workflow 실행 비용·출력 문제를 확인했습니다. 그러나 E 본평가가 없어 압축 손실, 원본 재접근 효과, 새로운 방법의 필요성은 검증하지 못했습니다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 본 가설 판정 불가:** E 표본 부족 및 D 비EOS 잔존. 자료 gate 실패 후 최종 답변 cap 추가 보완은 수행하지 않았습니다.
- **재사용 전 수정:** 일반 E 실행의 gate 강제 연결, 비불투명 alpha 입력 처리의 일관성, 초기 실행 전용 테스트 경로를 보완해야 합니다. 현재 실행기를 일반 승인본으로 취급하면 안 됩니다.
- **추후 개선:** 중단 요청의 정확한 종료 시각과 CPU·RAM·I/O 경합 측정을 보강할 수 있습니다. 현재 비용은 격리된 배포 latency 측정이 아닙니다.

# Recommendation to GPT

이번 반복은 **자료 gate 실패에 따른 종료**로 리뷰하십시오. D24 결과는 탐색 기록으로 보존하고, 의료 VLM 능력이나 다중 영상 가설의 기각으로 확대하지 마십시오. 후속 투자는 확보 가능한 평가 규모와 남은 출력 검증 비용을 함께 판단해야 합니다.

SELF_CHECK: FAIL
SUMMARY: CT 감사 적격 287개로 E263/280 자료 gate가 실패했다. D24 296건과 독립 재계산은 완료했지만 비EOS 20건이 남아 본 가설은 미검증이다.