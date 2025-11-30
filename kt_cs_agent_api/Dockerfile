# ===========================================
# KT 상담원 AI Agent API - Dockerfile
# ===========================================
# 
# 빌드: docker build -t kt-cs-agent .
# 실행: docker run -d -p 8000:8000 --env-file .env kt-cs-agent
#

# -----------------------------------------
# Base Image
# -----------------------------------------
FROM python:3.11-slim as base

# 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 작업 디렉토리 설정
WORKDIR /app

# -----------------------------------------
# Builder Stage
# -----------------------------------------
FROM base as builder

# 빌드 도구 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치 (캐싱 활용)
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# -----------------------------------------
# Production Stage
# -----------------------------------------
FROM base as production

# 사용자 생성 (보안)
RUN useradd --create-home --shell /bin/bash appuser

# 빌드 스테이지에서 설치된 패키지 복사
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# 애플리케이션 코드 복사
COPY --chown=appuser:appuser . .

# 사용자 전환
USER appuser

# 헬스 체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 포트 노출
EXPOSE 8000

# 실행 명령
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
