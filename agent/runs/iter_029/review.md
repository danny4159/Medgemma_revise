# 요약

- **판정:** CONTINUE / improve. 실제 결과 재평가는 유효하지만 계획한 교정의 완결성은 부족하다.
- **핵심 근거:** E 빈 출력 398명에서 entropy AUROC 0.8225, Presence B0 0.8154다. 차이의 97.5% CI는 [−0.0304, 0.0152]로 재현됐다.
- **의미·한계:** 단순 위험 baseline은 사전 목표를 충족한다. 새 confidence 학습의 필요성·독립 일반화·검출 개선은 입증되지 않았다.
- **다음:** decision과 재사용 검증을 제한적으로 보완하고 후속 연구 투자를 비교한다. 새 GPU 본실험 재생성은 필요 없다.

# Assessment

계획·plan.json·보고서·changes.patch·commit.json·reuse_manifest, 신규 소스 6개와 관련 통계·원시 결과를 직접 확인했다. 리뷰 SHA는 `0a47e99642921fb22fa49219e58805381e9eb25f`다. 신규 소스 bytes가 해당 SHA와 일치하고 git status/diff는 비어 있으며 unpreserved_paths는 없다. 별도 execution amendment는 없고 선별 반입 목록도 비어 있다.

이번에는 새 GPU 실험을 실행하지 않았다. 기존 GPU 출력으로 가설을 해석 가능하게 재평가했으므로 valid_experiment=true다. 코드 검사만 수행한 setup과는 다르지만, iter_028과 독립된 환자 실험이나 추가 재현으로 세면 안 된다. 리뷰에서는 파일을 생성·수정하거나 모델 실험을 실행하지 않고 읽기 전용 재계산을 수행했다.

# Key Findings

1. **원시 결과와 입력 연결:** C 2,000건, E 1,990건을 직접 읽었다. 예상 환자×variant×task 행렬 및 request_id가 일치했고 중복은 없었다. record의 영상 경로·file hash·저장 pixel hash·adapter·split 연결을 확인했다. 현재 영상 1,200개의 file hash와 원본 GT category/box도 일치했다. 현재 protocol의 잠긴 17개 파일 hash 불일치는 0이다.
2. **주분석과 대표 선택:** C 전체 생성 400명 중 빈 출력 199명·미검출 36명, E 빈 출력 398명·미검출 70명을 분석했다. 원시 Yes/No 값으로 Presence=Yes−No, P(True)=No−Yes를 별도로 구성했으며 저장 표와 일치했다. C의 대표 T는 entropy, V는 presence_b0이며 V AUROC는 0.7493183이다.
3. **E 통계 재현:** 별도 rank AUROC와 seed 28017 환자 bootstrap 10,000회를 사용했다. entropy AUROC는 0.8224739, 95% CI [0.7592101, 0.8795061]이다. Presence B0는 0.8153746, CI [0.7507369, 0.8730937]이다. 주요 bootstrap에서 비유한 값은 없었다.
4. **주비교:** E V−T는 −0.0070993, 97.5% CI [−0.0304403, 0.0151615]다. V−seed는 +0.2011760, CI [0.1251737, 0.2729738]다. 재질의가 seed disagreement보다 낫다는 결과와 token baseline보다 추가 이득이 있다는 주장은 구분해야 한다.
5. **검토 포착률:** 상위 80/398명, 즉 20.10% 검토에서 entropy는 43/70명, Presence B0는 경계 동점 기대값 40.2857/70명을 포착한다. 각각 Capture 0.6142857, 0.5755102로 별도 계산과 일치했다. entropy를 사용해도 27/70명의 사건이 남는다.
6. **Calibration:** C에서 적합한 8개 mapping을 검사했다. 양의 slope 조건의 gradient는 약 1e−16 수준이며 ptrue_m0는 비음수 slope 제약의 경계 최적 조건을 충족한다. E Brier/ECE도 별도 계산과 수치 오차 범위에서 일치했다. entropy Brier/ECE는 0.1105884/0.0450218, Presence B0는 0.1120420/0.0436252다.

# Problems / Concerns

**현재 과학적 판단:** 독립 재계산으로 주요 수치와 사전 단순 baseline 기준 충족을 확인했다. 전체 결과를 무효화할 문제는 발견하지 못했다. 다만 저장 decision이 계획을 정확히 구현했다는 보고는 승인할 수 없다.

**Decision 오류:** `run_iter029_decide.py`는 재질의 추가 이득을 E가 아니라 C의 차이와 CI로 판정한다. C CI는 95%인데 필드명을 `C_diff_V_minus_T_ci_lo_975`로 기록한다. 올바른 E 기준으로 계산해도 이번 positive=false는 유지된다. 따라서 현 데이터의 결론을 뒤집지는 않지만 재사용 전에 수정해야 한다. token family 판정에서 token_nll_eos도 빠졌다.

**감사 범위 과장:** `check_pixel_hashes`는 file hash만 계산하고 pixel 중복 검사도 file hash를 사용한다. protocol은 split 내 digest가 하나인지 확인하는 수준이며 과거 실행을 완전히 인증하지 않는다. 평가기는 audit 성공이나 입력·calibration digest를 강제하지 않고, decision은 연결되지 않은 verify의 ok만 읽는다. 이번 리뷰에서 실제 입력을 추가 대조한 사실이 실행기의 누락을 해결한 것은 아니다.

**보존:** C/E main에는 대표 report 존재 검사만 있고 산출물 묶음의 원자적 확정은 없다. audit·verify·decision은 기존 결과에 무조건 쓴다. stream에서 decision 삭제 명령이 거부된 뒤 같은 스크립트로 결과를 덮어쓴 것을 확인했다. 이때 보이는 코드 변경은 JSON 문자 표기 변경이지만, 계획한 기존 결과 보존 절차는 지켜지지 않았다. 후속 교정본은 새 경로에 저장해야 한다.

**검증 누락:** 저장 18/18 PASS는 실제 fixture 범위 안의 결과다. 단순 산술과 소스 문자열 존재 검사를 포함하므로 출처 변조·전체 완료 연결·덮어쓰기 거부 검사를 완료했다는 근거가 아니다. 독립 검증 스크립트 자체도 paired CI와 calibration 최적 조건은 검증하지 않는다. 해당 수치는 이번 리뷰에서 별도로 확인했다.

**과거 protocol:** iter_028 stream에서 전체 환자에서 빈 출력 환자로 제한하는 한 줄 변경과 protocol 재잠금을 확인했다. 해당 변경은 개별 환자의 scoring 계산을 바꾸지 않는다. 그러나 재잠금 전 protocol bytes와 당시 전체 파일 상태까지 복원한 것은 아니므로 보고서의 '완전히 재구성'은 범위를 좁혀야 한다.

# Interpretation

Presence 역상관은 모델 현상이 아니라 평가 부호 오류였고 이번 수치로 정정됐다. 동일한 빈 bbox 응답에서도 token uncertainty로 미검출 위험을 순위화할 수 있다는 관찰은 유지된다. 이 결과는 actor의 검출 성능을 개선하거나 미검출을 실제로 복구한 결과가 아니다.

재질의의 사전 +0.10 AUROC 이득 기준은 충족하지 않으며 E CI 상한도 0.0152다. 따라서 현 조건에서 큰 추가 이득을 근거로 새 방법에 투자할 이유는 부족하다. 작은 양의 효과 가능성, 다른 prompt·seed·데이터의 효과까지 기각한 것은 아니다.

C/E는 기존 개발 자료다. 환자 분리와 사전학습 미노출은 다르며 조건부 bootstrap은 C 대표 선택·calibration 추정의 전체 불확실성을 반영하지 않는다. opacity와 음성 category별 AUROC가 정의되지 않는 것은 각 category가 사건 단일 class이기 때문이다. 임상 유병률·안전성으로 일반화하면 안 된다.

새 생성 0건·학습 0건은 이번 계획에 부합한다. 이미 존재하는 유효한 GPU 산출물을 재집계하는 데 GPU 처리량 pilot을 반복할 이유는 없다. 다음 GPU 사용 시에는 기존 실행기 결함과 두 GPU의 실제 처리량·안전 여유를 선택한 경로에서 확인해야 한다.

# Strategy Check / 연구 방향 판단

- **실행 유효성:** 기존 실제 출력의 교정 분석은 유효하다. 새 독립 실험은 없으며 기계 판독 decision과 재사용 검증에는 결함이 남는다.
- **성능 개선:** 교정 전후 모델 행동은 같다. 위험 순위 baseline의 성능을 정확히 복구했으며 bbox 개선을 만든 것은 아니다.
- **가설 지지:** H1은 지지된다. H2의 사전 재질의 추가 이득 기준은 충족하지 않는다. 효과의 정확한 영점이나 모든 재질의의 실패를 주장하지 않는다.
- **신규 기여 가능성:** 강한 단순 baseline을 확보했지만 기존 uncertainty 방법과 구별되는 실패 조건·원리·해결책은 아직 없다.

현재 방법에 새 head/loss를 추가하는 선택은 보류한다. 동일 opacity의 외부 확인은 실제 사용 조건과 annotation 대응이 확보될 때 일반화 판단에 가치가 있다. 잔여 미검출 진단은 baseline이 놓치는 중요한 조건을 식별하고 후속 선택을 바꿀 때만 가치가 있다. 다른 질문으로의 전환도 기존 RSNA checkpoint에서 남은 정보 이득과 비교해야 한다. 사분면 진단을 이름만 바꿔 반복하거나 원본 모델의 다른 task로 조용히 이동하지 않는다.

논문 추천은 보류한다. 단순 baseline의 긍정적 근거는 있지만 새 confidence 방법 투자는 보류 대상이며, 이번 리뷰에서 바로 다음 판단에 연결할 미추천 논문의 원문 검증을 완료하지 않았다.

# Recommended Next Experiment

먼저 새 결과 경로에서 E 기준 decision과 필요한 입력 연결·보존 검증만 보완한다. C/E raw 생성과 검증된 통계를 전부 다시 실행할 필요는 없다. C와 E가 서로 다른 결론을 내는 fixture로 이번 판정 오류의 재발을 막는다.

동시에 다음 deep 계획에서 외부 확인·중요한 잔여 미검출 진단·다른 GOAL 내 질문의 정보 이득을 비교한다. 유용한 실패 조건과 강한 baseline 대비 판단 가능한 실험이 정해질 때만 새 GPU 작업으로 진행한다. 이번 improve를 같은 confidence 접근법의 자동 연장으로 해석하지 않으며 MRI F139·reserve·새 loss는 자동 투입하지 않는다.