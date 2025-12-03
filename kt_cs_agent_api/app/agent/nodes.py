"""
===========================================
LangGraph 에이전트 노드 정의
===========================================

이 모듈은 상담 Agent의 핵심 노드(Node)들을 정의합니다.
각 노드는 파이프라인의 한 단계를 담당합니다:

1. analyzer_node: 상담 내용 분석 및 키워드 추출
2. search_node: 벡터 DB 하이브리드 검색
3. response_generator_node: 신입 상담원용 대응방안 생성

수정 가이드:
    - 프롬프트 수정: 각 노드 내 ChatPromptTemplate 수정
    - 모델 변경: settings에서 모델명 변경
    - 검색 로직 변경: search_node의 검색 전략 수정

사용 예시:
    from app.agent.nodes import analyzer_node, search_node, response_generator_node
"""

import logging
import time
from typing import List

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.agent.state import AgentState
from app.config import settings
from app.database import get_vector_db_manager, get_doc_registry

# 로거 설정
logger = logging.getLogger(__name__)


def analyzer_node(state: AgentState) -> dict:
    """
    [Node 1] 상담 내용 분석 및 키워드 추출
    
    상담 요약 내용을 분석하여 핵심 키워드를 추출합니다.
    
    입력 (state):
        - summary: 상담 내용 요약 텍스트
    
    출력 (dict):
        - target_doc_name: 선택된 대상 문서 (현재는 "없음" 고정)
        - search_query: 추출된 검색 키워드
    
    사용 모델:
        - settings.ANALYZER_MODEL (기본: gpt-5-nano)
    
    Note:
        현재 버전에서는 문서 라우팅 기능이 비활성화되어 있습니다.
        target_doc_name은 항상 "없음"을 반환합니다.
        문서 라우팅이 필요하면 주석 처리된 코드를 참고하세요.
    """
    summary = state["summary"]
    logger.info(f"[Analyzer] 상담 내용 분석 시작: '{summary[:50]}...'")
    
    start_time = time.perf_counter()
    
    # LLM 모델 초기화
    # gpt-5-nano: 빠른 응답, 저비용, 키워드 추출에 적합
    llm = ChatOpenAI(
        model=settings.ANALYZER_MODEL,
        api_key=settings.OPENAI_API_KEY,

        temperature=0,
        max_completion_tokens=150,
        reasoning_effort="minimal",  # gpt-5 계열 전용 옵션
        streaming=False
    )
    
    # -----------------------------------------
    # [현재 사용] 키워드 추출 전용 프롬프트
    # -----------------------------------------
    prompt = ChatPromptTemplate.from_template("""
    아래 텍스트에서 핵심 키워드 3-8개를 추출하세요.

    출력 형식: 키워드1 키워드2 키워드3

    {summary}
    """)
    
    # -----------------------------------------
    # [비활성화] 문서 라우팅 + 키워드 추출 프롬프트
    # 문서 라우팅이 필요하면 아래 코드 활성화
    # -----------------------------------------
    # doc_registry = get_doc_registry()
    # doc_list_str = doc_registry.get_document_list_string()
    # 
    # prompt = ChatPromptTemplate.from_template("""
    # 당신은 상담 내용을 분석하여 검색 전략을 수립하는 관리자입니다.
    # 
    # [보유 문서 목록]
    # {doc_list}
    # 
    # [상담 요약]
    # {summary}
    # 
    # 위 내용을 바탕으로 가장 연관된 '문서 이름(목록 중 택1)'과 '검색 키워드'를 결정하세요.
    # 문서를 특정하기 어려우면 문서 이름에 '없음'이라고 적으세요.
    # 
    # 출력 형식: 문서이름 | 검색키워드
    # 예시: 인터넷이용약관 | 해지 위약금 산정식
    # """)
    # 
    # chain = prompt.partial(doc_list=doc_list_str) | llm | StrOutputParser()
    
    # 체인 실행
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke({"summary": summary})
    
    # 결과 파싱
    try:
        # 현재는 키워드만 추출 (문서 라우팅 비활성화)
        target_name = "없음"
        query = response.strip()
    except Exception as e:
        logger.warning(f"[Analyzer] 파싱 실패, 원본 응답 사용: {e}")
        target_name = "없음"
        query = response
    
    # 소요 시간 측정
    duration = time.perf_counter() - start_time
    logger.info(f"[Analyzer] 완료 - 문서: [{target_name}], 키워드: [{query}], 소요시간: {duration:.3f}초")
    
    return {
        "target_doc_name": target_name,
        "search_query": query
    }


def search_node(state: AgentState) -> dict:
    """
    [Node 2] 하이브리드 검색 수행
    
    추출된 키워드로 벡터 DB에서 관련 문서를 검색합니다.
    두 가지 검색 전략을 조합합니다:
    
    1. Scoped Search: 특정 문서 내에서 집중 검색 (k=2)
    2. Global Search: 전체 문서에서 보완 검색 (k=3)
    
    입력 (state):
        - target_doc_name: 대상 문서 이름 (또는 "없음")
        - search_query: 검색 키워드
    
    출력 (dict):
        - documents: 검색된 Document 리스트 (중복 제거됨)
    
    Note:
        검색 결과는 content 앞 50자 기준으로 중복 제거됩니다.
    """
    target_name = state["target_doc_name"]
    query = state["search_query"]
    
    logger.info(f"[Searcher] 검색 시작 - 문서: [{target_name}], 키워드: [{query}]")
    start_time = time.perf_counter()
    
    # DB 매니저 및 문서 레지스트리 가져오기
    db_manager = get_vector_db_manager()
    doc_registry = get_doc_registry()
    
    docs = []
    
    # -----------------------------------------
    # 전략 1: Scoped Search (타겟 문서 집중 검색)
    # -----------------------------------------
    if target_name != "없음" and doc_registry.has_document(target_name):
        real_path = doc_registry.get_document_path(target_name)
        logger.info(f"[Searcher] Scoped 검색: '{target_name}' (k=2)")
        
        try:
            scoped_results = db_manager.similarity_search(
                query,
                k=2,
                filter_dict={"source": real_path}
            )
            docs.extend(scoped_results)
            logger.debug(f"[Searcher] Scoped 검색 결과: {len(scoped_results)}개")
        except Exception as e:
            logger.warning(f"[Searcher] Scoped 검색 오류: {e}")
    else:
        logger.info("[Searcher] Scoped 검색 스킵 (대상 문서 없음)")
    
    # -----------------------------------------
    # 전략 2: Global Search (전체 범위 검색)
    # -----------------------------------------
    logger.info("[Searcher] Global 검색 수행 (k=3)")
    try:
        global_results = db_manager.similarity_search(query, k=3)
        docs.extend(global_results)
        logger.debug(f"[Searcher] Global 검색 결과: {len(global_results)}개")
    except Exception as e:
        logger.error(f"[Searcher] Global 검색 오류: {e}")
    
    # -----------------------------------------
    # 중복 제거 (내용 앞 50자 기준)
    # -----------------------------------------
    unique_docs = []
    seen_content = set()
    
    for doc in docs:
        # 앞 50자를 해시 키로 사용
        content_hash = doc.page_content[:50]
        if content_hash not in seen_content:
            unique_docs.append(doc)
            seen_content.add(content_hash)
    
    # 소요 시간 측정
    duration = time.perf_counter() - start_time
    logger.info(f"[Searcher] 완료 - {len(unique_docs)}개 문서 (중복 제거), 소요시간: {duration:.3f}초")
    
    return {"documents": unique_docs}


def response_generator_node(state: AgentState) -> dict:
    """
    [Node 3] 신입 상담원용 대응방안 생성
    
    검색된 문서를 바탕으로 신입 상담원이 고객에게
    안내할 수 있는 대응방안을 생성합니다.
    
    입력 (state):
        - summary: 원본 상담 요약
        - documents: 검색된 문서 리스트
    
    출력 (dict):
        - response_guide: 생성된 대응방안 텍스트
    
    사용 모델:
        - settings.RESPONSE_MODEL (기본: gpt-4o-mini)
    
    Note:
        gpt-4o-mini는 gpt-5-nano보다 품질이 좋으면서도
        비용 효율적인 모델입니다.
    """
    summary = state["summary"]
    documents = state["documents"]
    
    logger.info(f"[ResponseGen] 대응방안 생성 시작 - 참조 문서: {len(documents)}개")
    start_time = time.perf_counter()
    
    # -----------------------------------------
    # 컨텍스트 구성 (검색된 문서 내용 통합)
    # -----------------------------------------
    context_parts = []
    for i, doc in enumerate(documents):
        source_name = doc.metadata.get("source", "Unknown").split("/")[-1]
        page = doc.metadata.get("page", 0) + 1
        context_parts.append(
            f"[참고문서 {i+1}] {source_name} (p.{page})\n{doc.page_content}"
        )
    
    context = "\n\n".join(context_parts) if context_parts else "참고할 문서가 없습니다."
    
    # -----------------------------------------
    # LLM 모델 초기화
    # -----------------------------------------
    llm = ChatOpenAI(
        model=settings.RESPONSE_MODEL,
        api_key=settings.OPENAI_API_KEY,

        temperature=0.2,  # 약간의 창의성 허용
        max_tokens=800,  # 충분한 길이의 답변 생성 허용
        streaming=False
    
    )
    
    # -----------------------------------------
    # 대응방안 생성 프롬프트
    # -----------------------------------------
    # [간결 버전] 현재 사용 중
    prompt = ChatPromptTemplate.from_template("""
    신입 상담원 대응 가이드를 작성하세요.

    고객 문의: {summary}
    참고 자료: {context}

    포함: 안내 멘트, 주의사항, 확인 필요 사항
    """)
    
    # -----------------------------------------
    # [상세 버전] 필요시 활성화
    # -----------------------------------------
    # prompt = ChatPromptTemplate.from_template("""
    # 당신은 KT 고객센터의 시니어 상담원입니다.
    # 신입 상담원이 고객 문의에 적절히 대응할 수 있도록 
    # 친절하고 명확한 가이드를 제공해주세요.
    # 
    # === 고객 상담 요약 ===
    # {summary}
    # 
    # === 관련 내부 규정/약관 ===
    # {context}
    # 
    # === 작성 지침 ===
    # 1. 신입 상담원도 쉽게 이해할 수 있는 언어로 작성
    # 2. 고객에게 직접 안내할 수 있는 멘트 예시 포함
    # 3. 주의사항이나 예외 케이스가 있다면 명시
    # 4. 필요시 추가 확인이 필요한 사항 안내
    # 
    # === 대응방안 작성 ===
    # """)
    
    # 체인 실행
    chain = prompt | llm | StrOutputParser()
    response_guide = chain.invoke({
        "summary": summary,
        "context": context
    })
    
    # 소요 시간 측정
    duration = time.perf_counter() - start_time
    logger.info(f"[ResponseGen] 완료 - 응답 길이: {len(response_guide)}자, 소요시간: {duration:.3f}초")
    
    return {"response_guide": response_guide}
