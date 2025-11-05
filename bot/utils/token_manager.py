"""Менеджер для управления несколькими GitHub токенами"""
import logging
import time
from typing import List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class TokenManager:
    """Управляет несколькими GitHub токенами с автоматическим переключением"""
    
    def __init__(self, tokens: List[str]):
        """Инициализирует менеджер токенов
        
        Args:
            tokens: Список токенов (может быть пустым)
        """
        # Фильтруем пустые токены
        self.tokens = [t.strip() for t in tokens if t and t.strip()]
        self.current_index = 0
        
        # Храним информацию о rate limit для каждого токена
        # Формат: {token_hash: {"remaining": int, "reset": int, "limit": int}}
        self.token_stats = {}
        
        logger.info(f"TokenManager инициализирован с {len(self.tokens)} токен(ами)")
    
    def _get_token_hash(self, token: str) -> str:
        """Получает короткий хеш токена для идентификации"""
        return token[:10] + "..." if len(token) > 10 else token
    
    def get_current_token(self) -> Optional[str]:
        """Возвращает текущий активный токен"""
        if not self.tokens:
            return None
        return self.tokens[self.current_index]
    
    def update_token_stats(self, token: str, remaining: Optional[int], reset: Optional[int], limit: Optional[int]):
        """Обновляет статистику rate limit для токена"""
        token_hash = self._get_token_hash(token)
        if token_hash not in self.token_stats:
            self.token_stats[token_hash] = {}
        
        if remaining is not None:
            self.token_stats[token_hash]["remaining"] = remaining
        if reset is not None:
            self.token_stats[token_hash]["reset"] = reset
        if limit is not None:
            self.token_stats[token_hash]["limit"] = limit
    
    def get_token_wait_time(self, token: str) -> Optional[int]:
        """Возвращает время ожидания до сброса rate limit для токена в секундах"""
        token_hash = self._get_token_hash(token)
        if token_hash not in self.token_stats:
            return None
        
        stats = self.token_stats[token_hash]
        reset_time = stats.get("reset", 0)
        current_time = int(time.time())
        
        if reset_time > current_time:
            return reset_time - current_time
        return None
    
    def get_available_token(self) -> Optional[Tuple[str, Optional[int]]]:
        """Возвращает доступный токен и время ожидания если все исчерпаны
        
        Returns:
            Tuple (token, wait_time) или None если нет доступных токенов
        """
        if not self.tokens:
            return None
        
        # Проверяем все токены, начиная с текущего
        checked = 0
        while checked < len(self.tokens):
            token = self.tokens[self.current_index]
            wait_time = self.get_token_wait_time(token)
            
            # Если токен доступен (нет ожидания или ожидание закончилось)
            if wait_time is None or wait_time <= 0:
                return (token, None)
            
            # Если нужно ждать, проверяем следующий токен
            checked += 1
            self.current_index = (self.current_index + 1) % len(self.tokens)
        
        # Все токены исчерпаны, возвращаем токен с минимальным временем ожидания
        min_wait_time = None
        best_token = None
        
        for token in self.tokens:
            wait_time = self.get_token_wait_time(token)
            if wait_time is not None:
                if min_wait_time is None or wait_time < min_wait_time:
                    min_wait_time = wait_time
                    best_token = token
        
        if best_token:
            # Устанавливаем индекс на лучший токен
            self.current_index = self.tokens.index(best_token)
            return (best_token, min_wait_time)
        
        # Если нет статистики, возвращаем текущий токен
        return (self.tokens[self.current_index], None)
    
    def switch_to_next_token(self):
        """Переключается на следующий токен"""
        if len(self.tokens) > 1:
            self.current_index = (self.current_index + 1) % len(self.tokens)
            logger.info(f"Переключение на токен {self.current_index + 1}/{len(self.tokens)}")

