"""
===========================================
API 요청/응답 스키마 정의
===========================================

이 모듈은 FastAPI 엔드포인트의 입출력 데이터 모델을 정의합니다.
Pydantic을 사용하여 자동 유효성 검증과 문서화를 제공합니다.

수정 가이드:
    - 새 API 추가 시 해당 요청/응답 모델 정의
    - 필드 변경 시 기존 클라이언트 호환성 고려
    - 예시값(example)을 통해 API 문서 품질 향상

사용 예시:
    from app.models.schemas import ConsultationRequest, ConsultationResponse
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ==========================================
# 공통 모델
# ==========================================

class DocumentInfo(BaseModel):
    """
    검색된 문서 정보
    
    벡터 DB에서 검색된 단일 문서의 메타데이터와 내용을 담습니다.
    """
    source: str = Field(
        ...,
        description="문서 파일 경로/이름",
        json_schema_extra={"example": "인터넷서비스이용약관.pdf"}
    )
    page: int = Field(
        default=1,
        description="페이지 번호",
        json_schema_extra={"example": 5}
    )
    content: str = Field(
        ...,
        description="문서 내용 (일부 또는 전체)",
        json_schema_extra={"example": "제15조(해지) 1. 이용자가 서비스를 해지하고자 할 경우..."}
    )
    score: Optional[float] = Field(
        default=None,
        description="유사도 점수 (낮을수록 유사)",
        json_schema_extra={"example": 0.234}
    )


class HealthStatus(BaseModel):
    """
    서비스 상태 정보
    """
    status: str = Field(
        ...,
        description="전체 상태 (healthy/unhealthy)",
        json_schema_extra={"example": "healthy"}
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="체크 시간"
    )
    components: Dict[str, Any] = Field(
        default_factory=dict,
        description="개별 컴포넌트 상태"
    )


# ==========================================
# 신입 상담원용 API 모델 (Full Agent)
# ==========================================

class ConsultationRequest(BaseModel):
    """
    신입 상담원용 상담 요청
    
    상담 내용을 입력받아 키워드 추출, 문서 검색, 대응방안 생성을
    모두 수행하는 Full Agent API의 요청 모델입니다.
    """
    summary: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="상담 내용 요약",
        json_schema_extra={"example": "인터넷 약정 해지 시 위약금 계산법이 궁금합니다."}
    )
    
    # 선택적 옵션
    include_documents: bool = Field(
        default=True,
        description="응답에 참조 문서 포함 여부"
    )
    max_documents: int = Field(
        default=3,
        ge=1,
        le=10,
        description="검색할 최대 문서 수"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "3년 약정 기간 중 14개월 사용 후 중도 해지 시 발생하는 위약금 및 할인 반환금 산정 상세 내역 문의.",
                    "include_documents": True,
                    "max_documents": 3
                }
            ]
        }
    }


class ConsultationResponse(BaseModel):
    """
    신입 상담원용 상담 응답
    
    상담 요청에 대한 전체 처리 결과를 담습니다.
    """
    # 입력 정보
    original_summary: str = Field(
        ...,
        description="원본 상담 요약"
    )
    
    # 분석 결과
    extracted_keywords: str = Field(
        ...,
        description="추출된 검색 키워드",
        json_schema_extra={"example": "약정 해지 위약금 계산"}
    )
    target_document: str = Field(
        ...,
        description="선택된 대상 문서",
        json_schema_extra={"example": "인터넷이용약관"}
    )
    
    # 검색 결과
    documents: List[DocumentInfo] = Field(
        default_factory=list,
        description="검색된 참조 문서 목록"
    )
    
    # 대응방안
    response_guide: str = Field(
        ...,
        description="신입 상담원을 위한 대응방안",
        json_schema_extra={"example": "고객님께 다음과 같이 안내해 주세요..."}
    )
    
    # 메타 정보
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="처리 소요 시간 (밀리초)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "original_summary": "인터넷 약정 해지 시 위약금 계산법이 궁금합니다.",
                    "extracted_keywords": "약정 해지 위약금 계산",
                    "target_document": "인터넷이용약관",
                    "documents": [
                        {
                            "source": "인터넷서비스이용약관.pdf",
                            "page": 5,
                            "content": "제15조(해지) ...",
                            "score": 0.234
                        }
                    ],
                    "response_guide": "고객님께 다음과 같이 안내해 주세요...",
                    "processing_time_ms": 1234.5
                }
            ]
        }
    }


# ==========================================
# 전문가용 API 모델 (키워드 검색만)
# ==========================================

class ExpertSearchRequest(BaseModel):
    """
    전문가용 검색 요청
    
    상담 내용을 입력받아 키워드 추출 + 벡터 검색을 수행합니다.
    신입 상담원용 Agent에서 응답 생성 단계만 제외한 버전입니다.
    """
    keyword: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="상담 내용 또는 검색 키워드",
        json_schema_extra={"example": "인터넷 약정 해지 시 위약금 계산법이 궁금합니다."}
    )
    k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="반환할 문서 수"
    )
    include_score: bool = Field(
        default=False,
        description="유사도 점수 포함 여부 (현재 미지원)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "keyword": "3년 약정 기간 중 14개월 사용 후 중도 해지 시 위약금 문의",
                    "k": 5,
                    "include_score": False
                }
            ]
        }
    }


class ExpertSearchResponse(BaseModel):
    """
    전문가용 검색 응답
    
    신입 상담원용 Agent의 키워드 추출 + 검색 결과만 포함합니다.
    (대응방안 생성은 제외)
    """
    keyword: str = Field(
        ...,
        description="입력된 상담 내용"
    )
    extracted_keywords: str = Field(
        default="",
        description="AI가 추출한 검색 키워드",
        json_schema_extra={"example": "인터넷 약정 해지 위약금"}
    )
    target_document: str = Field(
        default="없음",
        description="선택된 대상 문서",
        json_schema_extra={"example": "인터넷이용약관"}
    )
    total_results: int = Field(
        ...,
        description="검색된 문서 수"
    )
    documents: List[DocumentInfo] = Field(
        default_factory=list,
        description="검색된 문서 목록"
    )
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="처리 소요 시간 (밀리초)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "keyword": "인터넷 약정 해지 시 위약금 문의",
                    "extracted_keywords": "인터넷 약정 해지 위약금",
                    "target_document": "없음",
                    "total_results": 3,
                    "documents": [
                        {
                            "source": "인터넷서비스이용약관.pdf",
                            "page": 5,
                            "content": "제15조(해지) ...",
                            "score": None
                        }
                    ],
                    "processing_time_ms": 456.7
                }
            ]
        }
    }


# ==========================================
# 에러 응답 모델
# ==========================================

class ErrorResponse(BaseModel):
    """
    에러 응답 모델
    """
    error: str = Field(
        ...,
        description="에러 타입",
        json_schema_extra={"example": "ValidationError"}
    )
    message: str = Field(
        ...,
        description="에러 메시지",
        json_schema_extra={"example": "summary 필드는 필수입니다."}
    )
    detail: Optional[Dict[str, Any]] = Field(
        default=None,
        description="상세 에러 정보"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="에러 발생 시간"
    )


class QueueStatusResponse(BaseModel):
    """
    대기열 상태 응답
    """
    current_requests: int = Field(
        ...,
        description="현재 처리 중인 요청 수"
    )
    max_requests: int = Field(
        ...,
        description="최대 동시 요청 수"
    )
    queue_length: int = Field(
        ...,
        description="대기 중인 요청 수"
    )
    is_accepting: bool = Field(
        ...,
        description="새 요청 수락 가능 여부"
    )


# ==========================================
# [신규] 비교용 API 모델
# ==========================================

class ComparisonRequest(BaseModel):
    """
    비교용 API 공통 요청 모델
    """
    summary: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="상담 내용 요약",
        json_schema_extra={"example": "인터넷 약정 해지 시 위약금 계산법이 궁금합니다."}
    )
    include_documents: bool = Field(
        default=True,
        description="응답에 참조 문서 포함 여부"
    )
    max_documents: int = Field(
        default=5,
        ge=1,
        le=10,
        description="반환할 최대 문서 수"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "3년 약정 기간 중 14개월 사용 후 중도 해지 시 위약금 문의",
                    "include_documents": True,
                    "max_documents": 5
                }
            ]
        }
    }


class DirectSearchResponse(BaseModel):
    """
    직접 임베딩 검색 결과 응답

    API 1: 질문 직접 임베딩하여 검색한 결과 확인용
    """
    original_summary: str = Field(
        ...,
        description="원본 상담 요약"
    )
    search_method: str = Field(
        default="direct_embedding",
        description="검색 방식"
    )
    total_results: int = Field(
        ...,
        description="검색된 문서 수"
    )
    documents: List[DocumentInfo] = Field(
        default_factory=list,
        description="검색된 참조 문서 목록"
    )
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="처리 소요 시간 (밀리초)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "original_summary": "인터넷 해지 위약금 문의",
                    "search_method": "direct_embedding",
                    "total_results": 5,
                    "documents": [],
                    "processing_time_ms": 234.5
                }
            ]
        }
    }


class KeywordGuideResponse(BaseModel):
    """
    핵심 키워드 가이드 응답

    API 2, 3: 핵심 키워드 기반 간결 가이드 생성용
    """
    original_summary: str = Field(
        ...,
        description="원본 상담 요약"
    )
    search_method: str = Field(
        ...,
        description="검색 방식 (direct_embedding / keyword_extraction)"
    )
    extracted_keywords: Optional[str] = Field(
        default=None,
        description="추출된 검색 키워드 (keyword_extraction 방식에서만)"
    )
    documents: List[DocumentInfo] = Field(
        default_factory=list,
        description="검색된 참조 문서 목록"
    )
    keyword_guide: str = Field(
        ...,
        description="핵심 키워드 기반 간결 가이드",
        json_schema_extra={"example": "• [요금제] 5G 스탠다드 월 69,000원. 데이터 무제한.\n• [위약금] 24개월 약정. 잔여개월 x 할인액."}
    )
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="처리 소요 시간 (밀리초)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "original_summary": "인터넷 해지 위약금 문의",
                    "search_method": "direct_embedding",
                    "extracted_keywords": None,
                    "documents": [],
                    "keyword_guide": "• [위약금] 24개월 약정. 잔여개월 x 할인액. 최대 300,000원.",
                    "processing_time_ms": 567.8
                }
            ]
        }
    }


class DirectFullGuideResponse(BaseModel):
    """
    직접 임베딩 + 긴 가이드 응답

    API 4: 직접 임베딩 검색 후 기존 문장형 가이드 생성용
    """
    original_summary: str = Field(
        ...,
        description="원본 상담 요약"
    )
    search_method: str = Field(
        default="direct_embedding",
        description="검색 방식"
    )
    documents: List[DocumentInfo] = Field(
        default_factory=list,
        description="검색된 참조 문서 목록"
    )
    response_guide: str = Field(
        ...,
        description="신입 상담원을 위한 대응방안 (문장형)",
        json_schema_extra={"example": "고객님께 다음과 같이 안내해 주세요..."}
    )
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="처리 소요 시간 (밀리초)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "original_summary": "인터넷 해지 위약금 문의",
                    "search_method": "direct_embedding",
                    "documents": [],
                    "response_guide": "고객님께 다음과 같이 안내해 주세요...",
                    "processing_time_ms": 789.0
                }
            ]
        }
    }
