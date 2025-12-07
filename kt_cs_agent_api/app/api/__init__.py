"""
API 라우터 패키지

이 패키지는 모든 FastAPI 라우터를 포함합니다.

라우터 목록:
    - health_router: 헬스 체크 (/health)
    - consultation_router: 신입 상담원용 (/consultation)
    - expert_router: 전문가용 (/expert)
    - comparison_router: 비교용 API (/comparison)

사용 예시:
    from app.api import health_router, consultation_router, expert_router, comparison_router

    app.include_router(health_router)
    app.include_router(consultation_router)
    app.include_router(expert_router)
    app.include_router(comparison_router)
"""

from app.api.health import router as health_router
from app.api.consultation import router as consultation_router
from app.api.expert import router as expert_router
from app.api.comparison import router as comparison_router

__all__ = [
    "health_router",
    "consultation_router",
    "expert_router",
    "comparison_router"
]
