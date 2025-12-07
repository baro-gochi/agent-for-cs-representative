"""
===========================================
LangGraph 에이전트 상태(State) 정의
===========================================

이 모듈은 LangGraph 워크플로우에서 사용되는 상태 스키마를 정의합니다.
상태는 노드 간에 전달되는 데이터 구조입니다.

수정 가이드:
    - 새로운 중간 데이터가 필요하면 AgentState에 필드 추가
    - TypedDict를 사용하여 타입 힌트 제공

사용 예시:
    from app.agent.state import AgentState
"""

from typing import List, TypedDict
from langchain_core.documents import Document


class AgentState(TypedDict):
    """
    상담원 Agent의 상태 스키마

    LangGraph 워크플로우에서 노드 간 전달되는 데이터를 정의합니다.

    Attributes:
        summary (str):
            [입력] 상담 내용 요약
            사용자로부터 입력받은 원본 상담 요약 텍스트

        target_doc_name (str):
            [중간] 선택된 문서 별칭
            analyzer_node에서 결정된 검색 대상 문서
            문서를 특정할 수 없으면 "없음"

        search_query (str):
            [중간] 추출된 검색 키워드
            analyzer_node에서 추출된 핵심 키워드

        documents (List[Document]):
            [중간] 검색된 문서 리스트
            search_node 또는 direct_embedding_search_node에서 검색된 관련 문서들

        response_guide (str):
            [출력] 신입 상담원용 대응방안
            response_generator_node에서 생성된 최종 가이드 텍스트 (문장 형태)

        keyword_guide (str):
            [출력] 핵심 키워드 기반 간결 가이드
            keyword_guide_node에서 생성된 핵심 요점 텍스트
            예: "• [요금제] 5G 스탠다드 월 69,000원. 데이터 무제한."

    워크플로우 옵션:

    [기존] 키워드 추출 → 검색 → 문장 가이드
        summary (입력)
            ↓
        [analyzer_node]
            ↓
        target_doc_name, search_query (중간)
            ↓
        [search_node]
            ↓
        documents (중간)
            ↓
        [response_generator_node]
            ↓
        response_guide (출력)

    [대안] 직접 임베딩 검색 → 핵심 가이드
        summary (입력)
            ↓
        [direct_embedding_search_node]
            ↓
        documents (중간)
            ↓
        [keyword_guide_node]
            ↓
        keyword_guide (출력)
    """
    
    # [입력] 상담 내용 요약
    summary: str
    
    # [중간] 선택된 문서 별칭 (또는 "없음")
    target_doc_name: str
    
    # [중간] 추출된 검색 키워드
    search_query: str
    
    # [중간] 검색된 문서 리스트
    documents: List[Document]
    
    # [출력] 신입 상담원용 대응방안
    response_guide: str

    # [출력] 핵심 키워드 기반 간결 가이드 (keyword_guide_node용)
    keyword_guide: str


# ==========================================
# 상태 초기화 헬퍼 함수
# ==========================================

def create_initial_state(summary: str) -> dict:
    """
    초기 상태 생성
    
    워크플로우 실행에 필요한 초기 상태를 생성합니다.
    
    Args:
        summary: 상담 내용 요약 텍스트
    
    Returns:
        dict: 초기 상태 딕셔너리
    
    사용 예시:
        state = create_initial_state("인터넷 해지 문의")
        result = app.invoke(state)
    """
    return {
        "summary": summary,
        "target_doc_name": "",
        "search_query": "",
        "documents": [],
        "response_guide": "",
        "keyword_guide": ""
    }
