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
    QueueStatusResponse,
    # 신규 비교용 API 모델
    ComparisonRequest,
    DirectSearchResponse,
    KeywordGuideResponse,
    DirectFullGuideResponse
)

__all__ = [
    "DocumentInfo",
    "HealthStatus",
    "ConsultationRequest",
    "ConsultationResponse",
    "ExpertSearchRequest",
    "ExpertSearchResponse",
    "ErrorResponse",
    "QueueStatusResponse",
    # 신규 비교용 API 모델
    "ComparisonRequest",
    "DirectSearchResponse",
    "KeywordGuideResponse",
    "DirectFullGuideResponse"
]
