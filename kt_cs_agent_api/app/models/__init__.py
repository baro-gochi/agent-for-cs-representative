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
    ErrorResponse,
    QueueStatusResponse,
    # JSON 구조화된 가이드 모델
    GuideSection,
    StructuredResponseGuide,
    KeywordGuideItem,
    StructuredKeywordGuide,
    # 비교용 API 모델
    ComparisonRequest,
    KeywordGuideResponse,
    DirectFullGuideResponse
)

__all__ = [
    "DocumentInfo",
    "HealthStatus",
    "ConsultationRequest",
    "ConsultationResponse",
    "ErrorResponse",
    "QueueStatusResponse",
    # JSON 구조화된 가이드 모델
    "GuideSection",
    "StructuredResponseGuide",
    "KeywordGuideItem",
    "StructuredKeywordGuide",
    # 비교용 API 모델
    "ComparisonRequest",
    "KeywordGuideResponse",
    "DirectFullGuideResponse"
]
