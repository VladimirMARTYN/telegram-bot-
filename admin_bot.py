#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
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

def get_moscow_time():
    """Получить текущее московское время"""
    moscow_tz = pytz.timezone('Europe/Moscow')
    return datetime.now(moscow_tz)

# Создание inline клавиатур
def create_main_menu_keyboard():
    """Создать главное меню с inline кнопками"""
    keyboard = [
        [
            InlineKeyboardButton("💱 Курсы валют", callback_data="rates"),
            InlineKeyboardButton("❓ Справка", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_rates_keyboard():
    """Создать клавиатуру для быстрого выбора валют"""
    keyboard = [
        [
            InlineKeyboardButton("💵 USD", callback_data="rate_USD"),
            InlineKeyboardButton("💶 EUR", callback_data="rate_EUR"),
            InlineKeyboardButton("💷 GBP", callback_data="rate_GBP")
        ],
        [
            InlineKeyboardButton("💴 JPY", callback_data="rate_JPY"),
            InlineKeyboardButton("🇨🇭 CHF", callback_data="rate_CHF"),
            InlineKeyboardButton("🇨🇳 CNY", callback_data="rate_CNY")
        ],
        [
            InlineKeyboardButton("₿ Bitcoin", callback_data="rate_BTC"),
            InlineKeyboardButton("⟠ Ethereum", callback_data="rate_ETH"),
            InlineKeyboardButton("🅣 Tether", callback_data="rate_USDT")
        ],
        [
            InlineKeyboardButton("🟢 Сбер", callback_data="rate_SBER"),
            InlineKeyboardButton("🔴 Яндекс", callback_data="rate_YDEX"),
            InlineKeyboardButton("🔵 ВК", callback_data="rate_VKCO")
        ],
        [
            InlineKeyboardButton("🟡 Т-Банк", callback_data="rate_T"),
            InlineKeyboardButton("💎 Газпром", callback_data="rate_GAZP")
        ],
        [
            InlineKeyboardButton("🏗️ ПИК", callback_data="rate_PIKK"),
            InlineKeyboardButton("✈️ Самолёт", callback_data="rate_SMLT")
        ],
        [
            InlineKeyboardButton("📊 Все курсы", callback_data="rates_all"),
            InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Функция для получения данных акций с MOEX
async def get_moex_stocks():
    """Получить данные акций с Московской биржи"""
    stocks_data = {}
    
    # Список акций для мониторинга
    stocks = {
        'SBER': {'name': 'Сбер', 'emoji': '🟢'},
        'YDEX': {'name': 'Яндекс', 'emoji': '🔴'},
        'VKCO': {'name': 'ВК', 'emoji': '🔵'},
        'T': {'name': 'Т-Технологии', 'emoji': '🟡'},
        'GAZP': {'name': 'Газпром', 'emoji': '💎'},
        'PIKK': {'name': 'ПИК', 'emoji': '🏗️'},
        'SMLT': {'name': 'Самолёт', 'emoji': '✈️'}
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # Получаем данные торгов
            trading_url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
            params = {
                'securities': ','.join(stocks.keys()),
                'iss.meta': 'off',
                'iss.only': 'securities,marketdata'
            }
            
            async with session.get(trading_url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Парсим данные торгов
                    securities_data = {}
                    marketdata = {}
                    
                    if 'securities' in data and 'data' in data['securities']:
                        securities_cols = data['securities']['columns']
                        for row in data['securities']['data']:
                            row_data = dict(zip(securities_cols, row))
                            secid = row_data.get('SECID')
                            if secid in stocks:
                                securities_data[secid] = {
                                    'shortname': row_data.get('SHORTNAME', stocks[secid]['name']),
                                    'lotsize': row_data.get('LOTSIZE', 1)
                                }
                    
                    if 'marketdata' in data and 'data' in data['marketdata']:
                        marketdata_cols = data['marketdata']['columns']
                        for row in data['marketdata']['data']:
                            row_data = dict(zip(marketdata_cols, row))
                            secid = row_data.get('SECID')
                            if secid in stocks:
                                marketdata[secid] = {
                                    'last': row_data.get('LAST'),
                                    'change': row_data.get('CHANGE'),
                                    'changeprcnt': row_data.get('CHANGEPRCNT'),
                                    'volume': row_data.get('VALTODAY'),
                                    'open': row_data.get('OPEN'),
                                    'high': row_data.get('HIGH'),
                                    'low': row_data.get('LOW')
                                }
                    
                    # Объединяем данные
                    for ticker in stocks:
                        if ticker in securities_data or ticker in marketdata:
                            stocks_data[ticker] = {
                                'name': stocks[ticker]['name'],
                                'emoji': stocks[ticker]['emoji'],
                                'shortname': securities_data.get(ticker, {}).get('shortname', stocks[ticker]['name']),
                                'price': marketdata.get(ticker, {}).get('last'),
                                'change': marketdata.get(ticker, {}).get('change'),
                                'change_pct': marketdata.get(ticker, {}).get('changeprcnt'),
                                'volume': marketdata.get(ticker, {}).get('volume'),
                                'open': marketdata.get(ticker, {}).get('open'),
                                'high': marketdata.get(ticker, {}).get('high'),
                                'low': marketdata.get(ticker, {}).get('low')
                            }
    
    except Exception as e:
        logger.error(f"Ошибка получения данных MOEX: {e}")
    
    return stocks_data

# Время запуска бота
bot_start_time = get_moscow_time()

# Данные пользователей (в памяти)
user_data = {}

def load_user_data():
    """Загрузить данные пользователей из файла"""
    global user_data
    try:
        if os.path.exists('user_data.json'):
            with open('user_data.json', 'r', encoding='utf-8') as f:
                user_data = json.load(f)
            logger.info(f"📊 Загружено пользователей: {len(user_data)}")
        else:
            user_data = {}
            logger.info("📊 Файл пользователей не найден, создаю новый")
    except Exception as e:
        logger.error(f"Ошибка загрузки пользователей: {e}")
        user_data = {}

def save_user_data():
    """Сохранить данные пользователей в файл"""
    try:
        with open('user_data.json', 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователей: {e}")

# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    
    # Регистрируем пользователя
    if user_id not in user_data:
        user_data[user_id] = {
            'name': user.first_name,
            'username': user.username,
            'first_seen': get_moscow_time().isoformat(),
            'last_activity': get_moscow_time().isoformat()
        }
        logger.info(f"👤 Новый пользователь: {user.first_name} (ID: {user_id})")
        save_user_data()
    else:
        # Обновляем время последней активности
        user_data[user_id]['last_activity'] = get_moscow_time().isoformat()
        save_user_data()
    
    welcome_text = (
        f"👋 <b>Привет, {user.first_name}!</b>\n\n"
        f"🤖 Это упрощенный Telegram бот\n\n"
        f"📋 <b>Доступные команды:</b>\n"
        f"/start - Главное меню\n"
        f"/help - Справка\n"
        f"/ping - Проверка работы\n"
        f"/rates - Курсы валют, криптовалют и акций\n\n"
        f"👤 <b>Статус:</b> Пользователь\n"
        f"📊 <b>Пользователей:</b> {len(user_data)}\n\n"
        f"Используйте кнопки ниже для быстрого доступа к функциям:"
    )
    
    await update.message.reply_html(
        welcome_text,
        reply_markup=create_main_menu_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    help_text = (
        "🤖 <b>Справка по боту</b>\n\n"
        "💱 <b>Курсы валют</b> - текущие курсы валют, криптовалют и российских акций\n\n"
        "📋 <b>Доступные команды:</b>\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n"
        "/ping - Проверка работы бота\n"
        "/rates - Показать все курсы\n\n"
        "🔄 <b>Источники данных:</b>\n"
        "• ЦБ РФ - курсы валют\n"
        "• CoinGecko - криптовалюты\n" 
        "• MOEX - российские акции\n\n"
        "Используйте кнопки для быстрого доступа!"
    )
    
    await update.message.reply_html(help_text)

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /ping"""
    current_time = get_moscow_time().strftime("%d.%m.%Y %H:%M:%S")
    await update.message.reply_text(f"🏓 Понг! Время: {current_time}")

async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получить курсы валют и криптовалют"""
    try:
        await update.message.reply_text("📊 Получаю курсы валют, криптовалют и акций...")
        
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
            
            # Сохраняем курс доллара для конвертации криптовалют в рубли
            usd_to_rub_rate = usd_rate if isinstance(usd_rate, (int, float)) else 0
            
            # Форматируем валютные курсы
            usd_str = f"{usd_rate:.2f} ₽" if isinstance(usd_rate, (int, float)) else str(usd_rate)
            eur_str = f"{eur_rate:.2f} ₽" if isinstance(eur_rate, (int, float)) else str(eur_rate)
            cny_str = f"{cny_rate:.2f} ₽" if isinstance(cny_rate, (int, float)) else str(cny_rate)
            gbp_str = f"{gbp_rate:.2f} ₽" if isinstance(gbp_rate, (int, float)) else str(gbp_rate)
            jpy_str = f"{jpy_rate:.4f} ₽" if isinstance(jpy_rate, (int, float)) else str(jpy_rate)
            chf_str = f"{chf_rate:.2f} ₽" if isinstance(chf_rate, (int, float)) else str(chf_rate)
                
        except Exception as e:
            logger.error(f"Ошибка получения курсов ЦБ РФ: {e}")
            usd_str = eur_str = cny_str = gbp_str = jpy_str = chf_str = "❌ Ошибка API"
        
        # 2. Курсы криптовалют CoinGecko
        try:
            crypto_response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,the-open-network&vs_currencies=usd",
                timeout=10
            )
            crypto_response.raise_for_status()
            crypto_data = crypto_response.json()
            
            # Получаем цены криптовалют
            bitcoin_price = crypto_data.get('bitcoin', {}).get('usd', 'Н/Д')
            ethereum_price = crypto_data.get('ethereum', {}).get('usd', 'Н/Д')
            ton_price = crypto_data.get('the-open-network', {}).get('usd', 'Н/Д')
            
            # Форматируем криптовалютные цены (доллары + рубли)
            if isinstance(bitcoin_price, (int, float)) and usd_to_rub_rate > 0:
                btc_rub = bitcoin_price * usd_to_rub_rate
                btc_str = f"${bitcoin_price:,.0f} ({btc_rub:,.0f} ₽)"
            elif isinstance(bitcoin_price, (int, float)):
                btc_str = f"${bitcoin_price:,.0f}"
            else:
                btc_str = str(bitcoin_price)
                
            if isinstance(ethereum_price, (int, float)) and usd_to_rub_rate > 0:
                eth_rub = ethereum_price * usd_to_rub_rate
                eth_str = f"${ethereum_price:,.0f} ({eth_rub:,.0f} ₽)"
            elif isinstance(ethereum_price, (int, float)):
                eth_str = f"${ethereum_price:,.0f}"
            else:
                eth_str = str(ethereum_price)
                
            if isinstance(ton_price, (int, float)) and usd_to_rub_rate > 0:
                ton_rub = ton_price * usd_to_rub_rate
                ton_str = f"${ton_price:.2f} ({ton_rub:.2f} ₽)"
            elif isinstance(ton_price, (int, float)):
                ton_str = f"${ton_price:.2f}"
            else:
                ton_str = str(ton_price)
                
        except Exception as e:
            logger.error(f"Ошибка получения курсов криптовалют: {e}")
            btc_str = eth_str = ton_str = "❌ Ошибка API"
        
        # 3. Получаем данные акций с MOEX
        moex_stocks = await get_moex_stocks()
        
        # Разделяем акции на основные и застройщиков
        main_stocks = {}
        real_estate_stocks = {}
        
        for ticker, data in moex_stocks.items():
            if ticker in ['PIKK', 'SMLT']:
                real_estate_stocks[ticker] = data
            else:
                main_stocks[ticker] = data
        
        # Форматируем строки для основных акций
        main_stock_strings = {}
        for ticker, data in main_stocks.items():
            price = data.get('price')
            change_pct = data.get('change_pct')
            
            if price is not None:
                price_str = f"{price:.2f} ₽"
                
                if change_pct is not None:
                    if change_pct > 0:
                        trend = "📈"
                        change_str = f"+{change_pct:.2f}%"
                    elif change_pct < 0:
                        trend = "📉"
                        change_str = f"{change_pct:.2f}%"
                    else:
                        trend = "➡️"
                        change_str = "0.00%"
                    
                    main_stock_strings[ticker] = f"{price_str} ({trend} {change_str})"
                else:
                    main_stock_strings[ticker] = price_str
            else:
                main_stock_strings[ticker] = "❌ Н/Д"
        
        # Форматируем строки для акций застройщиков
        real_estate_stock_strings = {}
        for ticker, data in real_estate_stocks.items():
            price = data.get('price')
            change_pct = data.get('change_pct')
            
            if price is not None:
                price_str = f"{price:.2f} ₽"
                
                if change_pct is not None:
                    if change_pct > 0:
                        trend = "📈"
                        change_str = f"+{change_pct:.2f}%"
                    elif change_pct < 0:
                        trend = "📉"
                        change_str = f"{change_pct:.2f}%"
                    else:
                        trend = "➡️"
                        change_str = "0.00%"
                    
                    real_estate_stock_strings[ticker] = f"{price_str} ({trend} {change_str})"
                else:
                    real_estate_stock_strings[ticker] = price_str
            else:
                real_estate_stock_strings[ticker] = "❌ Н/Д"
        
        # Формируем строки для основных акций с эмоджи
        main_stocks_info = []
        for ticker, data in main_stocks.items():
            emoji = data.get('emoji', '📊')
            name = data.get('name', ticker)
            price_info = main_stock_strings.get(ticker, '❌ Н/Д')
            main_stocks_info.append(f"{emoji} {name}: {price_info}")
        
        main_stocks_section = "\n".join(main_stocks_info) if main_stocks_info else "❌ Данные недоступны"
        
        # Формируем строки для акций застройщиков с эмоджи
        real_estate_info = []
        for ticker, data in real_estate_stocks.items():
            emoji = data.get('emoji', '🏗️')
            name = data.get('name', ticker)
            price_info = real_estate_stock_strings.get(ticker, '❌ Н/Д')
            real_estate_info.append(f"{emoji} {name}: {price_info}")
        
        real_estate_section = "\n".join(real_estate_info) if real_estate_info else "❌ Данные недоступны"
        
        # Формируем итоговое сообщение
        current_time = get_moscow_time().strftime("%d.%m.%Y %H:%M")

        message = f"""📊 <b>КУРСЫ ВАЛЮТ, КРИПТОВАЛЮТ И АКЦИЙ</b>

🏛️ <b>Ключевая ставка ЦБ РФ:</b> 20,00%

💱 <b>Основные валюты ЦБ РФ:</b>
🇺🇸 USD: {usd_str}
🇪🇺 EUR: {eur_str}
🇨🇳 CNY: {cny_str}
🇬🇧 GBP: {gbp_str}
🇯🇵 JPY: {jpy_str}
🇨🇭 CHF: {chf_str}

₿ <b>Криптовалюты:</b>
🟠 Bitcoin: {btc_str}
🔷 Ethereum: {eth_str}
💎 TON: {ton_str}

📈 <b>Российские акции (MOEX):</b>
{main_stocks_section}

🏠 <b>Недвижимость:</b>
{real_estate_section}

💳 <b>Ипотечные ставки:</b>
📊 Минимальная: от 5,75% (Абсолют Банк)
📊 Максимальная: до 22,10% (Сбербанк)

⏰ <b>Время:</b> {current_time}
📡 <b>Источники:</b> ЦБ РФ, CoinGecko, MOEX, Банки РФ"""

        await update.message.reply_html(message)
        
    except Exception as e:
        logger.error(f"Общая ошибка в rates_command: {e}")
        await update.message.reply_text(
            f"❌ Ошибка получения курсов: {str(e)}\n\n"
            f"🔄 Попробуйте позже или обратитесь к администратору."
        )

async def show_single_rate(query, currency: str):
    """Показать курс одной валюты или акции"""
    try:
        if currency in ['SBER', 'YDEX', 'VKCO', 'T', 'GAZP', 'PIKK', 'SMLT']:
            # Российская акция
            moex_stocks = await get_moex_stocks()
            
            if currency in moex_stocks:
                stock_data = moex_stocks[currency]
                price = stock_data.get('price')
                change = stock_data.get('change')
                change_pct = stock_data.get('change_pct')
                volume = stock_data.get('volume')
                high = stock_data.get('high')
                low = stock_data.get('low')
                open_price = stock_data.get('open')
                
                emoji = stock_data.get('emoji', '📊')
                name = stock_data.get('name', currency)
                
                text = f"{emoji} <b>{name} ({currency})</b>\n\n"
                
                if price is not None:
                    text += f"💰 <b>Цена:</b> {price:.2f} ₽\n"
                    
                    if change is not None and change_pct is not None:
                        if change_pct > 0:
                            trend = "📈"
                            change_str = f"+{change:.2f} ₽ (+{change_pct:.2f}%)"
                        elif change_pct < 0:
                            trend = "📉"
                            change_str = f"{change:.2f} ₽ ({change_pct:.2f}%)"
                        else:
                            trend = "➡️"
                            change_str = f"0.00 ₽ (0.00%)"
                        
                        text += f"{trend} <b>Изменение:</b> {change_str}\n"
                    
                    if high is not None and low is not None:
                        text += f"📊 <b>Диапазон:</b> {low:.2f} - {high:.2f} ₽\n"
                    
                    if open_price is not None:
                        text += f"🌅 <b>Открытие:</b> {open_price:.2f} ₽\n"
                    
                    if volume is not None and volume > 0:
                        volume_m = volume / 1_000_000
                        text += f"📈 <b>Объем:</b> {volume_m:.1f}M ₽\n"
                else:
                    text += "❌ Данные недоступны\n"
                
                text += f"\n🕐 {get_moscow_time().strftime('%H:%M, %d.%m.%Y')} МСК"
            else:
                text = f"❌ Акция {currency} не найдена"
                
        elif currency in ['BTC', 'ETH', 'USDT']:
            # Криптовалюта
            async with aiohttp.ClientSession() as session:
                crypto_map = {'BTC': 'bitcoin', 'ETH': 'ethereum', 'USDT': 'tether'}
                crypto_id = crypto_map.get(currency, currency.lower())
                
                async with session.get(f'https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd,rub') as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        crypto_data = data.get(crypto_id, {})
                        
                        usd_price = crypto_data.get('usd', 0)
                        rub_price = crypto_data.get('rub', 0)
                        
                        icons = {'BTC': '₿', 'ETH': '⟠', 'USDT': '🅣'}
                        icon = icons.get(currency, '💰')
                        
                        text = (
                            f"{icon} <b>{currency}</b>\n\n"
                            f"💵 <b>USD:</b> ${usd_price:,.2f}\n"
                            f"🇷🇺 <b>RUB:</b> ₽{rub_price:,.2f}\n\n"
                            f"🕐 {get_moscow_time().strftime('%H:%M, %d.%m.%Y')} МСК"
                        )
        else:
            # Обычная валюта
            async with aiohttp.ClientSession() as session:
                async with session.get('https://www.cbr-xml-daily.ru/daily_json.js') as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        valute_data = data.get('Valute', {})
                        
                        if currency == 'RUB':
                            text = (
                                f"🇷🇺 <b>Российский рубль</b>\n\n"
                                f"💵 <b>Базовая валюта</b>\n\n"
                                f"🕐 {get_moscow_time().strftime('%H:%M, %d.%m.%Y')} МСК"
                            )
                        elif currency in valute_data:
                            rate_info = valute_data[currency]
                            rate = rate_info['Value']
                            prev_rate = rate_info['Previous']
                            change = rate - prev_rate
                            change_pct = (change / prev_rate) * 100 if prev_rate != 0 else 0
                            
                            trend = "📈" if change > 0 else ("📉" if change < 0 else "➡️")
                            change_text = f"{change:+.4f} ({change_pct:+.2f}%)"
                            
                            icons = {
                                'USD': '💵', 'EUR': '💶', 'GBP': '💷', 
                                'JPY': '💴', 'CHF': '🇨🇭', 'CNY': '🇨🇳'
                            }
                            icon = icons.get(currency, '💰')
                            
                            text = (
                                f"{icon} <b>{rate_info['Name']} ({currency})</b>\n\n"
                                f"💰 <b>Курс:</b> {rate:.4f} ₽\n"
                                f"{trend} <b>Изменение:</b> {change_text}\n\n"
                                f"🕐 {get_moscow_time().strftime('%H:%M, %d.%m.%Y')} МСК"
                            )
                        else:
                            text = f"❌ Валюта {currency} не найдена"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="rates")]]
        await query.edit_message_text(
            text=text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    except Exception as e:
        logger.error(f"Ошибка показа курса {currency}: {e}")
        await query.edit_message_text("❌ Ошибка получения курса")

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик inline кнопок"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Обновляем активность пользователя
    if user_id in user_data:
        user_data[user_id]['last_activity'] = get_moscow_time().isoformat()
        save_user_data()
    
    data = query.data
    
    try:
        if data == "main_menu":
            # Возврат к главному меню
            welcome_text = (
                f"👋 <b>Главное меню</b>\n\n"
                f"Выберите нужную функцию:"
            )
            await query.edit_message_text(
                text=welcome_text,
                parse_mode='HTML',
                reply_markup=create_main_menu_keyboard()
            )
        
        elif data == "help":
            # Показать справку
            help_text = (
                "🤖 <b>Справка по боту</b>\n\n"
                "💱 <b>Курсы валют</b> - текущие курсы валют, криптовалют и российских акций\n\n"
                "📋 <b>Доступные команды:</b>\n"
                "/start - Главное меню\n"
                "/help - Эта справка\n"
                "/ping - Проверка работы бота\n"
                "/rates - Показать все курсы\n\n"
                "Используйте кнопки для быстрого доступа!"
            )
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
            await query.edit_message_text(
                text=help_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif data == "rates":
            # Показать меню курсов валют
            rates_text = (
                "💱 <b>Курсы валют и криптовалют</b>\n\n"
                "Выберите валюту или криптовалюту для просмотра курса:"
            )
            await query.edit_message_text(
                text=rates_text,
                parse_mode='HTML',
                reply_markup=create_rates_keyboard()
            )
        
        elif data == "rates_all":
            # Показать все курсы - используем существующую команду
            await rates_command(update, context)
            return
        
        elif data.startswith("rate_"):
            # Показать курс конкретной валюты
            currency = data.replace("rate_", "")
            await show_single_rate(query, currency)
        
        else:
            await query.edit_message_text("❌ Неизвестная команда")
    
    except Exception as e:
        logger.error(f"Ошибка в обработчике кнопок: {e}")
        await query.edit_message_text("❌ Произошла ошибка при обработке запроса")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка обычных сообщений"""
    message_text = update.message.text
    user_id = update.effective_user.id
    
    # Обновляем активность пользователя
    if user_id in user_data:
        user_data[user_id]['last_activity'] = get_moscow_time().isoformat()
        save_user_data()
    
    # Простой эхо ответ
    await update.message.reply_text(
        f"Получил: {message_text}\n\n"
        f"💡 Используй /help для списка команд"
    )

def main() -> None:
    """Запуск бота - упрощенная версия"""
    logger.info("🚀 Запуск упрощенного бота...")
    
    # Загружаем данные пользователей при старте
    load_user_data()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("rates", rates_command))

    # Обработчик inline кнопок
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Обработчик всех текстовых сообщений (эхо)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Запуск бота
    logger.info("✅ Упрощенный бот запущен и готов к работе")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 