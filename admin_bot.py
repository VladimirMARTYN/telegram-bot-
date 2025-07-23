#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import asyncio
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', '0'))

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
    exit(1)

if ADMIN_USER_ID == 0:
    logger.warning("⚠️ ADMIN_USER_ID не установлен!")

# Время запуска бота
bot_start_time = datetime.now()

# Простые данные в памяти
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    
    # Регистрируем пользователя
    if user_id not in user_data:
        user_data[user_id] = {
            'name': user.first_name,
            'username': user.username,
            'joined_at': datetime.now().isoformat()
        }
        logger.info(f"👤 Новый пользователь: {user.first_name} (@{user.username}, ID: {user_id})")
    
    welcome_text = (
        f"👋 <b>Привет, {user.first_name}!</b>\n\n"
        f"🤖 Это чистый Telegram бот\n\n"
        f"📋 <b>Доступные команды:</b>\n"
        f"/help - Справка\n"
        f"/ping - Проверка работы\n"
        f"/rates - Курсы валют и криптовалют\n"
        f"/my_id - Узнать свой ID\n\n"
    )
    
    if user_id == ADMIN_USER_ID:
        welcome_text += "👨‍💻 <b>Статус:</b> Администратор\n"
    else:
        welcome_text += "👤 <b>Статус:</b> Пользователь\n"
    
    welcome_text += f"📊 <b>Пользователей:</b> {len(user_data)}"
    
    await update.message.reply_html(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    help_text = (
        "🤖 <b>Справка по боту</b>\n\n"
        
        "📋 <b>Команды:</b>\n"
        "/start - Запуск бота\n"
        "/help - Эта справка\n"
        "/ping - Проверка работы\n"
        "/rates - Курсы валют и криптовалют\n"
        "/my_id - Узнать свой ID\n\n"
        
        "💱 <b>Функции:</b>\n"
        "• Курсы валют ЦБ РФ (USD, EUR, CNY)\n"
        "• Курсы криптовалют (Bitcoin, Ethereum, Dogecoin, TON)\n\n"
        
        "ℹ️ <b>Информация:</b>\n"
        "Бот готов к расширению функционала."
    )
    
    await update.message.reply_html(help_text)

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /ping"""
    current_time = datetime.now().strftime("%H:%M:%S")
    await update.message.reply_text(f"🏓 Понг! Время: {current_time}")

async def my_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /my_id"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    
    id_text = (
        f"🆔 <b>Ваша информация:</b>\n\n"
        f"👤 <b>ID:</b> <code>{user_id}</code>\n"
        f"📝 <b>Имя:</b> {first_name}\n"
    )
    
    if username:
        id_text += f"🔤 <b>Username:</b> @{username}\n"
    
    if user_id == ADMIN_USER_ID:
        id_text += f"\n👨‍💻 <b>Статус:</b> Администратор"
    
    await update.message.reply_html(id_text)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ панель"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен!")
        return
    
    uptime = datetime.now() - bot_start_time
    uptime_str = str(uptime).split('.')[0]  # Убираем микросекунды
    
    admin_text = (
        f"👨‍💻 <b>АДМИН ПАНЕЛЬ</b>\n\n"
        
        f"📊 <b>Статистика:</b>\n"
        f"• Пользователей: {len(user_data)}\n"
        f"• Время работы: {uptime_str}\n"
        f"• Запущен: {bot_start_time.strftime('%d.%m.%Y %H:%M')}\n\n"
        
        f"🔧 <b>Команды:</b>\n"
        f"/admin - Эта панель\n"
        f"/ping - Проверка работы\n"
        f"/rates - Курсы валют и криптовалют\n\n"
        
        f"💱 <b>Доступные функции:</b>\n"
        f"• Курсы валют ЦБ РФ (USD, EUR, CNY)\n"
        f"• Курсы криптовалют (BTC, ETH, DOGE, TON)\n\n"
        
        f"ℹ️ <b>Статус:</b> Бот готов к расширению"
    )
    
    await update.message.reply_html(admin_text)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка обычных сообщений"""
    message_text = update.message.text
    user_id = update.effective_user.id
    
    # Обновляем активность пользователя
    if user_id in user_data:
        user_data[user_id]['last_active'] = datetime.now().isoformat()
    
    # Простой эхо ответ
    await update.message.reply_text(
        f"Получил: {message_text}\n\n"
        f"💡 Используй /help для списка команд"
    )

async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получить курсы валют и криптовалют"""
    try:
        await update.message.reply_text("📊 Получаю курсы валют и криптовалют...")
        
        import requests
        
        # 1. Курсы валют ЦБ РФ
        try:
            cbr_response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
            cbr_response.raise_for_status()
            cbr_data = cbr_response.json()
            
            # Получаем курсы валют
            usd_rate = cbr_data.get('Valute', {}).get('USD', {}).get('Value', 'Н/Д')
            eur_rate = cbr_data.get('Valute', {}).get('EUR', {}).get('Value', 'Н/Д')
            cny_rate = cbr_data.get('Valute', {}).get('CNY', {}).get('Value', 'Н/Д')
            
            # Форматируем валютные курсы
            usd_str = f"{usd_rate:.2f} ₽" if isinstance(usd_rate, (int, float)) else str(usd_rate)
            eur_str = f"{eur_rate:.2f} ₽" if isinstance(eur_rate, (int, float)) else str(eur_rate)
            cny_str = f"{cny_rate:.2f} ₽" if isinstance(cny_rate, (int, float)) else str(cny_rate)
                
        except Exception as e:
            logger.error(f"Ошибка получения курсов ЦБ РФ: {e}")
            usd_str = eur_str = cny_str = "❌ Ошибка API"
        
        # 2. Курсы криптовалют CoinGecko
        try:
            crypto_response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,dogecoin,the-open-network&vs_currencies=usd",
                timeout=10
            )
            crypto_response.raise_for_status()
            crypto_data = crypto_response.json()
            
            # Получаем цены криптовалют
            bitcoin_price = crypto_data.get('bitcoin', {}).get('usd', 'Н/Д')
            ethereum_price = crypto_data.get('ethereum', {}).get('usd', 'Н/Д')
            dogecoin_price = crypto_data.get('dogecoin', {}).get('usd', 'Н/Д')
            ton_price = crypto_data.get('the-open-network', {}).get('usd', 'Н/Д')
            
            # Форматируем криптовалютные цены
            btc_str = f"${bitcoin_price:,.0f}" if isinstance(bitcoin_price, (int, float)) else str(bitcoin_price)
            eth_str = f"${ethereum_price:,.0f}" if isinstance(ethereum_price, (int, float)) else str(ethereum_price)
            doge_str = f"${dogecoin_price:.4f}" if isinstance(dogecoin_price, (int, float)) else str(dogecoin_price)
            ton_str = f"${ton_price:.2f}" if isinstance(ton_price, (int, float)) else str(ton_price)
                
        except Exception as e:
            logger.error(f"Ошибка получения курсов криптовалют: {e}")
            btc_str = eth_str = doge_str = ton_str = "❌ Ошибка API"
        
        # Формируем итоговое сообщение
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        message = f"""📊 <b>КУРСЫ ВАЛЮТ И КРИПТОВАЛЮТ</b>

💱 <b>Курсы валют ЦБ РФ:</b>
🇺🇸 USD: {usd_str}
🇪🇺 EUR: {eur_str}
🇨🇳 CNY: {cny_str}

₿ <b>Криптовалюты:</b>
🟠 Bitcoin: {btc_str}
🔷 Ethereum: {eth_str}
🐕 Dogecoin: {doge_str}
💎 TON: {ton_str}

⏰ <b>Время:</b> {current_time}
📡 <b>Источники:</b> ЦБ РФ, CoinGecko"""

        await update.message.reply_html(message)
        
    except Exception as e:
        logger.error(f"Общая ошибка в rates_command: {e}")
        await update.message.reply_text(
            f"❌ Ошибка получения курсов: {str(e)}\n\n"
            f"🔄 Попробуйте позже или обратитесь к администратору."
        )

def main() -> None:
    """Запуск бота - минимальная версия"""
    logger.info("🤖 Запуск чистого бота...")
    
    application = Application.builder().token(BOT_TOKEN).build()

    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("my_id", my_id_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("rates", rates_command))

    # Обработчик всех текстовых сообщений (эхо)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Запуск бота
    logger.info("✅ Бот запущен и готов к работе")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 