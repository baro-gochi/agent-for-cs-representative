"""
===========================================
LangGraph 에이전트 노드 정의
===========================================

이 모듈은 상담 Agent의 핵심 노드(Node)들을 정의합니다.
각 노드는 파이프라인의 한 단계를 담당합니다:

[기존 노드]
1. analyzer_node: 상담 내용 분석 및 키워드 추출
2. search_node: 벡터 DB 하이브리드 검색
3. response_generator_node: 신입 상담원용 대응방안 생성 (문장 형태)

[추가 노드]
4. direct_embedding_search_node: 요약문 직접 임베딩으로 유사 문서 검색
   - 키워드 추출 과정 없이 요약문 자체를 임베딩하여 검색
   - analyzer_node + search_node 대체 가능

5. keyword_guide_node: 핵심 키워드 기반 간결 가이드 생성
   - 긴 문장 대신 핵심만 짧게 나열
   - 상담원이 자신의 말로 정제 가능하도록 요점 제공

수정 가이드:
    - 프롬프트 수정: 각 노드 내 ChatPromptTemplate 수정
    - 모델 변경: settings에서 모델명 변경
    - 검색 로직 변경: search_node의 검색 전략 수정

사용 예시:
    from app.agent.nodes import analyzer_node, search_node, response_generator_node
    from app.agent.nodes import direct_embedding_search_node, keyword_guide_node
"""

import json
import logging
import time
from typing import List

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser

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
        max_completion_tokens=50,
        reasoning_effort="minimal",  # gpt-5 계열 전용 옵션
        streaming=False
    )
    
    # -----------------------------------------
    # [현재 사용] 키워드 추출 전용 프롬프트
    # -----------------------------------------
    # prompt = ChatPromptTemplate.from_template("""
    # 아래 텍스트에서 핵심 키워드 3-8개를 추출하세요.

    # 출력 형식: 키워드1 키워드2 키워드3

    # {summary}
    # """)
    prompt = ChatPromptTemplate.from_template("""
    아래 텍스트에서 상담/약관 검색에 필요한 핵심 키워드를 3~8개 추출하세요.

    규칙:
    - 약관/계약/요금·서비스 문맥에서 중요한 단어만 선택하세요.
    - 숫자 정보(개월 수, 약정 기간 등)는 반드시 포함하세요.
    - “해지/위약금/반환금” 계열 키워드 우선 가중치
    - 특정 상품명이나 결합상품은 텍스트에 명시되거나 의미상 필요한 경우에만 포함하세요.
    - 일반 단어(내용, 상세, 문의, 방식, 설명 등)는 제거하세요.
    - 출력은 공백으로 구분된 단어만 나열하세요.
    - 출력 형식: 키워드1 키워드2 키워드3 ...

    텍스트:
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
        # model=settings.RESPONSE_MODEL,
        # api_key=settings.OPENAI_API_KEY,

        # temperature=0.2,  # 약간의 창의성 허용
        # max_tokens=800,  # 충분한 길이의 답변 생성 허용
        # streaming=False
        model=settings.ANALYZER_MODEL,
        api_key=settings.OPENAI_API_KEY,

        temperature=0,
        # max_completion_tokens=150,
        reasoning_effort="minimal",  # gpt-5 계열 전용 옵션
        streaming=False
    
    )
    
    # -----------------------------------------
    # 대응방안 생성 프롬프트 (JSON 출력)
    # -----------------------------------------
    # 프론트엔드에서 자유롭게 렌더링할 수 있도록 JSON 구조로 출력
    prompt = ChatPromptTemplate.from_template("""
신입 상담원 대응 가이드를 JSON 형식으로 작성하세요.

고객 문의 요약: {summary}
관련 문서 내용: {context}

요구 조건:
- 문맥 기반으로 필요한 범위까지만 간결하게 확장하세요.
- 고객 문의와 실제 문서 내용이 직접적으로 일치하지 않는 경우, "직접적 규정 없음"이라고 명시하고, 문서가 어떤 범위에서만 참고 가능한지 기술하세요.
- 각 문서의 해당 조항에서 핵심 문구를 1~2줄로 요약해 제시하세요.
- 문서에 없는 내용은 임의로 생성하지 마세요.
- 서로 다른 문서에서 추출된 규정은 섞지 말고 문서별로 구분해 설명하세요.
- 문장 톤은 상담원이 고객에게 설명하듯 부드럽고 명확하게 작성하세요.
- 각 섹션의 items 배열에는 2~5개의 항목을 포함하세요.

반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트는 포함하지 마세요:
{{
    "announcement": {{
        "title": "안내 멘트",
        "items": ["고객에게 안내할 첫 번째 멘트", "두 번째 멘트", ...]
    }},
    "cautions": {{
        "title": "주의사항",
        "items": ["첫 번째 주의사항", "두 번째 주의사항", ...]
    }},
    "check_required": {{
        "title": "확인 필요 사항",
        "items": ["확인할 첫 번째 사항", "두 번째 사항", ...]
    }},
    "next_steps": {{
        "title": "다음 단계 안내",
        "items": ["다음 단계 첫 번째", "두 번째", ...]
    }}
}}
""")
    
    # 체인 실행 (JSON 파싱)
    chain = prompt | llm | StrOutputParser()
    raw_response = chain.invoke({
        "summary": summary,
        "context": context
    })

    # JSON 파싱 시도
    try:
        # JSON 블록 추출 (```json ... ``` 형태 처리)
        json_str = raw_response.strip()
        if json_str.startswith("```"):
            # 코드 블록 제거
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        response_guide = json.loads(json_str)
        logger.debug(f"[ResponseGen] JSON 파싱 성공")
    except json.JSONDecodeError as e:
        # 파싱 실패 시 기본 구조로 폴백
        logger.warning(f"[ResponseGen] JSON 파싱 실패, 폴백 구조 사용: {e}")
        response_guide = {
            "announcement": {
                "title": "안내 멘트",
                "items": [raw_response[:500] if len(raw_response) > 500 else raw_response]
            },
            "cautions": {
                "title": "주의사항",
                "items": ["파싱 오류로 인해 원본 응답을 안내 멘트에 포함했습니다."]
            },
            "check_required": {
                "title": "확인 필요 사항",
                "items": ["담당자 확인 필요"]
            },
            "next_steps": {
                "title": "다음 단계 안내",
                "items": ["상위 담당자에게 문의"]
            }
        }

    # 소요 시간 측정
    duration = time.perf_counter() - start_time
    logger.info(f"[ResponseGen] 완료 - 소요시간: {duration:.3f}초")

    return {"response_guide": response_guide}


def direct_embedding_search_node(state: AgentState) -> dict:
    """
    [Node] 요약문 직접 임베딩 검색

    기존 analyzer_node처럼 키워드를 추출하지 않고,
    상담 요약문 자체를 임베딩하여 벡터 DB에서 유사 문서를 검색합니다.

    입력 (state):
        - summary: 상담 내용 요약 텍스트

    출력 (dict):
        - documents: 검색된 Document 리스트

    장점:
        - 키워드 추출 과정 생략으로 속도 향상
        - 문맥 전체를 반영한 검색 가능
        - LLM API 호출 비용 절감

    Note:
        similarity_search 내부에서 임베딩 모델을 통해
        요약문을 벡터로 변환하여 유사도 검색을 수행합니다.
    """
    summary = state["summary"]

    logger.info(f"[DirectSearch] 직접 임베딩 검색 시작: '{summary[:50]}...'")
    start_time = time.perf_counter()

    # DB 매니저 가져오기
    db_manager = get_vector_db_manager()

    # -----------------------------------------
    # 요약문 직접 임베딩하여 유사도 검색 수행
    # -----------------------------------------
    try:
        # summary 자체를 쿼리로 사용 (내부적으로 임베딩 처리됨)
        docs = db_manager.similarity_search(summary, k=5)
        logger.debug(f"[DirectSearch] 검색 결과: {len(docs)}개 문서")
    except Exception as e:
        logger.error(f"[DirectSearch] 검색 오류: {e}")
        docs = []

    # -----------------------------------------
    # 중복 제거 (내용 앞 50자 기준)
    # -----------------------------------------
    unique_docs = []
    seen_content = set()

    for doc in docs:
        content_hash = doc.page_content[:50]
        if content_hash not in seen_content:
            unique_docs.append(doc)
            seen_content.add(content_hash)

    # 소요 시간 측정
    duration = time.perf_counter() - start_time
    logger.info(f"[DirectSearch] 완료 - {len(unique_docs)}개 문서, 소요시간: {duration:.3f}초")

    return {"documents": unique_docs}


def keyword_guide_node(state: AgentState) -> dict:
    """
    [Node] 핵심 키워드 기반 간결 가이드 생성

    벡터DB 검색 결과와 질문을 OpenAI API에 보내
    상담원에게 필요한 핵심만 짧게 제시합니다.

    기존 response_generator_node가 긴 문장 형태의 가이드를 생성했다면,
    이 노드는 핵심 요점만 한 줄씩 제시하여 상담원이 자신의 말로
    정제할 수 있도록 합니다.

    입력 (state):
        - summary: 원본 상담 요약
        - documents: 검색된 문서 리스트

    출력 (dict):
        - keyword_guide: JSON 구조화된 핵심 키워드/요점 데이터

    출력 예시 (JSON):
        {
            "guide_items": [
                {"topic": "요금제", "points": ["5G 스탠다드 월 69,000원", "데이터 무제한"]},
                {"topic": "위약금", "points": ["24개월 약정", "잔여개월 x 할인액"]}
            ]
        }

    사용 모델:
        - settings.ANALYZER_MODEL (빠른 응답)
    """
    summary = state["summary"]
    documents = state["documents"]

    logger.info(f"[KeywordGuide] 핵심 가이드 생성 시작 - 참조 문서: {len(documents)}개")
    start_time = time.perf_counter()

    # -----------------------------------------
    # 컨텍스트 구성 (검색된 문서 내용 통합)
    # -----------------------------------------
    context_parts = []
    for i, doc in enumerate(documents):
        source_name = doc.metadata.get("source", "Unknown").split("/")[-1]
        page = doc.metadata.get("page", 0) + 1
        context_parts.append(
            f"[문서 {i+1}] {source_name} (p.{page})\n{doc.page_content}"
        )

    context = "\n\n".join(context_parts) if context_parts else "참고 문서 없음"

    # -----------------------------------------
    # LLM 모델 초기화
    # -----------------------------------------
    llm = ChatOpenAI(
        model=settings.ANALYZER_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        # max_completion_tokens=300,
        reasoning_effort="minimal",
        streaming=False
    )

    # -----------------------------------------
    # 핵심 키워드 가이드 프롬프트 (JSON 출력)
    # -----------------------------------------
#     prompt = ChatPromptTemplate.from_template("""
# 상담원에게 필요한 사실 기반 핵심 정보만 JSON으로 정리하세요.

# 고객 문의: {summary}
# 참고 문서: {context}

# 핵심 규칙:
# 1) topic은 '문서 안에 실제 정량 데이터(금액·수치·산정식·조건)가 존재하는 경우에만' 생성한다.
#    - 지시문/절차/설명만 있는 경우 topic 생성 금지
#    - 예: "위약금 설명 필요" → 금액/산정식 없음 → topic 생성 금지

# 2) points는 반드시 문서에 있는 정량적이고 사실 기반 정보만 포함한다.
#    - 금액, 수식, 조건, 여부, 항목 등
#    - 지시/행동 표현 금지 (예: "~안내", "~설명", "~제시")

# 3) 문서에 정량 데이터가 전혀 없으면 guide_items를 아예 생성하지 않거나,
#    정량 정보가 있는 topic만 남긴다.

# 4) JSON 외 텍스트는 출력 금지.

# 출력 형식:
# {{
#     "guide_items": [
#         {{
#             "topic": "주제1",
#             "points": ["정량 사실1", "정량 사실2"]
#         }}
#     ]
# }}

#     """)
    prompt = ChatPromptTemplate.from_template("""
상담원에게 필요한 핵심만 JSON 형식으로 제시하세요.

고객 문의: {summary}
참고 문서: {context}

규칙:
- 긴 문장 금지. 핵심 키워드/요점만 나열
- 대화 순서에 맞게 정보 배치
- 상담원이 자신의 말로 정제할 수 있도록 필요 데이터 제공
- 각 points 항목은 짧은 문구로 작성 (10단어 이내)
- 문서에 없는 내용은 작성 금지
- 2~6개의 주제를 생성

반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트는 포함하지 마세요:
{{
    "guide_items": [
        {{
            "topic": "주제1",
            "points": ["핵심내용1", "핵심내용2", "핵심내용3"]
        }},
        {{
            "topic": "주제2",
            "points": ["핵심내용1", "핵심내용2"]
        }}
    ]
}}

예시 출력:
{{
    "guide_items": [
        {{"topic": "요금제", "points": ["5G 스탠다드 월 69,000원", "데이터 무제한", "통화 무제한"]}},
        {{"topic": "위약금", "points": ["24개월 약정", "잔여개월 x 할인액", "최대 300,000원"]}},
        {{"topic": "확인사항", "points": ["가입일 확인 필요", "결합상품 여부 체크"]}}
    ]
}}
""")

    # 체인 실행 (JSON 파싱)
    chain = prompt | llm | StrOutputParser()
    raw_response = chain.invoke({
        "summary": summary,
        "context": context
    })

    # JSON 파싱 시도
    try:
        # JSON 블록 추출 (```json ... ``` 형태 처리)
        json_str = raw_response.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        keyword_guide = json.loads(json_str)
        logger.debug(f"[KeywordGuide] JSON 파싱 성공")
    except json.JSONDecodeError as e:
        # 파싱 실패 시 기본 구조로 폴백
        logger.warning(f"[KeywordGuide] JSON 파싱 실패, 폴백 구조 사용: {e}")
        keyword_guide = {
            "guide_items": [
                {
                    "topic": "응답 내용",
                    "points": [raw_response[:200] if len(raw_response) > 200 else raw_response]
                }
            ]
        }

    # 소요 시간 측정
    duration = time.perf_counter() - start_time
    logger.info(f"[KeywordGuide] 완료 - 소요시간: {duration:.3f}초")

    return {"keyword_guide": keyword_guide}
