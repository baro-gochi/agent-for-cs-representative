#!/usr/bin/env python3
"""
===========================================
캐싱 시스템 테스트 스크립트
===========================================

이 스크립트는 캐싱 시스템이 올바르게 동작하는지 테스트합니다.

사용 전 준비:
1. Docker로 Redis 실행:
   cd kt_cs_agent_api
   docker-compose up -d redis

2. 의존성 설치:
   pip install redis httpx

3. API 서버 실행:
   uvicorn app.main:app --reload --port 8001

4. 테스트 실행:
   python scripts/test_cache.py

테스트 항목:
1. Redis 연결 테스트
2. 캐시 통계 조회
3. 질문 정규화 테스트
4. L1/L2 캐싱 테스트
5. 성능 벤치마크
"""

import asyncio
import httpx
import time
from typing import Dict, Any

# API 기본 URL
BASE_URL = "http://localhost:8001"


async def test_redis_connection():
    """Redis 연결 테스트"""
    print("\n" + "=" * 60)
    print("1. Redis 연결 테스트")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/cache/stats")
            data = response.json()

            if data.get("connected"):
                print("✅ Redis 연결 성공!")
                print(f"   - L1 캐시 항목: {data.get('l1_cache_count', 0)}개")
                print(f"   - L2 캐시 항목: {data.get('l2_cache_count', 0)}개")
                print(f"   - 메모리 사용량: {data.get('used_memory', 'N/A')}")
                return True
            else:
                print("❌ Redis 연결 실패")
                print(f"   - 에러: {data.get('error', 'Unknown')}")
                return False
        except Exception as e:
            print(f"❌ API 호출 실패: {e}")
            return False


async def test_normalize_queries():
    """질문 정규화 테스트"""
    print("\n" + "=" * 60)
    print("2. 질문 정규화 테스트")
    print("=" * 60)

    # 유사한 의미를 가진 질문들
    test_queries = [
        "위약금이 얼마예요?",
        "해지 위약금 알려주세요",
        "약정 해지시 위약금 비용",
        "인터넷 해지하면 위약금 얼마나 나와요?",
    ]

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(
                f"{BASE_URL}/cache/normalize-test",
                json={
                    "queries": test_queries,
                    "use_llm": True
                }
            )
            data = response.json()

            print(f"소요 시간: {data.get('processing_time_ms', 0):.1f}ms\n")

            # 정규화 결과 출력
            normalized_set = set()
            for result in data.get("results", []):
                original = result.get("original", "")
                normalized = result.get("normalized", "")
                normalized_set.add(normalized)
                print(f"  원본: {original}")
                print(f"  정규화: {normalized}")
                print()

            # 캐시 히트율 예측
            unique_count = len(normalized_set)
            total_count = len(test_queries)
            potential_hit_rate = (total_count - unique_count) / total_count * 100

            print(f"📊 분석:")
            print(f"   - 총 쿼리: {total_count}개")
            print(f"   - 고유 정규화 결과: {unique_count}개")
            print(f"   - 예상 캐시 히트율: {potential_hit_rate:.1f}%")

            return True
        except Exception as e:
            print(f"❌ 테스트 실패: {e}")
            return False


async def test_caching_effectiveness():
    """L1/L2 캐싱 효과 테스트"""
    print("\n" + "=" * 60)
    print("3. L1/L2 캐싱 효과 테스트")
    print("=" * 60)

    test_query = "인터넷 약정 해지 시 위약금이 얼마인가요?"

    async with httpx.AsyncClient(timeout=120) as client:
        # 먼저 캐시 무효화
        print("캐시 무효화 중...")
        await client.post(
            f"{BASE_URL}/cache/invalidate",
            json={"level": "all"}
        )

        results = []

        for i in range(3):
            print(f"\n요청 #{i + 1}:")
            start = time.perf_counter()

            response = await client.post(
                f"{BASE_URL}/cache/query",
                json={
                    "summary": test_query,
                    "use_l1_cache": True,
                    "use_l2_cache": True,
                    "use_llm_normalization": False  # 빠른 테스트를 위해 간단한 정규화 사용
                }
            )
            data = response.json()

            duration = (time.perf_counter() - start) * 1000
            cache_status = data.get("cache_status", "unknown")
            l1_hit = data.get("l1_cache_hit", False)
            l2_hit = data.get("l2_cache_hit", False)

            results.append({
                "iteration": i + 1,
                "duration_ms": duration,
                "cache_status": cache_status,
                "l1_hit": l1_hit,
                "l2_hit": l2_hit
            })

            status_emoji = "⚡" if l1_hit else ("🔍" if l2_hit else "🐢")
            print(f"  {status_emoji} 소요시간: {duration:.1f}ms")
            print(f"     - 캐시 상태: {cache_status}")
            print(f"     - L1 히트: {l1_hit}")
            print(f"     - L2 히트: {l2_hit}")

        # 결과 분석
        print("\n📊 결과 분석:")
        first_request = results[0]["duration_ms"]
        cached_requests = [r["duration_ms"] for r in results[1:]]
        avg_cached = sum(cached_requests) / len(cached_requests) if cached_requests else 0
        speedup = first_request / avg_cached if avg_cached > 0 else 0

        print(f"   - 첫 번째 요청 (캐시 미스): {first_request:.1f}ms")
        print(f"   - 캐시 히트 평균: {avg_cached:.1f}ms")
        print(f"   - 속도 향상: {speedup:.1f}x")

        return True


async def test_benchmark():
    """성능 벤치마크 테스트"""
    print("\n" + "=" * 60)
    print("4. 성능 벤치마크")
    print("=" * 60)

    test_query = "3년 약정 기간 중 14개월 사용 후 중도 해지 시 위약금 문의"

    async with httpx.AsyncClient(timeout=300) as client:
        try:
            response = await client.post(
                f"{BASE_URL}/cache/benchmark",
                params={
                    "summary": test_query,
                    "iterations": 5
                }
            )
            data = response.json()

            print(f"쿼리: {data.get('summary', '')[:50]}...")
            print(f"반복 횟수: {data.get('iterations', 0)}\n")

            # 각 반복 결과
            for result in data.get("results", []):
                status = result.get("cache_status", "unknown")
                emoji = "⚡" if result.get("l1_cache_hit") else "🐢"
                print(f"  {emoji} #{result.get('iteration')}: {result.get('duration_ms'):.1f}ms ({status})")

            # 통계
            stats = data.get("statistics", {})
            print(f"\n📊 통계:")
            print(f"   - 첫 번째 요청: {stats.get('first_request_ms', 0):.1f}ms")
            print(f"   - 캐시 히트 평균: {stats.get('avg_cached_request_ms', 0):.1f}ms")
            print(f"   - 속도 향상: {stats.get('speedup_factor', 0):.1f}x")

            return True
        except Exception as e:
            print(f"❌ 벤치마크 실패: {e}")
            return False


async def test_cache_invalidation():
    """캐시 무효화 테스트"""
    print("\n" + "=" * 60)
    print("5. 캐시 무효화 테스트")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=60) as client:
        # 현재 캐시 상태
        stats_before = (await client.get(f"{BASE_URL}/cache/stats")).json()
        print(f"무효화 전:")
        print(f"   - L1 캐시: {stats_before.get('l1_cache_count', 0)}개")
        print(f"   - L2 캐시: {stats_before.get('l2_cache_count', 0)}개")

        # L1 캐시만 무효화
        response = await client.post(
            f"{BASE_URL}/cache/invalidate",
            json={"level": "l1"}
        )
        data = response.json()
        print(f"\nL1 캐시 무효화: {data.get('l1_deleted', 0)}개 삭제")

        # 전체 무효화
        response = await client.post(
            f"{BASE_URL}/cache/invalidate",
            json={"level": "all"}
        )
        data = response.json()
        print(f"전체 캐시 무효화: L1={data.get('l1_deleted', 0)}개, L2={data.get('l2_deleted', 0)}개 삭제")

        # 무효화 후 상태
        stats_after = (await client.get(f"{BASE_URL}/cache/stats")).json()
        print(f"\n무효화 후:")
        print(f"   - L1 캐시: {stats_after.get('l1_cache_count', 0)}개")
        print(f"   - L2 캐시: {stats_after.get('l2_cache_count', 0)}개")

        return True


async def main():
    """메인 테스트 실행"""
    print("=" * 60)
    print("KT CS Agent 캐싱 시스템 테스트")
    print("=" * 60)
    print(f"API 서버: {BASE_URL}")

    # 서버 상태 확인
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(f"{BASE_URL}/health")
            if response.status_code != 200:
                print(f"❌ API 서버가 실행 중이지 않습니다.")
                print(f"   uvicorn app.main:app --reload --port 8001")
                return
        except Exception as e:
            print(f"❌ API 서버 연결 실패: {e}")
            print(f"   uvicorn app.main:app --reload --port 8001")
            return

    # 테스트 실행
    results = {}

    results["redis"] = await test_redis_connection()

    if results["redis"]:
        results["normalize"] = await test_normalize_queries()
        results["caching"] = await test_caching_effectiveness()
        results["benchmark"] = await test_benchmark()
        results["invalidation"] = await test_cache_invalidation()

    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)
    for test_name, passed in results.items():
        emoji = "✅" if passed else "❌"
        print(f"  {emoji} {test_name}")

    all_passed = all(results.values())
    print()
    if all_passed:
        print("🎉 모든 테스트 통과!")
    else:
        print("⚠️ 일부 테스트 실패")


if __name__ == "__main__":
    asyncio.run(main())
