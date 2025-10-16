class ApiError(Exception):
    """Ошибка при работетс API."""


class TokenError(Exception):
    """Ошибка при отсутствии необходимых переменных окружения"""