"""
===========================================
LLM 기반 질문 정규화 서비스
===========================================

이 모듈은 들어오는 질문을 정규화하여
캐시 히트율을 높입니다.

정규화 기능:
- 공백/줄바꿈 정리
- 유사 표현 통일 (예: "위약금", "약정 해지금", "해지 위약금" → "위약금")
- 불필요한 조사/어미 정리
- 의미 보존하며 핵심 표현 추출

사용 예시:
    from app.utils.query_normalizer import normalize_query

    original = "저 약정 해지하려고 하는데 위약금이 얼마나 되는지요?"
    normalized = await normalize_query(original)
    # 결과: "약정 해지 위약금 금액"
"""

import re
import logging
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.config import settings
from app.utils.cache_manager import cache_manager

logger = logging.getLogger(__name__)


# 간단한 정규화 규칙 (LLM 호출 전 사전 처리)
# 주의: 조사 제거는 LLM에게 맡김 (단어 중간의 글자 손상 방지)
SIMPLE_NORMALIZE_PATTERNS = [
    # 공백 정리
    (r'\s+', ' '),
    # 물음표, 마침표 등 제거
    (r'[?？!！.。]+$', ''),
    # 존칭/어미 정리 (문장 끝에서만)
    (r'요$|니다$|습니다$|세요$|입니다$', ''),
    # 조사는 LLM이 처리하도록 제거하지 않음 (베이직 → 베 직 같은 오류 방지)
]


def simple_normalize(text: str) -> str:
    """
    간단한 규칙 기반 정규화 (LLM 호출 전 사전 처리)

    Args:
        text: 원본 텍스트

    Returns:
        str: 간단히 정규화된 텍스트
    """
    result = text.strip()

    for pattern, replacement in SIMPLE_NORMALIZE_PATTERNS:
        result = re.sub(pattern, replacement, result)

    # 연속 공백 정리
    result = re.sub(r'\s+', ' ', result).strip()

    return result


async def normalize_query_with_llm(query: str) -> str:
    """
    LLM을 사용하여 질문을 정규화

    유사한 의미의 질문들을 동일한 형태로 변환합니다.
    예: "위약금 얼마야?" = "해지 위약금 금액" = "약정 해지시 위약금"

    Args:
        query: 원본 질문

    Returns:
        str: 정규화된 질문
    """
    llm = ChatOpenAI(
        model=settings.ANALYZER_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        max_completion_tokens=100,
        reasoning_effort="minimal",  # gpt-5 계열 전용 옵션
        streaming=False
    )
    

    prompt = ChatPromptTemplate.from_template("""고객 문의를 캐싱용 정규화된 형태로 변환하세요.

## 절대 보존 항목 (생략 시 캐시 오류 발생!)
1. **요금제/상품 전체 이름**:
   - 예: "5G 슈퍼플랜 베이직", "5G 프리미어 에센셜", "LTE 다이렉트 45", "인기LTE 데이터ON"
   - ❌ "5G 요금제"로 축약 금지 → ✅ 정확한 요금제명 유지
2. **문의 유형 (동작/행위)**:
   - 일시정지, 해지, 변경, 가입, 해외로밍, 위약금, 데이터 초과 등
3. **구체적 조건/상황**:
   - 약정 기간 (24개월, 36개월)
   - 사용 기간 (12개월 사용)
   - 특수 상황 (해외 장기체류, 군입대, 휴학 등)

## 정규화 규칙
1. 조사/어미만 제거 (은/는/이/가/을/를/요/습니다)
2. 유사 표현 통일: 위약금/해지금→위약금, 해지/해약→해지
3. 핵심 요소는 모두 포함하여 15~30단어로 정리
4. 띄어쓰기로 구분

## 예시
원본: "[모바일] 5G 슈퍼플랜 베이직 24개월 약정 중 12개월 사용. 해외 장기체류로 인한 일시정지 가능 여부 및 약정 기간 영향 문의"
정규화: "5G 슈퍼플랜 베이직 24개월 약정 12개월 사용 해외 장기체류 일시정지 가능 약정 기간 영향"

원본: "스마트폰 5G 프리미어 에센셜 요금제 문의"
정규화: "5G 프리미어 에센셜 요금제 정보 문의"

원본: {query}

정규화:""")

    chain = prompt | llm | StrOutputParser()
    result = chain.invoke({"query": query})

    # LLM 출력에서 불필요한 prefix/suffix 정리
    result = result.strip()
    # "정규화:" 또는 "정규화 원본:" 같은 prefix 제거
    result = re.sub(r'^정규화[:\s]*', '', result)
    result = re.sub(r'^원본[:\s]*', '', result)
    # 따옴표 제거
    result = result.strip('"\'')

    return result.strip()


async def normalize_query(query: str, use_llm: bool = True) -> str:
    """
    질문 정규화 메인 함수

    1. 캐시에서 이미 정규화된 쿼리 확인
    2. 없으면 LLM으로 정규화 후 캐시에 저장

    Args:
        query: 원본 질문
        use_llm: LLM 사용 여부 (False면 간단한 규칙만 적용)

    Returns:
        str: 정규화된 질문
    """
    # 1. 간단한 규칙 기반 정규화 (항상 적용)
    simple_normalized = simple_normalize(query)

    if not use_llm:
        return simple_normalized

    # 2. 캐시에서 정규화된 쿼리 확인
    if cache_manager.is_connected():
        cached_normalized = await cache_manager.get_normalized_query(simple_normalized)
        if cached_normalized:
            logger.debug(f"[Normalizer] 캐시 히트: {cached_normalized[:30]}...")
            return cached_normalized

    # 3. LLM으로 정규화
    try:
        llm_normalized = await normalize_query_with_llm(simple_normalized)
        logger.info(f"[Normalizer] LLM 정규화: '{simple_normalized[:30]}...' → '{llm_normalized}'")

        # 4. 정규화 결과 캐시에 저장
        if cache_manager.is_connected():
            await cache_manager.set_normalized_query(simple_normalized, llm_normalized)

        return llm_normalized

    except Exception as e:
        logger.warning(f"[Normalizer] LLM 정규화 실패: {e}, 간단 정규화 결과 사용")
        return simple_normalized


async def batch_normalize_queries(queries: list[str]) -> list[str]:
    """
    여러 질문을 일괄 정규화

    Args:
        queries: 원본 질문 리스트

    Returns:
        list[str]: 정규화된 질문 리스트
    """
    results = []
    for query in queries:
        normalized = await normalize_query(query)
        results.append(normalized)
    return results


# 동의어 사전 (LLM 정규화 보완용)
SYNONYM_MAP = {
    # 위약금 관련
    "해지금": "위약금",
    "약정해지금": "위약금",
    "위약": "위약금",
    "해약금": "위약금",
    "해약": "해지",
    "해지위약금": "위약금",

    # 요금 관련
    "월요금": "요금",
    "요금제가격": "요금",
    "월납": "요금",

    # 변경 관련
    "교체": "변경",
    "바꾸기": "변경",
    "전환": "변경",

    # 가입 관련
    "신규가입": "가입",
    "신청": "가입",
    "개통": "가입",

    # 약정 관련
    "약정기간": "약정",
    "계약기간": "약정",
    "의무사용기간": "약정",
}


def apply_synonyms(text: str) -> str:
    """
    동의어 사전을 적용하여 추가 정규화

    Args:
        text: 정규화된 텍스트

    Returns:
        str: 동의어 적용된 텍스트
    """
    result = text
    for original, replacement in SYNONYM_MAP.items():
        result = result.replace(original, replacement)
    return result
