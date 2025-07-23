import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, OPENAI_API_KEY
import openai
import asyncio
from datetime import datetime

# Время запуска бота
BOT_START_TIME = datetime.now()

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка OpenAI
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    CHATGPT_ENABLED = True
    logger.info("✅ ChatGPT функции активированы")
else:
    CHATGPT_ENABLED = False
    logger.warning("⚠️ ChatGPT функции отключены - не установлен OPENAI_API_KEY")

# ТВОЙ Telegram ID
ADMIN_USER_ID = 34331814  # Владелец бота

# Настройки ChatGPT
CHATGPT_MODEL = "gpt-3.5-turbo"
MAX_TOKENS = 1000
MAX_REQUESTS_PER_USER = 10  # лимит запросов для обычных пользователей
user_requests = {}  # счетчик запросов пользователей

# Доступные модели OpenAI с описанием и стоимостью
AVAILABLE_MODELS = {
    # GPT-4 модели (самые умные)
    "gpt-4o": {
        "name": "GPT-4o",
        "description": "🚀 Новейшая, быстрая и умная модель",
        "cost": "$0.005/$0.015 за 1K токенов",
        "speed": "Быстрая",
        "max_tokens": 4096
    },
    "gpt-4o-mini": {
        "name": "GPT-4o Mini", 
        "description": "⚡ Быстрая и дешевая GPT-4 модель",
        "cost": "$0.00015/$0.0006 за 1K токенов",
        "speed": "Очень быстрая",
        "max_tokens": 16384
    },
    "gpt-4-turbo": {
        "name": "GPT-4 Turbo",
        "description": "🧠 Мощная GPT-4 с большим контекстом",
        "cost": "$0.01/$0.03 за 1K токенов", 
        "speed": "Средняя",
        "max_tokens": 4096
    },
    "gpt-4": {
        "name": "GPT-4",
        "description": "🎯 Классическая GPT-4 модель",
        "cost": "$0.03/$0.06 за 1K токенов",
        "speed": "Медленная",
        "max_tokens": 4096
    },
    
    # GPT-3.5 модели (быстрые и дешевые)
    "gpt-3.5-turbo": {
        "name": "GPT-3.5 Turbo",
        "description": "💨 Быстрая и дешевая модель",
        "cost": "$0.001/$0.002 за 1K токенов",
        "speed": "Очень быстрая", 
        "max_tokens": 4096
    },
    "gpt-3.5-turbo-16k": {
        "name": "GPT-3.5 Turbo 16K",
        "description": "📚 Большой контекст для длинных текстов",
        "cost": "$0.003/$0.004 за 1K токенов",
        "speed": "Быстрая",
        "max_tokens": 16384
    },
    
    # O1 модели (reasoning)
    "o1-preview": {
        "name": "O1 Preview",
        "description": "🔬 Модель для сложных рассуждений",
        "cost": "$0.015/$0.06 за 1K токенов",
        "speed": "Очень медленная",
        "max_tokens": 32768
    },
    "o1-mini": {
        "name": "O1 Mini", 
        "description": "🤔 Быстрая модель для рассуждений",
        "cost": "$0.003/$0.012 за 1K токенов",
        "speed": "Медленная",
        "max_tokens": 65536
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    chatgpt_status = "✅ ChatGPT активен" if CHATGPT_ENABLED else "❌ ChatGPT отключен"
    
    await update.message.reply_html(
        f"🤖 <b>Привет! Я умный бот с AI!</b>\n\n"
        f"📋 <b>Основные команды:</b>\n"
        f"• /ai [вопрос] - Задать вопрос ChatGPT\n"
        f"• /gpt [вопрос] - Развернутый ответ от AI\n"
        f"• /my_id - Узнать свой ID\n"
        f"• /help - Показать это меню\n\n"
        f"🛠️ <b>Утилиты:</b>\n"
        f"• /ping - Проверить работу бота\n"
        f"• /currency - Курсы валют ЦБ РФ\n"
        f"• /uptime - Время работы бота\n"
        f"• /notify [сообщение] - Написать админу\n\n"
        f"🔧 <b>Статус:</b> {chatgpt_status}\n\n"
        f"💡 <b>Пример:</b> /ai Что такое Python?"
    )

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать ID пользователя"""
    user_id = update.effective_user.id
    await update.message.reply_text(f"Твой ID: {user_id}")

# ========== CHATGPT ФУНКЦИИ ==========

async def check_user_limit(user_id: int) -> bool:
    """Проверить лимит запросов пользователя"""
    if user_id == ADMIN_USER_ID:
        return True  # админу без лимитов
    
    current_count = user_requests.get(user_id, 0)
    return current_count < MAX_REQUESTS_PER_USER

async def increment_user_requests(user_id: int):
    """Увеличить счетчик запросов пользователя"""
    if user_id != ADMIN_USER_ID:
        user_requests[user_id] = user_requests.get(user_id, 0) + 1

async def ask_chatgpt(prompt: str) -> str:
    """Отправить запрос к ChatGPT и получить ответ"""
    try:
        # Проверяем, что модель существует
        if CHATGPT_MODEL not in AVAILABLE_MODELS:
            return f"❌ Ошибка: неизвестная модель {CHATGPT_MODEL}. Используй /list_models"
        
        # Адаптируем параметры для разных типов моделей
        model_info = AVAILABLE_MODELS[CHATGPT_MODEL]
        actual_max_tokens = min(MAX_TOKENS, model_info['max_tokens'])
        
        # O1 модели требуют особой обработки
        if CHATGPT_MODEL.startswith("o1"):
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=CHATGPT_MODEL,
                messages=[
                    {"role": "user", "content": f"Ответь на русском языке: {prompt}"}
                ],
                max_completion_tokens=actual_max_tokens
            )
        else:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=CHATGPT_MODEL,
                messages=[
                    {"role": "system", "content": "Ты умный помощник. Отвечай кратко и по делу на русском языке."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=actual_max_tokens,
                temperature=0.7
            )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"Ошибка ChatGPT API: {e}")
        
        # Более понятные сообщения об ошибках
        if "insufficient_quota" in error_msg or "quota" in error_msg:
            return "❌ Превышена квота OpenAI. Проверь баланс на platform.openai.com"
        elif "invalid_api_key" in error_msg:
            return "❌ Неверный API ключ OpenAI"
        elif "model_not_found" in error_msg:
            return f"❌ Модель {CHATGPT_MODEL} недоступна. Используй /list_models"
        elif "rate_limit" in error_msg:
            return "❌ Превышен лимит запросов к OpenAI. Подожди немного"
        else:
            return f"❌ Ошибка AI: {str(e)}"

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /ai - короткий вопрос к ChatGPT"""
    if not CHATGPT_ENABLED:
        await update.message.reply_text("❌ ChatGPT функции отключены. Администратор должен добавить OPENAI_API_KEY.")
        return
    
    user_id = update.effective_user.id
    
    if not await check_user_limit(user_id):
        await update.message.reply_text(
            f"❌ Превышен лимит запросов ({MAX_REQUESTS_PER_USER})!\n"
            f"Текущие запросы: {user_requests.get(user_id, 0)}"
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "🤖 Задай вопрос ChatGPT!\n\n"
            "Пример: /ai Объясни квантовую физику"
        )
        return
    
    question = " ".join(context.args)
    
    # Показываем, что бот печатает
    await update.message.reply_text("🤔 Думаю...")
    
    # Отправляем запрос к ChatGPT
    await increment_user_requests(user_id)
    answer = await ask_chatgpt(question)
    
    # Форматируем ответ
    response = f"❓ <b>Вопрос:</b> {question}\n\n🤖 <b>ChatGPT:</b>\n{answer}"
    
    if len(response) > 4000:  # лимит Telegram
        response = response[:3900] + "...\n\n⚠️ <i>Ответ обрезан</i>"
    
    await update.message.reply_html(response)

async def gpt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /gpt - развернутый ответ ChatGPT"""
    if not CHATGPT_ENABLED:
        await update.message.reply_text("❌ ChatGPT функции отключены.")
        return
    
    user_id = update.effective_user.id
    
    if not await check_user_limit(user_id):
        await update.message.reply_text(f"❌ Превышен лимит запросов ({MAX_REQUESTS_PER_USER})!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "🧠 Развернутый ответ от ChatGPT!\n\n"
            "Пример: /gpt Напиши план изучения Python"
        )
        return
    
    question = " ".join(context.args)
    await update.message.reply_text("🧠 Готовлю развернутый ответ...")
    
    # Добавляем инструкцию для более подробного ответа
    detailed_prompt = f"Дай подробный, развернутый ответ на вопрос: {question}"
    
    await increment_user_requests(user_id)
    answer = await ask_chatgpt(detailed_prompt)
    
    response = f"❓ <b>Вопрос:</b> {question}\n\n🧠 <b>Развернутый ответ:</b>\n{answer}"
    
    if len(response) > 4000:
        response = response[:3900] + "...\n\n⚠️ <i>Ответ обрезан</i>"
    
    await update.message.reply_html(response)

async def reset_limits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сбросить лимиты пользователей (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    user_requests.clear()
    await update.message.reply_text("✅ Лимиты всех пользователей сброшены!")

async def model_recommend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Рекомендации по выбору модели"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    recommendations = """
🎯 <b>Рекомендации по выбору модели:</b>

💰 <b>Экономия средств:</b>
• gpt-3.5-turbo - самая дешевая ($0.001)
• gpt-4o-mini - лучший баланс цена/качество

⚡ <b>Высокая скорость:</b>
• gpt-4o-mini - очень быстрая GPT-4
• gpt-3.5-turbo - максимальная скорость

🧠 <b>Сложные задачи:</b>
• o1-preview - математика, программирование
• o1-mini - логические рассуждения

🚀 <b>Универсальное использование:</b>
• gpt-4o - новейшая, быстрая и умная
• gpt-4-turbo - большой контекст (128k токенов)

📚 <b>Длинные тексты:</b>
• gpt-3.5-turbo-16k - дешево для больших текстов
• gpt-4-turbo - максимальный контекст

💡 <b>Быстрая смена:</b>
/quick_model 4o-mini - лучший баланс
/quick_model 4o - топовое качество  
/quick_model 35 - максимальная экономия
    """
    await update.message.reply_html(recommendations)

async def quick_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Быстрая смена модели (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    global CHATGPT_MODEL
    
    if not context.args:
        # Показать популярные модели для быстрой смены
        quick_info = f"""
🚀 <b>Быстрая смена модели:</b>

<b>Популярные модели:</b>
/quick_model 4o - GPT-4o (новейшая)
/quick_model 4o-mini - GPT-4o Mini (быстрая)
/quick_model 35 - GPT-3.5-turbo (дешевая)
/quick_model 4 - GPT-4 (классическая)

🔄 <b>Текущая:</b> {CHATGPT_MODEL}
💡 <b>Все модели:</b> /list_models
        """
        await update.message.reply_html(quick_info)
        return
    
    model_shortcuts = {
        "4o": "gpt-4o",
        "4o-mini": "gpt-4o-mini", 
        "35": "gpt-3.5-turbo",
        "4": "gpt-4",
        "4-turbo": "gpt-4-turbo",
        "o1": "o1-preview",
        "o1-mini": "o1-mini"
    }
    
    shortcut = context.args[0].lower()
    
    if shortcut not in model_shortcuts:
        await update.message.reply_text(
            f"❌ Неизвестный ярлык!\n"
            f"Доступно: {', '.join(model_shortcuts.keys())}"
        )
        return
    
    new_model = model_shortcuts[shortcut]
    old_model = CHATGPT_MODEL
    CHATGPT_MODEL = new_model
    
    model_info = AVAILABLE_MODELS[new_model]
    await update.message.reply_html(
        f"⚡ <b>Быстрая смена модели!</b>\n\n"
        f"🔄 {old_model} ➡️ <b>{model_info['name']}</b>\n"
        f"📝 {model_info['description']}\n"
        f"💰 {model_info['cost']}"
    )

async def list_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать все доступные модели ChatGPT"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    models_info = "🤖 <b>Все доступные модели OpenAI:</b>\n\n"
    
    # Группируем модели по типам
    gpt4_models = {k: v for k, v in AVAILABLE_MODELS.items() if k.startswith("gpt-4")}
    gpt35_models = {k: v for k, v in AVAILABLE_MODELS.items() if k.startswith("gpt-3.5")}
    o1_models = {k: v for k, v in AVAILABLE_MODELS.items() if k.startswith("o1")}
    
    # GPT-4 модели
    models_info += "🚀 <b>GPT-4 Модели:</b>\n"
    for model_id, info in gpt4_models.items():
        current_mark = "🟢 " if model_id == CHATGPT_MODEL else ""
        models_info += f"{current_mark}• <b>{info['name']}</b> ({model_id})\n"
        models_info += f"   {info['description']}\n"
        models_info += f"   💰 {info['cost']} | ⚡ {info['speed']}\n\n"
    
    # GPT-3.5 модели  
    models_info += "💨 <b>GPT-3.5 Модели:</b>\n"
    for model_id, info in gpt35_models.items():
        current_mark = "🟢 " if model_id == CHATGPT_MODEL else ""
        models_info += f"{current_mark}• <b>{info['name']}</b> ({model_id})\n"
        models_info += f"   {info['description']}\n"
        models_info += f"   💰 {info['cost']} | ⚡ {info['speed']}\n\n"
    
    # O1 модели
    models_info += "🔬 <b>O1 Модели (Reasoning):</b>\n"
    for model_id, info in o1_models.items():
        current_mark = "🟢 " if model_id == CHATGPT_MODEL else ""
        models_info += f"{current_mark}• <b>{info['name']}</b> ({model_id})\n"
        models_info += f"   {info['description']}\n"
        models_info += f"   💰 {info['cost']} | ⚡ {info['speed']}\n\n"
    
    models_info += "🟢 - <i>текущая модель</i>\n"
    models_info += "💡 <b>Смена модели:</b> /chatgpt_settings model [название]"
    
    # Разбиваем на части если слишком длинное сообщение
    if len(models_info) > 4000:
        # Отправляем по частям
        parts = [models_info[i:i+3800] for i in range(0, len(models_info), 3800)]
        for i, part in enumerate(parts):
            if i == 0:
                await update.message.reply_html(part)
            else:
                await update.message.reply_html(f"<i>Продолжение...</i>\n\n{part}")
    else:
        await update.message.reply_html(models_info)

async def chatgpt_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Настройки ChatGPT (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    global MAX_REQUESTS_PER_USER, MAX_TOKENS, CHATGPT_MODEL
    
    if not context.args:
        # Показать текущие настройки
        current_model_info = AVAILABLE_MODELS.get(CHATGPT_MODEL, {})
        model_description = current_model_info.get('description', 'Неизвестная модель')
        model_cost = current_model_info.get('cost', 'Неизвестно')
        
        settings_info = f"""
🤖 <b>Настройки ChatGPT:</b>

📊 <b>Статус:</b> {'✅ Активен' if CHATGPT_ENABLED else '❌ Отключен'}
🔄 <b>Текущая модель:</b> {CHATGPT_MODEL}
   {model_description}
   💰 {model_cost}
🎯 <b>Макс. токенов:</b> {MAX_TOKENS}
👥 <b>Лимит на пользователя:</b> {MAX_REQUESTS_PER_USER}

💡 <b>Управление:</b>
/list_models - Все доступные модели
/chatgpt_settings limit [число] - Лимит запросов  
/chatgpt_settings tokens [число] - Макс. токенов
/chatgpt_settings model [название] - Сменить модель

<b>Примеры:</b>
/chatgpt_settings model gpt-4o
/chatgpt_settings limit 20
        """
        await update.message.reply_html(settings_info)
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Неправильный формат!\nПример: /chatgpt_settings limit 20")
        return
    
    setting = context.args[0].lower()
    value = context.args[1]
    
    try:
        if setting == "limit":
            MAX_REQUESTS_PER_USER = int(value)
            await update.message.reply_text(f"✅ Лимит изменен на {MAX_REQUESTS_PER_USER} запросов на пользователя")
        
        elif setting == "tokens":
            new_tokens = int(value)
            if new_tokens > 100000:
                await update.message.reply_text("❌ Слишком много токенов! Максимум 100,000")
                return
            MAX_TOKENS = new_tokens
            await update.message.reply_text(f"✅ Максимальное количество токенов изменено на {MAX_TOKENS}")
        
        elif setting == "model":
            if value not in AVAILABLE_MODELS:
                available_list = ", ".join(AVAILABLE_MODELS.keys())
                await update.message.reply_text(
                    f"❌ Неизвестная модель!\n\n"
                    f"📋 <b>Доступные модели:</b>\n{available_list}\n\n"
                    f"💡 Используй /list_models для подробной информации"
                )
                return
            
            old_model = CHATGPT_MODEL
            CHATGPT_MODEL = value
            model_info = AVAILABLE_MODELS[value]
            
            await update.message.reply_html(
                f"✅ <b>Модель изменена!</b>\n\n"
                f"🔄 <b>Было:</b> {old_model}\n"
                f"🚀 <b>Стало:</b> {model_info['name']} ({value})\n"
                f"📝 {model_info['description']}\n"
                f"💰 <b>Стоимость:</b> {model_info['cost']}\n"
                f"⚡ <b>Скорость:</b> {model_info['speed']}"
            )
        
        else:
            await update.message.reply_text("❌ Неизвестная настройка! Доступно: limit, tokens, model")
    
    except ValueError:
        await update.message.reply_text("❌ Неправильное значение! Число должно быть целым.")

# ========== КОНЕЦ CHATGPT ФУНКЦИЙ ==========

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ-команды (только для админа)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    chatgpt_status = "✅ Активен" if CHATGPT_ENABLED else "❌ Отключен"
    
    admin_commands = f"""
🔧 <b>АДМИН КОМАНДЫ:</b>

<b>📊 Управление:</b>
/admin_help - Это меню
/stats - Статистика бота
/broadcast [сообщение] - Рассылка всем

<b>🤖 ChatGPT управление:</b> {chatgpt_status}
/ai [вопрос] - Задать вопрос ChatGPT
/gpt [вопрос] - Развернутый ответ
/quick_model [ярлык] - Быстрая смена модели
/list_models - Все доступные модели  
/model_recommend - Рекомендации по выбору
/chatgpt_settings - Настройки ChatGPT
/reset_limits - Сбросить лимиты пользователей

<b>🛠️ AI Разработка:</b>
/add_feature [описание] - Создать функцию через AI
/edit_feature [команда] - [новое описание] - Редактировать функцию
/list_features - Список созданных функций
/remove_feature [команда] - Удалить функцию
/generation_stats - Статистика AI генерации

<b>🤖 Автоисправление ошибок:</b>
/auto_fix [функция] - Диагностика и исправление через ChatGPT
/apply_fix [функция] - Применить готовые исправления
/show_diff [функция] - Сравнить код до и после
/cancel_fix [функция] - Отменить исправления

<b>🔧 Диагностика:</b>
/debug_status - Полная диагностика системы
/debug_errors - Отладка записи ошибок функций
/uptime - Время работы бота
/system_info - Информация о системе
/ping - Тест базовых функций
/currency - Тест API запросов

💡 <b>Примеры:</b>
/ai Объясни алгоритм сортировки
/add_feature курс - показать курс доллара и евро к рублю
/auto_fix currencybk - исправить ошибки в функции через ChatGPT
/broadcast Обновление бота завершено!
    """
    await update.message.reply_html(admin_commands)

async def generate_function_code(description: str, command_name: str) -> str:
    """Генерирует код функции через ChatGPT"""
    system_prompt = """
Ты опытный Python разработчик Telegram ботов. Создай полезную функцию для Telegram бота.

СТРОГО СЛЕДУЙ ЭТОМУ ФОРМАТУ:

```python
async def {command_name}_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    \"\"\"Описание функции\"\"\"
    # твой код здесь
    await update.message.reply_text("твой ответ")
```

ТРЕБОВАНИЯ:
1. Функция должна быть async
2. Обязательно используй await для Telegram операций  
3. Используй reply_text или reply_html для ответов
4. Добавь обработку ошибок try/except для внешних запросов
5. Можешь использовать ЛЮБЫЕ библиотеки: requests, bs4, json, datetime, random, re, os, etc.
6. Для API запросов используй requests или aiohttp
7. Делай функции максимально полезными и функциональными
8. Отвечай только кодом без дополнительных объяснений

Примеры:
```python
async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    \"\"\"Получить погоду в городе\"\"\"
    import requests
    try:
        if context.args:
            city = " ".join(context.args)
            # Используй реальный API погоды
            response = requests.get(f"http://wttr.in/{city}?format=3")
            await update.message.reply_text(f"🌤 {response.text}")
        else:
            await update.message.reply_text("Укажи город: /weather Москва")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
```
"""

    user_prompt = f"""
Создай команду /{command_name} для Telegram бота.

Описание: {description}

Функция должна называться {command_name}_command
"""

    try:
        response = await ask_chatgpt(f"{system_prompt}\n\n{user_prompt}")
        return response
    except Exception as e:
        logger.error(f"Ошибка генерации кода: {e}")
        return f"❌ Ошибка генерации кода: {str(e)}"

def validate_generated_code(code: str) -> tuple[bool, str]:
    """Базовая проверка структуры сгенерированного кода"""
    # Убираем все проверки безопасности для личного использования
    
    # Проверяем только базовую структуру функции
    if 'async def' not in code:
        return False, "Код должен содержать async функцию"
    
    if 'await update.message.reply' not in code:
        return False, "Функция должна отправлять ответ пользователю"
    
    # Все остальное разрешаем - requests, API, файлы, что угодно!
    return True, "Код прошел проверку"

async def add_feature(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """AI-генератор новых функций для бота (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    if not CHATGPT_ENABLED:
        await update.message.reply_text("❌ ChatGPT отключен. Генерация функций недоступна.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "🤖 <b>AI Генератор функций</b>\n\n"
            "Опиши функцию в формате:\n"
            "<code>/add_feature [название] - [подробное описание]</code>\n\n"
            "<b>Примеры:</b>\n"
            "• /add_feature погода - получить прогноз погоды для любого города\n"
            "• /add_feature курс - узнать курс валют доллар/евро к рублю\n"
            "• /add_feature новости - последние новости из России\n"
            "• /add_feature переводчик - переводить текст на русский язык\n"
            "• /add_feature qr - генерировать QR код из текста\n"
            "• /add_feature пароль - создать безопасный пароль\n\n"
            "💡 Я сгенерирую полноценный код с API запросами через ChatGPT!",
            parse_mode='HTML'
        )
        return
    
    # Парсим команду: первое слово - название команды, остальное - описание
    args = " ".join(context.args)
    parts = args.split(' - ', 1)
    
    if len(parts) == 2:
        command_name, description = parts
        command_name = command_name.strip().lower()
        description = description.strip()
    else:
        # Если нет разделителя, используем первое слово как команду
        words = args.split()
        command_name = words[0].lower()
        description = " ".join(words[1:]) if len(words) > 1 else f"Функция {command_name}"
    
    # Проверяем, что команда не существует
    if command_name in dynamic_commands:
        await update.message.reply_text(f"❌ Команда /{command_name} уже существует!")
        return
    
    await update.message.reply_text(
        f"🧠 <b>Генерирую функцию...</b>\n\n"
        f"📝 <b>Команда:</b> /{command_name}\n"
        f"💭 <b>Описание:</b> {description}\n\n"
        f"⏳ Создаю код через ChatGPT...",
        parse_mode='HTML'
    )
    
    # Генерируем код
    generated_code = await generate_function_code(description, command_name)
    
    # Проверяем базовую структуру кода
    is_valid, validation_message = validate_generated_code(generated_code)
    
    if not is_valid:
        await update.message.reply_text(
            f"❌ <b>Код некорректный!</b>\n\n"
            f"🚫 <b>Причина:</b> {validation_message}\n\n"
            f"🔄 Попробуй другое описание или измени запрос.",
            parse_mode='HTML'
        )
        return
    
    # Извлекаем чистый код функции
    try:
        # Ищем код между ```python и ```
        if '```python' in generated_code:
            code_start = generated_code.find('```python') + 9
            code_end = generated_code.find('```', code_start)
            clean_code = generated_code[code_start:code_end].strip()
        elif '```' in generated_code:
            code_start = generated_code.find('```') + 3
            code_end = generated_code.find('```', code_start)
            clean_code = generated_code[code_start:code_end].strip()
        else:
            clean_code = generated_code.strip()
        
        # Выполняем код с полным доступом ко всем возможностям Python
        local_vars = {
            'Update': Update,
            'ContextTypes': ContextTypes,
            'logger': logger
        }
        
        exec(clean_code, globals(), local_vars)
        
        # Находим созданную функцию
        function_name = f"{command_name}_command"
        if function_name in local_vars:
            new_function = local_vars[function_name]
            
            # Сохраняем функцию
            dynamic_commands[command_name] = new_function
            dynamic_functions[command_name] = new_function
            dynamic_commands[command_name] = {
                'function': new_function,
                'description': description,
                'code': clean_code,
                'created_at': __import__('datetime').datetime.now().isoformat()
            }
            
            # Добавляем в историю
            generation_history.append({
                'command': command_name,
                'description': description,
                'success': True,
                'timestamp': __import__('datetime').datetime.now().isoformat()
            })
            
            await update.message.reply_html(
                f"✅ <b>Функция успешно создана!</b>\n\n"
                f"🎉 <b>Новая команда:</b> /{command_name}\n"
                f"📄 <b>Описание:</b> {description}\n\n"
                f"🔧 <b>Сгенерированный код:</b>\n"
                f"<code>{clean_code[:500]}{'...' if len(clean_code) > 500 else ''}</code>\n\n"
                f"💡 <b>Попробуй прямо сейчас:</b> /{command_name}\n"
                f"📋 <b>Управление:</b> /list_features"
            )
            
        else:
            raise ValueError("Функция не найдена в сгенерированном коде")
    
    except Exception as e:
        error_msg = str(e)
        await update.message.reply_html(
            f"❌ <b>Ошибка выполнения кода:</b>\n\n"
            f"🚫 {error_msg}\n\n"
            f"🔧 <b>Сгенерированный код:</b>\n"
            f"<code>{generated_code[:800]}{'...' if len(generated_code) > 800 else ''}</code>\n\n"
            f"🔄 Попробуй изменить описание функции."
        )
        
        # Добавляем в историю ошибку
        generation_history.append({
            'command': command_name,
            'description': description, 
            'success': False,
            'error': error_msg,
            'timestamp': __import__('datetime').datetime.now().isoformat()
        })

async def list_features(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать список созданных AI функций (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    if not dynamic_commands:
        await update.message.reply_text(
            "📝 <b>Созданные функции:</b>\n\n"
            "Пока нет созданных функций.\n"
            "Используй /add_feature для создания новых!",
            parse_mode='HTML'
        )
        return
    
    features_info = "🤖 <b>AI-созданные функции:</b>\n\n"
    
    for cmd, info in dynamic_commands.items():
        features_info += f"• <b>/{cmd}</b> - {info['description']}\n"
        features_info += f"  📅 {info['created_at'][:16]}\n\n"
    
    features_info += f"📊 <b>Всего функций:</b> {len(dynamic_commands)}\n"
    features_info += "🗑 <b>Управление:</b> /remove_feature [команда]"
    
    await update.message.reply_html(features_info)

async def remove_feature(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удалить AI функцию (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажи команду для удаления!\nПример: /remove_feature weather")
        return
    
    command_name = context.args[0].lower()
    
    if command_name not in dynamic_commands:
        await update.message.reply_text(f"❌ Функция /{command_name} не найдена!")
        return
    
    # Удаляем функцию
    del dynamic_commands[command_name]
    if command_name in dynamic_functions:
        del dynamic_functions[command_name]
    
    await update.message.reply_text(
        f"✅ Функция /{command_name} удалена!\n"
        f"⚠️ Перезапусти бота для полного удаления."
    )

async def generation_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Статистика генерации функций (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    if not generation_history:
        await update.message.reply_text("📊 История генерации функций пуста.")
        return
    
    successful = len([h for h in generation_history if h['success']])
    failed = len([h for h in generation_history if not h['success']])
    
    stats = f"""
📊 <b>Статистика AI генерации:</b>

✅ <b>Успешно:</b> {successful}
❌ <b>Ошибок:</b> {failed}
📝 <b>Всего попыток:</b> {len(generation_history)}
🎯 <b>Успешность:</b> {successful/(len(generation_history))*100:.1f}%

🤖 <b>Активных функций:</b> {len(dynamic_commands)}

📋 <b>Последние 5 попыток:</b>
"""
    
    for entry in generation_history[-5:]:
        status = "✅" if entry['success'] else "❌"
        stats += f"{status} /{entry['command']} - {entry['timestamp'][:16]}\n"
    
    await update.message.reply_html(stats)

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Статистика бота (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    # Расширенная статистика с ChatGPT
    total_ai_requests = sum(user_requests.values())
    active_ai_users = len([u for u in user_requests.values() if u > 0])
    chatgpt_status = "✅ Работает" if CHATGPT_ENABLED else "❌ Отключен"
    
    # Информация о текущей модели
    current_model_info = AVAILABLE_MODELS.get(CHATGPT_MODEL, {})
    model_name = current_model_info.get('name', CHATGPT_MODEL)
    model_cost = current_model_info.get('cost', 'Неизвестно')
    model_speed = current_model_info.get('speed', 'Неизвестно')
    
    stats = f"""
📊 <b>Статистика бота:</b>

👥 <b>Пользователи:</b>
• Всего: {len(user_data)}
• Используют AI: {active_ai_users}

🔄 <b>Активность:</b>
• Всего сообщений: {total_requests}
• AI запросов: {total_ai_requests}

🤖 <b>ChatGPT:</b> {chatgpt_status}
• Модель: {model_name} ({CHATGPT_MODEL})
• Стоимость: {model_cost}
• Скорость: {model_speed}
• Лимит: {MAX_REQUESTS_PER_USER} запросов
• Макс. токенов: {MAX_TOKENS}

⏰ <b>Статус:</b> Работает нормально

💡 <b>Управление:</b> /list_models | /quick_model
    """
    await update.message.reply_html(stats)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Рассылка сообщений (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажи сообщение для рассылки!\nПример: /broadcast Привет всем!")
        return
    
    message = " ".join(context.args)
    sent_count = 0
    
    # Рассылка всем пользователям
    for uid in user_data:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 {message}")
            sent_count += 1
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {uid}: {e}")
    
    await update.message.reply_text(f"✅ Рассылка завершена! Отправлено {sent_count} сообщений.")

# Простая база данных в памяти
user_data = {}
total_requests = 0

# Динамически созданные функции
dynamic_functions = {}
dynamic_commands = {}

# История генерации функций
generation_history = []

# История ошибок для диагностики
function_errors = {}

async def auto_fix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Автоматическое исправление ошибок в AI-функциях через ChatGPT (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    if not CHATGPT_ENABLED:
        await update.message.reply_text("❌ ChatGPT отключен. Автоисправление недоступно.")
        return
    
    if not context.args:
        if not function_errors:
            await update.message.reply_text(
                "❌ <b>Нет записей об ошибках!</b>\n\n"
                "🔍 <b>Для отладки используй:</b>\n"
                "• /debug_errors - проверить систему ошибок\n"
                "• /list_features - показать все функции\n\n"
                "💡 <b>Чтобы получить ошибку:</b>\n"
                "1. Выполни любую AI-функцию с проблемой\n"
                "2. Ошибка автоматически запишется\n"
                "3. Используй /auto_fix [название_функции]",
                parse_mode='HTML'
            )
            return
            
        error_list = "🔧 <b>Функции с ошибками:</b>\n\n"
        for func_name, error_info in function_errors.items():
            error_list += f"• <b>/{func_name}</b> - {error_info['error_type']}\n"
            error_list += f"  📝 {error_info['error_message'][:50]}{'...' if len(error_info['error_message']) > 50 else ''}\n"
            error_list += f"  ⏰ {error_info['timestamp'][:16]}\n\n"
        
        error_list += "💡 <b>Использование:</b>\n<code>/auto_fix [название_функции]</code>\n\n"
        error_list += f"<b>Пример:</b> /auto_fix {list(function_errors.keys())[0] if function_errors else 'stocks'}"
        
        await update.message.reply_html(error_list)
        return
    
    function_name = context.args[0].lower()
    
    # Проверяем, что функция существует
    if function_name not in dynamic_commands:
        await update.message.reply_text(f"❌ Функция /{function_name} не найдена!\nИспользуй /list_features для просмотра функций.")
        return
    
    # Проверяем, есть ли информация об ошибке
    if function_name not in function_errors:
        await update.message.reply_text(f"❌ Нет записей об ошибках для функции /{function_name}!\nСначала выполни функцию, чтобы получить ошибку.")
        return
    
    function_info = dynamic_commands[function_name]
    error_info = function_errors[function_name]
    
    # Показываем процесс диагностики
    fix_msg = await update.message.reply_html(
        f"🔧 <b>АВТОИСПРАВЛЕНИЕ ФУНКЦИИ</b>\n\n"
        f"📝 <b>Функция:</b> /{function_name}\n"
        f"❌ <b>Ошибка:</b> {error_info['error_type']}\n"
        f"📋 <b>Описание ошибки:</b> {error_info['error_message'][:100]}{'...' if len(error_info['error_message']) > 100 else ''}\n\n"
        f"🤖 Анализирую код через ChatGPT..."
    )
    
    # Составляем детальный промпт для диагностики
    diagnostic_prompt = f"""
Ты эксперт по отладке Python кода для Telegram ботов. Проанализируй и исправь следующий код:

ФУНКЦИЯ: {function_name}_command
ОПИСАНИЕ: {function_info['description']}

ТЕКУЩИЙ КОД:
```python
{function_info['code']}
```

ОШИБКА:
Тип: {error_info['error_type']}
Сообщение: {error_info['error_message']}
Время: {error_info['timestamp']}

ЗАДАЧА:
1. Проанализируй причину ошибки
2. Исправь код, сохранив функциональность
3. Улучши обработку ошибок
4. Убедись, что функция работает правильно

ТРЕБОВАНИЯ:
- Функция должна называться ТОЧНО {function_name}_command
- Обязательно async def
- Используй await для Telegram операций
- Добавь try/except для внешних API
- Отвечай ТОЛЬКО исправленным кодом в формате:

```python
async def {function_name}_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # исправленный код
```

БЕЗ дополнительных объяснений!
"""
    
    try:
        # Отправляем запрос к ChatGPT для диагностики
        await fix_msg.edit_text(
            f"🔧 <b>АВТОИСПРАВЛЕНИЕ ФУНКЦИИ</b>\n\n"
            f"📝 <b>Функция:</b> /{function_name}\n"
            f"🤖 Отправляю код на анализ ChatGPT...\n"
            f"⏳ Это может занять до 60 секунд...",
            parse_mode='HTML'
        )
        
        fixed_code = await ask_chatgpt(diagnostic_prompt)
        
        if "❌ Ошибка" in fixed_code or "Таймаут" in fixed_code:
            await fix_msg.edit_text(
                f"❌ <b>Ошибка диагностики!</b>\n\n{fixed_code}",
                parse_mode='HTML'
            )
            return
        
        await fix_msg.edit_text(
            f"🔧 <b>АВТОИСПРАВЛЕНИЕ ФУНКЦИИ</b>\n\n"
            f"📝 <b>Функция:</b> /{function_name}\n"
            f"✅ Анализ завершен! Проверяю исправленный код...",
            parse_mode='HTML'
        )
        
        # Проверяем исправленный код
        is_valid, validation_message = validate_generated_code(fixed_code)
        if not is_valid:
            await fix_msg.edit_text(
                f"❌ <b>Некорректный код!</b>\n\n🚫 {validation_message}",
                parse_mode='HTML'
            )
            return
        
        # Извлекаем чистый код
        if '```python' in fixed_code:
            code_start = fixed_code.find('```python') + 9
            code_end = fixed_code.find('```', code_start)
            clean_fixed_code = fixed_code[code_start:code_end].strip()
        elif '```' in fixed_code:
            code_start = fixed_code.find('```') + 3
            code_end = fixed_code.find('```', code_start)
            clean_fixed_code = fixed_code[code_start:code_end].strip()
        else:
            clean_fixed_code = fixed_code.strip()
        
        # Показываем результат анализа
        result_message = f"""🔧 <b>ДИАГНОСТИКА ЗАВЕРШЕНА</b>

📝 <b>Функция:</b> /{function_name}
❌ <b>Ошибка была:</b> {error_info['error_type']}

🧩 <b>ИСПРАВЛЕННЫЙ КОД:</b>
<code>{clean_fixed_code[:800]}{'...' if len(clean_fixed_code) > 800 else ''}</code>

🔄 <b>ПРИМЕНИТЬ ИСПРАВЛЕНИЯ?</b>
• /apply_fix {function_name} - применить исправления
• /show_diff {function_name} - показать различия
• /cancel_fix {function_name} - отменить

⚠️ <b>Внимание:</b> Исправления заменят текущий код функции!"""
        
        await fix_msg.edit_text(result_message, parse_mode='HTML')
        
        # Сохраняем исправленный код для применения
        if 'pending_fixes' not in globals():
            global pending_fixes
            pending_fixes = {}
        
        pending_fixes[function_name] = {
            'fixed_code': clean_fixed_code,
            'original_error': error_info,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        await fix_msg.edit_text(
            f"❌ <b>Ошибка автоисправления:</b>\n\n{str(e)}",
            parse_mode='HTML'
        )

async def apply_fix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Применить исправления от auto_fix (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажи функцию для применения исправлений!\nПример: /apply_fix currencybk")
        return
    
    function_name = context.args[0].lower()
    
    if 'pending_fixes' not in globals() or function_name not in pending_fixes:
        await update.message.reply_text(f"❌ Нет готовых исправлений для /{function_name}!\nСначала используй /auto_fix {function_name}")
        return
    
    try:
        fix_info = pending_fixes[function_name]
        fixed_code = fix_info['fixed_code']
        
        # Выполняем исправленный код
        local_vars = {
            'Update': Update,
            'ContextTypes': ContextTypes,
            'logger': logger
        }
        
        exec(fixed_code, globals(), local_vars)
        
        # Находим исправленную функцию
        new_function = None
        for var_name, var_value in local_vars.items():
            if (var_name.endswith('_command') and 
                callable(var_value) and 
                hasattr(var_value, '__code__') and
                var_value.__code__.co_flags & 0x80):  # async функция
                new_function = var_value
                break
        
        if new_function:
            # Обновляем функцию
            old_description = dynamic_commands[function_name]['description']
            dynamic_functions[function_name] = new_function
            dynamic_commands[function_name] = {
                'function': new_function,
                'description': old_description,
                'code': fixed_code,
                'created_at': dynamic_commands[function_name]['created_at'],
                'fixed_at': datetime.now().isoformat(),
                'fixed_error': fix_info['original_error']['error_type']
            }
            
            # Удаляем ошибку из истории
            if function_name in function_errors:
                del function_errors[function_name]
            
            # Удаляем из ожидающих исправлений
            del pending_fixes[function_name]
            
            await update.message.reply_html(
                f"✅ <b>ИСПРАВЛЕНИЯ ПРИМЕНЕНЫ!</b>\n\n"
                f"🔧 <b>Функция:</b> /{function_name}\n"
                f"🎯 <b>Статус:</b> Ошибка исправлена\n"
                f"📅 <b>Время исправления:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"💡 <b>Протестируй функцию:</b> /{function_name}"
            )
        else:
            await update.message.reply_text("❌ Ошибка применения исправлений: функция не найдена в коде.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка применения исправлений:\n{str(e)}")

# Инициализируем глобальные переменные
pending_fixes = {}

async def dynamic_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик динамических команд"""
    command = update.message.text[1:].split()[0].lower()  # убираем / и берем первое слово
    
    logger.info(f"🔧 Попытка выполнить динамическую команду: /{command}")
    
    if command in dynamic_functions:
        try:
            logger.info(f"✅ Найдена функция для команды /{command}")
            await dynamic_functions[command](update, context)
            logger.info(f"✅ Команда /{command} выполнена успешно")
        except Exception as e:
            # Детальная диагностика ошибки
            import traceback
            error_type = type(e).__name__
            error_message = str(e)
            error_traceback = traceback.format_exc()
            
            logger.error(f"❌ Ошибка выполнения динамической команды /{command}: {error_type}: {error_message}")
            logger.error(f"   Полный стек:\n{error_traceback}")
            
            # ВАЖНО: Сохраняем информацию об ошибке для автоисправления
            function_errors[command] = {
                'error_type': error_type,
                'error_message': error_message,
                'timestamp': datetime.now().isoformat(),
                'function_code': dynamic_commands[command]['code'] if command in dynamic_commands else 'Код недоступен',
                'traceback': error_traceback
            }
            
            logger.info(f"✅ Ошибка сохранена в function_errors для команды /{command}")
            
            # Отправляем пользователю понятное сообщение
            debug_info = f"""❌ <b>Ошибка команды /{command}</b>

🔍 <b>Тип:</b> {error_type}
📝 <b>Описание:</b> {error_message}

🛠️ <b>Возможные причины:</b>"""
            
            # Анализируем тип ошибки
            if "ModuleNotFoundError" in error_type:
                debug_info += "\n• Отсутствует библиотека в requirements.txt"
            elif "requests" in error_message.lower() or "connection" in error_message.lower():
                debug_info += "\n• Проблема с интернет-запросом"
            elif "KeyError" in error_type:
                debug_info += "\n• API изменил формат данных"
            elif "JSONDecodeError" in error_type or "Expecting value" in error_message:
                debug_info += "\n• Сервер вернул некорректный JSON"
                debug_info += "\n• Возможно, API недоступен или изменился"
            elif "timeout" in error_message.lower():
                debug_info += "\n• Превышен таймаут запроса"
            else:
                debug_info += "\n• Ошибка в коде функции"
            
            debug_info += f"\n\n🔄 <b>Действия:</b>"
            debug_info += f"\n• /auto_fix {command} - 🤖 Автоисправление через ChatGPT"
            debug_info += f"\n• /remove_feature {command} - удалить функцию"
            debug_info += f"\n• /edit_feature {command} - [описание] - редактировать вручную"
            debug_info += f"\n\n🔍 <b>Отладка:</b> Ошибка записана для диагностики"
            
            await update.message.reply_html(debug_info)
    else:
        logger.warning(f"⚠️ Команда /{command} не найдена среди динамических функций")
        logger.info(f"📋 Доступные динамические команды: {list(dynamic_functions.keys())}")
        
        # Fallback к обычному echo
        await echo(update, context)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка обычных сообщений с умным режимом"""
    global total_requests
    total_requests += 1
    
    user_id = update.effective_user.id
    user_data[user_id] = user_data.get(user_id, 0) + 1
    
    # Проверяем, не является ли это динамической командой
    message_text = update.message.text
    if message_text.startswith('/'):
        command = message_text[1:].split()[0].lower()
        if command in dynamic_functions:
            await dynamic_command_handler(update, context)
            return
    
    message_lower = message_text.lower()
    
    # Проверяем, выглядит ли сообщение как вопрос
    question_indicators = ['?', 'что', 'как', 'когда', 'где', 'почему', 'зачем', 'какой', 'объясни', 'расскажи']
    is_question = any(indicator in message_lower for indicator in question_indicators)
    
    # Если это вопрос и ChatGPT включен, отвечаем через AI
    if is_question and CHATGPT_ENABLED and await check_user_limit(user_id):
        await update.message.reply_text("🤔 Это похоже на вопрос, отвечаю через ChatGPT...")
        
        await increment_user_requests(user_id)
        ai_answer = await ask_chatgpt(message_text)
        
        response = f"🤖 <b>AI ответ:</b>\n{ai_answer}\n\n💡 <i>Для более точных ответов используй /ai или /gpt</i>"
        
        if len(response) > 4000:
            response = response[:3900] + "...\n\n⚠️ <i>Ответ обрезан</i>"
            
        await update.message.reply_html(response)
    else:
        # Показываем подсказку о созданных функциях
        dynamic_hint = ""
        if dynamic_commands:
            commands_list = ", ".join([f"/{cmd}" for cmd in list(dynamic_commands.keys())[:3]])
            dynamic_hint = f"\n🤖 Созданные AI функции: {commands_list}"
            if len(dynamic_commands) > 3:
                dynamic_hint += f" и еще {len(dynamic_commands)-3}"
        
        # Обычный эхо-ответ
        await update.message.reply_text(
            f"Получил: {message_text}\n\n"
            f"💡 Подсказка: Используй /ai [вопрос] для ChatGPT ответов!"
            f"{dynamic_hint}"
        )

async def currency_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получить курс валют ЦБ РФ"""
    try:
        import requests
        from datetime import datetime
        
        # API Центробанка РФ
        response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
        data = response.json()
        
        # Получаем основные валюты
        usd = data['Valute']['USD']
        eur = data['Valute']['EUR']
        
        date = datetime.now().strftime("%d.%m.%Y")
        
        result = f"💰 <b>Курс валют ЦБ РФ</b>\n📅 {date}\n\n"
        result += f"🇺🇸 <b>Доллар США:</b> {usd['Value']:.2f} ₽\n"
        result += f"🇪🇺 <b>Евро:</b> {eur['Value']:.2f} ₽\n\n"
        result += "<i>Данные Центрального Банка РФ</i>"
        
        await update.message.reply_html(result)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка получения курса: {str(e)}")

async def edit_feature(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Редактировать существующую AI-функцию (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    if not CHATGPT_ENABLED:
        await update.message.reply_text("❌ ChatGPT отключен. Редактирование функций недоступно.")
        return
    
    if not context.args:
        # Показываем список доступных функций для редактирования
        if not dynamic_commands:
            await update.message.reply_text("❌ Нет функций для редактирования!\nИспользуй /add_feature для создания новых.")
            return
            
        functions_list = "🛠️ <b>Функции для редактирования:</b>\n\n"
        for cmd, info in dynamic_commands.items():
            functions_list += f"• <b>/{cmd}</b> - {info['description']}\n"
        
        functions_list += f"\n💡 <b>Использование:</b>\n<code>/edit_feature [команда] - [новое описание]</code>\n\n"
        functions_list += f"<b>Пример:</b>\n/edit_feature {list(dynamic_commands.keys())[0]} - улучшенное описание функции"
        
        await update.message.reply_html(functions_list)
        return
    
    # Парсим команду для редактирования  
    args = " ".join(context.args)
    parts = args.split(' - ', 1)
    
    if len(parts) != 2:
        await update.message.reply_text("❌ Неправильный формат!\nИспользуй: /edit_feature [команда] - [новое описание]")
        return
        
    command_name = parts[0].strip().lower()
    new_description = parts[1].strip()
    
    # Проверяем, что функция существует
    if command_name not in dynamic_commands:
        await update.message.reply_text(f"❌ Функция /{command_name} не найдена!\nИспользуй /list_features для просмотра всех функций.")
        return
    
    old_description = dynamic_commands[command_name]['description']
    
    # Показываем что редактируем
    edit_msg = await update.message.reply_html(
        f"🛠️ <b>Редактирую функцию...</b>\n\n"
        f"📝 <b>Команда:</b> /{command_name}\n"
        f"📖 <b>Было:</b> {old_description}\n"
        f"✨ <b>Стало:</b> {new_description}\n\n"
        f"🤖 Генерирую новый код через ChatGPT..."
    )
    
    # Генерируем новый код
    try:
        generated_code = await generate_function_code(new_description, command_name)
        
        if "❌ Ошибка" in generated_code or "Таймаут" in generated_code:
            await edit_msg.edit_text(
                f"❌ <b>Ошибка генерации!</b>\n\n{generated_code}",
                parse_mode='HTML'
            )
            return
        
        # Проверяем код
        is_valid, validation_message = validate_generated_code(generated_code)
        if not is_valid:
            await edit_msg.edit_text(
                f"❌ <b>Некорректный код!</b>\n\n🚫 {validation_message}",
                parse_mode='HTML'
            )
            return
        
        # Извлекаем и выполняем код
        if '```python' in generated_code:
            code_start = generated_code.find('```python') + 9
            code_end = generated_code.find('```', code_start)
            clean_code = generated_code[code_start:code_end].strip()
        elif '```' in generated_code:
            code_start = generated_code.find('```') + 3
            code_end = generated_code.find('```', code_start)
            clean_code = generated_code[code_start:code_end].strip()
        else:
            clean_code = generated_code.strip()
        
        # Выполняем новый код
        local_vars = {
            'Update': Update,
            'ContextTypes': ContextTypes,
            'logger': logger
        }
        
        exec(clean_code, globals(), local_vars)
        
        # Находим новую функцию
        new_function = None
        for var_name, var_value in local_vars.items():
            if (var_name.endswith('_command') and 
                callable(var_value) and 
                hasattr(var_value, '__code__') and
                var_value.__code__.co_flags & 0x80):  # async функция
                new_function = var_value
                break
        
        if new_function:
            # Обновляем функцию
            dynamic_functions[command_name] = new_function
            dynamic_commands[command_name] = {
                'function': new_function,
                'description': new_description,
                'code': clean_code,
                'created_at': dynamic_commands[command_name]['created_at'],  # сохраняем дату создания
                'edited_at': __import__('datetime').datetime.now().isoformat()
            }
            
            await edit_msg.edit_text(
                f"✅ <b>Функция успешно обновлена!</b>\n\n"
                f"🔄 <b>Команда:</b> /{command_name}\n"
                f"📝 <b>Новое описание:</b> {new_description}\n\n"
                f"🧩 <b>Обновленный код:</b>\n<code>{clean_code[:400]}{'...' if len(clean_code) > 400 else ''}</code>\n\n"
                f"💡 <b>Протестируй:</b> /{command_name}",
                parse_mode='HTML'
            )
        else:
            await edit_msg.edit_text(
                f"❌ <b>Новая функция не найдена!</b>\n\nПопробуй другое описание.",
                parse_mode='HTML'
            )
            
    except Exception as e:
        await edit_msg.edit_text(
            f"❌ <b>Ошибка выполнения:</b>\n\n{str(e)}\n\n🔄 Попробуй другое описание.",
            parse_mode='HTML'
        )

async def debug_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Простая диагностика состояния бота (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    from datetime import datetime
    
    # Собираем основную информацию
    debug_report = f"""🔧 <b>ДИАГНОСТИКА БОТА</b>
📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🤖 <b>ChatGPT:</b>
• Статус: {'✅ Активен' if CHATGPT_ENABLED else '❌ Отключен'}
• Модель: {CHATGPT_MODEL}
• API ключ: {'✅ Установлен' if OPENAI_API_KEY else '❌ Отсутствует'}

🛠️ <b>AI Функции:</b>
• Создано функций: {len(dynamic_functions)}
• Активных команд: {len(dynamic_commands)}
• История: {len(generation_history)} попыток

📊 <b>Статистика:</b>
• Всего запросов: {total_requests}
• Пользователей: {len(user_data)}
• ChatGPT запросов: {sum(user_requests.values())}

🧪 <b>Тест команд:</b>
• /ping - Простая команда
• /currency - API ЦБ РФ
• /ai привет - Тест ChatGPT
"""
    
    if dynamic_commands:
        debug_report += f"\n🧩 <b>AI Команды:</b>\n"
        for cmd in list(dynamic_commands.keys())[:3]:
            debug_report += f"• /{cmd}\n"
        if len(dynamic_commands) > 3:
            debug_report += f"• ... и еще {len(dynamic_commands)-3}"
    
    await update.message.reply_html(debug_report)

async def uptime_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать время работы бота"""
    current_time = datetime.now()
    uptime = current_time - BOT_START_TIME
    
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    uptime_text = f"⏰ <b>Время работы бота:</b>\n\n"
    uptime_text += f"🚀 <b>Запущен:</b> {BOT_START_TIME.strftime('%d.%m.%Y %H:%M:%S')}\n"
    uptime_text += f"⏳ <b>Работает:</b> "
    
    if days > 0:
        uptime_text += f"{days} дн. "
    if hours > 0:
        uptime_text += f"{hours} ч. "
    if minutes > 0:
        uptime_text += f"{minutes} мин. "
    uptime_text += f"{seconds} сек.\n\n"
    
    uptime_text += f"📊 <b>Статистика за сессию:</b>\n"
    uptime_text += f"• Всего запросов: {total_requests}\n"
    uptime_text += f"• ChatGPT запросов: {sum(user_requests.values())}\n"
    uptime_text += f"• Активных пользователей: {len(user_data)}\n"
    uptime_text += f"• AI функций создано: {len(dynamic_functions)}"
    
    await update.message.reply_html(uptime_text)

async def system_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Информация о системе (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    import sys
    import os
    import platform
    
    try:
        import psutil
        memory_info = f"💾 <b>Память:</b> {psutil.virtual_memory().percent}% использовано\n"
        cpu_info = f"⚡ <b>CPU:</b> {psutil.cpu_percent()}% нагрузка\n"
    except ImportError:
        memory_info = "💾 <b>Память:</b> Модуль psutil недоступен\n"
        cpu_info = "⚡ <b>CPU:</b> Модуль psutil недоступен\n"
    
    system_text = f"🖥️ <b>ИНФОРМАЦИЯ О СИСТЕМЕ</b>\n\n"
    system_text += f"🐍 <b>Python:</b> {sys.version.split()[0]}\n"
    system_text += f"🤖 <b>Платформа:</b> {platform.system()} {platform.release()}\n"
    system_text += f"📁 <b>Рабочая папка:</b> {os.getcwd()}\n"
    system_text += f"{memory_info}"
    system_text += f"{cpu_info}"
    system_text += f"\n🔧 <b>Компоненты:</b>\n"
    system_text += f"• Telegram Bot API: ✅\n"
    system_text += f"• OpenAI API: {'✅' if CHATGPT_ENABLED else '❌'}\n"
    system_text += f"• Requests: ✅\n"
    system_text += f"• Asyncio: ✅"
    
    await update.message.reply_html(system_text)

async def notify_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправить уведомление админу (только для пользователей)"""
    user_id = update.effective_user.id
    user = update.effective_user
    
    if user_id == ADMIN_USER_ID:
        await update.message.reply_text("ℹ️ Ты уже админ! Используй /admin_help для управления.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📢 <b>Уведомление админу</b>\n\n"
            "Отправь сообщение администратору бота:\n"
            "<code>/notify [твое сообщение]</code>\n\n"
            "<b>Пример:</b>\n/notify Привет! У меня есть предложение по улучшению бота.",
            parse_mode='HTML'
        )
        return
    
    message_text = " ".join(context.args)
    
    # Отправляем уведомление админу
    try:
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=f"📬 <b>УВЕДОМЛЕНИЕ ОТ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
                 f"👤 <b>Пользователь:</b> {user.mention_html()}\n"
                 f"🆔 <b>ID:</b> {user_id}\n"
                 f"📝 <b>Сообщение:</b>\n{message_text}\n\n"
                 f"💬 <b>Ответить:</b> /broadcast [ответ]",
            parse_mode='HTML'
        )
        
        await update.message.reply_text("✅ Сообщение отправлено администратору!")
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления админу: {e}")
        await update.message.reply_text("❌ Ошибка отправки уведомления. Попробуй позже.")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Простая тестовая команда"""
    from datetime import datetime
    current_time = datetime.now().strftime('%H:%M:%S')
    await update.message.reply_text(f"🏓 Понг! Время: {current_time}")

def load_saved_features():
    """Загружает сохраненные функции при запуске (заглушка)"""
    # В будущем здесь можно загружать функции из файла или базы данных
    logger.info("🔄 Загрузка сохраненных AI функций...")
    # TODO: Реализовать сохранение/загрузку в файл или БД

async def show_diff(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать различия между текущим и исправленным кодом (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажи функцию для просмотра различий!\nПример: /show_diff currencybk")
        return
    
    function_name = context.args[0].lower()
    
    if 'pending_fixes' not in globals() or function_name not in pending_fixes:
        await update.message.reply_text(f"❌ Нет готовых исправлений для /{function_name}!\nСначала используй /auto_fix {function_name}")
        return
    
    if function_name not in dynamic_commands:
        await update.message.reply_text(f"❌ Функция /{function_name} не найдена!")
        return
    
    fix_info = pending_fixes[function_name]
    original_code = dynamic_commands[function_name]['code']
    fixed_code = fix_info['fixed_code']
    
    diff_message = f"""📊 <b>СРАВНЕНИЕ КОДА</b>

📝 <b>Функция:</b> /{function_name}
❌ <b>Ошибка:</b> {fix_info['original_error']['error_type']}

📜 <b>ТЕКУЩИЙ КОД:</b>
<code>{original_code[:400]}{'...' if len(original_code) > 400 else ''}</code>

🔧 <b>ИСПРАВЛЕННЫЙ КОД:</b>
<code>{fixed_code[:400]}{'...' if len(fixed_code) > 400 else ''}</code>

🔄 <b>ДЕЙСТВИЯ:</b>
• /apply_fix {function_name} - применить исправления
• /cancel_fix {function_name} - отменить исправления"""
    
    await update.message.reply_html(diff_message)

async def cancel_fix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменить готовые исправления (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажи функцию для отмены исправлений!\nПример: /cancel_fix currencybk")
        return
    
    function_name = context.args[0].lower()
    
    if 'pending_fixes' not in globals() or function_name not in pending_fixes:
        await update.message.reply_text(f"❌ Нет готовых исправлений для /{function_name}!")
        return
    
    del pending_fixes[function_name]
    await update.message.reply_text(f"✅ Исправления для /{function_name} отменены.")

async def debug_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отладка системы записи ошибок (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    debug_report = f"🔍 <b>ОТЛАДКА СИСТЕМЫ ОШИБОК</b>\n\n"
    
    # Показываем состояние систем
    debug_report += f"📊 <b>Состояние систем:</b>\n"
    debug_report += f"• function_errors: {len(function_errors)} записей\n"
    debug_report += f"• dynamic_commands: {len(dynamic_commands)} функций\n"
    debug_report += f"• dynamic_functions: {len(dynamic_functions)} функций\n"
    
    if 'pending_fixes' in globals():
        debug_report += f"• pending_fixes: {len(pending_fixes)} исправлений\n"
    else:
        debug_report += f"• pending_fixes: не инициализировано\n"
    
    # Показываем записанные ошибки
    if function_errors:
        debug_report += f"\n❌ <b>Записанные ошибки:</b>\n"
        for func_name, error_info in function_errors.items():
            debug_report += f"• <b>/{func_name}</b> - {error_info['error_type']}\n"
            debug_report += f"  📝 {error_info['error_message'][:50]}{'...' if len(error_info['error_message']) > 50 else ''}\n"
            debug_report += f"  ⏰ {error_info['timestamp'][:16]}\n\n"
    else:
        debug_report += f"\n✅ <b>Нет записанных ошибок</b>\n"
    
    # Показываем доступные функции
    if dynamic_commands:
        debug_report += f"\n🧩 <b>AI Функции:</b>\n"
        for cmd in list(dynamic_commands.keys())[:5]:
            debug_report += f"• /{cmd}\n"
        if len(dynamic_commands) > 5:
            debug_report += f"• ... и еще {len(dynamic_commands)-5}\n"
    
    debug_report += f"\n💡 <b>Тестирование:</b>\n"
    debug_report += f"1. Выполни команду с ошибкой\n"
    debug_report += f"2. Проверь /debug_errors\n"
    debug_report += f"3. Используй /auto_fix [команда]"
    
    await update.message.reply_html(debug_report)

def main() -> None:
    """Запуск бота с ChatGPT и AI-генерацией функций"""
    # Загружаем сохраненные функции
    load_saved_features()
    
    application = Application.builder().token(BOT_TOKEN).build()

    # Обычные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("my_id", my_id))
    application.add_handler(CommandHandler("ping", ping_command))  # Тестовая команда

    # ChatGPT команды
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CommandHandler("gpt", gpt_command))
    application.add_handler(CommandHandler("currency", currency_command)) # Добавляем новую команду

    # Админ команды
    application.add_handler(CommandHandler("admin_help", admin_help))
    # AI Разработка команды
    application.add_handler(CommandHandler("add_feature", add_feature))
    application.add_handler(CommandHandler("list_features", list_features))
    application.add_handler(CommandHandler("remove_feature", remove_feature))
    application.add_handler(CommandHandler("generation_stats", generation_stats))
    application.add_handler(CommandHandler("edit_feature", edit_feature)) # Добавляем новую команду
    application.add_handler(CommandHandler("auto_fix", auto_fix)) # Добавляем новую команду
    application.add_handler(CommandHandler("apply_fix", apply_fix)) # Добавляем новую команду
    
    # Остальные админ команды
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("reset_limits", reset_limits_command))
    application.add_handler(CommandHandler("chatgpt_settings", chatgpt_settings))
    application.add_handler(CommandHandler("list_models", list_models))
    application.add_handler(CommandHandler("quick_model", quick_model))
    application.add_handler(CommandHandler("model_recommend", model_recommend))
    application.add_handler(CommandHandler("debug_status", debug_status)) # Добавляем новую команду
    application.add_handler(CommandHandler("uptime", uptime_command)) # Добавляем новую команду
    application.add_handler(CommandHandler("system_info", system_info)) # Добавляем новую команду
    application.add_handler(CommandHandler("notify", notify_admin)) # Добавляем новую команду
    application.add_handler(CommandHandler("show_diff", show_diff)) # Добавляем новую команду
    application.add_handler(CommandHandler("cancel_fix", cancel_fix)) # Добавляем новую команду
    application.add_handler(CommandHandler("debug_errors", debug_errors)) # Добавляем новую команду

    # ВАЖНО: MessageHandler должен быть последним для обработки динамических команд
    application.add_handler(MessageHandler(filters.TEXT, echo))

    features_count = len(dynamic_commands)
    chatgpt_info = "✅ ChatGPT активен" if CHATGPT_ENABLED else "❌ ChatGPT отключен"
    
    print(f"🚀 Умный AI-бот запущен!")
    print(f"   {chatgpt_info}")
    print(f"   🤖 AI функций: {features_count}")
    print(f"   💡 Используй /add_feature для создания новых функций через ChatGPT!")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 