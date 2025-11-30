"""
===========================================
문서 레지스트리 관리 모듈
===========================================

이 모듈은 상담에 사용되는 문서들의 매핑 정보를 관리합니다.
- 문서 별칭 → 실제 경로 매핑
- JSON 파일 기반 동적 로딩 지원
- 문서 목록 조회

수정 가이드:
    1. 새 문서 추가: DEFAULT_DOC_REGISTRY에 항목 추가
    2. 외부 JSON 파일 사용: DOC_REGISTRY_PATH 환경변수 설정
    
JSON 파일 형식 예시:
    {
        "인터넷이용약관": "/content/인터넷서비스이용약관.pdf",
        "TV서비스약관": "/content/TV서비스이용약관.pdf"
    }

사용 예시:
    from app.database.doc_registry import get_doc_registry
    
    registry = get_doc_registry()
    path = registry.get_document_path("인터넷이용약관")
"""

import json
import logging
from typing import Dict, List, Optional
from pathlib import Path

from app.config import settings

# 로거 설정
logger = logging.getLogger(__name__)


# ==========================================
# 기본 문서 레지스트리
# ==========================================
# 새 문서를 추가하려면 여기에 항목을 추가하세요.
# 형식: "문서 별칭": "실제 파일 경로"

DEFAULT_DOC_REGISTRY: Dict[str, str] = {
    # 예시 - 실제 환경에 맞게 수정 필요
    "인터넷이용약관": "/content/(이용약관전문)인터넷서비스이용약관_202509.pdf",
    # "TV서비스약관": "/content/TV서비스이용약관.pdf",
    # "모바일이용약관": "/content/모바일서비스이용약관.pdf",
}


class DocumentRegistry:
    """
    문서 레지스트리 관리 클래스
    
    문서 별칭과 실제 파일 경로 간의 매핑을 관리합니다.
    
    Attributes:
        registry: 문서 별칭 → 경로 매핑 딕셔너리
        source: 레지스트리 소스 ("default" 또는 JSON 파일 경로)
    """
    
    def __init__(self):
        """DocumentRegistry 초기화"""
        self.registry: Dict[str, str] = {}
        self.source: str = "default"
        self._load_registry()
    
    def _load_registry(self) -> None:
        """
        레지스트리 로딩
        
        환경변수 DOC_REGISTRY_PATH가 설정되어 있으면 
        해당 JSON 파일에서 로딩하고, 없으면 기본 레지스트리를 사용합니다.
        """
        if settings.DOC_REGISTRY_PATH:
            self._load_from_json(settings.DOC_REGISTRY_PATH)
        else:
            self._load_default()
    
    def _load_default(self) -> None:
        """기본 레지스트리 로딩"""
        self.registry = DEFAULT_DOC_REGISTRY.copy()
        self.source = "default"
        logger.info(f"기본 문서 레지스트리 로딩 완료: {len(self.registry)}개 문서")
    
    def _load_from_json(self, json_path: str) -> None:
        """
        JSON 파일에서 레지스트리 로딩
        
        Args:
            json_path: JSON 파일 경로
        
        Raises:
            FileNotFoundError: 파일이 없을 때
            json.JSONDecodeError: JSON 파싱 실패 시
        """
        try:
            path = Path(json_path)
            
            if not path.exists():
                logger.warning(f"JSON 파일 없음: {json_path}, 기본 레지스트리 사용")
                self._load_default()
                return
            
            with open(path, 'r', encoding='utf-8') as f:
                self.registry = json.load(f)
            
            self.source = json_path
            logger.info(f"JSON에서 문서 레지스트리 로딩 완료: {len(self.registry)}개 문서")
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {e}, 기본 레지스트리 사용")
            self._load_default()
        except Exception as e:
            logger.error(f"레지스트리 로딩 실패: {e}, 기본 레지스트리 사용")
            self._load_default()
    
    def get_document_path(self, doc_name: str) -> Optional[str]:
        """
        문서 별칭으로 실제 경로 조회
        
        Args:
            doc_name: 문서 별칭 (예: "인터넷이용약관")
        
        Returns:
            str: 실제 파일 경로, 없으면 None
        
        사용 예시:
            path = registry.get_document_path("인터넷이용약관")
            if path:
                print(f"경로: {path}")
        """
        return self.registry.get(doc_name)
    
    def has_document(self, doc_name: str) -> bool:
        """
        문서 존재 여부 확인
        
        Args:
            doc_name: 문서 별칭
        
        Returns:
            bool: 존재하면 True
        """
        return doc_name in self.registry
    
    def get_all_document_names(self) -> List[str]:
        """
        모든 문서 별칭 목록 반환
        
        Returns:
            List[str]: 문서 별칭 리스트
        """
        return list(self.registry.keys())
    
    def get_document_list_string(self) -> str:
        """
        문서 목록을 문자열로 반환 (프롬프트용)
        
        Returns:
            str: 줄바꿈으로 구분된 문서 목록
            
        예시 출력:
            - 인터넷이용약관
            - TV서비스약관
        """
        return "\n".join([f"- {name}" for name in self.registry.keys()])
    
    def get_registry_info(self) -> Dict:
        """
        레지스트리 정보 조회 (디버깅/관리용)
        
        Returns:
            Dict: 레지스트리 메타 정보
        """
        return {
            "source": self.source,
            "document_count": len(self.registry),
            "documents": self.get_all_document_names()
        }
    
    def reload(self) -> None:
        """
        레지스트리 재로딩
        
        JSON 파일이 업데이트되었을 때 사용합니다.
        """
        logger.info("문서 레지스트리 재로딩 중...")
        self._load_registry()


# ==========================================
# 싱글톤 인스턴스 관리
# ==========================================

_doc_registry: Optional[DocumentRegistry] = None


def get_doc_registry() -> DocumentRegistry:
    """
    DocumentRegistry 싱글톤 인스턴스 반환
    
    Returns:
        DocumentRegistry: 레지스트리 인스턴스
    """
    global _doc_registry
    
    if _doc_registry is None:
        _doc_registry = DocumentRegistry()
    
    return _doc_registry


def reset_doc_registry() -> None:
    """
    레지스트리 인스턴스 리셋
    
    설정 변경 후 재로딩이 필요할 때 사용합니다.
    """
    global _doc_registry
    logger.info("DocumentRegistry 리셋")
    _doc_registry = None
