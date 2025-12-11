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
    카테고리 자동 판별로 관련 문서만 검색합니다.
    두 가지 검색 전략을 조합합니다:

    1. Scoped Search: 특정 문서 내에서 집중 검색 (k=2)
    2. Global Search: 카테고리 필터 적용 전체 검색 (k=3)

    입력 (state):
        - target_doc_name: 대상 문서 이름 (또는 "없음")
        - search_query: 검색 키워드

    출력 (dict):
        - documents: 검색된 Document 리스트 (중복 제거됨)

    카테고리:
        - tv: TV 요금제
        - bundle: 결합 요금제
        - mobile_internet: 인터넷, 모바일 요금제
        - membership: 멤버십 혜택
    """
    target_name = state["target_doc_name"]
    query = state["search_query"]

    logger.info(f"[Searcher] 검색 시작 - 문서: [{target_name}], 키워드: [{query}]")
    start_time = time.perf_counter()

    # DB 매니저 및 문서 레지스트리 가져오기
    db_manager = get_vector_db_manager()
    doc_registry = get_doc_registry()

    # 카테고리 판별
    categories = detect_category_from_query(query)

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
    # 전략 2: Global Search (카테고리 필터 적용)
    # -----------------------------------------
    logger.info(f"[Searcher] Global 검색 수행 (k=3, 카테고리: {categories or '전체'})")
    try:
        global_results = db_manager.similarity_search_by_categories(query, categories, k=3)
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
    카테고리 자동 판별로 관련 문서만 검색합니다.

    입력 (state):
        - summary: 상담 내용 요약 텍스트

    출력 (dict):
        - documents: 검색된 Document 리스트
        - detected_categories: 감지된 카테고리 리스트

    카테고리:
        - tv: TV 요금제
        - bundle: 결합 요금제
        - mobile_internet: 인터넷, 모바일 요금제
        - membership: 멤버십 혜택
    """
    summary = state["summary"]

    logger.info(f"[DirectSearch] 직접 임베딩 검색 시작: '{summary[:50]}...'")
    start_time = time.perf_counter()

    # DB 매니저 가져오기
    db_manager = get_vector_db_manager()

    # -----------------------------------------
    # 카테고리 판별
    # -----------------------------------------
    categories = detect_category_from_query(summary)

    # -----------------------------------------
    # 카테고리 필터 적용하여 유사도 검색 수행
    # -----------------------------------------
    try:
        docs = db_manager.similarity_search_by_categories(summary, categories, k=5)
        logger.debug(f"[DirectSearch] 검색 결과: {len(docs)}개 문서 (카테고리: {categories or '전체'})")
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
        # model=settings.ANSWER_MODEL,
        model=settings.RESPONSE_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        # max_completion_tokens=300,
        # reasoning_effort="minimal",
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

반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트는 포함하지 마세요:
{{
    "guide_items": [
        {{
            "topic": "분류1",
            "points": ["핵심내용1", "핵심내용2", "핵심내용3"]
        }},
        {{
            "topic": "분류2",
            "points": ["핵심내용1", "핵심내용2"]
        }}
    ]
}}

- 문서에 사실이 충분하지 않다면 빈 배열을 반환하세요.
- topic 또는 points를 임의로 생성하거나 추론하지 마세요.
- 상담 가이드는 생성하지 마세요. 문서에 있는 사실만 요약하세요.
- 문서에 사실이 거의 없을 경우 아래 형태로만 출력하세요:
{{
  "guide_items": []
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


# ==========================================
# 카테고리 판별 관련 상수 및 함수
# ==========================================

# 카테고리별 키워드 매핑 (5개 카테고리)
CATEGORY_KEYWORDS = {
    "mobile": [
        "모바일", "휴대폰", "스마트폰", "5G", "LTE", "3G",
        "통화", "문자", "로밍", "해외", "번호이동", "기기변경", "유심",
        "데이터", "무제한"
    ],
    "internet": [
        "인터넷", "광랜", "기가", "와이파이", "wifi", "공유기",
        "속도", "회선", "광케이블", "유선"
    ],
    "tv": [
        "tv", "티비", "IPTV", "올레tv", "셋톱박스", "채널", "VOD",
        "지니tv", "skylife", "스카이라이프", "방송", "시청"
    ],
    "bundle": [
        "결합", "뭉치면", "가족결합", "인터넷결합", "묶음", "패밀리",
        "올레가", "프리미엄가족", "결합할인", "동시가입"
    ],
    "membership": [
        "멤버십", "포인트", "VIP", "혜택", "적립", "쿠폰",
        "제휴", "할인쿠폰", "등급", "리워드"
    ]
}

# 공통 키워드 (여러 카테고리에 적용)
COMMON_KEYWORDS = {
    "요금제": ["mobile", "internet", "tv"],  # 요금제는 모바일/인터넷/TV 모두 해당
    "월정액": ["mobile", "internet", "tv"],
    "약정": ["mobile", "internet", "tv", "bundle"],
    "위약금": ["mobile", "internet", "tv", "bundle"],
    "해지": ["mobile", "internet", "tv", "bundle"],
}


def detect_category_from_query(query: str) -> list:
    """
    질문에서 관련 카테고리를 판별합니다.

    Args:
        query: 사용자 질문

    Returns:
        list: 관련 카테고리 리스트 (예: ["tv", "bundle"])
              빈 리스트면 전체 검색

    카테고리:
        - mobile: 모바일 요금제
        - internet: 인터넷 요금제
        - tv: TV 요금제
        - bundle: 결합 요금제
        - membership: 멤버십 혜택
    """
    query_lower = query.lower()
    detected = set()

    # 1. 공통 키워드 체크 (여러 카테고리에 적용)
    for keyword, categories in COMMON_KEYWORDS.items():
        if keyword.lower() in query_lower:
            detected.update(categories)

    # 2. 카테고리별 전용 키워드 체크
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in query_lower:
                detected.add(category)
                break

    detected = list(detected)

    if detected:
        logger.info(f"[CategoryDetect] 질문: '{query[:30]}...' → 카테고리: {detected}")
    else:
        logger.info(f"[CategoryDetect] 질문: '{query[:30]}...' → 전체 검색")

    return detected


async def detect_category_with_llm(query: str) -> list:
    """
    LLM을 사용하여 질문의 카테고리를 판별합니다.

    Args:
        query: 사용자 질문

    Returns:
        list: 관련 카테고리 리스트
    """
    import asyncio

    llm = ChatOpenAI(
        model=settings.ANSWER_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        max_tokens=20,
        reasoning_effort="minimal",
    )

    prompt = ChatPromptTemplate.from_template("""카테고리 목록:
- mobile: 모바일/휴대폰 요금제, 5G, LTE, 3G, 데이터, 통화, 문자, 로밍
- internet: 인터넷 요금제, 광랜, 기가인터넷, 와이파이, 회선 속도
- tv: TV 요금제, IPTV, 올레tv, 지니tv, 채널, VOD, 셋톱박스
- bundle: 결합할인, 뭉치면올레, 가족결합, 패밀리, 묶음할인
- membership: 멤버십, 포인트, VIP, 등급, 쿠폰 혜택

질문: {query}

규칙:
1. 질문에서 언급되거나 강하게 연관된 카테고리만 선택한다.
2. 여러 카테고리가 해당되면 쉼표(,)로 구분하여 출력한다.
3. 어떤 카테고리에도 명확히 해당하지 않으면 "all"을 출력한다.
4. 카테고리명만 출력하고 설명은 포함하지 않는다.

출력 형식 예시:
mobile
 혹은
mobile,bundle
 혹은
all

카테고리:""")

    chain = prompt | llm | StrOutputParser()

    try:
        result = await asyncio.to_thread(chain.invoke, {"query": query})
        result = result.strip().lower()

        if result == "all" or not result:
            logger.info(f"[CategoryDetect-LLM] '{query[:30]}...' → 전체 (LLM 응답: '{result}')")
            return []

        categories = [c.strip() for c in result.split(",")]
        valid_categories = [c for c in categories if c in CATEGORY_KEYWORDS]

        if valid_categories:
            logger.info(f"[CategoryDetect-LLM] '{query[:30]}...' → {valid_categories}")
        else:
            logger.info(f"[CategoryDetect-LLM] '{query[:30]}...' → 전체 (유효하지 않은 카테고리: {categories})")

        return valid_categories

    except Exception as e:
        logger.warning(f"[CategoryDetect-LLM] 실패, 키워드 기반 폴백: {e}")
        return detect_category_from_query(query)


def query_expansion_node(state: AgentState) -> dict:
    """
    [Node] 질문 확장 노드

    모호하거나 짧은 질문을 검색에 적합하도록 확장합니다.
    벡터 검색의 품질을 높이기 위해 관련 키워드와 문맥을 추가합니다.

    입력 (state):
        - summary: 원본 상담 요약/질문

    출력 (dict):
        - expanded_query: 확장된 검색 쿼리

    예시:
        입력: "요금제 종류"
        출력: "요금제 종류 5G LTE 월정액 데이터 무제한 요금 가격 혜택 할인"

        입력: "해지"
        출력: "해지 위약금 약정 해지 절차 방법 잔여 개월 할인 반환금"
    """
    summary = state["summary"]
    logger.info(f"[QueryExpansion] 질문 확장 시작: '{summary[:50]}...'")
    start_time = time.perf_counter()

    # LLM 모델 초기화
    llm = ChatOpenAI(
        model=settings.ANSWER_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        # max_completion_tokens=300,
        reasoning_effort="minimal",
        streaming=False
    )

    # 질문 확장 프롬프트
    prompt = ChatPromptTemplate.from_template("""
당신은 통신사 고객센터 검색 시스템의 쿼리 확장 전문가입니다.
사용자 질문을 벡터 검색에 적합하도록, 짧은 자연어 문장으로 확장하세요.

원본 질문: {query}

규칙:
1. 원본 질문의 핵심 의도를 유지하세요.
2. "요금제 이름, 월정액, 데이터 제공량, 통화 제공량, 위약금, 약정 조건, 부가서비스 세부 내용" 등
   실제 문서에 존재할 수 있는 사실 정보 위주로 확장하세요.
3. 상담 멘트, 추천 문구, 안내 문장(예: "~을 안내합니다", "~을 추천드립니다")은 포함하지 마세요.
4. 관련 키워드를 무작정 나열하지 말고, 1~2개의 짧은 문장으로 표현하세요.
5. 통신사 업무 범위 안에서, 검색 대상을 적절히 좁히세요.
   - 예: "요금제 종류" → "모바일 요금제의 플랜 이름과 월 요금, 데이터 제공량을 설명하는 공식 요금제 문서"
6. 40단어 이내의 자연어 문장으로만 출력하세요.
7. 쉼표로 나열된 키워드 리스트 형태로 쓰지 마세요.

확장된 쿼리:""")

    chain = prompt | llm | StrOutputParser()

    try:
        raw_response = chain.invoke({"query": summary})
        expanded_query = raw_response.strip()

        # 빈 응답이거나 너무 짧으면 원본 사용
        if not expanded_query or len(expanded_query) < len(summary):
            logger.warning(f"[QueryExpansion] 확장 결과가 부적절함 ('{raw_response}'), 원본 사용")
            expanded_query = summary
        else:
            logger.info(f"[QueryExpansion] 확장 결과: '{expanded_query}'")
    except Exception as e:
        logger.warning(f"[QueryExpansion] 확장 실패, 원본 사용: {e}")
        expanded_query = summary

    duration = time.perf_counter() - start_time
    logger.info(f"[QueryExpansion] 완료 - 소요시간: {duration:.3f}초")

    return {"expanded_query": expanded_query}


async def expand_query_async(query: str) -> str:
    """
    질문 확장 유틸리티 함수 (비동기)

    API 레이어에서 직접 호출 가능한 독립적인 함수입니다.

    Args:
        query: 원본 질문/요약문

    Returns:
        str: 확장된 쿼리 (실패 시 원본 반환)

    사용 예시:
        expanded = await expand_query_async("요금제 종류")
    """
    import asyncio

    logger.info(f"[QueryExpansion] 비동기 질문 확장 시작: '{query[:50]}...'")
    start_time = time.perf_counter()

    llm = ChatOpenAI(
        model=settings.ANSWER_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        # max_completion_tokens=300,
        reasoning_effort="minimal",
        streaming=False
    )

    prompt = ChatPromptTemplate.from_template("""
당신은 통신사 고객센터 검색 시스템의 쿼리 확장 전문가입니다.
사용자 질문을 벡터 검색에 적합하도록, 짧은 자연어 문장으로 확장하세요.

원본 질문: {query}

규칙:
1. 원본 질문의 핵심 의도를 유지하세요.
2. "요금제 이름, 월정액, 데이터 제공량, 통화 제공량, 위약금, 약정 조건, 부가서비스 세부 내용" 등
   실제 문서에 존재할 수 있는 사실 정보 위주로 확장하세요.
3. 상담 멘트, 추천 문구, 안내 문장(예: "~을 안내합니다", "~을 추천드립니다")은 포함하지 마세요.
4. 관련 키워드를 무작정 나열하지 말고, 1~2개의 짧은 문장으로 표현하세요.
5. 통신사 업무 범위 안에서, 검색 대상을 적절히 좁히세요.
   - 예: "요금제 종류" → "모바일 요금제의 플랜 이름과 월 요금, 데이터 제공량을 설명하는 공식 요금제 문서"
6. 40단어 이내의 자연어 문장으로만 출력하세요.
7. 쉼표로 나열된 키워드 리스트 형태로 쓰지 마세요.

확장된 쿼리:""")

    chain = prompt | llm | StrOutputParser()

    try:
        raw_response = await asyncio.to_thread(
            chain.invoke, {"query": query}
        )
        expanded_query = raw_response.strip()

        # 빈 응답이거나 너무 짧으면 원본 사용
        if not expanded_query or len(expanded_query) < len(query):
            logger.warning(f"[QueryExpansion] 확장 결과가 부적절함 ('{raw_response}'), 원본 사용")
            expanded_query = query
        else:
            logger.info(f"[QueryExpansion] 확장 결과: '{expanded_query}'")
    except Exception as e:
        logger.warning(f"[QueryExpansion] 확장 실패, 원본 사용: {e}")
        expanded_query = query

    duration = time.perf_counter() - start_time
    logger.info(f"[QueryExpansion] 완료 - 소요시간: {duration:.3f}초")

    return expanded_query


