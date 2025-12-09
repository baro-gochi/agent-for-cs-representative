"""
===========================================
캐싱이 적용된 LangGraph 에이전트 노드
===========================================

이 모듈은 Redis 캐싱이 적용된 노드들을 정의합니다.
기존 nodes.py의 노드들을 래핑하여 캐싱 기능을 추가합니다.

캐싱 레벨:
- L1: 정규화된 질문 → 전체 응답 캐싱 (response_guide, keyword_guide)
- L2: 검색 쿼리 → 벡터 검색 결과 캐싱 (documents)

사용 예시:
    from app.agent.cached_nodes import (
        cached_direct_embedding_search_node,
        cached_response_generator_node,
        cached_keyword_guide_node,
    )
"""

import asyncio
import json
import logging
import time
from typing import List, Dict, Any, Optional

from langchain_core.documents import Document

from app.agent.state import AgentState
from app.agent.nodes import (
    analyzer_node,
    search_node,
    response_generator_node,
    direct_embedding_search_node,
    keyword_guide_node,
)
from app.config import settings
from app.database import get_vector_db_manager
from app.utils.cache_manager import cache_manager
from app.utils.query_normalizer import normalize_query

logger = logging.getLogger(__name__)


def documents_to_dict(docs: List[Document]) -> List[Dict[str, Any]]:
    """
    Document 객체를 JSON 직렬화 가능한 딕셔너리로 변환

    Args:
        docs: Document 객체 리스트

    Returns:
        List[Dict]: 직렬화 가능한 딕셔너리 리스트
    """
    return [
        {
            "page_content": doc.page_content,
            "metadata": doc.metadata
        }
        for doc in docs
    ]


def dict_to_documents(doc_dicts: List[Dict[str, Any]]) -> List[Document]:
    """
    딕셔너리를 Document 객체로 변환

    Args:
        doc_dicts: 딕셔너리 리스트

    Returns:
        List[Document]: Document 객체 리스트
    """
    return [
        Document(
            page_content=d["page_content"],
            metadata=d.get("metadata", {})
        )
        for d in doc_dicts
    ]


async def ensure_cache_connected():
    """캐시 연결 확인 및 연결"""
    if not cache_manager.is_connected():
        await cache_manager.connect()


# ==========================================
# L2 캐싱: 벡터 검색 결과 캐싱
# ==========================================

async def cached_direct_embedding_search_node(state: AgentState) -> dict:
    """
    [캐싱 적용] 요약문 직접 임베딩 검색

    L2 캐시를 확인하여 이전에 같은 쿼리로 검색한 결과가 있으면
    캐시된 결과를 반환합니다.

    입력 (state):
        - summary: 상담 내용 요약 텍스트

    출력 (dict):
        - documents: 검색된 Document 리스트
        - cache_hit: 캐시 히트 여부
        - cache_level: 캐시 레벨 (L2 또는 None)
    """
    summary = state["summary"]
    logger.info(f"[CachedDirectSearch] 검색 시작: '{summary[:50]}...'")
    start_time = time.perf_counter()

    await ensure_cache_connected()

    # L2 캐시 확인
    if cache_manager.is_connected():
        cached_docs = await cache_manager.get_l2_cache(summary, k=5)
        if cached_docs:
            duration = time.perf_counter() - start_time
            logger.info(f"[CachedDirectSearch] L2 캐시 히트! 소요시간: {duration:.3f}초")
            return {
                "documents": dict_to_documents(cached_docs),
                "cache_hit": True,
                "cache_level": "L2"
            }

    # 캐시 미스 - 실제 검색 수행
    result = direct_embedding_search_node(state)
    documents = result["documents"]

    # L2 캐시에 저장
    if cache_manager.is_connected() and documents:
        await cache_manager.set_l2_cache(
            summary,
            documents_to_dict(documents),
            k=5
        )

    duration = time.perf_counter() - start_time
    logger.info(f"[CachedDirectSearch] 완료 (캐시 미스) - 소요시간: {duration:.3f}초")

    return {
        "documents": documents,
        "cache_hit": False,
        "cache_level": None
    }


async def cached_search_node(state: AgentState) -> dict:
    """
    [캐싱 적용] 하이브리드 검색

    L2 캐시를 확인하여 이전에 같은 쿼리로 검색한 결과가 있으면
    캐시된 결과를 반환합니다.

    입력 (state):
        - target_doc_name: 대상 문서 이름
        - search_query: 검색 키워드

    출력 (dict):
        - documents: 검색된 Document 리스트
        - cache_hit: 캐시 히트 여부
        - cache_level: 캐시 레벨 (L2 또는 None)
    """
    query = state["search_query"]
    target_name = state.get("target_doc_name", "없음")

    logger.info(f"[CachedSearch] 검색 시작 - 문서: [{target_name}], 키워드: [{query}]")
    start_time = time.perf_counter()

    await ensure_cache_connected()

    # 캐시 키 생성 (타겟 문서명 + 쿼리)
    cache_key = f"{target_name}|{query}"

    # L2 캐시 확인
    if cache_manager.is_connected():
        cached_docs = await cache_manager.get_l2_cache(cache_key, k=5)
        if cached_docs:
            duration = time.perf_counter() - start_time
            logger.info(f"[CachedSearch] L2 캐시 히트! 소요시간: {duration:.3f}초")
            return {
                "documents": dict_to_documents(cached_docs),
                "cache_hit": True,
                "cache_level": "L2"
            }

    # 캐시 미스 - 실제 검색 수행
    result = search_node(state)
    documents = result["documents"]

    # L2 캐시에 저장
    if cache_manager.is_connected() and documents:
        await cache_manager.set_l2_cache(
            cache_key,
            documents_to_dict(documents),
            k=5
        )

    duration = time.perf_counter() - start_time
    logger.info(f"[CachedSearch] 완료 (캐시 미스) - 소요시간: {duration:.3f}초")

    return {
        "documents": documents,
        "cache_hit": False,
        "cache_level": None
    }


# ==========================================
# L1 캐싱: 전체 응답 캐싱
# ==========================================

async def cached_response_generator_node(state: AgentState) -> dict:
    """
    [캐싱 적용] 신입 상담원용 대응방안 생성

    L1 캐시를 확인하여 정규화된 질문에 대한 응답이
    이미 캐시되어 있으면 캐시된 결과를 반환합니다.

    입력 (state):
        - summary: 원본 상담 요약
        - documents: 검색된 문서 리스트

    출력 (dict):
        - response_guide: 생성된 대응방안 (JSON)
        - cache_hit: 캐시 히트 여부
        - cache_level: 캐시 레벨 (L1 또는 None)
    """
    summary = state["summary"]
    logger.info(f"[CachedResponseGen] 대응방안 생성 시작: '{summary[:50]}...'")
    start_time = time.perf_counter()

    await ensure_cache_connected()

    # 질문 정규화
    normalized_summary = await normalize_query(summary, use_llm=True)
    logger.debug(f"[CachedResponseGen] 정규화된 질문: '{normalized_summary}'")

    # L1 캐시 키 생성 (정규화된 질문 + 노드 타입)
    cache_key = f"response:{normalized_summary}"

    # L1 캐시 확인
    if cache_manager.is_connected():
        cached_response = await cache_manager.get_l1_cache(cache_key)
        if cached_response:
            duration = time.perf_counter() - start_time
            logger.info(f"[CachedResponseGen] L1 캐시 히트! 소요시간: {duration:.3f}초")
            return {
                "response_guide": cached_response,
                "cache_hit": True,
                "cache_level": "L1",
                "normalized_query": normalized_summary
            }

    # 캐시 미스 - 실제 응답 생성
    result = response_generator_node(state)
    response_guide = result["response_guide"]

    # L1 캐시에 저장
    if cache_manager.is_connected() and response_guide:
        await cache_manager.set_l1_cache(cache_key, response_guide)

    duration = time.perf_counter() - start_time
    logger.info(f"[CachedResponseGen] 완료 (캐시 미스) - 소요시간: {duration:.3f}초")

    return {
        "response_guide": response_guide,
        "cache_hit": False,
        "cache_level": None,
        "normalized_query": normalized_summary
    }


async def cached_keyword_guide_node(state: AgentState) -> dict:
    """
    [캐싱 적용] 핵심 키워드 기반 간결 가이드 생성

    L1 캐시를 확인하여 정규화된 질문에 대한 가이드가
    이미 캐시되어 있으면 캐시된 결과를 반환합니다.

    입력 (state):
        - summary: 원본 상담 요약
        - documents: 검색된 문서 리스트

    출력 (dict):
        - keyword_guide: 생성된 핵심 가이드 (JSON)
        - cache_hit: 캐시 히트 여부
        - cache_level: 캐시 레벨 (L1 또는 None)
    """
    summary = state["summary"]
    logger.info(f"[CachedKeywordGuide] 핵심 가이드 생성 시작: '{summary[:50]}...'")
    start_time = time.perf_counter()

    await ensure_cache_connected()

    # 질문 정규화
    normalized_summary = await normalize_query(summary, use_llm=True)
    logger.debug(f"[CachedKeywordGuide] 정규화된 질문: '{normalized_summary}'")

    # L1 캐시 키 생성 (정규화된 질문 + 노드 타입)
    cache_key = f"keyword:{normalized_summary}"

    # L1 캐시 확인
    if cache_manager.is_connected():
        cached_guide = await cache_manager.get_l1_cache(cache_key)
        if cached_guide:
            duration = time.perf_counter() - start_time
            logger.info(f"[CachedKeywordGuide] L1 캐시 히트! 소요시간: {duration:.3f}초")
            return {
                "keyword_guide": cached_guide,
                "cache_hit": True,
                "cache_level": "L1",
                "normalized_query": normalized_summary
            }

    # 캐시 미스 - 실제 가이드 생성
    result = keyword_guide_node(state)
    keyword_guide = result["keyword_guide"]

    # L1 캐시에 저장
    if cache_manager.is_connected() and keyword_guide:
        await cache_manager.set_l1_cache(cache_key, keyword_guide)

    duration = time.perf_counter() - start_time
    logger.info(f"[CachedKeywordGuide] 완료 (캐시 미스) - 소요시간: {duration:.3f}초")

    return {
        "keyword_guide": keyword_guide,
        "cache_hit": False,
        "cache_level": None,
        "normalized_query": normalized_summary
    }


# ==========================================
# 풀 파이프라인 캐싱 (L1 + L2 조합)
# ==========================================

async def full_cached_pipeline(
    summary: str,
    use_l1_cache: bool = True,
    use_l2_cache: bool = True
) -> Dict[str, Any]:
    """
    완전한 캐싱 파이프라인

    L1 캐시 (전체 응답)와 L2 캐시 (검색 결과)를 모두 활용합니다.

    흐름:
    1. L1 캐시 확인 (정규화된 질문 → 전체 응답)
    2. L1 미스 시 → L2 캐시 확인 (검색 결과)
    3. L2 미스 시 → 실제 검색 수행 → L2 캐시 저장
    4. LLM 응답 생성 → L1 캐시 저장

    Args:
        summary: 상담 요약 텍스트
        use_l1_cache: L1 캐시 사용 여부
        use_l2_cache: L2 캐시 사용 여부

    Returns:
        Dict: 응답 결과 및 캐시 메타데이터
    """
    logger.info(f"[FullPipeline] 시작: '{summary[:50]}...'")
    start_time = time.perf_counter()

    await ensure_cache_connected()

    result = {
        "summary": summary,
        "normalized_query": None,
        "keyword_guide": None,
        "documents": [],
        "l1_cache_hit": False,
        "l2_cache_hit": False,
        "processing_time_ms": 0
    }

    # 1. 질문 정규화
    normalized_summary = await normalize_query(summary, use_llm=True)
    result["normalized_query"] = normalized_summary

    # 2. L1 캐시 확인
    if use_l1_cache and cache_manager.is_connected():
        cache_key = f"keyword:{normalized_summary}"
        cached_guide = await cache_manager.get_l1_cache(cache_key)
        if cached_guide:
            duration = (time.perf_counter() - start_time) * 1000
            logger.info(f"[FullPipeline] L1 캐시 히트! 소요시간: {duration:.1f}ms")
            result["keyword_guide"] = cached_guide
            result["l1_cache_hit"] = True
            result["processing_time_ms"] = duration
            return result

    # 3. L2 캐시 확인 (검색 결과)
    documents = []
    if use_l2_cache and cache_manager.is_connected():
        cached_docs = await cache_manager.get_l2_cache(summary, k=5)
        if cached_docs:
            documents = dict_to_documents(cached_docs)
            result["l2_cache_hit"] = True
            logger.info("[FullPipeline] L2 캐시 히트!")

    # 4. L2 캐시 미스 - 실제 검색 수행
    if not documents:
        state = {"summary": summary}
        search_result = direct_embedding_search_node(state)
        documents = search_result["documents"]

        # L2 캐시에 저장
        if use_l2_cache and cache_manager.is_connected() and documents:
            await cache_manager.set_l2_cache(
                summary,
                documents_to_dict(documents),
                k=5
            )

    result["documents"] = documents_to_dict(documents)

    # 5. LLM 응답 생성
    state = {"summary": summary, "documents": documents}
    guide_result = keyword_guide_node(state)
    keyword_guide = guide_result["keyword_guide"]
    result["keyword_guide"] = keyword_guide

    # 6. L1 캐시에 저장
    if use_l1_cache and cache_manager.is_connected() and keyword_guide:
        cache_key = f"keyword:{normalized_summary}"
        await cache_manager.set_l1_cache(cache_key, keyword_guide)

    duration = (time.perf_counter() - start_time) * 1000
    result["processing_time_ms"] = duration
    logger.info(f"[FullPipeline] 완료 - 소요시간: {duration:.1f}ms")

    return result


# ==========================================
# 동기 래퍼 (LangGraph 호환용)
# ==========================================

def sync_cached_direct_search(state: AgentState) -> dict:
    """동기 버전의 캐싱된 직접 검색 노드"""
    return asyncio.get_event_loop().run_until_complete(
        cached_direct_embedding_search_node(state)
    )


def sync_cached_search(state: AgentState) -> dict:
    """동기 버전의 캐싱된 검색 노드"""
    return asyncio.get_event_loop().run_until_complete(
        cached_search_node(state)
    )


def sync_cached_response_generator(state: AgentState) -> dict:
    """동기 버전의 캐싱된 응답 생성 노드"""
    return asyncio.get_event_loop().run_until_complete(
        cached_response_generator_node(state)
    )


def sync_cached_keyword_guide(state: AgentState) -> dict:
    """동기 버전의 캐싱된 키워드 가이드 노드"""
    return asyncio.get_event_loop().run_until_complete(
        cached_keyword_guide_node(state)
    )
