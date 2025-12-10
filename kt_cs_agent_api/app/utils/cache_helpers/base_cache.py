"""
캐시 헬퍼 베이스 클래스

공통 기능만 제공하고, 각 API별 헬퍼에서 상속받아 사용합니다.
"""

import logging
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod

from langchain_core.documents import Document

from app.utils.cache_manager import cache_manager
from app.utils.query_normalizer import normalize_query
from app.config import settings

logger = logging.getLogger(__name__)


class BaseCacheHelper(ABC):
    """캐시 헬퍼 베이스 클래스"""

    # 서브클래스에서 정의해야 할 속성
    L1_PREFIX: str = ""  # 예: "consultation", "direct_keyword"
    L2_PREFIX: str = ""  # 예: "keyword", "direct"

    @classmethod
    def is_cache_enabled(cls) -> bool:
        """캐시 사용 가능 여부 확인"""
        return settings.CACHE_ENABLED and cache_manager.is_connected()

    @classmethod
    async def get_normalized_query(cls, query: str, use_llm: bool = True) -> str:
        """질문 정규화"""
        return await normalize_query(query, use_llm=use_llm)

    @classmethod
    def _get_l1_key(cls, normalized_query: str) -> str:
        """L1 캐시 키 생성"""
        return f"{cls.L1_PREFIX}:{normalized_query}"

    @classmethod
    def _get_l2_key(cls, normalized_query: str) -> str:
        """L2 캐시 키 생성"""
        return f"{cls.L2_PREFIX}:{normalized_query}"

    # ==========================================
    # L1 캐시 (전체 응답)
    # ==========================================

    @classmethod
    async def get_l1_cache(cls, normalized_query: str) -> Optional[Dict[str, Any]]:
        """L1 캐시에서 전체 응답 조회"""
        if not cls.is_cache_enabled():
            return None

        try:
            cache_key = cls._get_l1_key(normalized_query)
            return await cache_manager.get_l1_cache(cache_key)
        except Exception as e:
            logger.warning(f"[{cls.L1_PREFIX}] L1 캐시 조회 오류: {e}")
            return None

    @classmethod
    async def set_l1_cache(cls, normalized_query: str, response: Dict[str, Any]):
        """L1 캐시에 전체 응답 저장"""
        if not cls.is_cache_enabled():
            return

        try:
            cache_key = cls._get_l1_key(normalized_query)
            await cache_manager.set_l1_cache(cache_key, response)
            logger.debug(f"[{cls.L1_PREFIX}] L1 캐시 저장 완료")
        except Exception as e:
            logger.warning(f"[{cls.L1_PREFIX}] L1 캐시 저장 오류: {e}")

    # ==========================================
    # L2 캐시 (검색 결과)
    # ==========================================

    @classmethod
    async def get_l2_cache(cls, normalized_query: str, k: int = 5) -> Optional[List[Dict]]:
        """L2 캐시에서 검색 결과 조회"""
        if not cls.is_cache_enabled():
            return None

        try:
            # L2 키는 검색 타입 기반
            return await cache_manager.get_l2_cache(
                f"{cls.L2_PREFIX}:{normalized_query}",
                k=k
            )
        except Exception as e:
            logger.warning(f"[{cls.L1_PREFIX}] L2 캐시 조회 오류: {e}")
            return None

    @classmethod
    async def set_l2_cache(cls, normalized_query: str, documents: List, k: int = 5):
        """L2 캐시에 검색 결과 저장"""
        if not cls.is_cache_enabled():
            return

        try:
            # Document 객체를 dict로 변환
            docs_dict = cls._documents_to_dict(documents)
            await cache_manager.set_l2_cache(
                f"{cls.L2_PREFIX}:{normalized_query}",
                docs_dict,
                k=k
            )
            logger.debug(f"[{cls.L1_PREFIX}] L2 캐시 저장 완료")
        except Exception as e:
            logger.warning(f"[{cls.L1_PREFIX}] L2 캐시 저장 오류: {e}")

    # ==========================================
    # 유틸리티
    # ==========================================

    @staticmethod
    def _documents_to_dict(docs: List) -> List[Dict]:
        """Document 객체를 dict로 변환"""
        result = []
        for doc in docs:
            if hasattr(doc, 'page_content'):
                result.append({
                    "page_content": doc.page_content,
                    "metadata": doc.metadata
                })
            elif isinstance(doc, dict):
                result.append(doc)
        return result

    @staticmethod
    def _dict_to_documents(docs_dict: List[Dict]) -> List[Document]:
        """dict를 Document 객체로 변환"""
        return [
            Document(
                page_content=doc.get("page_content", ""),
                metadata=doc.get("metadata", {})
            )
            for doc in docs_dict
        ]
