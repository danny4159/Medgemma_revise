# MedGemma 1.5-4B-IT 서버 세팅

## 환경
- conda env: `medgemma` (python 3.11, `/home/test/.conda/envs/medgemma`)
  - `conda activate medgemma`
  - user-site(`~/.local`) 패키지와 격리되도록 `PYTHONNOUSERSITE=1`을 활성화 시 자동 설정함
- 주요 패키지: torch 2.5.1+cu121, transformers>=4.50, accelerate, huggingface_hub, pillow

## 모델
- HF repo: `google/medgemma-1.5-4b-it` (gated, 라이선스 동의 필요)
- 캐시 위치: `hf_cache/` (이 폴더 내부, `HF_HOME`으로 지정)
- 로그인: `huggingface_hub.login()`으로 계정(danny4159) 토큰 등록 완료
  (토큰은 `~/.cache/huggingface/token`에 저장됨. 새 셸에서 캐시 디렉토리를
  바꿔 쓸 경우 `token=` 인자로 명시적으로 넘겨야 함)

## 실행
```bash
conda activate medgemma
export HF_HOME=/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache
python run_medgemma.py
```

`run_medgemma.py`는 예시 흉부 X-ray 이미지를 다운받아 모델에게 설명을 요청하는
간단한 스모크 테스트입니다. 실제 사용 시 `pipeline(...)` 호출 부분을 필요한
이미지/프롬프트로 바꿔 쓰면 됩니다.

## 참고
- 모델 크기: 약 4B 파라미터, bf16 기준 GPU 메모리 약 8~10GB 필요
- 서버 GPU: RTX 3090 24GB x2 (인덱스 0, 1) — 충분히 여유 있음
