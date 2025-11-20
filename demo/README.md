# [2025 KT CS 일경험 사업] 상담 지식 검색(RAG) 모듈

## Team 바로고치 - Search Module

Consulting Knowledge RAG System
약관 및 상담 매뉴얼 기반의 지능형 검색 및 답변 보조 시스템

## 프로젝트 개요

**목표**: 상담 내용 분석 및 벡터 DB(Chroma) 기반 최적의 약관 검색 기능 구현

**현재 상태**: ✅ LangGraph 및 LCEL을 활용한 단일/다중 문서 검색 로직 초기 버전 구현 완료

## 구성 파일 및 기능

### 📂 Single Document Search (단일 문서 대상)

하나의 약관 파일(예: 인터넷 이용약관) 내에서 정확한 조항을 찾는 기본 모델입니다.

  - **Data_preprocessing_sample.ipynb**
    - PDF 문서를 로드하고 임베딩하여 로컬 벡터 DB(Chroma)를 생성하는 **간이(Simple) 구축 스크립트**입니다.
    - RAG 시스템 테스트를 위한 초기 데이터 적재 용도로 사용됩니다.

  - **Searchquery\_simple\_langgraph\_withOpenai.py**
      - **기능**: LangGraph의 State/Node 구조를 활용한 기본 검색기
      - **특징**: 확장성을 고려한 그래프 구조, 질문 분석 → 키워드 추출 → 검색 흐름 제어
  - **Searchquery\_simple\_LCEL\_withOpenai.py**
      - **기능**: LCEL(LangChain Expression Language)을 적용한 경량화 버전
      - **특징**: 파이프라인(`|`) 구조로 코드 간소화 및 실행 속도 최적화

### 📂 Multi Document Search (다중 문서 대상)

여러 약관(인터넷, TV, 모바일 등) 중 적합한 문서를 자동으로 판단하고 검색합니다.

  - **Searchquery\_multi\_langgraph\_withOpenai.py**
      - **기능**: 상담 내용에 따라 검색할 문서 파일(Source)을 지정하는 라우팅(Routing) 로직 포함
      - **특징**: `Analyzer Node`(분석)와 `Search Node`(검색)의 역할 분리, 하이브리드 검색(Scoped + Global) 구현
  - **Searchquery\_multi\_LCEL\_withOpenai.py**
      - **기능**: 문서 관리 대장(Registry)과 매핑 로직을 LCEL 체인으로 구현
      - **특징**: 복잡한 분기 처리를 단일 체인으로 통합하여 유지보수성 및 효율성 극대화

## 핵심 로직 (Architecture)

### 🧠 Query Analysis (질문 분석)

  - 상담 요약 텍스트를 입력받아 **검색에 최적화된 키워드(Keyword)** 를 추출
  - 불필요한 조사를 제거하고 '명사 중심'의 핵심 용어로 변환 (GPT-5-nano 활용)

### 🔀 Document Routing (문서 라우팅)

  - **Multi 버전 기능**: 상담 내용이 '인터넷' 관련인지 'TV' 관련인지 AI가 판단
  - **Registry 패턴**: AI가 인식하기 쉬운 '별칭'과 실제 DB의 '파일 경로'를 매핑하여 정확도 확보

### 🔍 Hybrid Retrieval (하이브리드 검색)

1.  **Scoped Search**: AI가 추천한 특정 문서 내에서 정밀 검색 (k=2)
2.  **Global Search**: 전체 문서 대상 보완 검색 (k=1)
3.  **Result**: 중복 제거 후 최종 근거 문서 제시

## 기술 스택

  - **Framework**: LangChain, LangGraph
  - **LLM**: OpenAI (gpt-5-nano)
  - **Vector DB**: ChromaDB (Local Persist)
  - **Embedding**: HuggingFace (`jhgan/ko-sroberta-multitask`)

## 빠른 시작

```bash
# 1. 벡터 DB 생성 (선행 필요)
# PDF 파일을 로드하여 로컬 ChromaDB 생성

# 2. 검색 모듈 실행 (예시: Multi LCEL 버전)
python Searchquery_multi_LCEL_withOpenai.py
```

-----

**Version**: 0.1.0 (RAG Logic Implementation)