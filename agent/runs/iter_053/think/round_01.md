# 사고 라운드 1

## 이번 판단

현재 CT 압축·재접근 본평가의 투자 보류를 유지한다. E263으로 축소하거나 MRI 감사로 이어가지 않는다. 확보한 D24를 보완하는 것만으로 원 E280 자료 gate가 해결되지 않으며, 현재 출력에서 후속 방법 투자를 정당화할 내용상 실패도 분리되지 않았다.

다음 후보는 소견 검토 과정의 오류 수정과 올바른 내용 보존으로 좁혔지만, 실행을 승인할 근거는 아직 부족하다. 공개 자료의 실제 정답과 강한 비교군 경로를 확인하는 한정 후속 판단이 필요하다. 이는 iter_047의 자동 재개나 새로운 contribution 선정이 아니다.

## 원문에서 확인한 사실

- GOAL, GPT_USAGE_POLICY, REPORTING_STYLE, LIMITATIONS의 관련 항목, CODE_ASSETS의 관련 기록을 확인했다. iter_052 plan/review 및 review.json/code_assets, iter_048 review, iter_051 review, iter_047 plan과 review.json을 읽었다. 대안 판단에는 iter_018·029·042의 원본 review.json과 iter_049 첫 전략 조사 노트를 확인했다.
- iter_052 리뷰는 적격 CT 287개, D24 제외 E263/280, 본평가 미실행을 기록한다. D24 최종 invalid는 35/120건, 전체 비EOS는 20/296건이다. 정상 출력 조건의 압축 손실이나 재접근 효과는 미판정이다. 이 수치는 원 리뷰의 독립 검증 결과를 인용하며 이번에 신규 재계산한 값은 아니다.
- 완료 생성 466건의 generation time 합 13,358.49초에는 sanity·pilot·재개가 포함된다. 이를 정확한 총 device 점유시간이나 배포 latency로 바꾸지 않는다. iter_049~052의 자료 확보·감사 비용도 투자 판단에 포함하되 유효 가설 실험 횟수로 세지 않는다.
- iter_048에서는 공동 직접 SFT가 공동 F1@0.3을 E 0.333116에서 J 0.523251로 높였다. 그러나 적응 MedGrounder A는 0.594444였고 J/E 비용 기회도 충족하지 못했다. 현재 공동 grounding의 새 loss 투자를 다시 여는 근거는 없다.
- iter_047은 혼합 상태 자료 34/52명과 D8 oracle 29/32로 본평가가 미실행됐다. 원 계획은 이미 직접 검토·보존 지시·초안 없는 공동/개별 판독·text-only를 포함했다. 같은 대조를 새 아이디어라고 다시 제안해서는 안 된다. 새 자료가 원래 정답 문제를 해결하는지와 가까운 기존 방법 이후의 질문이 남는지가 재개 조건이다.
- iter_018의 인터페이스 민감성과 iter_042의 부재 거부 관찰은 유지한다. 단순 분리 처리나 presence gate 이후의 중요한 부족함이 확정된 결과로 확대하지 않는다. iter_029에는 강한 entropy 위험 순위 baseline이 있어 일반적인 confidence 측정 반복도 우선하지 않는다.

## 인계와 보존 경계

두 RETRACTION 원문을 직접 확인했다. 후자가 image_redo_01~25 및 redo_26 일부까지 무효화한다. 이전 무효 감사는 근거로 사용하지 않는다. 담당 전환 인계는 iter_051에서 자료 종료점까지 처리됐고 iter_052가 이를 명시하므로 이번에 반복하지 않는다. 현재 실행 설정의 구현 담당은 Claude다.

현재 research HEAD는 `3f9bff15a0cd2d198171580f783919eb9d84c9d9`이고 작업 트리는 깨끗했다. `git ls-files`와 실제 `rsna_diag/generate.py`, `mt52_run.py`, `mt52_spec.py`를 확인했다. 모델 loader·생성 helper는 존재하지만 과거 단일 영상 padding과 D 전용 runner를 새 과제의 승인된 실행기로 취급할 수 없다. iter_052의 gate 연결·alpha·GPU 고정·감사 provenance reuse_issues는 유지한다. 실행 과제가 확정되지 않았으므로 선별 반입이나 미사용 코드 수정을 요청하지 않는다.

## 선행 조사에서 새로 확인한 것

1. **CoT 저하 자체는 이미 직접 연구됐다.** Better Eyes, Better Thoughts는 의료 VQA에서 CoT와 직접 답변을 비교하고 ROI 및 설명 제공 개입까지 다룬다. 따라서 D24의 긴 출력 문제를 근거로 단순 CoT 대 직접 답변 실험으로 이동하는 정보 가치는 제한적이다. 원인 분리 없이 같은 현상을 MedGemma에서 관찰하는 것만으로 차별화하기 어렵다. [원문 v2](https://arxiv.org/html/2603.06665v2)
2. **임상 문맥 편향도 가까운 방법이 있다.** Med-CP는 정확하거나 잘못된 임상 prompt의 영향을 비교하고 cross-modal reflection SFT를 제안한다. 이전 iter_052가 이 연구를 이미 언급했으므로 이번 조회는 미확인 비교 범위를 확인한 것이다. 단순히 문맥에 속는다는 진단은 새 방향 선정의 충분한 근거가 아니다. [EACL 논문](https://aclanthology.org/2026.eacl-industry.67/)
3. **단계별 검증에는 적합해 보이는 자료가 있지만 접근성은 별도다.** Med-StepBench는 PET/CT의 네 단계 진술과 오류 변형을 평가하며 병원에서 수집한 자료를 사용한다. 논문·IJCAI 페이지는 확인했지만 이번 조회에서 실제 다운로드 가능한 공식 데이터 경로를 확인하지 못했다. 공개 benchmark라는 이름만으로 확보 가능한 자료로 계산하지 않는다. [논문](https://arxiv.org/html/2605.10002v1), [IJCAI](https://www.ijcai.org/proceedings/2026/761)
4. **MedHEval은 이미지가 포함된 즉시 실행 자산이 아니다.** 공식 저장소는 annotation과 split을 제공하고 원천 영상은 별도 확보하도록 명시한다. 문맥 misalignment 부분은 MIMIC-CXR/IV 연결 자료이므로 현재 접근 권한·로컬 존재 확인 없이 후보 규모로 사용할 수 없다. SLAKE·VQA-RAD·IU-Xray 부분이 이번 수정–보존 질문에 맞는지도 아직 확인하지 않았다. [공식 저장소](https://github.com/Aofei-Chang/MedHEval), [자료 구성 원문](https://arxiv.org/html/2503.02157v1)
5. **Med-HallMark의 확인한 평가 입력은 그대로 사용할 수 없다.** 공식 `Med-HallMark.json`의 공개 예시는 질문·모델 답변과 함께 ground-truth를 judge 입력에 제공한다. 이 설정을 영상만으로 오류를 검증하는 실용 baseline으로 쓰면 정답 누출이다. README는 단계적 공개 및 원천 영상 별도 확보를 명시한다. 파일 존재를 충분한 오류·보존 정답 확보로 해석하지 않는다. [공식 예시](https://raw.githubusercontent.com/ydk122024/Med-HallMark/main/Med-HallMark.json), [README](https://raw.githubusercontent.com/ydk122024/Med-HallMark/main/README.md)
6. **교정·보존도 기존 방법과의 비교가 필수다.** iter_047에서 이미 CorBenchX와 phrase-grounded fact-checking/APO를 다뤘다. 이번에 관련 원문을 다시 확인한 이유는 새 후보가 이미 검토한 설계의 반복인지 판단하기 위해서다. CorBenchX는 MIMIC-CXR 기반 오류 교정과 MSRL을 제안한다. 가까운 fact-checking의 공개 실행 경로와 현재 접근 가능한 영상에 대한 적용성을 다음 확인 대상으로 남긴다. [CorBenchX](https://arxiv.org/html/2505.12057v1), [phrase-grounded fact-checking](https://arxiv.org/html/2509.21356v1)
7. **기본 지각 benchmark로의 단순 이동도 우선하지 않는다.** MedBLINK는 임상적으로 의미 있는 기본 지각 과제를 제공하지만 일부 과제에는 강한 전용 모델 baseline이 이미 있다. 점수가 낮다는 사실만 찾는 전수 평가보다 해결하려는 실패 조건이 먼저 필요하다. [MedBLINK](https://arxiv.org/html/2508.02951v1)

위 문헌은 후보 판단용 조사 근거다. 긍정적인 로컬 실험이 없으므로 사용자 논문 추천으로 등록하지 않는다.

## 대안의 가치·비용 비교

- **교정·보존 후보의 자료 및 비교군 확인:** 실제 검토 workflow와 연결되고, 오류를 고치는 이득과 맞는 내용을 훼손하는 비용을 구분할 수 있다. 다만 기존 선행과 겹치며 공개 정답의 적합성도 미확정이다. 다음 단계는 학습이나 자료 구축이 아니라 원본 자산이 필요한 비교를 허용하는지 확인하는 것이다.
- **현재 CT의 한정 보완:** 기존 자산은 있으나 D24 정상 출력 보완 이후에도 E 부족이 남는다. 수정 비용을 들일 만큼 중요한 경쟁 설명을 현재 출력에서 확보하지 못했다. 따라서 이번 우선순위에서 제외한다. 이는 압축 손실 가설의 기각이 아니다.
- **현재 grounding 개선:** 직접 SFT·모듈형 적응·공동 SFT가 중요한 경쟁 설명을 이미 다뤘다. 새 효과 근거 없이 loss·epoch·seed를 추가하지 않는다.
- **문맥 편향·일반 uncertainty·기본 지각으로 전환:** 사용 가치는 있으나 가까운 선행과 단순 baseline을 넘어설 구체적 질문이 이번 조사에서 확인되지 않았다. 즉시 GPU 탐색 목록으로 만들지 않는다.

## 남은 판단과 종료점

다음 라운드는 교정 후보의 자료·baseline 적합성에 집중한다. 원천 영상에 연결된 오류 주석, 정답 노출 없는 입력, 수정 대상과 보존 대상의 구분, 환자 또는 원천 영상 cluster를 확인한다. 가능한 표본과 paired 평가 정밀도를 실제 집계로 산출할 수 있어야 구현을 계획한다.

이 조건이 성립하지 않으면 교정 후보를 보류한다. 자료 확보부터 시작하는 setup을 발주하거나 새 benchmark 이름만 바꾸어 같은 조사·감사를 연장하지 않는다. 현재 후보도 영상 근거와 언어 출력 연결이라는 같은 큰 질문에 속하므로 research_track과 과거 비용 이력을 유지한다.

## 대규모 GPU 필요 후보

전문가 수정 이력과 다양한 오류 밀도를 가진 다기관 자료로 시각 verifier와 편집기를 공동 학습하는 방향은 장기 후보로 보존한다. 현재는 데이터·기존 방법 대비 필요성이 미확정이다. 두 3090에서 가능한 실제 출력 대조와 경량 직접 SFT의 가치 판단이 먼저다.

파일 생성·수정, 모델 추론, GPU 실험은 수행하지 않았다.

## 다음에 파고들 질문
- phrase-grounded fact-checking/APO의 공식 데이터·checkpoint·평가 코드는 현재 접근 가능한 영상에서 직접 검토와 초안 없는 재판독을 공정하게 비교할 수 있는가? 원문에 연결된 공식 저장소와 checkpoint의 학습자료·입력 규칙을 확인한다.
- MedHEval의 비MIMIC 원본 annotation 또는 관련 공개 교정 자료에 오류 수정과 올바른 소견 보존을 함께 채점할 정답 및 원천 영상 cluster가 있는가? 실제 schema와 규모를 확인하고, ground-truth가 입력에 섞이는 judge 예시는 제외한다.
- 확보 가능한 평가 단위에서 단순 재판독·결정론적 편집 이후의 잔여 문제를 식별할 최소 대조와 정확도–비용 기준을 고정할 수 있는가? 가능하면 diagnostic 계획을 완성하고, 불가능하면 교정 후보를 보류한다.
