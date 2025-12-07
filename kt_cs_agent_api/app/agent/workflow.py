"""
===========================================
LangGraph 워크플로우 구성
===========================================

이 모듈은 LangGraph 워크플로우(그래프)를 구성하고
실행 가능한 Agent 애플리케이션을 생성합니다.

워크플로우 구조:
    START → analyzer → searcher → response_generator → END

수정 가이드:
    - 노드 추가/제거: workflow.add_node() / add_edge() 수정
    - 조건부 분기: add_conditional_edges() 사용
    - 병렬 처리: 여러 엣지를 같은 노드에서 분기

사용 예시:
    from app.agent.workflow import get_agent_app, run_consultation
    
    # 방법 1: 직접 실행
    result = run_consultation("인터넷 해지 문의")
    
    # 방법 2: 앱 인스턴스 사용
    app = get_agent_app()
    result = app.invoke({"summary": "인터넷 해지 문의"})
"""

import logging
from typing import Dict, Any, Optional
from functools import lru_cache

from langgraph.graph import StateGraph, START, END

from app.agent.state import AgentState, create_initial_state
from app.agent.nodes import (
    analyzer_node,
    search_node,
    response_generator_node,
    direct_embedding_search_node,
    keyword_guide_node
)

# 로거 설정
logger = logging.getLogger(__name__)


def build_workflow() -> StateGraph:
    """
    LangGraph 워크플로우 구성
    
    노드와 엣지를 정의하여 워크플로우를 구성합니다.
    
    Returns:
        StateGraph: 구성된 워크플로우 (컴파일 전)
    
    워크플로우 구조:
        [START]
           ↓
        [analyzer] - 상담 분석 및 키워드 추출
           ↓
        [searcher] - 벡터 DB 검색
           ↓
        [response_generator] - 대응방안 생성
           ↓
        [END]
    """
    logger.info("LangGraph 워크플로우 구성 중...")
    
    # StateGraph 인스턴스 생성
    workflow = StateGraph(AgentState)
    
    # -----------------------------------------
    # 노드 등록
    # -----------------------------------------
    # 각 노드는 state를 입력받아 업데이트할 필드를 dict로 반환
    workflow.add_node("analyzer", analyzer_node)
    workflow.add_node("searcher", search_node)
    workflow.add_node("response_generator", response_generator_node)
    
    # -----------------------------------------
    # 엣지 연결 (순차 실행)
    # -----------------------------------------
    workflow.add_edge(START, "analyzer")
    workflow.add_edge("analyzer", "searcher")
    workflow.add_edge("searcher", "response_generator")
    workflow.add_edge("response_generator", END)
    
    logger.info("워크플로우 구성 완료")
    return workflow


@lru_cache(maxsize=1)
def get_agent_app():
    """
    컴파일된 Agent 애플리케이션 반환 (싱글톤)
    
    워크플로우를 컴파일하여 실행 가능한 앱을 생성합니다.
    lru_cache로 한 번만 컴파일됩니다.
    
    Returns:
        CompiledGraph: 실행 가능한 Agent 앱
    
    사용 예시:
        app = get_agent_app()
        result = app.invoke({"summary": "상담 내용"})
    """
    logger.info("Agent 애플리케이션 컴파일 중...")
    
    workflow = build_workflow()
    app = workflow.compile()
    
    logger.info("Agent 애플리케이션 컴파일 완료")
    return app


def run_consultation(summary: str) -> Dict[str, Any]:
    """
    상담 Agent 실행 (편의 함수)
    
    상담 요약을 입력받아 전체 워크플로우를 실행합니다.
    
    Args:
        summary: 상담 내용 요약 텍스트
    
    Returns:
        Dict: 워크플로우 실행 결과
            - summary: 원본 입력
            - target_doc_name: 선택된 문서
            - search_query: 추출된 키워드
            - documents: 검색된 문서 리스트
            - response_guide: 생성된 대응방안
    
    Raises:
        Exception: 워크플로우 실행 중 오류 발생 시
    
    사용 예시:
        result = run_consultation("인터넷 해지 시 위약금 문의")
        print(result["response_guide"])
    """
    logger.info(f"상담 Agent 실행: '{summary[:50]}...'")
    
    # Agent 앱 가져오기
    app = get_agent_app()
    
    # 초기 상태 생성
    initial_state = create_initial_state(summary)
    
    # 워크플로우 실행
    try:
        result = app.invoke(initial_state)
        logger.info("상담 Agent 실행 완료")
        return result
    except Exception as e:
        logger.error(f"상담 Agent 실행 실패: {e}")
        raise


async def run_consultation_async(summary: str) -> Dict[str, Any]:
    """
    상담 Agent 비동기 실행
    
    FastAPI의 비동기 엔드포인트에서 사용합니다.
    
    Args:
        summary: 상담 내용 요약 텍스트
    
    Returns:
        Dict: 워크플로우 실행 결과
    
    Note:
        현재는 동기 실행을 래핑한 형태입니다.
        LangGraph의 ainvoke가 안정화되면 업데이트 필요.
    """
    import asyncio
    
    # 동기 함수를 별도 스레드에서 실행
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_consultation, summary)
    return result


def reset_agent_app() -> None:
    """
    Agent 앱 캐시 초기화
    
    설정 변경 후 Agent를 재컴파일해야 할 때 사용합니다.
    
    Warning:
        운영 환경에서 사용 시 주의가 필요합니다.
    """
    logger.warning("Agent 앱 캐시 초기화")
    get_agent_app.cache_clear()


# ==========================================
# 전문가용 워크플로우 (응답 생성 제외)
# ==========================================

def build_expert_workflow() -> StateGraph:
    """
    전문가용 워크플로우 구성 (응답 생성 노드 제외)
    
    신입 상담원용과 동일하지만 response_generator 노드가 없습니다.
    
    Returns:
        StateGraph: 구성된 워크플로우 (컴파일 전)
    
    워크플로우 구조:
        [START]
           ↓
        [analyzer] - 상담 분석 및 키워드 추출
           ↓
        [searcher] - 벡터 DB 검색
           ↓
        [END]  ← response_generator 없음!
    """
    logger.info("전문가용 워크플로우 구성 중...")
    
    # StateGraph 인스턴스 생성
    workflow = StateGraph(AgentState)
    
    # 노드 등록 (response_generator 제외)
    workflow.add_node("analyzer", analyzer_node)
    workflow.add_node("searcher", search_node)
    
    # 엣지 연결 (searcher에서 바로 END)
    workflow.add_edge(START, "analyzer")
    workflow.add_edge("analyzer", "searcher")
    workflow.add_edge("searcher", END)  # response_generator 스킵
    
    logger.info("전문가용 워크플로우 구성 완료")
    return workflow


@lru_cache(maxsize=1)
def get_expert_app():
    """
    전문가용 Agent 애플리케이션 반환 (싱글톤)
    
    응답 생성 노드가 제외된 워크플로우입니다.
    키워드 추출 + 벡터 검색만 수행합니다.
    
    Returns:
        CompiledGraph: 실행 가능한 전문가용 Agent 앱
    """
    logger.info("전문가용 Agent 애플리케이션 컴파일 중...")
    
    workflow = build_expert_workflow()
    app = workflow.compile()
    
    logger.info("전문가용 Agent 애플리케이션 컴파일 완료")
    return app


def run_expert_search(summary: str, max_docs: int = 5) -> Dict[str, Any]:
    """
    전문가용 검색 실행 (키워드 추출 + 벡터 검색만)
    
    신입 상담원용 Agent에서 response_generator 노드만 제외하고 실행합니다.
    
    Args:
        summary: 상담 내용 요약 텍스트
        max_docs: 최대 검색 문서 수 (search_node의 k값에는 영향 없음)
    
    Returns:
        Dict: 워크플로우 실행 결과
            - summary: 원본 입력
            - target_doc_name: 선택된 문서
            - search_query: 추출된 키워드
            - documents: 검색된 문서 리스트
            - response_guide: 빈 문자열 (생성 안 함)
    
    Note:
        response_guide는 빈 문자열로 반환됩니다.
        전문가는 검색 결과만 보고 직접 판단합니다.
    """
    logger.info(f"전문가용 검색 실행: '{summary[:50]}...'")
    
    # 전문가용 앱 가져오기
    app = get_expert_app()
    
    # 초기 상태 생성
    initial_state = create_initial_state(summary)
    
    # 워크플로우 실행
    try:
        result = app.invoke(initial_state)
        logger.info("전문가용 검색 실행 완료")
        return result
    except Exception as e:
        logger.error(f"전문가용 검색 실행 실패: {e}")
        raise


async def run_expert_search_async(summary: str, max_docs: int = 5) -> Dict[str, Any]:
    """
    전문가용 검색 비동기 실행

    FastAPI의 비동기 엔드포인트에서 사용합니다.

    Args:
        summary: 상담 내용 요약 텍스트
        max_docs: 최대 검색 문서 수

    Returns:
        Dict: 워크플로우 실행 결과
    """
    import asyncio

    # 동기 함수를 별도 스레드에서 실행
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: run_expert_search(summary, max_docs)
    )
    return result


# ==========================================
# [신규] 직접 임베딩 검색 워크플로우
# ==========================================

def build_direct_search_workflow() -> StateGraph:
    """
    직접 임베딩 검색 워크플로우 구성

    키워드 추출 없이 요약문 자체를 임베딩하여 검색합니다.

    Returns:
        StateGraph: 구성된 워크플로우 (컴파일 전)

    워크플로우 구조:
        [START]
           ↓
        [direct_searcher] - 요약문 직접 임베딩 검색
           ↓
        [END]
    """
    logger.info("직접 임베딩 검색 워크플로우 구성 중...")

    workflow = StateGraph(AgentState)

    # 노드 등록 (direct_embedding_search_node만)
    workflow.add_node("direct_searcher", direct_embedding_search_node)

    # 엣지 연결
    workflow.add_edge(START, "direct_searcher")
    workflow.add_edge("direct_searcher", END)

    logger.info("직접 임베딩 검색 워크플로우 구성 완료")
    return workflow


@lru_cache(maxsize=1)
def get_direct_search_app():
    """
    직접 임베딩 검색 Agent 애플리케이션 반환 (싱글톤)
    """
    logger.info("직접 임베딩 검색 Agent 컴파일 중...")
    workflow = build_direct_search_workflow()
    app = workflow.compile()
    logger.info("직접 임베딩 검색 Agent 컴파일 완료")
    return app


def run_direct_search(summary: str) -> Dict[str, Any]:
    """
    직접 임베딩 검색 실행

    키워드 추출 없이 요약문 자체를 임베딩하여 벡터 DB 검색만 수행합니다.

    Args:
        summary: 상담 내용 요약 텍스트

    Returns:
        Dict: 워크플로우 실행 결과
            - documents: 검색된 문서 리스트
    """
    logger.info(f"직접 임베딩 검색 실행: '{summary[:50]}...'")

    app = get_direct_search_app()
    initial_state = create_initial_state(summary)

    try:
        result = app.invoke(initial_state)
        logger.info("직접 임베딩 검색 실행 완료")
        return result
    except Exception as e:
        logger.error(f"직접 임베딩 검색 실행 실패: {e}")
        raise


async def run_direct_search_async(summary: str) -> Dict[str, Any]:
    """직접 임베딩 검색 비동기 실행"""
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_direct_search, summary)
    return result


# ==========================================
# [신규] 직접 임베딩 + 핵심 가이드 워크플로우
# ==========================================

def build_direct_keyword_guide_workflow() -> StateGraph:
    """
    직접 임베딩 검색 + 핵심 가이드 워크플로우 구성

    워크플로우 구조:
        [START]
           ↓
        [direct_searcher] - 요약문 직접 임베딩 검색
           ↓
        [keyword_guide] - 핵심 키워드 기반 간결 가이드 생성
           ↓
        [END]
    """
    logger.info("직접 임베딩 + 핵심 가이드 워크플로우 구성 중...")

    workflow = StateGraph(AgentState)

    workflow.add_node("direct_searcher", direct_embedding_search_node)
    workflow.add_node("keyword_guide", keyword_guide_node)

    workflow.add_edge(START, "direct_searcher")
    workflow.add_edge("direct_searcher", "keyword_guide")
    workflow.add_edge("keyword_guide", END)

    logger.info("직접 임베딩 + 핵심 가이드 워크플로우 구성 완료")
    return workflow


@lru_cache(maxsize=1)
def get_direct_keyword_guide_app():
    """직접 임베딩 + 핵심 가이드 Agent 애플리케이션 반환 (싱글톤)"""
    logger.info("직접 임베딩 + 핵심 가이드 Agent 컴파일 중...")
    workflow = build_direct_keyword_guide_workflow()
    app = workflow.compile()
    logger.info("직접 임베딩 + 핵심 가이드 Agent 컴파일 완료")
    return app


def run_direct_keyword_guide(summary: str) -> Dict[str, Any]:
    """
    직접 임베딩 검색 + 핵심 가이드 생성 실행

    요약문을 직접 임베딩하여 검색 후 핵심 키워드 기반 간결 가이드를 생성합니다.

    Args:
        summary: 상담 내용 요약 텍스트

    Returns:
        Dict: 워크플로우 실행 결과
            - documents: 검색된 문서 리스트
            - keyword_guide: 핵심 키워드 기반 간결 가이드
    """
    logger.info(f"직접 임베딩 + 핵심 가이드 실행: '{summary[:50]}...'")

    app = get_direct_keyword_guide_app()
    initial_state = create_initial_state(summary)

    try:
        result = app.invoke(initial_state)
        logger.info("직접 임베딩 + 핵심 가이드 실행 완료")
        return result
    except Exception as e:
        logger.error(f"직접 임베딩 + 핵심 가이드 실행 실패: {e}")
        raise


async def run_direct_keyword_guide_async(summary: str) -> Dict[str, Any]:
    """직접 임베딩 + 핵심 가이드 비동기 실행"""
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_direct_keyword_guide, summary)
    return result


# ==========================================
# [신규] 키워드 추출 + 검색 + 핵심 가이드 워크플로우
# ==========================================

def build_keyword_extraction_guide_workflow() -> StateGraph:
    """
    키워드 추출 + 검색 + 핵심 가이드 워크플로우 구성

    기존 analyzer + search 노드를 사용하되, 핵심 가이드를 생성합니다.

    워크플로우 구조:
        [START]
           ↓
        [analyzer] - 키워드 추출
           ↓
        [searcher] - 벡터 DB 검색
           ↓
        [keyword_guide] - 핵심 키워드 기반 간결 가이드 생성
           ↓
        [END]
    """
    logger.info("키워드 추출 + 핵심 가이드 워크플로우 구성 중...")

    workflow = StateGraph(AgentState)

    workflow.add_node("analyzer", analyzer_node)
    workflow.add_node("searcher", search_node)
    workflow.add_node("keyword_guide", keyword_guide_node)

    workflow.add_edge(START, "analyzer")
    workflow.add_edge("analyzer", "searcher")
    workflow.add_edge("searcher", "keyword_guide")
    workflow.add_edge("keyword_guide", END)

    logger.info("키워드 추출 + 핵심 가이드 워크플로우 구성 완료")
    return workflow


@lru_cache(maxsize=1)
def get_keyword_extraction_guide_app():
    """키워드 추출 + 핵심 가이드 Agent 애플리케이션 반환 (싱글톤)"""
    logger.info("키워드 추출 + 핵심 가이드 Agent 컴파일 중...")
    workflow = build_keyword_extraction_guide_workflow()
    app = workflow.compile()
    logger.info("키워드 추출 + 핵심 가이드 Agent 컴파일 완료")
    return app


def run_keyword_extraction_guide(summary: str) -> Dict[str, Any]:
    """
    키워드 추출 + 검색 + 핵심 가이드 생성 실행

    기존 analyzer + search를 사용하여 검색 후 핵심 가이드를 생성합니다.

    Args:
        summary: 상담 내용 요약 텍스트

    Returns:
        Dict: 워크플로우 실행 결과
            - search_query: 추출된 키워드
            - documents: 검색된 문서 리스트
            - keyword_guide: 핵심 키워드 기반 간결 가이드
    """
    logger.info(f"키워드 추출 + 핵심 가이드 실행: '{summary[:50]}...'")

    app = get_keyword_extraction_guide_app()
    initial_state = create_initial_state(summary)

    try:
        result = app.invoke(initial_state)
        logger.info("키워드 추출 + 핵심 가이드 실행 완료")
        return result
    except Exception as e:
        logger.error(f"키워드 추출 + 핵심 가이드 실행 실패: {e}")
        raise


async def run_keyword_extraction_guide_async(summary: str) -> Dict[str, Any]:
    """키워드 추출 + 핵심 가이드 비동기 실행"""
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_keyword_extraction_guide, summary)
    return result


# ==========================================
# [신규] 직접 임베딩 + 긴 가이드 워크플로우
# ==========================================

def build_direct_full_guide_workflow() -> StateGraph:
    """
    직접 임베딩 검색 + 긴 가이드 워크플로우 구성

    요약문을 직접 임베딩하여 검색 후 기존 문장형 가이드를 생성합니다.

    워크플로우 구조:
        [START]
           ↓
        [direct_searcher] - 요약문 직접 임베딩 검색
           ↓
        [response_generator] - 기존 문장형 가이드 생성
           ↓
        [END]
    """
    logger.info("직접 임베딩 + 긴 가이드 워크플로우 구성 중...")

    workflow = StateGraph(AgentState)

    workflow.add_node("direct_searcher", direct_embedding_search_node)
    workflow.add_node("response_generator", response_generator_node)

    workflow.add_edge(START, "direct_searcher")
    workflow.add_edge("direct_searcher", "response_generator")
    workflow.add_edge("response_generator", END)

    logger.info("직접 임베딩 + 긴 가이드 워크플로우 구성 완료")
    return workflow


@lru_cache(maxsize=1)
def get_direct_full_guide_app():
    """직접 임베딩 + 긴 가이드 Agent 애플리케이션 반환 (싱글톤)"""
    logger.info("직접 임베딩 + 긴 가이드 Agent 컴파일 중...")
    workflow = build_direct_full_guide_workflow()
    app = workflow.compile()
    logger.info("직접 임베딩 + 긴 가이드 Agent 컴파일 완료")
    return app


def run_direct_full_guide(summary: str) -> Dict[str, Any]:
    """
    직접 임베딩 검색 + 긴 가이드 생성 실행

    요약문을 직접 임베딩하여 검색 후 기존 문장형 가이드를 생성합니다.

    Args:
        summary: 상담 내용 요약 텍스트

    Returns:
        Dict: 워크플로우 실행 결과
            - documents: 검색된 문서 리스트
            - response_guide: 기존 문장형 대응방안
    """
    logger.info(f"직접 임베딩 + 긴 가이드 실행: '{summary[:50]}...'")

    app = get_direct_full_guide_app()
    initial_state = create_initial_state(summary)

    try:
        result = app.invoke(initial_state)
        logger.info("직접 임베딩 + 긴 가이드 실행 완료")
        return result
    except Exception as e:
        logger.error(f"직접 임베딩 + 긴 가이드 실행 실패: {e}")
        raise


async def run_direct_full_guide_async(summary: str) -> Dict[str, Any]:
    """직접 임베딩 + 긴 가이드 비동기 실행"""
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_direct_full_guide, summary)
    return result
