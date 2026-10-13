"""main protocol 잠금: i136_lock.main을 쓰되 technical 출력 후 추가된 gate 재계산 코드(i136_gate.py)와 이 파일을 code 잠금에 포함한다."""
import i136_lock as L
L.CODE = L.CODE + ['i136_gate.py', 'i136_lock_main.py']
L.main('main')
