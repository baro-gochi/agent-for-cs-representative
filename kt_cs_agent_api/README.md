# 상담원 AI Agent API

고객센터 상담원을 지원하는 AI Agent FastAPI 서버입니다.

## 📋 개요

이 서비스는 LangGraph 기반의 AI Agent를 통해 다음 기능을 제공합니다:

- **신입 상담원 지원**: 상담 내용 분석 → 키워드 추출 → 문서 검색 → 대응방안 생성
- **전문가 직접 검색**: 키워드 기반 벡터 DB 직접 검색 (빠른 응답)
- **시스템 모니터링**: 헬스 체크 및 대기열 상태 조회

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
  -d '{"summary": "인터넷 약정 해지 시 위약금 계산법이 궁금합니다."}'
```

### 전문가용

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/expert/search` | 키워드 직접 검색 |
| GET | `/expert/search` | 키워드 직접 검색 (GET) |
| GET | `/expert/documents` | 문서 목록 조회 |

**요청 예시:**
```bash
# GET 방식
curl "http://localhost:8000/expert/search?keyword=해지위약금&k=5"

# POST 방식
curl -X POST http://localhost:8000/expert/search \
  -H "Content-Type: application/json" \
  -d '{"keyword": "해지 위약금", "k": 5, "include_score": true}'
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
| `MAX_CONCURRENT_REQUESTS` | 최대 동시 요청 | 10 |
| `RATE_LIMIT_PER_MINUTE` | 분당 요청 제한 | 30 |
| `REQUEST_TIMEOUT` | 요청 타임아웃(초) | 60 |
| `DEBUG` | 디버그 모드 | False |
| `LOG_LEVEL` | 로그 레벨 | INFO |

## 🔧 담당팀별 가이드

### AI/ML 팀
- `app/agent/nodes.py`: 노드 로직 및 프롬프트 수정
- `app/agent/workflow.py`: 워크플로우 구조 변경
- `app/config/settings.py`: 모델 관련 설정

### 데이터/ML 엔지니어팀
- `app/database/vector_db.py`: 벡터 DB 연결 및 검색 로직
- 다른 벡터 DB(Pinecone, Weaviate 등)로 교체 시 이 파일만 수정

### 콘텐츠/운영팀
- `app/database/doc_registry.py`: 문서 레지스트리 관리
- 새 문서 추가: `DEFAULT_DOC_REGISTRY` 딕셔너리 수정
- 외부 JSON 파일 사용: `DOC_REGISTRY_PATH` 환경변수 설정

### 인프라/DevOps 팀
- `app/utils/queue_manager.py`: 대기열 및 Rate Limit 설정
- `app/api/health.py`: 헬스 체크 로직
- `.env.example`: 환경 변수 템플릿

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

