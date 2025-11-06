import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
import aiofiles
import logging

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "database.json"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Блокировка для предотвращения одновременного доступа
_lock = asyncio.Lock()


def get_default_events() -> Dict[str, Any]:
    """Возвращает структуру событий по умолчанию (все отключены)"""
    return {
        "commits": False,
        "forks": False,
        "watch": False,
        "issues": {
            "opened": False,
            "closed": False
        },
        "issue_comments": {
            "created": False,
            "deleted": False
        },
        "pull_requests": {
            "opened": False,
            "closed": False,
            "synchronize": False
        },
        "pull_request_comments": {
            "created": False,
            "deleted": False
        },
        "releases": {
            "published": False,
            "released": False
        }
    }


async def _load_db() -> Dict[str, Any]:
    """Загружает базу данных из JSON файла"""
    async with _lock:
        try:
            if not DB_PATH.exists():
                return {"repositories": {}, "statistics": {}}
            async with aiofiles.open(DB_PATH, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content) if content.strip() else {"repositories": {}, "statistics": {}}
        except Exception as e:
            logger.error(f"Ошибка загрузки БД: {e}")
            return {"repositories": {}, "statistics": {}}


async def _save_db(data: Dict[str, Any]) -> None:
    """Сохраняет базу данных в JSON файл"""
    async with _lock:
        try:
            async with aiofiles.open(DB_PATH, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Ошибка сохранения БД: {e}")
            raise


def _get_repo_storage_key(repo_key: str, chat_id: int) -> str:
    """Генерирует ключ для хранения репозитория в базе данных"""
    return f"{repo_key}:{chat_id}"


async def add_repository(repo_key: str, chat_id: int, github_token: Optional[str] = None) -> bool:
    """Добавляет репозиторий в базу данных"""
    try:
        db = await _load_db()
        storage_key = _get_repo_storage_key(repo_key, chat_id)
        
        # Проверяем, не добавлен ли уже этот репозиторий этим пользователем
        if storage_key in db["repositories"]:
            return False
        
        db["repositories"][storage_key] = {
            "repo_key": repo_key,
            "chat_id": chat_id,
            "events": get_default_events(),
            "last_commit_sha": None,
            "last_star_count": 0,
            "github_token": github_token
        }
        
        if repo_key not in db["statistics"]:
            db["statistics"][repo_key] = {
                "stars": 0,
                "forks": 0,
                "commits": 0,
                "issues": 0,
                "pull_requests": 0,
                "contributors": [],
                "languages": {},
                "last_updated": None
            }
        
        await _save_db(db)
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления репозитория: {e}")
        return False


async def remove_repository(repo_key: str, chat_id: int) -> bool:
    """Удаляет репозиторий из базы данных"""
    try:
        db = await _load_db()
        storage_key = _get_repo_storage_key(repo_key, chat_id)
        if storage_key not in db["repositories"]:
            return False
        
        del db["repositories"][storage_key]
        # Статистику оставляем для истории
        await _save_db(db)
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления репозитория: {e}")
        return False


async def get_repository(repo_key: str, chat_id: int) -> Optional[Dict[str, Any]]:
    """Получает информацию о репозитории для конкретного пользователя"""
    try:
        db = await _load_db()
        storage_key = _get_repo_storage_key(repo_key, chat_id)
        return db["repositories"].get(storage_key)
    except Exception as e:
        logger.error(f"Ошибка получения репозитория: {e}")
        return None


async def get_repositories_by_repo_key(repo_key: str) -> Dict[str, Dict[str, Any]]:
    """Получает все репозитории для данного repo_key (всех пользователей)"""
    try:
        db = await _load_db()
        return {
            storage_key: repo_data
            for storage_key, repo_data in db["repositories"].items()
            if repo_data.get("repo_key") == repo_key
        }
    except Exception as e:
        logger.error(f"Ошибка получения репозиториев по ключу: {e}")
        return {}


async def get_all_repositories() -> Dict[str, Dict[str, Any]]:
    """Получает все репозитории"""
    try:
        db = await _load_db()
        return db["repositories"].copy()
    except Exception as e:
        logger.error(f"Ошибка получения всех репозиториев: {e}")
        return {}


async def get_user_repositories(chat_id: int) -> Dict[str, Dict[str, Any]]:
    """Получает все репозитории пользователя"""
    try:
        db = await _load_db()
        result = {}
        for storage_key, repo_data in db["repositories"].items():
            if repo_data.get("chat_id") == chat_id:
                repo_key = repo_data.get("repo_key", storage_key.split(":")[0])
                result[repo_key] = repo_data
        return result
    except Exception as e:
        logger.error(f"Ошибка получения репозиториев пользователя: {e}")
        return {}


async def update_repository_events(repo_key: str, chat_id: int, events: Dict[str, Any]) -> bool:
    """Обновляет настройки событий для репозитория"""
    try:
        db = await _load_db()
        storage_key = _get_repo_storage_key(repo_key, chat_id)
        if storage_key not in db["repositories"]:
            return False
        
        db["repositories"][storage_key]["events"] = events
        await _save_db(db)
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления событий: {e}")
        return False


async def update_event_status(
    repo_key: str,
    chat_id: int,
    event_path: str,
    status: bool
) -> bool:
    """Обновляет статус конкретного события
    
    Args:
        repo_key: Ключ репозитория (owner/repo)
        chat_id: ID чата пользователя
        event_path: Путь к событию (например, "commits", "issues.opened", "pull_requests.opened")
        status: Новый статус (True/False)
    """
    try:
        db = await _load_db()
        storage_key = _get_repo_storage_key(repo_key, chat_id)
        if storage_key not in db["repositories"]:
            return False
        
        events = db["repositories"][storage_key]["events"]
        path_parts = event_path.split(".")
        
        # Навигация по вложенной структуре
        current = events
        for part in path_parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                return False
            current = current[part]
        
        # Установка значения
        final_key = path_parts[-1]
        if final_key not in current:
            return False
        
        current[final_key] = status
        await _save_db(db)
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления статуса события: {e}")
        return False


async def update_last_commit_sha(repo_key: str, commit_sha: str) -> None:
    """Обновляет SHA последнего коммита для всех пользователей, отслеживающих репозиторий"""
    try:
        db = await _load_db()
        repos = await get_repositories_by_repo_key(repo_key)
        for storage_key in repos.keys():
            if storage_key in db["repositories"]:
                db["repositories"][storage_key]["last_commit_sha"] = commit_sha
        await _save_db(db)
    except Exception as e:
        logger.error(f"Ошибка обновления SHA коммита: {e}")


async def update_last_star_count(repo_key: str, star_count: int) -> None:
    """Обновляет количество звезд для всех пользователей, отслеживающих репозиторий"""
    try:
        db = await _load_db()
        repos = await get_repositories_by_repo_key(repo_key)
        for storage_key in repos.keys():
            if storage_key in db["repositories"]:
                db["repositories"][storage_key]["last_star_count"] = star_count
        await _save_db(db)
    except Exception as e:
        logger.error(f"Ошибка обновления количества звезд: {e}")


async def update_statistics(repo_key: str, stats: Dict[str, Any]) -> None:
    """Обновляет статистику репозитория"""
    try:
        db = await _load_db()
        if repo_key not in db["statistics"]:
            db["statistics"][repo_key] = {}
        
        db["statistics"][repo_key].update(stats)
        await _save_db(db)
    except Exception as e:
        logger.error(f"Ошибка обновления статистики: {e}")


async def get_statistics(repo_key: str) -> Optional[Dict[str, Any]]:
    """Получает статистику репозитория"""
    try:
        db = await _load_db()
        return db["statistics"].get(repo_key)
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return None


async def get_all_statistics() -> Dict[str, Dict[str, Any]]:
    """Получает всю статистику"""
    try:
        db = await _load_db()
        return db["statistics"].copy()
    except Exception as e:
        logger.error(f"Ошибка получения всей статистики: {e}")
        return {}

