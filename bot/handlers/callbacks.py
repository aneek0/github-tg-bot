import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram import html

from bot.services.database import (
    get_repository,
    get_all_repositories,
    update_event_status,
    remove_repository,
    update_statistics
)
from bot.services.formatter import format_stats_message
from bot.keyboards.inline import (
    SettingsCallback,
    EventToggleCallback,
    get_repo_hash,
    build_settings_keyboard,
    build_issues_keyboard,
    build_issue_comments_keyboard,
    build_pull_requests_keyboard,
    build_pull_request_comments_keyboard,
    build_releases_keyboard
)
from bot.utils.github import create_github_client
from bot.utils.callbacks import get_repo_and_check_access

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(SettingsCallback.filter(F.action == "select_repo"))
async def settings_select_repo(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    """Обработчик выбора репозитория из списка"""
    result = await get_repo_and_check_access(callback, callback_data.repo_hash, check_access=False)
    if not result:
        return
    
    repo_key, repo_data = result
    events = repo_data.get("events", {})
    keyboard = build_settings_keyboard(repo_key, events)
    
    await callback.message.edit_text(
        f"⚙️ Настройки репозитория {html.code(repo_key)}:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "back"))
async def settings_back(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    """Обработчик возврата в главное меню настроек"""
    result = await get_repo_and_check_access(callback, callback_data.repo_hash)
    if not result:
        return
    
    repo_key, repo_data = result
    events = repo_data.get("events", {})
    await callback.message.edit_text(
        f"⚙️ Настройки для {html.code(repo_key)}:\n\n"
        "Выберите события для отслеживания:",
        reply_markup=build_settings_keyboard(repo_key, events)
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "issues"))
async def settings_issues(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    """Обработчик перехода к настройкам Issues"""
    result = await get_repo_and_check_access(callback, callback_data.repo_hash)
    if not result:
        return
    
    repo_key, repo_data = result
    events = repo_data.get("events", {})
    await callback.message.edit_text(
        f"📝 Настройки Issues для {html.code(repo_key)}:",
        reply_markup=build_issues_keyboard(repo_key, events)
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "issue_comments"))
async def settings_issue_comments(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    """Обработчик перехода к настройкам Issue Comments"""
    result = await get_repo_and_check_access(callback, callback_data.repo_hash)
    if not result:
        return
    
    repo_key, repo_data = result
    events = repo_data.get("events", {})
    await callback.message.edit_text(
        f"💬 Настройки Issue Comments для {html.code(repo_key)}:",
        reply_markup=build_issue_comments_keyboard(repo_key, events)
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "pull_requests"))
async def settings_pull_requests(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    """Обработчик перехода к настройкам Pull Requests"""
    result = await get_repo_and_check_access(callback, callback_data.repo_hash)
    if not result:
        return
    
    repo_key, repo_data = result
    events = repo_data.get("events", {})
    await callback.message.edit_text(
        f"📦 Настройки Pull Requests для {html.code(repo_key)}:",
        reply_markup=build_pull_requests_keyboard(repo_key, events)
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "pull_request_comments"))
async def settings_pull_request_comments(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    """Обработчик перехода к настройкам PR Comments"""
    result = await get_repo_and_check_access(callback, callback_data.repo_hash)
    if not result:
        return
    
    repo_key, repo_data = result
    events = repo_data.get("events", {})
    await callback.message.edit_text(
        f"💬 Настройки PR Comments для {html.code(repo_key)}:",
        reply_markup=build_pull_request_comments_keyboard(repo_key, events)
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "releases"))
async def settings_releases(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    """Обработчик перехода к настройкам Releases"""
    result = await get_repo_and_check_access(callback, callback_data.repo_hash)
    if not result:
        return
    
    repo_key, repo_data = result
    events = repo_data.get("events", {})
    await callback.message.edit_text(
        f"🚀 Настройки Releases для {html.code(repo_key)}:",
        reply_markup=build_releases_keyboard(repo_key, events)
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "stats"))
async def settings_stats(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    """Обработчик просмотра статистики репозитория"""
    result = await get_repo_and_check_access(callback, callback_data.repo_hash)
    if not result:
        return
    
    repo_key, repo_data = result
    
    # Получаем статистику
    repo_token = repo_data.get("github_token")
    github_client = create_github_client(repo_token)
    owner, repo = repo_key.split("/", 1)
    stats = await github_client.get_statistics(owner, repo)
    
    # Обновляем в базе
    await update_statistics(repo_key, stats)
    
    # Форматируем сообщение
    user_repos = {repo_key: repo_data}
    formatted_stats = {repo_key: stats}
    text = format_stats_message(formatted_stats, user_repos)
    
    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "remove"))
async def settings_remove(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    """Обработчик запроса на удаление репозитория"""
    result = await get_repo_and_check_access(callback, callback_data.repo_hash)
    if not result:
        return
    
    repo_key, _ = result
    from bot.keyboards.inline import build_confirm_remove_keyboard
    await callback.message.edit_text(
        f"⚠️ Вы уверены, что хотите удалить репозиторий {html.code(repo_key)}?",
        reply_markup=build_confirm_remove_keyboard(repo_key)
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "confirm_remove"))
async def settings_confirm_remove(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    """Обработчик подтверждения удаления репозитория"""
    result = await get_repo_and_check_access(callback, callback_data.repo_hash)
    if not result:
        return
    
    repo_key, _ = result
    chat_id = callback.message.chat.id
    success = await remove_repository(repo_key, chat_id)
    if success:
        await callback.message.edit_text(f"✅ Репозиторий {html.code(repo_key)} удален.")
    else:
        await callback.answer("❌ Ошибка при удалении репозитория.", show_alert=True)
    
    await callback.answer()


@router.callback_query(EventToggleCallback.filter(F.action == "toggle"))
async def event_toggle(callback: CallbackQuery, callback_data: EventToggleCallback) -> None:
    """Обработчик переключения статуса события"""
    result = await get_repo_and_check_access(callback, callback_data.repo_hash)
    if not result:
        return
    
    repo_key, repo_data = result
    event_path = callback_data.event_path
    
    # Получаем текущее значение события
    events = repo_data.get("events", {})
    path_parts = event_path.split(".")
    
    current = events
    for part in path_parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            await callback.answer("❌ Ошибка доступа к событию.", show_alert=True)
            return
        current = current[part]
    
    final_key = path_parts[-1]
    if final_key not in current:
        await callback.answer("❌ Событие не найдено.", show_alert=True)
        return
    
    # Переключаем статус
    new_status = not current[final_key]
    chat_id = callback.message.chat.id
    success = await update_event_status(repo_key, chat_id, event_path, new_status)
    
    if not success:
        await callback.answer("❌ Ошибка обновления статуса.", show_alert=True)
        return
    
    # Обновляем клавиатуру
    repo_data = await get_repository(repo_key, chat_id)
    events = repo_data.get("events", {})
    
    # Определяем, какую клавиатуру показывать
    if event_path.startswith("issues."):
        keyboard = build_issues_keyboard(repo_key, events)
        text = f"📝 Настройки Issues для {html.code(repo_key)}:"
    elif event_path.startswith("issue_comments."):
        keyboard = build_issue_comments_keyboard(repo_key, events)
        text = f"💬 Настройки Issue Comments для {html.code(repo_key)}:"
    elif event_path.startswith("pull_requests."):
        keyboard = build_pull_requests_keyboard(repo_key, events)
        text = f"📦 Настройки Pull Requests для {html.code(repo_key)}:"
    elif event_path.startswith("pull_request_comments."):
        keyboard = build_pull_request_comments_keyboard(repo_key, events)
        text = f"💬 Настройки PR Comments для {html.code(repo_key)}:"
    elif event_path.startswith("releases."):
        keyboard = build_releases_keyboard(repo_key, events)
        text = f"🚀 Настройки Releases для {html.code(repo_key)}:"
    else:
        keyboard = build_settings_keyboard(repo_key, events)
        text = f"⚙️ Настройки для {html.code(repo_key)}:\n\nВыберите события для отслеживания:"
    
    status_text = "включено" if new_status else "выключено"
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer(f"✅ Событие {status_text}")

