"""
===========================================
신입 상담원용 API 라우터
===========================================

이 모듈은 신입 상담원을 위한 API를 제공합니다.
상담 내용을 입력받아 다음을 수행합니다:
1. 질문 확장 + 카테고리 판별 (병렬)
2. 직접 임베딩 벡터 검색
3. 핵심 가이드 생성

엔드포인트:
    POST /consultation/assist - 상담 지원 요청 (직접 임베딩 + 핵심 가이드)

캐싱:
    - L1 캐시: 정규화된 질문 → 전체 응답
    - L2 캐시: 정규화된 질문 → 검색 결과 (direct 기반)
"""

import logging
import time
import asyncio
import hashlib

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.models import (
    ConsultationRequest,
    KeywordGuideResponse,
    ErrorResponse
)
from app.agent.workflow import run_keyword_guide_only_async
from app.agent.nodes import expand_query_async, detect_category_with_llm
from app.utils.query_normalizer import normalize_query
from app.database import get_vector_db_manager
from app.utils import request_limiter
from app.utils.cache_helpers import DirectKeywordCacheHelper

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
    summary="실시간 상담 지원 (직접 임베딩 + 핵심 가이드)",
    description="""
    실시간 고객 상담 중 상담원을 지원하는 핵심 API입니다.

    **입력:** 현재 진행 중인 상담 내용의 요약문 (STT 또는 상담원 입력)

    **처리 과정:**
    1. **질문 확장**: 상담 요약문을 벡터 검색에 최적화된 형태로 확장
    2. **카테고리 판별 (LLM)**: mobile, internet, tv, bundle, membership 중 관련 카테고리 자동 식별
    3. **벡터 검색**: 카테고리 필터링된 문서에서 유사도 기반 검색 (ChromaDB/PGVector)
    4. **핵심 가이드 생성**: 검색된 약관/규정에서 상담에 필요한 핵심 정보만 추출

    **카테고리 자동 판별:**
    - mobile: 모바일/휴대폰 요금제, 5G/LTE, 데이터, 통화, 로밍
    - internet: 인터넷 요금제, 광랜, 기가인터넷, 회선 속도
    - tv: TV/IPTV 요금제, 올레tv, 채널, VOD, 셋톱박스
    - bundle: 결합상품, 가족결합, 묶음할인
    - membership: 멤버십, 포인트, VIP 혜택

    **캐싱 적용:** L1(전체 응답), L2(검색 결과)

    **응답 시간:**
    - L1 캐시 히트: ~50ms
    - L2 캐시 히트: ~500ms
    - 캐시 미스: ~2000ms
    """,
    response_model=KeywordGuideResponse,
    responses={
        200: {
            "description": "성공적으로 처리됨",
            "content": {
                "application/json": {
                    "example": {
                        "original_summary": "[모바일] 고객이 현재 5G 스탠다드 요금제 36개월 약정 중이며, 14개월 사용 후 해지 희망. 위약금과 단말 할부금 잔액 문의.",
                        "search_method": "direct_embedding",
                        "extracted_keywords": None,
                        "keyword_guide": {
                            "guide_items": [
                                {"topic": "약정 위약금", "points": ["36개월 약정 중 14개월 사용", "잔여 22개월분 할인반환금 발생", "위약금 = 잔여개월 × 월 할인액"]},
                                {"topic": "단말 할부금", "points": ["잔여 할부금 일시납 또는 승계 가능", "할부원금 잔액 확인 필요"]},
                                {"topic": "확인사항", "points": ["정확한 가입일자 조회", "결합상품 여부 확인", "번호이동 여부"]}
                            ]
                        },
                        "processing_time_ms": 1850.5
                    }
                }
            }
        }
    }
)
async def assist_consultation(request: ConsultationRequest):
    """
    상담 지원 요청 처리 (직접 임베딩 + 핵심 가이드, 병렬 처리 방식)

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
            logger.info(f"[API] 상담 지원 요청: '{request.summary[:50]}...'")

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

                # 2. 벡터 검색 (확장된 쿼리 사용)
                db_manager = get_vector_db_manager()
                raw_documents = await asyncio.to_thread(
                    db_manager.similarity_search_by_categories,
                    expanded_query,
                    categories,
                    5
                )

                # 3. 중복 제거 (MD5 해시 기반)
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
        logger.error(f"[API] 상담 지원 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"처리 중 오류가 발생했습니다: {str(e)}"
        )
