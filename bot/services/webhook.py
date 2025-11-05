import logging
import hmac
import hashlib
import json
from typing import Dict, Any, Optional
from aiohttp import web
from aiogram import Bot

from bot.services.database import (
    get_all_repositories,
    get_repository,
    update_last_commit_sha,
    update_last_star_count
)
from bot.services.formatter import (
    format_commit_message,
    format_star_message,
    format_fork_message,
    format_issue_message,
    format_issue_comment_message,
    format_pull_request_message,
    format_pull_request_comment_message,
    format_release_message
)

logger = logging.getLogger(__name__)


def verify_webhook_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """Проверяет подпись webhook от GitHub"""
    if not secret:
        return True  # Если секрет не установлен, пропускаем проверку
    
    expected_signature = hmac.new(
        secret.encode(),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected_signature}", signature)


async def handle_webhook(request: web.Request, bot: Bot, webhook_secret: str) -> web.Response:
    """Обработчик webhook от GitHub"""
    try:
        # Получаем заголовки
        signature = request.headers.get("X-Hub-Signature-256", "")
        event_type = request.headers.get("X-GitHub-Event", "")
        
        # Читаем тело запроса
        payload_body = await request.read()
        
        # Проверяем подпись
        if not verify_webhook_signature(payload_body, signature, webhook_secret):
            logger.warning("Неверная подпись webhook")
            return web.Response(status=401, text="Invalid signature")
        
        # Парсим JSON
        payload = json.loads(payload_body.decode())
        
        # Обрабатываем событие
        repo_full_name = payload.get("repository", {}).get("full_name", "")
        if not repo_full_name:
            return web.Response(status=400, text="No repository found")
        
        # Получаем все репозитории
        repos = await get_all_repositories()
        repo_data = repos.get(repo_full_name)
        
        if not repo_data:
            logger.info(f"Репозиторий {repo_full_name} не отслеживается")
            return web.Response(status=200, text="Repository not tracked")
        
        events_config = repo_data.get("events", {})
        chat_id = repo_data.get("chat_id")
        
        # Обрабатываем разные типы событий
        if event_type == "push" and events_config.get("commits", False):
            await handle_push_event(bot, chat_id, repo_full_name, payload, events_config)
        
        elif event_type == "watch" and events_config.get("watch", False):
            await handle_watch_event(bot, chat_id, repo_full_name, payload, events_config)
        
        elif event_type == "fork" and events_config.get("forks", False):
            await handle_fork_event(bot, chat_id, repo_full_name, payload, events_config)
        
        elif event_type == "issues":
            action = payload.get("action", "")
            issues_config = events_config.get("issues", {})
            if issues_config.get(action, False):
                await handle_issue_event(bot, chat_id, repo_full_name, payload, events_config)
        
        elif event_type == "issue_comment":
            action = payload.get("action", "")
            issue_comments_config = events_config.get("issue_comments", {})
            if issue_comments_config.get(action, False):
                await handle_issue_comment_event(bot, chat_id, repo_full_name, payload, events_config)
        
        elif event_type == "pull_request":
            action = payload.get("action", "")
            pr_config = events_config.get("pull_requests", {})
            if pr_config.get(action, False):
                await handle_pull_request_event(bot, chat_id, repo_full_name, payload, events_config)
        
        elif event_type == "pull_request_review_comment":
            action = payload.get("action", "")
            pr_comments_config = events_config.get("pull_request_comments", {})
            if pr_comments_config.get(action, False):
                await handle_pull_request_comment_event(bot, chat_id, repo_full_name, payload, events_config)
        
        elif event_type == "release":
            action = payload.get("action", "")
            releases_config = events_config.get("releases", {})
            if releases_config.get(action, False):
                await handle_release_event(bot, chat_id, repo_full_name, payload, events_config)
        
        return web.Response(status=200, text="OK")
    
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}", exc_info=True)
        return web.Response(status=500, text=f"Error: {str(e)}")


async def handle_push_event(
    bot: Bot,
    chat_id: int,
    repo_full_name: str,
    payload: Dict[str, Any],
    events_config: Dict[str, Any]
) -> None:
    """Обрабатывает событие push (коммиты)"""
    commits = payload.get("commits", [])
    if not commits:
        return
    
    branch = payload.get("ref", "").replace("refs/heads/", "")
    compare_url = payload.get("compare", "")
    
    text = format_commit_message(repo_full_name, branch, commits, compare_url)
    await bot.send_message(chat_id=chat_id, text=text)
    
    # Обновляем SHA последнего коммита
    if commits:
        last_commit_sha = commits[0].get("id", "")
        await update_last_commit_sha(repo_full_name, last_commit_sha)


async def handle_watch_event(
    bot: Bot,
    chat_id: int,
    repo_full_name: str,
    payload: Dict[str, Any],
    events_config: Dict[str, Any]
) -> None:
    """Обрабатывает событие watch (звезды)"""
    sender = payload.get("sender", {})
    user_login = sender.get("login")
    user_name = sender.get("name")
    
    repository = payload.get("repository", {})
    stargazers_count = repository.get("stargazers_count", 0)
    
    text = format_star_message(repo_full_name, user_login, user_name, stargazers_count)
    await bot.send_message(chat_id=chat_id, text=text)
    
    # Обновляем количество звезд
    await update_last_star_count(repo_full_name, stargazers_count)


async def handle_fork_event(
    bot: Bot,
    chat_id: int,
    repo_full_name: str,
    payload: Dict[str, Any],
    events_config: Dict[str, Any]
) -> None:
    """Обрабатывает событие fork"""
    fork = payload.get("forkee", {})
    fork_owner = fork.get("owner", {}).get("login", "")
    fork_full_name = fork.get("full_name", "")
    
    text = format_fork_message(repo_full_name, fork_owner, fork_full_name)
    await bot.send_message(chat_id=chat_id, text=text)


async def handle_issue_event(
    bot: Bot,
    chat_id: int,
    repo_full_name: str,
    payload: Dict[str, Any],
    events_config: Dict[str, Any]
) -> None:
    """Обрабатывает событие issue"""
    action = payload.get("action", "")
    issue = payload.get("issue", {})
    
    text = format_issue_message(repo_full_name, action, issue)
    await bot.send_message(chat_id=chat_id, text=text)


async def handle_issue_comment_event(
    bot: Bot,
    chat_id: int,
    repo_full_name: str,
    payload: Dict[str, Any],
    events_config: Dict[str, Any]
) -> None:
    """Обрабатывает событие комментария к issue"""
    action = payload.get("action", "")
    comment = payload.get("comment", {})
    issue = payload.get("issue", {})
    
    text = format_issue_comment_message(repo_full_name, action, comment, issue)
    await bot.send_message(chat_id=chat_id, text=text)


async def handle_pull_request_event(
    bot: Bot,
    chat_id: int,
    repo_full_name: str,
    payload: Dict[str, Any],
    events_config: Dict[str, Any]
) -> None:
    """Обрабатывает событие pull request"""
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    
    text = format_pull_request_message(repo_full_name, action, pr)
    await bot.send_message(chat_id=chat_id, text=text)


async def handle_pull_request_comment_event(
    bot: Bot,
    chat_id: int,
    repo_full_name: str,
    payload: Dict[str, Any],
    events_config: Dict[str, Any]
) -> None:
    """Обрабатывает событие комментария к pull request"""
    action = payload.get("action", "")
    comment = payload.get("comment", {})
    pr = payload.get("pull_request", {})
    
    text = format_pull_request_comment_message(repo_full_name, action, comment, pr)
    await bot.send_message(chat_id=chat_id, text=text)


async def handle_release_event(
    bot: Bot,
    chat_id: int,
    repo_full_name: str,
    payload: Dict[str, Any],
    events_config: Dict[str, Any]
) -> None:
    """Обрабатывает событие release"""
    action = payload.get("action", "")
    release = payload.get("release", {})
    
    text = format_release_message(repo_full_name, action, release)
    await bot.send_message(chat_id=chat_id, text=text)


def create_webhook_app(bot: Bot, webhook_secret: str, webhook_path: str) -> web.Application:
    """Создает aiohttp приложение для обработки webhook"""
    app = web.Application()
    
    async def webhook_handler(request: web.Request) -> web.Response:
        return await handle_webhook(request, bot, webhook_secret)
    
    app.router.add_post(webhook_path, webhook_handler)
    
    return app

