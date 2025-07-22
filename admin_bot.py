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
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=CHATGPT_MODEL,
            messages=[
                {"role": "system", "content": "Ты умный помощник. Отвечай кратко и по делу на русском языке."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=MAX_TOKENS,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Ошибка ChatGPT API: {e}")
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

async def chatgpt_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Настройки ChatGPT (только админ)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    global MAX_REQUESTS_PER_USER, MAX_TOKENS, CHATGPT_MODEL
    
    if not context.args:
        # Показать текущие настройки
        settings_info = f"""
🤖 <b>Настройки ChatGPT:</b>

📊 <b>Статус:</b> {'✅ Активен' if CHATGPT_ENABLED else '❌ Отключен'}
🔄 <b>Модель:</b> {CHATGPT_MODEL}
🎯 <b>Макс. токенов:</b> {MAX_TOKENS}
👥 <b>Лимит на пользователя:</b> {MAX_REQUESTS_PER_USER}

💡 <b>Изменить настройки:</b>
/chatgpt_settings limit 20 - изменить лимит
/chatgpt_settings tokens 1500 - изменить токены
/chatgpt_settings model gpt-4 - изменить модель
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
            MAX_TOKENS = int(value)
            await update.message.reply_text(f"✅ Максимальное количество токенов изменено на {MAX_TOKENS}")
        
        elif setting == "model":
            CHATGPT_MODEL = value
            await update.message.reply_text(f"✅ Модель изменена на {CHATGPT_MODEL}")
        
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
/reset_limits - Сбросить лимиты пользователей
/chatgpt_settings - Настройки ChatGPT

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
    
    stats = f"""
📊 <b>Статистика бота:</b>

👥 <b>Пользователи:</b>
• Всего: {len(user_data)}
• Используют AI: {active_ai_users}

🔄 <b>Активность:</b>
• Всего сообщений: {total_requests}
• AI запросов: {total_ai_requests}
• Модель: {CHATGPT_MODEL if CHATGPT_ENABLED else 'Нет'}

🤖 <b>ChatGPT:</b> {chatgpt_status}
• Лимит на пользователя: {MAX_REQUESTS_PER_USER}
• Макс. токенов: {MAX_TOKENS}

⏰ <b>Статус:</b> Работает нормально
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

    # Текстовые сообщения
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    chatgpt_info = "✅ ChatGPT активен" if CHATGPT_ENABLED else "❌ ChatGPT отключен"
    print(f"🚀 Умный бот запущен! {chatgpt_info}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 