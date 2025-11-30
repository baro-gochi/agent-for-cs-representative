"""
데이터베이스 모듈 패키지

이 패키지는 벡터 DB와 문서 레지스트리 관련 기능을 제공합니다.

사용 예시:
    from app.database import get_vector_db_manager, get_doc_registry
    
    # 벡터 DB 검색
    db = get_vector_db_manager()
    docs = db.similarity_search("검색어")
    
    # 문서 레지스트리 조회
    registry = get_doc_registry()
    path = registry.get_document_path("인터넷이용약관")
"""

from app.database.vector_db import (
    VectorDBManager,
    get_vector_db_manager,
    reset_vector_db_manager
)

from app.database.doc_registry import (
    DocumentRegistry,
    get_doc_registry,
    reset_doc_registry
)

__all__ = [
    "VectorDBManager",
    "get_vector_db_manager",
    "reset_vector_db_manager",
    "DocumentRegistry",
    "get_doc_registry",
    "reset_doc_registry"
]
