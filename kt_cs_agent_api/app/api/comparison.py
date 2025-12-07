"""
===========================================
비교용 API 라우터
===========================================

이 모듈은 다양한 검색/가이드 생성 방식을 비교하기 위한 API를 제공합니다.

엔드포인트:
    POST /comparison/direct-search       - 직접 임베딩 검색 결과 확인
    POST /comparison/direct-keyword      - 직접 임베딩 + 핵심 가이드 생성
    POST /comparison/keyword-extraction  - 키워드 추출 + 핵심 가이드 생성
    POST /comparison/direct-full-guide   - 직접 임베딩 + 긴 가이드 생성

비교 목적:
    1. 직접 임베딩 vs 키워드 추출 검색 품질 비교
    2. 핵심 가이드 vs 긴 가이드 유용성 비교
"""

import logging
import time
from typing import List

from fastapi import APIRouter, HTTPException

from app.models import (
    ComparisonRequest,
    DirectSearchResponse,
    KeywordGuideResponse,
    DirectFullGuideResponse,
    DocumentInfo,
    ErrorResponse
)
from app.agent.workflow import (
    run_direct_search_async,
    run_direct_keyword_guide_async,
    run_keyword_extraction_guide_async,
    run_direct_full_guide_async
)
from app.utils import request_limiter

# 로거 설정
logger = logging.getLogger(__name__)

# 라우터 생성
router = APIRouter(
    prefix="/comparison",
    tags=["비교용 API"],
    responses={
        400: {"model": ErrorResponse, "description": "잘못된 요청"},
        429: {"model": ErrorResponse, "description": "요청 한도 초과"},
        500: {"model": ErrorResponse, "description": "서버 오류"}
    }
)


def _convert_documents(documents: list, max_docs: int) -> List[DocumentInfo]:
    """문서 리스트를 DocumentInfo 리스트로 변환"""
    result = []
    for doc in documents[:max_docs]:
        content = doc.page_content
        result.append(DocumentInfo(
            source=doc.metadata.get("source", "Unknown").split("/")[-1],
            page=doc.metadata.get("page", 0) + 1,
            content=content[:500] + "..." if len(content) > 500 else content,
            score=None
        ))
    return result


# ==========================================
# API 1: 직접 임베딩 검색 결과 확인
# ==========================================

@router.post(
    "/direct-search",
    summary="직접 임베딩 검색 결과 확인",
    description="""
    질문을 직접 임베딩하여 벡터 DB에서 유사 문서를 검색합니다.

    **특징:**
    - 키워드 추출 과정 없이 요약문 자체를 임베딩
    - LLM API 호출 없이 검색만 수행
    - 빠른 응답 속도

    **비교 대상:** 기존 /expert/search (키워드 추출 후 검색)
    """,
    response_model=DirectSearchResponse
)
async def direct_search(request: ComparisonRequest):
    """
    직접 임베딩 검색 API

    요약문을 임베딩하여 벡터 DB에서 유사 문서를 검색합니다.
    키워드 추출 과정이 없어 빠른 응답이 가능합니다.
    """
    start_time = time.perf_counter()

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 직접 임베딩 검색: '{request.summary[:50]}...'")

            try:
                result = await run_direct_search_async(request.summary)
            except Exception as e:
                logger.error(f"[API] 직접 임베딩 검색 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"검색 중 오류가 발생했습니다: {str(e)}"
                )

            # 문서 변환
            documents = []
            if request.include_documents and result.get("documents"):
                documents = _convert_documents(
                    result["documents"],
                    request.max_documents
                )

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            response = DirectSearchResponse(
                original_summary=request.summary,
                search_method="direct_embedding",
                total_results=len(result.get("documents", [])),
                documents=documents,
                processing_time_ms=round(processing_time_ms, 2)
            )

            logger.info(f"[API] 직접 임베딩 검색 완료: {len(documents)}개, {processing_time_ms:.2f}ms")
            return response

    except RuntimeError as e:
        if "Rate limit" in str(e):
            raise HTTPException(
                status_code=429,
                detail="요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            )
        raise


# ==========================================
# API 2: 직접 임베딩 + 핵심 가이드 생성
# ==========================================

@router.post(
    "/direct-keyword",
    summary="직접 임베딩 + 핵심 가이드 생성",
    description="""
    질문을 직접 임베딩하여 검색 후 핵심 키워드 기반 간결 가이드를 생성합니다.

    **워크플로우:**
    요약문 → 직접 임베딩 검색 → 핵심 가이드 생성

    **특징:**
    - 키워드 추출 과정 생략 (빠른 검색)
    - 긴 문장 대신 핵심만 짧게 나열
    - 상담원이 자신의 말로 정제 가능

    **비교 대상:** /comparison/keyword-extraction (키워드 추출 후 검색)
    """,
    response_model=KeywordGuideResponse
)
async def direct_keyword_guide(request: ComparisonRequest):
    """
    직접 임베딩 + 핵심 가이드 생성 API

    요약문을 직접 임베딩하여 검색 후 핵심 키워드 기반 간결 가이드를 생성합니다.
    """
    start_time = time.perf_counter()

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 직접 임베딩 + 핵심 가이드: '{request.summary[:50]}...'")

            try:
                result = await run_direct_keyword_guide_async(request.summary)
            except Exception as e:
                logger.error(f"[API] 직접 임베딩 + 핵심 가이드 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"처리 중 오류가 발생했습니다: {str(e)}"
                )

            # 문서 변환
            documents = []
            if request.include_documents and result.get("documents"):
                documents = _convert_documents(
                    result["documents"],
                    request.max_documents
                )

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            response = KeywordGuideResponse(
                original_summary=request.summary,
                search_method="direct_embedding",
                extracted_keywords=None,  # 직접 임베딩은 키워드 추출 없음
                documents=documents,
                keyword_guide=result.get("keyword_guide", ""),
                processing_time_ms=round(processing_time_ms, 2)
            )

            logger.info(f"[API] 직접 임베딩 + 핵심 가이드 완료: {processing_time_ms:.2f}ms")
            return response

    except RuntimeError as e:
        if "Rate limit" in str(e):
            raise HTTPException(
                status_code=429,
                detail="요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            )
        raise


# ==========================================
# API 3: 키워드 추출 + 핵심 가이드 생성
# ==========================================

@router.post(
    "/keyword-extraction",
    summary="키워드 추출 + 핵심 가이드 생성",
    description="""
    기존 방식대로 키워드를 추출하여 검색 후 핵심 키워드 기반 간결 가이드를 생성합니다.

    **워크플로우:**
    요약문 → 키워드 추출 → 벡터 검색 → 핵심 가이드 생성

    **특징:**
    - 기존 analyzer_node로 키워드 추출
    - 기존 search_node로 검색
    - 긴 문장 대신 핵심만 짧게 나열

    **비교 대상:** /comparison/direct-keyword (직접 임베딩 검색)
    """,
    response_model=KeywordGuideResponse
)
async def keyword_extraction_guide(request: ComparisonRequest):
    """
    키워드 추출 + 핵심 가이드 생성 API

    기존 키워드 추출 방식으로 검색 후 핵심 가이드를 생성합니다.
    """
    start_time = time.perf_counter()

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 키워드 추출 + 핵심 가이드: '{request.summary[:50]}...'")

            try:
                result = await run_keyword_extraction_guide_async(request.summary)
            except Exception as e:
                logger.error(f"[API] 키워드 추출 + 핵심 가이드 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"처리 중 오류가 발생했습니다: {str(e)}"
                )

            # 문서 변환
            documents = []
            if request.include_documents and result.get("documents"):
                documents = _convert_documents(
                    result["documents"],
                    request.max_documents
                )

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            response = KeywordGuideResponse(
                original_summary=request.summary,
                search_method="keyword_extraction",
                extracted_keywords=result.get("search_query", ""),
                documents=documents,
                keyword_guide=result.get("keyword_guide", ""),
                processing_time_ms=round(processing_time_ms, 2)
            )

            logger.info(f"[API] 키워드 추출 + 핵심 가이드 완료: {processing_time_ms:.2f}ms")
            return response

    except RuntimeError as e:
        if "Rate limit" in str(e):
            raise HTTPException(
                status_code=429,
                detail="요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            )
        raise


# ==========================================
# API 4: 직접 임베딩 + 긴 가이드 생성
# ==========================================

@router.post(
    "/direct-full-guide",
    summary="직접 임베딩 + 긴 가이드 생성",
    description="""
    질문을 직접 임베딩하여 검색 후 기존 문장형 가이드를 생성합니다.

    **워크플로우:**
    요약문 → 직접 임베딩 검색 → 긴 가이드 생성

    **특징:**
    - 키워드 추출 과정 생략 (빠른 검색)
    - 기존 response_generator_node로 문장형 가이드 생성

    **비교 대상:** /consultation/assist (키워드 추출 후 긴 가이드 생성)
    """,
    response_model=DirectFullGuideResponse
)
async def direct_full_guide(request: ComparisonRequest):
    """
    직접 임베딩 + 긴 가이드 생성 API

    요약문을 직접 임베딩하여 검색 후 기존 문장형 가이드를 생성합니다.
    """
    start_time = time.perf_counter()

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 직접 임베딩 + 긴 가이드: '{request.summary[:50]}...'")

            try:
                result = await run_direct_full_guide_async(request.summary)
            except Exception as e:
                logger.error(f"[API] 직접 임베딩 + 긴 가이드 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"처리 중 오류가 발생했습니다: {str(e)}"
                )

            # 문서 변환
            documents = []
            if request.include_documents and result.get("documents"):
                documents = _convert_documents(
                    result["documents"],
                    request.max_documents
                )

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            response = DirectFullGuideResponse(
                original_summary=request.summary,
                search_method="direct_embedding",
                documents=documents,
                response_guide=result.get("response_guide", ""),
                processing_time_ms=round(processing_time_ms, 2)
            )

            logger.info(f"[API] 직접 임베딩 + 긴 가이드 완료: {processing_time_ms:.2f}ms")
            return response

    except RuntimeError as e:
        if "Rate limit" in str(e):
            raise HTTPException(
                status_code=429,
                detail="요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            )
        raise
