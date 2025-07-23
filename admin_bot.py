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
        f"/convert - Конвертер валют\n"
        f"/compare - Сравнение активов\n"
        f"/trending - Тренды и лидеры дня\n"
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
        "/convert - Конвертер валют\n"
        "/compare - Сравнение активов\n"
        "/trending - Тренды и лидеры дня\n"
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
        "• Курсы валют ЦБ РФ (9 валют)\n"
        "• Конвертер валют с актуальными курсами\n"
        "• Сравнение валют и криптовалют\n"
        "• Анализ трендов и лидеров дня\n"
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
        f"/convert - Конвертер валют\n"
        f"/compare - Сравнение активов\n"
        f"/trending - Тренды и лидеры дня\n"
        f"/stocks - Топ российских акций\n"
        f"/fix_admin_id - Исправить права администратора\n\n"
        
        f"💱 <b>Доступные функции:</b>\n"
        f"• Курсы валют ЦБ РФ (9 валют)\n"
        f"• Конвертер валют между всеми парами\n"
        f"• Сравнение активов с аналитикой\n"
        f"• Анализ трендов и волатильности\n"
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
            gbp_rate = cbr_data.get('Valute', {}).get('GBP', {}).get('Value', 'Н/Д')
            jpy_rate = cbr_data.get('Valute', {}).get('JPY', {}).get('Value', 'Н/Д')
            chf_rate = cbr_data.get('Valute', {}).get('CHF', {}).get('Value', 'Н/Д')
            cad_rate = cbr_data.get('Valute', {}).get('CAD', {}).get('Value', 'Н/Д')
            aud_rate = cbr_data.get('Valute', {}).get('AUD', {}).get('Value', 'Н/Д')
            
            # Форматируем валютные курсы
            usd_str = f"{usd_rate:.2f} ₽" if isinstance(usd_rate, (int, float)) else str(usd_rate)
            eur_str = f"{eur_rate:.2f} ₽" if isinstance(eur_rate, (int, float)) else str(eur_rate)
            cny_str = f"{cny_rate:.2f} ₽" if isinstance(cny_rate, (int, float)) else str(cny_rate)
            gbp_str = f"{gbp_rate:.2f} ₽" if isinstance(gbp_rate, (int, float)) else str(gbp_rate)
            jpy_str = f"{jpy_rate:.4f} ₽" if isinstance(jpy_rate, (int, float)) else str(jpy_rate)  # JPY обычно в копейках
            chf_str = f"{chf_rate:.2f} ₽" if isinstance(chf_rate, (int, float)) else str(chf_rate)
            cad_str = f"{cad_rate:.2f} ₽" if isinstance(cad_rate, (int, float)) else str(cad_rate)
            aud_str = f"{aud_rate:.2f} ₽" if isinstance(aud_rate, (int, float)) else str(aud_rate)
                
        except Exception as e:
            logger.error(f"Ошибка получения курсов ЦБ РФ: {e}")
            usd_str = eur_str = cny_str = gbp_str = jpy_str = chf_str = cad_str = aud_str = "❌ Ошибка API"
        
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

💱 <b>Основные валюты ЦБ РФ:</b>
🇺🇸 USD: {usd_str}
🇪🇺 EUR: {eur_str}
🇨🇳 CNY: {cny_str}

🌍 <b>Дополнительные валюты:</b>
🇬🇧 GBP: {gbp_str}
🇯🇵 JPY: {jpy_str}
🇨🇭 CHF: {chf_str}
🇨🇦 CAD: {cad_str}
🇦🇺 AUD: {aud_str}

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
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(moex_url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"MOEX API error {response.status}: {error_text[:200]}")
                    raise Exception(f"Ошибка API MOEX: статус {response.status}")
                
                data = await response.json()
                
                # Проверяем структуру данных
                if not data or 'securities' not in data or 'marketdata' not in data:
                    raise Exception("Неверная структура данных от MOEX API")
                
                securities_data = data.get('securities', {}).get('data', [])
                marketdata_data = data.get('marketdata', {}).get('data', [])
                
                if not securities_data or not marketdata_data:
                    raise Exception("Пустые данные от MOEX API")
                
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
                        # Безопасное преобразование значений в числа
                        def safe_float(value, default=0.0):
                            if value is None or value == '':
                                return default
                            try:
                                return float(value)
                            except (ValueError, TypeError):
                                return default
                        
                        def safe_int(value, default=0):
                            if value is None or value == '':
                                return default
                            try:
                                return int(float(value))
                            except (ValueError, TypeError):
                                return default
                        
                        stocks_info[secid].update({
                            'last': safe_float(market_dict.get('LAST'), 0),
                            'change': safe_float(market_dict.get('CHANGE'), 0),
                            'changeprcnt': safe_float(market_dict.get('CHANGEPRCNT'), 0),
                            'voltoday': safe_int(market_dict.get('VOLTODAY'), 0),
                            'valtoday': safe_float(market_dict.get('VALTODAY'), 0),
                            'marketcap': safe_float(market_dict.get('MARKETCAP'), 0),
                            'time': str(market_dict.get('TIME', '')),
                            'updatetime': str(market_dict.get('UPDATETIME', ''))
                        })
                
                # Фильтруем акции с рыночными данными и сортируем по капитализации
                active_stocks = []
                for secid, info in stocks_info.items():
                    # Проверяем что у акции есть цена и капитализация
                    last_price = info.get('last', 0)
                    market_cap = info.get('marketcap', 0)
                    
                    if (last_price and last_price > 0 and market_cap and market_cap > 0):
                        active_stocks.append(info)
                
                # Сортируем по рыночной капитализации (по убыванию)
                active_stocks.sort(key=lambda x: float(x.get('marketcap', 0)), reverse=True)
                
                # Берем топ 10
                top_stocks = active_stocks[:10]
                
                if not top_stocks:
                    # Если нет акций с полными данными, берем любые доступные
                    all_stocks = list(stocks_info.values())
                    available_stocks = [s for s in all_stocks if s.get('last', 0) and float(s.get('last', 0)) > 0]
                    
                    if available_stocks:
                        available_stocks.sort(key=lambda x: float(x.get('last', 0)), reverse=True)
                        top_stocks = available_stocks[:10]
                    else:
                        raise Exception("Нет доступных данных по российским акциям")
                
                # Формируем результат
                result_text = "📈 <b>ТОП-10 РОССИЙСКИХ АКЦИЙ</b>\n"
                result_text += f"🏛️ <b>Московская биржа (MOEX)</b>\n\n"
                
                for i, stock in enumerate(top_stocks, 1):
                    name = stock.get('shortname', 'Не указано')
                    price = stock.get('last', 0)
                    change = stock.get('change', 0)
                    change_pct = stock.get('changeprcnt', 0)
                    marketcap = stock.get('marketcap', 0)
                    
                    # Безопасное преобразование значений для отображения
                    try:
                        price = float(price) if price else 0
                        change = float(change) if change else 0
                        change_pct = float(change_pct) if change_pct else 0
                        marketcap = float(marketcap) if marketcap else 0
                    except (ValueError, TypeError):
                        price = change = change_pct = marketcap = 0
                    
                    # Форматируем название (обрезаем если слишком длинное)
                    if len(str(name)) > 25:
                        name = str(name)[:22] + "..."
                    
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
                        cap_formatted = f"{marketcap:.0f} ₽" if marketcap > 0 else "н/д"
                    
                    result_text += f"{i}. <b>{name}</b> ({stock.get('secid', '')})\n"
                    
                    # Безопасное форматирование цены
                    if price > 0:
                        result_text += f"   💰 <b>{price:.2f} ₽</b>\n"
                    else:
                        result_text += f"   💰 <b>н/д</b>\n"
                    
                    # Безопасное форматирование изменения
                    if price > 0:
                        result_text += f"   {change_color} {change:+.2f} ₽ ({change_pct:+.2f}%) {change_emoji}\n"
                    else:
                        result_text += f"   ⚪ н/д ➡️\n"
                    
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

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Конвертер валют - /convert [сумма] [из] [в]"""
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
    
    # Проверяем аргументы команды
    if len(context.args) != 3:
        await update.message.reply_html(
            "💱 <b>КОНВЕРТЕР ВАЛЮТ</b>\n\n"
            "🔍 <b>Использование:</b>\n"
            "<code>/convert [сумма] [из валюты] [в валюту]</code>\n\n"
            "💡 <b>Примеры:</b>\n"
            "• <code>/convert 100 USD RUB</code> - доллары в рубли\n"
            "• <code>/convert 5000 RUB EUR</code> - рубли в евро\n"
            "• <code>/convert 1000 CNY USD</code> - юани в доллары\n"
            "• <code>/convert 50 EUR CNY</code> - евро в юани\n\n"
            "💰 <b>Поддерживаемые валюты:</b>\n"
            "🇷🇺 <code>RUB</code> - Российский рубль\n"
            "🇺🇸 <code>USD</code> - Доллар США\n"
            "🇪🇺 <code>EUR</code> - Евро\n"
            "🇨🇳 <code>CNY</code> - Китайский юань\n"
            "🇬🇧 <code>GBP</code> - Британский фунт\n"
            "🇯🇵 <code>JPY</code> - Японская иена\n"
            "🇨🇭 <code>CHF</code> - Швейцарский франк\n"
            "🇨🇦 <code>CAD</code> - Канадский доллар\n"
            "🇦🇺 <code>AUD</code> - Австралийский доллар\n\n"
            "📊 <b>Курсы обновляются в реальном времени от ЦБ РФ</b>"
        )
        return
    
    try:
        # Парсим аргументы
        amount_str, from_currency, to_currency = context.args
        amount = float(amount_str)
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        
        # Проверяем корректность суммы
        if amount <= 0:
            await update.message.reply_html("❌ <b>Сумма должна быть положительным числом!</b>")
            return
            
        if amount > 1_000_000_000:
            await update.message.reply_html("❌ <b>Слишком большая сумма! Максимум 1 миллиард.</b>")
            return
        
        # Список поддерживаемых валют
        supported_currencies = ['RUB', 'USD', 'EUR', 'CNY', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD']
        if from_currency not in supported_currencies or to_currency not in supported_currencies:
            await update.message.reply_html(
                f"❌ <b>Неподдерживаемая валюта!</b>\n\n"
                f"💰 <b>Поддерживаемые:</b> {', '.join(supported_currencies)}\n"
                f"🚫 <b>Получено:</b> {from_currency} → {to_currency}"
            )
            return
            
        # Если конвертируем одну и ту же валюту
        if from_currency == to_currency:
            await update.message.reply_html(
                f"💱 <b>РЕЗУЛЬТАТ КОНВЕРТАЦИИ</b>\n\n"
                f"💰 <b>{amount:,.2f} {from_currency} = {amount:,.2f} {to_currency}</b>\n\n"
                f"💡 Конвертация в ту же валюту 😊"
            )
            return
        
        loading_msg = await update.message.reply_html("💱 <b>Получаю курсы валют...</b>")
        
        # Получаем курсы валют от ЦБ РФ
        import requests
        
        cbr_response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
        cbr_response.raise_for_status()
        cbr_data = cbr_response.json()
        
        # Создаем словарь курсов относительно рубля
        rates = {
            'RUB': 1.0,  # Рубль как базовая валюта
            'USD': cbr_data.get('Valute', {}).get('USD', {}).get('Value', 0),
            'EUR': cbr_data.get('Valute', {}).get('EUR', {}).get('Value', 0),
            'CNY': cbr_data.get('Valute', {}).get('CNY', {}).get('Value', 0),
            'GBP': cbr_data.get('Valute', {}).get('GBP', {}).get('Value', 0),
            'JPY': cbr_data.get('Valute', {}).get('JPY', {}).get('Value', 0),
            'CHF': cbr_data.get('Valute', {}).get('CHF', {}).get('Value', 0),
            'CAD': cbr_data.get('Valute', {}).get('CAD', {}).get('Value', 0),
            'AUD': cbr_data.get('Valute', {}).get('AUD', {}).get('Value', 0)
        }
        
        # Проверяем что получили курсы
        if not rates[from_currency] or not rates[to_currency]:
            raise Exception("Не удалось получить курсы валют")
        
        # Выполняем конвертацию через рубли
        if from_currency == 'RUB':
            # Из рублей в другую валюту
            result = amount / rates[to_currency]
        elif to_currency == 'RUB':
            # Из другой валюты в рубли
            result = amount * rates[from_currency]
        else:
            # Между двумя иностранными валютами через рубли
            rub_amount = amount * rates[from_currency]
            result = rub_amount / rates[to_currency]
        
        # Определяем эмодзи для валют
        currency_emoji = {
            'RUB': '🇷🇺',
            'USD': '🇺🇸', 
            'EUR': '🇪🇺',
            'CNY': '🇨🇳',
            'GBP': '🇬🇧',
            'JPY': '🇯🇵',
            'CHF': '🇨🇭',
            'CAD': '🇨🇦',
            'AUD': '🇦🇺'
        }
        
        # Формируем результат
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        result_text = f"💱 <b>РЕЗУЛЬТАТ КОНВЕРТАЦИИ</b>\n\n"
        result_text += f"{currency_emoji[from_currency]} <b>{amount:,.2f} {from_currency}</b>\n"
        result_text += f"                    ⬇️\n"
        result_text += f"{currency_emoji[to_currency]} <b>{result:,.2f} {to_currency}</b>\n\n"
        
        # Добавляем курс
        if from_currency == 'RUB':
            rate_display = f"1 {to_currency} = {rates[to_currency]:.4f} RUB"
        elif to_currency == 'RUB':
            rate_display = f"1 {from_currency} = {rates[from_currency]:.4f} RUB"
        else:
            cross_rate = rates[from_currency] / rates[to_currency]
            rate_display = f"1 {from_currency} = {cross_rate:.4f} {to_currency}"
        
        result_text += f"📊 <b>Курс:</b> {rate_display}\n"
        result_text += f"⏰ <b>Время:</b> {current_time} (МСК)\n"
        result_text += f"📡 <b>Источник:</b> ЦБ РФ\n\n"
        result_text += f"💡 <b>Другие примеры:</b>\n"
        result_text += f"<code>/convert 1000 {to_currency} {from_currency}</code>\n"
        result_text += f"<code>/convert {amount} {from_currency} EUR</code>"
        
        await loading_msg.edit_text(result_text, parse_mode='HTML')
        
    except ValueError:
        await update.message.reply_html(
            "❌ <b>Неверный формат суммы!</b>\n\n"
            "💡 <b>Примеры правильного формата:</b>\n"
            "• <code>/convert 100 USD RUB</code>\n"
            "• <code>/convert 50.5 EUR CNY</code>\n"
            "• <code>/convert 1000 RUB USD</code>"
        )
    except Exception as e:
        error_text = (
            f"❌ <b>Ошибка конвертации валют</b>\n\n"
            f"🚫 <b>Причина:</b> {str(e)}\n\n"
            f"💡 <b>Возможные причины:</b>\n"
            f"• Проблемы с API ЦБ РФ\n"
            f"• Временные неполадки сети\n"
            f"• Технические работы\n\n"
            f"🔄 <b>Попробуйте позже или используйте:</b>\n"
            f"/rates - просмотр курсов валют"
        )
        
        if 'loading_msg' in locals():
            await loading_msg.edit_text(error_text, parse_mode='HTML')
        else:
            await update.message.reply_html(error_text)
        
        logger.error(f"Ошибка конвертации валют: {e}")

async def compare_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сравнение валют и криптовалют - /compare [актив1] [актив2]"""
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
    
    # Проверяем аргументы команды
    if len(context.args) != 2:
        await update.message.reply_html(
            "⚖️ <b>СРАВНЕНИЕ АКТИВОВ</b>\n\n"
            "🔍 <b>Использование:</b>\n"
            "<code>/compare [актив1] [актив2]</code>\n\n"
            "💡 <b>Примеры:</b>\n"
            "<b>Валюты:</b>\n"
            "• <code>/compare USD EUR</code> - доллар vs евро\n"
            "• <code>/compare GBP JPY</code> - фунт vs иена\n"
            "• <code>/compare RUB CNY</code> - рубль vs юань\n\n"
            "<b>Криптовалюты:</b>\n"
            "• <code>/compare BTC ETH</code> - Bitcoin vs Ethereum\n"
            "• <code>/compare ETH TON</code> - Ethereum vs TON\n"
            "• <code>/compare BTC DOGE</code> - Bitcoin vs Dogecoin\n\n"
            "💰 <b>Поддерживаемые активы:</b>\n"
            "<b>Валюты:</b> RUB, USD, EUR, CNY, GBP, JPY, CHF, CAD, AUD\n"
            "<b>Криптовалюты:</b> BTC, ETH, DOGE, TON\n\n"
            "📊 <b>В результате вы получите подробное сравнение</b>"
        )
        return
    
    try:
        # Парсим аргументы
        asset1, asset2 = context.args
        asset1 = asset1.upper()
        asset2 = asset2.upper()
        
        # Если сравниваем один и тот же актив
        if asset1 == asset2:
            await update.message.reply_html(
                f"⚖️ <b>СРАВНЕНИЕ АКТИВОВ</b>\n\n"
                f"💡 <b>{asset1} = {asset2}</b>\n\n"
                f"Сравнение актива с самим собой 😊\n"
                f"Попробуйте сравнить разные активы!"
            )
            return
        
        # Определяем поддерживаемые активы
        currencies = ['RUB', 'USD', 'EUR', 'CNY', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD']
        crypto_assets = ['BTC', 'ETH', 'DOGE', 'TON']
        all_assets = currencies + crypto_assets
        
        # Проверяем что активы поддерживаются
        if asset1 not in all_assets or asset2 not in all_assets:
            unsupported = []
            if asset1 not in all_assets:
                unsupported.append(asset1)
            if asset2 not in all_assets:
                unsupported.append(asset2)
                
            await update.message.reply_html(
                f"❌ <b>Неподдерживаемые активы!</b>\n\n"
                f"🚫 <b>Не поддерживаются:</b> {', '.join(unsupported)}\n\n"
                f"💰 <b>Поддерживаемые валюты:</b>\n{', '.join(currencies)}\n\n"
                f"₿ <b>Поддерживаемые криптовалюты:</b>\n{', '.join(crypto_assets)}\n\n"
                f"💡 <b>Попробуйте:</b> <code>/compare BTC ETH</code>"
            )
            return
        
        loading_msg = await update.message.reply_html("⚖️ <b>Получаю данные для сравнения...</b>")
        
        # Получаем данные
        import requests
        
        # Данные валют от ЦБ РФ
        currency_data = {}
        if asset1 in currencies or asset2 in currencies:
            try:
                cbr_response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
                cbr_response.raise_for_status()
                cbr_data = cbr_response.json()
                
                currency_data = {
                    'RUB': {'value': 1.0, 'name': 'Российский рубль', 'flag': '🇷🇺'},
                    'USD': {'value': cbr_data.get('Valute', {}).get('USD', {}).get('Value', 0), 'name': 'Доллар США', 'flag': '🇺🇸'},
                    'EUR': {'value': cbr_data.get('Valute', {}).get('EUR', {}).get('Value', 0), 'name': 'Евро', 'flag': '🇪🇺'},
                    'CNY': {'value': cbr_data.get('Valute', {}).get('CNY', {}).get('Value', 0), 'name': 'Китайский юань', 'flag': '🇨🇳'},
                    'GBP': {'value': cbr_data.get('Valute', {}).get('GBP', {}).get('Value', 0), 'name': 'Британский фунт', 'flag': '🇬🇧'},
                    'JPY': {'value': cbr_data.get('Valute', {}).get('JPY', {}).get('Value', 0), 'name': 'Японская иена', 'flag': '🇯🇵'},
                    'CHF': {'value': cbr_data.get('Valute', {}).get('CHF', {}).get('Value', 0), 'name': 'Швейцарский франк', 'flag': '🇨🇭'},
                    'CAD': {'value': cbr_data.get('Valute', {}).get('CAD', {}).get('Value', 0), 'name': 'Канадский доллар', 'flag': '🇨🇦'},
                    'AUD': {'value': cbr_data.get('Valute', {}).get('AUD', {}).get('Value', 0), 'name': 'Австралийский доллар', 'flag': '🇦🇺'}
                }
            except Exception as e:
                logger.error(f"Ошибка получения курсов валют для сравнения: {e}")
                raise Exception("Не удалось получить курсы валют")
        
        # Данные криптовалют от CoinGecko
        crypto_data = {}
        if asset1 in crypto_assets or asset2 in crypto_assets:
            try:
                crypto_response = requests.get(
                    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,dogecoin,the-open-network&vs_currencies=usd&include_24hr_change=true&include_market_cap=true",
                    timeout=10
                )
                crypto_response.raise_for_status()
                crypto_json = crypto_response.json()
                
                crypto_data = {
                    'BTC': {
                        'value': crypto_json.get('bitcoin', {}).get('usd', 0),
                        'change': crypto_json.get('bitcoin', {}).get('usd_24h_change', 0),
                        'market_cap': crypto_json.get('bitcoin', {}).get('usd_market_cap', 0),
                        'name': 'Bitcoin',
                        'emoji': '🟠'
                    },
                    'ETH': {
                        'value': crypto_json.get('ethereum', {}).get('usd', 0),
                        'change': crypto_json.get('ethereum', {}).get('usd_24h_change', 0),
                        'market_cap': crypto_json.get('ethereum', {}).get('usd_market_cap', 0),
                        'name': 'Ethereum',
                        'emoji': '🔷'
                    },
                    'DOGE': {
                        'value': crypto_json.get('dogecoin', {}).get('usd', 0),
                        'change': crypto_json.get('dogecoin', {}).get('usd_24h_change', 0),
                        'market_cap': crypto_json.get('dogecoin', {}).get('usd_market_cap', 0),
                        'name': 'Dogecoin',
                        'emoji': '🐕'
                    },
                    'TON': {
                        'value': crypto_json.get('the-open-network', {}).get('usd', 0),
                        'change': crypto_json.get('the-open-network', {}).get('usd_24h_change', 0),
                        'market_cap': crypto_json.get('the-open-network', {}).get('usd_market_cap', 0),
                        'name': 'TON',
                        'emoji': '💎'
                    }
                }
            except Exception as e:
                logger.error(f"Ошибка получения данных криптовалют для сравнения: {e}")
                raise Exception("Не удалось получить данные криптовалют")
        
        # Формируем результат сравнения
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
        result_text = f"⚖️ <b>СРАВНЕНИЕ АКТИВОВ</b>\n\n"
        
        # Получаем данные для каждого актива
        def get_asset_info(asset):
            if asset in currencies:
                data = currency_data[asset]
                return {
                    'type': 'currency',
                    'symbol': data['flag'],
                    'name': data['name'],
                    'value_rub': data['value'],
                    'code': asset
                }
            else:
                data = crypto_data[asset]
                return {
                    'type': 'crypto',
                    'symbol': data['emoji'],
                    'name': data['name'],
                    'value_usd': data['value'],
                    'change_24h': data['change'],
                    'market_cap': data['market_cap'],
                    'code': asset
                }
        
        info1 = get_asset_info(asset1)
        info2 = get_asset_info(asset2)
        
        # Заголовки активов
        result_text += f"{info1['symbol']} <b>{info1['name']} ({asset1})</b>\n"
        
        if info1['type'] == 'currency':
            if asset1 == 'RUB':
                result_text += f"💰 Курс: 1.00 ₽ (базовая валюта)\n"
            else:
                result_text += f"💰 Курс: {info1['value_rub']:.4f} ₽\n"
        else:
            change_emoji = "📈" if info1['change_24h'] > 0 else "📉" if info1['change_24h'] < 0 else "➡️"
            result_text += f"💰 Цена: ${info1['value_usd']:,.2f}\n"
            result_text += f"📊 24ч: {info1['change_24h']:+.2f}% {change_emoji}\n"
            if info1['market_cap'] > 0:
                market_cap_b = info1['market_cap'] / 1_000_000_000
                result_text += f"🏛️ Капитализация: ${market_cap_b:.1f}B\n"
        
        result_text += f"\n              🆚\n\n"
        
        result_text += f"{info2['symbol']} <b>{info2['name']} ({asset2})</b>\n"
        
        if info2['type'] == 'currency':
            if asset2 == 'RUB':
                result_text += f"💰 Курс: 1.00 ₽ (базовая валюта)\n"
            else:
                result_text += f"💰 Курс: {info2['value_rub']:.4f} ₽\n"
        else:
            change_emoji = "📈" if info2['change_24h'] > 0 else "📉" if info2['change_24h'] < 0 else "➡️"
            result_text += f"💰 Цена: ${info2['value_usd']:,.2f}\n"
            result_text += f"📊 24ч: {info2['change_24h']:+.2f}% {change_emoji}\n"
            if info2['market_cap'] > 0:
                market_cap_b = info2['market_cap'] / 1_000_000_000
                result_text += f"🏛️ Капитализация: ${market_cap_b:.1f}B\n"
        
        # Добавляем сравнительный анализ
        result_text += f"\n📊 <b>АНАЛИЗ СРАВНЕНИЯ:</b>\n"
        
        # Сравнение валют
        if info1['type'] == 'currency' and info2['type'] == 'currency':
            if asset1 == 'RUB':
                rate = 1 / info2['value_rub']
                result_text += f"• 1 {asset2} = {info2['value_rub']:.4f} {asset1}\n"
                result_text += f"• 1 {asset1} = {rate:.4f} {asset2}\n"
            elif asset2 == 'RUB':
                rate = 1 / info1['value_rub']
                result_text += f"• 1 {asset1} = {info1['value_rub']:.4f} {asset2}\n"
                result_text += f"• 1 {asset2} = {rate:.4f} {asset1}\n"
            else:
                cross_rate = info1['value_rub'] / info2['value_rub']
                reverse_rate = info2['value_rub'] / info1['value_rub']
                result_text += f"• 1 {asset1} = {cross_rate:.4f} {asset2}\n"
                result_text += f"• 1 {asset2} = {reverse_rate:.4f} {asset1}\n"
        
        # Сравнение криптовалют
        elif info1['type'] == 'crypto' and info2['type'] == 'crypto':
            ratio = info1['value_usd'] / info2['value_usd'] if info2['value_usd'] > 0 else 0
            reverse_ratio = info2['value_usd'] / info1['value_usd'] if info1['value_usd'] > 0 else 0
            
            result_text += f"• 1 {asset1} = {ratio:.4f} {asset2}\n"
            result_text += f"• 1 {asset2} = {reverse_ratio:.4f} {asset1}\n"
            
            # Сравнение динамики
            if abs(info1['change_24h']) > abs(info2['change_24h']):
                result_text += f"• {asset1} более волатилен сегодня\n"
            elif abs(info2['change_24h']) > abs(info1['change_24h']):
                result_text += f"• {asset2} более волатилен сегодня\n"
            else:
                result_text += f"• Похожая волатильность\n"
            
            # Сравнение капитализации
            if info1['market_cap'] > info2['market_cap'] * 2:
                result_text += f"• {asset1} значительно крупнее по капитализации\n"
            elif info2['market_cap'] > info1['market_cap'] * 2:
                result_text += f"• {asset2} значительно крупнее по капитализации\n"
            else:
                result_text += f"• Сопоставимые по капитализации\n"
        
        # Смешанное сравнение (валюта vs крипто)
        else:
            result_text += f"• Сравнение валюты и криптовалюты\n"
            result_text += f"• Разные классы активов\n"
            result_text += f"• Разные источники данных\n"
        
        result_text += f"\n⏰ <b>Время:</b> {current_time} (МСК)\n"
        result_text += f"📡 <b>Источники:</b> "
        
        sources = []
        if any(info['type'] == 'currency' for info in [info1, info2]):
            sources.append("ЦБ РФ")
        if any(info['type'] == 'crypto' for info in [info1, info2]):
            sources.append("CoinGecko")
        
        result_text += ", ".join(sources)
        
        result_text += f"\n\n💡 <b>Другие сравнения:</b>\n"
        result_text += f"<code>/compare BTC ETH</code>\n"
        result_text += f"<code>/compare USD EUR</code>"
        
        await loading_msg.edit_text(result_text, parse_mode='HTML')
        
    except Exception as e:
        error_text = (
            f"❌ <b>Ошибка сравнения активов</b>\n\n"
            f"🚫 <b>Причина:</b> {str(e)}\n\n"
            f"💡 <b>Возможные причины:</b>\n"
            f"• Проблемы с API (ЦБ РФ или CoinGecko)\n"
            f"• Временные неполадки сети\n"
            f"• Технические работы\n\n"
            f"🔄 <b>Попробуйте позже или используйте:</b>\n"
            f"/rates - просмотр курсов\n"
            f"/convert - конвертер валют"
        )
        
        if 'loading_msg' in locals():
            await loading_msg.edit_text(error_text, parse_mode='HTML')
        else:
            await update.message.reply_html(error_text)
        
        logger.error(f"Ошибка сравнения активов: {e}")

async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Тренды дня - лидеры роста и падения /trending"""
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
    
    loading_msg = await update.message.reply_html("🔥 <b>Анализирую тренды рынка...</b>")
    
    try:
        import requests
        
        # Получаем данные криптовалют с изменениями за 24ч
        crypto_response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,dogecoin,the-open-network&vs_currencies=usd&include_24hr_change=true&include_market_cap=true",
            timeout=10
        )
        crypto_response.raise_for_status()
        crypto_data = crypto_response.json()
        
        # Получаем курсы валют (они обновляются ежедневно, поэтому изменения будут минимальными)
        cbr_response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
        cbr_response.raise_for_status()
        cbr_data = cbr_response.json()
        
        # Формируем данные криптовалют
        crypto_assets = []
        
        bitcoin_data = crypto_data.get('bitcoin', {})
        if bitcoin_data:
            crypto_assets.append({
                'symbol': 'BTC',
                'name': 'Bitcoin',
                'emoji': '🟠',
                'price': bitcoin_data.get('usd', 0),
                'change_24h': bitcoin_data.get('usd_24h_change', 0),
                'market_cap': bitcoin_data.get('usd_market_cap', 0)
            })
        
        ethereum_data = crypto_data.get('ethereum', {})
        if ethereum_data:
            crypto_assets.append({
                'symbol': 'ETH',
                'name': 'Ethereum',
                'emoji': '🔷',
                'price': ethereum_data.get('usd', 0),
                'change_24h': ethereum_data.get('usd_24h_change', 0),
                'market_cap': ethereum_data.get('usd_market_cap', 0)
            })
        
        dogecoin_data = crypto_data.get('dogecoin', {})
        if dogecoin_data:
            crypto_assets.append({
                'symbol': 'DOGE',
                'name': 'Dogecoin',
                'emoji': '🐕',
                'price': dogecoin_data.get('usd', 0),
                'change_24h': dogecoin_data.get('usd_24h_change', 0),
                'market_cap': dogecoin_data.get('usd_market_cap', 0)
            })
        
        ton_data = crypto_data.get('the-open-network', {})
        if ton_data:
            crypto_assets.append({
                'symbol': 'TON',
                'name': 'TON',
                'emoji': '💎',
                'price': ton_data.get('usd', 0),
                'change_24h': ton_data.get('usd_24h_change', 0),
                'market_cap': ton_data.get('usd_market_cap', 0)
            })
        
        # Сортируем по изменению за 24ч
        crypto_assets.sort(key=lambda x: x['change_24h'], reverse=True)
        
        # Формируем валютные данные (для валют изменения минимальны, но покажем курсы)
        currency_assets = []
        
        currencies_info = {
            'USD': {'name': 'Доллар США', 'flag': '🇺🇸', 'rate': cbr_data.get('Valute', {}).get('USD', {}).get('Value', 0)},
            'EUR': {'name': 'Евро', 'flag': '🇪🇺', 'rate': cbr_data.get('Valute', {}).get('EUR', {}).get('Value', 0)},
            'GBP': {'name': 'Британский фунт', 'flag': '🇬🇧', 'rate': cbr_data.get('Valute', {}).get('GBP', {}).get('Value', 0)},
            'CNY': {'name': 'Китайский юань', 'flag': '🇨🇳', 'rate': cbr_data.get('Valute', {}).get('CNY', {}).get('Value', 0)},
            'JPY': {'name': 'Японская иена', 'flag': '🇯🇵', 'rate': cbr_data.get('Valute', {}).get('JPY', {}).get('Value', 0)}
        }
        
        for symbol, info in currencies_info.items():
            if info['rate']:
                currency_assets.append({
                    'symbol': symbol,
                    'name': info['name'],
                    'flag': info['flag'],
                    'rate': info['rate']
                })
        
        # Формируем результат
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
        result_text = f"🔥 <b>ТРЕНДЫ ДНЯ</b>\n\n"
        
        # Криптовалютные тренды
        result_text += f"₿ <b>КРИПТОВАЛЮТЫ (24 часа):</b>\n\n"
        
        if crypto_assets:
            # Лидер роста
            best_crypto = crypto_assets[0]
            if best_crypto['change_24h'] > 0:
                result_text += f"📈 <b>ЛИДЕР РОСТА:</b>\n"
                result_text += f"{best_crypto['emoji']} <b>{best_crypto['name']} ({best_crypto['symbol']})</b>\n"
                result_text += f"💰 ${best_crypto['price']:,.2f}\n"
                result_text += f"🚀 <b>+{best_crypto['change_24h']:.2f}%</b> 📈\n"
                if best_crypto['market_cap'] > 0:
                    cap_b = best_crypto['market_cap'] / 1_000_000_000
                    result_text += f"🏛️ ${cap_b:.1f}B\n"
                result_text += f"\n"
            
            # Лидер падения  
            worst_crypto = crypto_assets[-1]
            if worst_crypto['change_24h'] < 0:
                result_text += f"📉 <b>ЛИДЕР ПАДЕНИЯ:</b>\n"
                result_text += f"{worst_crypto['emoji']} <b>{worst_crypto['name']} ({worst_crypto['symbol']})</b>\n"
                result_text += f"💰 ${worst_crypto['price']:,.2f}\n"
                result_text += f"🔴 <b>{worst_crypto['change_24h']:.2f}%</b> 📉\n"
                if worst_crypto['market_cap'] > 0:
                    cap_b = worst_crypto['market_cap'] / 1_000_000_000
                    result_text += f"🏛️ ${cap_b:.1f}B\n"
                result_text += f"\n"
            
            # Все криптовалюты по порядку
            result_text += f"📊 <b>ВСЕ КРИПТОВАЛЮТЫ:</b>\n"
            for i, asset in enumerate(crypto_assets, 1):
                change = asset['change_24h']
                if change > 0:
                    change_emoji = "📈"
                    change_str = f"+{change:.2f}%"
                    change_color = "🟢"
                elif change < 0:
                    change_emoji = "📉"
                    change_str = f"{change:.2f}%"
                    change_color = "🔴"
                else:
                    change_emoji = "➡️"
                    change_str = "0.00%"
                    change_color = "⚪"
                
                result_text += f"{i}. {asset['emoji']} <b>{asset['symbol']}</b> {change_color} {change_str} {change_emoji}\n"
        
        # Волатильность анализ
        if crypto_assets:
            volatilities = [abs(asset['change_24h']) for asset in crypto_assets]
            max_volatility = max(volatilities)
            most_volatile = next(asset for asset in crypto_assets if abs(asset['change_24h']) == max_volatility)
            
            result_text += f"\n🌡️ <b>ВОЛАТИЛЬНОСТЬ:</b>\n"
            result_text += f"🔥 Самый волатильный: <b>{most_volatile['symbol']}</b> (±{max_volatility:.2f}%)\n"
            
            # Средняя волатильность
            avg_volatility = sum(volatilities) / len(volatilities)
            result_text += f"📊 Средняя волатильность: {avg_volatility:.2f}%\n"
        
        # Валютная секция
        result_text += f"\n💱 <b>ОСНОВНЫЕ ВАЛЮТЫ (ЦБ РФ):</b>\n"
        
        if currency_assets:
            for i, currency in enumerate(currency_assets[:5], 1):
                if currency['symbol'] == 'JPY':
                    rate_str = f"{currency['rate']:.4f} ₽"
                else:
                    rate_str = f"{currency['rate']:.2f} ₽"
                
                result_text += f"{i}. {currency['flag']} <b>{currency['symbol']}</b> - {rate_str}\n"
        
        # Добавляем общую аналитику
        result_text += f"\n🎯 <b>РЫНОЧНАЯ СВОДКА:</b>\n"
        
        if crypto_assets:
            positive_count = sum(1 for asset in crypto_assets if asset['change_24h'] > 0)
            negative_count = sum(1 for asset in crypto_assets if asset['change_24h'] < 0)
            
            if positive_count > negative_count:
                result_text += f"✅ Рынок криптовалют: <b>Растущий</b> ({positive_count} растут, {negative_count} падают)\n"
            elif negative_count > positive_count:
                result_text += f"❌ Рынок криптовалют: <b>Падающий</b> ({negative_count} падают, {positive_count} растут)\n"
            else:
                result_text += f"⚖️ Рынок криптовалют: <b>Смешанный</b> ({positive_count} растут, {negative_count} падают)\n"
            
            # Общий тренд
            avg_change = sum(asset['change_24h'] for asset in crypto_assets) / len(crypto_assets)
            if avg_change > 1:
                result_text += f"📈 Общий тренд: <b>Сильный рост</b> (+{avg_change:.2f}%)\n"
            elif avg_change > 0:
                result_text += f"📈 Общий тренд: <b>Умеренный рост</b> (+{avg_change:.2f}%)\n"
            elif avg_change < -1:
                result_text += f"📉 Общий тренд: <b>Сильное падение</b> ({avg_change:.2f}%)\n"
            elif avg_change < 0:
                result_text += f"📉 Общий тренд: <b>Умеренное падение</b> ({avg_change:.2f}%)\n"
            else:
                result_text += f"➡️ Общий тренд: <b>Боковое движение</b> ({avg_change:.2f}%)\n"
        
        result_text += f"\n⏰ <b>Время:</b> {current_time} (МСК)\n"
        result_text += f"📡 <b>Источники:</b> CoinGecko, ЦБ РФ\n\n"
        result_text += f"💡 <b>Используйте для детального анализа:</b>\n"
        result_text += f"<code>/compare BTC ETH</code> - сравнить активы\n"
        result_text += f"<code>/rates</code> - текущие курсы"
        
        await loading_msg.edit_text(result_text, parse_mode='HTML')
        
    except Exception as e:
        error_text = (
            f"❌ <b>Ошибка получения трендов</b>\n\n"
            f"🚫 <b>Причина:</b> {str(e)}\n\n"
            f"💡 <b>Возможные причины:</b>\n"
            f"• Проблемы с API CoinGecko или ЦБ РФ\n"
            f"• Временные неполадки сети\n"
            f"• Технические работы на биржах\n\n"
            f"🔄 <b>Попробуйте позже или используйте:</b>\n"
            f"/rates - текущие курсы\n"
            f"/compare BTC ETH - сравнение активов"
        )
        
        await loading_msg.edit_text(error_text, parse_mode='HTML')
        logger.error(f"Ошибка получения трендов: {e}")

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
    application.add_handler(CommandHandler("convert", convert_command))
    application.add_handler(CommandHandler("compare", compare_command))
    application.add_handler(CommandHandler("trending", trending_command))
    application.add_handler(CommandHandler("fix_admin_id", fix_admin_id_command))
    application.add_handler(CommandHandler("stocks", stocks_command))

    # Обработчик всех текстовых сообщений (эхо)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Запуск бота
    logger.info("✅ Бот запущен и готов к работе")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 