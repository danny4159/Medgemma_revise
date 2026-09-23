"""iter_005: grounding 데이터 준비·검증 (CPU 전용, GPU 0).

- net: 예산이 있는 다운로드 ledger와 HTTP Range 기반 seekable file
- nih: NIH ChestX-ray14 bbox·patient metadata 파싱, split, ZIP member 확보
- scr: SCR(JSRT 영상 기반) 수동 anatomy mask archive 검사
- targets: 64x64 / 16x16 occupancy target과 affine pooling 교환법칙 검증
"""
