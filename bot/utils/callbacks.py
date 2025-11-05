"""Утилиты для работы с callback handlers"""
from typing import Optional, Tuple
from aiogram.types import CallbackQuery
from bot.services.database import get_repository, get_all_repositories
from bot.keyboards.inline import get_repo_hash


async def get_repo_key_by_hash(repo_hash: str, chat_id: int) -> Optional[str]:
    """Получает repo_key по хешу"""
    repos = await get_all_repositories()
    for repo_key, repo_data in repos.items():
        if get_repo_hash(repo_key) == repo_hash and repo_data.get("chat_id") == chat_id:
            return repo_key
    return None


async def get_repo_and_check_access(
    callback: CallbackQuery,
    repo_hash: str,
    check_access: bool = True
) -> Optional[Tuple[str, dict]]:
    """Получает репозиторий по хешу и проверяет права доступа
    
    Args:
        callback: CallbackQuery объект
        repo_hash: Хеш репозитория
        check_access: Проверять ли права доступа (по умолчанию True)
    
    Returns:
        Tuple (repo_key, repo_data) если все ОК, иначе None
    """
    # Используем chat.id для поддержки групповых чатов
    chat_id = callback.message.chat.id
    repo_key = await get_repo_key_by_hash(repo_hash, chat_id)
    
    if not repo_key:
        await callback.answer("❌ Репозиторий не найден.", show_alert=True)
        return None
    
    repo_data = await get_repository(repo_key)
    if not repo_data:
        await callback.answer("❌ Репозиторий не найден.", show_alert=True)
        return None
    
    if check_access and repo_data.get("chat_id") != chat_id:
        await callback.answer("❌ У вас нет прав на этот репозиторий.", show_alert=True)
        return None
    
    return repo_key, repo_data

