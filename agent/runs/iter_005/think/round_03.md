# 사고 라운드 3

### 1. EasyLens와의 중복 및 남은 차이
- EasyLens v3는 MedGemma1.5를 기본 backbone으로 사용한다. Appendix B·C의 실제 적용 위치는 **first vision layer, injection layer=1**이다. 따라서 이를 MedGemma projector 직전의 pooling 보정 방법으로 특정했던 해석은 수정해야 한다.
- EasyBank 구축에는 병변 mask supervision이 들어간다. 정상 reference는 병변 mask 밖의 동일 patch 위치에서 구축하므로, 수동 organ annotation을 이용한 anatomy transfer와는 다르다. 다만 정상 anatomy 대비 병변 residual 증폭이라는 큰 아이디어는 이미 겹친다.
- 본문·부록에서 prototype 구축 집단, calibration 집단, 평가 집단의 명시적 patient-disjoint 목록이나 분할 비율을 확인하지 못했다. 이것은 leakage가 있다는 증거가 아니라 재현에 필요한 미확인 사항이다. 공개 코드 링크는 있으나 이번 도구에서는 본문 접근에 실패했다.
- subtle-lesion의 Gen. 점수는 완성된 보고서 정확도가 아니라 첫 3 decoding steps의 병변 관련 token probability probe다. 후속 연구에서는 localization, 완결된 답변, false-positive 변화를 구분해야 한다. [EasyLens v3](https://arxiv.org/html/2606.06379v3)
- **판단:** anatomy supervision 추가나 feature 증폭 자체의 novelty는 부족하다. pooling에 의해 어떤 정보가 접근 불가능해지는지 통제된 probe로 확인하는 것은 가능하지만, 그 분석만으로 논문 contribution이 성립하지는 않는다.

### 2. 데이터 연결: 구체적 경로는 좁혔지만 독립 집단 확보는 미완료
- SCR 원저자 배포에는 `jpg.zip` 7.8 MB, `masks.zip` 4.0 MB가 있다. 이번에도 archive 내부 파일명·영상 해상도·JSRT nodule metadata와의 대응은 확인하지 못했다. 작은 파일 크기만으로 고해상도 병변 평가가 가능하다고 판단하면 안 된다. [SCR 배포](https://zenodo.org/records/7056076)
- NIH 공식 연계 Google Cloud 경로는 `gs://gcs-public-data--healthcare-nih-chest-xray/png/FILENAME.png`이다. **Requester Pays**이므로 인증·결제 설정 없이 무료 개별 다운로드가 가능하다고 가정하지 않는다. NIH Box 원본 배포는 이번 웹 도구에서 열리지 않았다. [Google Cloud 공식 안내](https://docs.cloud.google.com/healthcare-api/docs/resources/public-datasets/nih-chest)
- CheXmask 공식 schema는 원본 image ID, `Left Lung`, `Right Lung`, `Heart` RLE, `Height`, `Width`, RCA scores다. 원본 영상과 patient metadata는 포함하지 않는다. NIH용 mask는 1024×1024이며, anatomy 평가의 수동 GT가 아니라 보조 pseudo-label이다. [CheXmask 공식 배포](https://www.physionet.org/content/chexmask-cxr-segmentation-data/1.0.0/)
- 로컬 `hf_cache/hub/datasets--alkzar90--NIH-Chest-X-ray-dataset/blobs/dc1a62a4da91842b8b4b30c817f0a4eac3e728cf`를 읽었다. loader에는 `data/Data_Entry_2017_v2020.csv`, `data/BBox_List_2017.csv` 및 12개 영상 zip의 미러 경로가 있다. 그러나 실제 `_generate_examples()`는 classification만 구현하고, `_split_generators()`는 전체 영상 archive를 다운로드한다. 선언된 object-detection schema만 보고 바로 사용할 수 있다고 판단하면 안 된다.
- 따라서 NIH 후보의 필요한 join은 `bbox image ID → metadata의 patient ID → PNG → CheXmask image ID`다. 원본 CSV header와 실제 join 성공률은 아직 검증하지 못했다. 현재 확보된 근거로는 작은 다운로드만으로 충분한 독립 평가 집단이 준비됐다고 답할 수 없다.

### 3. pooling probe 설계의 중요한 수정
- 설치된 `transformers/models/gemma3/modeling_gemma3.py:662–696,790`을 다시 읽었다. `vision_tower.last_hidden_state`에 4×4 average pooling, RMSNorm, projection을 차례로 적용한다. 이전 라운드의 64×64×1152 → 16×16×1152 구조와 일치한다.
- **수학적 확인:** 위치별 affine head `h(z)=Wz+b`와 average pooling `P`는 `P(h(Z))=h(P(Z))`를 만족한다. 같은 coarse grid에서 선형 head와 pooling의 순서만 바꾸는 비교는 정보 손실을 검증하지 못한다. 차이가 나면 normalization, loss, 최적화 또는 구현 차이부터 의심해야 한다.
- 유효한 최소 비교는 `Z`와 `U(P(Z))`를 동일 64×64 grid에서 같은 pointwise head·동일 label·loss·학습 영상으로 비교하는 것이다. `U`는 고정 nearest upsampling이다. 다만 fine-grid 개선만 있으면 subcell 위치 정보의 이득일 수 있으므로, 두 결과를 동일 16×16 grid에서도 평가해야 한다.
- 비선형 head는 동일 구조·용량·학습 예산으로 비교하고, linear control과 분리한다. RMSNorm·projection은 별도 단계로 두어 pooling 효과와 섞지 않는다. 위치 prior와 image-swap control도 필요하다.
- **판단:** anatomy 보조 학습보다 이 제한된 표현 분석을 먼저 검토한다. 단, probe 성능 차이는 해당 readout에서의 접근 가능성 차이이며, 곧바로 LLM의 인과적 병목이나 진단 개선 가능성을 증명하지 않는다.

### 4. 공식 좌표 예제와 요청 예산
- 이번 검색에서도 MedGemma 1.5 전용으로 좌표 순서·scale을 명시한 공식 localization 예제를 확보하지 못했다. 검색된 Gemini 문서는 근거로 대체하지 않는다.
- `legacy/scripts/04_official_format/rerun_localization_official.py`는 형식을 probing으로 발견했다고 명시하며, parser는 scale 자동 전환과 역전 좌표 정렬을 수행한다. 따라서 로컬 detection prompt라는 명칭이 정확하다.
- bbox 생성 비교가 필요하면 `Where is the {object}?`와 기존 detection prompt를 고정하고, 독립 수동 anatomy calibration에서 좌표 convention을 정한 뒤 평가 집단에서는 변경하지 않는다. 원시 parse 성공, 보정 후 성공, 잘림을 별도로 보고하고 parse 실패를 주평가에서 제외하지 않는다.
- 예산 초안은 calibration 8영상×3기관×2prompt=48요청, 평가 24영상×4target×2prompt=192요청으로 총 240요청 이하이다. 이는 시간 보장이 아니다. 구현 시 calibration 초반의 실측 시간으로 45 device-min 이내 여부를 판단하고, 초과 예상이면 평가 전에 표본 수를 고정 축소한다. feature probe만 수행한다면 이 생성 비교는 이번 실행에 포함하지 않는다.

이번 라운드에서는 기록·코드 읽기와 웹 조사만 수행했다. 파일 생성·수정·실험 실행은 하지 않았다.

## 다음에 파고들 질문
- NIH bbox·patient CSV와 개별 PNG를 결제 설정·대용량 전체 다운로드 없이 확보할 수 있는 경로가 있는가? 원본 provenance를 추적할 수 있는 미러에서 실제 header와 영상 ID 대응까지 확인할 수 있는가?
- NIH 경로가 불가능하면 SCR archive의 실제 해상도·파일명과 JSRT nodule metadata를 확인할 수 있는가? 병변 annotation이 연결되지 않으면 이번 반복을 GPU 없는 데이터 준비·검증 구현으로 제한할 것인가?
- 확인된 annotation이 bbox인지 mask인지에 맞춰, pooling probe의 fine/coarse target·표본 수·patient split·효과크기 기준을 어떻게 고정할 것인가? 선형 교환법칙과 비선형 readout 차이를 구분하는 최소 비교를 45 device-min 안에 구성할 수 있는가?
