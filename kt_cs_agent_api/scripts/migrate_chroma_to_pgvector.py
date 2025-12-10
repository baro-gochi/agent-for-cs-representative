"""
===========================================
ChromaDB → PGVector 마이그레이션 스크립트
===========================================

기존 ChromaDB의 벡터 데이터를 PostgreSQL + pgvector로 마이그레이션합니다.

사용법:
    # 1. PostgreSQL 데이터베이스 및 pgvector 확장 먼저 설정
    # 2. .env 파일에서 PostgreSQL 연결 정보 설정
    # 3. 스크립트 실행

    python scripts/migrate_chroma_to_pgvector.py

주의사항:
    - 마이그레이션 전 PostgreSQL에 pgvector 확장이 설치되어 있어야 함
    - 기존 ChromaDB 경로가 .env의 CHROMA_DB_PATH에 설정되어 있어야 함
    - 마이그레이션 후 VECTOR_DB_TYPE=pgvector로 변경
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from typing import List, Dict, Any
from tqdm import tqdm

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_postgres import PGVector
from langchain_core.documents import Document

from dotenv import load_dotenv

# .env 파일 로드
load_dotenv(project_root / ".env")

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_chroma_client() -> Chroma:
    """ChromaDB 클라이언트 생성"""
    chroma_path = os.getenv("CHROMA_DB_PATH")
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", "kt_terms")

    if not chroma_path:
        raise ValueError("CHROMA_DB_PATH가 설정되지 않았습니다.")

    logger.info(f"ChromaDB 연결 중: {chroma_path}")

    embedding_model = OpenAIEmbeddings(
        model=os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small"),
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

    return Chroma(
        persist_directory=chroma_path,
        embedding_function=embedding_model,
        collection_name=collection_name
    )


def get_pgvector_client() -> PGVector:
    """PGVector 클라이언트 생성"""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "vectordb")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", "kt_terms")

    connection_string = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"

    logger.info(f"PGVector 연결 중: {host}:{port}/{db}")

    embedding_model = OpenAIEmbeddings(
        model=os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small"),
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

    return PGVector(
        embeddings=embedding_model,
        collection_name=collection_name,
        connection=connection_string,
        use_jsonb=True,
    )


def extract_all_documents_from_chroma(chroma: Chroma) -> List[Dict[str, Any]]:
    """ChromaDB에서 모든 문서 추출"""
    logger.info("ChromaDB에서 문서 추출 중...")

    collection = chroma._collection
    total_count = collection.count()
    logger.info(f"총 {total_count}개 문서 발견")

    if total_count == 0:
        return []

    # 모든 문서 가져오기 (배치로 처리)
    batch_size = 1000
    all_documents = []

    for offset in range(0, total_count, batch_size):
        result = collection.get(
            limit=batch_size,
            offset=offset,
            include=["documents", "metadatas", "embeddings"]
        )

        for i in range(len(result["ids"])):
            doc_data = {
                "id": result["ids"][i],
                "content": result["documents"][i] if result["documents"] else "",
                "metadata": result["metadatas"][i] if result["metadatas"] else {},
                "embedding": result["embeddings"][i] if result["embeddings"] else None
            }
            all_documents.append(doc_data)

        logger.info(f"추출 진행: {min(offset + batch_size, total_count)}/{total_count}")

    return all_documents


def migrate_to_pgvector(documents: List[Dict[str, Any]], pgvector: PGVector, batch_size: int = 100):
    """문서를 PGVector로 마이그레이션"""
    logger.info(f"PGVector로 {len(documents)}개 문서 마이그레이션 시작...")

    # Document 객체로 변환
    docs = []
    for doc_data in documents:
        doc = Document(
            page_content=doc_data["content"],
            metadata=doc_data["metadata"]
        )
        docs.append(doc)

    # 배치로 추가
    for i in tqdm(range(0, len(docs), batch_size), desc="마이그레이션 진행"):
        batch = docs[i:i + batch_size]
        pgvector.add_documents(batch)

    logger.info("마이그레이션 완료!")


def verify_migration(chroma: Chroma, pgvector: PGVector):
    """마이그레이션 검증"""
    logger.info("마이그레이션 검증 중...")

    # ChromaDB 문서 수
    chroma_count = chroma._collection.count()

    # PGVector에서 테스트 검색
    test_results = pgvector.similarity_search("테스트", k=1)

    logger.info(f"ChromaDB 문서 수: {chroma_count}")
    logger.info(f"PGVector 검색 테스트: {'성공' if test_results else '결과 없음'}")

    if test_results:
        logger.info(f"샘플 문서: {test_results[0].page_content[:100]}...")


def main():
    """메인 실행 함수"""
    print("=" * 50)
    print("ChromaDB → PGVector 마이그레이션")
    print("=" * 50)

    # 환경 변수 확인
    required_vars = ["OPENAI_API_KEY", "CHROMA_DB_PATH", "POSTGRES_HOST", "POSTGRES_DB"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logger.error(f"필수 환경 변수가 설정되지 않았습니다: {missing_vars}")
        sys.exit(1)

    try:
        # 1. ChromaDB 연결
        chroma = get_chroma_client()

        # 2. 문서 추출
        documents = extract_all_documents_from_chroma(chroma)

        if not documents:
            logger.warning("마이그레이션할 문서가 없습니다.")
            return

        # 3. PGVector 연결
        pgvector = get_pgvector_client()

        # 4. 마이그레이션 실행
        migrate_to_pgvector(documents, pgvector)

        # 5. 검증
        verify_migration(chroma, pgvector)

        print("\n" + "=" * 50)
        print("마이그레이션 완료!")
        print("=" * 50)
        print("\n다음 단계:")
        print("1. .env 파일에서 VECTOR_DB_TYPE=pgvector로 변경")
        print("2. 서버 재시작")

    except Exception as e:
        logger.error(f"마이그레이션 실패: {str(e)}")
        raise


if __name__ == "__main__":
    main()
