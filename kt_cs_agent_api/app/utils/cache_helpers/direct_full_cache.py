"""
/comparison/direct-full-guide API 전용 캐시 헬퍼

특징:
- 검색 방식: 질문 직접 임베딩 검색
- 가이드 유형: 긴 가이드 (response_guide)
- L1 캐시: 전체 응답 (documents, response_guide)
- L2 캐시: 검색 결과 (direct 기반)

이 API만 남길 경우:
- 이 파일만 유지
- comparison.py에서 이 헬퍼 사용
"""

import logging
from typing import Optional, List, Dict, Any

from .base_cache import BaseCacheHelper

logger = logging.getLogger(__name__)


class DirectFullCacheHelper(BaseCacheHelper):
    """
    /comparison/direct-full-guide 전용 캐시 헬퍼

    캐시 키 구조:
    - L1: direct_full_guide:{normalized_query_hash} → 전체 응답
    - L2: direct:{normalized_query_hash} → 직접 임베딩 기반 검색 결과
    """

    L1_PREFIX = "direct_full_guide"
    L2_PREFIX = "direct"  # 직접 임베딩 기반 검색

    @classmethod
    def build_l1_response(
        cls,
        documents: List,
        response_guide: Dict[str, Any]
    ) -> Dict[str, Any]:
        """L1 캐시에 저장할 응답 데이터 구성"""
        return {
            "documents": cls._documents_to_dict(documents),
            "response_guide": response_guide
        }

    @classmethod
    def get_search_method_display(cls, cache_status: str) -> str:
        """캐시 상태에 따른 search_method 표시 문자열"""
        if cache_status == "l1_hit":
            return "direct_embedding (L1 cached)"
        elif cache_status == "l2_hit":
            return "direct_embedding (L2 cached)"
        return "direct_embedding"
