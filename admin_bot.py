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

<b>🛠️ Разработка:</b>
/add_feature [код] - Добавить функцию
/update_code [файл] - Обновить код

💡 <b>Примеры:</b>
/ai Объясни алгоритм сортировки
/broadcast Обновление бота завершено!
/reset_limits - если нужно сбросить счетчики
    """
    await update.message.reply_html(admin_commands)

async def add_feature(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавить новую функцию (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажи название функции!\nПример: /add_feature weather")
        return
    
    feature_name = " ".join(context.args)
    
    # Здесь ты можешь добавить логику для динамического добавления функций
    await update.message.reply_text(
        f"✅ Функция '{feature_name}' добавлена в очередь разработки!\n"
        f"Скоро я её реализую."
    )

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

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка обычных сообщений с умным режимом"""
    global total_requests
    total_requests += 1
    
    user_id = update.effective_user.id
    user_data[user_id] = user_data.get(user_id, 0) + 1
    
    message_text = update.message.text.lower()
    
    # Проверяем, выглядит ли сообщение как вопрос
    question_indicators = ['?', 'что', 'как', 'когда', 'где', 'почему', 'зачем', 'какой', 'объясни', 'расскажи']
    is_question = any(indicator in message_text for indicator in question_indicators)
    
    # Если это вопрос и ChatGPT включен, отвечаем через AI
    if is_question and CHATGPT_ENABLED and await check_user_limit(user_id):
        await update.message.reply_text("🤔 Это похоже на вопрос, отвечаю через ChatGPT...")
        
        await increment_user_requests(user_id)
        ai_answer = await ask_chatgpt(update.message.text)
        
        response = f"🤖 <b>AI ответ:</b>\n{ai_answer}\n\n💡 <i>Для более точных ответов используй /ai или /gpt</i>"
        
        if len(response) > 4000:
            response = response[:3900] + "...\n\n⚠️ <i>Ответ обрезан</i>"
            
        await update.message.reply_html(response)
    else:
        # Обычный эхо-ответ
        await update.message.reply_text(
            f"Получил: {update.message.text}\n\n"
            f"💡 Подсказка: Используй /ai [вопрос] для ChatGPT ответов!"
        )

def main() -> None:
    """Запуск бота с ChatGPT и админ-функциями"""
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
    application.add_handler(CommandHandler("add_feature", add_feature))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("reset_limits", reset_limits_command))
    application.add_handler(CommandHandler("chatgpt_settings", chatgpt_settings))
    application.add_handler(CommandHandler("list_models", list_models))
    application.add_handler(CommandHandler("quick_model", quick_model))
    application.add_handler(CommandHandler("model_recommend", model_recommend))

    # Текстовые сообщения
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    chatgpt_info = "✅ ChatGPT активен" if CHATGPT_ENABLED else "❌ ChatGPT отключен"
    print(f"🚀 Умный бот запущен! {chatgpt_info}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 