"""
KT 상담원 AI Agent API 패키지

이 패키지는 FastAPI 기반의 상담원 지원 AI 서비스입니다.

패키지 구조:
    app/
    ├── config/       # 환경 변수 및 설정
    ├── database/     # 벡터 DB 및 문서 레지스트리
    ├── agent/        # LangGraph 에이전트 로직
    ├── api/          # FastAPI 라우터
    ├── models/       # Pydantic 스키마
    ├── utils/        # 유틸리티 (로깅, 대기열 등)
    └── main.py       # 애플리케이션 진입점

사용 예시:
    # 서버 실행
    uvicorn app.main:app --reload
"""

__version__ = "1.0.0"
