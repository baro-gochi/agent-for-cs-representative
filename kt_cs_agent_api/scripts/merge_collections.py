"""
ChromaDB 컬렉션 통합 스크립트

여러 컬렉션을 하나의 aicc_documents 컬렉션으로 통합합니다.
각 문서에 doc_category 메타데이터를 추가하여 카테고리 필터링이 가능하도록 합니다.

사용법:
    python scripts/merge_collections.py
"""

import chromadb
from collections import Counter

# ChromaDB 경로
CHROMA_DB_PATH = "/Users/jang-yunho/Desktop/project/kt_cs/chroma_db_plans"
TARGET_COLLECTION = "aicc_documents"

# 컬렉션명 → 서비스 카테고리 매핑
COLLECTION_TO_CATEGORY = {
    "kt_mobile_plans": "mobile",
    "kt_mobile_penalty": "mobile",  # 위약금도 mobile로 분류
    "kt_internet_plans": "internet",
    "kt_tv_plans": "tv",
    "kt_bundle_discount": "bundle",
    "kt_membership": "membership",
}


def merge_collections():
    """모든 컬렉션을 aicc_documents로 통합"""

    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    # 기존 aicc_documents 컬렉션이 있으면 삭제
    try:
        client.delete_collection(TARGET_COLLECTION)
        print(f"기존 '{TARGET_COLLECTION}' 컬렉션 삭제됨")
    except Exception:
        pass

    # 새 컬렉션 생성
    target_collection = client.create_collection(
        name=TARGET_COLLECTION,
        metadata={"description": "통합 문서 컬렉션 (카테고리별 필터링 지원)"}
    )
    print(f"새 '{TARGET_COLLECTION}' 컬렉션 생성됨")

    # 각 컬렉션에서 문서 가져와서 통합
    total_docs = 0
    category_counts = Counter()

    for col_name, category in COLLECTION_TO_CATEGORY.items():
        try:
            source_collection = client.get_collection(col_name)

            # 모든 데이터 가져오기
            data = source_collection.get(
                include=["embeddings", "documents", "metadatas"]
            )

            if not data["ids"]:
                print(f"  - {col_name}: 문서 없음, 스킵")
                continue

            # 메타데이터에 doc_category 추가
            new_metadatas = []
            for meta in data["metadatas"]:
                new_meta = meta.copy() if meta else {}
                new_meta["doc_category"] = category
                new_meta["source_collection"] = col_name  # 원본 컬렉션 추적용
                new_metadatas.append(new_meta)

            # ID 중복 방지를 위해 접두어 추가
            new_ids = [f"{col_name}_{id}" for id in data["ids"]]

            # 타겟 컬렉션에 추가
            target_collection.add(
                ids=new_ids,
                embeddings=data["embeddings"],
                documents=data["documents"],
                metadatas=new_metadatas
            )

            doc_count = len(data["ids"])
            total_docs += doc_count
            category_counts[category] += doc_count
            print(f"  - {col_name} → {category}: {doc_count}개 문서 추가됨")

        except Exception as e:
            print(f"  - {col_name}: 오류 발생 - {e}")

    print(f"\n=== 통합 완료 ===")
    print(f"총 문서 수: {total_docs}개")
    print(f"\n카테고리별 문서 수:")
    for cat, count in sorted(category_counts.items()):
        print(f"  - {cat}: {count}개")

    # 검증
    print(f"\n=== 검증 ===")
    verify_collection = client.get_collection(TARGET_COLLECTION)
    print(f"aicc_documents 컬렉션 문서 수: {verify_collection.count()}개")

    return total_docs


if __name__ == "__main__":
    merge_collections()
