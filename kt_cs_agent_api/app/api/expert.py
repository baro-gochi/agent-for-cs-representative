"""
===========================================
전문가용 API 라우터
===========================================

이 모듈은 전문가/시니어 상담원을 위한 검색 API를 제공합니다.
신입 상담원용 Agent에서 마지막 응답 생성 단계만 제외하고
키워드 추출 + 벡터 DB 검색 결과만 반환합니다.

워크플로우:
    [신입용] summary → analyzer → searcher → response_generator → 대응방안
    [전문가용] summary → analyzer → searcher → 검색 결과만 반환 (응답 생성 X)

엔드포인트:
    POST /expert/search - 상담 내용 기반 검색 (키워드 추출 + 검색)
    GET /expert/documents - 문서 목록 조회
"""

import logging
import time
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Query

from app.models import (
    ExpertSearchRequest,
    ExpertSearchResponse,
    DocumentInfo,
    ErrorResponse
)
from app.agent.workflow import run_expert_search_async
from app.database import get_doc_registry, get_vector_db_manager
from app.utils import request_limiter

# 로거 설정
logger = logging.getLogger(__name__)

# 라우터 생성
router = APIRouter(
    prefix="/expert",
    tags=["전문가용"],
    responses={
        400: {"model": ErrorResponse, "description": "잘못된 요청"},
        429: {"model": ErrorResponse, "description": "요청 한도 초과"},
        500: {"model": ErrorResponse, "description": "서버 오류"}
    }
)


@router.post(
    "/search",
    summary="상담 내용 기반 검색",
    description="""
    전문가/시니어 상담원을 위한 검색 API입니다.
    
    신입 상담원용 Agent와 동일한 프로세스를 사용하되,
    마지막 대응방안 생성 단계만 제외합니다:
    
    1. AI가 상담 내용을 분석하여 핵심 키워드 추출
    2. 추출된 키워드로 벡터 DB 검색
    3. 검색 결과만 반환 (대응방안 생성 X)
    
    **Rate Limit**: 분당 30회
    """,
    response_model=ExpertSearchResponse
)
async def expert_search(request: ExpertSearchRequest):
    """
    상담 내용 기반 검색 (키워드 추출 + 벡터 검색)
    
    신입 상담원용 Agent의 analyzer_node + search_node만 실행합니다.
    response_generator_node는 호출하지 않아 빠른 응답이 가능합니다.
    
    Args:
        request: 검색 요청 정보
            - keyword: 상담 내용 또는 검색 키워드 (필수)
            - k: 반환할 문서 수 (기본: 5, 최대: 20)
            - include_score: 유사도 점수 포함 여부 (기본: False)
    
    Returns:
        ExpertSearchResponse: 검색 결과
            - keyword: 입력된 상담 내용
            - extracted_keywords: AI가 추출한 검색 키워드
            - total_results: 검색된 문서 수
            - documents: 문서 목록
            - processing_time_ms: 처리 시간
    """
    start_time = time.perf_counter()
    
    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 전문가 검색: '{request.keyword[:50]}...', k={request.k}")
            
            # Agent 실행 (analyzer + search만)
            try:
                result = await run_expert_search_async(
                    summary=request.keyword,
                    max_docs=request.k
                )
            except Exception as e:
                logger.error(f"[API] 검색 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"검색 중 오류가 발생했습니다: {str(e)}"
                )
            
            # 문서 정보 변환
            documents: List[DocumentInfo] = []
            for doc in result.get("documents", []):
                content = doc.page_content
                documents.append(DocumentInfo(
                    source=doc.metadata.get("source", "Unknown").split("/")[-1],
                    page=doc.metadata.get("page", 0) + 1,
                    content=content[:500] + "..." if len(content) > 500 else content,
                    score=None  # 기본 검색에서는 score 미포함
                ))
            
            # 처리 시간 계산
            processing_time_ms = (time.perf_counter() - start_time) * 1000
            
            # 응답 생성
            response = ExpertSearchResponse(
                keyword=request.keyword,
                extracted_keywords=result.get("search_query", ""),
                total_results=len(documents),
                documents=documents,
                target_document=result.get("target_doc_name", "없음"),
                processing_time_ms=round(processing_time_ms, 2)
            )
            
            logger.info(f"[API] 전문가 검색 완료: {len(documents)}개, {processing_time_ms:.2f}ms")
            return response
            
    except RuntimeError as e:
        if "Rate limit" in str(e):
            raise HTTPException(
                status_code=429,
                detail="요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            )
        raise


@router.get(
    "/search",
    summary="상담 내용 기반 검색 (GET)",
    description="GET 방식의 검색 API입니다. 브라우저에서 직접 테스트하기 좋습니다.",
    response_model=ExpertSearchResponse
)
async def expert_search_get(
    keyword: str = Query(..., min_length=1, max_length=2000, description="상담 내용 또는 검색 키워드"),
    k: int = Query(default=5, ge=1, le=20, description="반환할 문서 수")
):
    """
    상담 내용 기반 검색 (GET 방식)
    
    Query Parameter로 간단하게 검색할 수 있습니다.
    
    예시:
        GET /expert/search?keyword=인터넷해지위약금문의&k=5
    """
    request = ExpertSearchRequest(
        keyword=keyword,
        k=k,
        include_score=False
    )
    return await expert_search(request)


@router.get(
    "/documents",
    summary="등록된 문서 목록",
    description="벡터 DB에 등록된 문서 목록과 레지스트리 정보를 조회합니다.",
    response_model=Dict[str, Any]
)
async def list_documents():
    """
    등록된 문서 목록 조회
    
    현재 시스템에 등록된 문서 레지스트리와
    벡터 DB 컬렉션 정보를 반환합니다.
    
    Returns:
        dict:
            - registry: 문서 레지스트리 정보
            - vector_db: 벡터 DB 정보
    """
    try:
        # 문서 레지스트리 정보
        doc_registry = get_doc_registry()
        registry_info = doc_registry.get_registry_info()
        
        # 벡터 DB 정보
        db_manager = get_vector_db_manager()
        db_info = db_manager.get_collection_info()
        
        return {
            "registry": registry_info,
            "vector_db": db_info
        }
        
    except Exception as e:
        logger.error(f"[API] 문서 목록 조회 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"문서 목록 조회 중 오류가 발생했습니다: {str(e)}"
        )
