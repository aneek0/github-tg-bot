import asyncio
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from aiohttp import web

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot.handlers import commands, callbacks, messages
from bot.services.polling import PollingService
from bot.utils.constants import RATE_LIMIT_WITH_TOKEN
from bot.services.github import set_global_bot
from bot.utils.github import get_token_manager

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
MODE = os.getenv("MODE", "polling").lower()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "60"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения")

# Проверяем наличие GitHub токена
token_manager = get_token_manager()
if token_manager and token_manager.tokens:
    token_count = len(token_manager.tokens)
    logger.info(f"✅ Загружено {token_count} GitHub токен(ов) (лимит {RATE_LIMIT_WITH_TOKEN} запросов/час на токен)")
    if token_count > 1:
        logger.info(f"💡 Автоматическое переключение между токенами включено")
elif GITHUB_TOKEN and GITHUB_TOKEN.strip():
    logger.info(f"✅ GitHub токен найден (лимит {RATE_LIMIT_WITH_TOKEN} запросов/час), токен: {GITHUB_TOKEN[:10]}...")
else:
    from bot.utils.constants import RATE_LIMIT_WITHOUT_TOKEN
    logger.warning(f"⚠️ GITHUB_TOKEN не установлен или пустой! Лимит: {RATE_LIMIT_WITHOUT_TOKEN} запросов/час. Добавьте токен в .env для увеличения лимита.")


async def register_commands(bot: Bot) -> None:
    """Регистрирует команды бота"""
    commands_list = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="add", description="Добавить репозиторий"),
        BotCommand(command="remove", description="Удалить репозиторий"),
        BotCommand(command="list", description="Список репозиториев"),
        BotCommand(command="stats", description="Статистика"),
        BotCommand(command="settings", description="Настройки репозитория"),
    ]
    await bot.set_my_commands(commands_list)
    logger.info("Команды бота зарегистрированы")


async def on_startup(bot: Bot) -> None:
    """Вызывается при запуске бота"""
    await register_commands(bot)
    logger.info("Бот запущен")


async def on_shutdown(bot: Bot) -> None:
    """Вызывается при остановке бота"""
    logger.info("Бот остановлен")


def setup_handlers(dp: Dispatcher) -> None:
    """Настраивает handlers"""
    # Регистрируем routers
    dp.include_router(commands.router)
    dp.include_router(callbacks.router)
    dp.include_router(messages.router)
    
    logger.info("Handlers зарегистрированы")


async def run_polling() -> None:
    """Запускает бота в режиме polling"""
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Устанавливаем глобальный bot для отправки уведомлений о rate limit
    set_global_bot(bot)
    
    dp = Dispatcher()
    setup_handlers(dp)
    
    # Регистрируем startup/shutdown handlers
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Запускаем polling сервис
    polling_service = PollingService(bot, POLLING_INTERVAL)
    polling_task = asyncio.create_task(polling_service.start())
    
    try:
        logger.info("Запуск бота в режиме polling...")
        await dp.start_polling(bot)
    finally:
        polling_service.stop()
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()


async def run_webhook() -> None:
    """Запускает бота в режиме webhook"""
    if not WEBHOOK_URL:
        raise ValueError("WEBHOOK_URL не установлен для режима webhook")
    
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Устанавливаем глобальный bot для отправки уведомлений о rate limit
    set_global_bot(bot)
    
    dp = Dispatcher()
    setup_handlers(dp)
    
    # Регистрируем startup/shutdown handlers
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Создаем aiohttp приложение
    webhook_app = web.Application()
    
    # Настраиваем Telegram webhook handler
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET if WEBHOOK_SECRET else None,
    )
    webhook_requests_handler.register(webhook_app, path=WEBHOOK_PATH)
    setup_application(webhook_app, dp, bot=bot)
    
    # Добавляем GitHub webhook handler на отдельный путь
    GITHUB_WEBHOOK_PATH = os.getenv("GITHUB_WEBHOOK_PATH", "/webhook/github")
    async def github_webhook_handler(request: web.Request) -> web.Response:
        from bot.services.webhook import handle_webhook
        return await handle_webhook(request, bot, WEBHOOK_SECRET)
    
    webhook_app.router.add_post(GITHUB_WEBHOOK_PATH, github_webhook_handler)
    
    # Устанавливаем Telegram webhook
    telegram_webhook_url = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
    await bot.set_webhook(telegram_webhook_url, secret_token=WEBHOOK_SECRET if WEBHOOK_SECRET else None)
    logger.info(f"Telegram webhook установлен: {telegram_webhook_url}")
    logger.info(f"GitHub webhook путь: {GITHUB_WEBHOOK_PATH}")
    
    # Запускаем polling сервис в фоне (для проверки изменений)
    polling_service = PollingService(bot, POLLING_INTERVAL)
    polling_task = asyncio.create_task(polling_service.start())
    
    # Запускаем HTTP сервер
    runner = web.AppRunner(webhook_app)
    await runner.setup()
    
    # Определяем host и port из WEBHOOK_URL или используем значения по умолчанию
    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.getenv("WEBHOOK_PORT", "8080"))
    
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    logger.info(f"HTTP сервер запущен на {host}:{port}")
    
    try:
        # Держим приложение запущенным
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    finally:
        polling_service.stop()
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        await runner.cleanup()
        await bot.session.close()


def main() -> None:
    """Главная функция"""
    if MODE == "webhook":
        asyncio.run(run_webhook())
    elif MODE == "polling":
        asyncio.run(run_polling())
    else:
        raise ValueError(f"Неизвестный режим: {MODE}. Используйте 'webhook' или 'polling'")


if __name__ == "__main__":
    main()

