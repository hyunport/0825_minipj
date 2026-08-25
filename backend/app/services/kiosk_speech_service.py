"""로컬 faster-whisper 음성 인식 Service 뼈대 — 인혜님 담당.

모델은 요청마다 생성하지 말고 최초 요청 시 한 번 지연 로드합니다. STT 실패가 텍스트
주문 Endpoint까지 막지 않게 분리합니다.
"""


# TODO(inhye): 10MB 이하 WAV 검증과 faster-whisper tiny 한국어 변환 구현
