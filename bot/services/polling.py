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
        
        # Группируем репозитории по repo_key, чтобы не проверять один репозиторий несколько раз
        repos_by_key: Dict[str, list] = {}
        for storage_key, repo_data in repos.items():
            repo_key = repo_data.get("repo_key", storage_key.split(":")[0])
            if repo_key not in repos_by_key:
                repos_by_key[repo_key] = []
            repos_by_key[repo_key].append(repo_data)
        
        # Проверяем каждый уникальный репозиторий один раз
        for repo_key, repo_data_list in repos_by_key.items():
            try:
                # Используем первый репозиторий для проверки (все они имеют одинаковый repo_key)
                # Но отправляем уведомления всем пользователям
                await self._check_repository(repo_key, repo_data_list)
                # Добавляем задержку между проверками репозиториев
                # чтобы не превысить rate limit
                await asyncio.sleep(DELAY_BETWEEN_REPO_CHECKS)  # Увеличил до 2 секунд
            except Exception as e:
                logger.error(f"Ошибка проверки репозитория {repo_key}: {e}")
                # Задержка даже при ошибке
                await asyncio.sleep(DELAY_BETWEEN_REPO_CHECKS)
    
    async def _check_repository(self, repo_key: str, repo_data_list: list) -> None:
        """Проверяет конкретный репозиторий на изменения для всех пользователей"""
        owner, repo = repo_key.split("/", 1)
        
        # Используем токен из первого репозитория или глобальный из .env
        first_repo_data = repo_data_list[0]
        repo_token = first_repo_data.get("github_token")
        # Проверяем что токен не пустой (не None и не пустая строка)
        github_token = repo_token if repo_token and repo_token.strip() else GITHUB_TOKEN
        
        # Логируем для отладки
        if not github_token or not github_token.strip():
            logger.error(f"⚠️ ВНИМАНИЕ! Для репозитория {repo_key} токен не найден! repo_token={repo_token}, env_token={bool(GITHUB_TOKEN)}")
        
        github_client = GitHubClient(github_token)
        
        # Проверяем коммиты для всех пользователей
        await self._check_commits_for_all_users(github_client, repo_key, owner, repo, repo_data_list)
        
        # Проверяем звезды для всех пользователей
        await self._check_stars_for_all_users(github_client, repo_key, owner, repo, repo_data_list)
        
        # Проверяем форки для всех пользователей
        await self._check_forks_for_all_users(github_client, repo_key, owner, repo, repo_data_list)
        
        # Проверяем issues для всех пользователей
        await self._check_issues_for_all_users(github_client, repo_key, owner, repo, repo_data_list)
        
        # Проверяем pull requests для всех пользователей
        await self._check_pull_requests_for_all_users(github_client, repo_key, owner, repo, repo_data_list)
        
        # Обновляем статистику
        stats = await github_client.get_statistics(owner, repo)
        await update_statistics(repo_key, stats)
    
    async def _check_commits_for_all_users(
        self,
        github_client: GitHubClient,
        repo_key: str,
        owner: str,
        repo: str,
        repo_data_list: list
    ) -> None:
        """Проверяет новые коммиты для всех пользователей"""
        # Используем last_commit_sha из первого репозитория (они должны быть одинаковыми)
        first_repo_data = repo_data_list[0]
        last_commit_sha = first_repo_data.get("last_commit_sha")
        
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
            
            # Отправляем уведомление всем пользователям, у которых включены коммиты
            for repo_data in repo_data_list:
                events_config = repo_data.get("events", {})
                if events_config.get("commits", False):
                    chat_id = repo_data.get("chat_id")
                    thread_id = repo_data.get("thread_id")
                    try:
                        await self.bot.send_message(
                            chat_id=chat_id,
                            text=text,
                            message_thread_id=thread_id
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки сообщения пользователю {chat_id}: {e}")
            
            # Обновляем SHA последнего коммита
            await update_last_commit_sha(repo_key, new_commits[0].get("sha", ""))
    
    async def _check_stars_for_all_users(
        self,
        github_client: GitHubClient,
        repo_key: str,
        owner: str,
        repo: str,
        repo_data_list: list
    ) -> None:
        """Проверяет новые звезды для всех пользователей"""
        # Используем last_star_count из первого репозитория (они должны быть одинаковыми)
        first_repo_data = repo_data_list[0]
        last_star_count = first_repo_data.get("last_star_count", 0)
        
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
                
                # Отправляем уведомление всем пользователям, у которых включены звезды
                for repo_data in repo_data_list:
                    events_config = repo_data.get("events", {})
                    if events_config.get("watch", False):
                        chat_id = repo_data.get("chat_id")
                        thread_id = repo_data.get("thread_id")
                        try:
                            await self.bot.send_message(
                                chat_id=chat_id,
                                text=text,
                                message_thread_id=thread_id
                            )
                        except Exception as e:
                            logger.error(f"Ошибка отправки сообщения пользователю {chat_id}: {e}")
            
            # Обновляем количество звезд
            await update_last_star_count(repo_key, current_star_count)
    
    async def _check_forks_for_all_users(
        self,
        github_client: GitHubClient,
        repo_key: str,
        owner: str,
        repo: str,
        repo_data_list: list
    ) -> None:
        """Проверяет новые форки для всех пользователей"""
        # Получаем последние форки
        forks = await github_client.get_forks(owner, repo, per_page=5)
        
        if forks:
            # Здесь можно добавить логику отслеживания последнего форка
            # Для простоты пропускаем, так как это требует дополнительного хранения
            pass
    
    async def _check_issues_for_all_users(
        self,
        github_client: GitHubClient,
        repo_key: str,
        owner: str,
        repo: str,
        repo_data_list: list
    ) -> None:
        """Проверяет новые issues для всех пользователей"""
        # Получаем открытые issues
        issues = await github_client.get_issues(owner, repo, state="open", per_page=10)
        
        for issue in issues:
            # Проверяем, нужно ли отслеживать это действие
            # Для polling мы проверяем только открытые issues
            # Здесь можно добавить логику проверки новых issues
            # Для простоты пропускаем, так как это требует дополнительного хранения
            pass
    
    async def _check_pull_requests_for_all_users(
        self,
        github_client: GitHubClient,
        repo_key: str,
        owner: str,
        repo: str,
        repo_data_list: list
    ) -> None:
        """Проверяет новые pull requests для всех пользователей"""
        # Получаем открытые PR
        prs = await github_client.get_pull_requests(owner, repo, state="open", per_page=10)
        
        for pr in prs:
            # Проверяем, нужно ли отслеживать это действие
            # Для polling мы проверяем только открытые PR
            # Здесь можно добавить логику проверки новых PR
            # Для простоты пропускаем, так как это требует дополнительного хранения
            pass

