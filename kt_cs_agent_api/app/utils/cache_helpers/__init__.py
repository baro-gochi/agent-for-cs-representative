"""
API별 독립 캐시 헬퍼 모듈

각 API별로 독립적인 캐시 로직을 제공합니다.
나중에 하나의 API만 남길 경우, 해당 파일만 유지하면 됩니다.

구조:
- consultation_cache.py   : /consultation/assist 전용 (키워드추출 + 긴가이드)
- direct_keyword_cache.py : /comparison/direct-keyword 전용 (직접임베딩 + 핵심가이드)
- keyword_extraction_cache.py : /comparison/keyword-extraction 전용 (키워드추출 + 핵심가이드)
- direct_full_cache.py    : /comparison/direct-full-guide 전용 (직접임베딩 + 긴가이드)

캐시 키 구조:
- L1 (전체 응답): l1:{api_prefix}:{normalized_query_hash}
- L2 (검색 결과): l2:{search_type}:{query_hash}
  - search_type: "direct" (직접 임베딩) 또는 "keyword" (키워드 추출)
"""

from .consultation_cache import ConsultationCacheHelper
from .direct_keyword_cache import DirectKeywordCacheHelper
from .keyword_extraction_cache import KeywordExtractionCacheHelper
from .direct_full_cache import DirectFullCacheHelper

__all__ = [
    "ConsultationCacheHelper",
    "DirectKeywordCacheHelper",
    "KeywordExtractionCacheHelper",
    "DirectFullCacheHelper",
]
