import asyncio
import logging
import os
import time
from typing import Dict, Any
from datetime import datetime, timedelta
from aiogram import Bot
from dotenv import load_dotenv
from bot.utils.constants import DELAY_BETWEEN_REPO_CHECKS

from bot.services.database import (
    get_all_repositories,
    update_last_commit_sha,
    update_last_star_count,
    update_statistics
)
from bot.services.github import GitHubClient
from bot.services.formatter import (
    format_commit_message,
    format_star_message,
    format_fork_message,
    format_issue_message,
    format_pull_request_message
)

# Загружаем переменные окружения (на случай если они не загружены)
load_dotenv()

# Глобальный GitHub токен из .env
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

logger = logging.getLogger(__name__)


class PollingService:
    """Сервис для периодической проверки изменений через GitHub API"""
    
    def __init__(self, bot: Bot, interval: int = 60):
        self.bot = bot
        self.interval = interval
        self.running = False
    
    async def start(self) -> None:
        """Запускает polling сервис"""
        self.running = True
        logger.info(f"Polling service started with interval {self.interval}s")
        
        while self.running:
            try:
                await self._check_all_repositories()
            except Exception as e:
                logger.error(f"Ошибка в polling сервисе: {e}", exc_info=True)
            
            await asyncio.sleep(self.interval)
    
    def stop(self) -> None:
        """Останавливает polling сервис"""
        self.running = False
        logger.info("Polling service stopped")
    
    async def _check_all_repositories(self) -> None:
        """Проверяет все репозитории на изменения"""
        repos = await get_all_repositories()
        
        if not repos:
            return
        
        # Примечание: rate limit проверяется внутри GitHubClient при каждом запросе
        # Если лимит исчерпан, запросы будут пропускаться автоматически
        
        for repo_key, repo_data in repos.items():
            try:
                await self._check_repository(repo_key, repo_data)
                # Добавляем задержку между проверками репозиториев
                # чтобы не превысить rate limit
                await asyncio.sleep(DELAY_BETWEEN_REPO_CHECKS)  # Увеличил до 2 секунд
            except Exception as e:
                logger.error(f"Ошибка проверки репозитория {repo_key}: {e}")
                # Задержка даже при ошибке
                await asyncio.sleep(DELAY_BETWEEN_REPO_CHECKS)
    
    async def _check_repository(self, repo_key: str, repo_data: Dict[str, Any]) -> None:
        """Проверяет конкретный репозиторий на изменения"""
        owner, repo = repo_key.split("/", 1)
        events_config = repo_data.get("events", {})
        chat_id = repo_data.get("chat_id")
        # Используем токен из репозитория или глобальный из .env
        repo_token = repo_data.get("github_token")
        # Проверяем что токен не пустой (не None и не пустая строка)
        github_token = repo_token if repo_token and repo_token.strip() else GITHUB_TOKEN
        
        # Логируем для отладки
        if not github_token or not github_token.strip():
            logger.error(f"⚠️ ВНИМАНИЕ! Для репозитория {repo_key} токен не найден! repo_token={repo_token}, env_token={bool(GITHUB_TOKEN)}")
        
        github_client = GitHubClient(github_token)
        
        # Проверяем коммиты
        if events_config.get("commits", False):
            await self._check_commits(github_client, repo_key, owner, repo, chat_id, repo_data)
        
        # Проверяем звезды
        if events_config.get("watch", False):
            await self._check_stars(github_client, repo_key, owner, repo, chat_id, repo_data)
        
        # Проверяем форки
        if events_config.get("forks", False):
            await self._check_forks(github_client, repo_key, owner, repo, chat_id, repo_data)
        
        # Проверяем issues
        issues_config = events_config.get("issues", {})
        if any(issues_config.values()):
            await self._check_issues(github_client, repo_key, owner, repo, chat_id, issues_config)
        
        # Проверяем pull requests
        pr_config = events_config.get("pull_requests", {})
        if any(pr_config.values()):
            await self._check_pull_requests(github_client, repo_key, owner, repo, chat_id, pr_config)
        
        # Обновляем статистику
        stats = await github_client.get_statistics(owner, repo)
        await update_statistics(repo_key, stats)
    
    async def _check_commits(
        self,
        github_client: GitHubClient,
        repo_key: str,
        owner: str,
        repo: str,
        chat_id: int,
        repo_data: Dict[str, Any]
    ) -> None:
        """Проверяет новые коммиты"""
        last_commit_sha = repo_data.get("last_commit_sha")
        
        # Получаем последние коммиты
        commits = await github_client.get_commits(owner, repo, per_page=10)
        if not commits:
            return
        
        # Если это первый раз, сохраняем SHA и не отправляем уведомление
        if not last_commit_sha:
            await update_last_commit_sha(repo_key, commits[0].get("sha", ""))
            return
        
        # Находим новые коммиты
        new_commits = []
        for commit in commits:
            if commit.get("sha") == last_commit_sha:
                break
            new_commits.append(commit)
        
        if new_commits:
            # Получаем информацию о ветке
            repo_info = await github_client.get_repository_info(owner, repo)
            default_branch = repo_info.get("default_branch", "main") if repo_info else "main"
            
            text = format_commit_message(repo_key, default_branch, new_commits)
            await self.bot.send_message(chat_id=chat_id, text=text)
            
            # Обновляем SHA последнего коммита
            await update_last_commit_sha(repo_key, new_commits[0].get("sha", ""))
    
    async def _check_stars(
        self,
        github_client: GitHubClient,
        repo_key: str,
        owner: str,
        repo: str,
        chat_id: int,
        repo_data: Dict[str, Any]
    ) -> None:
        """Проверяет новые звезды"""
        last_star_count = repo_data.get("last_star_count", 0)
        
        # Получаем текущее количество звезд
        current_star_count = await github_client.get_star_count(owner, repo)
        
        if current_star_count > last_star_count:
            # Получаем информацию о последнем пользователе, поставившем звезду
            stargazers = await github_client.get_stargazers(owner, repo, per_page=1)
            
            if stargazers:
                user = stargazers[0]
                user_login = user.get("login")
                user_name = user.get("name")
                
                text = format_star_message(repo_key, user_login, user_name, current_star_count)
                await self.bot.send_message(chat_id=chat_id, text=text)
            
            # Обновляем количество звезд
            await update_last_star_count(repo_key, current_star_count)
    
    async def _check_forks(
        self,
        github_client: GitHubClient,
        repo_key: str,
        owner: str,
        repo: str,
        chat_id: int,
        repo_data: Dict[str, Any]
    ) -> None:
        """Проверяет новые форки"""
        # Получаем последние форки
        forks = await github_client.get_forks(owner, repo, per_page=5)
        
        if forks:
            # Здесь можно добавить логику отслеживания последнего форка
            # Для простоты пропускаем, так как это требует дополнительного хранения
            pass
    
    async def _check_issues(
        self,
        github_client: GitHubClient,
        repo_key: str,
        owner: str,
        repo: str,
        chat_id: int,
        issues_config: Dict[str, bool]
    ) -> None:
        """Проверяет новые issues"""
        # Получаем открытые issues
        issues = await github_client.get_issues(owner, repo, state="open", per_page=10)
        
        for issue in issues:
            # Проверяем, нужно ли отслеживать это действие
            # Для polling мы проверяем только открытые issues
            if issues_config.get("opened", False):
                # Здесь можно добавить логику проверки новых issues
                # Для простоты пропускаем, так как это требует дополнительного хранения
                pass
    
    async def _check_pull_requests(
        self,
        github_client: GitHubClient,
        repo_key: str,
        owner: str,
        repo: str,
        chat_id: int,
        pr_config: Dict[str, bool]
    ) -> None:
        """Проверяет новые pull requests"""
        # Получаем открытые PR
        prs = await github_client.get_pull_requests(owner, repo, state="open", per_page=10)
        
        for pr in prs:
            # Проверяем, нужно ли отслеживать это действие
            # Для polling мы проверяем только открытые PR
            if pr_config.get("opened", False):
                # Здесь можно добавить логику проверки новых PR
                # Для простоты пропускаем, так как это требует дополнительного хранения
                pass

