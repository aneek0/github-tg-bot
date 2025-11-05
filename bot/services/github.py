import aiohttp
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from bot.utils.constants import (
    RATE_LIMIT_WITH_TOKEN,
    RATE_LIMIT_WITHOUT_TOKEN,
    RATE_LIMIT_WAIT_THRESHOLD
)

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

# Глобальная переменная для хранения функции отправки сообщений о rate limit
_rate_limit_notifier: Optional[Callable[[str], None]] = None
# Глобальная переменная для хранения bot для отправки сообщений
_global_bot = None


def set_rate_limit_notifier(notifier: Callable[[str], None]):
    """Устанавливает функцию для отправки уведомлений о rate limit"""
    global _rate_limit_notifier
    _rate_limit_notifier = notifier


def set_global_bot(bot):
    """Устанавливает глобальный bot для отправки сообщений о rate limit"""
    global _global_bot
    _global_bot = bot


async def _send_rate_limit_notification(message: str):
    """Отправляет уведомление о rate limit через глобальный bot всем пользователям с репозиториями"""
    global _global_bot
    if not _global_bot:
        return
    
    try:
        from bot.services.database import get_all_repositories
        repos = await get_all_repositories()
        # Получаем уникальные chat_id
        chat_ids = set(repo_data.get("chat_id") for repo_data in repos.values() if repo_data.get("chat_id"))
        
        for chat_id in chat_ids:
            try:
                await _global_bot.send_message(chat_id=chat_id, text=message)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о rate limit пользователю {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей для уведомления о rate limit: {e}")


class GitHubClient:
    """Клиент для работы с GitHub API"""
    
    def __init__(self, token: Optional[str] = None, token_manager=None):
        # Проверяем что токен не пустой (не None и не пустая строка)
        self.token = token if token and token.strip() else None
        self.token_manager = token_manager
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Telegram-Bot"
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
            self._rate_limit_remaining = RATE_LIMIT_WITH_TOKEN
            logger.debug(f"GitHubClient инициализирован с токеном (лимит {RATE_LIMIT_WITH_TOKEN}/час), токен: {self.token[:10]}...")
        else:
            self._rate_limit_remaining = RATE_LIMIT_WITHOUT_TOKEN
            logger.warning(f"GitHubClient инициализирован БЕЗ токена (лимит {RATE_LIMIT_WITHOUT_TOKEN}/час)! Переданный токен был пустым или None.")
        self._rate_limit_reset = 0  # Время сброса rate limit
    
    async def _request(self, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Выполняет HTTP запрос к GitHub API"""
        import asyncio
        import time
        
        # Проверяем, не нужно ли ждать сброса rate limit
        current_time = int(time.time())
        if self._rate_limit_remaining == 0 and self._rate_limit_reset > current_time:
            wait_time = self._rate_limit_reset - current_time
            if wait_time > 0:
                # Если ждать больше порога, просто возвращаем None вместо ожидания
                if wait_time > RATE_LIMIT_WAIT_THRESHOLD:
                    wait_minutes = wait_time // 60
                    token_status = "с токеном" if self.token else "без токена"
                    if not self.token:
                        logger.warning(
                            f"⏸️ Rate limit исчерпан ({token_status}). Пропускаем запрос. "
                            f"Сброс через {wait_minutes} минут. "
                            f"💡 Добавьте GITHUB_TOKEN в .env для увеличения лимита до 5000/час!"
                        )
                    else:
                        logger.warning(
                            f"⏸️ Rate limit исчерпан ({token_status}). Пропускаем запрос. "
                            f"Сброс через {wait_minutes} минут."
                        )
                    return None
                else:
                    wait_minutes = wait_time // 60
                    wait_seconds = wait_time % 60
                    logger.warning(
                        f"⏳ Rate limit исчерпан. Ожидание {wait_minutes}м {wait_seconds}с до сброса..."
                    )
                    await asyncio.sleep(wait_time + 1)
                    logger.info("✅ Rate limit сброшен, продолжаем")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    url,
                    headers=self.headers,
                    **kwargs
                ) as response:
                    # Обновляем информацию о rate limit из заголовков
                    rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
                    rate_limit_reset = response.headers.get("X-RateLimit-Reset")
                    rate_limit_total = response.headers.get("X-RateLimit-Limit", str(RATE_LIMIT_WITH_TOKEN))
                    
                    if rate_limit_remaining is not None:
                        try:
                            old_remaining = self._rate_limit_remaining
                            self._rate_limit_remaining = int(rate_limit_remaining)
                            
                            # Обновляем статистику в менеджере токенов
                            if self.token_manager and self.token:
                                self.token_manager.update_token_stats(
                                    self.token,
                                    self._rate_limit_remaining,
                                    self._rate_limit_reset if rate_limit_reset else None,
                                    int(rate_limit_total) if rate_limit_total else None
                                )
                            
                            # Логируем изменение rate limit если осталось мало
                            if self._rate_limit_remaining < 100 and old_remaining >= 100:
                                logger.warning(
                                    f"⚠️ Rate limit: осталось {self._rate_limit_remaining}/{rate_limit_total} запросов!"
                                )
                            elif self._rate_limit_remaining == 0:
                                token_info = "с токеном" if self.token else "без токена"
                                logger.error(
                                    f"🚫 Rate limit исчерпан! Осталось 0/{rate_limit_total} запросов ({token_info})"
                                )
                        except (ValueError, TypeError):
                            pass
                    
                    if rate_limit_reset is not None:
                        try:
                            self._rate_limit_reset = int(rate_limit_reset)
                            # Обновляем статистику в менеджере токенов
                            if self.token_manager and self.token:
                                self.token_manager.update_token_stats(
                                    self.token,
                                    None,
                                    self._rate_limit_reset,
                                    None
                                )
                        except (ValueError, TypeError):
                            pass
                    
                    # Проверяем rate limit
                    if response.status == 403:
                        error_text = await response.text()
                        
                        # Проверяем, не rate limit ли это
                        if self._rate_limit_remaining == 0 and self._rate_limit_reset > current_time:
                            wait_time = self._rate_limit_reset - current_time
                            if wait_time > 0:
                                # Форматируем время ожидания
                                wait_hours = wait_time // 3600
                                wait_minutes = (wait_time % 3600) // 60
                                wait_seconds = wait_time % 60
                                
                                if wait_hours > 0:
                                    wait_str = f"{wait_hours}ч {wait_minutes}м"
                                elif wait_minutes > 0:
                                    wait_str = f"{wait_minutes}м {wait_seconds}с"
                                else:
                                    wait_str = f"{wait_seconds}с"
                                
                                # Форматируем время сброса
                                reset_time = datetime.fromtimestamp(self._rate_limit_reset)
                                reset_str = reset_time.strftime("%H:%M:%S")
                                
                                # Если ждать больше порога, пытаемся переключиться на другой токен или возвращаем None
                                if wait_time > RATE_LIMIT_WAIT_THRESHOLD:
                                    # Пытаемся переключиться на другой токен через менеджер
                                    if self.token_manager:
                                        self.token_manager.switch_to_next_token()
                                        # Пробуем повторить запрос с новым токеном
                                        new_token = self.token_manager.get_current_token()
                                        if new_token and new_token != self.token:
                                            logger.info(f"🔄 Переключение на другой токен после rate limit")
                                            self.token = new_token
                                            self.headers["Authorization"] = f"token {self.token}"
                                            # Повторяем запрос с новым токеном
                                            return await self._request(method, url, **kwargs)
                                    
                                    token_status = "с токеном" if self.token else "без токена"
                                    error_msg = (
                                        f"🚫 Rate limit исчерпан ({token_status})!\n\n"
                                        f"⏰ Сброс через: {wait_str}\n"
                                        f"🕐 Время сброса: {reset_str}\n\n"
                                        f"💡 Можно добавить несколько токенов в .env через запятую для автоматического переключения."
                                    )
                                    
                                    if not self.token:
                                        error_msg += "\n\n💡 Добавьте GITHUB_TOKEN в .env для увеличения лимита до 5000/час!"
                                    
                                    logger.error(error_msg)
                                    
                                    # Отправляем уведомление пользователю если есть функция или глобальный bot
                                    if _rate_limit_notifier:
                                        try:
                                            _rate_limit_notifier(error_msg)
                                        except Exception as e:
                                            logger.error(f"Ошибка отправки уведомления о rate limit: {e}")
                                    elif _global_bot:
                                        # Создаем задачу для асинхронной отправки уведомлений
                                        import asyncio
                                        try:
                                            asyncio.create_task(_send_rate_limit_notification(error_msg))
                                        except Exception as e:
                                            logger.error(f"Ошибка создания задачи для отправки уведомления о rate limit: {e}")
                                    
                                    return None
                                else:
                                    wait_minutes = wait_time // 60
                                    wait_seconds = wait_time % 60
                                    logger.warning(
                                        f"⏳ Rate limit превышен. Ожидание {wait_minutes}м {wait_seconds}с..."
                                    )
                                    await asyncio.sleep(wait_time + 1)
                                    logger.info("✅ Rate limit сброшен, продолжаем")
                                    # Повторяем запрос после ожидания
                                    return await self._request(method, url, **kwargs)
                        
                        # Проверяем, не слишком ли большой репозиторий (для contributors и т.д.)
                        if "too large" in error_text.lower() or "history" in error_text.lower():
                            logger.debug(f"Repository too large for this endpoint: {url}")
                            return None  # Возвращаем None вместо ошибки
                        
                        logger.error(f"403 Forbidden: {error_text}")
                        return None
                    
                    if response.status == 404:
                        return None
                    
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка запроса к GitHub API: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            return None
    
    async def get_repository_info(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о репозитории"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
        return await self._request("GET", url)
    
    async def get_commits(
        self,
        owner: str,
        repo: str,
        branch: str = "main",
        since: Optional[str] = None,
        per_page: int = 10
    ) -> List[Dict[str, Any]]:
        """Получает список коммитов"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits"
        params = {"sha": branch, "per_page": per_page}
        if since:
            params["since"] = since
        
        result = await self._request("GET", url, params=params)
        return result if result else []
    
    async def get_commit_details(self, owner: str, repo: str, sha: str) -> Optional[Dict[str, Any]]:
        """Получает детальную информацию о коммите"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{sha}"
        return await self._request("GET", url)
    
    async def get_stargazers(
        self,
        owner: str,
        repo: str,
        per_page: int = 1
    ) -> List[Dict[str, Any]]:
        """Получает список пользователей, поставивших звезду"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/stargazers"
        params = {"per_page": per_page}
        
        result = await self._request("GET", url, params=params)
        return result if result else []
    
    async def get_star_count(self, owner: str, repo: str) -> int:
        """Получает количество звезд репозитория"""
        repo_info = await self.get_repository_info(owner, repo)
        if repo_info:
            return repo_info.get("stargazers_count", 0)
        return 0
    
    async def get_issues(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        per_page: int = 10
    ) -> List[Dict[str, Any]]:
        """Получает список issues"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"
        params = {"state": state, "per_page": per_page}
        
        result = await self._request("GET", url, params=params)
        return result if result else []
    
    async def get_issue_details(self, owner: str, repo: str, issue_number: int) -> Optional[Dict[str, Any]]:
        """Получает детальную информацию об issue"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}"
        return await self._request("GET", url)
    
    async def get_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        per_page: int = 10
    ) -> List[Dict[str, Any]]:
        """Получает список pull requests"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls"
        params = {"state": state, "per_page": per_page}
        
        result = await self._request("GET", url, params=params)
        return result if result else []
    
    async def get_pull_request_details(self, owner: str, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        """Получает детальную информацию о pull request"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
        return await self._request("GET", url)
    
    async def get_forks(self, owner: str, repo: str, per_page: int = 10) -> List[Dict[str, Any]]:
        """Получает список форков"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/forks"
        params = {"per_page": per_page}
        
        result = await self._request("GET", url, params=params)
        return result if result else []
    
    async def get_releases(self, owner: str, repo: str, per_page: int = 10) -> List[Dict[str, Any]]:
        """Получает список релизов"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/releases"
        params = {"per_page": per_page}
        
        result = await self._request("GET", url, params=params)
        return result if result else []
    
    async def get_contributors(self, owner: str, repo: str, per_page: int = 30) -> List[Dict[str, Any]]:
        """Получает список контрибьюторов
        
        Возвращает пустой список если репозиторий слишком большой
        для получения списка контрибьюторов через API
        """
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contributors"
        params = {"per_page": per_page}
        
        result = await self._request("GET", url, params=params)
        # Если None (ошибка или репозиторий слишком большой), возвращаем пустой список
        return result if result else []
    
    async def get_languages(self, owner: str, repo: str) -> Dict[str, int]:
        """Получает языки программирования репозитория"""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/languages"
        result = await self._request("GET", url)
        return result if result else {}
    
    async def _get_issues_count(self, owner: str, repo: str, state: str) -> int:
        """Получает точное количество issues через Search API"""
        # Используем Search API для получения точного количества
        # Search API возвращает total_count в ответе
        url = f"{GITHUB_API_BASE}/search/issues"
        query = f"repo:{owner}/{repo} is:issue state:{state}"
        params = {"q": query, "per_page": 1}  # Нам нужен только total_count
        
        result = await self._request("GET", url, params=params)
        if result and isinstance(result, dict):
            total_count = result.get("total_count", 0)
            logger.debug(f"Search API для issues ({owner}/{repo}, state={state}): total_count={total_count}")
            return total_count
        logger.warning(f"Search API не вернул результат для issues ({owner}/{repo}, state={state})")
        return 0
    
    async def _get_prs_count(self, owner: str, repo: str, state: str) -> int:
        """Получает точное количество pull requests через Search API"""
        url = f"{GITHUB_API_BASE}/search/issues"
        query = f"repo:{owner}/{repo} is:pr state:{state}"
        params = {"q": query, "per_page": 1}  # Нам нужен только total_count
        
        result = await self._request("GET", url, params=params)
        if result and isinstance(result, dict):
            total_count = result.get("total_count", 0)
            logger.debug(f"Search API для PR ({owner}/{repo}, state={state}): total_count={total_count}")
            return total_count
        logger.warning(f"Search API не вернул результат для PR ({owner}/{repo}, state={state})")
        return 0
    
    async def get_statistics(self, owner: str, repo: str) -> Dict[str, Any]:
        """Получает расширенную статистику репозитория"""
        repo_info = await self.get_repository_info(owner, repo)
        if not repo_info:
            return {}
        
        # Получаем дополнительные данные
        languages = await self.get_languages(owner, repo)
        
        # Получаем точное количество issues и PR через Search API
        issues_open = await self._get_issues_count(owner, repo, "open")
        issues_closed = await self._get_issues_count(owner, repo, "closed")
        prs_open = await self._get_prs_count(owner, repo, "open")
        prs_closed = await self._get_prs_count(owner, repo, "closed")
        
        return {
            "stars": repo_info.get("stargazers_count", 0),
            "forks": repo_info.get("forks_count", 0),
            "commits": 0,  # Будет обновляться отдельно
            "issues": {
                "open": issues_open,
                "closed": issues_closed,
                "total": issues_open + issues_closed
            },
            "pull_requests": {
                "open": prs_open,
                "closed": prs_closed,
                "total": prs_open + prs_closed
            },
            "languages": languages,
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }
    
    def parse_repo_url(self, url: str) -> Optional[tuple]:
        """Парсит GitHub URL и возвращает (owner, repo)"""
        try:
            # Убираем возможные префиксы и суффиксы
            url = url.strip()
            url = url.rstrip("/")
            
            # Убираем .git если есть
            if url.endswith(".git"):
                url = url[:-4]
            
            # Извлекаем owner/repo
            if "github.com" in url:
                parts = url.split("github.com/")
                if len(parts) > 1:
                    repo_part = parts[1].split("/")
                    if len(repo_part) >= 2:
                        return repo_part[0], "/".join(repo_part[1:2])
            elif "/" in url and not url.startswith("http"):
                # Просто owner/repo
                parts = url.split("/")
                if len(parts) >= 2:
                    return parts[0], parts[1]
            
            return None
        except Exception as e:
            logger.error(f"Ошибка парсинга URL: {e}")
            return None

