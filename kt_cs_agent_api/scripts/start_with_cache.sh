#!/bin/bash
# ===========================================
# 캐시 모드로 API 서버 실행
# ===========================================
#
# 이 스크립트는 Redis 캐싱이 활성화된 상태로
# API 서버를 실행합니다.
#
# 사용법:
#   chmod +x scripts/start_with_cache.sh
#   ./scripts/start_with_cache.sh
#
# 옵션:
#   --dev    개발 모드 (Redis Commander UI 포함)
#   --reset  캐시 초기화 후 시작
# ===========================================

set -e

# 프로젝트 루트로 이동
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "KT CS Agent API - 캐시 모드 시작"
echo "=========================================="

# 인자 파싱
DEV_MODE=false
RESET_CACHE=false

for arg in "$@"; do
    case $arg in
        --dev)
            DEV_MODE=true
            shift
            ;;
        --reset)
            RESET_CACHE=true
            shift
            ;;
    esac
done

# 1. Docker 확인
if ! command -v docker &> /dev/null; then
    echo "❌ Docker가 설치되어 있지 않습니다."
    echo "   https://docs.docker.com/get-docker/ 에서 설치하세요."
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "❌ Docker가 실행 중이지 않습니다."
    echo "   Docker Desktop을 시작해주세요."
    exit 1
fi

echo "✅ Docker 확인 완료"

# 2. Redis 컨테이너 시작
echo ""
echo "📦 Redis 컨테이너 시작 중..."

if [ "$DEV_MODE" = true ]; then
    echo "   (개발 모드: Redis Commander UI 포함)"
    docker-compose --profile dev up -d
    echo "   Redis Commander: http://localhost:8081"
else
    docker-compose up -d redis
fi

# Redis 준비 대기
echo ""
echo "⏳ Redis 준비 대기 중..."
for i in {1..30}; do
    if docker exec kt_cs_redis redis-cli ping &> /dev/null; then
        echo "✅ Redis 준비 완료"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Redis 시작 시간 초과"
        exit 1
    fi
    sleep 1
done

# 3. 캐시 초기화 (옵션)
if [ "$RESET_CACHE" = true ]; then
    echo ""
    echo "🗑️ 캐시 초기화 중..."
    docker exec kt_cs_redis redis-cli FLUSHDB
    echo "✅ 캐시 초기화 완료"
fi

# 4. 환경 변수 확인
echo ""
echo "🔧 환경 설정 확인..."

# .env 파일에서 CACHE_ENABLED 확인
if grep -q "CACHE_ENABLED=True" .env 2>/dev/null || grep -q "CACHE_ENABLED=true" .env 2>/dev/null; then
    echo "✅ 캐싱 활성화됨 (CACHE_ENABLED=True)"
else
    echo "⚠️ CACHE_ENABLED가 설정되지 않았습니다. .env 파일을 확인하세요."
    echo "   자동으로 True로 설정됩니다 (기본값)"
fi

# 5. 가상환경 활성화 (존재하는 경우)
if [ -d "venv" ]; then
    echo ""
    echo "🐍 가상환경 활성화..."
    source venv/bin/activate
fi

# 6. 의존성 확인
echo ""
echo "📚 의존성 확인..."
if ! python -c "import redis" 2>/dev/null; then
    echo "⚠️ redis 패키지가 없습니다. 설치 중..."
    pip install redis
fi

# 7. API 서버 시작
echo ""
echo "=========================================="
echo "🚀 API 서버 시작"
echo "=========================================="
echo ""
echo "캐싱 모드: 활성화"
echo "API 문서: http://localhost:8001/docs"
echo "캐시 API: http://localhost:8001/cache/stats"
if [ "$DEV_MODE" = true ]; then
    echo "Redis UI: http://localhost:8081"
fi
echo ""
echo "종료하려면 Ctrl+C를 누르세요."
echo ""

# 환경 변수 설정 후 서버 실행
export CACHE_ENABLED=True
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
