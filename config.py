import os
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# Токен бота от BotFather
BOT_TOKEN = os.getenv('BOT_TOKEN')

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
SUPPORTED_CURRENCIES = ['USD', 'EUR', 'CNY']
SUPPORTED_CRYPTO = ['BTC', 'TON', 'SOL', 'USDT']
SUPPORTED_STOCKS = ['SBER', 'YDEX', 'VKCO', 'T', 'GAZP', 'GMKN', 'ROSN', 'LKOH', 'MTSS', 'MFON', 'PIKK', 'SMLT', 'TGLD@', 'TOFZ@', 'DOMRF']

# Настройки сохранения данных
SAVE_DEBOUNCE_DELAY = 5  # Задержка перед сохранением данных (секунды)

# Fallback курсы валют (используются только при полной недоступности API)
# Эти значения можно переопределить через переменные окружения
FALLBACK_USD_RUB_RATE = float(os.getenv('FALLBACK_USD_RUB_RATE', '92.0'))  # Более актуальное значение (2024-2025)

# Соотношения для расчетов
GOLD_SILVER_RATIO = float(os.getenv('GOLD_SILVER_RATIO', '80.0'))  # Среднее историческое соотношение
USO_TO_BRENT_MULTIPLIER = float(os.getenv('USO_TO_BRENT_MULTIPLIER', '1.35'))  # Реальное соотношение USO ETF к Brent

# Минимальные и максимальные значения для валидации fallback курсов
MIN_USD_RUB_RATE = 50.0
MAX_USD_RUB_RATE = 200.0
MIN_GOLD_SILVER_RATIO = 15.0
MAX_GOLD_SILVER_RATIO = 100.0
MIN_USO_TO_BRENT_MULTIPLIER = 0.5
MAX_USO_TO_BRENT_MULTIPLIER = 2.0

# Файл для хранения последних известных значений
LAST_KNOWN_RATES_FILE = 'last_known_rates.json'

if not BOT_TOKEN:
    raise ValueError("Необходимо установить BOT_TOKEN в переменных окружения или в файле .env") 
