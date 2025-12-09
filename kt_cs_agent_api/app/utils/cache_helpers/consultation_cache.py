"""
/consultation/assist API 전용 캐시 헬퍼

특징:
- 검색 방식: 키워드 추출 후 검색
- 가이드 유형: 긴 가이드 (response_guide)
- L1 캐시: 전체 응답 (extracted_keywords, documents, response_guide)
- L2 캐시: 검색 결과 (keyword 기반)

이 API만 남길 경우:
- 이 파일만 유지
- consultation.py에서 이 헬퍼 사용
"""

import logging
from typing import Optional, List, Dict, Any

from .base_cache import BaseCacheHelper

logger = logging.getLogger(__name__)


class ConsultationCacheHelper(BaseCacheHelper):
    """
    /consultation/assist 전용 캐시 헬퍼

    캐시 키 구조:
    - L1: consultation:{normalized_query_hash} → 전체 응답
    - L2: keyword:{normalized_query_hash} → 키워드 추출 기반 검색 결과
    """

    L1_PREFIX = "consultation"
    L2_PREFIX = "keyword"  # 키워드 추출 기반 검색

    @classmethod
    def build_l1_response(
        cls,
        extracted_keywords: str,
        target_document: str,
        documents: List,
        response_guide: Dict[str, Any]
    ) -> Dict[str, Any]:
        """L1 캐시에 저장할 응답 데이터 구성"""
        return {
            "extracted_keywords": extracted_keywords,
            "target_document": target_document,
            "documents": cls._documents_to_dict(documents),
            "response_guide": response_guide
        }

    @classmethod
    def get_search_method_display(cls, cache_status: str) -> str:
        """캐시 상태에 따른 search_method 표시 문자열"""
        if cache_status == "l1_hit":
            return "keyword_extraction (L1 cached)"
        elif cache_status == "l2_hit":
            return "keyword_extraction (L2 cached)"
        return "keyword_extraction"
