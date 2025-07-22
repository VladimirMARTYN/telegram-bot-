import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ТВОЙ Telegram ID
ADMIN_USER_ID = 34331814  # Владелец бота

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    await update.message.reply_text(
        "🤖 Привет! Я бот с админ-управлением.\n"
        "Отправь /help для списка команд."
    )

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать ID пользователя"""
    user_id = update.effective_user.id
    await update.message.reply_text(f"Твой ID: {user_id}")

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ-команды (только для админа)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    admin_commands = """
🔧 <b>АДМИН КОМАНДЫ:</b>

/admin_help - Это меню
/add_feature [код] - Добавить новую функцию
/restart - Перезапустить бота
/stats - Статистика бота
/broadcast [сообщение] - Рассылка всем пользователям
/update_code [файл] - Обновить код бота

💡 <b>Примеры:</b>
/add_feature weather - добавить команду погоды
/broadcast Привет всем!
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
    
    # Простая статистика
    stats = f"""
📊 <b>Статистика бота:</b>

👥 Пользователей: {len(user_data)}
🔄 Запросов обработано: {total_requests}
⏰ Время работы: активен
💾 Статус: работает нормально
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
    """Обработка обычных сообщений"""
    global total_requests
    total_requests += 1
    
    user_id = update.effective_user.id
    user_data[user_id] = user_data.get(user_id, 0) + 1
    
    await update.message.reply_text(f"Получил: {update.message.text}")

def main() -> None:
    """Запуск бота с админ-функциями"""
    application = Application.builder().token(BOT_TOKEN).build()

    # Обычные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("my_id", my_id))

    # Админ команды
    application.add_handler(CommandHandler("admin_help", admin_help))
    application.add_handler(CommandHandler("add_feature", add_feature))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", broadcast))

    # Текстовые сообщения
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("🚀 Бот с админ-управлением запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 