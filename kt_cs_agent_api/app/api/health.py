"""
===========================================
Health Check API 라우터
===========================================

이 모듈은 서비스 상태 확인 엔드포인트를 제공합니다.
- 기본 헬스 체크 (Kubernetes liveness)
- 상세 상태 확인 (Kubernetes readiness)
- 대기열 상태 조회

엔드포인트:
    GET /health          - 기본 헬스 체크
    GET /health/ready    - 상세 준비 상태
    GET /health/queue    - 대기열 상태
"""

import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.models import HealthStatus, QueueStatusResponse
from app.database import get_vector_db_manager
from app.utils import get_queue_status

# 로거 설정
logger = logging.getLogger(__name__)

# 라우터 생성
router = APIRouter(
    prefix="/health",
    tags=["Health Check"],
    responses={503: {"description": "Service Unavailable"}}
)


@router.get(
    "",
    summary="기본 헬스 체크",
    description="서비스가 실행 중인지 확인합니다. Kubernetes liveness probe에 사용.",
    response_model=Dict[str, str]
)
async def health_check():
    """
    기본 헬스 체크 (Liveness Probe)
    
    서비스가 응답 가능한 상태인지만 확인합니다.
    DB 연결 등은 체크하지 않습니다.
    
    Returns:
        {"status": "healthy", "timestamp": "..."}
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@router.get(
    "/ready",
    summary="준비 상태 확인",
    description="서비스가 요청을 처리할 준비가 되었는지 확인합니다. Kubernetes readiness probe에 사용.",
    response_model=HealthStatus
)
async def readiness_check():
    """
    상세 준비 상태 확인 (Readiness Probe)
    
    서비스의 모든 컴포넌트가 정상인지 확인합니다:
    - 벡터 DB 연결 상태
    - 대기열 상태
    
    Returns:
        HealthStatus: 상세 상태 정보
    
    Raises:
        HTTPException(503): 서비스가 준비되지 않은 경우
    """
    components = {}
    is_healthy = True
    
    # -----------------------------------------
    # 벡터 DB 상태 확인
    # -----------------------------------------
    try:
        db_manager = get_vector_db_manager()
        db_info = db_manager.get_collection_info()
        components["vector_db"] = {
            "status": "healthy" if db_manager.health_check() else "unhealthy",
            "collection": db_info.get("collection_name"),
            "document_count": db_info.get("document_count")
        }
        if components["vector_db"]["status"] == "unhealthy":
            is_healthy = False
    except Exception as e:
        logger.error(f"벡터 DB 상태 확인 실패: {e}")
        components["vector_db"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        is_healthy = False
    
    # -----------------------------------------
    # 대기열 상태 확인
    # -----------------------------------------
    try:
        queue_stats = get_queue_status()
        components["queue"] = {
            "status": "healthy" if queue_stats["concurrency"]["is_accepting"] else "busy",
            **queue_stats
        }
    except Exception as e:
        logger.error(f"대기열 상태 확인 실패: {e}")
        components["queue"] = {
            "status": "unknown",
            "error": str(e)
        }
    
    # 결과 생성
    status = HealthStatus(
        status="healthy" if is_healthy else "unhealthy",
        timestamp=datetime.now(),
        components=components
    )
    
    # unhealthy면 503 반환
    if not is_healthy:
        return JSONResponse(
            status_code=503,
            content=status.model_dump(mode='json')
        )
    
    return status


@router.get(
    "/queue",
    summary="대기열 상태",
    description="현재 요청 대기열 및 Rate Limit 상태를 조회합니다.",
    response_model=Dict[str, Any]
)
async def queue_status():
    """
    대기열 상태 조회
    
    현재 처리 중인 요청 수, 대기 중인 요청 수,
    Rate Limit 상태 등을 반환합니다.
    
    Returns:
        dict: 대기열 상태 정보
    """
    stats = get_queue_status()
    return {
        "timestamp": datetime.now().isoformat(),
        **stats
    }
