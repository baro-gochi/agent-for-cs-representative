# KT 상담원 AI Agent API

KT 고객센터 상담원을 지원하는 AI Agent FastAPI 서버입니다.

## 📋 개요

이 서비스는 LangGraph 기반의 AI Agent를 통해 다음 기능을 제공합니다:

- **신입 상담원 지원**: 상담 내용 분석 → 키워드 추출 → 문서 검색 → 대응방안 생성
- **전문가 직접 검색**: 키워드 기반 벡터 DB 직접 검색 (빠른 응답)
- **시스템 모니터링**: 헬스 체크 및 대기열 상태 조회

## 🛠 기술 스택

### Core Framework
- **FastAPI** - 고성능 비동기 웹 프레임워크
- **LangGraph** - AI Agent 워크플로우 오케스트레이션
- **LangChain** - LLM 애플리케이션 구축 프레임워크

### AI/ML
- **OpenAI GPT-4o-mini** - 응답 생성 LLM
- **OpenAI GPT-5-nano** - 키워드 추출 LLM
- **HuggingFace Transformers** - 한국어 임베딩 모델
- **ChromaDB** - 벡터 데이터베이스

### Infrastructure
- **Pydantic** - 데이터 검증 및 설정 관리
- **Uvicorn** - ASGI 웹 서버
- **Docker** - 컨테이너화 배포

## 🏛 아키텍처

### 신입 상담원용 워크플로우
```
[사용자 요청]
      ↓
  [analyzer]          ← GPT-5-nano로 키워드 추출 + 문서 선택
      ↓
  [searcher]          ← ChromaDB에서 관련 문서 검색
      ↓
[response_generator]  ← GPT-4o-mini로 대응방안 생성
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

## 🏗 프로젝트 구조

```
kt_cs_agent_api/
├── app/
│   ├── config/           # 환경 변수 및 설정
│   │   ├── __init__.py
│   │   └── settings.py   # Pydantic Settings
│   │
│   ├── database/         # 데이터베이스 관련
│   │   ├── __init__.py
│   │   ├── vector_db.py     # 벡터 DB 연결 관리 [데이터/ML팀]
│   │   └── doc_registry.py  # 문서 레지스트리 [콘텐츠팀]
│   │
│   ├── agent/            # LangGraph 에이전트
│   │   ├── __init__.py
│   │   ├── state.py      # 상태 스키마 정의
│   │   ├── nodes.py      # 노드 함수 정의 [AI팀]
│   │   └── workflow.py   # 워크플로우 구성
│   │
│   ├── api/              # FastAPI 라우터
│   │   ├── __init__.py
│   │   ├── health.py        # 헬스 체크 [인프라팀]
│   │   ├── consultation.py  # 신입 상담원용 API
│   │   └── expert.py        # 전문가용 API
│   │
│   ├── models/           # Pydantic 스키마
│   │   ├── __init__.py
│   │   └── schemas.py    # 요청/응답 모델
│   │
│   ├── utils/            # 유틸리티
│   │   ├── __init__.py
│   │   ├── queue_manager.py   # 대기열/Rate Limit [인프라팀]
│   │   └── logging_config.py  # 로깅 설정
│   │
│   ├── __init__.py
│   └── main.py           # FastAPI 진입점
│
├── tests/                # 테스트 코드
├── .env.example          # 환경 변수 예시
├── requirements.txt      # 의존성 패키지
└── README.md
```

## 🚀 빠른 시작

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

### 2. 환경 변수 설정

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

### 3. 서버 실행

```bash
# 개발 모드 (자동 리로드)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 프로덕션 모드
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4. API 문서 확인

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 📡 API 엔드포인트

### 헬스 체크

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/health` | 기본 헬스 체크 (Liveness) |
| GET | `/health/ready` | 상세 상태 확인 (Readiness) |
| GET | `/health/queue` | 대기열 상태 |

### 신입 상담원용

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

**응답 예시:**
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
  "response_guide": "고객님께서 3년 약정 중 14개월 사용 후 해지하시는 경우, 약관 제15조에 따라...",
  "processing_time_ms": 1234.5
}
```

### 전문가용

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/expert/search` | 상담내용 기반 검색 |
| GET | `/expert/search` | 상담내용 기반 (GET) |
| GET | `/expert/documents` | 문서 목록 조회 |

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

**응답 예시:**
```json
{
  "keyword": "3년 약정 기간 중 14개월 사용 후 중도 해지 시 위약금 문의",
  "extracted_keywords": "인터넷 약정 해지 위약금",
  "target_document": "인터넷이용약관",
  "total_results": 3,
  "documents": [
    {
      "source": "인터넷서비스이용약관.pdf",
      "page": 5,
      "content": "제15조(해지) 1. 이용자가 서비스를 해지하고자 할 경우..."
    }
  ],
  "processing_time_ms": 456.7
}
```

## ⚙️ 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 키 (필수) | - |
| `CHROMA_DB_PATH` | ChromaDB 경로 (필수) | - |
| `CHROMA_COLLECTION_NAME` | 컬렉션 이름 | kt_terms |
| `EMBEDDING_MODEL_NAME` | 임베딩 모델 | jhgan/ko-sroberta-multitask |
| `EMBEDDING_DEVICE` | 디바이스 (cpu/cuda) | cpu |
| `ANALYZER_MODEL` | 키워드 추출 모델 | gpt-5-nano |
| `RESPONSE_MODEL` | 응답 생성 모델 | gpt-4o-mini |
| `API_HOST` | API 서버 호스트 | 0.0.0.0 |
| `API_PORT` | API 서버 포트 | 8000 |
| `MAX_CONCURRENT_REQUESTS` | 최대 동시 요청 | 10 |
| `RATE_LIMIT_PER_MINUTE` | 분당 요청 제한 | 30 |
| `REQUEST_TIMEOUT` | 요청 타임아웃(초) | 60 |
| `DEBUG` | 디버그 모드 | False |
| `LOG_LEVEL` | 로그 레벨 | INFO |


## 🐳 Docker 배포

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

## 📊 모니터링

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

## 🔒 보안 고려사항

1. **API 키 관리**: `.env` 파일은 절대 Git에 커밋하지 마세요
2. **CORS 설정**: 프로덕션에서는 특정 도메인만 허용
3. **Rate Limiting**: 환경변수로 조절 가능
4. **인증**: 필요 시 JWT 또는 API Key 인증 추가

## 🔍 트러블슈팅

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

### 임베딩 모델 로딩 느림
**해결방법:**
- 첫 요청 시 모델이 다운로드되므로 시간이 걸릴 수 있음
- GPU 사용 시: `EMBEDDING_DEVICE=cuda` 설정
- 모델 캐시 위치: `~/.cache/huggingface/`

### Rate Limit 초과
```
ERROR: Too many requests
```
**해결방법:**
- `.env`에서 `RATE_LIMIT_PER_MINUTE` 값 증가
- `MAX_CONCURRENT_REQUESTS` 값 조정
- Redis 기반 분산 Rate Limiting 구현 고려

## 🧪 테스트

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
```

### 부하 테스트
```bash
# Apache Bench 사용
ab -n 100 -c 10 -p request.json -T application/json \
  http://localhost:8000/consultation/assist

# 또는 Python으로 간단히
python -c "
import requests
import concurrent.futures

def test_request():
    response = requests.post(
        'http://localhost:8000/consultation/assist',
        json={'summary': '테스트 문의'}
    )
    return response.status_code

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(lambda _: test_request(), range(50)))
    print(f'Success: {results.count(200)}/{len(results)}')
"
```

## 🚧 개발 가이드

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

### 다른 벡터 DB로 교체하기
`app/database/vector_db.py` 파일만 수정하면 됩니다:
```python
# Pinecone 예시
class VectorDBManager:
    def __init__(self):
        import pinecone
        pinecone.init(api_key=settings.PINECONE_API_KEY)
        self.index = pinecone.Index("kt-docs")
    
    def search(self, query: str, k: int = 5):
        # Pinecone 검색 로직
        pass
```

### 로그 확인하기
```bash
# 실시간 로그 모니터링
tail -f app.log

# 에러만 필터링
grep ERROR app.log

# 특정 요청 추적
grep "request_id:abc123" app.log
```

## 📊 성능 최적화 팁

1. **임베딩 캐싱**: 동일한 쿼리는 캐싱하여 재사용
2. **배치 처리**: 여러 요청을 묶어서 처리
3. **비동기 I/O**: `ainvoke()` 메서드 활용 (향후 지원)
4. **GPU 활용**: `EMBEDDING_DEVICE=cuda` 설정
5. **Worker 수 증가**: `uvicorn --workers 4` (CPU 코어 수만큼)

## 🔐 보안 체크리스트

- [ ] `.env` 파일 Git에 커밋 안함 (.gitignore 확인)
- [ ] OpenAI API 키 보안 저장소에 별도 관리
- [ ] CORS 설정을 프로덕션 도메인으로 제한
- [ ] Rate Limiting 활성화
- [ ] HTTPS 사용 (프로덕션)
- [ ] 입력 데이터 검증 (Pydantic으로 자동 처리)
- [ ] 로그에 민감 정보 포함하지 않음
