"""
===========================================
비교용 API 라우터
===========================================

이 모듈은 다양한 검색/가이드 생성 방식을 비교하기 위한 API를 제공합니다.

엔드포인트:
    POST /comparison/direct-keyword      - 직접 임베딩 + 핵심 가이드 생성
    POST /comparison/keyword-extraction  - 키워드 추출 + 핵심 가이드 생성
    POST /comparison/direct-full-guide   - 직접 임베딩 + 긴 가이드 생성
    POST /comparison/keyword-full-guide  - 키워드 추출 + 긴 가이드 생성 (기존 consultation 방식)

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
import asyncio
import hashlib

from fastapi import APIRouter, HTTPException

from app.models import (
    ComparisonRequest,
    ConsultationResponse,
    KeywordGuideResponse,
    DirectFullGuideResponse,
    ErrorResponse
)
from app.agent import run_consultation_async
from app.agent.workflow import (
    run_direct_search_only_async,
    run_keyword_guide_only_async,
    run_keyword_search_only_async,
    run_response_guide_only_async
)
from app.agent.nodes import expand_query_async, detect_category_with_llm
from app.utils.query_normalizer import normalize_query
from app.database import get_vector_db_manager
from app.utils import request_limiter
from app.utils.cache_helpers import (
    DirectKeywordCacheHelper,
    KeywordExtractionCacheHelper,
    DirectFullCacheHelper,
    ConsultationCacheHelper
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
    summary="[비교] 직접 임베딩 + 핵심 가이드",
    description="""
    상담 요약문을 직접 벡터 임베딩하여 검색 후, 핵심 키워드 기반 간결 가이드를 생성합니다.
    **/consultation/assist와 동일한 로직**이며, 비교 테스트용으로 제공됩니다.

    **입력:** 상담 중 요약된 고객 문의 내용

    **처리 과정:**
    1. **질문 확장 (LLM)**: 요약문을 검색에 최적화된 형태로 확장
    2. **카테고리 판별 (LLM)**: mobile, internet, tv, bundle, membership 자동 식별
    3. **벡터 검색**: 카테고리 필터 적용하여 ChromaDB/PGVector에서 유사 문서 검색
    4. **핵심 가이드 생성**: 검색된 약관에서 핵심 정보만 추출 (짧은 요점 형태)

    **카테고리 자동 판별:**
    - mobile: 5G/LTE 요금제, 데이터, 통화, 로밍, 번호이동
    - internet: 광랜, 기가인터넷, 회선, 공유기
    - tv: IPTV, 올레tv, 채널, VOD, 셋톱박스
    - bundle: 결합상품, 뭉치면올레, 가족결합
    - membership: 멤버십 포인트, VIP 혜택

    **비교 대상:** /comparison/keyword-extraction (키워드 추출 방식)

    **캐싱:** L1(전체 응답), L2(검색 결과)
    """,
    response_model=KeywordGuideResponse
)
async def direct_keyword_guide(request: ComparisonRequest):
    """
    직접 임베딩 + 핵심 가이드 생성 API (병렬 처리 방식)

    병렬 처리:
    - Task A: 질문 정규화 → 캐시 확인 (원본 질문 기반)
    - Task B: 질문 확장 → 카테고리 판별 → 벡터 검색 → 가이드 생성 (백그라운드)

    캐시 히트 시 Task B 취소하고 즉시 반환
    캐시 미스 시 Task B 결과 사용
    """
    start_time = time.perf_counter()
    cache = DirectKeywordCacheHelper

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 직접 임베딩 + 핵심 가이드: '{request.summary[:50]}...'")

            # ==========================================
            # 검색 + 가이드 생성 함수
            # ==========================================
            async def search_and_generate_guide():
                """확장 쿼리로 검색 후 가이드 생성"""
                # 1. 질문 확장 + 카테고리 판별 (병렬 처리)
                expanded_query, categories = await asyncio.gather(
                    expand_query_async(request.summary),
                    detect_category_with_llm(request.summary)
                )
                logger.info(f"[Search] 확장된 쿼리: '{expanded_query[:60]}...'")
                logger.info(f"[Search] 카테고리: {categories or '전체'}")

                # 3. 벡터 검색 (확장된 쿼리 사용)
                db_manager = get_vector_db_manager()
                raw_documents = await asyncio.to_thread(
                    db_manager.similarity_search_by_categories,
                    expanded_query,
                    categories,
                    5
                )

                # 4. 중복 제거 (MD5 해시 기반)
                seen_hashes = set()
                documents = []
                for doc in raw_documents:
                    content_hash = hashlib.md5(doc.page_content.encode()).hexdigest()
                    if content_hash not in seen_hashes:
                        documents.append(doc)
                        seen_hashes.add(content_hash)

                logger.info(f"[Search] 검색 결과: {len(raw_documents)}개 → 중복 제거 후 {len(documents)}개")

                # 4. 가이드 생성
                guide_result = await run_keyword_guide_only_async(
                    request.summary,
                    documents
                )

                return {
                    "documents": documents,
                    "keyword_guide": guide_result.get("keyword_guide", {}),
                    "expanded_query": expanded_query
                }

            # ==========================================
            # 캐시 비활성화 시: 바로 검색 실행
            # ==========================================
            if not cache.is_cache_enabled():
                logger.info("[API] 캐시 비활성화 - 검색 직접 실행")
                result = await search_and_generate_guide()

                keyword_guide = result["keyword_guide"]
                if isinstance(keyword_guide, str):
                    keyword_guide = {"guide_items": [{"topic": "응답", "points": [keyword_guide]}]}

                processing_time_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[API] 완료 (캐시 없음): {processing_time_ms:.2f}ms")

                return KeywordGuideResponse(
                    original_summary=request.summary,
                    search_method="direct_embedding (no cache)",
                    extracted_keywords=None,
                    keyword_guide=keyword_guide,
                    processing_time_ms=round(processing_time_ms, 2)
                )

            # ==========================================
            # 캐시 활성화 시: 병렬 실행
            # ==========================================
            # 검색 Task를 백그라운드로 시작
            search_task = asyncio.create_task(search_and_generate_guide())

            try:
                # ==========================================
                # Task A: 정규화 → 캐시 확인 (원본 질문 기반)
                # ==========================================
                normalized_query = await normalize_query(request.summary, use_llm=True)
                logger.info(f"[TaskA] 정규화된 캐시 키: '{normalized_query}'")

                # L1 캐시 확인
                cached_response = await cache.get_l1_cache(normalized_query)
                if cached_response:
                    # 캐시 히트! Task B 취소
                    search_task.cancel()
                    try:
                        await search_task
                    except asyncio.CancelledError:
                        logger.info("[API] 캐시 히트로 백그라운드 작업 취소됨")

                    processing_time_ms = (time.perf_counter() - start_time) * 1000
                    logger.info(f"[API] L1 캐시 히트! 소요시간: {processing_time_ms:.2f}ms")

                    keyword_guide = cached_response.get("keyword_guide", {})
                    if isinstance(keyword_guide, str):
                        keyword_guide = {"guide_items": [{"topic": "응답", "points": [keyword_guide]}]}

                    return KeywordGuideResponse(
                        original_summary=request.summary,
                        search_method=cache.get_search_method_display("l1_hit"),
                        extracted_keywords=cached_response.get("extracted_keywords"),
                        keyword_guide=keyword_guide,
                        processing_time_ms=round(processing_time_ms, 2)
                    )

                # L2 캐시 확인
                cached_documents = await cache.get_l2_cache(normalized_query, k=5)
                if cached_documents:
                    # L2 캐시 히트! Task B 취소
                    search_task.cancel()
                    try:
                        await search_task
                    except asyncio.CancelledError:
                        logger.info("[API] L2 캐시 히트로 백그라운드 작업 취소됨")

                    logger.info(f"[API] L2 캐시 히트! 문서 {len(cached_documents)}개로 가이드 생성")
                    documents_for_guide = cache._dict_to_documents(cached_documents)

                    guide_result = await run_keyword_guide_only_async(
                        request.summary,
                        documents_for_guide
                    )
                    keyword_guide = guide_result.get("keyword_guide", {})

                    if isinstance(keyword_guide, str):
                        keyword_guide = {"guide_items": [{"topic": "응답", "points": [keyword_guide]}]}

                    processing_time_ms = (time.perf_counter() - start_time) * 1000

                    # L1 캐시에 저장
                    l1_data = cache.build_l1_response(
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
                # 캐시 미스 - Task B 결과 대기
                # ==========================================
                logger.info("[API] 캐시 미스 - 백그라운드 작업 결과 대기")
                result = await search_task

                raw_documents = result["documents"]
                keyword_guide = result["keyword_guide"]

                if isinstance(keyword_guide, str):
                    keyword_guide = {"guide_items": [{"topic": "응답", "points": [keyword_guide]}]}

                # L2 캐시에 검색 결과 저장
                if raw_documents:
                    await cache.set_l2_cache(normalized_query, raw_documents, k=5)

                # L1 캐시에 저장
                l1_data = cache.build_l1_response(
                    documents=raw_documents if raw_documents else [],
                    keyword_guide=keyword_guide
                )
                await cache.set_l1_cache(normalized_query, l1_data)

                processing_time_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[API] 캐시 미스 처리 완료: {processing_time_ms:.2f}ms")

                return KeywordGuideResponse(
                    original_summary=request.summary,
                    search_method=cache.get_search_method_display("miss"),
                    extracted_keywords=None,
                    keyword_guide=keyword_guide,
                    processing_time_ms=round(processing_time_ms, 2)
                )

            except Exception as e:
                # 에러 발생 시 Task B도 취소
                search_task.cancel()
                try:
                    await search_task
                except asyncio.CancelledError:
                    pass
                raise

    except RuntimeError as e:
        if "Rate limit" in str(e):
            raise HTTPException(
                status_code=429,
                detail="요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            )
        raise
    except Exception as e:
        logger.error(f"[API] 직접 임베딩 + 핵심 가이드 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"처리 중 오류가 발생했습니다: {str(e)}"
        )


# ==========================================
# API 2: 키워드 추출 + 핵심 가이드 생성
# ==========================================

@router.post(
    "/keyword-extraction",
    summary="[비교] 키워드 추출 + 핵심 가이드",
    description="""
    상담 요약문에서 핵심 키워드를 추출한 후 검색하여 핵심 가이드를 생성합니다.
    **직접 임베딩 방식과의 검색 품질 비교**를 위한 API입니다.

    **입력:** 상담 중 요약된 고객 문의 내용

    **처리 과정:**
    1. **질문 확장 (LLM)**: 요약문을 검색에 최적화된 형태로 확장
    2. **키워드 추출 (LLM)**: 요약문에서 검색용 핵심 키워드 3~8개 추출
    3. **벡터 검색**: 추출된 키워드로 ChromaDB/PGVector에서 유사 문서 검색
    4. **핵심 가이드 생성**: 검색된 약관에서 핵심 정보만 추출

    **직접 임베딩 vs 키워드 추출:**
    - 직접 임베딩: 문장 전체의 의미를 벡터화하여 검색
    - 키워드 추출: 핵심 단어만 추출하여 검색 (검색 범위가 좁아질 수 있음)

    **비교 대상:** /comparison/direct-keyword (직접 임베딩 방식)

    **캐싱:** L1(전체 응답), L2(검색 결과)
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
            # Step 3: 캐시 미스 - 질문 확장 후 전체 처리
            # ==========================================
            logger.info("[API] 캐시 미스 - 질문 확장 + 키워드 추출 + 검색 + 가이드 생성 수행")

            try:
                # 질문 확장 (검색 품질 향상)
                expanded_query = await expand_query_async(request.summary)
                logger.info(f"[API] 확장된 쿼리: '{expanded_query[:80]}...'")

                # 확장된 쿼리로 키워드 추출 + 검색 수행
                search_result = await run_keyword_search_only_async(expanded_query)
                raw_documents = search_result.get("documents", [])
                extracted_keywords = search_result.get("search_query", "")

                # L2 캐시에 검색 결과 저장
                if raw_documents:
                    await cache.set_l2_cache(normalized_query, raw_documents, k=5)

                # 가이드 생성 (원본 질문 사용)
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
    summary="[비교] 직접 임베딩 + 상세 가이드",
    description="""
    상담 요약문을 직접 벡터 임베딩하여 검색 후, **구조화된 상세 가이드**를 생성합니다.
    **핵심 가이드 vs 상세 가이드 비교**를 위한 API입니다.

    **입력:** 상담 중 요약된 고객 문의 내용

    **처리 과정:**
    1. **질문 확장 (LLM)**: 요약문을 검색에 최적화된 형태로 확장
    2. **카테고리 판별 (LLM)**: mobile, internet, tv, bundle, membership 자동 식별
    3. **벡터 검색**: 카테고리 필터 적용하여 유사 문서 검색
    4. **상세 가이드 생성**: 검색된 약관을 바탕으로 구조화된 상세 응대 가이드 생성

    **출력 구조:**
    - announcement: 고객에게 안내할 멘트
    - cautions: 상담 시 주의사항
    - check_required: 추가 확인 필요 사항
    - next_steps: 후속 조치 안내

    **핵심 가이드 vs 상세 가이드:**
    - 핵심 가이드: 짧은 키워드/요점 형태 (상담원이 직접 말로 풀어서 설명)
    - 상세 가이드: 완성된 문장 형태의 구조화된 응대 스크립트

    **비교 대상:** /comparison/direct-keyword (핵심 가이드)

    **캐싱:** L1(전체 응답), L2(검색 결과)
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

            # ==========================================
            # Step 1: 질문 확장 (먼저 수행 - 캐시 키 생성용)
            # ==========================================
            expanded_query = await expand_query_async(request.summary)
            logger.info(f"[API] 확장된 쿼리: '{expanded_query[:80]}...'")

            # 확장된 질문을 정규화하여 캐시 키로 사용
            normalized_query = await cache.get_normalized_query(expanded_query, use_llm=True)
            logger.info(f"[API] 정규화된 캐시 키: '{normalized_query[:50]}...'")

            # ==========================================
            # Step 2: L1 캐시 확인 (전체 응답)
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
            # Step 3: L2 캐시 확인 (검색 결과만)
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
            # Step 4: 캐시 미스 - 카테고리 판별 후 검색
            # ==========================================
            logger.info("[API] 캐시 미스 - 카테고리 판별 + 검색 + 긴 가이드 생성 수행")

            try:
                # 1. 원본 질문으로 카테고리 판별 (LLM 사용)
                categories = await detect_category_with_llm(request.summary)
                logger.info(f"[API] 카테고리 판별 (LLM): {categories or '전체'}")

                # 2. 확장된 쿼리 + 카테고리 필터로 검색 (확장은 이미 완료됨)
                import asyncio
                db_manager = get_vector_db_manager()
                raw_documents = await asyncio.to_thread(
                    db_manager.similarity_search_by_categories,
                    expanded_query,
                    categories,
                    5  # k=5
                )
                logger.info(f"[API] 검색 결과: {len(raw_documents)}개 문서")

                # L2 캐시에 검색 결과 저장
                if raw_documents:
                    await cache.set_l2_cache(normalized_query, raw_documents, k=5)

                # 긴 가이드 생성 (원본 질문 사용)
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


# ==========================================
# API 4: 키워드 추출 + 긴 가이드 생성 (기존 consultation 방식)
# ==========================================

@router.post(
    "/keyword-full-guide",
    summary="[비교] 키워드 추출 + 상세 가이드 (Legacy)",
    description="""
    **기존 /consultation/assist의 레거시 방식**입니다.
    키워드 추출 후 검색하여 구조화된 상세 가이드를 생성합니다.

    **입력:** 상담 중 요약된 고객 문의 내용

    **처리 과정:**
    1. **질문 확장 (LLM)**: 요약문을 검색에 최적화된 형태로 확장
    2. **키워드 추출 (LLM)**: analyzer_node로 핵심 키워드 추출
    3. **하이브리드 검색**: search_node로 Scoped + Global 검색
    4. **상세 가이드 생성**: response_generator_node로 구조화된 응대 가이드 생성

    **출력 구조:**
    - extracted_keywords: 추출된 검색 키워드
    - target_document: 타겟 문서 (현재 미사용)
    - response_guide: 구조화된 상세 응대 가이드
      - announcement: 안내 멘트
      - cautions: 주의사항
      - check_required: 확인 필요 사항
      - next_steps: 다음 단계 안내

    **현재 메인 API와의 차이:**
    - 메인(/consultation/assist): 직접 임베딩 + 핵심 가이드 (빠름, 간결)
    - 레거시(이 API): 키워드 추출 + 상세 가이드 (상세하지만 느림)

    **비교 대상:** /consultation/assist (직접 임베딩 + 핵심 가이드)

    **캐싱:** L1(전체 응답), L2(검색 결과)
    """,
    response_model=ConsultationResponse
)
async def keyword_full_guide(request: ComparisonRequest):
    """
    키워드 추출 + 긴 가이드 생성 API (기존 consultation 방식)

    캐시 동작:
    - L1 캐시: consultation:{hash} → 전체 응답
    - L2 캐시: keyword:{hash} → 키워드 추출 기반 검색 결과
    """
    start_time = time.perf_counter()
    cache = ConsultationCacheHelper

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 키워드 추출 + 긴 가이드: '{request.summary[:50]}...'")

            # 질문 정규화 (캐시 키 생성용)
            normalized_query = await cache.get_normalized_query(request.summary, use_llm=True)

            # ==========================================
            # Step 1: L1 캐시 확인 (전체 응답)
            # ==========================================
            cached_response = await cache.get_l1_cache(normalized_query)
            if cached_response:
                processing_time_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"[API] L1 캐시 히트! 소요시간: {processing_time_ms:.2f}ms")

                # 응답 구성
                response_guide = cached_response.get("response_guide", {})
                if isinstance(response_guide, str):
                    response_guide = {
                        "announcement": {"title": "안내 멘트", "items": [response_guide]},
                        "cautions": {"title": "주의사항", "items": []},
                        "check_required": {"title": "확인 필요 사항", "items": []},
                        "next_steps": {"title": "다음 단계 안내", "items": []}
                    }

                return ConsultationResponse(
                    original_summary=request.summary,
                    extracted_keywords=cached_response.get("extracted_keywords", "") + " (L1 cached)",
                    target_document=cached_response.get("target_document", "없음"),
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
                    # 긴 가이드만 생성 (검색 생략)
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

                # 폴백
                if isinstance(response_guide, str):
                    response_guide = {
                        "announcement": {"title": "안내 멘트", "items": [response_guide]},
                        "cautions": {"title": "주의사항", "items": []},
                        "check_required": {"title": "확인 필요 사항", "items": []},
                        "next_steps": {"title": "다음 단계 안내", "items": []}
                    }

                processing_time_ms = (time.perf_counter() - start_time) * 1000

                # L1 캐시에 저장 (다음번에는 L1 히트)
                l1_data = cache.build_l1_response(
                    extracted_keywords="(L2 cached)",
                    target_document="없음",
                    documents=documents_for_guide,
                    response_guide=response_guide
                )
                await cache.set_l1_cache(normalized_query, l1_data)

                return ConsultationResponse(
                    original_summary=request.summary,
                    extracted_keywords="(L2 cached)",
                    target_document="없음",
                    response_guide=response_guide,
                    processing_time_ms=round(processing_time_ms, 2)
                )

            # ==========================================
            # Step 3: 캐시 미스 - 질문 확장 후 전체 처리
            # ==========================================
            logger.info("[API] 캐시 미스 - 질문 확장 + 전체 처리 수행")

            try:
                # 질문 확장 (검색 품질 향상)
                expanded_query = await expand_query_async(request.summary)
                logger.info(f"[API] 확장된 쿼리: '{expanded_query[:80]}...'")

                # 확장된 쿼리로 Agent 실행
                result = await run_consultation_async(expanded_query)
            except Exception as e:
                logger.error(f"[API] Agent 실행 실패: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"상담 처리 중 오류가 발생했습니다: {str(e)}"
                )

            raw_documents = result.get("documents", [])
            extracted_keywords = result.get("search_query", "")
            target_document = result.get("target_doc_name", "없음")

            # L2 캐시에 검색 결과 저장
            if raw_documents:
                await cache.set_l2_cache(normalized_query, raw_documents, k=5)

            # 처리 시간 계산
            processing_time_ms = (time.perf_counter() - start_time) * 1000

            # 응답 생성 (response_guide는 이제 JSON 구조)
            response_guide = result.get("response_guide", {})
            # 폴백: 문자열인 경우 기본 구조로 변환
            if isinstance(response_guide, str):
                response_guide = {
                    "announcement": {"title": "안내 멘트", "items": [response_guide]},
                    "cautions": {"title": "주의사항", "items": []},
                    "check_required": {"title": "확인 필요 사항", "items": []},
                    "next_steps": {"title": "다음 단계 안내", "items": []}
                }

            # L1 캐시에 저장
            l1_data = cache.build_l1_response(
                extracted_keywords=extracted_keywords,
                target_document=target_document,
                documents=raw_documents,
                response_guide=response_guide
            )
            await cache.set_l1_cache(normalized_query, l1_data)

            response = ConsultationResponse(
                original_summary=request.summary,
                extracted_keywords=extracted_keywords,
                target_document=target_document,
                response_guide=response_guide,
                processing_time_ms=round(processing_time_ms, 2)
            )

            logger.info(f"[API] 키워드 추출 + 긴 가이드 완료: {processing_time_ms:.2f}ms")
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