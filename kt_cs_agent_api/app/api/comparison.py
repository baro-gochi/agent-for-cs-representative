"""
===========================================
비교용 API 라우터
===========================================

이 모듈은 다양한 검색/가이드 생성 방식을 비교하기 위한 API를 제공합니다.

엔드포인트:
    POST /comparison/direct-keyword      - 직접 임베딩 + 핵심 가이드 생성
    POST /comparison/keyword-extraction  - 키워드 추출 + 핵심 가이드 생성
    POST /comparison/direct-full-guide   - 직접 임베딩 + 긴 가이드 생성

비교 목적:
    1. 직접 임베딩 vs 키워드 추출 검색 품질 비교
    2. 핵심 가이드 vs 긴 가이드 유용성 비교

캐싱:
    - 각 API별 독립적인 캐시 헬퍼 사용
    - L1 캐시: 전체 응답
    - L2 캐시: 검색 결과 (direct/keyword 기반 분리)
"""

import logging
import time

from fastapi import APIRouter, HTTPException

from app.models import (
    ComparisonRequest,
    KeywordGuideResponse,
    DirectFullGuideResponse,
    ErrorResponse
)
from app.agent.workflow import (
    run_direct_search_only_async,
    run_keyword_guide_only_async,
    run_keyword_search_only_async,
    run_response_guide_only_async
)
from app.utils import request_limiter
from app.utils.cache_helpers import (
    DirectKeywordCacheHelper,
    KeywordExtractionCacheHelper,
    DirectFullCacheHelper
)

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


# ==========================================
# API 1: 직접 임베딩 + 핵심 가이드 생성
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
    - **캐싱 적용**: L1(응답 전체), L2(검색 결과) 캐싱

    **캐시 흐름:**
    1. L1 히트 → 즉시 응답 (~50ms)
    2. L2 히트 → 검색 생략, LLM만 호출 (~500ms)
    3. 캐시 미스 → 전체 처리 (~2000ms)

    **비교 대상:** /comparison/keyword-extraction (키워드 추출 후 검색)
    """,
    response_model=KeywordGuideResponse
)
async def direct_keyword_guide(request: ComparisonRequest):
    """
    직접 임베딩 + 핵심 가이드 생성 API (DirectKeywordCacheHelper 사용)

    캐시 동작:
    - L1 캐시: direct_keyword:{hash} → 전체 응답
    - L2 캐시: direct:{hash} → 직접 임베딩 기반 검색 결과
    """
    start_time = time.perf_counter()
    cache = DirectKeywordCacheHelper

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 직접 임베딩 + 핵심 가이드: '{request.summary[:50]}...'")

            # 질문 정규화 (캐시 키 생성용)
            normalized_query = await cache.get_normalized_query(request.summary, use_llm=True)

            # ==========================================
            # Step 1: L1 캐시 확인 (전체 응답)
            # ==========================================
            cached_response = await cache.get_l1_cache(normalized_query)
            if cached_response:
                processing_time_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[API] L1 캐시 히트! 소요시간: {processing_time_ms:.2f}ms")

                keyword_guide = cached_response.get("keyword_guide", {})
                if isinstance(keyword_guide, str):
                    keyword_guide = {
                        "guide_items": [{"topic": "응답", "points": [keyword_guide]}]
                    }

                return KeywordGuideResponse(
                    original_summary=request.summary,
                    search_method=cache.get_search_method_display("l1_hit"),
                    extracted_keywords=cached_response.get("extracted_keywords"),
                    keyword_guide=keyword_guide,
                    processing_time_ms=round(processing_time_ms, 2)
                )

            # ==========================================
            # Step 2: L2 캐시 확인 (검색 결과만)
            # ==========================================
            cached_documents = await cache.get_l2_cache(normalized_query, k=5)

            if cached_documents:
                logger.info(f"[API] L2 캐시 히트! 문서 {len(cached_documents)}개로 가이드 생성")

                # dict를 Document 객체로 변환
                documents_for_guide = cache._dict_to_documents(cached_documents)

                try:
                    # 가이드만 생성 (검색 생략)
                    guide_result = await run_keyword_guide_only_async(
                        request.summary,
                        documents_for_guide
                    )
                    keyword_guide = guide_result.get("keyword_guide", {})
                except Exception as e:
                    logger.error(f"[API] L2 캐시 히트 후 가이드 생성 실패: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"가이드 생성 중 오류가 발생했습니다: {str(e)}"
                    )

                if isinstance(keyword_guide, str):
                    keyword_guide = {
                        "guide_items": [{"topic": "응답", "points": [keyword_guide]}]
                    }

                processing_time_ms = (time.perf_counter() - start_time) * 1000

                # L1 캐시에 저장
                l1_data = cache.build_l1_response(
                    extracted_keywords=None,
                    documents=documents_for_guide,
                    keyword_guide=keyword_guide
                )
                await cache.set_l1_cache(normalized_query, l1_data)

                return KeywordGuideResponse(
                    original_summary=request.summary,
                    search_method=cache.get_search_method_display("l2_hit"),
                    extracted_keywords=None,
                    keyword_guide=keyword_guide,
                    processing_time_ms=round(processing_time_ms, 2)
                )

            # ==========================================
            # Step 3: 캐시 미스 - 전체 처리
            # ==========================================
            logger.info("[API] 캐시 미스 - 검색 + 가이드 생성 수행")

            try:
                # 검색 수행
                raw_documents = await run_direct_search_only_async(request.summary)

                # L2 캐시에 검색 결과 저장
                if raw_documents:
                    await cache.set_l2_cache(normalized_query, raw_documents, k=5)

                # 가이드 생성
                guide_result = await run_keyword_guide_only_async(
                    request.summary,
                    raw_documents
                )
                keyword_guide = guide_result.get("keyword_guide", {})

            except Exception as e:
                logger.error(f"[API] 직접 임베딩 + 핵심 가이드 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"처리 중 오류가 발생했습니다: {str(e)}"
                )

            if isinstance(keyword_guide, str):
                keyword_guide = {
                    "guide_items": [{"topic": "응답", "points": [keyword_guide]}]
                }

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            # L1 캐시에 저장
            l1_data = cache.build_l1_response(
                documents=raw_documents if raw_documents else [],
                keyword_guide=keyword_guide
            )
            await cache.set_l1_cache(normalized_query, l1_data)

            response = KeywordGuideResponse(
                original_summary=request.summary,
                search_method=cache.get_search_method_display("miss"),
                extracted_keywords=None,
                keyword_guide=keyword_guide,
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
# API 2: 키워드 추출 + 핵심 가이드 생성
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
    - **캐싱 적용**: L1(응답 전체), L2(검색 결과) 캐싱

    **캐시 흐름:**
    1. L1 히트 → 즉시 응답 (~50ms)
    2. L2 히트 → 검색 생략, LLM만 호출 (~500ms)
    3. 캐시 미스 → 전체 처리 (~2000ms)

    **비교 대상:** /comparison/direct-keyword (직접 임베딩 검색)
    """,
    response_model=KeywordGuideResponse
)
async def keyword_extraction_guide(request: ComparisonRequest):
    """
    키워드 추출 + 핵심 가이드 생성 API (KeywordExtractionCacheHelper 사용)

    캐시 동작:
    - L1 캐시: keyword_extraction:{hash} → 전체 응답
    - L2 캐시: keyword:{hash} → 키워드 추출 기반 검색 결과
    """
    start_time = time.perf_counter()
    cache = KeywordExtractionCacheHelper

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 키워드 추출 + 핵심 가이드: '{request.summary[:50]}...'")

            # 질문 정규화 (캐시 키 생성용)
            normalized_query = await cache.get_normalized_query(request.summary, use_llm=True)

            # ==========================================
            # Step 1: L1 캐시 확인 (전체 응답)
            # ==========================================
            cached_response = await cache.get_l1_cache(normalized_query)
            if cached_response:
                processing_time_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[API] L1 캐시 히트! 소요시간: {processing_time_ms:.2f}ms")

                keyword_guide = cached_response.get("keyword_guide", {})
                if isinstance(keyword_guide, str):
                    keyword_guide = {
                        "guide_items": [{"topic": "응답", "points": [keyword_guide]}]
                    }

                return KeywordGuideResponse(
                    original_summary=request.summary,
                    search_method=cache.get_search_method_display("l1_hit"),
                    extracted_keywords=cached_response.get("extracted_keywords", ""),
                    keyword_guide=keyword_guide,
                    processing_time_ms=round(processing_time_ms, 2)
                )

            # ==========================================
            # Step 2: L2 캐시 확인 (검색 결과만)
            # ==========================================
            cached_documents = await cache.get_l2_cache(normalized_query, k=5)

            if cached_documents:
                logger.info(f"[API] L2 캐시 히트! 문서 {len(cached_documents)}개로 가이드 생성")

                # dict를 Document 객체로 변환
                documents_for_guide = cache._dict_to_documents(cached_documents)

                try:
                    # 가이드만 생성 (검색 생략)
                    guide_result = await run_keyword_guide_only_async(
                        request.summary,
                        documents_for_guide
                    )
                    keyword_guide = guide_result.get("keyword_guide", {})
                except Exception as e:
                    logger.error(f"[API] L2 캐시 히트 후 가이드 생성 실패: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"가이드 생성 중 오류가 발생했습니다: {str(e)}"
                    )

                if isinstance(keyword_guide, str):
                    keyword_guide = {
                        "guide_items": [{"topic": "응답", "points": [keyword_guide]}]
                    }

                processing_time_ms = (time.perf_counter() - start_time) * 1000

                # L1 캐시에 저장
                l1_data = cache.build_l1_response(
                    extracted_keywords="(L2 cached)",
                    documents=documents_for_guide,
                    keyword_guide=keyword_guide
                )
                await cache.set_l1_cache(normalized_query, l1_data)

                return KeywordGuideResponse(
                    original_summary=request.summary,
                    search_method=cache.get_search_method_display("l2_hit"),
                    extracted_keywords="(L2 cached)",
                    keyword_guide=keyword_guide,
                    processing_time_ms=round(processing_time_ms, 2)
                )

            # ==========================================
            # Step 3: 캐시 미스 - 전체 처리
            # ==========================================
            logger.info("[API] 캐시 미스 - 키워드 추출 + 검색 + 가이드 생성 수행")

            try:
                # 키워드 추출 + 검색 수행
                search_result = await run_keyword_search_only_async(request.summary)
                raw_documents = search_result.get("documents", [])
                extracted_keywords = search_result.get("search_query", "")

                # L2 캐시에 검색 결과 저장
                if raw_documents:
                    await cache.set_l2_cache(normalized_query, raw_documents, k=5)

                # 가이드 생성
                guide_result = await run_keyword_guide_only_async(
                    request.summary,
                    raw_documents
                )
                keyword_guide = guide_result.get("keyword_guide", {})

            except Exception as e:
                logger.error(f"[API] 키워드 추출 + 핵심 가이드 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"처리 중 오류가 발생했습니다: {str(e)}"
                )

            if isinstance(keyword_guide, str):
                keyword_guide = {
                    "guide_items": [{"topic": "응답", "points": [keyword_guide]}]
                }

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            # L1 캐시에 저장
            l1_data = cache.build_l1_response(
                extracted_keywords=extracted_keywords,
                documents=raw_documents if raw_documents else [],
                keyword_guide=keyword_guide
            )
            await cache.set_l1_cache(normalized_query, l1_data)

            response = KeywordGuideResponse(
                original_summary=request.summary,
                search_method=cache.get_search_method_display("miss"),
                extracted_keywords=extracted_keywords,
                keyword_guide=keyword_guide,
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
# API 3: 직접 임베딩 + 긴 가이드 생성
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
    - **캐싱 적용**: L1(응답 전체), L2(검색 결과) 캐싱

    **캐시 흐름:**
    1. L1 히트 → 즉시 응답 (~50ms)
    2. L2 히트 → 검색 생략, LLM만 호출 (~500ms)
    3. 캐시 미스 → 전체 처리 (~2000ms)

    **비교 대상:** /consultation/assist (키워드 추출 후 긴 가이드 생성)
    """,
    response_model=DirectFullGuideResponse
)
async def direct_full_guide(request: ComparisonRequest):
    """
    직접 임베딩 + 긴 가이드 생성 API (DirectFullCacheHelper 사용)

    캐시 동작:
    - L1 캐시: direct_full_guide:{hash} → 전체 응답
    - L2 캐시: direct:{hash} → 직접 임베딩 기반 검색 결과
    """
    start_time = time.perf_counter()
    cache = DirectFullCacheHelper

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 직접 임베딩 + 긴 가이드: '{request.summary[:50]}...'")

            # 질문 정규화 (캐시 키 생성용)
            normalized_query = await cache.get_normalized_query(request.summary, use_llm=True)

            # ==========================================
            # Step 1: L1 캐시 확인 (전체 응답)
            # ==========================================
            cached_response = await cache.get_l1_cache(normalized_query)
            if cached_response:
                processing_time_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[API] L1 캐시 히트! 소요시간: {processing_time_ms:.2f}ms")

                response_guide = cached_response.get("response_guide", {})
                if isinstance(response_guide, str):
                    response_guide = {
                        "announcement": {"title": "안내 멘트", "items": [response_guide]},
                        "cautions": {"title": "주의사항", "items": []},
                        "check_required": {"title": "확인 필요 사항", "items": []},
                        "next_steps": {"title": "다음 단계 안내", "items": []}
                    }

                return DirectFullGuideResponse(
                    original_summary=request.summary,
                    search_method=cache.get_search_method_display("l1_hit"),
                    response_guide=response_guide,
                    processing_time_ms=round(processing_time_ms, 2)
                )

            # ==========================================
            # Step 2: L2 캐시 확인 (검색 결과만)
            # ==========================================
            cached_documents = await cache.get_l2_cache(normalized_query, k=5)

            if cached_documents:
                logger.info(f"[API] L2 캐시 히트! 문서 {len(cached_documents)}개로 가이드 생성")

                # dict를 Document 객체로 변환
                documents_for_guide = cache._dict_to_documents(cached_documents)

                try:
                    # 긴 가이드 생성 (검색 생략)
                    guide_result = await run_response_guide_only_async(
                        request.summary,
                        documents_for_guide
                    )
                    response_guide = guide_result.get("response_guide", {})
                except Exception as e:
                    logger.error(f"[API] L2 캐시 히트 후 가이드 생성 실패: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"가이드 생성 중 오류가 발생했습니다: {str(e)}"
                    )

                if isinstance(response_guide, str):
                    response_guide = {
                        "announcement": {"title": "안내 멘트", "items": [response_guide]},
                        "cautions": {"title": "주의사항", "items": []},
                        "check_required": {"title": "확인 필요 사항", "items": []},
                        "next_steps": {"title": "다음 단계 안내", "items": []}
                    }

                processing_time_ms = (time.perf_counter() - start_time) * 1000

                # L1 캐시에 저장
                l1_data = cache.build_l1_response(
                    documents=documents_for_guide,
                    response_guide=response_guide
                )
                await cache.set_l1_cache(normalized_query, l1_data)

                return DirectFullGuideResponse(
                    original_summary=request.summary,
                    search_method=cache.get_search_method_display("l2_hit"),
                    response_guide=response_guide,
                    processing_time_ms=round(processing_time_ms, 2)
                )

            # ==========================================
            # Step 3: 캐시 미스 - 전체 처리
            # ==========================================
            logger.info("[API] 캐시 미스 - 검색 + 긴 가이드 생성 수행")

            try:
                # 직접 임베딩 검색 수행
                raw_documents = await run_direct_search_only_async(request.summary)

                # L2 캐시에 검색 결과 저장
                if raw_documents:
                    await cache.set_l2_cache(normalized_query, raw_documents, k=5)

                # 긴 가이드 생성
                guide_result = await run_response_guide_only_async(
                    request.summary,
                    raw_documents
                )
                response_guide = guide_result.get("response_guide", {})

            except Exception as e:
                logger.error(f"[API] 직접 임베딩 + 긴 가이드 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"처리 중 오류가 발생했습니다: {str(e)}"
                )

            if isinstance(response_guide, str):
                response_guide = {
                    "announcement": {"title": "안내 멘트", "items": [response_guide]},
                    "cautions": {"title": "주의사항", "items": []},
                    "check_required": {"title": "확인 필요 사항", "items": []},
                    "next_steps": {"title": "다음 단계 안내", "items": []}
                }

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            # L1 캐시에 저장
            l1_data = cache.build_l1_response(
                documents=raw_documents if raw_documents else [],
                response_guide=response_guide
            )
            await cache.set_l1_cache(normalized_query, l1_data)

            response = DirectFullGuideResponse(
                original_summary=request.summary,
                search_method=cache.get_search_method_display("miss"),
                response_guide=response_guide,
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
