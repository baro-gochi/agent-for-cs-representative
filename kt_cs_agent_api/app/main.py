"""
===========================================
KT CS 상담원 AI Agent API - 메인 애플리케이션
===========================================

이 파일은 FastAPI 애플리케이션의 진입점입니다.

실행 방법:
    # 개발 모드 (자동 리로드)
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    
    # 프로덕션 모드
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

API 문서:
    - Swagger UI: http://localhost:8000/docs
    - ReDoc: http://localhost:8000/redoc
    - OpenAPI JSON: http://localhost:8000/openapi.json
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api import health_router, consultation_router, comparison_router
from app.api.cache import router as cache_router
from app.utils import setup_logging
from app.database import get_vector_db_manager
from app.utils.cache_manager import cache_manager

# 로깅 설정
setup_logging()
logger = logging.getLogger(__name__)


# ==========================================
# 애플리케이션 생명주기 관리
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    애플리케이션 생명주기 이벤트 핸들러
    
    시작 시:
        - 로깅 초기화
        - 벡터 DB 연결 초기화 (Lazy loading)
    
    종료 시:
        - 리소스 정리
    """
    # -----------------------------------------
    # Startup
    # -----------------------------------------
    logger.info("=" * 60)
    logger.info("KT 상담원 AI Agent API 시작")
    logger.info("=" * 60)
    logger.info(f"환경: {'DEBUG' if settings.DEBUG else 'PRODUCTION'}")
    logger.info(f"벡터 DB: {settings.CHROMA_DB_PATH}")
    logger.info(f"분석 모델: {settings.ANALYZER_MODEL}")
    logger.info(f"응답 모델: {settings.RESPONSE_MODEL}")
    logger.info(f"최대 동시 요청: {settings.MAX_CONCURRENT_REQUESTS}")
    logger.info(f"Rate Limit: {settings.RATE_LIMIT_PER_MINUTE}/분")
    logger.info(f"캐싱 활성화: {settings.CACHE_ENABLED}")

    # Redis 캐시 연결 초기화
    if settings.CACHE_ENABLED:
        try:
            connected = await cache_manager.connect()
            if connected:
                logger.info(f"Redis 캐시 연결 성공: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
                logger.info(f"L1 캐시 TTL: {settings.CACHE_L1_TTL}초")
                logger.info(f"L2 캐시 TTL: {settings.CACHE_L2_TTL}초")
            else:
                logger.warning("Redis 캐시 연결 실패 - 캐싱 없이 운영됩니다")
        except Exception as e:
            logger.warning(f"Redis 캐시 초기화 오류: {e} - 캐싱 없이 운영됩니다")

    # 벡터 DB 미리 초기화 (선택적)
    # 첫 요청 시 지연을 피하고 싶다면 주석 해제
    # try:
    #     db_manager = get_vector_db_manager()
    #     db_manager.initialize()
    #     logger.info("벡터 DB 초기화 완료")
    # except Exception as e:
    #     logger.error(f"벡터 DB 초기화 실패: {e}")

    yield  # 애플리케이션 실행

    # -----------------------------------------
    # Shutdown
    # -----------------------------------------
    # Redis 연결 종료
    if cache_manager.is_connected():
        await cache_manager.disconnect()
        logger.info("Redis 캐시 연결 종료")

    logger.info("KT 상담원 AI Agent API 종료")


# ==========================================
# FastAPI 애플리케이션 생성
# ==========================================

app = FastAPI(
    title="KT CS 상담원 AI Agent API",
    description="""
## 개요
KT CS 고객센터 상담원을 지원하는 AI Agent API입니다.

## 주요 기능

### 🆕 신입 상담원용 API (`/consultation`)
- 상담 내용을 분석하여 키워드 추출
- 관련 내부 규정/약관 문서 검색
- AI 기반 대응방안 생성

### 🏥 시스템 API (`/health`)
- 서비스 상태 확인
- 대기열 상태 조회

### 🔬 비교용 API (`/comparison`)
- 직접 임베딩 + 핵심 가이드 생성
- 키워드 추출 + 핵심 가이드 생성
- 직접 임베딩 + 긴 가이드 생성

### ⚡ 캐시 API (`/cache`)
- L1 캐시: 정규화된 질문 → 전체 응답 캐싱
- L2 캐시: 검색 쿼리 → 벡터 검색 결과 캐싱
- 캐시 통계 조회 및 무효화
- 질문 정규화 테스트

## Rate Limiting
- 분당 최대 30회 요청
- 동시 요청 최대 10개

## 인증
현재 버전에서는 인증이 필요하지 않습니다.
    """,
    version="1.0.0",
    contact={
        "name": "Team Barogochi",
        "email": "-"
    },
    license_info={
        "name": "MIT License",
    },
    lifespan=lifespan
)


# ==========================================
# 미들웨어 설정
# ==========================================

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ==========================================
# 전역 예외 처리
# ==========================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    전역 예외 처리기
    
    처리되지 않은 모든 예외를 500 에러로 변환합니다.
    """
    logger.error(f"처리되지 않은 예외: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "서버 내부 오류가 발생했습니다.",
            "detail": str(exc) if settings.DEBUG else None
        }
    )


# ==========================================
# 라우터 등록
# ==========================================

# 헬스 체크 API
app.include_router(health_router)

# 신입 상담원용 API
app.include_router(consultation_router)

# 비교용 API
app.include_router(comparison_router)

# 캐시 관리 API (신규)
app.include_router(cache_router)


# ==========================================
# 루트 엔드포인트
# ==========================================

@app.get("/", tags=["Root"])
async def root():
    """
    API 루트 엔드포인트
    
    API 정보와 주요 엔드포인트 링크를 반환합니다.
    """
    return {
        "name": "KT 상담원 AI Agent API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/health",
            "consultation": "/consultation/assist",
            "comparison": {
                "direct_keyword": "/comparison/direct-keyword",
                "keyword_extraction": "/comparison/keyword-extraction",
                "direct_full_guide": "/comparison/direct-full-guide"
            },
            "cache": {
                "query": "/cache/query",
                "stats": "/cache/stats",
                "invalidate": "/cache/invalidate",
                "normalize_test": "/cache/normalize-test",
                "benchmark": "/cache/benchmark"
            }
        }
    }


# ==========================================
# 직접 실행 시
# ==========================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
