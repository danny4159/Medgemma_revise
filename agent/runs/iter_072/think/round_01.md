# 사고 라운드 1

## 핵심 결정

**기존 세부 설계는 재개하지 않는다. 다음 검토는 질문이 지정한 MRI 부위의 실제 중증도 판정 하나로 좁힌다.** 아직 실행 계획을 확정할 자료·대조 연결이 부족하므로 이번에는 구현을 발주하지 않는다. 최종 GOAL과 MRI 우선순위는 유지한다.

## 원문에서 확인한 사실과 투자 판단

`agent/GOAL.md`, iter_071 plan/review, iter_014·037·042·048·061·062·064·069 리뷰, iter_071 think/round_01·02, `agent/LIMITATIONS.md` 관련 항목과 iter_037·048·064·071 review.json의 code_assets를 확인했다.

- **iter_071:** E24 F1@0.5는 직접 SFT D8 0.1577, source 초기화 R8 0.1295, detector 0.8175다. 현재 두-category 위치 과제에는 충분한 대안이 있다. T24·추가 seed·다른 source로 자동 확대하지 않는다. 실제 생성과 학습은 유효했지만 MRI 전반의 학습 실패를 뜻하지 않는다.
- **iter_064:** MedGemma의 복제 대비 다른 slice 추가 손실은 0.2708 BA로 보존한다. Qwen에는 같은 손실이 없고 명시적 target은 routing으로 분리할 수 있다. 이 관찰을 근거로 context 안정화 loss를 바로 개발하지 않는다.
- **iter_048:** 공동 직접 SFT는 공동 F1을 0.3331→0.5233으로 회복했다. 그러나 적응 MedGrounder 0.5944와 비용 대조 이후 추가 방법의 투자 근거는 약했다. 남은 0.0672 손실만으로 재개하지 않는다.
- **iter_042:** presence gate는 음성 오출력을 크게 줄였으며 C_neutral 대비 P0 gate의 양성 환자별 F1은 같았다. 넓은 CI를 단순 대안의 실패로 해석해 negative SFT나 새 보존 loss를 발주하지 않는다.
- **iter_037:** RSNA의 위치 정밀도·검출 범위 trade-off는 남는다. 하지만 detector threshold를 낮추면 SFT-only GT 대부분이 회복되고 FP가 증가한다. 이것만으로 새로운 후보 발견 능력이나 fusion 방법의 필요성을 입증하지 않는다.
- **iter_014:** 기존 GIoU 가중 후보의 음성 결과와 비용을 유지한다. 이번에 다른 이름의 기하 loss를 제안할 새 실험 근거는 확보하지 못했다.

## Strategy Check / 연구 방향 판단

**상위 질문:** 질문에 필요한 영상 근거를 선택하고 사용해 올바른 답변을 만드는가.

**해결된 부분:** 현재 anatomy 위치 출력에는 detector가 강하고, 명시적 영상 index에는 routing이 있으며, 공동 출력 저하의 상당 부분은 직접 형식 학습으로 회복된다.

**남은 설명:** 이 결과들은 영역 내부의 질환·중증도 판독을 직접 평가하지 않았다. 반대로 기존 MRI 신호·Modic 진단의 약한 frozen 결과도 충분한 supervision을 사용하는 부위별 판독의 가능성을 기각하지 않는다.

**세 선택의 비교:**

1. 기존 방법 개선은 단순 대안 이후의 가치가 약해 보류한다.
2. 기존 context 원인을 추가 분해하는 진단은 현재 투자 결정을 바꿀 가능성이 낮아 보류한다.
3. 실제 임상 등급이 있는 부위별 판독으로 최소 비교를 옮기는 선택을 한정 검토한다. 위치 정확도만 높이면 끝나는 과제인지, 위치 지원 이후에도 판독 문제가 남는지 구분할 수 있어야 한다.

이는 새 dataset이 있다는 이유의 전환이 아니다. detector의 위치 성공을 실제 판독 성공과 구분하는 것이 선택 이유다. 다중 slice를 사용하더라도 정답 근거 없이 결합 능력이라고 부르지 않는다. 단순 분류기가 충분하면 해당 범위의 VLM 방법 투자도 보류할 수 있다.

기존 반복에서는 생성보다 준비·검증이 상당한 부담이었던 사례가 있다. 다만 전체 누적 비용 비중은 계측되지 않았으므로 절감률을 만들지 않는다. 다음은 후보 하나의 자료·대조 적합성만 확인한다.

## 새 문헌 확인: 바로 방법을 발주하지 않는 이유

[RefineRank 원문](https://arxiv.org/html/2608.23928v1)은 frozen 의료 VLM의 언어·영역 feature와 detector proposal을 결합해 box 보정과 순위를 학습한다. 따라서 'VLM의 의미와 detector의 위치를 결합한다'는 일반 설명은 이미 가까운 선행과 겹친다. 수술 영상 결과를 RSNA 또는 MRI에서의 충분성으로 일반화하지는 않지만, 단순 결합을 새 기여로 부를 수 없다는 판단에는 관련된다. 이번에는 해당 모델이나 코드를 확보하지 않았다.

## 확인 후 보류한 후보: MRI 고유 병변 counting

[SGMRI-VQA 논문](https://arxiv.org/html/2604.15808v1)은 적응 모델의 volume Detection/Classification/Counting A-Score를 99.18/97.70/37.77로 보고한다. 이는 저자 보고이며 우리 실험이 아니다. 서로 다른 문항과 채점 방식의 수치이므로 충분한 인식 이후 결합 실패의 증거로 사용할 수 없다.

원래 검토한 실패 조건은 여러 slice에 반복된 동일 병변을 중복 계산하는 문제였다. 그러나 [공식 brain QA 생성 코드](https://raw.githubusercontent.com/lamawmouk/SGMRI-VQA/main/scripts/generation/generate_qa_gpt4o_brain.py)의 `create_volume_prompt`는 slice별 box를 모은 뒤 `total_lesions = len(all_bboxes)`로 계산한다. 이것은 고유 3D 병변 수를 보장하지 않는다. [정제 코드](https://raw.githubusercontent.com/lamawmouk/SGMRI-VQA/main/scripts/cleaning/clean_brain_qa.py)에도 box 나열과 finding category 수에 관한 처리가 함께 있다.

따라서 현재 공개 counting 점수를 고유 병변 중복 제거의 정답으로 채택하지 않는다. 전체 배포 문항이 틀렸다고 판정한 것은 아니다. 새 instance annotation을 대규모로 만들거나 counting 모델을 먼저 실행하지 않는다.

[공식 배포 페이지](https://huggingface.co/datasets/SpatialGroundingVQA/SGMRI-VQA)는 image/volume JSON의 schema 차이로 viewer 오류를 보이며, 기반 fastMRI 이용조건 준수를 명시한다. viewer 오류는 자료 부재가 아니다. 이번에 원본 영상·전체 QA·checkpoint를 다운로드하거나 공식 test를 평가하지 않았다.

## 다음 한정 검토: 실제 부위별 임상 등급

[3DReasonKnee 원논문](https://psb.stanford.edu/psb-online/proceedings/psb26/sambara.pdf)은 OAI DESS MRI와 부위별 MOAKS 등급을 연결한다. 영역 주석은 일부 수동 segmentation에서 학습한 nnU-Net으로 확장됐으므로 모든 box를 수동 병변 정답으로 부를 수 없다. reasoning도 전문가가 구성한 유형별 절차와 실제 환자별 관찰을 구분해야 한다.

[공식 배포 설명](https://huggingface.co/datasets/rajpurkarlab/3DReasonKnee)에서 질문·영역·등급 연결 예시와 환자/시점 정보를 담는 split 파일 구조를 확인했다. 영상은 OAI에서 별도로 확보하는 경로이며 NDA 계정이 필요하다고 명시한다. 현재 프로젝트의 접근 권한이나 실제 영상 확보 여부는 확인하지 않았다. 공개 annotation의 접근성을 원본 영상 사용 승인으로 해석하지 않는다.

다음 검토의 질문은 이 자료 전체 benchmark를 만들 수 있는지가 아니다. **질문이 지정한 부위의 임상 등급 한 종류에 대해, 위치 지원과 내용 판독을 구분하는 공정한 학습·출력 비교를 만들 수 있는가**다. grade를 box 크기나 생성 reasoning에서 역산하는 과제라면 채택하지 않는다. grade의 관측 범위와 필요한 slice를 임의로 줄이지 않는다.

## 재사용과 실행 경계

현재 research 작업 트리는 clean이다. iter_071의 parser/matching 승인은 제한된 범위이며 학습 CE 검사, 재개, GPU 여유, 출력 provenance에 needs_fix가 남는다. iter_064·048·037도 전체 스냅샷 승인이 아니다. 현재는 실행 경로를 선택하지 않았으므로 코드 반입·전면 정비를 발주하지 않는다. `reuse_assets=[]`는 기존 자산이 없다는 뜻이 아니다.

새 후보에 연결할 observed MRI 판독 한계는 아직 없다. `mri-explicit-target-context-effect`는 기존 관찰의 계보를 유지하기 위한 연결이며 새 과제의 method gate가 아니다. 후보가 성립해도 첫 실행 역할은 diagnostic이다.

## 다음 확인과 종료점

공식 schema·split·영상 접근과 부위별 임상 판독 baseline을 확인해 실행 또는 보류를 결정한다. 자료 접근이 성립하더라도 단순히 학습 가능한 과제라는 이유로 투자하지 않는다. 실제 출력 결과가 다음 방법 투자 여부를 바꾸는 대조와 종료 행동이 필요하다.

이번 조사 문헌은 사용자 논문 추천으로 등록하지 않는다. 새로운 방법 방향의 유효한 실험 근거를 아직 얻지 못했다.

## 대규모 GPU 필요 후보

다기관 MRI에서 영역 선택과 임상 판독을 함께 학습하는 vision encoder–connector–language 공동 적응은 장기 후보로 남긴다. 현재 자료 검토나 frozen 실패만으로 그 필요성·효과를 주장하지 않는다.

## 다음에 파고들 질문
- 3DReasonKnee의 공식 question/grade mapping과 생성 코드를 보면, 실제 OAI 임상 등급에 직접 연결되며 box·reasoning 문구만으로 답을 얻을 수 없는 부위별 판독 과제 하나를 정의할 수 있는가? 성립하면 그 과제만 채택하고, 성립하지 않으면 후보를 보류한다.
- 공식 split의 patient_id·시점·좌우 무릎을 기준으로 환자 분리가 가능한가? 프로젝트에 OAI 원본 영상의 유효한 접근 경로가 있는지, 없다면 필요한 권한이 정확히 무엇인지 확인할 수 있는가?
- 동일 영상·등급 supervision의 직접 SFT와 영역 추출+분류기, oracle 영역 지원을 어떻게 비교해야 선택 오류와 내용 판독 부족을 구분할 수 있는가? 원 논문의 실행 경로와 가장 가까운 부위별 MOAKS 판독 baseline을 근거로 최소 실험·실측 예산·결과별 종료 조건을 정할 수 있는가?
