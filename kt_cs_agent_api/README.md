# KT 상담원 AI Agent API

KT 고객센터 상담원을 지원하는 AI Agent FastAPI 서버입니다.

## 개요

이 서비스는 LangGraph 기반의 AI Agent를 통해 다음 기능을 제공합니다:

- **신입 상담원 지원**: 상담 내용 분석 → 키워드 추출 → 문서 검색 → 구조화된 대응방안 생성
- **전문가 직접 검색**: 키워드 기반 벡터 DB 직접 검색 (빠른 응답)
- **비교 API**: 다양한 검색/응답 생성 방식 A/B 테스트
- **2단계 캐싱**: Redis 기반 L1/L2 캐싱으로 응답 속도 최적화
- **시스템 모니터링**: 헬스 체크, 대기열 상태, 캐시 통계 조회

## 기술 스택

### Core Framework
- **FastAPI** - 고성능 비동기 웹 프레임워크
- **LangGraph** - AI Agent 워크플로우 오케스트레이션
- **LangChain** - LLM 애플리케이션 구축 프레임워크

### AI/ML
- **OpenAI GPT-5-nano** - 키워드 추출, 응답 생성, 쿼리 정규화 LLM
- **OpenAI text-embedding-3-small** - 벡터 임베딩
- **ChromaDB** - 벡터 데이터베이스

### Infrastructure
- **Redis** - 2단계 캐싱 시스템 (L1/L2)
- **Pydantic** - 데이터 검증 및 설정 관리
- **Uvicorn** - ASGI 웹 서버
- **Docker** - 컨테이너화 배포

## 아키텍처

### 전체 요청 처리 흐름

```
┌─────────────────────────────────────────────────────────┐
│                    클라이언트 요청                        │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│              요청 처리 파이프라인                          │
│  1. Request Validation (Pydantic)                       │
│  2. Rate Limiting & Concurrency Check                   │
│  3. Query Normalization (선택적 LLM 정규화)               │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│              캐싱 레이어 (Redis)                          │
│  L1 Hit? → 즉시 반환 (~50ms)                             │
│  L2 Hit? → 검색 스킵, LLM만 실행 (~500ms)                 │
│  Miss?   → 전체 처리 (~2000ms)                           │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│           LangGraph Agent 워크플로우                      │
│  [analyzer] → [searcher] → [response_generator]         │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│              캐시 저장 (L1 + L2)                          │
└──────────────────────────┬──────────────────────────────┘
                           ↓
                    클라이언트 응답
```

### 신입 상담원용 워크플로우
```
[사용자 요청]
      ↓
  [analyzer]          ← GPT-5-nano로 키워드 추출 + 문서 선택
      ↓
  [searcher]          ← ChromaDB에서 관련 문서 검색
      ↓
[response_generator]  ← GPT-5-nano로 구조화된 JSON 대응방안 생성
      ↓
  [AI 응답 반환]
```

### 전문가용 워크플로우
```
[사용자 요청]
      ↓
  [analyzer]          ← GPT-5-nano로 키워드 추출 + 문서 선택
      ↓
  [searcher]          ← ChromaDB에서 관련 문서 검색
      ↓
  [검색 결과 반환]   (응답 생성 없이 바로 반환)
```

## 프로젝트 구조

```
kt_cs_agent_api/
├── app/
│   ├── config/              # 환경 변수 및 설정
│   │   ├── __init__.py
│   │   └── settings.py      # Pydantic Settings
│   │
│   ├── database/            # 데이터베이스 관련
│   │   ├── __init__.py
│   │   ├── vector_db.py     # 벡터 DB 연결 관리
│   │   └── doc_registry.py  # 문서 레지스트리
│   │
│   ├── agent/               # LangGraph 에이전트
│   │   ├── __init__.py
│   │   ├── state.py         # 상태 스키마 정의
│   │   ├── nodes.py         # 노드 함수 정의
│   │   └── workflow.py      # 워크플로우 구성
│   │
│   ├── api/                 # FastAPI 라우터
│   │   ├── __init__.py
│   │   ├── health.py        # 헬스 체크
│   │   ├── consultation.py  # 신입 상담원용 API
│   │   ├── expert.py        # 전문가용 API
│   │   ├── comparison.py    # 비교 테스트 API
│   │   └── cache.py         # 캐시 관리 API
│   │
│   ├── models/              # Pydantic 스키마
│   │   ├── __init__.py
│   │   └── schemas.py       # 요청/응답 모델
│   │
│   ├── utils/               # 유틸리티
│   │   ├── __init__.py
│   │   ├── queue_manager.py     # 대기열/Rate Limit
│   │   ├── logging_config.py    # 로깅 설정
│   │   ├── cache_manager.py     # Redis 캐시 매니저
│   │   └── cache_helpers/       # API별 캐시 헬퍼
│   │       ├── __init__.py
│   │       ├── consultation_cache.py
│   │       ├── direct_keyword_cache.py
│   │       ├── keyword_extraction_cache.py
│   │       └── direct_full_cache.py
│   │
│   ├── __init__.py
│   └── main.py              # FastAPI 진입점
│
├── scripts/                 # 헬퍼 스크립트
│   ├── test_cache.py        # 캐시 테스트
│   ├── start_with_cache.sh  # 캐시 활성화 실행
│   └── start_without_cache.sh # 캐시 비활성화 실행
│
├── docker-compose.yml       # Redis 컨테이너 설정
├── requirements.txt         # 의존성 패키지
└── README.md
```

## 빠른 시작

### 1. 환경 설정

```bash
# 저장소 클론
git clone <repository-url>
cd kt_cs_agent_api

# 가상 환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. Redis 설정 (캐싱 사용 시)

```bash
# Docker Compose로 Redis 실행
docker-compose up -d

# 또는 로컬 Redis 사용
# brew install redis && brew services start redis  # macOS
# sudo apt install redis-server && sudo systemctl start redis  # Ubuntu
```

### 3. 환경 변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집
nano .env
```

**필수 설정:**
```env
# OpenAI API 키
OPENAI_API_KEY=sk-your-key-here

# 벡터 DB 경로
CHROMA_DB_PATH=/path/to/your/chroma_db
CHROMA_COLLECTION_NAME=kt_terms
```

**선택 설정 (캐싱):**
```env
# Redis 설정
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=       # 선택사항

# 캐시 설정
CACHE_ENABLED=True
CACHE_L1_TTL=3600     # L1 캐시 TTL (초)
CACHE_L2_TTL=7200     # L2 캐시 TTL (초)
```

### 4. 서버 실행

```bash
# 개발 모드 (자동 리로드)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 프로덕션 모드
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# 캐시 활성화/비활성화 스크립트 사용
./scripts/start_with_cache.sh
./scripts/start_without_cache.sh
```

### 5. API 문서 확인

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 엔드포인트

### 헬스 체크 (`/health`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/health` | 기본 헬스 체크 (Liveness) |
| GET | `/health/ready` | 상세 상태 확인 (Readiness) - Vector DB, Queue 상태 포함 |
| GET | `/health/queue` | 대기열 상태 (동시 요청 수, Rate Limit 상태) |

### 신입 상담원용 (`/consultation`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/consultation/assist` | 상담 지원 요청 (Full Agent) |

**요청 예시:**
```bash
curl -X POST http://localhost:8000/consultation/assist \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "3년 약정 기간 중 14개월 사용 후 중도 해지 시 발생하는 위약금 문의",
    "include_documents": true,
    "max_documents": 3
  }'
```

**응답 예시 (구조화된 JSON):**
```json
{
  "original_summary": "3년 약정 기간 중 14개월 사용 후 중도 해지 시 발생하는 위약금 문의",
  "extracted_keywords": "약정 해지 위약금 계산",
  "target_document": "인터넷이용약관",
  "documents": [
    {
      "source": "인터넷서비스이용약관.pdf",
      "page": 5,
      "content": "제15조(해지) 1. 이용자가 서비스를 해지하고자 할 경우...",
      "score": 0.234
    }
  ],
  "response_guide": {
    "announcement": {
      "title": "안내 멘트",
      "items": ["약정 해지 위약금은 남은 약정 기간에 비례하여 계산됩니다", "..."]
    },
    "cautions": {
      "title": "주의사항",
      "items": ["해지 후 재가입 시 신규 가입 조건 적용", "..."]
    },
    "check_required": {
      "title": "확인 필요 사항",
      "items": ["고객 약정 시작일 확인", "..."]
    },
    "next_steps": {
      "title": "다음 단계 안내",
      "items": ["위약금 정확한 금액 안내", "..."]
    }
  },
  "processing_time_ms": 1234.5
}
```

### 전문가용 (`/expert`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/expert/search` | 상담내용 기반 검색 (키워드 추출 포함) |
| GET | `/expert/search` | 상담내용 기반 검색 (GET 방식) |
| GET | `/expert/documents` | 등록된 문서 목록 및 벡터 DB 정보 조회 |

**요청 예시:**
```bash
# GET 방식
curl "http://localhost:8000/expert/search?keyword=해지위약금&k=5"

# POST 방식
curl -X POST http://localhost:8000/expert/search \
  -H "Content-Type: application/json" \
  -d '{
    "keyword": "3년 약정 기간 중 14개월 사용 후 중도 해지 시 위약금 문의",
    "k": 5,
    "include_score": false
  }'
```

### 비교 API (`/comparison`)

다양한 검색 및 응답 생성 방식을 비교 테스트할 수 있는 API입니다.

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/comparison/direct-search` | 직접 임베딩 검색 (키워드 추출 없음) |
| POST | `/comparison/direct-keyword` | 직접 임베딩 + 간단한 키워드 가이드 |
| POST | `/comparison/keyword-extraction` | 키워드 추출 + 키워드 가이드 |
| POST | `/comparison/direct-full-guide` | 직접 임베딩 + 전체 가이드 |

### 캐시 관리 (`/cache`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/cache/stats` | 캐시 통계 (히트 수, 메모리 사용량, TTL 설정) |
| POST | `/cache/invalidate` | 캐시 무효화 (전체/L1/L2 선택 가능) |
| POST | `/cache/normalize-test` | 쿼리 정규화 테스트 |
| POST | `/cache/cleanup` | 수동 LRU 기반 캐시 정리 |
| GET | `/cache/benchmark` | 성능 벤치마킹 |

## 캐싱 시스템

### 2단계 캐싱 구조

```
┌─────────────────────────────────────────────────────────┐
│                    L1 캐시 (전체 응답)                    │
│  Key: normalized_query                                  │
│  Value: 키워드 + 문서 + 가이드 전체                       │
│  TTL: 1시간 (기본)                                       │
│  히트 시: ~50ms                                          │
└─────────────────────────────────────────────────────────┘
                           ↓ (L1 미스)
┌─────────────────────────────────────────────────────────┐
│                    L2 캐시 (검색 결과)                    │
│  Key: search_query                                      │
│  Value: 검색된 문서 목록                                  │
│  TTL: 2시간 (기본)                                       │
│  히트 시: ~500ms (LLM 응답 생성만 실행)                   │
└─────────────────────────────────────────────────────────┘
                           ↓ (L2 미스)
┌─────────────────────────────────────────────────────────┐
│                    전체 처리                              │
│  키워드 추출 + 검색 + 응답 생성                           │
│  소요 시간: ~2000ms                                      │
└─────────────────────────────────────────────────────────┘
```

### 쿼리 정규화

유사한 질문에 대한 캐시 히트율을 높이기 위해 쿼리 정규화를 수행합니다:

- **단순 정규화**: 정규식 기반 (항상 적용)
- **LLM 정규화**: GPT-5-nano 기반 의미론적 정규화 (선택적)

**예시:**
- "위약금 얼마야?" = "해지 위약금 금액" = "약정 해지시 위약금"

## 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 키 (필수) | - |
| `CHROMA_DB_PATH` | ChromaDB 경로 (필수) | - |
| `CHROMA_COLLECTION_NAME` | 컬렉션 이름 | kt_terms |
| `EMBEDDING_MODEL_NAME` | 임베딩 모델 | text-embedding-3-small |
| `EMBEDDING_DEVICE` | 디바이스 (cpu/cuda) | cpu |
| `ANALYZER_MODEL` | 키워드 추출 모델 | gpt-5-nano |
| `RESPONSE_MODEL` | 응답 생성 모델 | gpt-5-nano |
| `NORMALIZER_MODEL` | 쿼리 정규화 모델 | gpt-5-nano |
| `API_HOST` | API 서버 호스트 | 0.0.0.0 |
| `API_PORT` | API 서버 포트 | 8000 |
| `MAX_CONCURRENT_REQUESTS` | 최대 동시 요청 | 10 |
| `RATE_LIMIT_PER_MINUTE` | 분당 요청 제한 | 30 |
| `REQUEST_TIMEOUT` | 요청 타임아웃(초) | 60 |
| `DEBUG` | 디버그 모드 | False |
| `LOG_LEVEL` | 로그 레벨 | INFO |
| `REDIS_HOST` | Redis 호스트 | localhost |
| `REDIS_PORT` | Redis 포트 | 6379 |
| `REDIS_DB` | Redis DB 번호 | 0 |
| `REDIS_PASSWORD` | Redis 비밀번호 | (없음) |
| `CACHE_ENABLED` | 캐싱 활성화 | True |
| `CACHE_L1_TTL` | L1 캐시 TTL(초) | 3600 |
| `CACHE_L2_TTL` | L2 캐시 TTL(초) | 7200 |

## Docker 배포

### 단독 배포

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# 빌드 및 실행
docker build -t kt-cs-agent .
docker run -d -p 8000:8000 --env-file .env kt-cs-agent
```

### Docker Compose (Redis 포함)

```bash
# Redis와 함께 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 종료
docker-compose down
```

## 성능 특성

| 시나리오 | 예상 응답 시간 |
|---------|--------------|
| L1 캐시 히트 | ~50ms |
| L2 캐시 히트 | ~500ms |
| 전체 처리 (캐시 미스) | ~2000ms |

| 제한 | 기본값 |
|-----|-------|
| 최대 동시 요청 | 10 |
| 분당 요청 제한 | 30 |
| 요청 타임아웃 | 60초 |

## 모니터링

### Kubernetes Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
```

### 캐시 모니터링

```bash
# 캐시 통계 조회
curl http://localhost:8000/cache/stats

# 캐시 벤치마킹
curl http://localhost:8000/cache/benchmark
```

## 보안 고려사항

1. **API 키 관리**: `.env` 파일은 절대 Git에 커밋하지 마세요
2. **CORS 설정**: 프로덕션에서는 특정 도메인만 허용
3. **Rate Limiting**: 환경변수로 조절 가능
4. **인증**: 필요 시 JWT 또는 API Key 인증 추가
5. **Redis 보안**: 프로덕션에서는 Redis 비밀번호 설정

## 트러블슈팅

### 벡터 DB 연결 오류
```
ERROR: ChromaDB 연결 실패
```
**해결방법:**
- `CHROMA_DB_PATH` 경로가 존재하는지 확인
- ChromaDB 컬렉션이 초기화되어 있는지 확인
- 파일 권한 확인 (`chmod -R 755 /path/to/chroma_db`)

### OpenAI API 오류
```
ERROR: Incorrect API key provided
```
**해결방법:**
- `.env` 파일의 `OPENAI_API_KEY` 값 확인
- API 키가 유효한지 OpenAI 대시보드에서 확인
- 환경 변수가 제대로 로딩되었는지 확인

### Redis 연결 오류
```
ERROR: Redis connection failed
```
**해결방법:**
- Redis 서버가 실행 중인지 확인 (`redis-cli ping`)
- `REDIS_HOST`, `REDIS_PORT` 설정 확인
- Docker 사용 시 `docker-compose up -d` 실행
- 캐싱 없이 실행: `CACHE_ENABLED=False`

### Rate Limit 초과
```
ERROR: Too many requests
```
**해결방법:**
- `.env`에서 `RATE_LIMIT_PER_MINUTE` 값 증가
- `MAX_CONCURRENT_REQUESTS` 값 조정

## 테스트

### 기본 테스트
```bash
# 헬스 체크
curl http://localhost:8000/health

# 문서 목록 조회
curl http://localhost:8000/expert/documents

# 간단한 검색 테스트
curl -X POST http://localhost:8000/expert/search \
  -H "Content-Type: application/json" \
  -d '{"keyword": "해지", "k": 3}'

# 캐시 통계 확인
curl http://localhost:8000/cache/stats
```

### 캐시 테스트
```bash
# 캐시 테스트 스크립트 실행
python scripts/test_cache.py

# 동일 쿼리 반복으로 캐시 효과 확인
for i in {1..3}; do
  curl -X POST http://localhost:8000/consultation/assist \
    -H "Content-Type: application/json" \
    -d '{"summary": "해지 위약금 문의"}'
  echo ""
done
```

## 개발 가이드

### 새 문서 추가하기
1. ChromaDB에 문서 추가
2. `app/database/doc_registry.py`의 `DEFAULT_DOC_REGISTRY` 수정
   ```python
   DEFAULT_DOC_REGISTRY = {
       "신규서비스약관": {
           "name": "신규서비스약관",
           "description": "신규 서비스 관련 이용약관 및 정책",
           "keywords": ["신규", "서비스", "가입"]
       }
   }
   ```

### 새 노드 추가하기 (워크플로우 확장)
1. `app/agent/nodes.py`에 노드 함수 정의
   ```python
   def new_node(state: AgentState) -> Dict[str, Any]:
       # 노드 로직
       return {"new_field": "value"}
   ```

2. `app/agent/state.py`의 `AgentState`에 필드 추가
   ```python
   class AgentState(TypedDict):
       new_field: str
   ```

3. `app/agent/workflow.py`에서 노드 등록
   ```python
   workflow.add_node("new_node", new_node)
   workflow.add_edge("searcher", "new_node")
   workflow.add_edge("new_node", "response_generator")
   ```

### 새 캐시 헬퍼 추가하기
1. `app/utils/cache_helpers/` 디렉토리에 새 파일 생성
2. 기존 캐시 헬퍼 패턴 따르기
   ```python
   class NewCacheHelper:
       def __init__(self, cache_manager: CacheManager):
           self.cache = cache_manager

       async def get_cached(self, query: str):
           # L1, L2 캐시 확인 로직
           pass

       async def set_cached(self, query: str, response: dict):
           # 캐시 저장 로직
           pass
   ```

## 성능 최적화 팁

1. **캐싱 활용**: L1/L2 캐싱으로 반복 쿼리 최적화
2. **쿼리 정규화**: 유사 질문 캐시 히트율 향상
3. **비동기 I/O**: FastAPI의 async 엔드포인트 활용
4. **Worker 수 증가**: `uvicorn --workers 4` (CPU 코어 수만큼)
5. **Redis 튜닝**: 메모리 정책 및 TTL 최적화

## 보안 체크리스트

- [ ] `.env` 파일 Git에 커밋 안함 (.gitignore 확인)
- [ ] OpenAI API 키 보안 저장소에 별도 관리
- [ ] Redis 비밀번호 설정 (프로덕션)
- [ ] CORS 설정을 프로덕션 도메인으로 제한
- [ ] Rate Limiting 활성화
- [ ] HTTPS 사용 (프로덕션)
- [ ] 입력 데이터 검증 (Pydantic으로 자동 처리)
- [ ] 로그에 민감 정보 포함하지 않음
