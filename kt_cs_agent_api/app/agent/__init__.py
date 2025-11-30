"""
에이전트 패키지 - LangGraph 기반 상담 Agent

이 패키지는 상담원 지원 Agent의 핵심 로직을 포함합니다.

주요 컴포넌트:
    - AgentState: 워크플로우 상태 스키마
    - analyzer_node: 상담 분석 및 키워드 추출
    - search_node: 벡터 DB 검색
    - response_generator_node: 대응방안 생성
    - run_consultation: Agent 실행 함수

사용 예시:
    from app.agent import run_consultation
    
    result = run_consultation("인터넷 해지 문의")
    print(result["response_guide"])
"""

from app.agent.state import AgentState, create_initial_state
from app.agent.nodes import (
    analyzer_node,
    search_node,
    response_generator_node
)
from app.agent.workflow import (
    get_agent_app,
    run_consultation,
    run_consultation_async,
    reset_agent_app,
    # 전문가용
    get_expert_app,
    run_expert_search,
    run_expert_search_async
)

__all__ = [
    # 상태
    "AgentState",
    "create_initial_state",
    # 노드
    "analyzer_node",
    "search_node",
    "response_generator_node",
    # 신입 상담원용 워크플로우
    "get_agent_app",
    "run_consultation",
    "run_consultation_async",
    "reset_agent_app",
    # 전문가용 워크플로우
    "get_expert_app",
    "run_expert_search",
    "run_expert_search_async"
]