# 사고 라운드 2

## 핵심

전처리와 생성 평가 규칙은 상당 부분 구체화했다. NIH에서는 기존 개발 환자를 제외하고 클래스별 50명씩 총 200명을 확보할 수 있음을 CSV 집계로 확인했다. 다만 공개 CSV와 논문에 기술된 주석 규모가 다르고, 추가 예측 box를 어떻게 해석할지가 남아 있다. 독립 평가 자료와 주평가 지표를 결정하는 데 필요한 조사만 한 라운드 더 진행한다.

이번에는 문서·소스·환경 경로 조회와 기존 CSV의 메모리 내 집계만 했다. 파일 수정·생성, 테스트, 모델 추론은 수행하지 않았다.

## 1. 공식 버전·전처리 질문에 대한 답

공식 notebook의 main 본문은 읽었지만 commit API와 history 조회는 실패했다. 확인하지 못한 SHA를 지정하지 않는다. 구현에서는 내려받은 원문과 SHA256을 실행 전에 보존해 내용을 고정할 수 있다. commit 조회 실패 자체가 추론을 막는 이유는 아니다. 이전 실행 당시 notebook과 동일하다는 주장도 하지 않는다. [공식 notebook](https://github.com/Google-Health/medgemma/blob/main/notebooks/cxr_anatomy_localization_with_hugging_face.ipynb)

원본 예제 영상은 Wikimedia의 2412×1956 PNG다. 웹 문서만으로 원본 PNG의 color type은 확인하지 못했다. notebook에 저장된 RGB 표시는 전처리 후 영상이므로 원본 mode의 증거가 아니다. [원본 영상 설명](https://commons.wikimedia.org/wiki/File:Chest_Xray_PA_3-8-2010.png)

앞 라운드의 dtype 우려는 정적 소스 대조로 더 구체화됐다. notebook은 uint8 변환 뒤 RGBA에서만 float alpha blending을 수행하고, 호출부에서 공통으로 255를 곱한다. 따라서 L/RGB 경로와 RGBA 경로의 수치 처리가 다르다. scikit-image v0.25.2의 rgba2rgb는 흰 배경과 float blending을 사용한다. 이는 소스상 확인이며 현재 모델 실행에서 전처리 오류를 재현한 결과는 아니다. [scikit-image 고정 버전 소스](https://raw.githubusercontent.com/scikit-image/scikit-image/v0.25.2/skimage/color/colorconv.py)

계획 단계 환경의 Python에서 skimage는 발견되지 않았다. 로컬 구현을 읽어 검증했다고 표현할 수 없다. Claude 실행 환경에서도 먼저 확인하고, 패키지를 임의 설치하지 않는다. 필요한 uint8 L/RGB/RGBA 처리는 기존 NumPy/PIL로 명시할 수 있지만, 이를 notebook 원본 실행과 동일하다고 주장하려면 별도 수치 대조가 필요하다.

전처리의 설계 방향은 다음으로 좁혔다.

- uint8 L/RGB의 기존 밝기 값을 보존한다. RGBA는 alpha 범위와 흰 배경 합성을 명시한다.
- 중앙의 검은 square padding과 홀수 여백 배분을 고정한다. 원본→padding→processor 변환을 기록한다.
- 원본 예제 경로와 안전하게 일반화한 경로가 달라지면 차이를 보고한다. 모델 점수로 전처리를 선택하지 않는다.
- y-first 0–1000 출력은 padding된 영상 좌표로 해석하고 원본 좌표로 역변환한다. 비정사각형·경계·홀수 padding fixture로 검증할 수 있다.

## 2. NIH 좌표와 대체 자료 질문에 대한 답

`research/grounding_data/coord_evidence.py`를 읽어 과거 근거와 대조했다. 논문의 1024 영상 크기 및 GT 비교 문맥은 이미 iter_006에서 확보한 근거다. 이번 웹 조회를 새로운 좌표 증명으로 세지 않는다. `documented_direct`의 근거는 여전히 없으며 기존 readiness=false와 canvas=assumed 기록을 유지한다.

추가로 확인한 공식 FAQ Q03은 저자가 해당 framework의 코드·학습 모델을 공개할 계획이 없다고 설명한다. 저장된 공식 목록에는 CSV와 영상 폴더는 있지만 원논문이 설명한 개별 annotation XML은 보이지 않았다. 따라서 저자 평가 코드를 찾으면 해결될 것이라는 가정으로 검색을 계속하지 않는다. 출처: `research/results/iter_007/official/FAQ_CHESTXRAY_p01.txt`, `research/results/iter_006/coord_evidence/nih_box_official_page.html`.

평가 설계에 영향을 주는 차이도 확인했다. 논문은 983영상·1600개 병변 주석과 질병 질의에 대응하는 개별 instance의 annotation 절차를 설명한다. 현재 공식 CSV는 앞선 기록상 984개 box다. 이번 집계에서는 기존 160명을 제외한 네 클래스의 407개 image–class 쌍이 모두 box 한 개씩이었다. 이 차이의 원인을 공식 LOG에서 확인하지 못했다. 공개 CSV를 논문의 모든 instance 주석과 동등하거나 완전한 병변 목록이라고 가정할 수 없다. [원논문 §2.4](https://arxiv.org/pdf/1705.02315v5), `research/results/iter_007/official/LOG_CHESTXRAY_p01.txt`.

이것이 NIH를 사용할 수 없다는 뜻은 아니다. 다만 여러 box를 출력한 모델의 추가 box를 모두 임상적 오탐으로 해석하거나, 특정 주석 box와의 불일치를 곧바로 위치 인식 부재로 해석하면 안 된다.

대체 자료는 두 가지로 좁혔다.

- VinDr-CXR는 명시적인 xyxy schema와 test의 다중 판독자 합의 주석을 제공한다. 그러나 공식 자료는 credentialed access이고, 기존 로컬 10영상은 HF 미러에서 가져온 개발 자료다. 미러가 있다는 사실만으로 공식 접근 권한이나 원본 전처리 정합성이 확인되지는 않는다. 이번 확인만으로 새 독립 평가 자료로 채택하지 않는다. [공식 VinDr-CXR](https://physionet.org/content/vindr-cxr/1.0.0/), `legacy/scripts/01_data/download_vindr_cxr_samples.py`.
- RSNA Pneumonia Detection 자료는 폐렴 가능성이 있는 pulmonary opacity를 전문 판독자가 다시 주석한 후보다. 임상적 pneumonia 확진과 같은 target이 아니다. 원천 영상이 NIH이므로 외부 데이터셋 일반화라고 부를 수 없고, 기존 NIH 환자·영상과의 대응 및 중복 검사가 필요하다. 공식 배포의 접근 조건과 부분 확보 가능성은 다음 라운드에서 확인한다. [RSNA 원저자 논문](https://pubs.rsna.org/doi/10.1148/ryai.2019180041), [공식 challenge 데이터 설명](https://www.kaggle.com/competitions/rsna-pneumonia-detection-challenge/data).

## 3. Prompt·parser·다중 box 질문에 대한 답

세 prompt의 역할은 정했다.

1. 공식 긴 prompt는 보존한 notebook의 해당 source cell에서 추출하고 object_name만 치환한다. reasoning 요구와 최종 답 형식을 유지한다.
2. 간결한 명시형은 대상 클래스, box_2d와 label, y-first 순서, 0–1000 범위, padding된 전체 영상 기준, 빈 목록의 의미를 명시한다. 추가적인 해부학적 힌트는 주지 않는다.
3. legacy는 `legacy/scripts/04_official_format/rerun_localization_official.py`의 DETECT 문자열을 그대로 사용한다. 이 문자열은 좌표 순서와 scale을 명시하지 않는다. 따라서 정상 사용의 주조건이 아니라 기존 사용 조건과의 대조다.

기존 자료에서 parser와 template을 검증한 뒤 독립 표본을 열어야 한다. 최종 규칙 후보는 다음과 같다.

- 전체 token ID·원문·입력 길이·생성 길이·종료 사유를 저장한다. 생성된 부분만 파싱한다.
- 알려진 thinking 경계 이후의 Final Answer 영역을 우선한다. marker가 없으면 reasoning 밖의 유일한 완결 JSON 목록만 허용하고 marker 누락을 별도로 센다. 여러 후보 사이에서 GT와 맞는 것을 선택하지 않는다.
- 문법 실패, 모호한 최종 답, label 오류, 비유한 값, 범위 밖 좌표, 뒤집힌 끝점, 미검출, 생성 잘림을 분리한다. scale 추정·끝점 정렬·범위 clipping으로 주평가를 구제하지 않는다.
- 공식 1000-token 실행에서 EOS 없이 cap에 도달한 요청만 2000, 이후 4000으로 연장하는 규칙을 모든 prompt에 동일 적용하는 것이 합리적이다. cap 결과도 보존한다. 최대 길이에서도 끝나지 않은 답은 내용상 위치 오류와 구분한다.
- 다중 box는 one-to-one matching과 unmatched 개수를 기록하고 bbox union IoU도 보조 보고한다. 전체 조합의 최대 IoU 하나만 보고하는 legacy 방식은 주평가에 쓰지 않는다.

남은 결정은 NIH의 주석 범위에 맞춰 추가 box 벌점을 포함한 점수를 주지표로 둘지, 다른 자료에서 이를 평가할지다. 부정확한 주석 완전성 가정으로 metric을 먼저 고정하지 않는다.

## 4. 표본·CI·재사용·GPU 질문에 대한 답

공식 CSV와 기존 manifest를 다시 집계한 결과는 앞선 iter_008 기록과 일치했다. 신규 patient 수는 Atelectasis 121, Effusion 95, Cardiomegaly 84, Pneumonia 74명이며 합집합은 339명이다. 네 클래스의 모든 부분집합에 대해 환자 합집합 크기를 검사했고, 클래스별 50명씩 서로 다른 총 200명을 배정할 수 있음을 확인했다. 아직 환자를 선택하거나 split 파일을 생성하지 않았다.

200개의 독립 patient에서 이항 비율 95% CI의 단순 최악조건 근사 반폭은 약 6.9%p다. 클래스당 50명은 약 13.9%p다. 따라서 전체 오류가 흔한지 판단하기에는 유용하지만 작은 클래스별 차이를 정밀하게 판정하는 규모는 아니다. 주분석에는 patient 단위 paired bootstrap을 사용하고 prompt·box를 독립 표본으로 세지 않는다. 이 계산은 power 보장이 아니다.

NIH를 유지한다면 기존 개발 자료의 32명과 신규 200명에서 patient당 사전 배정한 한 클래스, 세 prompt를 평가하는 696개 기본 생성 요청이 구체적인 규모 후보다. 위치 prior는 기존 train 80명만으로 정한다. 같은 클래스·같은 prompt의 다른 환자 예측을 고정 permutation으로 옮기면 image-swap baseline을 계산할 수 있어 동일한 생성 요청을 다시 실행할 필요가 없다. 부가 클래스는 별도 분석으로 구분한다.

두 GPU에 모델 한 개와 독립 patient shard를 우선 배정한다. 기본 요청당 10–60초라는 미측정 가정을 놓으면 696요청의 추론은 두 GPU에서 약 1–6시간이며, 모델 로딩·길이 연장·검증 시간은 추가된다. 실제 계획은 개발 pilot의 peak memory와 처리량으로 갱신한다. GPU당 약 10–16GB는 초기 추정일 뿐이다. 실측 peak 외에 최소 2GB 여유를 요구하며 임의 시간 상한은 두지 않는다.

현재 HEAD는 `68117cfd08429ffc3cb9b77e14fb1db3221d86ab`이고 tracked diff는 없다. 재사용 최소 범위는 승인본에 있는 `grounding_data/nih.py`, `grounding_data/net.py`, `grounding_data/__init__.py`다. CSV parser·patient 연결·ZIP 부분 조회를 활용할 수 있다. 필요에 따라 `nih_audit.py`의 검사 함수를 사용하되 기존 160명 고정 readiness를 신규 집단에 그대로 적용하지 않는다. 생성 평가에는 pooling feature·head runner와 QES scorer가 필요하지 않다. 이들의 미사용 경로 결함을 이번 실행의 선행 정비로 확대하지 않는다.

`net.py`에는 과거 256MiB·20분 다운로드 기본값이 남아 있다. 새 표본 확보 시 ZIP member의 실제 크기와 전송량으로 값을 정해야 하며, 옛 기본값 때문에 표본을 자동 축소하면 안 된다. Range 응답 검증·CRC·현재 입력 hash·재개 시 provenance 대조는 유지한다. 다른 checkpoint 파일의 선별 반입은 현재 필요하지 않아 reuse_assets는 비워 둔다.

## 유지·보류·다음 판단

최종 목표, 과거 결과, 승인 코드, 기존 개발 환자 160명과 iter_008 보관본은 유지한다. anatomy→lesion 전이 구현은 계속 보류한다. 이번 조사는 실제 출력 diagnostic을 위한 것이며 방법 개발의 우회 명칭이 아니다.

다음 라운드는 NIH의 직접 문장을 다시 찾는 대신 RSNA의 공식 배포·좌표·NIH 대응 가능성을 확인한다. 이 결과로 NIH의 조건부 주석 일치 평가를 사용할지, 더 명확한 annotation 자료로 주평가를 옮길지 결정한다. 추가 자료가 접근 불가라면 이를 분명히 기록하고 NIH에서 주장할 수 있는 범위를 좁힌다. 공식 notebook SHA 조회 실패만을 이유로 조사 라운드를 늘리지는 않는다.

## 대규모 GPU 필요 후보

고해상도 region–text alignment와 vision encoder/projector/decoder 공동 적응, anatomy·lesion·report 공동 학습은 후보로 유지한다. 현재 자료에서는 이러한 학습의 필요성이나 우월성이 검증되지 않았다.

## 다음에 파고들 질문
- RSNA 공식 배포에서 DICOM 크기·bbox 좌표 기준·annotation target을 확정하고 필요한 일부 영상을 기존 권한 안에서 확보할 수 있는가? NIH 원본 patient와 연결할 공개 mapping이 있는가?
- NIH 공개 CSV의 주석 범위를 고려할 때 추가 box 벌점을 포함한 지표가 내용상 grounding 오류를 판정하기에 충분한가? NIH는 주석 일치의 보조 평가로 두고 RSNA를 주평가로 옮기는 편이 더 타당한가?
- 선택한 자료에서 기존 개발 환자와의 독립성, 위치 prior, 오류율과 paired CI를 함께 만족하는 최종 표본·지표·validated 진입 기준을 무엇으로 고정할 것인가?
