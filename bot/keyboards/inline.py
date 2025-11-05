import hashlib
from typing import Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData


def get_repo_hash(repo_key: str) -> str:
    """Генерирует короткий хеш для репозитория"""
    return hashlib.md5(repo_key.encode()).hexdigest()[:8]


class SettingsCallback(CallbackData, prefix="set"):
    """Callback для настроек репозитория"""
    action: str
    repo_hash: str  # Короткий хеш вместо полного имени
    event: str = ""


class EventToggleCallback(CallbackData, prefix="evt"):
    """Callback для переключения событий"""
    action: str  # "toggle" или "back"
    repo_hash: str  # Короткий хеш вместо полного имени
    event_path: str = ""  # Путь к событию (например, "commits", "issues.opened")


def get_status_icon(status: bool) -> str:
    """Возвращает иконку статуса"""
    return "✅" if status else "❌"


def build_settings_keyboard(repo_key: str, events: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Строит клавиатуру основных настроек репозитория"""
    builder = InlineKeyboardBuilder()
    repo_hash = get_repo_hash(repo_key)
    
    # Простые события (без вложенности)
    simple_events = ["commits", "forks", "watch"]
    for event in simple_events:
        status = events.get(event, False)
        icon = get_status_icon(status)
        builder.button(
            text=f"{icon} {event.capitalize()}",
            callback_data=EventToggleCallback(
                action="toggle",
                repo_hash=repo_hash,
                event_path=event
            ).pack()
        )
    
    # Сложные события (с вложенностью)
    builder.button(
        text="📝 Issues",
        callback_data=SettingsCallback(action="issues", repo_hash=repo_hash).pack()
    )
    builder.button(
        text="💬 Issue Comments",
        callback_data=SettingsCallback(action="issue_comments", repo_hash=repo_hash).pack()
    )
    builder.button(
        text="📦 Pull Requests",
        callback_data=SettingsCallback(action="pull_requests", repo_hash=repo_hash).pack()
    )
    builder.button(
        text="💬 PR Comments",
        callback_data=SettingsCallback(action="pull_request_comments", repo_hash=repo_hash).pack()
    )
    builder.button(
        text="🚀 Releases",
        callback_data=SettingsCallback(action="releases", repo_hash=repo_hash).pack()
    )
    
    # Кнопки действий
    builder.adjust(2)
    builder.button(
        text="📊 Statistics",
        callback_data=SettingsCallback(action="stats", repo_hash=repo_hash).pack()
    )
    builder.button(
        text="🗑️ Remove Repository",
        callback_data=SettingsCallback(action="remove", repo_hash=repo_hash).pack()
    )
    
    builder.adjust(1)
    
    return builder.as_markup()


def build_issues_keyboard(repo_key: str, events: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Строит клавиатуру настроек Issues"""
    builder = InlineKeyboardBuilder()
    repo_hash = get_repo_hash(repo_key)
    
    issues_events = events.get("issues", {})
    event_names = {
        "opened": "Opened",
        "closed": "Closed"
    }
    
    for event_key, event_name in event_names.items():
        status = issues_events.get(event_key, False)
        icon = get_status_icon(status)
        builder.button(
            text=f"{icon} {event_name}",
            callback_data=EventToggleCallback(
                action="toggle",
                repo_hash=repo_hash,
                event_path=f"issues.{event_key}"
            ).pack()
        )
    
    builder.adjust(2)
    builder.button(
        text="🔙 Back",
        callback_data=SettingsCallback(action="back", repo_hash=repo_hash).pack()
    )
    builder.adjust(1)
    
    return builder.as_markup()


def build_issue_comments_keyboard(repo_key: str, events: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Строит клавиатуру настроек Issue Comments"""
    builder = InlineKeyboardBuilder()
    repo_hash = get_repo_hash(repo_key)
    
    issue_comments_events = events.get("issue_comments", {})
    event_names = {
        "created": "Created",
        "deleted": "Deleted"
    }
    
    for event_key, event_name in event_names.items():
        status = issue_comments_events.get(event_key, False)
        icon = get_status_icon(status)
        builder.button(
            text=f"{icon} {event_name}",
            callback_data=EventToggleCallback(
                action="toggle",
                repo_hash=repo_hash,
                event_path=f"issue_comments.{event_key}"
            ).pack()
        )
    
    builder.adjust(2)
    builder.button(
        text="🔙 Back",
        callback_data=SettingsCallback(action="back", repo_hash=repo_hash).pack()
    )
    builder.adjust(1)
    
    return builder.as_markup()


def build_pull_requests_keyboard(repo_key: str, events: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Строит клавиатуру настроек Pull Requests"""
    builder = InlineKeyboardBuilder()
    repo_hash = get_repo_hash(repo_key)
    
    pr_events = events.get("pull_requests", {})
    event_names = {
        "opened": "Opened",
        "closed": "Closed",
        "synchronize": "Synchronize"
    }
    
    for event_key, event_name in event_names.items():
        status = pr_events.get(event_key, False)
        icon = get_status_icon(status)
        builder.button(
            text=f"{icon} {event_name}",
            callback_data=EventToggleCallback(
                action="toggle",
                repo_hash=repo_hash,
                event_path=f"pull_requests.{event_key}"
            ).pack()
        )
    
    builder.adjust(2)
    builder.button(
        text="🔙 Back",
        callback_data=SettingsCallback(action="back", repo_hash=repo_hash).pack()
    )
    builder.adjust(1)
    
    return builder.as_markup()


def build_pull_request_comments_keyboard(repo_key: str, events: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Строит клавиатуру настроек PR Comments"""
    builder = InlineKeyboardBuilder()
    repo_hash = get_repo_hash(repo_key)
    
    pr_comments_events = events.get("pull_request_comments", {})
    event_names = {
        "created": "Created",
        "deleted": "Deleted"
    }
    
    for event_key, event_name in event_names.items():
        status = pr_comments_events.get(event_key, False)
        icon = get_status_icon(status)
        builder.button(
            text=f"{icon} {event_name}",
            callback_data=EventToggleCallback(
                action="toggle",
                repo_hash=repo_hash,
                event_path=f"pull_request_comments.{event_key}"
            ).pack()
        )
    
    builder.adjust(2)
    builder.button(
        text="🔙 Back",
        callback_data=SettingsCallback(action="back", repo_hash=repo_hash).pack()
    )
    builder.adjust(1)
    
    return builder.as_markup()


def build_releases_keyboard(repo_key: str, events: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Строит клавиатуру настроек Releases"""
    builder = InlineKeyboardBuilder()
    repo_hash = get_repo_hash(repo_key)
    
    releases_events = events.get("releases", {})
    event_names = {
        "published": "Published",
        "released": "Released"
    }
    
    for event_key, event_name in event_names.items():
        status = releases_events.get(event_key, False)
        icon = get_status_icon(status)
        builder.button(
            text=f"{icon} {event_name}",
            callback_data=EventToggleCallback(
                action="toggle",
                repo_hash=repo_hash,
                event_path=f"releases.{event_key}"
            ).pack()
        )
    
    builder.adjust(2)
    builder.button(
        text="🔙 Back",
        callback_data=SettingsCallback(action="back", repo_hash=repo_hash).pack()
    )
    builder.adjust(1)
    
    return builder.as_markup()


def build_confirm_remove_keyboard(repo_key: str) -> InlineKeyboardMarkup:
    """Строит клавиатуру подтверждения удаления"""
    builder = InlineKeyboardBuilder()
    repo_hash = get_repo_hash(repo_key)
    
    builder.button(
        text="✅ Yes, remove",
        callback_data=SettingsCallback(action="confirm_remove", repo_hash=repo_hash).pack()
    )
    builder.button(
        text="❌ Cancel",
        callback_data=SettingsCallback(action="back", repo_hash=repo_hash).pack()
    )
    
    builder.adjust(2)
    
    return builder.as_markup()


def build_repo_list_keyboard(repos: Dict[str, Dict[str, Any]], chat_id: int) -> InlineKeyboardMarkup:
    """Строит клавиатуру со списком репозиториев пользователя"""
    builder = InlineKeyboardBuilder()
    
    # Фильтруем репозитории только для текущего чата
    user_repos = {
        repo_key: repo_data 
        for repo_key, repo_data in repos.items() 
        if repo_data.get("chat_id") == chat_id
    }
    
    if not user_repos:
        return None
    
    # Сортируем репозитории по имени
    sorted_repos = sorted(user_repos.items())
    
    for repo_key, repo_data in sorted_repos:
        repo_hash = get_repo_hash(repo_key)
        builder.button(
            text=f"⚙️ {repo_key}",
            callback_data=SettingsCallback(action="select_repo", repo_hash=repo_hash).pack()
        )
    
    builder.adjust(1)
    
    return builder.as_markup()

