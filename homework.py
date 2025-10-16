import logging
import os
import sys
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot
from telebot.apihelper import ApiException

from exeptions import ApiError, TokenError

logger = logging.getLogger(__name__)
load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    error_tokens = []
    for name, value in tokens.items():
        if not value:
            error_tokens.append(name)
    if error_tokens:
        message = (
            "Отсутствуют обязательные переменные окружения: "
            f"{error_tokens}. Программа принудительно остановлена."
        )
        logger.critical(message)
        raise TokenError(message)


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        logger.debug(f'Начало отправки сообщения: {message}')
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Сообщение отправлено: {message}')
        return True
    except (ApiException, requests.RequestException) as error:
        logger.error(f'Ошибка при отправке сообщения: {error}')
        return False


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}
    logger.info(f'Запрос к API: {ENDPOINT} с from_date={timestamp}')

    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as error:
        raise ApiError(f'Ошибка при запросе к API: {error}')
    if response.status_code != HTTPStatus.OK:
        raise ApiError(
            f'Запрос к API завершился с кодом {response.status_code}'
        )
    try:
        return response.json()
    except ValueError as error:
        raise ApiError(f'Ошибка парсинга JSON: {error}')


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(
            'Ответ API не является словарём. '
            f'Получено: {type(response).__name__}'
        )
    if 'homeworks' not in response:
        raise KeyError('Отсутствует ключ "homeworks".')

    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        raise TypeError(
            'Значение "homeworks" не является списком.'
            f'Получено: {type(homeworks).__name__}'
        )

    return homeworks


def parse_status(homework):
    """Извлекает статус конкретной домашней работы."""
    status = homework.get('status')
    if status is None:
        raise KeyError('Отсутствует ключ "status".')
    verdict = HOMEWORK_VERDICTS.get(status)
    if verdict is None:
        raise ValueError(f'Неизвестный статус домашней работы: {status}')
    homework_name = homework.get('homework_name')
    if homework_name is None:
        raise KeyError('Отсутствует ключ "homework_name".')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    logger.info('Бот запущен.')
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot, message):
                    timestamp = response.get('current_date', timestamp)
                    last_error_message = None

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if last_error_message != str(error):
                send_message(bot, message)
                logger.info(
                    f'Сообщение об ошибке отправлено в Telegram: {error}'
                )
                last_error_message = str(error)

        finally:
            logger.debug(f'Новый запрос через {RETRY_PERIOD} секунд.')
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )

    main()
