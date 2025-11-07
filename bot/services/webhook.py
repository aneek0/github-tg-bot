import logging
import hmac
import hashlib
import json
from typing import Dict, Any, Optional
from aiohttp import web
from aiogram import Bot

from bot.services.database import (
    get_repositories_by_repo_key,
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
        
        # Получаем все репозитории для данного repo_key (всех пользователей)
        repos = await get_repositories_by_repo_key(repo_full_name)
        
        if not repos:
            logger.info(f"Репозиторий {repo_full_name} не отслеживается")
            return web.Response(status=200, text="Repository not tracked")
        
        # Обрабатываем разные типы событий для всех пользователей
        if event_type == "push":
            await handle_push_event_for_all_users(bot, repos, repo_full_name, payload)
        
        elif event_type == "watch":
            await handle_watch_event_for_all_users(bot, repos, repo_full_name, payload)
        
        elif event_type == "fork":
            await handle_fork_event_for_all_users(bot, repos, repo_full_name, payload)
        
        elif event_type == "issues":
            await handle_issue_event_for_all_users(bot, repos, repo_full_name, payload)
        
        elif event_type == "issue_comment":
            await handle_issue_comment_event_for_all_users(bot, repos, repo_full_name, payload)
        
        elif event_type == "pull_request":
            await handle_pull_request_event_for_all_users(bot, repos, repo_full_name, payload)
        
        elif event_type == "pull_request_review_comment":
            await handle_pull_request_comment_event_for_all_users(bot, repos, repo_full_name, payload)
        
        elif event_type == "release":
            await handle_release_event_for_all_users(bot, repos, repo_full_name, payload)
        
        return web.Response(status=200, text="OK")
    
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}", exc_info=True)
        return web.Response(status=500, text=f"Error: {str(e)}")


async def handle_push_event_for_all_users(
    bot: Bot,
    repos: Dict[str, Dict[str, Any]],
    repo_full_name: str,
    payload: Dict[str, Any]
) -> None:
    """Обрабатывает событие push (коммиты) для всех пользователей"""
    commits = payload.get("commits", [])
    if not commits:
        return
    
    branch = payload.get("ref", "").replace("refs/heads/", "")
    compare_url = payload.get("compare", "")
    
    text = format_commit_message(repo_full_name, branch, commits, compare_url)
    
    # Отправляем уведомление всем пользователям, у которых включены коммиты
    for repo_data in repos.values():
        events_config = repo_data.get("events", {})
        if events_config.get("commits", False):
            chat_id = repo_data.get("chat_id")
            thread_id = repo_data.get("thread_id")
            try:
                # Используем message_thread_id если он есть (для групп с топиками)
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    message_thread_id=thread_id
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {chat_id}: {e}")
    
    # Обновляем SHA последнего коммита
    if commits:
        last_commit_sha = commits[0].get("id", "")
        await update_last_commit_sha(repo_full_name, last_commit_sha)


async def handle_watch_event_for_all_users(
    bot: Bot,
    repos: Dict[str, Dict[str, Any]],
    repo_full_name: str,
    payload: Dict[str, Any]
) -> None:
    """Обрабатывает событие watch (звезды) для всех пользователей"""
    sender = payload.get("sender", {})
    user_login = sender.get("login")
    user_name = sender.get("name")
    
    repository = payload.get("repository", {})
    stargazers_count = repository.get("stargazers_count", 0)
    
    text = format_star_message(repo_full_name, user_login, user_name, stargazers_count)
    
    # Отправляем уведомление всем пользователям, у которых включены звезды
    for repo_data in repos.values():
        events_config = repo_data.get("events", {})
        if events_config.get("watch", False):
            chat_id = repo_data.get("chat_id")
            thread_id = repo_data.get("thread_id")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    message_thread_id=thread_id
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {chat_id}: {e}")
    
    # Обновляем количество звезд
    await update_last_star_count(repo_full_name, stargazers_count)


async def handle_fork_event_for_all_users(
    bot: Bot,
    repos: Dict[str, Dict[str, Any]],
    repo_full_name: str,
    payload: Dict[str, Any]
) -> None:
    """Обрабатывает событие fork для всех пользователей"""
    fork = payload.get("forkee", {})
    fork_owner = fork.get("owner", {}).get("login", "")
    fork_full_name = fork.get("full_name", "")
    
    text = format_fork_message(repo_full_name, fork_owner, fork_full_name)
    
    # Отправляем уведомление всем пользователям, у которых включены форки
    for repo_data in repos.values():
        events_config = repo_data.get("events", {})
        if events_config.get("forks", False):
            chat_id = repo_data.get("chat_id")
            thread_id = repo_data.get("thread_id")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    message_thread_id=thread_id
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {chat_id}: {e}")


async def handle_issue_event_for_all_users(
    bot: Bot,
    repos: Dict[str, Dict[str, Any]],
    repo_full_name: str,
    payload: Dict[str, Any]
) -> None:
    """Обрабатывает событие issue для всех пользователей"""
    action = payload.get("action", "")
    issue = payload.get("issue", {})
    
    text = format_issue_message(repo_full_name, action, issue)
    
    # Отправляем уведомление всем пользователям, у которых включено это событие
    for repo_data in repos.values():
        events_config = repo_data.get("events", {})
        issues_config = events_config.get("issues", {})
        if issues_config.get(action, False):
            chat_id = repo_data.get("chat_id")
            thread_id = repo_data.get("thread_id")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    message_thread_id=thread_id
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {chat_id}: {e}")


async def handle_issue_comment_event_for_all_users(
    bot: Bot,
    repos: Dict[str, Dict[str, Any]],
    repo_full_name: str,
    payload: Dict[str, Any]
) -> None:
    """Обрабатывает событие комментария к issue для всех пользователей"""
    action = payload.get("action", "")
    comment = payload.get("comment", {})
    issue = payload.get("issue", {})
    
    text = format_issue_comment_message(repo_full_name, action, comment, issue)
    
    # Отправляем уведомление всем пользователям, у которых включено это событие
    for repo_data in repos.values():
        events_config = repo_data.get("events", {})
        issue_comments_config = events_config.get("issue_comments", {})
        if issue_comments_config.get(action, False):
            chat_id = repo_data.get("chat_id")
            thread_id = repo_data.get("thread_id")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    message_thread_id=thread_id
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {chat_id}: {e}")


async def handle_pull_request_event_for_all_users(
    bot: Bot,
    repos: Dict[str, Dict[str, Any]],
    repo_full_name: str,
    payload: Dict[str, Any]
) -> None:
    """Обрабатывает событие pull request для всех пользователей"""
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    
    text = format_pull_request_message(repo_full_name, action, pr)
    
    # Отправляем уведомление всем пользователям, у которых включено это событие
    for repo_data in repos.values():
        events_config = repo_data.get("events", {})
        pr_config = events_config.get("pull_requests", {})
        if pr_config.get(action, False):
            chat_id = repo_data.get("chat_id")
            thread_id = repo_data.get("thread_id")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    message_thread_id=thread_id
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {chat_id}: {e}")


async def handle_pull_request_comment_event_for_all_users(
    bot: Bot,
    repos: Dict[str, Dict[str, Any]],
    repo_full_name: str,
    payload: Dict[str, Any]
) -> None:
    """Обрабатывает событие комментария к pull request для всех пользователей"""
    action = payload.get("action", "")
    comment = payload.get("comment", {})
    pr = payload.get("pull_request", {})
    
    text = format_pull_request_comment_message(repo_full_name, action, comment, pr)
    
    # Отправляем уведомление всем пользователям, у которых включено это событие
    for repo_data in repos.values():
        events_config = repo_data.get("events", {})
        pr_comments_config = events_config.get("pull_request_comments", {})
        if pr_comments_config.get(action, False):
            chat_id = repo_data.get("chat_id")
            thread_id = repo_data.get("thread_id")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    message_thread_id=thread_id
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {chat_id}: {e}")


async def handle_release_event_for_all_users(
    bot: Bot,
    repos: Dict[str, Dict[str, Any]],
    repo_full_name: str,
    payload: Dict[str, Any]
) -> None:
    """Обрабатывает событие release для всех пользователей"""
    action = payload.get("action", "")
    release = payload.get("release", {})
    
    text = format_release_message(repo_full_name, action, release)
    
    # Отправляем уведомление всем пользователям, у которых включено это событие
    for repo_data in repos.values():
        events_config = repo_data.get("events", {})
        releases_config = events_config.get("releases", {})
        if releases_config.get(action, False):
            chat_id = repo_data.get("chat_id")
            thread_id = repo_data.get("thread_id")
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    message_thread_id=thread_id
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю {chat_id}: {e}")


def create_webhook_app(bot: Bot, webhook_secret: str, github_webhook_path: str = "/webhook/github") -> web.Application:
    """Создает aiohttp приложение для обработки GitHub webhook"""
    app = web.Application()
    
    async def github_webhook_handler(request: web.Request) -> web.Response:
        return await handle_webhook(request, bot, webhook_secret)
    
    app.router.add_post(github_webhook_path, github_webhook_handler)
    
    return app

