"""
모델 패키지 - API 스키마 정의

사용 예시:
    from app.models import ConsultationRequest, ConsultationResponse
"""

from app.models.schemas import (
    DocumentInfo,
    HealthStatus,
    ConsultationRequest,
    ConsultationResponse,
    ExpertSearchRequest,
    ExpertSearchResponse,
    ErrorResponse,
    QueueStatusResponse
)

__all__ = [
    "DocumentInfo",
    "HealthStatus",
    "ConsultationRequest",
    "ConsultationResponse",
    "ExpertSearchRequest",
    "ExpertSearchResponse",
    "ErrorResponse",
    "QueueStatusResponse"
]
