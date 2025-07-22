import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from config import BOT_TOKEN

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Простое хранилище данных в памяти (в реальном проекте лучше использовать базу данных)
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Расширенная команда /start с клавиатурой"""
    user = update.effective_user
    user_id = user.id
    
    # Инициализируем данные пользователя
    if user_id not in user_data:
        user_data[user_id] = {
            'name': user.first_name,
            'messages_count': 0,
            'registration_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    # Создаем inline клавиатуру
    keyboard = [
        [
            InlineKeyboardButton("📊 Статистика", callback_data='stats'),
            InlineKeyboardButton("🎲 Случайное число", callback_data='random'),
        ],
        [
            InlineKeyboardButton("📅 Дата и время", callback_data='datetime'),
            InlineKeyboardButton("ℹ️ Помощь", callback_data='help'),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
🤖 Привет, {user.mention_html()}!

Я продвинутый Telegram бот с дополнительными возможностями.

Выбери действие из меню ниже или отправь мне текстовое сообщение:
    """
    
    await update.message.reply_html(welcome_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline кнопки"""
    query = update.callback_query
    await query.answer()  # Подтверждаем получение нажатия
    
    user_id = query.from_user.id
    
    if query.data == 'stats':
        if user_id in user_data:
            stats_text = f"""
📊 <b>Твоя статистика:</b>

👤 Имя: {user_data[user_id]['name']}
📝 Отправлено сообщений: {user_data[user_id]['messages_count']}
📅 Дата регистрации: {user_data[user_id]['registration_date']}
            """
        else:
            stats_text = "📊 Статистика пока недоступна"
        
        await query.edit_message_text(stats_text, parse_mode='HTML')
        
    elif query.data == 'random':
        import random
        random_number = random.randint(1, 100)
        await query.edit_message_text(f"🎲 Твое случайное число: <b>{random_number}</b>", parse_mode='HTML')
        
    elif query.data == 'datetime':
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await query.edit_message_text(f"📅 Текущее время: <b>{current_time}</b>", parse_mode='HTML')
        
    elif query.data == 'help':
        help_text = """
ℹ️ <b>Доступные команды:</b>

/start - Главное меню
/weather - Узнать погоду (пример)
/joke - Получить шутку
/count - Счетчик сообщений

<b>Inline кнопки:</b>
📊 Статистика - твои данные
🎲 Случайное число - от 1 до 100
📅 Дата и время - текущее время
        """
        await query.edit_message_text(help_text, parse_mode='HTML')

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Пример команды погоды (заглушка)"""
    await update.message.reply_text(
        "🌤 В данный момент функция погоды недоступна.\n"
        "Для реализации подключи API погоды (например, OpenWeatherMap)"
    )

async def joke_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для получения шутки"""
    jokes = [
        "Почему программисты предпочитают iOS? Потому что они любят Swift решения! 😄",
        "- Сколько программистов нужно, чтобы поменять лампочку?\n- Ноль, это аппаратная проблема! 🔧",
        "Как называется программист после отпуска? Отлаженный! 😎",
        "У программистов только два твердых числа: 0, 1 и 2! 🤓",
    ]
    
    import random
    joke = random.choice(jokes)
    await update.message.reply_text(f"😂 {joke}")

async def count_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать счетчик сообщений пользователя"""
    user_id = update.effective_user.id
    if user_id in user_data:
        count = user_data[user_id]['messages_count']
        await update.message.reply_text(f"📊 Ты отправил мне {count} сообщений")
    else:
        await update.message.reply_text("📊 У тебя пока нет статистики")

async def echo_advanced(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Улучшенная эхо-функция с подсчетом сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Увеличиваем счетчик сообщений
    if user_id not in user_data:
        user_data[user_id] = {
            'name': update.effective_user.first_name,
            'messages_count': 0,
            'registration_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    user_data[user_id]['messages_count'] += 1
    
    # Разные ответы в зависимости от содержания сообщения
    message_lower = user_message.lower()
    
    if "привет" in message_lower or "hello" in message_lower:
        response = "👋 Привет! Как дела?"
    elif "пока" in message_lower or "bye" in message_lower:
        response = "👋 До свидания! Увидимся позже!"
    elif "спасибо" in message_lower or "thanks" in message_lower:
        response = "😊 Пожалуйста! Рад помочь!"
    elif "?" in user_message:
        response = "🤔 Интересный вопрос! Но я пока не знаю ответа."
    else:
        responses = [
            f"✉️ Получил твое сообщение: '{user_message}'",
            f"👍 Понял! Ты написал: {user_message}",
            f"📝 Сообщение принято: {user_message}",
            f"💬 Ответ на '{user_message}': Отличное сообщение!",
        ]
        import random
        response = random.choice(responses)
    
    await update.message.reply_text(response)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error("Exception while handling an update:", exc_info=context.error)

def main() -> None:
    """Основная функция для запуска продвинутого бота"""
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("weather", weather_command))
    application.add_handler(CommandHandler("joke", joke_command))
    application.add_handler(CommandHandler("count", count_command))

    # Добавляем обработчик для inline кнопок
    application.add_handler(CallbackQueryHandler(button_handler))

    # Добавляем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_advanced))

    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    print("🚀 Продвинутый бот запущен! Нажми Ctrl+C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 