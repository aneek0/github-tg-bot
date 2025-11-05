"""Утилиты для работы с GitHub"""
import os
import logging
from typing import Optional, List
from dotenv import load_dotenv
from bot.services.github import GitHubClient
from bot.utils.token_manager import TokenManager

# Загружаем переменные окружения
load_dotenv()

logger = logging.getLogger(__name__)

# Глобальные GitHub токены из .env (поддерживается несколько токенов через запятую)
_GITHUB_TOKENS_STR = os.getenv("GITHUB_TOKEN", "")
_GITHUB_TOKENS: List[str] = []

# Парсим токены (поддерживаем запятую и точку с запятой как разделители)
if _GITHUB_TOKENS_STR:
    # Пробуем сначала точку с запятой (если указано несколько токенов явно)
    if ";" in _GITHUB_TOKENS_STR:
        _GITHUB_TOKENS = [t.strip() for t in _GITHUB_TOKENS_STR.split(";") if t.strip()]
    else:
        # Иначе используем запятую
        _GITHUB_TOKENS = [t.strip() for t in _GITHUB_TOKENS_STR.split(",") if t.strip()]

# Создаем менеджер токенов
_token_manager = TokenManager(_GITHUB_TOKENS) if _GITHUB_TOKENS else None


def get_github_token() -> Optional[str]:
    """Получает текущий GitHub токен из менеджера"""
    if _token_manager:
        return _token_manager.get_current_token()
    return None


def get_token_manager() -> Optional[TokenManager]:
    """Возвращает менеджер токенов"""
    return _token_manager


def create_github_client(token: Optional[str] = None) -> GitHubClient:
    """Создает экземпляр GitHubClient с токеном
    
    Если token не указан, использует менеджер токенов для автоматического выбора
    """
    if token and token.strip():
        # Используем переданный токен (например, из настроек репозитория)
        github_token = token.strip()
    elif _token_manager:
        # Используем менеджер токенов
        result = _token_manager.get_available_token()
        if result:
            github_token, wait_time = result
            if wait_time and wait_time > 0:
                logger.warning(f"⚠️ Все токены исчерпаны. Минимальное время ожидания: {wait_time // 60}м {wait_time % 60}с")
        else:
            github_token = None
    else:
        github_token = None
    
    if not github_token:
        logger.warning("⚠️ GITHUB_TOKEN пустой! Создается клиент без токена.")
    
    return GitHubClient(github_token, token_manager=_token_manager)

