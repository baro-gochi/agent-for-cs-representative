"""
===========================================
로깅 설정 모듈
===========================================

이 모듈은 애플리케이션의 로깅 설정을 관리합니다.
- 콘솔 출력 포맷
- 파일 출력 설정
- 로그 레벨 관리

사용 예시:
    from app.utils.logging_config import setup_logging
    
    # 애플리케이션 시작 시 호출
    setup_logging()
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from app.config import settings


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None
) -> None:
    """
    로깅 설정 초기화
    
    Args:
        level: 로그 레벨 (기본: settings.LOG_LEVEL)
        log_file: 로그 파일 경로 (기본: settings.LOG_FILE_PATH)
    
    Note:
        이 함수는 애플리케이션 시작 시 한 번만 호출해야 합니다.
    """
    level = level or settings.LOG_LEVEL
    log_file = log_file or settings.LOG_FILE_PATH
    
    # 로그 레벨 변환
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # 포맷 설정
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 기존 핸들러 제거
    root_logger.handlers.clear()
    
    # -----------------------------------------
    # 콘솔 핸들러
    # -----------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # -----------------------------------------
    # 파일 핸들러 (설정된 경우)
    # -----------------------------------------
    if log_file:
        # 디렉토리 생성
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 로테이팅 파일 핸들러
        # - 10MB마다 새 파일
        # - 최대 5개 백업 유지
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # -----------------------------------------
    # 외부 라이브러리 로그 레벨 조정
    # -----------------------------------------
    # 너무 상세한 로그 억제
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    
    # uvicorn 로그 조정
    logging.getLogger("uvicorn").setLevel(log_level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    logging.info(f"로깅 설정 완료: level={level}, file={log_file or 'None'}")


def get_logger(name: str) -> logging.Logger:
    """
    모듈별 로거 생성
    
    Args:
        name: 로거 이름 (보통 __name__ 사용)
    
    Returns:
        Logger: 설정된 로거 인스턴스
    
    사용 예시:
        logger = get_logger(__name__)
        logger.info("메시지")
    """
    return logging.getLogger(name)
