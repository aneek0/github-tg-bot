import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram import html

from bot.services.database import (
    add_repository,
    get_user_repositories,
    get_repository,
    get_all_statistics,
    set_chat_thread_id,
    get_chat_thread_id
)
from bot.services.formatter import format_stats_message
from bot.keyboards.inline import build_settings_keyboard
from bot.utils.github import create_github_client
from bot.utils.repository import parse_repo_input, get_repo_key

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обработчик команды /start"""
    # Сохраняем thread_id если команда выполнена в топике группы
    thread_id = getattr(message, 'message_thread_id', None)
    if thread_id is not None:
        await set_chat_thread_id(message.chat.id, thread_id)
        response_text = (
            f"Привет, {html.bold(message.from_user.full_name)}! 👋\n\n"
            "Я бот для отслеживания событий GitHub репозиториев.\n\n"
            f"✅ Бот настроен для работы в этом топике (ID: {thread_id}).\n"
            "Все уведомления будут приходить сюда.\n\n"
            "Доступные команды:\n"
            "• /add owner/repo - добавить репозиторий\n"
            "• /remove owner/repo - удалить репозиторий\n"
            "• /list - список отслеживаемых репозиториев\n"
            "• /stats - статистика по репозиториям\n"
            "• /settings owner repo - настройки репозитория\n\n"
            "Также можно просто отправить ссылку на GitHub репозиторий!"
        )
    else:
        response_text = (
            f"Привет, {html.bold(message.from_user.full_name)}! 👋\n\n"
            "Я бот для отслеживания событий GitHub репозиториев.\n\n"
            "Доступные команды:\n"
            "• /add owner/repo - добавить репозиторий\n"
            "• /remove owner/repo - удалить репозиторий\n"
            "• /list - список отслеживаемых репозиториев\n"
            "• /stats - статистика по репозиториям\n"
            "• /settings owner repo - настройки репозитория\n\n"
            "Также можно просто отправить ссылку на GitHub репозиторий!"
        )
    
    await message.answer(response_text)


@router.message(Command("add"))
async def cmd_add(message: Message, command: Command) -> None:
    """Обработчик команды /add"""
    # Проверяем thread_id для групп с топиками
    thread_id = getattr(message, 'message_thread_id', None)
    saved_thread_id = await get_chat_thread_id(message.chat.id)
    
    # Если это группа с топиками, проверяем что команда выполняется в правильном топике
    if saved_thread_id is not None:
        if thread_id != saved_thread_id:
            await message.answer(
                "⚠️ Команды должны выполняться в том же топике, где был выполнен /start.\n"
                f"Используйте /start в нужном топике для настройки бота."
            )
            return
    
    if not command.args:
        await message.answer(
            "Использование: /add owner/repo\n"
            "Пример: /add microsoft/vscode"
        )
        return
    
    repo_input = command.args.strip()
    github_client = create_github_client()
    
    # Парсим репозиторий
    parsed = parse_repo_input(repo_input, github_client)
    if not parsed:
        await message.answer("❌ Неверный формат. Используйте: owner/repo или ссылку на GitHub")
        return
    
    owner, repo = parsed
    repo_key = get_repo_key(owner, repo)
    
    # Проверяем, существует ли репозиторий
    repo_info = await github_client.get_repository_info(owner, repo)
    if not repo_info:
        await message.answer(f"❌ Репозиторий {html.code(repo_key)} не найден или недоступен.")
        return
    
    # Проверяем, не добавлен ли уже этим пользователем
    existing_repo = await get_repository(repo_key, message.chat.id)
    if existing_repo:
        await message.answer(f"⚠️ Репозиторий {html.code(repo_key)} уже добавлен.")
        return
    
    # Используем saved_thread_id если он есть, иначе текущий thread_id
    thread_id_to_use = saved_thread_id if saved_thread_id is not None else thread_id
    
    # Добавляем репозиторий
    success = await add_repository(repo_key, message.chat.id, thread_id=thread_id_to_use)
    if success:
        repo_data = await get_repository(repo_key, message.chat.id)
        events = repo_data.get("events", {}) if repo_data else {}
        await message.answer(
            f"✅ Репозиторий {html.code(repo_key)} успешно добавлен!\n\n"
            f"Используйте кнопки ниже для настройки событий.",
            reply_markup=build_settings_keyboard(repo_key, events)
        )
    else:
        await message.answer("❌ Ошибка при добавлении репозитория.")


@router.message(Command("remove"))
async def cmd_remove(message: Message, command: Command) -> None:
    """Обработчик команды /remove"""
    # Проверяем thread_id для групп с топиками
    thread_id = getattr(message, 'message_thread_id', None)
    saved_thread_id = await get_chat_thread_id(message.chat.id)
    
    # Если это группа с топиками, проверяем что команда выполняется в правильном топике
    if saved_thread_id is not None:
        if thread_id != saved_thread_id:
            await message.answer(
                "⚠️ Команды должны выполняться в том же топике, где был выполнен /start.\n"
                f"Используйте /start в нужном топике для настройки бота."
            )
            return
    
    if not command.args:
        await message.answer(
            "Использование: /remove owner/repo\n"
            "Пример: /remove microsoft/vscode"
        )
        return
    
    repo_input = command.args.strip()
    github_client = create_github_client()
    
    # Парсим репозиторий
    parsed = parse_repo_input(repo_input, github_client)
    if not parsed:
        await message.answer("❌ Неверный формат. Используйте: owner/repo или ссылку на GitHub")
        return
    
    owner, repo = parsed
    repo_key = get_repo_key(owner, repo)
    
    # Проверяем, существует ли репозиторий в базе для этого пользователя
    existing_repo = await get_repository(repo_key, message.chat.id)
    if not existing_repo:
        await message.answer(f"❌ Репозиторий {html.code(repo_key)} не найден в списке отслеживаемых.")
        return
    
    # Показываем подтверждение через inline кнопку
    from bot.keyboards.inline import build_confirm_remove_keyboard
    await message.answer(
        f"⚠️ Вы уверены, что хотите удалить репозиторий {html.code(repo_key)}?",
        reply_markup=build_confirm_remove_keyboard(repo_key)
    )


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    """Обработчик команды /list"""
    # Проверяем thread_id для групп с топиками
    thread_id = getattr(message, 'message_thread_id', None)
    saved_thread_id = await get_chat_thread_id(message.chat.id)
    
    # Если это группа с топиками, проверяем что команда выполняется в правильном топике
    if saved_thread_id is not None:
        if thread_id != saved_thread_id:
            await message.answer(
                "⚠️ Команды должны выполняться в том же топике, где был выполнен /start.\n"
                f"Используйте /start в нужном топике для настройки бота."
            )
            return
    
    repos = await get_user_repositories(message.chat.id)
    
    if not repos:
        await message.answer("📋 У вас нет отслеживаемых репозиториев.")
        return
    
    text = "📋 Отслеживаемые репозитории:\n\n"
    for repo_key in repos.keys():
        owner, repo = repo_key.split("/", 1)
        repo_url = f"https://github.com/{owner}/{repo}"
        text += f"• {html.link(repo_key, repo_url)}\n"
    
    await message.answer(text)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Обработчик команды /stats"""
    # Проверяем thread_id для групп с топиками
    thread_id = getattr(message, 'message_thread_id', None)
    saved_thread_id = await get_chat_thread_id(message.chat.id)
    
    # Если это группа с топиками, проверяем что команда выполняется в правильном топике
    if saved_thread_id is not None:
        if thread_id != saved_thread_id:
            await message.answer(
                "⚠️ Команды должны выполняться в том же топике, где был выполнен /start.\n"
                f"Используйте /start в нужном топике для настройки бота."
            )
            return
    
    user_repos = await get_user_repositories(message.chat.id)
    
    if not user_repos:
        await message.answer("📊 У вас нет отслеживаемых репозиториев.")
        return
    
    all_stats = await get_all_statistics()
    
    # Фильтруем статистику только для репозиториев пользователя
    user_stats = {
        repo_key: all_stats.get(repo_key, {})
        for repo_key in user_repos.keys()
    }
    
    text = format_stats_message(user_stats, user_repos)
    await message.answer(text)


@router.message(Command("settings"))
async def cmd_settings(message: Message, command: Command) -> None:
    """Обработчик команды /settings"""
    # Проверяем thread_id для групп с топиками
    thread_id = getattr(message, 'message_thread_id', None)
    saved_thread_id = await get_chat_thread_id(message.chat.id)
    
    # Если это группа с топиками, проверяем что команда выполняется в правильном топике
    if saved_thread_id is not None:
        if thread_id != saved_thread_id:
            await message.answer(
                "⚠️ Команды должны выполняться в том же топике, где был выполнен /start.\n"
                f"Используйте /start в нужном топике для настройки бота."
            )
            return
    
    if not command.args:
        # Показываем список репозиториев пользователя
        from bot.services.database import get_all_repositories
        from bot.keyboards.inline import build_repo_list_keyboard
        
        all_repos = await get_all_repositories()
        keyboard = build_repo_list_keyboard(all_repos, message.chat.id)
        
        if not keyboard:
            await message.answer("❌ У вас нет отслеживаемых репозиториев.\nИспользуйте /add для добавления репозитория.")
            return
        
        await message.answer(
            "⚙️ Выберите репозиторий для настройки:",
            reply_markup=keyboard
        )
        return
    
    repo_input = command.args.strip()
    github_client = create_github_client()
    
    # Парсим репозиторий
    parsed = parse_repo_input(repo_input, github_client)
    if not parsed:
        await message.answer("❌ Неверный формат. Используйте: owner/repo или ссылку на GitHub")
        return
    
    owner, repo = parsed
    repo_key = get_repo_key(owner, repo)
    
    # Проверяем, существует ли репозиторий для этого пользователя
    repo_data = await get_repository(repo_key, message.chat.id)
    if not repo_data:
        await message.answer(f"❌ Репозиторий {html.code(repo_key)} не найден в списке отслеживаемых.")
        return
    
    events = repo_data.get("events", {})
    await message.answer(
        f"⚙️ Настройки для {html.code(repo_key)}:\n\n"
        "Выберите события для отслеживания:",
        reply_markup=build_settings_keyboard(repo_key, events)
    )

