import logging
import re
from aiogram import Router, F
from aiogram.types import Message
from aiogram import html

from bot.services.database import add_repository, get_repository
from bot.keyboards.inline import build_settings_keyboard
from bot.utils.github import create_github_client
from bot.utils.repository import get_repo_key

logger = logging.getLogger(__name__)
router = Router()

# Регулярное выражение для поиска GitHub ссылок
GITHUB_URL_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)',
    re.IGNORECASE
)


@router.message(F.text)
async def handle_github_url(message: Message) -> None:
    """Обработчик текстовых сообщений с GitHub ссылками"""
    text = message.text
    
    # Ищем GitHub ссылки в тексте
    matches = GITHUB_URL_PATTERN.findall(text)
    
    if not matches:
        return  # Не GitHub ссылка, пропускаем
    
    github_client = create_github_client()
    
    for owner, repo in matches:
        # Убираем возможные суффиксы (.git, слэши и т.д.)
        repo = repo.rstrip("/").rstrip(".git")
        
        repo_key = get_repo_key(owner, repo)
        
        # Проверяем, не добавлен ли уже
        existing_repo = await get_repository(repo_key)
        if existing_repo:
            if existing_repo.get("chat_id") == message.chat.id:
                await message.answer(
                    f"⚠️ Репозиторий {html.code(repo_key)} уже добавлен.\n"
                    f"Используйте /settings {owner} {repo} для настройки."
                )
                continue
            else:
                await message.answer(
                    f"⚠️ Репозиторий {html.code(repo_key)} уже отслеживается другим пользователем."
                )
                continue
        
        # Проверяем, существует ли репозиторий
        repo_info = await github_client.get_repository_info(owner, repo)
        if not repo_info:
            await message.answer(
                f"❌ Репозиторий {html.code(repo_key)} не найден или недоступен."
            )
            continue
        
        # Добавляем репозиторий
        success = await add_repository(repo_key, message.chat.id)
        if success:
            repo_data = await get_repository(repo_key)
            events = repo_data.get("events", {}) if repo_data else {}
            await message.answer(
                f"✅ Репозиторий {html.code(repo_key)} успешно добавлен!\n\n"
                f"Используйте кнопки ниже для настройки событий.",
                reply_markup=build_settings_keyboard(repo_key, events)
            )
        else:
            await message.answer(f"❌ Ошибка при добавлении репозитория {html.code(repo_key)}.")

