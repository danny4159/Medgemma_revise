# 요약

- **핵심 결과:** 사전 정한 자료 적합성 점검에서 회복 집단 N이 0명이었다. 계획된 종료 분기에 따라 N/T/L 생성은 실행하지 않았다. 학습도 하지 않았다.
- **근거:** E96 비정상 48명의 reference·초안(C-G)·영역 설명 29개를 전부 읽고 대조했다. 초안에 없던 reference 양성 사실이 영역 설명에 명확히 있는 환자(Q)는 2명(P085, P090)이다. 둘 다 초안이 보존한 reference 사실(P)이 없다.
- **미검증·주의:** H1·H2는 검증되지 않았다. 이번 결과는 자료 점검 결과이고, 영역 설명 교정이 무익하다는 결론이 아니다. 판정은 assistant 한 명의 수동 검토다. 전문의 검토도 독립 검증도 아니다.
- **다음:** 이 E96 표본에서는 이 교정 인터페이스 투자를 보류하길 권고한다. 재개 조건은 Recommendation to GPT에 적었다.

# Work Performed

- 자료 연결용 모듈 `report98_data.py`를 작성했다.
  - iter_086 `readings.jsonl`에서 C-H의 영역 segment 29개와 GRG segment를 분리한다.
  - `Description` 본문만 추출하고 정확히 같은 본문은 묶는다.
  - 헤더 형식 실패나 좌표 잔존은 assertion으로 중단하게 했다. 48명 모두 통과했다.
- 환자별 초안, reference 사실(v2 class 포함), 묶은 영역 설명을 한 파일로 만들어 직접 읽었다. 파일은 `results/iter_098/data/view_abnormal48.txt`다.
- 읽는 중 P042의 `left lung` 영역 출력이 같은 문장을 수천 번 반복하는 퇴화 출력임을 확인했다. 입력 구성 시 그대로 두면 컨텍스트가 비정상적으로 길어진다.
- iter_088 `linked.json`의 자동 라벨로 후보 색인을 재현했다.
  - C-H에만 있는 reference 양성 사실이 있는 환자는 9명이다: P008, P033, P036, P053, P076, P080, P085, P086, P090.
  - 이 9명을 원 reference와 원문 문맥으로 수동 재판정했다.
- `report98_lock.py`로 판정을 인용 문구와 함께 고정했다. 모든 인용이 실제 원문에 존재하는지 기계 검사하고, 결과를 배타 생성(`"x"`)으로 저장했다.
- 생성 경로 보완(task 3~5)과 사실 단위 평가(task 6~7)는 하지 않았다. N=0이면 생성하지 않는다는 계획의 종료 분기를 따랐다.

# Files Changed

- `report98_data.py` (신규)
- `report98_lock.py` (신규)
- `results/iter_098/data/view_abnormal48.txt` (신규, 검토용 원문 모음)
- `results/iter_098/data/eligibility_decision.json` (신규, 잠금과 결정)
- 기존 파일은 수정하지 않았다.

# Commands / Experiments (실제 실행한 명령과 성공/실패)

- `nvidia-smi` 조회: 성공. GPU 0·1 모두 거의 비어 있었다. 이번 반복에서 GPU 작업은 없었다.
- 데이터 구조 확인용 `python -c`: 성공.
- 48명 검토 파일 생성: 성공 (`python -c`, 128KB).
- `python report98_lock.py`: 성공, exit 0, `quote_check_problems=[]`.
- 학습과 GPU 생성은 실행하지 않았다. 따라서 tensor 대조, 재개·변조 검사, 병렬 처리량 비교는 이번에 수행하지 않았다. GPU 대기 helper도 사용하지 않았다.
- 시간과 비용은 측정하지 않았다. 수동 검토 시간도 미측정이다.

# Results (수치와 결과 파일 경로)

결과 파일은 `results/iter_098/data/eligibility_decision.json`이다.

- 자동 색인에서 Q 후보는 9명이다. P가 비어 있지 않은 환자 중 Q 후보는 P008, P033, P053 세 명이다.
- 수동 판정 결과는 다음과 같다.

| 구분 | 환자 | 사유 |
|---|---|---|
| Q 명확 | P085, P090 | 우측 기저부 opacification, 우측 횡격막 거상이 reference와 대응한다. 둘 다 초안이 reference 사실을 보존하지 못해 P가 비어 있다. |
| 모호·시간 속성 | P008, P033, P053, P036 | reference가 시간 비교 속성이다. P008은 초안이 이미 유사 소견을 기술한다. P033·P053은 hedged 음영과 위치 범위만 부분 대응한다. P036은 P가 비어 있다. |
| 모호 | P076, P080, P086 | `new RLL opacity`와 `infiltrate`, `tortuous`와 `elongation`, `unfolding`과 `elongation`의 의미 동치가 규약 밖이다. P도 비어 있다. |

- 초안이 reference 양성 사실을 명확히 보존한 P 환자는 14명이다. 이 중 영역 설명이 다른 reference 양성 사실을 추가로 명확히 제공하는 환자는 없다.
- **N = 0명이므로 `run_generation=false`.**
- 영역 설명 본문의 대부분은 정상 문구이거나 여러 환자에 반복되는 템플릿이다. 예: `trachea deviated by large goiter`, `vague opacity in RLL, new since prior`. 이 점은 소수 사례로 확인했을 뿐 빈도로 정량화하지 않았다.

# Goal Progress / Reused Assets (목표 진전·미검증 범위, 재사용 출처·검증)

**새로 알게 된 것**
- 이 E96 비정상 48명에서는 "영역 설명에 있고 초안에 없는 reference 양성 사실"이 매우 드물다.
- 그 사실이 있는 환자에게는 보존할 초안 사실이 없다.
- 현재 CURE 영역 출력은 이 교정 질문의 기회를 거의 만들지 못한다.
- 평가 가능성은 확보되지 않았다.

**운영 복구와 과학적 관찰의 구분**
- 운영 복구는 없었고 연구 판단의 새 근거만 얻었다.

**세 판단**
- 시험 설정: 이 표본에서 교정 인터페이스 실행은 보류다.
- 연구 관찰: 영역 출력이 기회를 거의 제공하지 않는다는 점은 유지한다.
- 연구 질문: 다른 정답 근거나 다른 영역 출력이 있으면 미해결로 남는다. 이 결과만으로 기각하지 않는다.

**미검증**
- H1(내용 효과), H2(출처 메타데이터 효과).
- 단순 추가(A)와 초안 유지(K) 대비 효과.
- 정상 층과 E96 밖의 빈도.

**재사용**
- iter_086 `readings.jsonl`, iter_087 reference amendment, iter_088 `linked.json`을 읽기 전용으로 재사용했다.
- 파일 hash는 `inputs_sha256`에 기록했다.
- 생성기·평가기 코드는 이번에 쓰지 않았고, iter_097 생성기의 `needs_fix`는 그대로 남아 있다.

# Problems (현재 결론 무효 / 재사용 전 수정 / 추후 개선을 구분)

- **현재 결론 무효:** 없음. 다만 판정이 assistant 한 명의 단일 검토다. `ambiguous` 7건을 `clear`로 다르게 보면 Q 후보는 늘 수 있다. 그래도 P가 비어 있어 N=0은 유지된다. P의 `clear` 14건은 단일 검토다.
- **재사용 전 수정:** 해당 없음. 새 생성 코드를 쓰지 않았다.
- **추후 개선:** P042 같은 퇴화 반복 출력은 입력 구성 단계에서 길이 상한 같은 규칙이 필요하다. 이번에는 생성하지 않아 영향이 없었다.
- 자동 색인 후보 9명 외의 환자는 영역 설명과 reference를 직접 읽어 확인했다. Q가 없다는 판정은 단일 검토다.

# Recommendation to GPT

- **권고: 보류.** 이 E96 표본의 영역 설명 교정은 투자를 보류하길 권한다.
  - 이유: 정보 가치가 작다. N=0이라 생성해도 H1·H2를 판별하지 못한다.
- **재개 조건 (아래 중 하나)**
  - 영역 설명이 reference 양성 소견을 실제로 담는 다른 영역 출력이나 모델이 있다.
  - 새 독립 정답 근거가 생겨 `ambiguous` 판정을 바꾼다.
- **선택하지 않은 대안:** Q-only 환자 P085·P090으로 교정 생성을 하는 것. 사전 고정한 N 정의를 사후 변경하는 일이라 하지 않았다.
- **다음 투자 후보:** 이번 관찰(영역 출력이 소견을 거의 새로 제공하지 않음)은 이전 관찰(iter_088의 추가 정보와 충돌 공존)과 방향이 다르다. 다음 계획에서 두 관찰을 함께 놓고 최소 비교 하나를 선택하는 것이 좋다.
- 학습은 발주하지 않았고, 현재 LoRA 설정은 보류 상태 그대로다.

SELF_CHECK: FAIL
SUMMARY: E96 비정상 48명에서 영역 설명 교정의 회복 집단 N이 0명이라 생성 없이 보류했다. H1·H2는 미검증이고, 판정은 assistant 단일 수동 검토다.

# [orchestrator] 권한 거부된 도구 호출
- Bash: python - <<'E'
import json
L={ (r['ImageID'],r['condition']):r for r in map(json.loads,open('results/iter_086/E96/readings.jsonl'))}
inp=json.load(open('results/iter_086/E/inputs_E96.json'))
ab=[i for i in inp if i['stratum']=='abnormal']
print(len(ab))
i0=ab[0]['ImageID']
h=L[(i0,'C-H')]; g=L[(i0,'C-G')]
print([ (s['source']) for s in h['segments']])
print(json.dumps(g,ensure_ascii=False)[:1500])
print(h['segments'][29])
print(h['request_ids'][:3], h['record_sources'][:2])
R=json.load(open('results/iter_087/reference_amend_E96.json'))
print(type(R), list(R)[:5] if isinstance(R,dict) else R[:1])
P=json.load(open('results/iter_086/E/reference_facts_E_private.json'))
print(type(P), list(P)[:3] if isinstance(P,dict) else P[:1])
E
