import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, OPENAI_API_KEY
import openai
import asyncio

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
/list_features - Список созданных функций
/remove_feature [команда] - Удалить функцию
/generation_stats - Статистика AI генерации

💡 <b>Примеры:</b>
/ai Объясни алгоритм сортировки
/add_feature погода - узнать погоду в городе
/broadcast Обновление бота завершено!
    """
    await update.message.reply_html(admin_commands)

async def generate_function_code(description: str, command_name: str) -> str:
    """Генерирует код функции через ChatGPT"""
    system_prompt = """
Ты опытный Python разработчик Telegram ботов. Создай функцию для Telegram бота.

СТРОГО СЛЕДУЙ ЭТОМУ ФОРМАТУ:

```python
async def {command_name}_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    \"\"\"Описание функции\"\"\"
    # твой код здесь
    await update.message.reply_text("твой ответ")
```

ТРЕБОВАНИЯ:
1. Используй только стандартные библиотеки Python и библиотеки telegram
2. Функция должна быть async
3. Обязательно используй await для Telegram операций
4. Добавь обработку ошибок try/except если нужно
5. Используй reply_text или reply_html для ответов
6. НЕ используй внешние API без явного указания
7. Код должен быть безопасным и не содержать exec/eval
8. Отвечай только кодом без дополнительных объяснений

Пример простой функции:
```python
async def joke_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    \"\"\"Отправляет случайную шутку\"\"\"
    import random
    jokes = ["Шутка 1", "Шутка 2", "Шутка 3"]
    joke = random.choice(jokes)
    await update.message.reply_text(f"😂 {joke}")
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
    """Проверяет безопасность сгенерированного кода"""
    dangerous_patterns = [
        'exec(', 'eval(', '__import__',
        'open(', 'file(', 'input(',
        'os.system', 'subprocess',
        'import os', 'from os', 'import sys',
        'requests.', 'urllib.', 'http.',
        'socket.', 'ftplib.', 'smtplib.',
        'telnetlib.', 'xmlrpc.', 'pickle.',
        'threading.', 'multiprocessing.',
        'shutil.', 'glob.', 'tempfile.',
        'getpass.', 'pty.', 'tty.',
        '__builtins__', 'globals()', 'locals()',
        'compile(', 'memoryview(', 'bytearray('
    ]
    
    code_lower = code.lower()
    for pattern in dangerous_patterns:
        if pattern in code_lower:
            return False, f"Небезопасный код: содержит {pattern}"
    
    # Проверяем структуру функции
    if 'async def' not in code:
        return False, "Код должен содержать async функцию"
    
    if 'await update.message.reply' not in code:
        return False, "Функция должна отправлять ответ пользователю"
    
    # Проверяем на подозрительные конструкции
    suspicious_patterns = [
        'while True:', 'for i in range(999',
        'time.sleep(', 'infinite', 'forever'
    ]
    
    for pattern in suspicious_patterns:
        if pattern in code_lower:
            return False, f"Подозрительный код: {pattern} может зависнуть"
    
    # Проверяем длину кода (не более 50 строк)
    lines = code.strip().split('\n')
    if len(lines) > 50:
        return False, f"Код слишком длинный: {len(lines)} строк (максимум 50)"
    
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
            "Опиши функцию, которую хочешь добавить:\n\n"
            "<b>Примеры:</b>\n"
            "• /add_feature погода - узнать погоду в городе\n"
            "• /add_feature шутки - рассказывать анекдоты\n"
            "• /add_feature время - показать текущее время\n"
            "• /add_feature переводчик - переводить текст\n\n"
            "💡 Я сгенерирую код через ChatGPT и добавлю в бот!",
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
    
    # Проверяем код на безопасность
    is_safe, validation_message = validate_generated_code(generated_code)
    
    if not is_safe:
        await update.message.reply_text(
            f"❌ <b>Код не прошел проверку безопасности!</b>\n\n"
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
        
        # Выполняем код в ограниченной безопасной среде
        safe_builtins = {
            'len': len, 'str': str, 'int': int, 'float': float,
            'bool': bool, 'list': list, 'dict': dict, 'tuple': tuple,
            'set': set, 'range': range, 'enumerate': enumerate,
            'zip': zip, 'min': min, 'max': max, 'sum': sum,
            'abs': abs, 'round': round, 'sorted': sorted,
            'reversed': reversed, 'any': any, 'all': all
        }
        
        local_vars = {
            'Update': Update,
            'ContextTypes': ContextTypes,
            'logger': logger,
            'random': __import__('random'),
            'datetime': __import__('datetime'),
            'json': __import__('json'),
            're': __import__('re'),
            'math': __import__('math'),
            '__builtins__': safe_builtins
        }
        
        exec(clean_code, globals(), local_vars)
        
        # Находим созданную функцию
        function_name = f"{command_name}_command"
        if function_name in local_vars:
            new_function = local_vars[function_name]
            
            # Сохраняем функцию
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

async def dynamic_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик динамических команд"""
    command = update.message.text[1:].split()[0].lower()  # убираем / и берем первое слово
    
    if command in dynamic_functions:
        try:
            await dynamic_functions[command](update, context)
        except Exception as e:
            logger.error(f"Ошибка выполнения динамической команды {command}: {e}")
            await update.message.reply_text(
                f"❌ Ошибка выполнения команды /{command}:\n{str(e)}"
            )
    else:
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

def load_saved_features():
    """Загружает сохраненные функции при запуске (заглушка)"""
    # В будущем здесь можно загружать функции из файла или базы данных
    logger.info("🔄 Загрузка сохраненных AI функций...")
    # TODO: Реализовать сохранение/загрузку в файл или БД

def main() -> None:
    """Запуск бота с ChatGPT и AI-генерацией функций"""
    # Загружаем сохраненные функции
    load_saved_features()
    
    application = Application.builder().token(BOT_TOKEN).build()

    # Обычные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("my_id", my_id))

    # ChatGPT команды
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CommandHandler("gpt", gpt_command))

    # Админ команды
    application.add_handler(CommandHandler("admin_help", admin_help))
    # AI Разработка команды
    application.add_handler(CommandHandler("add_feature", add_feature))
    application.add_handler(CommandHandler("list_features", list_features))
    application.add_handler(CommandHandler("remove_feature", remove_feature))
    application.add_handler(CommandHandler("generation_stats", generation_stats))
    
    # Остальные админ команды
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("reset_limits", reset_limits_command))
    application.add_handler(CommandHandler("chatgpt_settings", chatgpt_settings))
    application.add_handler(CommandHandler("list_models", list_models))
    application.add_handler(CommandHandler("quick_model", quick_model))
    application.add_handler(CommandHandler("model_recommend", model_recommend))

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