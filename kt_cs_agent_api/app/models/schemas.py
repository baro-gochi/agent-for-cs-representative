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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "3년 약정 기간 중 14개월 사용 후 중도 해지 시 발생하는 위약금 및 할인 반환금 산정 상세 내역 문의."
                }
            ]
        }
    }


class ConsultationResponse(BaseModel):
    """
    신입 상담원용 상담 응답

    상담 요청에 대한 전체 처리 결과를 담습니다.
    response_guide는 JSON 구조화된 데이터로, 프론트엔드에서 자유롭게 렌더링할 수 있습니다.
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

    # 대응방안 (JSON 구조화)
    response_guide: Dict[str, Any] = Field(
        ...,
        description="신입 상담원을 위한 대응방안 (JSON 구조화)",
        json_schema_extra={"example": {
            "announcement": {
                "title": "안내 멘트",
                "items": ["고객님, 약정 해지 관련 안내드리겠습니다."]
            },
            "cautions": {
                "title": "주의사항",
                "items": ["중도 해지 시 위약금이 발생합니다."]
            },
            "check_required": {
                "title": "확인 필요 사항",
                "items": ["정확한 가입일자 확인"]
            },
            "next_steps": {
                "title": "다음 단계 안내",
                "items": ["해지 신청서 작성 안내"]
            }
        }}
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
                    "response_guide": {
                        "announcement": {
                            "title": "안내 멘트",
                            "items": [
                                "고객님, 약정 해지 관련 안내드리겠습니다.",
                                "현재 사용 중이신 상품은 24개월 약정 상품입니다."
                            ]
                        },
                        "cautions": {
                            "title": "주의사항",
                            "items": [
                                "중도 해지 시 위약금이 발생합니다.",
                                "위약금은 잔여 약정 기간에 따라 산정됩니다."
                            ]
                        },
                        "check_required": {
                            "title": "확인 필요 사항",
                            "items": [
                                "정확한 가입일자 확인",
                                "결합상품 여부 확인"
                            ]
                        },
                        "next_steps": {
                            "title": "다음 단계 안내",
                            "items": [
                                "해지 신청서 작성 안내",
                                "위약금 정산 절차 안내"
                            ]
                        }
                    },
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
# [신규] JSON 구조화된 가이드 모델
# ==========================================

class GuideSection(BaseModel):
    """
    가이드 섹션 모델

    각 섹션은 제목과 항목 리스트로 구성됩니다.
    프론트엔드에서 자유롭게 스타일링할 수 있도록 구조화되어 있습니다.
    """
    title: str = Field(
        ...,
        description="섹션 제목",
        json_schema_extra={"example": "안내 멘트"}
    )
    items: List[str] = Field(
        default_factory=list,
        description="섹션 내 항목 리스트",
        json_schema_extra={"example": ["고객님, 약정 해지 관련 안내드리겠습니다.", "현재 사용 중이신 상품은 24개월 약정 상품입니다."]}
    )


class StructuredResponseGuide(BaseModel):
    """
    구조화된 대응방안 가이드 (response_generator_node용)

    신입 상담원용 대응방안을 JSON 구조로 반환합니다.
    프론트엔드에서 각 섹션별로 자유롭게 렌더링할 수 있습니다.
    """
    announcement: GuideSection = Field(
        ...,
        description="안내 멘트 섹션"
    )
    cautions: GuideSection = Field(
        ...,
        description="주의사항 섹션"
    )
    check_required: GuideSection = Field(
        ...,
        description="확인 필요 사항 섹션"
    )
    next_steps: GuideSection = Field(
        ...,
        description="다음 단계 안내 섹션"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "announcement": {
                        "title": "안내 멘트",
                        "items": [
                            "고객님, 약정 해지 관련 안내드리겠습니다.",
                            "현재 사용 중이신 상품은 24개월 약정 상품입니다."
                        ]
                    },
                    "cautions": {
                        "title": "주의사항",
                        "items": [
                            "중도 해지 시 위약금이 발생합니다.",
                            "위약금은 잔여 약정 기간에 따라 산정됩니다."
                        ]
                    },
                    "check_required": {
                        "title": "확인 필요 사항",
                        "items": [
                            "정확한 가입일자 확인",
                            "결합상품 여부 확인"
                        ]
                    },
                    "next_steps": {
                        "title": "다음 단계 안내",
                        "items": [
                            "해지 신청서 작성 안내",
                            "위약금 정산 절차 안내"
                        ]
                    }
                }
            ]
        }
    }


class KeywordGuideItem(BaseModel):
    """
    핵심 키워드 가이드 항목 모델

    각 항목은 주제와 핵심 포인트 리스트로 구성됩니다.
    """
    topic: str = Field(
        ...,
        description="주제/카테고리",
        json_schema_extra={"example": "요금제"}
    )
    points: List[str] = Field(
        default_factory=list,
        description="핵심 포인트 리스트",
        json_schema_extra={"example": ["5G 스탠다드 월 69,000원", "데이터 무제한", "통화 무제한"]}
    )


class StructuredKeywordGuide(BaseModel):
    """
    구조화된 핵심 키워드 가이드 (keyword_guide_node용)

    상담원에게 필요한 핵심만 짧게 제시합니다.
    프론트엔드에서 각 항목을 태그, 칩, 카드 등으로 렌더링할 수 있습니다.
    """
    guide_items: List[KeywordGuideItem] = Field(
        default_factory=list,
        description="핵심 가이드 항목 리스트"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "guide_items": [
                        {
                            "topic": "요금제",
                            "points": ["5G 스탠다드 월 69,000원", "데이터 무제한", "통화 무제한"]
                        },
                        {
                            "topic": "위약금",
                            "points": ["24개월 약정", "잔여개월 x 할인액", "최대 300,000원"]
                        },
                        {
                            "topic": "확인사항",
                            "points": ["가입일 확인 필요", "결합상품 여부 체크"]
                        }
                    ]
                }
            ]
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "3년 약정 기간 중 14개월 사용 후 중도 해지 시 위약금 문의"
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
    keyword_guide는 JSON 구조화된 데이터로, 프론트엔드에서 자유롭게 렌더링할 수 있습니다.
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
    keyword_guide: Dict[str, Any] = Field(
        ...,
        description="핵심 키워드 기반 간결 가이드 (JSON 구조화)",
        json_schema_extra={"example": {
            "guide_items": [
                {"topic": "요금제", "points": ["5G 스탠다드 월 69,000원", "데이터 무제한"]},
                {"topic": "위약금", "points": ["24개월 약정", "잔여개월 x 할인액"]}
            ]
        }}
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
                    "keyword_guide": {
                        "guide_items": [
                            {"topic": "위약금", "points": ["24개월 약정", "잔여개월 x 할인액", "최대 300,000원"]},
                            {"topic": "확인사항", "points": ["가입일 확인 필요", "결합상품 여부 체크"]}
                        ]
                    },
                    "processing_time_ms": 567.8
                }
            ]
        }
    }


class DirectFullGuideResponse(BaseModel):
    """
    직접 임베딩 + 긴 가이드 응답

    API 4: 직접 임베딩 검색 후 구조화된 가이드 생성용
    response_guide는 JSON 구조화된 데이터로, 프론트엔드에서 자유롭게 렌더링할 수 있습니다.
    """
    original_summary: str = Field(
        ...,
        description="원본 상담 요약"
    )
    search_method: str = Field(
        default="direct_embedding",
        description="검색 방식"
    )
    response_guide: Dict[str, Any] = Field(
        ...,
        description="신입 상담원을 위한 대응방안 (JSON 구조화)",
        json_schema_extra={"example": {
            "announcement": {"title": "안내 멘트", "items": ["고객님, 안내드리겠습니다."]},
            "cautions": {"title": "주의사항", "items": ["위약금이 발생합니다."]},
            "check_required": {"title": "확인 필요 사항", "items": ["가입일 확인"]},
            "next_steps": {"title": "다음 단계 안내", "items": ["해지 신청서 작성"]}
        }}
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
                    "response_guide": {
                        "announcement": {
                            "title": "안내 멘트",
                            "items": ["고객님, 약정 해지 관련 안내드리겠습니다."]
                        },
                        "cautions": {
                            "title": "주의사항",
                            "items": ["중도 해지 시 위약금이 발생합니다."]
                        },
                        "check_required": {
                            "title": "확인 필요 사항",
                            "items": ["정확한 가입일자 확인"]
                        },
                        "next_steps": {
                            "title": "다음 단계 안내",
                            "items": ["해지 신청서 작성 안내"]
                        }
                    },
                    "processing_time_ms": 789.0
                }
            ]
        }
    }


# ==========================================
# [신규] 캐싱 관련 API 모델
# ==========================================

class CachedRequest(BaseModel):
    """
    캐싱 적용 API 요청 모델
    """
    summary: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="상담 내용 요약",
        json_schema_extra={"example": "인터넷 약정 해지 시 위약금 계산법이 궁금합니다."}
    )
    use_l1_cache: bool = Field(
        default=True,
        description="L1 캐시 사용 여부 (질문→응답 캐싱)"
    )
    use_l2_cache: bool = Field(
        default=True,
        description="L2 캐시 사용 여부 (검색 결과 캐싱)"
    )
    use_llm_normalization: bool = Field(
        default=True,
        description="LLM 기반 질문 정규화 사용 여부"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "3년 약정 기간 중 14개월 사용 후 중도 해지 시 위약금 문의",
                    "use_l1_cache": True,
                    "use_l2_cache": True,
                    "use_llm_normalization": True
                }
            ]
        }
    }


class CachedResponse(BaseModel):
    """
    캐싱 적용 API 응답 모델
    """
    original_summary: str = Field(
        ...,
        description="원본 상담 요약"
    )
    normalized_query: Optional[str] = Field(
        default=None,
        description="정규화된 질문 (캐시 키 생성용)"
    )
    keyword_guide: Dict[str, Any] = Field(
        ...,
        description="핵심 키워드 기반 간결 가이드 (JSON 구조화)"
    )
    documents: List[DocumentInfo] = Field(
        default_factory=list,
        description="검색된 참조 문서 목록"
    )

    # 캐시 메타데이터
    l1_cache_hit: bool = Field(
        default=False,
        description="L1 캐시 히트 여부"
    )
    l2_cache_hit: bool = Field(
        default=False,
        description="L2 캐시 히트 여부"
    )
    cache_status: str = Field(
        default="miss",
        description="캐시 상태 (l1_hit, l2_hit, miss)"
    )

    processing_time_ms: float = Field(
        ...,
        description="처리 소요 시간 (밀리초)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "original_summary": "인터넷 해지 위약금 문의",
                    "normalized_query": "인터넷 해지 위약금",
                    "keyword_guide": {
                        "guide_items": [
                            {"topic": "위약금", "points": ["24개월 약정", "잔여개월 x 할인액"]}
                        ]
                    },
                    "documents": [],
                    "l1_cache_hit": True,
                    "l2_cache_hit": False,
                    "cache_status": "l1_hit",
                    "processing_time_ms": 15.2
                }
            ]
        }
    }


class CacheStatsResponse(BaseModel):
    """
    캐시 통계 응답 모델
    """
    connected: bool = Field(
        ...,
        description="Redis 연결 상태"
    )
    l1_cache_count: int = Field(
        default=0,
        description="L1 캐시 항목 수"
    )
    l2_cache_count: int = Field(
        default=0,
        description="L2 캐시 항목 수"
    )
    used_memory: str = Field(
        default="N/A",
        description="Redis 메모리 사용량"
    )
    used_memory_peak: str = Field(
        default="N/A",
        description="Redis 최대 메모리 사용량"
    )
    l1_ttl_seconds: int = Field(
        ...,
        description="L1 캐시 TTL (초)"
    )
    l2_ttl_seconds: int = Field(
        ...,
        description="L2 캐시 TTL (초)"
    )
    error: Optional[str] = Field(
        default=None,
        description="에러 메시지 (있는 경우)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "connected": True,
                    "l1_cache_count": 150,
                    "l2_cache_count": 320,
                    "used_memory": "2.5M",
                    "used_memory_peak": "3.1M",
                    "l1_ttl_seconds": 3600,
                    "l2_ttl_seconds": 7200,
                    "error": None
                }
            ]
        }
    }


class CacheInvalidateRequest(BaseModel):
    """
    캐시 무효화 요청 모델
    """
    level: str = Field(
        default="all",
        description="무효화할 캐시 레벨 (l1, l2, all)"
    )
    query: Optional[str] = Field(
        default=None,
        description="특정 쿼리의 캐시만 무효화 (선택적)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "level": "l1",
                    "query": None
                }
            ]
        }
    }


class CacheInvalidateResponse(BaseModel):
    """
    캐시 무효화 응답 모델
    """
    success: bool = Field(
        ...,
        description="무효화 성공 여부"
    )
    l1_deleted: int = Field(
        default=0,
        description="삭제된 L1 캐시 항목 수"
    )
    l2_deleted: int = Field(
        default=0,
        description="삭제된 L2 캐시 항목 수"
    )
    message: str = Field(
        ...,
        description="결과 메시지"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "l1_deleted": 150,
                    "l2_deleted": 320,
                    "message": "모든 캐시가 무효화되었습니다."
                }
            ]
        }
    }


class NormalizeTestRequest(BaseModel):
    """
    질문 정규화 테스트 요청 모델
    """
    queries: List[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="정규화할 질문 목록 (최대 10개)"
    )
    use_llm: bool = Field(
        default=True,
        description="LLM 기반 정규화 사용 여부"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "queries": [
                        "위약금이 얼마예요?",
                        "해지 위약금 알려주세요",
                        "약정 해지시 위약금"
                    ],
                    "use_llm": True
                }
            ]
        }
    }


class NormalizeTestResponse(BaseModel):
    """
    질문 정규화 테스트 응답 모델
    """
    results: List[Dict[str, str]] = Field(
        ...,
        description="정규화 결과 목록"
    )
    processing_time_ms: float = Field(
        ...,
        description="총 처리 소요 시간 (밀리초)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "results": [
                        {"original": "위약금이 얼마예요?", "normalized": "위약금 금액"},
                        {"original": "해지 위약금 알려주세요", "normalized": "위약금 금액"},
                        {"original": "약정 해지시 위약금", "normalized": "위약금 금액"}
                    ],
                    "processing_time_ms": 456.7
                }
            ]
        }
    }
