"""
===========================================
캐시 관리 API
===========================================

이 모듈은 캐싱 시스템 관리 기능을 제공합니다.

엔드포인트:
- GET /cache/stats: 캐시 통계 조회
- POST /cache/invalidate: 전체 캐시 무효화
- POST /cache/invalidate/{api_type}: API별 캐시 무효화
- POST /cache/cleanup: 캐시 정리 (LRU 기반 삭제)
- POST /cache/normalize-test: 질문 정규화 테스트

캐시 정리 전략:
- 각 API별로 최대 캐시 개수 제한 (기본: L1 1000개, L2 500개)
- 제한 초과 시 가장 오래된 항목부터 삭제 (LRU)
- TTL 기반 자동 만료 (L1: 1시간, L2: 2시간)
"""

import logging
import time
from typing import Optional, Literal
from enum import Enum

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.models.schemas import (
    CacheStatsResponse,
    NormalizeTestRequest,
    NormalizeTestResponse,
)
from app.utils.cache_manager import cache_manager
from app.utils.query_normalizer import normalize_query

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cache",
    tags=["캐시 관리"],
    responses={
        500: {"description": "서버 오류"}
    }
)


# ===========================================
# 상수 및 설정
# ===========================================

class ApiType(str, Enum):
    """API 타입 열거형"""
    CONSULTATION = "consultation"
    DIRECT_KEYWORD = "direct_keyword"
    KEYWORD_EXTRACTION = "keyword_extraction"
    DIRECT_FULL = "direct_full"
    ALL = "all"


# 실제 Redis 캐시 프리픽스 (cache_manager에서 사용하는 것과 동일)
CACHE_PREFIXES = {
    "l1": "l1:response:",   # L1 캐시 (전체 응답)
    "l2": "l2:search:",     # L2 캐시 (검색 결과)
    "norm": "norm:query:",  # 정규화 쿼리 캐시
}

# API 타입별 설명 (통계 표시용)
API_DESCRIPTIONS = {
    ApiType.CONSULTATION: "/consultation/assist - 직접 임베딩 + 핵심 가이드",
    ApiType.DIRECT_KEYWORD: "/comparison/direct-keyword - 직접 임베딩 + 핵심 가이드",
    ApiType.KEYWORD_EXTRACTION: "/comparison/keyword-extraction - 키워드 추출 + 핵심 가이드",
    ApiType.DIRECT_FULL: "/comparison/direct-full-guide - 직접 임베딩 + 긴 가이드",
}

# 캐시 제한 설정
CACHE_LIMITS = {
    "l1_max_count": 1000,  # L1 캐시 최대 개수
    "l2_max_count": 500,   # L2 캐시 최대 개수
    "cleanup_batch_size": 100  # 한 번에 삭제할 최대 개수
}


# ===========================================
# 요청/응답 모델
# ===========================================

class CacheInvalidateByApiRequest(BaseModel):
    """API별 캐시 무효화 요청"""
    level: Literal["l1", "l2", "all"] = Field(
        default="all",
        description="무효화할 캐시 레벨 (l1, l2, all)"
    )


class CacheInvalidateByApiResponse(BaseModel):
    """API별 캐시 무효화 응답"""
    success: bool
    api_type: str
    l1_deleted: int = 0
    l2_deleted: int = 0
    message: str


class CacheCleanupRequest(BaseModel):
    """캐시 정리 요청"""
    l1_max_count: int = Field(
        default=1000,
        ge=100,
        le=10000,
        description="L1 캐시 최대 개수 (초과 시 오래된 항목 삭제)"
    )
    l2_max_count: int = Field(
        default=500,
        ge=50,
        le=5000,
        description="L2 캐시 최대 개수 (초과 시 오래된 항목 삭제)"
    )
    dry_run: bool = Field(
        default=False,
        description="True면 실제 삭제 없이 삭제 대상만 조회"
    )


class CacheCleanupResponse(BaseModel):
    """캐시 정리 응답"""
    success: bool
    dry_run: bool
    before_counts: dict
    after_counts: dict
    deleted_counts: dict
    message: str


class DetailedCacheStatsResponse(BaseModel):
    """상세 캐시 통계 응답"""
    connected: bool
    total_l1_count: int = 0
    total_l2_count: int = 0
    api_stats: dict = Field(default_factory=dict)
    used_memory: str = "N/A"
    used_memory_peak: str = "N/A"
    l1_ttl_seconds: int = 3600
    l2_ttl_seconds: int = 7200
    limits: dict = Field(default_factory=dict)
    error: Optional[str] = None


# ===========================================
# API 엔드포인트
# ===========================================

@router.get(
    "/stats",
    response_model=DetailedCacheStatsResponse,
    summary="캐시 통계 조회",
    description="""
캐시 상태 및 통계를 조회합니다.

**반환 정보:**
- 전체 L1/L2 캐시 개수
- 정규화 쿼리 캐시 개수
- 메모리 사용량
- TTL 설정
- 캐시 제한 설정
    """
)
async def get_cache_stats() -> DetailedCacheStatsResponse:
    """상세 캐시 통계 조회"""
    try:
        if not cache_manager.is_connected():
            await cache_manager.connect()

        if not cache_manager.is_connected():
            return DetailedCacheStatsResponse(
                connected=False,
                error="Redis에 연결되어 있지 않습니다."
            )

        # 기본 통계
        stats = await cache_manager.get_cache_stats()

        # 캐시 유형별 통계 수집
        l1_count = await _count_keys_by_prefix(CACHE_PREFIXES["l1"])
        l2_count = await _count_keys_by_prefix(CACHE_PREFIXES["l2"])
        norm_count = await _count_keys_by_prefix(CACHE_PREFIXES["norm"])

        api_stats = {
            "cache_types": {
                "l1_response": {
                    "prefix": CACHE_PREFIXES["l1"],
                    "count": l1_count,
                    "description": "전체 응답 캐시 (정규화된 질문 → 응답)"
                },
                "l2_search": {
                    "prefix": CACHE_PREFIXES["l2"],
                    "count": l2_count,
                    "description": "검색 결과 캐시 (쿼리 → 문서 목록)"
                },
                "norm_query": {
                    "prefix": CACHE_PREFIXES["norm"],
                    "count": norm_count,
                    "description": "정규화 쿼리 캐시 (원본 → 정규화)"
                }
            },
            "api_endpoints": {
                api_type.value: desc for api_type, desc in API_DESCRIPTIONS.items()
            }
        }

        return DetailedCacheStatsResponse(
            connected=True,
            total_l1_count=l1_count,
            total_l2_count=l2_count,
            api_stats=api_stats,
            used_memory=stats.get("used_memory", "N/A"),
            used_memory_peak=stats.get("used_memory_peak", "N/A"),
            l1_ttl_seconds=stats.get("l1_ttl_seconds", 3600),
            l2_ttl_seconds=stats.get("l2_ttl_seconds", 7200),
            limits=CACHE_LIMITS
        )

    except Exception as e:
        logger.error(f"[CacheAPI] 통계 조회 오류: {e}")
        return DetailedCacheStatsResponse(
            connected=False,
            error=str(e)
        )


@router.post(
    "/invalidate/{api_type}",
    response_model=CacheInvalidateByApiResponse,
    summary="캐시 무효화",
    description="""
캐시를 무효화합니다.

**API 타입:**
- `all`: 모든 캐시 무효화 (권장)
- `consultation`, `direct_keyword`, `keyword_extraction`, `direct_full`: 현재 구조에서는 모두 동일하게 전체 캐시 삭제

**레벨:**
- `l1`: L1 캐시만 무효화 (전체 응답 캐시)
- `l2`: L2 캐시만 무효화 (검색 결과 캐시)
- `all`: L1, L2, 정규화 캐시 모두 무효화

**참고:** 현재 캐시 구조에서는 API별로 캐시가 분리되지 않고 공유됩니다.
    """
)
async def invalidate_cache_by_api(
    api_type: ApiType,
    request: CacheInvalidateByApiRequest
) -> CacheInvalidateByApiResponse:
    """캐시 무효화"""
    try:
        if not cache_manager.is_connected():
            await cache_manager.connect()

        if not cache_manager.is_connected():
            return CacheInvalidateByApiResponse(
                success=False,
                api_type=api_type.value,
                message="Redis에 연결되어 있지 않습니다."
            )

        l1_deleted = 0
        l2_deleted = 0
        norm_deleted = 0

        # 캐시 레벨에 따라 삭제
        if request.level in ("l1", "all"):
            l1_deleted = await _delete_keys_by_prefix(CACHE_PREFIXES["l1"])
        if request.level in ("l2", "all"):
            l2_deleted = await _delete_keys_by_prefix(CACHE_PREFIXES["l2"])
        if request.level == "all":
            norm_deleted = await _delete_keys_by_prefix(CACHE_PREFIXES["norm"])

        total_deleted = l1_deleted + l2_deleted + norm_deleted
        message = f"캐시 무효화 완료 - L1: {l1_deleted}개, L2: {l2_deleted}개"
        if norm_deleted > 0:
            message += f", 정규화: {norm_deleted}개"
        message += " 삭제됨"

        return CacheInvalidateByApiResponse(
            success=True,
            api_type=api_type.value,
            l1_deleted=l1_deleted,
            l2_deleted=l2_deleted,
            message=message
        )

    except Exception as e:
        logger.error(f"[CacheAPI] 무효화 오류: {e}")
        return CacheInvalidateByApiResponse(
            success=False,
            api_type=api_type.value,
            message=str(e)
        )


@router.post(
    "/cleanup",
    response_model=CacheCleanupResponse,
    summary="캐시 정리 (LRU 기반)",
    description="""
캐시 개수가 제한을 초과하면 가장 오래된 항목부터 삭제합니다.

**정리 전략:**
- Redis SCAN으로 키 목록 조회
- TTL이 짧은 (오래된) 항목부터 삭제
- dry_run=true로 실제 삭제 없이 대상 확인 가능

**기본 제한:**
- L1 캐시: 최대 1000개
- L2 캐시: 최대 500개

**주의:** 이 작업은 캐시 히트율에 영향을 줄 수 있습니다.
    """
)
async def cleanup_cache(request: CacheCleanupRequest) -> CacheCleanupResponse:
    """캐시 정리 (LRU 기반 삭제)"""
    try:
        if not cache_manager.is_connected():
            await cache_manager.connect()

        if not cache_manager.is_connected():
            return CacheCleanupResponse(
                success=False,
                dry_run=request.dry_run,
                before_counts={},
                after_counts={},
                deleted_counts={},
                message="Redis에 연결되어 있지 않습니다."
            )

        # 정리 전 카운트
        l1_count_before = await _count_keys_by_prefix(CACHE_PREFIXES["l1"])
        l2_count_before = await _count_keys_by_prefix(CACHE_PREFIXES["l2"])

        before_counts = {
            "l1": {"total": l1_count_before},
            "l2": {"total": l2_count_before}
        }
        deleted_counts = {
            "l1": {"total": 0},
            "l2": {"total": 0}
        }

        # L1 캐시 정리
        if l1_count_before > request.l1_max_count:
            to_delete = l1_count_before - request.l1_max_count
            if not request.dry_run:
                deleted = await _delete_oldest_keys(CACHE_PREFIXES["l1"], to_delete)
                deleted_counts["l1"]["total"] = deleted
            else:
                deleted_counts["l1"]["total"] = to_delete

        # L2 캐시 정리
        if l2_count_before > request.l2_max_count:
            to_delete = l2_count_before - request.l2_max_count
            if not request.dry_run:
                deleted = await _delete_oldest_keys(CACHE_PREFIXES["l2"], to_delete)
                deleted_counts["l2"]["total"] = deleted
            else:
                deleted_counts["l2"]["total"] = to_delete

        # 정리 후 카운트
        if not request.dry_run:
            after_counts = {
                "l1": {"total": await _count_keys_by_prefix(CACHE_PREFIXES["l1"])},
                "l2": {"total": await _count_keys_by_prefix(CACHE_PREFIXES["l2"])}
            }
        else:
            after_counts = before_counts  # dry run이면 변경 없음

        total_deleted = deleted_counts["l1"]["total"] + deleted_counts["l2"]["total"]

        return CacheCleanupResponse(
            success=True,
            dry_run=request.dry_run,
            before_counts=before_counts,
            after_counts=after_counts,
            deleted_counts=deleted_counts,
            message=f"{'[DRY RUN] ' if request.dry_run else ''}캐시 정리 완료 - 총 {total_deleted}개 삭제"
        )

    except Exception as e:
        logger.error(f"[CacheAPI] 정리 오류: {e}")
        return CacheCleanupResponse(
            success=False,
            dry_run=request.dry_run,
            before_counts={},
            after_counts={},
            deleted_counts={},
            message=str(e)
        )


@router.post(
    "/normalize-test",
    response_model=NormalizeTestResponse,
    summary="질문 정규화 테스트",
    description="""
여러 질문의 정규화 결과를 테스트합니다.

유사한 의미의 질문들이 동일한 정규화 결과를 반환하는지 확인할 수 있습니다.
이를 통해 캐시 히트율 향상을 예측할 수 있습니다.

**예시:**
- "위약금이 얼마예요?" → "위약금 금액"
- "해지 위약금 알려주세요" → "위약금 금액"
- "약정 해지시 위약금" → "위약금 금액"

위 3개 질문이 모두 같은 정규화 결과를 가지면 L1 캐시 히트율이 높아집니다.
    """
)
async def normalize_test(request: NormalizeTestRequest) -> NormalizeTestResponse:
    """질문 정규화 테스트"""
    start_time = time.perf_counter()

    try:
        results = []

        for query in request.queries:
            normalized = await normalize_query(query, use_llm=request.use_llm)
            results.append({
                "original": query,
                "normalized": normalized
            })

        duration_ms = (time.perf_counter() - start_time) * 1000

        return NormalizeTestResponse(
            results=results,
            processing_time_ms=duration_ms
        )

    except Exception as e:
        logger.error(f"[CacheAPI] 정규화 테스트 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# 헬퍼 함수
@router.post(
    "/invalidate",
    response_model=CacheInvalidateByApiResponse,
    summary="전체 캐시 무효화 (간편)",
    description="""
모든 캐시를 무효화합니다. `/invalidate/all`의 간편 버전입니다.

L1 (응답 캐시), L2 (검색 캐시), 정규화 캐시를 모두 삭제합니다.
    """
)
async def invalidate_all_cache() -> CacheInvalidateByApiResponse:
    """전체 캐시 무효화"""
    try:
        if not cache_manager.is_connected():
            await cache_manager.connect()

        if not cache_manager.is_connected():
            return CacheInvalidateByApiResponse(
                success=False,
                api_type="all",
                message="Redis에 연결되어 있지 않습니다."
            )

        l1_deleted = await _delete_keys_by_prefix(CACHE_PREFIXES["l1"])
        l2_deleted = await _delete_keys_by_prefix(CACHE_PREFIXES["l2"])
        norm_deleted = await _delete_keys_by_prefix(CACHE_PREFIXES["norm"])

        total = l1_deleted + l2_deleted + norm_deleted
        return CacheInvalidateByApiResponse(
            success=True,
            api_type="all",
            l1_deleted=l1_deleted,
            l2_deleted=l2_deleted,
            message=f"전체 캐시 무효화 완료 - L1: {l1_deleted}개, L2: {l2_deleted}개, 정규화: {norm_deleted}개 삭제됨 (총 {total}개)"
        )

    except Exception as e:
        logger.error(f"[CacheAPI] 전체 무효화 오류: {e}")
        return CacheInvalidateByApiResponse(
            success=False,
            api_type="all",
            message=str(e)
        )


# ===========================================
# 헬퍼 함수
# ===========================================

async def _count_keys_by_prefix(prefix: str) -> int:
    """특정 프리픽스를 가진 키 개수 조회"""
    try:
        if not cache_manager._client:
            return 0

        count = 0
        cursor = 0
        pattern = f"{prefix}*"

        while True:
            cursor, keys = await cache_manager._client.scan(
                cursor=cursor,
                match=pattern,
                count=100
            )
            count += len(keys)
            if cursor == 0:
                break

        return count
    except Exception as e:
        logger.error(f"키 카운트 오류 ({prefix}): {e}")
        return 0


async def _delete_keys_by_prefix(prefix: str) -> int:
    """특정 프리픽스를 가진 모든 키 삭제"""
    try:
        if not cache_manager._client:
            return 0

        deleted = 0
        cursor = 0
        pattern = f"{prefix}*"

        while True:
            cursor, keys = await cache_manager._client.scan(
                cursor=cursor,
                match=pattern,
                count=100
            )

            if keys:
                await cache_manager._client.delete(*keys)
                deleted += len(keys)

            if cursor == 0:
                break

        return deleted
    except Exception as e:
        logger.error(f"키 삭제 오류 ({prefix}): {e}")
        return 0


async def _delete_oldest_keys(prefix: str, count: int) -> int:
    """TTL 기준으로 가장 오래된 키 삭제 (LRU 방식)"""
    try:
        if not cache_manager._client or count <= 0:
            return 0

        # 키와 TTL 수집
        keys_with_ttl = []
        cursor = 0
        pattern = f"{prefix}*"

        while True:
            cursor, keys = await cache_manager._client.scan(
                cursor=cursor,
                match=pattern,
                count=100
            )

            for key in keys:
                ttl = await cache_manager._client.ttl(key)
                keys_with_ttl.append((key, ttl))

            if cursor == 0:
                break

        # TTL이 작은 순으로 정렬 (만료가 가까운 = 오래된 항목)
        keys_with_ttl.sort(key=lambda x: x[1])

        # 삭제할 키 선택
        to_delete = [key for key, _ in keys_with_ttl[:count]]

        if to_delete:
            await cache_manager._client.delete(*to_delete)

        return len(to_delete)
    except Exception as e:
        logger.error(f"오래된 키 삭제 오류 ({prefix}): {e}")
        return 0
