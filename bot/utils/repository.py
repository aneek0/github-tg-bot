"""Утилиты для работы с репозиториями"""
import logging
from typing import Optional, Tuple
from bot.services.github import GitHubClient

logger = logging.getLogger(__name__)


def parse_repo_input(repo_input: str, github_client: GitHubClient) -> Optional[Tuple[str, str]]:
    """Парсит ввод пользователя (URL или owner/repo) и возвращает (owner, repo)"""
    repo_input = repo_input.strip()
    
    # Если это URL GitHub
    if "github.com" in repo_input:
        parsed = github_client.parse_repo_url(repo_input)
        if parsed:
            return parsed
        return None
    
    # Если есть пробел (owner repo)
    if " " in repo_input:
        parts = repo_input.split()
        if len(parts) >= 2:
            return parts[0], parts[1]
        return None
    
    # Если это owner/repo
    if "/" in repo_input:
        parts = repo_input.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
        return None
    
    return None


def get_repo_key(owner: str, repo: str) -> str:
    """Формирует ключ репозитория из owner и repo"""
    return f"{owner}/{repo}"

