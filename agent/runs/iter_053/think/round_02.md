# 사고 라운드 2

## 이번 결론

외부 교정 benchmark를 이용한 iter_047 재개는 보류한다. 공개 파일의 존재와 실제 교정·보존 평가 가능성은 달랐다. 이는 교정 능력이나 연구 가치의 기각이 아니라, 확인한 자료·비교군 경로로 즉시 구현을 발주할 근거가 부족하다는 판단이다.

이번에는 기존 CheXpert 자산이라는 구체적 대안도 확인했다. 따라서 '교정 정답 자료가 전혀 없다'고 결론내리지 않는다. 다만 이 자산의 사용 여부는 직접 판독 오류와 편집 한계의 구분, 보존된 평가 집단의 용도 변경, 기존 선행 이후의 정보 가치를 함께 판단해야 한다.

## 직전 질문에 대한 답

### 1. phrase-grounded fact-checking/APO를 바로 실행할 수 있는가?

공식 논문과 저자 페이지를 확인했지만 재현 가능한 checkpoint·추론 코드의 전체 경로는 확인하지 못했다. FC는 영상과 자유형 보고서를 곧바로 비교하는 단일 모델이 아니라, 소견을 FFL 형식으로 추출하고 해부구조 위치를 연결하는 전처리를 포함한다. polarity 반전·위치 변경·소견 대체도 이미 학습 자료 구성에 사용한다. [FC 원문](https://arxiv.org/html/2509.21356v1)

저자 공식 페이지에서 실제 공개 자료인 RadCheck 링크를 찾았다. 공개 card는 Chest ImaGenome/MIMIC-CXR 영상에 대한 참조, 원 소견과 합성 real/fake 조합, 기존 환자 split을 설명한다. 영상 자체가 즉시 확보된 자산은 아니다. card의 license 항목도 미기재 상태다. [저자 페이지](https://www.tsyedamahmood.org/), [RadCheck 공식 자료](https://huggingface.co/datasets/razi-mahmood/RadCheck)

저자 Hugging Face 계정에는 공개 models가 0개로 표시됐다. 이것은 해당 계정의 확인 결과이며 다른 곳에도 checkpoint가 없다는 증명은 아니다. [저자 계정](https://huggingface.co/razi-mahmood)

APO 공식 PDF 직접 열기는 실패했다. 공식 CVF 검색 결과에서 FC를 고정한 채 교정 LLM과 정렬을 수행하고, FC 학습 자료가 Chest ImaGenome Silver/MIMIC-CXR에서 유래한다는 부분을 확인했다. PDF 전체나 부록을 읽었다고 주장하지 않는다. [APO 공식 논문](https://openaccess.thecvf.com/content/CVPR2026/papers/Mahmood_Phrase-grounded_APO_for_Improving_Chest_X-ray_Report_Generation_CVPR_2026_paper.pdf)

결론은 '미설치라 제외'가 아니다. 현재 확인하지 못한 것은 사용할 정확한 checkpoint·전처리·원천 영상 연결이다. 이를 확보하지 않은 상태에서 논문의 성능을 재현된 강한 비교군으로 계산할 수 없다.

### 2. MedHEval의 비MIMIC 자료에 필요한 정답이 있는가?

논문은 SLAKE/VQA-RAD 기반 MM-VisHal을 494영상·3,610 VQA, IU-Xray/MIMIC-CXR 기반 CXR-VisHal을 790영상·5,587 VQA로 설명한다. 이 수치는 논문 전체 구성이지 비MIMIC 교정 평가의 적격 표본 수가 아니다. 구성은 기존 QA·metadata 또는 보고서에서 생성한 질문과 답변이며, 오류가 섞인 초안에서 수정 대상과 보존 대상을 함께 표시한 정답이 확보됐다는 근거는 확인하지 못했다. [MedHEval 본문 및 Appendix B](https://arxiv.org/html/2503.02157v1)

공식 저장소는 annotation과 split을 제공하고 영상은 별도로 확보하도록 안내한다. benchmark_data 디렉터리 및 GitHub tree API 조회는 도구 접근 오류가 났고, 로컬 Python 조회는 DNS 실패였다. 따라서 실제 JSON schema와 영상별 적격 수를 검사했다고 보고하지 않는다. 접근 실패를 annotation 부재나 설치 불가능의 증거로 쓰지 않는다. [공식 저장소](https://github.com/Aofei-Chang/MedHEval)

로컬 파일 검색에서는 legacy/eval_samples/used_in_training/slake와 vqa_rad의 각각 10개 JPEG 및 metadata를 확인했다. 이 작은 기존 자산을 전체 benchmark나 독립 평가 집단으로 확대 해석하지 않는다.

### 3. 기존 자산으로 최소 대조를 고정할 수 있는가?

iter_018 원본 review.json과 실제 manifests/sets.json, labels.json, provenance.json을 확인했다. 기존 CheXpert 자료에는 169명의 단일 frontal 영상과 cardiomegaly/pleural_effusion 상태가 연결돼 있다. 네 상태 조합 수는 72/33/36/28명이다. 기존 분할은 D16, E48, F105이며 F의 조합별 수는 56/17/20/12명이다.

iter_018 리뷰는 원본 parquet 234행과 CSV의 label 대응, 169개 영상의 bytes/hash 연결을 검증했다. 따라서 이는 PadChest의 명시적 음성 문장 부족과 다른 자산이다. 다만 이번 라운드에서 전체 파일 hash를 다시 검증한 것은 아니고, 재사용 시 기존 provenance 결함과 중복 검사를 보완해야 한다. 출처: agent/runs/iter_018/review.json 및 research/results/iter_018/manifests/.

중요한 제약도 있다. 기존 E48 직접 답변의 주방향 정확도는 34/48이었다. 이는 새 교정 과제의 정확도가 아니라 기존 질문의 결과지만, 시각 판독 자체가 충분하다고 가정할 수 없다는 근거다. 기존 D16/E48은 개발 자료이며 F105를 새 교정 과제에 사용하는 것은 명시적 용도 변경이다. 이번에 F 출력 생성이나 영상 열람을 하지 않았고, 자동 재배정도 하지 않는다.

그러므로 두 소견 상태의 합성 초안을 구성하는 것은 기술적으로 가능하지만, 그것만으로 중요한 교정 병목이나 새로운 방법의 필요성이 성립하지 않는다. 더 작은 표본으로 iter_047 기준을 통과시키거나 새로운 benchmark 이름을 붙이는 실행은 선택하지 않는다.

## 유지할 판단과 새로 남은 결정

round_01.json 원문을 읽었고 CT E280 보류, iter_048 공동 grounding 추가 투자 보류, iter_050→051 인계 완료 판단을 유지한다. RETRACTION 감사의 무효 항목을 다시 근거로 쓰지 않는다. 현재 구현 담당은 Claude이며 담당 변경 작업을 반복하지 않는다.

외부 교정 자산 확인은 종료한다. 다음 선택은 기존 CheXpert로 제한된 교정 질문을 검증할 것인지, 검증된 직접 SFT·detector 자산으로 학습 효율 또는 일반화 질문을 다시 정할 것인지다. 후자는 아직 선택된 방법이 아니며 iter_008·012·014·035~037의 실제 시도 범위와 경쟁 설명을 확인해야 한다. 기존 자산이 있다는 이유만으로 과거 기각 설계를 되살리지 않는다.

legacy 정리의 맨 앞 중대 정정도 읽었다. 잘못된 좌표 형식과 MedGemma 버전 혼동에서 나온 과거 결론을 새 방향의 근거로 사용하지 않는다.

## 종료와 비용

이번 라운드의 학습·모델 생성·파일 변경은 0이다. 외부 자산 확인 결과만을 저장하기 위한 Claude setup 반복은 발주하지 않는다. 추가 사고는 같은 자료 검색을 계속하기 위해서가 아니라, 이 연구 묶음의 계속과 전환을 결정하기 위한 것이다. 다음 판단에는 원문이 이미 확인된 사실을 재조사하지 않고 남은 투자 선택만 다룬다.

## 대규모 GPU 필요 후보

다기관 전문가 수정 이력으로 verifier와 editor를 공동 학습하는 방향은 장기 후보로 보존한다. 현재 자료·비교군·잔여 문제의 근거가 부족하므로 본격 학습이나 새로운 contribution으로 채택하지 않는다. 이번 문헌은 조사 자료이며 긍정적 로컬 실험에 근거한 사용자 논문 추천은 아니다.

## 다음에 파고들 질문
- 기존 CheXpert D16/E48의 직접 판독 수준과 F105 보존 조건을 고려할 때, 초안 검토가 단순 재판독보다 갖는 고유한 실패 조건을 충분히 구분할 수 있는가? 가능하다면 필요한 표본·최소 대조·종료 행동을 고정하고, 불가능하면 교정 후보 전체의 현재 투자를 보류한다.
- iter_008·012·014·035~037의 원 계획·리뷰를 대조하면, 직접 SFT와 detector 비교 이후에도 남는 학습 효율 또는 일반화 질문은 무엇인가? 과거 GIoU 설계의 기각 범위와 단순 baseline으로 설명된 관찰을 제외하고 판단한다.
- 위 두 경로 중 중요한 능력, 가까운 선행 이후의 정보 가치, 실제 접근 가능한 자료와 두 GPU 비용을 함께 고려할 때 어느 하나에 투자할 것인가? 다음 출력은 선택한 경로의 구체적 실행 계획을 우선하며 자료 확인만을 위한 setup은 만들지 않는다.
