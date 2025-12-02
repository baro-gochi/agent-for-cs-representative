"""
===========================================
벡터 데이터베이스 연결 및 관리 모듈
===========================================

이 모듈은 ChromaDB 벡터 스토어의 연결과 검색을 담당합니다.
- 임베딩 모델 초기화
- ChromaDB 연결 관리
- 유사도 검색 기능

수정 가이드:
    1. 다른 벡터 DB(Pinecone, Weaviate 등)로 교체 시 이 파일만 수정
    2. 임베딩 모델 변경 시 get_embedding_model() 함수 수정
    3. 검색 로직 변경 시 VectorDBManager 클래스 메서드 수정

사용 예시:
    from app.database.vector_db import get_vector_db_manager
    
    db_manager = get_vector_db_manager()
    results = db_manager.similarity_search("검색 키워드", k=3)
"""

import logging
from typing import List, Dict, Any, Optional
from functools import lru_cache

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

from app.config import settings

# 로거 설정
logger = logging.getLogger(__name__)


class VectorDBManager:
    """
    벡터 데이터베이스 관리 클래스
    
    ChromaDB와의 연결을 관리하고 검색 기능을 제공합니다.
    싱글톤 패턴으로 구현되어 있어 애플리케이션 전체에서
    하나의 인스턴스만 사용됩니다.
    
    Attributes:
        embedding_model: HuggingFace 임베딩 모델
        vectorstore: ChromaDB 벡터 스토어 인스턴스
        is_initialized: 초기화 완료 여부
    """
    
    def __init__(self):
        """
        VectorDBManager 초기화
        
        실제 DB 연결은 initialize() 메서드에서 수행됩니다.
        lazy loading 패턴으로 필요할 때만 연결합니다.
        """
        self.embedding_model = None
        self.vectorstore = None
        self.is_initialized = False
        logger.info("VectorDBManager 인스턴스 생성됨 (아직 초기화 안됨)")
    
    def initialize(self) -> None:
        """
        벡터 DB 연결 초기화
        
        임베딩 모델을 로드하고 ChromaDB에 연결합니다.
        이 메서드는 첫 검색 요청 시 자동으로 호출됩니다.
        
        Raises:
            RuntimeError: DB 연결 실패 시
        
        Note:
            초기화에는 임베딩 모델 로딩 시간이 포함되어
            첫 요청 시 약간의 지연이 발생할 수 있습니다.
        """
        if self.is_initialized:
            logger.debug("이미 초기화됨 - 스킵")
            return
        
        try:
            logger.info("벡터 DB 초기화 시작...")
            
            # 1. 임베딩 모델 로드 (OpenAI 임베딩 사용)
            logger.info(f"임베딩 모델 로딩 중: {settings.EMBEDDING_MODEL_NAME}")
            self.embedding_model = OpenAIEmbeddings(
                model=settings.EMBEDDING_MODEL_NAME,
                openai_api_key=settings.OPENAI_API_KEY
            )
            logger.info("임베딩 모델 로딩 완료")
            
            # 2. ChromaDB 연결
            logger.info(f"ChromaDB 연결 중: {settings.CHROMA_DB_PATH}")
            self.vectorstore = Chroma(
                persist_directory=settings.CHROMA_DB_PATH,
                embedding_function=self.embedding_model,
                collection_name=settings.CHROMA_COLLECTION_NAME
            )
            logger.info(f"ChromaDB 연결 완료 (컬렉션: {settings.CHROMA_COLLECTION_NAME})")
            
            self.is_initialized = True
            logger.info("벡터 DB 초기화 완료")
            
        except Exception as e:
            logger.error(f"벡터 DB 초기화 실패: {str(e)}")
            raise RuntimeError(f"벡터 DB 초기화 실패: {str(e)}")
    
    def ensure_initialized(self) -> None:
        """
        초기화 상태 확인 및 필요시 초기화 수행
        
        모든 검색 메서드에서 내부적으로 호출됩니다.
        """
        if not self.is_initialized:
            self.initialize()
    
    def similarity_search(
        self, 
        query: str, 
        k: int = 3,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        유사도 기반 문서 검색
        
        주어진 쿼리와 가장 유사한 문서들을 반환합니다.
        
        Args:
            query: 검색 쿼리 텍스트
            k: 반환할 문서 수 (기본값: 3)
            filter_dict: 메타데이터 필터 조건 (선택)
                예: {"source": "/path/to/doc.pdf"}
        
        Returns:
            List[Document]: 유사도 순으로 정렬된 문서 리스트
        
        Raises:
            RuntimeError: 검색 실패 시
        
        사용 예시:
            # 기본 검색
            docs = db_manager.similarity_search("해지 위약금", k=5)
            
            # 필터 적용 검색
            docs = db_manager.similarity_search(
                "해지 위약금",
                k=2,
                filter_dict={"source": "/content/약관.pdf"}
            )
        """
        self.ensure_initialized()
        
        try:
            logger.debug(f"검색 수행: query='{query[:50]}...', k={k}, filter={filter_dict}")
            
            if filter_dict:
                results = self.vectorstore.similarity_search(
                    query,
                    k=k,
                    filter=filter_dict
                )
            else:
                results = self.vectorstore.similarity_search(query, k=k)
            
            logger.debug(f"검색 완료: {len(results)}개 문서 반환")
            return results
            
        except Exception as e:
            logger.error(f"검색 실패: {str(e)}")
            raise RuntimeError(f"벡터 검색 실패: {str(e)}")
    
    def similarity_search_with_score(
        self, 
        query: str, 
        k: int = 3,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[tuple]:
        """
        유사도 점수와 함께 문서 검색
        
        Args:
            query: 검색 쿼리 텍스트
            k: 반환할 문서 수
            filter_dict: 메타데이터 필터 조건
        
        Returns:
            List[tuple]: (Document, score) 튜플 리스트
                score가 낮을수록 유사도가 높음 (거리 기반)
        """
        self.ensure_initialized()
        
        try:
            if filter_dict:
                results = self.vectorstore.similarity_search_with_score(
                    query, k=k, filter=filter_dict
                )
            else:
                results = self.vectorstore.similarity_search_with_score(query, k=k)
            
            return results
            
        except Exception as e:
            logger.error(f"검색(with score) 실패: {str(e)}")
            raise RuntimeError(f"벡터 검색 실패: {str(e)}")
    
    def get_collection_info(self) -> Dict[str, Any]:
        """
        컬렉션 정보 조회
        
        현재 연결된 컬렉션의 메타데이터를 반환합니다.
        헬스 체크나 디버깅에 유용합니다.
        
        Returns:
            Dict: 컬렉션 정보
                - collection_name: 컬렉션 이름
                - count: 저장된 문서 수
                - is_initialized: 초기화 상태
        """
        self.ensure_initialized()
        
        try:
            # ChromaDB 컬렉션 정보 조회
            collection = self.vectorstore._collection
            count = collection.count()
            
            return {
                "collection_name": settings.CHROMA_COLLECTION_NAME,
                "db_path": settings.CHROMA_DB_PATH,
                "document_count": count,
                "is_initialized": self.is_initialized,
                "embedding_model": settings.EMBEDDING_MODEL_NAME
            }
            
        except Exception as e:
            logger.error(f"컬렉션 정보 조회 실패: {str(e)}")
            return {
                "collection_name": settings.CHROMA_COLLECTION_NAME,
                "is_initialized": self.is_initialized,
                "error": str(e)
            }
    
    def health_check(self) -> bool:
        """
        DB 연결 상태 확인
        
        Returns:
            bool: 정상이면 True, 문제 있으면 False
        """
        try:
            self.ensure_initialized()
            # 간단한 테스트 쿼리로 연결 확인
            self.vectorstore.similarity_search("test", k=1)
            return True
        except Exception as e:
            logger.error(f"Health check 실패: {str(e)}")
            return False


# ==========================================
# 싱글톤 인스턴스 관리
# ==========================================

# 전역 인스턴스 (lazy initialization)
_vector_db_manager: Optional[VectorDBManager] = None


def get_vector_db_manager() -> VectorDBManager:
    """
    VectorDBManager 싱글톤 인스턴스 반환
    
    애플리케이션 전체에서 하나의 DB 연결만 사용합니다.
    
    Returns:
        VectorDBManager: DB 매니저 인스턴스
    
    사용 예시:
        db_manager = get_vector_db_manager()
        results = db_manager.similarity_search("키워드")
    """
    global _vector_db_manager
    
    if _vector_db_manager is None:
        _vector_db_manager = VectorDBManager()
    
    return _vector_db_manager


def reset_vector_db_manager() -> None:
    """
    DB 매니저 인스턴스 리셋
    
    테스트나 설정 변경 후 재연결이 필요할 때 사용합니다.
    
    Warning:
        운영 환경에서 사용 시 주의가 필요합니다.
        진행 중인 요청이 실패할 수 있습니다.
    """
    global _vector_db_manager
    
    logger.warning("VectorDBManager 리셋 수행")
    _vector_db_manager = None
