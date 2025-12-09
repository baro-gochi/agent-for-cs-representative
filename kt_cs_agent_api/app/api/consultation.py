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

캐싱:
    - L1 캐시: 정규화된 질문 → 전체 응답 (extracted_keywords, documents, response_guide)
    - L2 캐시: 정규화된 질문 → 검색 결과 (keyword 기반)
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
from app.agent.workflow import (
    run_keyword_search_only_async,
    run_response_guide_only_async
)
from app.utils import request_limiter
from app.utils.cache_helpers import ConsultationCacheHelper

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


def _convert_documents(documents: list, max_docs: int) -> List[DocumentInfo]:
    """문서 리스트를 DocumentInfo 리스트로 변환"""
    result = []
    for doc in documents[:max_docs]:
        # Document 객체 또는 dict 처리
        if hasattr(doc, 'page_content'):
            content = doc.page_content
            metadata = doc.metadata
        else:
            content = doc.get("page_content", "")
            metadata = doc.get("metadata", {})

        result.append(DocumentInfo(
            source=metadata.get("source", "Unknown").split("/")[-1],
            page=metadata.get("page", 0) + 1,
            content=content[:500] + "..." if len(content) > 500 else content,
            score=None
        ))
    return result


@router.post(
    "/assist",
    summary="상담 지원 요청",
    description="""
    신입 상담원을 위한 상담 지원 API입니다.

    상담 내용을 입력하면 다음을 수행합니다:
    1. AI가 상담 내용을 분석하여 핵심 키워드 추출
    2. 관련 내부 규정/약관 문서 검색
    3. 신입 상담원용 대응방안 생성

    **캐싱 적용**: L1(전체 응답), L2(검색 결과)

    **캐시 흐름:**
    1. L1 히트 → 즉시 응답 (~50ms)
    2. L2 히트 → 검색 생략, LLM만 호출 (~500ms)
    3. 캐시 미스 → 전체 처리 (~2000ms)

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
    상담 지원 요청 처리 (L1+L2 캐싱 적용)

    캐시 동작:
    - L1 캐시: 정규화된 질문 → 전체 응답
    - L2 캐시: 정규화된 질문 → 검색 결과 (keyword 기반)
    """
    start_time = time.perf_counter()
    cache = ConsultationCacheHelper

    try:
        async with request_limiter.acquire():
            logger.info(f"[API] 상담 지원 요청: '{request.summary[:50]}...'")

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
                    documents=_convert_documents(
                        cached_response.get("documents", []),
                        request.max_documents
                    ) if request.include_documents else [],
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
                    documents=_convert_documents(
                        cached_documents,
                        request.max_documents
                    ) if request.include_documents else [],
                    response_guide=response_guide,
                    processing_time_ms=round(processing_time_ms, 2)
                )

            # ==========================================
            # Step 3: 캐시 미스 - 전체 처리
            # ==========================================
            logger.info("[API] 캐시 미스 - 전체 처리 수행")

            try:
                result = await run_consultation_async(request.summary)
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

            # 문서 정보 변환
            documents: List[DocumentInfo] = []
            if request.include_documents and raw_documents:
                documents = _convert_documents(raw_documents, request.max_documents)

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
                documents=documents,
                response_guide=response_guide,
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
