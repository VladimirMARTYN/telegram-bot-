import os
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# Токен бота от BotFather
BOT_TOKEN = os.getenv('BOT_TOKEN')

# OpenAI API ключ для ChatGPT
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not BOT_TOKEN:
    raise ValueError("Необходимо установить BOT_TOKEN в переменных окружения или в файле .env")

if not OPENAI_API_KEY:
    print("⚠️ ВНИМАНИЕ: OPENAI_API_KEY не установлен. ChatGPT функции будут недоступны.") 