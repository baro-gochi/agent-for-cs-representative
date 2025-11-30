"""
===========================================
신입 상담원용 API 라우터
===========================================

이 모듈은 신입 상담원을 위한 Full Agent API를 제공합니다.
상담 내용을 입력받아 다음을 수행합니다:
1. 키워드 추출
2. 관련 문서 검색
3. 대응방안 생성

엔드포인트:
    POST /consultation/assist - 상담 지원 요청
"""

import logging
import time
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.models import (
    ConsultationRequest,
    ConsultationResponse,
    DocumentInfo,
    ErrorResponse
)
from app.agent import run_consultation_async
from app.utils import request_limiter

# 로거 설정
logger = logging.getLogger(__name__)

# 라우터 생성
router = APIRouter(
    prefix="/consultation",
    tags=["신입 상담원용"],
    responses={
        400: {"model": ErrorResponse, "description": "잘못된 요청"},
        429: {"model": ErrorResponse, "description": "요청 한도 초과"},
        500: {"model": ErrorResponse, "description": "서버 오류"}
    }
)


@router.post(
    "/assist",
    summary="상담 지원 요청",
    description="""
    신입 상담원을 위한 상담 지원 API입니다.
    
    상담 내용을 입력하면 다음을 수행합니다:
    1. AI가 상담 내용을 분석하여 핵심 키워드 추출
    2. 관련 내부 규정/약관 문서 검색
    3. 신입 상담원용 대응방안 생성
    
    **Rate Limit**: 분당 30회
    **동시 요청**: 최대 10개
    """,
    response_model=ConsultationResponse,
    responses={
        200: {
            "description": "성공적으로 처리됨",
            "content": {
                "application/json": {
                    "example": {
                        "original_summary": "인터넷 약정 해지 시 위약금 문의",
                        "extracted_keywords": "인터넷 약정 해지 위약금",
                        "target_document": "없음",
                        "documents": [],
                        "response_guide": "고객님께 다음과 같이 안내해 주세요...",
                        "processing_time_ms": 1234.5
                    }
                }
            }
        }
    }
)
async def assist_consultation(request: ConsultationRequest):
    """
    상담 지원 요청 처리
    
    Args:
        request: 상담 요청 정보
            - summary: 상담 내용 요약 (필수)
            - include_documents: 응답에 문서 포함 여부 (기본: True)
            - max_documents: 최대 문서 수 (기본: 3)
    
    Returns:
        ConsultationResponse: 상담 지원 결과
            - extracted_keywords: 추출된 키워드
            - target_document: 선택된 문서
            - documents: 검색된 문서 목록
            - response_guide: 대응방안
    
    Raises:
        HTTPException(429): Rate limit 초과 시
        HTTPException(500): 처리 중 오류 발생 시
    
    Note:
        이 API는 Rate Limiting과 동시성 제한이 적용됩니다.
        - 분당 최대 30회 요청 가능
        - 동시에 최대 10개 요청 처리
    """
    start_time = time.perf_counter()
    
    # Rate Limit 및 동시성 제한 적용
    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 상담 지원 요청: '{request.summary[:50]}...'")
            
            # Agent 실행
            try:
                result = await run_consultation_async(request.summary)
            except Exception as e:
                logger.error(f"[API] Agent 실행 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"상담 처리 중 오류가 발생했습니다: {str(e)}"
                )
            
            # 문서 정보 변환
            documents: List[DocumentInfo] = []
            if request.include_documents and result.get("documents"):
                for doc in result["documents"][:request.max_documents]:
                    documents.append(DocumentInfo(
                        source=doc.metadata.get("source", "Unknown").split("/")[-1],
                        page=doc.metadata.get("page", 0) + 1,
                        content=doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content,
                        score=None
                    ))
            
            # 처리 시간 계산
            processing_time_ms = (time.perf_counter() - start_time) * 1000
            
            # 응답 생성
            response = ConsultationResponse(
                original_summary=request.summary,
                extracted_keywords=result.get("search_query", ""),
                target_document=result.get("target_doc_name", "없음"),
                documents=documents,
                response_guide=result.get("response_guide", ""),
                processing_time_ms=round(processing_time_ms, 2)
            )
            
            logger.info(f"[API] 상담 지원 완료: {processing_time_ms:.2f}ms")
            return response
            
    except RuntimeError as e:
        # Rate limit 초과
        if "Rate limit" in str(e):
            logger.warning(f"[API] Rate limit 초과")
            raise HTTPException(
                status_code=429,
                detail="요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            )
        raise
    
    except TimeoutError:
        logger.error(f"[API] 요청 타임아웃")
        raise HTTPException(
            status_code=503,
            detail="서버가 바쁩니다. 잠시 후 다시 시도해주세요."
        )
