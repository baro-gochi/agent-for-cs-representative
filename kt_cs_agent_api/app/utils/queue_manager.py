"""
===========================================
대기열 및 Rate Limiting 관리
===========================================

이 모듈은 서버 안정성을 위한 요청 제어 기능을 제공합니다:
- 동시 요청 수 제한 (Semaphore)
- Rate Limiting (분당 요청 수 제한)
- 요청 대기열 관리

수정 가이드:
    - 제한값 변경: settings에서 환경변수 수정
    - 알고리즘 변경: RateLimiter 클래스 수정

사용 예시:
    from app.utils.queue_manager import request_limiter, get_queue_status
    
    # 데코레이터로 사용
    @request_limiter.limit
    async def my_endpoint():
        ...
    
    # 컨텍스트 매니저로 사용
    async with request_limiter.acquire():
        ...
"""

import asyncio
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Optional, Callable
from functools import wraps

from app.config import settings

# 로거 설정
logger = logging.getLogger(__name__)


@dataclass
class QueueStats:
    """
    대기열 통계 정보
    
    Attributes:
        current_requests: 현재 처리 중인 요청 수
        max_requests: 최대 동시 요청 수
        queue_length: 대기 중인 요청 수
        total_processed: 총 처리된 요청 수
        total_rejected: 거부된 요청 수
    """
    current_requests: int = 0
    max_requests: int = 10
    queue_length: int = 0
    total_processed: int = 0
    total_rejected: int = 0
    
    @property
    def is_accepting(self) -> bool:
        """새 요청 수락 가능 여부"""
        return self.current_requests < self.max_requests


class ConcurrencyLimiter:
    """
    동시 요청 수 제한기 (Semaphore 기반)
    
    최대 동시 실행 가능한 요청 수를 제한합니다.
    초과 요청은 대기하거나 거부됩니다.
    
    Attributes:
        max_concurrent: 최대 동시 요청 수
        timeout: 대기 타임아웃 (초)
    """
    
    def __init__(
        self, 
        max_concurrent: int = None,
        timeout: float = None
    ):
        """
        ConcurrencyLimiter 초기화
        
        Args:
            max_concurrent: 최대 동시 요청 수 (기본: settings.MAX_CONCURRENT_REQUESTS)
            timeout: 대기 타임아웃 초 (기본: settings.REQUEST_TIMEOUT)
        """
        self.max_concurrent = max_concurrent or settings.MAX_CONCURRENT_REQUESTS
        self.timeout = timeout or settings.REQUEST_TIMEOUT
        
        # 동시성 제어를 위한 Semaphore
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # 통계 정보
        self._current_count = 0
        self._waiting_count = 0
        self._total_processed = 0
        self._total_rejected = 0
        
        # Lock for thread-safe counter updates
        self._lock = asyncio.Lock()
        
        logger.info(f"ConcurrencyLimiter 초기화: max={self.max_concurrent}, timeout={self.timeout}s")
    
    @asynccontextmanager
    async def acquire(self, timeout: float = None):
        """
        요청 슬롯 획득 (컨텍스트 매니저)
        
        Args:
            timeout: 대기 타임아웃 (기본: 인스턴스 설정값)
        
        Yields:
            None
        
        Raises:
            asyncio.TimeoutError: 타임아웃 시
        
        사용 예시:
            async with limiter.acquire():
                # 요청 처리
                pass
        """
        timeout = timeout or self.timeout
        
        async with self._lock:
            self._waiting_count += 1
        
        try:
            # 타임아웃 내에 Semaphore 획득 시도
            acquired = await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=timeout
            )
            
            async with self._lock:
                self._waiting_count -= 1
                self._current_count += 1
            
            logger.debug(f"요청 슬롯 획득: {self._current_count}/{self.max_concurrent}")
            
            try:
                yield
            finally:
                self._semaphore.release()
                async with self._lock:
                    self._current_count -= 1
                    self._total_processed += 1
                logger.debug(f"요청 슬롯 반환: {self._current_count}/{self.max_concurrent}")
                
        except asyncio.TimeoutError:
            async with self._lock:
                self._waiting_count -= 1
                self._total_rejected += 1
            logger.warning(f"요청 타임아웃: 대기 시간 초과 ({timeout}s)")
            raise
    
    def get_stats(self) -> QueueStats:
        """
        현재 대기열 상태 조회
        
        Returns:
            QueueStats: 대기열 통계 정보
        """
        return QueueStats(
            current_requests=self._current_count,
            max_requests=self.max_concurrent,
            queue_length=self._waiting_count,
            total_processed=self._total_processed,
            total_rejected=self._total_rejected
        )


class RateLimiter:
    """
    Rate Limiter (Token Bucket 알고리즘)
    
    일정 시간 내 최대 요청 수를 제한합니다.
    
    Attributes:
        max_requests: 시간 윈도우 내 최대 요청 수
        window_seconds: 시간 윈도우 크기 (초)
    """
    
    def __init__(
        self,
        max_requests: int = None,
        window_seconds: int = 60
    ):
        """
        RateLimiter 초기화
        
        Args:
            max_requests: 분당 최대 요청 수 (기본: settings.RATE_LIMIT_PER_MINUTE)
            window_seconds: 시간 윈도우 크기 (기본: 60초)
        """
        self.max_requests = max_requests or settings.RATE_LIMIT_PER_MINUTE
        self.window_seconds = window_seconds
        
        # 요청 타임스탬프 기록 (슬라이딩 윈도우)
        self._request_times: deque = deque()
        self._lock = asyncio.Lock()
        
        logger.info(f"RateLimiter 초기화: {self.max_requests} req/{self.window_seconds}s")
    
    async def is_allowed(self) -> bool:
        """
        요청 허용 여부 확인
        
        Returns:
            bool: 허용되면 True, 제한 초과면 False
        """
        async with self._lock:
            current_time = time.time()
            
            # 윈도우 밖의 오래된 요청 제거
            window_start = current_time - self.window_seconds
            while self._request_times and self._request_times[0] < window_start:
                self._request_times.popleft()
            
            # 현재 윈도우 내 요청 수 확인
            if len(self._request_times) < self.max_requests:
                self._request_times.append(current_time)
                return True
            else:
                logger.warning(f"Rate limit 초과: {len(self._request_times)}/{self.max_requests}")
                return False
    
    async def wait_if_needed(self) -> None:
        """
        필요시 대기 (Rate limit 초과 시)
        
        Rate limit에 걸리면 다음 슬롯이 열릴 때까지 대기합니다.
        """
        while not await self.is_allowed():
            # 가장 오래된 요청이 만료될 때까지 대기
            async with self._lock:
                if self._request_times:
                    wait_time = (
                        self._request_times[0] + self.window_seconds - time.time()
                    )
                    if wait_time > 0:
                        logger.debug(f"Rate limit 대기: {wait_time:.2f}s")
                        await asyncio.sleep(min(wait_time, 1.0))
    
    def get_remaining(self) -> int:
        """
        남은 요청 가능 횟수 조회
        
        Returns:
            int: 현재 윈도우에서 남은 요청 가능 횟수
        """
        current_time = time.time()
        window_start = current_time - self.window_seconds
        
        # 현재 윈도우 내 요청 수 계산
        current_count = sum(
            1 for t in self._request_times if t >= window_start
        )
        
        return max(0, self.max_requests - current_count)


class RequestLimiter:
    """
    통합 요청 제한기
    
    동시성 제한과 Rate Limiting을 모두 적용합니다.
    
    Attributes:
        concurrency_limiter: 동시 요청 제한기
        rate_limiter: Rate Limiter
    """
    
    def __init__(self):
        """RequestLimiter 초기화"""
        self.concurrency_limiter = ConcurrencyLimiter()
        self.rate_limiter = RateLimiter()
        
        logger.info("RequestLimiter 초기화 완료")
    
    @asynccontextmanager
    async def acquire(self, timeout: float = None):
        """
        요청 슬롯 획득 (Rate Limit + Concurrency 모두 적용)
        
        Args:
            timeout: 대기 타임아웃
        
        Yields:
            None
        
        Raises:
            asyncio.TimeoutError: 타임아웃 시
            RuntimeError: Rate limit 초과 시
        """
        # Rate limit 체크
        if not await self.rate_limiter.is_allowed():
            raise RuntimeError("Rate limit exceeded")
        
        # 동시성 제한 적용
        async with self.concurrency_limiter.acquire(timeout=timeout):
            yield
    
    def limit(self, func: Callable):
        """
        요청 제한 데코레이터
        
        비동기 함수에 적용하여 자동으로 제한을 적용합니다.
        
        사용 예시:
            @request_limiter.limit
            async def my_endpoint():
                ...
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with self.acquire():
                return await func(*args, **kwargs)
        return wrapper
    
    def get_stats(self) -> dict:
        """
        전체 상태 조회
        
        Returns:
            dict: 대기열 및 Rate limit 상태
        """
        queue_stats = self.concurrency_limiter.get_stats()
        rate_remaining = self.rate_limiter.get_remaining()
        
        return {
            "concurrency": {
                "current": queue_stats.current_requests,
                "max": queue_stats.max_requests,
                "waiting": queue_stats.queue_length,
                "is_accepting": queue_stats.is_accepting
            },
            "rate_limit": {
                "remaining": rate_remaining,
                "max_per_minute": self.rate_limiter.max_requests
            },
            "totals": {
                "processed": queue_stats.total_processed,
                "rejected": queue_stats.total_rejected
            }
        }


# ==========================================
# 전역 인스턴스
# ==========================================

# 싱글톤 인스턴스
request_limiter = RequestLimiter()


def get_queue_status() -> dict:
    """
    대기열 상태 조회 (편의 함수)
    
    Returns:
        dict: 대기열 및 Rate limit 상태
    """
    return request_limiter.get_stats()
