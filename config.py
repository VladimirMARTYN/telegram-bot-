import os
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# Токен бота от BotFather
BOT_TOKEN = os.getenv('BOT_TOKEN')

# OpenAI API ключ для ChatGPT
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Администратор бота
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', '0'))

# API ключи для внешних сервисов
METALPRICEAPI_KEY = os.getenv('METALPRICEAPI_KEY', 'demo')
API_NINJAS_KEY = os.getenv('API_NINJAS_KEY', 'demo')
FMP_API_KEY = os.getenv('FMP_API_KEY', 'demo')
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_KEY', 'demo')
EIA_API_KEY = os.getenv('EIA_API_KEY', 'demo')

# Константы для настроек бота
DEFAULT_THRESHOLD = 2.0  # Порог изменений по умолчанию (%)
PRICE_CHECK_INTERVAL = 1800  # Интервал проверки изменений цен (30 минут в секундах)
DEFAULT_DAILY_TIME = '09:00'  # Время ежедневной сводки по умолчанию
DEFAULT_TIMEZONE = 'Europe/Moscow'  # Часовой пояс по умолчанию
URALS_DISCOUNT = 3.5  # Дисконт Urals к Brent (USD)

# Настройки кэширования
CACHE_TTL_DEFAULT = 60  # Время жизни кэша по умолчанию (секунды)
CACHE_TTL_CURRENCIES = 300  # Кэш для валют (5 минут)
CACHE_TTL_CRYPTO = 60  # Кэш для криптовалют (1 минута)
CACHE_TTL_STOCKS = 300  # Кэш для акций (5 минут)
CACHE_TTL_COMMODITIES = 300  # Кэш для товаров (5 минут)
CACHE_TTL_INDICES = 300  # Кэш для индексов (5 минут)

# Настройки retry для API запросов
API_RETRY_ATTEMPTS = 3  # Количество попыток
API_RETRY_DELAY_MIN = 2  # Минимальная задержка между попытками (секунды)
API_RETRY_DELAY_MAX = 10  # Максимальная задержка между попытками (секунды)
API_TIMEOUT = 10  # Таймаут запросов (секунды)

# Поддерживаемые активы
SUPPORTED_CURRENCIES = ['USD', 'EUR', 'CNY', 'GBP']
SUPPORTED_CRYPTO = ['BTC', 'ETH', 'TON', 'XRP', 'ADA', 'SOL', 'DOGE', 'USDT']
SUPPORTED_STOCKS = ['SBER', 'YDEX', 'VKCO', 'T', 'GAZP', 'GMKN', 'ROSN', 'LKOH', 'MTSS', 'MFON', 'PIKK', 'SMLT']

# Настройки сохранения данных
SAVE_DEBOUNCE_DELAY = 5  # Задержка перед сохранением данных (секунды)

if not BOT_TOKEN:
    raise ValueError("Необходимо установить BOT_TOKEN в переменных окружения или в файле .env") 

if not OPENAI_API_KEY:
    print("⚠️ ВНИМАНИЕ: OPENAI_API_KEY не установлен. ChatGPT функции будут недоступны.") 