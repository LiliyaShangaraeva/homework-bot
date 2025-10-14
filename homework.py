import logging
import os
import sys
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
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

last_error_message = None


def send_error_to_telegram(bot, error_message):
    """Отправляет сообщение об ошибке в Telegram."""
    global last_error_message
    if last_error_message == error_message:
        return
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                         text=f'Ошибка: {error_message}')
        logger.info(
            f'Сообщение об ошибке отправлено в Telegram: {error_message}'
        )
        last_error_message = error_message
    except Exception as error:
        logger.error(
            f'Не удалось отправить сообщение об ошибке в Telegram: {error}'
        )


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    for name, value in tokens.items():
        if not value:
            logger.critical(
                f"Отсутствует обязательная переменная окружения:'{name}'. "
                "Программа принудительно остановлена."
            )
            return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Сообщение отправлено: {message}')
    except Exception as error:
        logger.error(f'Ошибка при отправке сообщения: {error}')


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}

    try:
        logger.info(f'Запрос к API: {ENDPOINT} с from_date={timestamp}')
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
        if response.status_code != HTTPStatus.OK:
            raise Exception(
                f'Запрос к API завершился с кодом {response.status_code}'
            )
        return response.json()
    except requests.RequestException as error:
        logger.error(f'Ошибка при запросе к API: {error}')
        return None


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API не является словарём.')
    if 'homeworks' not in response:
        raise KeyError('Отсутствует ключ "homeworks".')

    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        raise TypeError('Значение "homeworks" не является списком.')
    if not homeworks:
        logger.debug('Нет новых домашних работ.')
        return None
    if not isinstance(homeworks[0], dict):
        raise TypeError('Первая домашняя работа не является словарём.')

    return homeworks[0]


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
    if not check_tokens():
        exit()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework is not None:
                message = parse_status(homework)
                send_message(bot, message)
            if 'current_date' in response:
                timestamp = response['current_date']
            logger.debug(f'Новый запрос через {RETRY_PERIOD} секунд.')
            time.sleep(RETRY_PERIOD)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            send_error_to_telegram(bot, message)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
