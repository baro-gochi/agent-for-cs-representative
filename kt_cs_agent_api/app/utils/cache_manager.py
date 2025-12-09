"""
===========================================
Redis 기반 캐싱 매니저
===========================================

이 모듈은 두 레벨의 캐싱을 제공합니다:

레벨 1 (L1): 질문 → 전체 응답 캐싱
    - key: 정규화된 질문의 해시
    - value: LLM이 생성한 전체 응답 (JSON)
    - TTL: CACHE_L1_TTL (기본 1시간)

레벨 2 (L2): 벡터 검색 결과 캐싱
    - key: 검색 쿼리의 해시
    - value: 상위 N개 문서 ID 및 메타데이터 리스트
    - TTL: CACHE_L2_TTL (기본 2시간)

사용 예시:
    from app.utils.cache_manager import cache_manager

    # L1 캐시 조회/저장
    cached = await cache_manager.get_l1_cache(normalized_question)
    if not cached:
        result = await generate_response(...)
        await cache_manager.set_l1_cache(normalized_question, result)

    # L2 캐시 조회/저장
    cached_docs = await cache_manager.get_l2_cache(query_hash)
    if not cached_docs:
        docs = vector_search(...)
        await cache_manager.set_l2_cache(query_hash, docs)
"""

import json
import hashlib
import logging
from typing import Optional, Dict, Any, List
from functools import lru_cache

import redis.asyncio as redis
from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Redis 기반 캐싱 매니저

    두 레벨의 캐싱을 지원합니다:
    - L1: 질문 → 전체 응답 캐싱
    - L2: 벡터 검색 결과 캐싱
    """

    # 캐시 키 프리픽스
    L1_PREFIX = "l1:response:"     # L1 캐시 (질문→응답)
    L2_PREFIX = "l2:search:"       # L2 캐시 (검색 결과)
    NORM_PREFIX = "norm:query:"    # 정규화된 쿼리 캐시

    def __init__(self):
        self._client: Optional[Redis] = None
        self._connected: bool = False

    async def connect(self) -> bool:
        """
        Redis 연결 초기화

        Returns:
            bool: 연결 성공 여부
        """
        if not settings.CACHE_ENABLED:
            logger.info("[Cache] 캐싱 비활성화됨")
            return False

        if self._connected and self._client:
            return True

        try:
            self._client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )

            # 연결 테스트
            await self._client.ping()
            self._connected = True
            logger.info(f"[Cache] Redis 연결 성공: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            return True

        except Exception as e:
            logger.warning(f"[Cache] Redis 연결 실패: {e}")
            self._connected = False
            self._client = None
            return False

    async def disconnect(self):
        """Redis 연결 종료"""
        if self._client:
            await self._client.close()
            self._connected = False
            self._client = None
            logger.info("[Cache] Redis 연결 종료")

    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return self._connected and self._client is not None

    # ==========================================
    # 해시 유틸리티
    # ==========================================

    @staticmethod
    def generate_hash(text: str) -> str:
        """
        텍스트의 SHA256 해시 생성

        Args:
            text: 해시할 텍스트

        Returns:
            str: 64자 해시 문자열
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    @staticmethod
    def generate_short_hash(text: str, length: int = 16) -> str:
        """
        텍스트의 짧은 해시 생성 (디버깅용)

        Args:
            text: 해시할 텍스트
            length: 해시 길이 (기본 16자)

        Returns:
            str: 지정된 길이의 해시 문자열
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:length]

    # ==========================================
    # L1 캐시: 질문 → 전체 응답
    # ==========================================

    async def get_l1_cache(self, normalized_question: str) -> Optional[Dict[str, Any]]:
        """
        L1 캐시에서 응답 조회

        Args:
            normalized_question: 정규화된 질문 텍스트

        Returns:
            Optional[Dict]: 캐시된 응답 또는 None
        """
        if not self.is_connected():
            return None

        try:
            key = f"{self.L1_PREFIX}{self.generate_hash(normalized_question)}"
            cached = await self._client.get(key)

            if cached:
                logger.info(f"[Cache] L1 HIT: {self.generate_short_hash(normalized_question)}")
                return json.loads(cached)

            logger.debug(f"[Cache] L1 MISS: {self.generate_short_hash(normalized_question)}")
            return None

        except Exception as e:
            logger.warning(f"[Cache] L1 조회 오류: {e}")
            return None

    async def set_l1_cache(
        self,
        normalized_question: str,
        response: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        L1 캐시에 응답 저장

        Args:
            normalized_question: 정규화된 질문 텍스트
            response: 저장할 응답 데이터
            ttl: TTL (초), None이면 기본값 사용

        Returns:
            bool: 저장 성공 여부
        """
        if not self.is_connected():
            return False

        try:
            key = f"{self.L1_PREFIX}{self.generate_hash(normalized_question)}"
            value = json.dumps(response, ensure_ascii=False)
            cache_ttl = ttl or settings.CACHE_L1_TTL

            await self._client.setex(key, cache_ttl, value)
            logger.info(f"[Cache] L1 SET: {self.generate_short_hash(normalized_question)}, TTL={cache_ttl}s")
            return True

        except Exception as e:
            logger.warning(f"[Cache] L1 저장 오류: {e}")
            return False

    # ==========================================
    # L2 캐시: 벡터 검색 결과
    # ==========================================

    async def get_l2_cache(self, query: str, k: int = 5) -> Optional[List[Dict[str, Any]]]:
        """
        L2 캐시에서 검색 결과 조회

        Args:
            query: 검색 쿼리
            k: 검색 결과 개수

        Returns:
            Optional[List]: 캐시된 문서 리스트 또는 None
        """
        if not self.is_connected():
            return None

        try:
            # 쿼리 + k값을 조합하여 캐시 키 생성
            cache_key_input = f"{query}|k={k}"
            key = f"{self.L2_PREFIX}{self.generate_hash(cache_key_input)}"
            cached = await self._client.get(key)

            if cached:
                logger.info(f"[Cache] L2 HIT: {self.generate_short_hash(cache_key_input)}")
                return json.loads(cached)

            logger.debug(f"[Cache] L2 MISS: {self.generate_short_hash(cache_key_input)}")
            return None

        except Exception as e:
            logger.warning(f"[Cache] L2 조회 오류: {e}")
            return None

    async def set_l2_cache(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        k: int = 5,
        ttl: Optional[int] = None
    ) -> bool:
        """
        L2 캐시에 검색 결과 저장

        Args:
            query: 검색 쿼리
            documents: 저장할 문서 리스트 (직렬화 가능한 형태)
            k: 검색 결과 개수
            ttl: TTL (초), None이면 기본값 사용

        Returns:
            bool: 저장 성공 여부
        """
        if not self.is_connected():
            return False

        try:
            cache_key_input = f"{query}|k={k}"
            key = f"{self.L2_PREFIX}{self.generate_hash(cache_key_input)}"
            value = json.dumps(documents, ensure_ascii=False)
            cache_ttl = ttl or settings.CACHE_L2_TTL

            await self._client.setex(key, cache_ttl, value)
            logger.info(f"[Cache] L2 SET: {self.generate_short_hash(cache_key_input)}, TTL={cache_ttl}s")
            return True

        except Exception as e:
            logger.warning(f"[Cache] L2 저장 오류: {e}")
            return False

    # ==========================================
    # 정규화 쿼리 캐시
    # ==========================================

    async def get_normalized_query(self, original_query: str) -> Optional[str]:
        """
        정규화된 쿼리 조회 (LLM 호출 절약용)

        Args:
            original_query: 원본 질문

        Returns:
            Optional[str]: 캐시된 정규화 쿼리 또는 None
        """
        if not self.is_connected():
            return None

        try:
            key = f"{self.NORM_PREFIX}{self.generate_hash(original_query)}"
            cached = await self._client.get(key)

            if cached:
                logger.debug(f"[Cache] NORM HIT: {self.generate_short_hash(original_query)}")
                return cached

            return None

        except Exception as e:
            logger.warning(f"[Cache] NORM 조회 오류: {e}")
            return None

    async def set_normalized_query(
        self,
        original_query: str,
        normalized_query: str,
        ttl: int = 86400  # 기본 24시간
    ) -> bool:
        """
        정규화된 쿼리 저장

        Args:
            original_query: 원본 질문
            normalized_query: 정규화된 질문
            ttl: TTL (초), 기본 24시간

        Returns:
            bool: 저장 성공 여부
        """
        if not self.is_connected():
            return False

        try:
            key = f"{self.NORM_PREFIX}{self.generate_hash(original_query)}"
            await self._client.setex(key, ttl, normalized_query)
            logger.debug(f"[Cache] NORM SET: {self.generate_short_hash(original_query)}")
            return True

        except Exception as e:
            logger.warning(f"[Cache] NORM 저장 오류: {e}")
            return False

    # ==========================================
    # 캐시 관리
    # ==========================================

    async def invalidate_l1_cache(self, normalized_question: str) -> bool:
        """L1 캐시 특정 항목 무효화"""
        if not self.is_connected():
            return False

        try:
            key = f"{self.L1_PREFIX}{self.generate_hash(normalized_question)}"
            await self._client.delete(key)
            logger.info(f"[Cache] L1 INVALIDATE: {self.generate_short_hash(normalized_question)}")
            return True
        except Exception as e:
            logger.warning(f"[Cache] L1 무효화 오류: {e}")
            return False

    async def invalidate_all_l1(self) -> int:
        """모든 L1 캐시 무효화"""
        if not self.is_connected():
            return 0

        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await self._client.scan(cursor, match=f"{self.L1_PREFIX}*", count=100)
                if keys:
                    deleted += await self._client.delete(*keys)
                if cursor == 0:
                    break
            logger.info(f"[Cache] L1 전체 무효화: {deleted}개 삭제")
            return deleted
        except Exception as e:
            logger.warning(f"[Cache] L1 전체 무효화 오류: {e}")
            return 0

    async def invalidate_all_l2(self) -> int:
        """모든 L2 캐시 무효화"""
        if not self.is_connected():
            return 0

        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await self._client.scan(cursor, match=f"{self.L2_PREFIX}*", count=100)
                if keys:
                    deleted += await self._client.delete(*keys)
                if cursor == 0:
                    break
            logger.info(f"[Cache] L2 전체 무효화: {deleted}개 삭제")
            return deleted
        except Exception as e:
            logger.warning(f"[Cache] L2 전체 무효화 오류: {e}")
            return 0

    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        캐시 통계 조회

        Returns:
            Dict: 캐시 통계 정보
        """
        if not self.is_connected():
            return {"connected": False, "error": "Redis 연결 안됨"}

        try:
            # L1 캐시 키 개수
            l1_count = 0
            cursor = 0
            while True:
                cursor, keys = await self._client.scan(cursor, match=f"{self.L1_PREFIX}*", count=100)
                l1_count += len(keys)
                if cursor == 0:
                    break

            # L2 캐시 키 개수
            l2_count = 0
            cursor = 0
            while True:
                cursor, keys = await self._client.scan(cursor, match=f"{self.L2_PREFIX}*", count=100)
                l2_count += len(keys)
                if cursor == 0:
                    break

            # Redis 서버 정보
            info = await self._client.info(section="memory")

            return {
                "connected": True,
                "l1_cache_count": l1_count,
                "l2_cache_count": l2_count,
                "used_memory": info.get("used_memory_human", "N/A"),
                "used_memory_peak": info.get("used_memory_peak_human", "N/A"),
                "l1_ttl_seconds": settings.CACHE_L1_TTL,
                "l2_ttl_seconds": settings.CACHE_L2_TTL,
            }

        except Exception as e:
            logger.warning(f"[Cache] 통계 조회 오류: {e}")
            return {"connected": True, "error": str(e)}


# 싱글톤 인스턴스
cache_manager = CacheManager()


async def get_cache_manager() -> CacheManager:
    """
    캐시 매니저 인스턴스 반환 (의존성 주입용)

    자동으로 연결을 시도합니다.
    """
    if not cache_manager.is_connected():
        await cache_manager.connect()
    return cache_manager
