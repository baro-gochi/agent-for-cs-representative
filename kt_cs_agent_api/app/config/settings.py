"""
===========================================
환경 변수 및 설정 관리 모듈
===========================================

이 모듈은 애플리케이션의 모든 설정을 중앙에서 관리합니다.
- .env 파일에서 환경 변수 로딩
- 설정값 유효성 검증
- 기본값 제공

사용 예시:
    from app.config.settings import settings
    print(settings.OPENAI_API_KEY)
"""

import os
from typing import Optional
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """
    애플리케이션 설정 클래스
    
    환경 변수를 Python 객체로 매핑하고 유효성을 검증합니다.
    .env 파일이나 시스템 환경 변수에서 값을 자동으로 로딩합니다.
    """
    
    # ==========================================
    # [필수] OpenAI API 설정
    # ==========================================
    OPENAI_API_KEY: str = Field(
        ...,  # 필수값
        description="OpenAI API 키"
    )
    
    # ==========================================
    # [선택] 벡터 데이터베이스 설정
    # ==========================================
    # 벡터 DB 타입 선택: "chroma" 또는 "pgvector"
    VECTOR_DB_TYPE: str = Field(
        default="chroma",
        description="벡터 DB 타입 (chroma 또는 pgvector)"
    )

    # ChromaDB 설정 (VECTOR_DB_TYPE=chroma일 때 사용)
    CHROMA_DB_PATH: Optional[str] = Field(
        default=None,
        description="ChromaDB 저장 경로"
    )

    CHROMA_COLLECTION_NAME: str = Field(
        default="kt_terms",
        description="벡터 DB 컬렉션/테이블 이름"
    )

    # ==========================================
    # [선택] PostgreSQL + pgvector 설정
    # ==========================================
    POSTGRES_HOST: str = Field(
        default="localhost",
        description="PostgreSQL 서버 호스트"
    )

    POSTGRES_PORT: int = Field(
        default=5432,
        description="PostgreSQL 서버 포트"
    )

    POSTGRES_DB: str = Field(
        default="vectordb",
        description="PostgreSQL 데이터베이스 이름"
    )

    POSTGRES_USER: str = Field(
        default="postgres",
        description="PostgreSQL 사용자"
    )

    POSTGRES_PASSWORD: Optional[str] = Field(
        default=None,
        description="PostgreSQL 비밀번호"
    )
    
    # ==========================================
    # [선택] 임베딩 모델 설정
    # ==========================================
    EMBEDDING_MODEL_NAME: str = Field(
        default="text-embedding-3-small",
        description="OpenAI 임베딩 모델명 (벡터 DB 생성 시 사용한 모델과 동일해야 함)"
    )
    
    EMBEDDING_DEVICE: str = Field(
        default="cpu",
        description="임베딩 모델 실행 디바이스 (OpenAI 임베딩은 사용하지 않음)"
    )
    
    # ==========================================
    # [선택] LLM 모델 설정
    # ==========================================
    ANALYZER_MODEL: str = Field(
        default="gpt-5-nano",
        description="키워드 추출용 LLM 모델"
    )
    
    RESPONSE_MODEL: str = Field(
        default="gpt-5-nano",
        description="응답 생성용 LLM 모델"
    )

    ANSWER_MODEL: str = Field(
        default="gpt-5-nano",
        description="답변 생성용 LLM 모델"
    )

    # ==========================================
    # [선택] 서버 설정
    # ==========================================
    API_HOST: str = Field(
        default="0.0.0.0",
        description="API 서버 호스트"
    )
    
    API_PORT: int = Field(
        default=8000,
        description="API 서버 포트"
    )
    
    DEBUG: bool = Field(
        default=False,
        description="디버그 모드"
    )
    
    # ==========================================
    # [선택] 대기열 및 Rate Limiting 설정
    # ==========================================
    MAX_CONCURRENT_REQUESTS: int = Field(
        default=10,
        description="최대 동시 요청 수"
    )
    
    REQUEST_TIMEOUT: int = Field(
        default=60,
        description="요청당 타임아웃 (초)"
    )
    
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=30,
        description="분당 최대 요청 수"
    )
    
    # ==========================================
    # [선택] 문서 레지스트리 설정
    # ==========================================
    DOC_REGISTRY_PATH: Optional[str] = Field(
        default=None,
        description="문서 매핑 JSON 파일 경로"
    )
    
    # ==========================================
    # [선택] 로깅 설정
    # ==========================================
    LOG_LEVEL: str = Field(
        default="INFO",
        description="로그 레벨"
    )

    LOG_FILE_PATH: Optional[str] = Field(
        default=None,
        description="로그 파일 경로"
    )

    # ==========================================
    # [선택] Redis 캐싱 설정
    # ==========================================
    REDIS_HOST: str = Field(
        default="localhost",
        description="Redis 서버 호스트"
    )

    REDIS_PORT: int = Field(
        default=6379,
        description="Redis 서버 포트"
    )

    REDIS_DB: int = Field(
        default=0,
        description="Redis 데이터베이스 번호"
    )

    REDIS_PASSWORD: Optional[str] = Field(
        default=None,
        description="Redis 비밀번호 (선택)"
    )

    CACHE_ENABLED: bool = Field(
        default=True,
        description="캐싱 활성화 여부"
    )

    # 레벨1: 질문 → 전체 응답 캐싱 TTL (초)
    CACHE_L1_TTL: int = Field(
        default=3600,
        description="레벨1 캐시 TTL (기본 1시간)"
    )

    # 레벨2: 벡터 검색 결과 캐싱 TTL (초)
    CACHE_L2_TTL: int = Field(
        default=7200,
        description="레벨2 캐시 TTL (기본 2시간)"
    )

    # 질문 정규화용 LLM 모델 (저비용 모델 권장)
    NORMALIZER_MODEL: str = Field(
        default="gpt-5-nano",
        description="질문 정규화용 LLM 모델"
    )

    # 캐시 초기화 여부
    RESET_CACHE: bool = Field(
        default=False,
        description="서버 시작 시 캐시 초기화 여부"
    )
    
    # ==========================================
    # 유효성 검증
    # ==========================================
    @field_validator('VECTOR_DB_TYPE')
    @classmethod
    def validate_vector_db_type(cls, v: str) -> str:
        """벡터 DB 타입 유효성 검증"""
        allowed = ['chroma', 'pgvector']
        if v.lower() not in allowed:
            raise ValueError(f"VECTOR_DB_TYPE은 {allowed} 중 하나여야 합니다.")
        return v.lower()

    @field_validator('EMBEDDING_DEVICE')
    @classmethod
    def validate_device(cls, v: str) -> str:
        """임베딩 디바이스 유효성 검증"""
        allowed = ['cpu', 'cuda']
        if v.lower() not in allowed:
            raise ValueError(f"EMBEDDING_DEVICE는 {allowed} 중 하나여야 합니다.")
        return v.lower()
    
    @field_validator('LOG_LEVEL')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """로그 레벨 유효성 검증"""
        allowed = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL은 {allowed} 중 하나여야 합니다.")
        return v.upper()
    
    @field_validator('OPENAI_API_KEY')
    @classmethod
    def validate_openai_key(cls, v: str) -> str:
        """OpenAI API 키 형식 검증"""
        if not v or v == "sk-your-openai-api-key-here":
            raise ValueError("유효한 OpenAI API 키를 설정해주세요.")
        return v
    
    class Config:
        """Pydantic 설정"""
        # .env 파일 경로 (프로젝트 루트 기준)
        env_file = ".env"
        env_file_encoding = "utf-8"
        # 대소문자 구분 안함
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    설정 싱글톤 인스턴스 반환
    
    lru_cache 데코레이터로 인해 한 번만 로딩됩니다.
    설정 재로딩이 필요하면 get_settings.cache_clear()를 호출하세요.
    
    Returns:
        Settings: 설정 객체
    
    사용 예시:
        settings = get_settings()
        print(settings.OPENAI_API_KEY)
    """
    return Settings()


# 전역 settings 객체 (편의를 위한 alias)
# 주의: 이 객체는 모듈 로딩 시점에 생성됩니다.
# 지연 로딩이 필요하면 get_settings() 함수를 사용하세요.
settings = get_settings()
