# iter_007 코드 복구 기록

iter_008 브랜치 `approach/anatomy-lesion-transfer`에서 필요한 이전 소스가 없던 문제를 보완했다.
원본 stash는 유지하고, `refs/research-archive/before-iter-008-b8dcd48d43f9`로 고정했다.
출처: `b8dcd48d43f9d0f35ef7322a01ca16e054794eb9^3` (미추적 파일 tree).

복구한 파일:

- `extract_pooling_features_iter007.py`
- `fetch_nih_official_iter007.py`
- `gate_pooling_probe_iter007.py`
- `notes/pooling_probe_iter007.md`
- `pooling_probe/__init__.py`
- `pooling_probe/evaluate.py`
- `pooling_probe/features.py`
- `pooling_probe/gate.py`
- `pooling_probe/probe.py`
- `run_pooling_probe_iter007.py`
- `test_pooling_probe_iter007.py`

이 복구는 원본 보존이며 재사용 승인이나 결함 수정 완료가 아니다.
`iter_007/review.md`의 완료 판정, 현재 입력과 cache provenance 연결, GPU 가시성 덮어쓰기
문제는 재사용 전에 수정·검증해야 한다. 기존 결과 파일과 가설 판정은 변경하지 않았다.
원본의 임의 45 device-minute 상한은 현재 RESOURCE_POLICY에 맞게 재검토한다.
수정된 연구 코드의 검증·커밋은 재개된 구현·리뷰 단계에서 수행한다.
