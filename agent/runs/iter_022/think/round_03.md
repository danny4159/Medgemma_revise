# 사고 라운드 3

## 핵심

자연적인 영상 반복·상보성 진단은 현재 확보한 주석으로 식별하기 어려워 우선순위를 내린다. 대체 후보로 **영상 제시 순서와 의미상 비교 방향을 분리하는 시간·역할 진단**을 우선 검토한다. TemMed-Bench에서 시간 관계와 원천 연결 방식은 확인했지만, 실행 가능한 영상 자료와 정답 변환 규칙은 아직 확보하지 못했다.

파일 수정·생성, 테스트, 모델 로딩, GPU 실험은 하지 않았다. 이번 결과는 문헌·공개 코드·로컬 파일의 read-only 조사이며 모델 한계나 신규 방법의 실험 근거가 아니다.

## 1. 질문 1 — MedThinkVQA의 전문가 판정 파일이 있는가?

이전 라운드에서 확인한 Appendix C의 96-case 감사와 supportive/complementary/sufficient의 구분은 유지한다. 이번에는 공식 GitHub의 공개 schema·최상위 구성과 Hugging Face의 assets까지 확인했다. HF assets에는 dataset.png, figure1.png, overview.png가 있으며, 별도의 영상별 감사 판정 파일은 확인되지 않았다. GitHub schema에는 영상 ID·경로·caption·modality와 case 정답이 있지만 supportive/redundant 감사 필드는 명시되지 않는다. [공식 코드·schema](https://github.com/benluwang/MedThinkVQA), [HF assets](https://huggingface.co/datasets/bio-nlp-umass/MedThinkVQA/tree/main/assets)

GitHub 하위 디렉터리와 recursive tree 조회 일부가 실패했으므로 저장소 전체에 주석이 없다고 확정하지 않는다. 정확한 결론은 **현재 확인한 배포 경로에서 해당 주석을 확보하지 못했다**는 것이다. 이 불확실성 아래서는 caption·유사도·modality를 상보성 정답으로 대체하지 않는다. 같은 검색을 더 반복하는 것보다 해당 주석을 필수로 요구하지 않는 과제를 비교할 가치가 높다.

따라서 전체 영상 집합을 사용하는 진단 정확도 비교는 가능하지만, 특정 부분집합의 오답을 충분한 근거 무시로 해석하거나 자연적인 유사 view를 정답 보존 중복으로 선언할 근거는 없다. 정확한 복제만의 대조는 중복 제거 baseline이 원래 입력을 복원하므로 주방법 후보에서 계속 제외한다.

## 2. 질문 2 — joint 대 분리 실행에서 TwI와 다른 실패 조건이 남는가?

이전 라운드의 일반적인 중복 판단을 구체화하기 위해 MedThinkVQA §4.2를 확인했다. 논문은 expert 소견과 self-generated 소견을 구분하고, 생성 소견을 추가했을 때의 성능 하락도 이미 보고한다. 예를 들어 MedGemma-27B의 self-hint 조건은 baseline보다 3.5 pp, self-summary/Both는 12.5 pp 낮다. 이 수치는 MedGemma 1.5 4B의 자체 실험 결과가 아니다. [MedThinkVQA §4.2](https://arxiv.org/html/2604.16506v1#S4.SS2)

따라서 direct·분리 소견 생성·소견 통합·oracle 소견의 평균 정확도만 비교하면 기존 분석과 겹친다. 원본 영상을 다시 보는 reader의 비교는 유용한 baseline이지만, 그것만으로 새로운 원리를 확보한 것은 아니다.

현재 자료에서 자연적 상보성에 관한 고유한 실패 조건을 확정하지 못했다. 이를 숨기고 큰 benchmark나 새 loss를 시작하지 않는다. 대신 다음처럼 정답 관계가 명시되는 질문은 별도로 검토할 수 있다.

- 영상과 역할 표지를 함께 재배열하면 의미상 과제와 정답은 유지돼야 한다.
- 같은 두 영상의 비교 방향 자체를 바꾸면, 방향성 소견에서는 정답 관계가 달라져야 한다.
- 첫 조건만 실패하면 제시 위치·입력 연결이 경쟁 설명이다. 두 번째만 실패하면 방향 해석 또는 시각적 변화 인식이 경쟁 설명이다.

이는 새 실험에서 사용할 수 있는 논리적 구분이지, 아직 재현된 실패나 독창성 주장도 아니다. 단순 yes/no 정답을 일괄 반전하는 규칙은 성립하지 않는다. stable·부정·불확실·복합 소견은 별도 취급해야 한다.

## 3. 질문 3 — 대체 임상 과제와 원천 영상 접근

### TemMed-Bench에서 새로 확인한 것

TemMed-Bench는 CheXpert Plus의 현재 영상과 같은 환자의 가장 최근 이전 방문 영상을 연결한다. 변화 보고서에서 VQA를 만들며, 논문은 2,000 VQA, 1,000 report-generation 사례, 862 image-pair selection 문항을 기술한다. VQA의 수동 검토는 질문과 보고서의 정합성을 확인하는 절차다. 영상의 모든 변화가 독립 판독으로 검증됐다는 의미는 아니다. [TemMed-Bench §2](https://arxiv.org/html/2509.25143v1#S2)

이 과제는 자연적 상보성보다 시간 역할이 명시적이라는 장점이 있다. 그러나 가장 최근 방문이 실제 보고서의 비교 기준과 항상 같다는 보장은 별도 확인이 필요하다. 방향성 문장을 추출하더라도 원본 comparison 내용·환자·시점 연결을 검증해야 한다.

공식 저장소는 CheXpert Plus 영상·보고서를 재배포하지 않으며 Stanford에서 별도로 받아야 한다고 명시한다. HF의 공개 JSON만으로 영상 실험을 실행할 수 없다. [TemMed-Bench 자료 준비 안내](https://github.com/Levi-ZJY/TemMed-Bench)

공식 `Get_Report_TestSet.ipynb`를 직접 읽었다. 이 코드는 `df_chexpert_plus_240401.csv`의 `path_to_image`와 `section_impression`을 연결하고, JSON의 `image_path`·`reference_images`를 사용해 보고서를 붙인다. 저장된 notebook 출력에는 `deid_patient_id`, `patient_report_date_order`, `section_comparison` 등 원천 필드가 있다. 이는 연결 경로의 존재를 보여 주지만 우리 환경의 자료 확보나 연결 검증 완료를 뜻하지 않는다. [공식 연결 notebook](https://raw.githubusercontent.com/Levi-ZJY/TemMed-Bench/main/Get_Data/Get_Report_TestSet.ipynb)

Stanford의 현재 CheXpert Plus 소개는 canonical URL로 Redivis를 안내한다. 이전 Azure 링크와 현재 canonical 페이지 모두 이번 도구에서는 상세 접근 화면을 읽지 못했다. 사용자의 기존 승인 여부나 실제 다운로드 가능성을 추정하지 않는다. [Stanford 공식 자료 안내](https://aimi.stanford.edu/datasets/chexpert-plus)

### 로컬 접근 확인의 범위

`legacy/eval_samples`와 `research/results`를 ignore 파일까지 포함해 파일명으로 검색했다. 확인된 관련 자료는 legacy CheXpert 소량 영상과 `research/results/iter_018/source/chexpert_validation.parquet`다. TemMed-Bench 또는 `df_chexpert_plus_240401.csv`는 이 검색 범위에서 찾지 못했다. 다른 저장 위치나 사용자 권한의 부재까지 의미하지 않는다. 기존 validation subset이 필요한 longitudinal pair를 제공한다고 가정하지 않는다.

### 대체 공개 자료의 위치

MedMultiBench의 공식 README에서 Temporal Analysis와 Difference Description이 실제 하위 과제로 명시된 것은 확인했다. 그러나 해당 하위 디렉터리 조회는 실패해 문항·원천 영상·시간 관계 정답을 연결하지 못했다. 따라서 이름만 보고 TemMed-Bench의 접근 문제를 해결하는 대체 자료로 채택하지 않는다. [공식 과제 목록](https://github.com/pkusixspace/MedMultiBench)

## 4. Strategy Check / 연구 방향 판단

중요한 능력은 동일한 임상 영상에서도 어떤 시점·역할을 비교하는지에 맞춰 답을 바꾸는 것이다. 현재 비교는 다음과 같다.

1. **시간·영상 역할 관계 진단:** 정답 보존 재배열과 의미 변화 대조를 분리할 가능성이 가장 높다. TemMed-Bench의 원천 연결 코드는 확인됐지만 영상 접근과 비교 기준 검증이 남아 있다. 제한적인 추가 확인이 실제 GPU 실험의 가능 여부를 바꾼다.
2. **자연적인 반복·상보성 진단:** 임상적 가치는 있으나 필요한 주석을 확보하지 못했다. generic joint/분리 비교는 TwI와 겹친다. 현재는 투자를 보류한다.
3. **현재 MRI 과제 보정:** 기존 출력은 있지만 동일-grid 좌표 복사로 높은 점수가 가능한 문제가 남는다. 이번 새 근거는 F139 개방이나 O prompt 탐색을 지지하지 않는다.
4. **기존 grounding 방법 개선:** 직접 SFT 자산을 보존한다. 추가 loss를 재개할 새로운 효과·효율 가설은 확보하지 못했다.

이번 우선순위는 자료 이름이나 새 benchmark의 저점수에 따른 결정이 아니다. 질문·입력 변화에 따른 정답 관계의 식별성과 실제 접근 비용에 따른 잠정 판단이다. 현재 MRI의 inconclusive 판정도 소급 변경하지 않는다.

시간 역할 후보에서도 양성 결과는 정상 사용 후 남는 방향 의존 오류를 지지할 뿐 내부 원인을 확정하지 않는다. 역할 표시·정상 입력 보정으로 해소되는 음성 결과면 해당 설계의 방법 개발을 중단한다. 원본 비교 기준이나 자료 접근이 불확정이면 표본 확대보다 자료·과제 선택을 먼저 해결한다.

## 5. 재사용·자원·보존

`agent/GOAL.md`, `agent/REPORTING_STYLE.md`, `agent/LIMITATIONS.md`, iter_021 원본 리뷰와 관련 `CODE_ASSETS.md`, iter_019의 시간 자료 조사 기록을 읽었다. 연구 HEAD는 `933eebaba2689d6eb654808ea177d8625ca2ca4c`이며 `git status --short`와 `git diff --stat`에 변경이 없었다. tracked 목록에서 기존 생성·다중 영상·잠금 모듈을 확인했고 `generate.py`와 `mi19_gen.py`의 관련 경로를 읽었다.

기존 `load_image`는 정사각 padding을 수행한다. 새 흉부 영상 진단에서 그대로 사용해 정상 사용이 검증됐다고 간주하지 않는다. 실제 development 영상으로 공식 processor 경로와 입력 tensor를 대조해야 한다. 완료 재사용의 성공 상태·종료 코드·예상 요청 집합·source 연결 및 통제 재개 검사는 실제 선택한 경로에서 보완한다. MRI 좌표·S1→S2 전용 정비는 자동 편입하지 않는다.

`reuse_assets=[]`는 조사 단계의 미확정 값이다. 새 구현 계획에서는 승인 기반과 필요한 파일·의존성을 실제 blob과 대조해 선별 반입을 확정한다. 현 저장소에 파일이 있다는 사실을 전체 재사용 승인으로 취급하지 않는다.

GPU 실험 규모와 시간은 이번에 정하지 않았다. 과제가 확정되면 두 GPU에서 development 입력으로 batch 확대 또는 GPU당 2 worker를 비교한다. 실제 긴 입력·출력 peak, worker당 최소 2 GiB 여유, 출력 정합성과 전체 처리량으로 배치를 정한다. 기존 MRI 처리 시간을 새 과제에 그대로 적용하지 않는다.

MRI F139, 기존 RSNA·CheXpert reserve, checkpoint와 결과를 유지한다. iter_008 anatomy 전이는 재개하지 않는다. 새 방향의 자체 실험 근거가 없어 사용자 논문 추천은 계속 보류한다.

## 다음 확인의 종료 조건

다음 라운드는 지원 주석을 다시 광범위하게 검색하지 않는다. 시간·역할 후보의 실제 자료 경로, 유효한 정답 변환, 가까운 선행 평가의 범위만 확인한다. 확보되면 단계별 GPU diagnostic을 작성한다. 영상 접근에 사용자만 제공할 수 있는 승인·경로가 필요하면 그 구체적 항목을 묻는다. 자료와 정답 관계를 확보하지 못한 상태에서 구현 성공을 목표로 하는 준비 반복을 만들지 않는다.

## 대규모 GPU 필요 후보

시각적 변화와 시간 역할을 함께 학습하는 vision encoder–언어 모델 공동 post-training, 일반 능력 보존을 포함한 혼합 학습을 후보로 남긴다. 현재는 그 필요성을 입증하지 못했다. 정상 사용 진단과 모듈형 비교 이후에도 중요한 잔여 오류가 확인될 때 LoRA·adapter와 함께 검토한다.

## 다음에 파고들 질문
- TemMed-Bench의 원천 CheXpert Plus에서 현재 공식 접근 절차와 필요한 파일의 제공 단위를 확인할 수 있는가? 기존 프로젝트 자료로 연결 가능한 범위와 사용자에게 승인·로컬 경로를 물어야 하는 범위를 구분하라.
- 시간 방향 대조에서 report의 실제 비교 기준이 확보되고, 증가·감소·안정·부정 문장을 구분해 정답 변환을 보장할 최소 하위 과제는 무엇인가? 제시 순서 변경과 비교 방향 변경을 혼동하지 않는 평가 및 모듈형 baseline을 확정할 수 있는가?
- TemMed-Bench와 가까운 temporal 평가가 이미 방향 반전·역할 재배열 대조를 어디까지 수행했는가? 접근 가능한 MedMultiBench의 특정 하위 과제가 이를 더 명확히 검증할 자료를 제공하는지 확인하고, 둘 다 자료 연결이 불충분하면 후보 보류 또는 구체적인 사용자 확인으로 결론 낼 수 있는가?
