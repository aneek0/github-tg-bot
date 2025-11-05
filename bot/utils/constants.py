"""Константы для бота"""

# Rate limits GitHub API
RATE_LIMIT_WITH_TOKEN = 5000  # Запросов в час с токеном
RATE_LIMIT_WITHOUT_TOKEN = 60  # Запросов в час без токена

# Таймауты и задержки
RATE_LIMIT_WAIT_THRESHOLD = 300  # 5 минут в секундах - если ждать больше, пропускаем запрос
DELAY_BETWEEN_REPO_CHECKS = 2  # Задержка между проверками репозиториев в секундах

# Размеры данных
BODY_PREVIEW_LENGTH = 200  # Длина превью описания в сообщениях
RELEASE_BODY_PREVIEW_LENGTH = 300  # Длина превью описания релиза

