#!/bin/bash
# ===========================================
# 논캐시 모드로 API 서버 실행
# ===========================================
#
# 이 스크립트는 Redis 캐싱 없이
# API 서버를 실행합니다.
#
# 사용법:
#   chmod +x scripts/start_without_cache.sh
#   ./scripts/start_without_cache.sh
#
# 캐싱이 비활성화되면:
# - 매 요청마다 임베딩 + 벡터 검색 + LLM 호출
# - 일관된 응답 시간 (캐시 히트/미스 변동 없음)
# - Redis 의존성 없음
# ===========================================

set -e

# 프로젝트 루트로 이동
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "KT CS Agent API - 논캐시 모드 시작"
echo "=========================================="

# 1. 가상환경 활성화 (존재하는 경우)
if [ -d "venv" ]; then
    echo ""
    echo "🐍 가상환경 활성화..."
    source venv/bin/activate
fi

# 2. 의존성 확인
echo ""
echo "📚 의존성 확인..."
python -c "import fastapi, langchain" 2>/dev/null || {
    echo "⚠️ 필수 패키지가 없습니다."
    echo "   pip install -r requirements.txt"
    exit 1
}

# 3. API 서버 시작
echo ""
echo "=========================================="
echo "🚀 API 서버 시작"
echo "=========================================="
echo ""
echo "캐싱 모드: 비활성화"
echo "API 문서: http://localhost:8001/docs"
echo ""
echo "⚠️ 주의: 캐싱 없이 운영되므로 응답 시간이 길어질 수 있습니다."
echo ""
echo "종료하려면 Ctrl+C를 누르세요."
echo ""

# 환경 변수로 캐싱 비활성화
export CACHE_ENABLED=False
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
