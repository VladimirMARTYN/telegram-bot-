#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import asyncio
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import json
import aiohttp

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

# Файл для сохранения данных пользователей
USER_DATA_FILE = "user_data.json"

# Словарь пользователей (будет загружен из файла)
user_data = {}

def save_user_data():
    """Сохранение данных пользователей в файл"""
    try:
        with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Данные {len(user_data)} пользователей сохранены в {USER_DATA_FILE}")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения пользователей: {e}")

def load_user_data():
    """Загрузка данных пользователей из файла"""
    global user_data
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                # Преобразуем строковые ключи обратно в int
                user_data = {int(user_id): user_info for user_id, user_info in loaded_data.items()}
                logger.info(f"📂 Загружены данные {len(user_data)} пользователей из {USER_DATA_FILE}")
        else:
            logger.info(f"📂 Файл {USER_DATA_FILE} не найден, создаем новую базу пользователей")
            user_data = {}
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки пользователей: {e}")
        user_data = {}

# Функции команд

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    
    # Регистрируем пользователя
    if user_id not in user_data:
        user_data[user_id] = {
            'name': user.first_name,
            'username': user.username,
            'first_seen': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat()
        }
        logger.info(f"👤 Новый пользователь: {user.first_name} (ID: {user_id})")
        # Сохраняем данные пользователей при добавлении нового
        save_user_data()
    else:
        # Обновляем время последней активности
        user_data[user_id]['last_activity'] = datetime.now().isoformat()
        # Сохраняем обновленные данные
        save_user_data()
    
    welcome_text = (
        f"👋 <b>Привет, {user.first_name}!</b>\n\n"
        f"🤖 Это чистый Telegram бот\n\n"
        f"📋 <b>Доступные команды:</b>\n"
        f"/help - Справка\n"
        f"/ping - Проверка работы\n"
        f"/rates - Курсы валют и криптовалют\n"
        f"/stocks - Топ российских акций\n"
        f"/my_id - Узнать свой ID\n"
    )
    
    # Показываем админские команды только администратору
    if user_id == ADMIN_USER_ID:
        welcome_text += f"/fix_admin_id - Исправить права администратора\n"
    elif ADMIN_USER_ID == 0:
        # Если ADMIN_USER_ID не настроен, показываем команду исправления
        welcome_text += f"/fix_admin_id - Стать администратором (не настроен)\n"
    
    welcome_text += "\n"
    
    if user_id == ADMIN_USER_ID:
        welcome_text += "👨‍💻 <b>Статус:</b> Администратор\n"
    else:
        welcome_text += "👤 <b>Статус:</b> Пользователь\n"
    
    welcome_text += f"📊 <b>Пользователей:</b> {len(user_data)}"
    
    await update.message.reply_html(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    user_id = update.effective_user.id
    is_admin = user_id == ADMIN_USER_ID
    
    help_text = (
        "🤖 <b>Справка по боту</b>\n\n"
        
        "📋 <b>Команды:</b>\n"
        "/start - Запуск бота\n"
        "/help - Эта справка\n"
        "/ping - Проверка работы\n"
        "/rates - Курсы валют и криптовалют\n"
        "/stocks - Топ российских акций\n"
        "/my_id - Узнать свой ID\n"
    )
    
    # Показываем админские команды только администратору
    if is_admin:
        help_text += "/fix_admin_id - Исправить права администратора\n"
    elif ADMIN_USER_ID == 0:
        # Если ADMIN_USER_ID не настроен, показываем команду исправления всем
        help_text += "/fix_admin_id - Стать администратором (не настроен)\n"
    
    help_text += (
        "\n💱 <b>Функции:</b>\n"
        "• Курсы валют ЦБ РФ (USD, EUR, CNY)\n"
        "• Курсы криптовалют (Bitcoin, Ethereum, Dogecoin, TON)\n"
        "• Топ российских акций (Московская биржа)\n"
    )
    
    help_text += (
        "\nℹ️ <b>Информация:</b>\n"
        "Бот готов к расширению функционала."
    )
    
    if is_admin:
        help_text += f"\n\n👨‍💻 <b>Статус:</b> Администратор\n📊 Пользователей в базе: {len(user_data)}"
    
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
        f"/rates - Курсы валют и криптовалют\n"
        f"/stocks - Топ российских акций\n"
        f"/fix_admin_id - Исправить права администратора\n\n"
        
        f"💱 <b>Доступные функции:</b>\n"
        f"• Курсы валют ЦБ РФ (USD, EUR, CNY)\n"
        f"• Курсы криптовалют (BTC, ETH, DOGE, TON)\n"
        f"• Топ российских акций (Московская биржа)\n\n"
        
        f"👥 <b>Статистика:</b>\n"
        f"• Пользователей в базе: {len(user_data)}\n\n"
        
        f"🔧 <b>ADMIN_USER_ID:</b> {ADMIN_USER_ID}\n"
        f"🆔 <b>Ваш ID:</b> {user_id}\n"
        f"✅ <b>Права:</b> {'Корректные' if user_id == ADMIN_USER_ID else '❌ Требуют исправления (/fix_admin_id)'}\n\n"
        
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



async def fix_admin_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Временное исправление ADMIN_USER_ID"""
    global ADMIN_USER_ID
    user_id = update.effective_user.id
    
    # Показываем текущее состояние
    current_info = (
        f"🔧 <b>ИСПРАВЛЕНИЕ ADMIN_USER_ID</b>\n\n"
        f"📊 <b>Текущие значения:</b>\n"
        f"• Ваш ID: <code>{user_id}</code>\n"
        f"• ADMIN_USER_ID: <code>{ADMIN_USER_ID}</code>\n"
        f"• Из переменной окружения: <code>{os.getenv('ADMIN_USER_ID', 'НЕ УСТАНОВЛЕНА')}</code>\n\n"
    )
    
    # Если уже правильно настроено
    if ADMIN_USER_ID == user_id:
        await update.message.reply_html(
            current_info +
            f"✅ <b>УЖЕ НАСТРОЕНО ПРАВИЛЬНО!</b>\n\n"
            f"ADMIN_USER_ID = {ADMIN_USER_ID} совпадает с вашим ID.\n"
            f"Попробуйте команду /broadcast снова."
        )
        return
    
    # Исправляем ADMIN_USER_ID
    old_admin_id = ADMIN_USER_ID
    ADMIN_USER_ID = user_id
    
    success_msg = (
        current_info +
        f"✅ <b>ИСПРАВЛЕНО УСПЕШНО!</b>\n\n"
        f"🔄 <b>Изменения:</b>\n"
        f"• Было: <code>{old_admin_id}</code>\n"
        f"• Стало: <code>{ADMIN_USER_ID}</code>\n\n"
        f"🎉 <b>Теперь вы администратор!</b>\n"
        f"Попробуйте команду /broadcast\n\n"
        f"⚠️ <b>ВНИМАНИЕ:</b> Это временное исправление!\n"
        f"После перезапуска бота нужно будет:\n"
        f"1. Установить переменную ADMIN_USER_ID = {user_id} на Railway\n"
        f"2. Или снова использовать /fix_admin_id"
    )
    
    await update.message.reply_html(success_msg)
    
    # Логируем изменение
    logger.info(f"🔧 ADMIN_USER_ID исправлен: {old_admin_id} → {ADMIN_USER_ID}")







async def stocks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /stocks - топ 10 российских акций"""
    user_id = update.effective_user.id
    user = update.effective_user
    
    # Регистрируем/обновляем пользователя
    if user_id not in user_data:
        user_data[user_id] = {
            'name': user.first_name,
            'username': user.username,
            'first_seen': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat()
        }
        save_user_data()
    else:
        user_data[user_id]['last_activity'] = datetime.now().isoformat()
        save_user_data()
    
    loading_msg = await update.message.reply_html("📈 <b>Загружаю данные российских акций...</b>")
    
    try:
        # API Московской биржи для получения акций
        moex_url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
        
        # Получаем данные с Московской биржи
        async with aiohttp.ClientSession() as session:
            async with session.get(moex_url) as response:
                if response.status != 200:
                    raise Exception(f"Ошибка API MOEX: {response.status}")
                
                data = await response.json()
                
                # Извлекаем данные об акциях
                securities = data['securities']['data']
                marketdata = data['marketdata']['data']
                
                # Создаем словарь для объединения данных
                stocks_info = {}
                
                # Обрабатываем основную информацию об акциях
                security_columns = data['securities']['columns']
                for stock in securities:
                    stock_dict = dict(zip(security_columns, stock))
                    secid = stock_dict.get('SECID')
                    if secid:
                        stocks_info[secid] = {
                            'secid': secid,
                            'shortname': stock_dict.get('SHORTNAME', 'Не указано'),
                            'regnumber': stock_dict.get('REGNUMBER', ''),
                            'lotsize': stock_dict.get('LOTSIZE', 1),
                            'facevalue': stock_dict.get('FACEVALUE', 0)
                        }
                
                # Обрабатываем рыночные данные
                marketdata_columns = data['marketdata']['columns']
                for market in marketdata:
                    market_dict = dict(zip(marketdata_columns, market))
                    secid = market_dict.get('SECID')
                    if secid and secid in stocks_info:
                        stocks_info[secid].update({
                            'last': market_dict.get('LAST', 0),
                            'change': market_dict.get('CHANGE', 0),
                            'changeprcnt': market_dict.get('CHANGEPRCNT', 0),
                            'voltoday': market_dict.get('VOLTODAY', 0),
                            'valtoday': market_dict.get('VALTODAY', 0),
                            'marketcap': market_dict.get('MARKETCAP', 0),
                            'time': market_dict.get('TIME', ''),
                            'updatetime': market_dict.get('UPDATETIME', '')
                        })
                
                # Фильтруем акции с рыночными данными и сортируем по капитализации
                active_stocks = []
                for secid, info in stocks_info.items():
                    if (info.get('last', 0) and info.get('last') > 0 and 
                        info.get('marketcap', 0) and info.get('marketcap') > 0):
                        active_stocks.append(info)
                
                # Сортируем по рыночной капитализации (по убыванию)
                active_stocks.sort(key=lambda x: x.get('marketcap', 0), reverse=True)
                
                # Берем топ 10
                top_stocks = active_stocks[:10]
                
                if not top_stocks:
                    raise Exception("Не удалось получить данные об акциях")
                
                # Формируем результат
                result_text = "📈 <b>ТОП-10 РОССИЙСКИХ АКЦИЙ</b>\n"
                result_text += f"🏛️ <b>Московская биржа (MOEX)</b>\n\n"
                
                for i, stock in enumerate(top_stocks, 1):
                    name = stock.get('shortname', 'Не указано')
                    price = stock.get('last', 0)
                    change = stock.get('change', 0)
                    change_pct = stock.get('changeprcnt', 0)
                    marketcap = stock.get('marketcap', 0)
                    
                    # Форматируем название (обрезаем если слишком длинное)
                    if len(name) > 25:
                        name = name[:22] + "..."
                    
                    # Определяем эмодзи для изменения
                    if change > 0:
                        change_emoji = "📈"
                        change_color = "🟢"
                    elif change < 0:
                        change_emoji = "📉"
                        change_color = "🔴"
                    else:
                        change_emoji = "➡️"
                        change_color = "⚪"
                    
                    # Форматируем капитализацию
                    if marketcap >= 1_000_000_000_000:  # триллионы
                        cap_formatted = f"{marketcap/1_000_000_000_000:.1f} трлн ₽"
                    elif marketcap >= 1_000_000_000:  # миллиарды
                        cap_formatted = f"{marketcap/1_000_000_000:.1f} млрд ₽"
                    elif marketcap >= 1_000_000:  # миллионы
                        cap_formatted = f"{marketcap/1_000_000:.1f} млн ₽"
                    else:
                        cap_formatted = f"{marketcap:.0f} ₽"
                    
                    result_text += f"{i}. <b>{name}</b> ({stock.get('secid', '')})\n"
                    result_text += f"   💰 <b>{price:.2f} ₽</b>\n"
                    result_text += f"   {change_color} {change:+.2f} ₽ ({change_pct:+.2f}%) {change_emoji}\n"
                    result_text += f"   🏢 Капитализация: {cap_formatted}\n\n"
                
                # Добавляем время обновления
                current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
                result_text += f"📊 <b>Сортировка:</b> По рыночной капитализации\n"
                result_text += f"⏰ <b>Обновлено:</b> {current_time} (МСК)\n"
                result_text += f"📡 <b>Источник:</b> Московская биржа (MOEX)\n\n"
                result_text += f"💡 <b>Примечание:</b>\n"
                result_text += f"• Цены в российских рублях\n"
                result_text += f"• Данные обновляются в режиме реального времени\n"
                result_text += f"• 🟢 рост, 🔴 падение цены за день"
                
                await loading_msg.edit_text(result_text, parse_mode='HTML')
                
    except Exception as e:
        error_text = (
            f"❌ <b>Ошибка получения данных об акциях</b>\n\n"
            f"🚫 <b>Причина:</b> {str(e)}\n\n"
            f"💡 <b>Возможные причины:</b>\n"
            f"• Проблемы с API Московской биржи\n"
            f"• Временные неполадки сети\n"
            f"• Технические работы на бирже\n\n"
            f"🔄 <b>Попробуйте позже или используйте:</b>\n"
            f"/rates - курсы валют и криптовалют\n"
            f"/stocks - российские акции"
        )
        
        await loading_msg.edit_text(error_text, parse_mode='HTML')
        logger.error(f"Ошибка получения акций: {e}")

def main() -> None:
    """Запуск бота - минимальная версия"""
    logger.info("🚀 Запуск бота...")
    
    # Загружаем данные пользователей при старте
    load_user_data()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("my_id", my_id_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("rates", rates_command))
    application.add_handler(CommandHandler("fix_admin_id", fix_admin_id_command))
    application.add_handler(CommandHandler("stocks", stocks_command))

    # Обработчик всех текстовых сообщений (эхо)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Запуск бота
    logger.info("✅ Бот запущен и готов к работе")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 