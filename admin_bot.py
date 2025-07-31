#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import asyncio
from datetime import datetime, time
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue
import json
import aiohttp
import requests
import threading

# Безопасный импорт schedule (может отсутствовать)
try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ Модуль 'schedule' не установлен. Альтернативная система задач будет использовать только Timer")
    SCHEDULE_AVAILABLE = False

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', '0'))

# Глобальная переменная для системы задач
GLOBAL_JOB_QUEUE = None

# API ключи для внешних сервисов (для продакшена нужны настоящие ключи)
METALPRICEAPI_KEY = os.getenv('METALPRICEAPI_KEY', 'demo')  # https://metalpriceapi.com/
API_NINJAS_KEY = os.getenv('API_NINJAS_KEY', 'demo')        # https://api.api-ninjas.com/
FMP_API_KEY = os.getenv('FMP_API_KEY', 'demo')              # https://financialmodelingprep.com/
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_KEY', 'demo')  # https://www.alphavantage.co/
EIA_API_KEY = os.getenv('EIA_API_KEY', 'demo')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
    exit(1)

if ADMIN_USER_ID == 0:
    logger.warning("⚠️ ADMIN_USER_ID не установлен!")

# Функция для получения московского времени
def get_moscow_time():
    """Возвращает текущее время в московском часовом поясе"""
    moscow_tz = pytz.timezone('Europe/Moscow')
    return datetime.now(moscow_tz)

# Функция для форматирования чисел с разделителями тысяч
def format_price(price, decimal_places=2):
    """Форматирует цену с разделителями тысяч и нужным количеством знаков после запятой"""
    if isinstance(price, (int, float)):
        return f"{price:,.{decimal_places}f}".replace(',', ' ')
    return str(price)

# Создание inline клавиатур
# УДАЛЕНО: inline клавиатуры больше не используются

# Функция для получения данных акций с MOEX
async def get_moex_stocks():
    """Получить данные акций с Московской биржи"""
    stocks_data = {}
    
    # Список акций для мониторинга
    stocks = {
        # Основные российские акции
        'SBER': {'name': 'Сбер', 'emoji': '🟢'},
        'YDEX': {'name': 'Яндекс', 'emoji': '🔴'},
        'VKCO': {'name': 'ВК', 'emoji': '🔵'},
        'T': {'name': 'Т-Технологии', 'emoji': '🟡'},
        'GAZP': {'name': 'Газпром', 'emoji': '💎'},
        'GMKN': {'name': 'Норникель', 'emoji': '⚡'},
        'ROSN': {'name': 'Роснефть', 'emoji': '🛢️'},
        'LKOH': {'name': 'ЛУКОЙЛ', 'emoji': '⛽'},
        'MTSS': {'name': 'МТС', 'emoji': '📱'},
        'MFON': {'name': 'Мегафон', 'emoji': '📶'},
        # Акции застройщиков
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

# Функция для получения ключевой ставки ЦБ РФ убрана - API не работает стабильно

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
        f"🤖 Это продвинутый финансовый Telegram бот\n\n"
        f"📋 <b>Основные команды:</b>\n"
        f"/start - Главное меню\n"
        f"/help - Справка\n"
        f"/ping - Проверка работы\n"
        f"/rates - Курсы валют, криптовалют и акций\n\n"
        f"🔔 <b>Уведомления:</b>\n"
        f"/subscribe - Подписаться на уведомления о резких изменениях\n"
        f"/unsubscribe - Отписаться от уведомлений\n"
        f"/set_alert - Установить пороговые алерты\n"
        f"/view_alerts - Посмотреть активные алерты\n\n"
        f"👤 <b>Статус:</b> Пользователь\n"
        f"📊 <b>Пользователей:</b> {len(user_data)}"
    )
    
    await update.message.reply_html(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    help_text = (
        "🤖 <b>Справка по продвинутому финансовому боту</b>\n\n"
        "💱 <b>Основные функции:</b>\n"
        "• Курсы валют, криптовалют и акций\n"
        "• Товары (нефть Brent/Urals, золото, серебро)\n"
        "• Фондовые индексы\n"
        "• Уведомления о резких изменениях\n"
        "• Пороговые алерты\n"
        "• Ежедневная сводка в 9:00 МСК\n\n"
        "📋 <b>Команды:</b>\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n"
        "/ping - Проверка работы\n"
        "/rates - Показать все курсы\n\n"
        "🔔 <b>Уведомления:</b>\n"
        "/subscribe - Подписаться на уведомления\n"
        "/unsubscribe - Отписаться\n"
        "/set_alert - Пороговые алерты\n"
        "/view_alerts - Посмотреть настройки\n\n"
    )
    
    # Добавляем админские команды только для администратора
    if update.effective_user.id == ADMIN_USER_ID:
        help_text += (
            "🔧 <b>Админские команды:</b>\n"
            "/test_daily - Тестовая ежедневная сводка\n"
            "/check_subscribers - Статус подписчиков\n"
            "/set_daily_time HH:MM - Настроить время сводки\n"
            "/get_daily_settings - Посмотреть настройки\n"
            "/restart_daily_job - Перезапустить задачу сводки\n\n"
        )
    
    help_text += (
        "🔄 <b>Источники данных:</b>\n"
        "• ЦБ РФ - курсы валют\n"
        "• CoinGecko - криптовалюты\n" 
        "• MOEX - российские акции и индексы\n"
        "• Gold-API.com - драгоценные металлы\n"
        "• EIA API - точные цены нефти\n"
        "• Alpha Vantage - фондовые индексы\n\n"
        "💡 <b>Совет:</b> Выполните /subscribe чтобы получать ежедневную сводку в 9:00 МСК!"
    )
    
    await update.message.reply_html(help_text)

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /ping"""
    current_time = get_moscow_time().strftime("%d.%m.%Y %H:%M:%S")
    await update.message.reply_text(f"🏓 Понг! Время: {current_time}")

async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получить полные курсы валют, криптовалют, акций, товаров и индексов"""
    try:
        await update.message.reply_text("📊 Получаю информацию")
        
        # 1. Курсы валют ЦБ РФ
        try:
            cbr_response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
            cbr_response.raise_for_status()
            cbr_data = cbr_response.json()
            
            # Получаем курсы валют (только 4 основные)
            usd_rate = cbr_data.get('Valute', {}).get('USD', {}).get('Value', 'Н/Д')
            eur_rate = cbr_data.get('Valute', {}).get('EUR', {}).get('Value', 'Н/Д')
            cny_rate = cbr_data.get('Valute', {}).get('CNY', {}).get('Value', 'Н/Д')
            gbp_rate = cbr_data.get('Valute', {}).get('GBP', {}).get('Value', 'Н/Д')
            
            # Сохраняем курс доллара для конвертации в рубли
            usd_to_rub_rate = usd_rate if isinstance(usd_rate, (int, float)) else 0
            
            # Форматируем валютные курсы
            usd_str = f"{format_price(usd_rate)} ₽" if isinstance(usd_rate, (int, float)) else str(usd_rate)
            eur_str = f"{format_price(eur_rate)} ₽" if isinstance(eur_rate, (int, float)) else str(eur_rate)
            cny_str = f"{format_price(cny_rate)} ₽" if isinstance(cny_rate, (int, float)) else str(cny_rate)
            gbp_str = f"{format_price(gbp_rate)} ₽" if isinstance(gbp_rate, (int, float)) else str(gbp_rate)
                
        except Exception as e:
            logger.error(f"Ошибка получения курсов ЦБ РФ: {e}")
            usd_str = eur_str = cny_str = gbp_str = "❌ Ошибка API"
            usd_to_rub_rate = 80  # Fallback значение для конвертации
        
        # 2. Расширенные курсы криптовалют CoinGecko
        try:
            crypto_response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,the-open-network,ripple,cardano,solana,dogecoin&vs_currencies=usd",
                timeout=10
            )
            crypto_response.raise_for_status()
            crypto_data = crypto_response.json()
            
            # Получаем цены криптовалют
            bitcoin_price = crypto_data.get('bitcoin', {}).get('usd', 'Н/Д')
            ethereum_price = crypto_data.get('ethereum', {}).get('usd', 'Н/Д')
            ton_price = crypto_data.get('the-open-network', {}).get('usd', 'Н/Д')
            ripple_price = crypto_data.get('ripple', {}).get('usd', 'Н/Д')
            cardano_price = crypto_data.get('cardano', {}).get('usd', 'Н/Д')
            solana_price = crypto_data.get('solana', {}).get('usd', 'Н/Д')
            dogecoin_price = crypto_data.get('dogecoin', {}).get('usd', 'Н/Д')
            
            # Форматируем криптовалютные цены (доллары + рубли)
            crypto_strings = {}
            
            # Bitcoin
            if isinstance(bitcoin_price, (int, float)) and usd_to_rub_rate > 0:
                btc_rub = bitcoin_price * usd_to_rub_rate
                crypto_strings['bitcoin'] = f"Bitcoin: ${format_price(bitcoin_price, 0)} ({format_price(btc_rub, 0)} ₽)"
            elif isinstance(bitcoin_price, (int, float)):
                crypto_strings['bitcoin'] = f"Bitcoin: ${format_price(bitcoin_price, 0)}"
            else:
                crypto_strings['bitcoin'] = "Bitcoin: ❌ Н/Д"
                
            # Ethereum
            if isinstance(ethereum_price, (int, float)) and usd_to_rub_rate > 0:
                eth_rub = ethereum_price * usd_to_rub_rate
                crypto_strings['ethereum'] = f"Ethereum: ${format_price(ethereum_price, 0)} ({format_price(eth_rub, 0)} ₽)"
            elif isinstance(ethereum_price, (int, float)):
                crypto_strings['ethereum'] = f"Ethereum: ${format_price(ethereum_price, 0)}"
            else:
                crypto_strings['ethereum'] = "Ethereum: ❌ Н/Д"
                
            # TON
            if isinstance(ton_price, (int, float)) and usd_to_rub_rate > 0:
                ton_rub = ton_price * usd_to_rub_rate
                crypto_strings['ton'] = f"TON: ${format_price(ton_price)} ({format_price(ton_rub)} ₽)"
            elif isinstance(ton_price, (int, float)):
                crypto_strings['ton'] = f"TON: ${format_price(ton_price)}"
            else:
                crypto_strings['ton'] = "TON: ❌ Н/Д"
                
            # XRP
            if isinstance(ripple_price, (int, float)) and usd_to_rub_rate > 0:
                xrp_rub = ripple_price * usd_to_rub_rate
                crypto_strings['ripple'] = f"XRP: ${format_price(ripple_price, 3)} ({format_price(xrp_rub)} ₽)"
            elif isinstance(ripple_price, (int, float)):
                crypto_strings['ripple'] = f"XRP: ${format_price(ripple_price, 3)}"
            else:
                crypto_strings['ripple'] = "XRP: ❌ Н/Д"
                
            # Cardano
            if isinstance(cardano_price, (int, float)) and usd_to_rub_rate > 0:
                ada_rub = cardano_price * usd_to_rub_rate
                crypto_strings['cardano'] = f"Cardano: ${format_price(cardano_price, 3)} ({format_price(ada_rub)} ₽)"
            elif isinstance(cardano_price, (int, float)):
                crypto_strings['cardano'] = f"Cardano: ${format_price(cardano_price, 3)}"
            else:
                crypto_strings['cardano'] = "Cardano: ❌ Н/Д"
                
            # Solana
            if isinstance(solana_price, (int, float)) and usd_to_rub_rate > 0:
                sol_rub = solana_price * usd_to_rub_rate
                crypto_strings['solana'] = f"Solana: ${format_price(solana_price)} ({format_price(sol_rub)} ₽)"
            elif isinstance(solana_price, (int, float)):
                crypto_strings['solana'] = f"Solana: ${format_price(solana_price)}"
            else:
                crypto_strings['solana'] = "Solana: ❌ Н/Д"
                
            # Dogecoin
            if isinstance(dogecoin_price, (int, float)) and usd_to_rub_rate > 0:
                doge_rub = dogecoin_price * usd_to_rub_rate
                crypto_strings['dogecoin'] = f"Dogecoin: ${format_price(dogecoin_price, 3)} ({format_price(doge_rub)} ₽)"
            elif isinstance(dogecoin_price, (int, float)):
                crypto_strings['dogecoin'] = f"Dogecoin: ${format_price(dogecoin_price, 3)}"
            else:
                crypto_strings['dogecoin'] = "Dogecoin: ❌ Н/Д"
                
        except Exception as e:
            logger.error(f"Ошибка получения курсов криптовалют: {e}")
            crypto_strings = {
                'bitcoin': 'Bitcoin: ❌ Ошибка API',
                'ethereum': 'Ethereum: ❌ Ошибка API',
                'ton': 'TON: ❌ Ошибка API',
                'ripple': 'XRP: ❌ Ошибка API',
                'cardano': 'Cardano: ❌ Ошибка API',
                'solana': 'Solana: ❌ Ошибка API',
                'dogecoin': 'Dogecoin: ❌ Ошибка API'
            }
        
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
        
        # Форматируем акции
        def format_stock_data(stocks_dict):
            result = {}
            for ticker, data in stocks_dict.items():
                price = data.get('price')
                change_pct = data.get('change_pct')
                name = data.get('name', ticker)
                
                if price is not None:
                    price_str = f"{price:.2f} ₽"
                    
                    if change_pct is not None:
                        if change_pct > 0:
                            change_str = f"(+{change_pct:.2f}%)"
                        elif change_pct < 0:
                            change_str = f"({change_pct:.2f}%)"
                        else:
                            change_str = "(0.00%)"
                        
                        result[ticker] = f"{name}: {price_str} {change_str}"
                    else:
                        result[ticker] = f"{name}: {price_str}"
                else:
                    result[ticker] = f"{name}: ❌ Н/Д"
            return result
        

        
        # Формируем итоговое сообщение с улучшенным форматированием
        message = "📊 **На сегодня курсы такие:**\n\n"
        
        # Валюты ЦБ РФ
        message += "🏛️ **ВАЛЮТЫ (по курсу ЦБ РФ):**\n"
        message += f"├ USD: **{usd_str}**\n"
        message += f"├ EUR: **{eur_str}**\n"
        message += f"├ CNY: **{cny_str}**\n"
        message += f"└ GBP: **{gbp_str}**\n\n"
        
        # Криптовалюты
        message += "💎 **КРИПТА:**\n"
        crypto_items = ['bitcoin', 'ethereum', 'ton', 'ripple', 'cardano', 'solana', 'dogecoin']
        for i, crypto in enumerate(crypto_items):
            if crypto in crypto_strings:
                prefix = "├" if i < len(crypto_items) - 1 else "└"
                message += f"{prefix} {crypto_strings[crypto]}\n"
        message += "\n"
        
        # Российские акции
        message += "📈 **РОССИЙСКИЕ АКЦИИ (MOEX):**\n"
        stocks_data = await get_moex_stocks()
        stock_names = {
            'SBER': 'Сбер', 'YDEX': 'Яндекс', 'VKCO': 'ВК', 
            'T': 'T-Технологии', 'GAZP': 'Газпром', 'GMKN': 'Норникель',
            'ROSN': 'Роснефть', 'LKOH': 'ЛУКОЙЛ', 'MTSS': 'МТС', 'MFON': 'Мегафон'
        }
        stock_items = list(stock_names.keys())
        for i, ticker in enumerate(stock_items):
            if ticker in stocks_data and stocks_data[ticker].get('price'):
                name = stock_names[ticker]
                price = stocks_data[ticker]['price']
                prefix = "├" if i < len(stock_items) - 1 else "└"
                message += f"{prefix} {name}: **{format_price(price)} ₽**\n"
        message += "\n"
        
        # Недвижимость
        message += "🏠 **НЕДВИЖИМОСТЬ:**\n"
        real_estate_tickers = ['PIKK', 'SMLT']
        real_estate_names = {'PIKK': 'ПИК', 'SMLT': 'Самолёт'}
        for i, ticker in enumerate(real_estate_tickers):
            if ticker in stocks_data and stocks_data[ticker].get('price'):
                name = real_estate_names[ticker]
                price = stocks_data[ticker]['price']
                prefix = "├" if i < len(real_estate_tickers) - 1 else "└"
                message += f"{prefix} {name}: **{format_price(price)} ₽**\n"
        message += "\n"
        
        # Товары 
        message += "🛠️ **ЗОЛОТО, НЕФТЬ:**\n"
        commodities_data = await get_commodities_data()
        commodity_items = ['gold', 'silver', 'brent', 'urals']  # Добавляем urals
        commodity_names = {
            'gold': 'Золото', 
            'silver': 'Серебро', 
            'brent': 'Нефть Brent',
            'urals': 'Нефть Urals'
        }
        
        for i, commodity in enumerate(commodity_items):
            if commodity in commodities_data:
                name = commodity_names[commodity]
                price = commodities_data[commodity]['price']
                rub_price = price * usd_to_rub_rate if usd_to_rub_rate > 0 else 0
                prefix = "├" if i < len(commodity_items) - 1 else "└"
                if rub_price > 0:
                    message += f"{prefix} {name}: **${format_price(price)}** ({format_price(rub_price)} ₽)\n"
                else:
                    message += f"{prefix} {name}: **${format_price(price)}**\n"
        message += "\n"
        
        # Фондовые индексы
        message += "📊 **ФОНДОВЫЕ ИНДЕКСЫ:**\n"
        indices_data = await get_indices_data()
        index_items = ['imoex', 'rts', 'sp500']
        
        for i, index in enumerate(index_items):
            if index in indices_data:
                name = indices_data[index]['name']
                price = indices_data[index]['price']
                change = indices_data[index].get('change_pct', 0)
                prefix = "├" if i < len(index_items) - 1 else "└"
                change_str = f"({change:+.2f}%)" if change != 0 else ""
                message += f"{prefix} {name}: **{format_price(price)}** {change_str}\n"
        message += "\n"
        
        # Время и источники
        current_time = get_moscow_time().strftime("%d.%m.%Y %H:%M")
        message += f"🕐 **Время:** {current_time}\n"
        message += f"📡 **Источники:** ЦБ РФ, CoinGecko, MOEX, Gold-API, Alpha Vantage"

        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Общая ошибка в rates_command: {e}")
        await update.message.reply_text(
            f"❌ Ошибка получения курсов: {str(e)}\n\n"
            f"🔄 Попробуйте позже или обратитесь к администратору."
        )

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

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подписаться на уведомления о резких изменениях курсов"""
    user_id = update.effective_user.id
    notifications = load_notification_data()
    
    if str(user_id) not in notifications:
        notifications[str(user_id)] = {
            'subscribed': True,
            'threshold': 2.0,  # 2% по умолчанию
            'alerts': {},
            'daily_summary': True
        }
        save_notification_data(notifications)
        
        await update.message.reply_html(
            "✅ <b>Подписка активирована!</b>\n\n"
            "📈 Вы будете получать уведомления о:\n"
            "• Резких изменениях курсов >2%\n"
            "• Ежедневной сводке в 9:00 МСК\n\n"
            "⚙️ Используйте /set_alert для пороговых алертов\n"
            "🔕 /unsubscribe для отписки"
        )
    else:
        notifications[str(user_id)]['subscribed'] = True
        save_notification_data(notifications)
        
        await update.message.reply_html(
            "🔔 <b>Подписка уже активна!</b>\n\n"
            "Используйте /view_alerts для просмотра настроек"
        )

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отписаться от уведомлений"""
    user_id = update.effective_user.id
    notifications = load_notification_data()
    
    if str(user_id) in notifications:
        notifications[str(user_id)]['subscribed'] = False
        save_notification_data(notifications)
        
        await update.message.reply_html(
            "🔕 <b>Подписка отключена</b>\n\n"
            "Вы больше не будете получать уведомления.\n"
            "Используйте /subscribe для повторной активации."
        )
    else:
        await update.message.reply_html(
            "❌ Вы не подписаны на уведомления.\n"
            "Используйте /subscribe для подписки."
        )

async def set_alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Установить пороговые алерты"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_html(
            "⚙️ <b>Установка пороговых алертов</b>\n\n"
            "📝 Примеры использования:\n"
            "• <code>/set_alert USD 85</code> - доллар выше 85₽\n"
            "• <code>/set_alert BTC 115000</code> - биткоин ниже 115K$\n"
            "• <code>/set_alert SBER 200</code> - Сбер выше 200₽\n\n"
            "💡 Поддерживаемые активы:\n"
            "• Валюты: USD, EUR, CNY, GBP\n"
            "• Криптовалюты: BTC, ETH, TON, XRP, ADA, SOL, DOGE\n"
            "• Акции: SBER, YDEX, VKCO, T, GAZP, GMKN, ROSN, LKOH, MTSS, MFON, PIKK, SMLT"
        )
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажите актив и пороговое значение")
        return
    
    asset = context.args[0].upper()
    try:
        threshold = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Пороговое значение должно быть числом")
        return
    
    notifications = load_notification_data()
    if str(user_id) not in notifications:
        notifications[str(user_id)] = {
            'subscribed': True,
            'threshold': 2.0,
            'alerts': {},
            'daily_summary': True
        }
    
    notifications[str(user_id)]['alerts'][asset] = threshold
    save_notification_data(notifications)
    
    await update.message.reply_html(
        f"✅ <b>Алерт установлен!</b>\n\n"
        f"🎯 <b>Актив:</b> {asset}\n"
        f"📊 <b>Порог:</b> {threshold}\n\n"
        f"🔔 Вы получите уведомление при достижении этого значения"
    )

async def view_alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Посмотреть активные алерты"""
    user_id = update.effective_user.id
    notifications = load_notification_data()
    
    if str(user_id) not in notifications:
        await update.message.reply_html(
            "❌ У вас нет настроенных уведомлений.\n"
            "Используйте /subscribe для подписки."
        )
        return
    
    user_notifications = notifications[str(user_id)]
    
    status = "🔔 Включены" if user_notifications.get('subscribed', False) else "🔕 Отключены"
    threshold = user_notifications.get('threshold', 2.0)
    daily = "✅ Да" if user_notifications.get('daily_summary', False) else "❌ Нет"
    
    alerts_text = ""
    alerts = user_notifications.get('alerts', {})
    if alerts:
        alerts_text = "\n\n📊 <b>Пороговые алерты:</b>\n"
        for asset, value in alerts.items():
            alerts_text += f"• {asset}: {value}\n"
    else:
        alerts_text = "\n\n📊 <b>Пороговые алерты:</b> не установлены"
    
    message = (
        f"⚙️ <b>Ваши настройки уведомлений</b>\n\n"
        f"🔔 <b>Статус:</b> {status}\n"
        f"📈 <b>Порог изменений:</b> {threshold}%\n"
        f"🌅 <b>Ежедневная сводка:</b> {daily}"
        f"{alerts_text}"
    )
    
    await update.message.reply_html(message)

async def test_daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Тестовая команда для проверки ежедневной сводки (только для админа)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return
    
    await update.message.reply_text("🧪 Запускаю тестовую ежедневную сводку...")
    
    try:
        # Вызываем функцию ежедневной сводки вручную
        await daily_summary_job(context)
        await update.message.reply_text("✅ Тестовая ежедневная сводка завершена! Проверьте логи.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при выполнении тестовой сводки: {e}")
        logger.error(f"Ошибка тестовой ежедневной сводки: {e}")

async def check_subscribers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверить статус подписчиков (только для админа)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return
    
    try:
        notifications = load_notification_data()
        
        if not notifications:
            await update.message.reply_html(
                "📋 **СТАТУС ПОДПИСОК**\n\n"
                "❌ Нет подписчиков\n\n"
                "💡 Чтобы подписаться на ежедневную сводку, используйте /subscribe"
            )
            return
        
        message = "📋 **СТАТУС ПОДПИСОК**\n\n"
        
        total_users = len(notifications)
        active_subscribers = 0
        daily_summary_subscribers = 0
        
        for uid, data in notifications.items():
            if data.get('subscribed', False):
                active_subscribers += 1
            if data.get('daily_summary', True) and data.get('subscribed', False):
                daily_summary_subscribers += 1
        
        message += f"👥 **Всего пользователей:** {total_users}\n"
        message += f"🔔 **Активных подписчиков:** {active_subscribers}\n"
        message += f"🌅 **Подписано на ежедневную сводку:** {daily_summary_subscribers}\n\n"
        
        if daily_summary_subscribers > 0:
            message += "👤 **Детали подписчиков:**\n"
            for uid, data in notifications.items():
                if data.get('subscribed', False) and data.get('daily_summary', True):
                    alerts_count = len(data.get('alerts', {}))
                    threshold = data.get('threshold', 2.0)
                    message += f"├ ID: {uid}\n"
                    message += f"├ Порог: {threshold}%\n"
                    message += f"└ Алертов: {alerts_count}\n\n"
        
        # Проверяем наличие файла
        import os
        file_exists = os.path.exists(NOTIFICATION_DATA_FILE)
        message += f"💾 **Файл данных:** {'✅ Существует' if file_exists else '❌ Отсутствует'}\n"
        
        if file_exists:
            file_size = os.path.getsize(NOTIFICATION_DATA_FILE)
            message += f"📏 **Размер файла:** {file_size} байт"
        
        await update.message.reply_html(message)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка проверки подписчиков: {e}")
        logger.error(f"Ошибка check_subscribers: {e}")

# Функции для получения дополнительных данных
async def get_commodities_data():
    """Получить данные по товарам из ПОЛНОСТЬЮ БЕСПЛАТНЫХ источников"""
    commodities_data = {}
    
    try:
        # 🥇 Gold-API.com - полностью бесплатный для золота и серебра, без ключей!
        logger.info("🥇 Запрашиваю металлы с Gold-API.com (100% бесплатно)...")
        
        # Золото
        try:
            gold_response = requests.get("https://api.gold-api.com/price/XAU", timeout=10)
            logger.info(f"📊 Gold-API золото статус: {gold_response.status_code}")
            
            if gold_response.status_code == 200:
                gold_data = gold_response.json()
                logger.info(f"📊 Gold-API золото ответ: {gold_data}")
                
                if 'price' in gold_data:
                    commodities_data['gold'] = {
                        'name': 'Золото',
                        'price': gold_data['price'],
                        'currency': 'USD'
                    }
                    logger.info(f"✅ Золото получено: ${gold_data['price']:.2f}")
                else:
                    logger.warning("❌ Gold-API: нет 'price' в ответе золота")
            else:
                logger.error(f"❌ Gold-API золото ошибка {gold_response.status_code}: {gold_response.text}")
        except Exception as e:
            logger.error(f"❌ Ошибка запроса золота: {e}")
        
        # Серебро
        try:
            silver_response = requests.get("https://api.gold-api.com/price/XAG", timeout=10)
            logger.info(f"📊 Gold-API серебро статус: {silver_response.status_code}")
            
            if silver_response.status_code == 200:
                silver_data = silver_response.json()
                logger.info(f"📊 Gold-API серебро ответ: {silver_data}")
                
                if 'price' in silver_data:
                    commodities_data['silver'] = {
                        'name': 'Серебро',
                        'price': silver_data['price'],
                        'currency': 'USD'
                    }
                    logger.info(f"✅ Серебро получено: ${silver_data['price']:.2f}")
                else:
                    logger.warning("❌ Gold-API: нет 'price' в ответе серебра")
            else:
                logger.error(f"❌ Gold-API серебро ошибка {silver_response.status_code}: {silver_response.text}")
        except Exception as e:
            logger.error(f"❌ Ошибка запроса серебра: {e}")
        
        # 🛢️ EIA API для точной нефти Brent (официальный API правительства США, бесплатно!)
        logger.info(f"🛢️ Запрашиваю нефть Brent из EIA API, ключ: {EIA_API_KEY[:10]}...")
        try:
            # Получаем последнюю цену Brent Europe из EIA
            brent_response = requests.get(
                f"https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key={EIA_API_KEY}&facets[product][]=EPCBRENT&data[0]=value&sort[0][column]=period&sort[0][direction]=desc&length=1",
                timeout=10
            )
            logger.info(f"📊 EIA Brent статус: {brent_response.status_code}")
            
            if brent_response.status_code == 200:
                brent_data = brent_response.json()
                logger.info(f"📊 EIA Brent ответ: {brent_data}")
                
                # EIA возвращает данные в "response.data"
                if 'response' in brent_data and 'data' in brent_data['response'] and len(brent_data['response']['data']) > 0:
                    brent_price = float(brent_data['response']['data'][0]['value'])
                    commodities_data['brent'] = {
                        'name': 'Нефть Brent',
                        'price': brent_price,
                        'currency': 'USD'
                    }
                    logger.info(f"✅ Нефть Brent получена: ${brent_price:.2f}")
                else:
                    logger.warning(f"❌ EIA: нет данных в ответе: {brent_data}")
            else:
                logger.error(f"❌ EIA Brent ошибка {brent_response.status_code}: {brent_response.text}")
        except Exception as e:
            logger.error(f"❌ Ошибка запроса Brent из EIA: {e}")
        
        # Fallback: Alpha Vantage для нефти WTI через USO ETF (если EIA не сработал)
        if 'brent' not in commodities_data:
            logger.info("🔄 EIA не сработал, пробуем Alpha Vantage USO ETF...")
            try:
                oil_response = requests.get(
                    f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=USO&apikey={ALPHA_VANTAGE_KEY}",
                    timeout=10
                )
                logger.info(f"📊 Alpha Vantage USO статус: {oil_response.status_code}")
                
                if oil_response.status_code == 200:
                    oil_data = oil_response.json()
                    logger.info(f"📊 Alpha Vantage USO ответ: {oil_data}")
                    
                    if 'Global Quote' in oil_data and '05. price' in oil_data['Global Quote']:
                        oil_price = float(oil_data['Global Quote']['05. price'])
                        estimated_oil_price = oil_price * 12  # Приблизительная конвертация USO ETF
                        commodities_data['brent'] = {
                            'name': 'Нефть Brent (приблиз.)',
                            'price': estimated_oil_price,
                            'currency': 'USD'
                        }
                        logger.info(f"✅ Нефть Brent (USO fallback): ${estimated_oil_price:.2f}")
                    else:
                        logger.warning(f"❌ Alpha Vantage USO: неожиданная структура: {oil_data}")
                else:
                    logger.error(f"❌ Alpha Vantage USO ошибка {oil_response.status_code}: {oil_response.text}")
            except Exception as e:
                logger.error(f"❌ Ошибка Alpha Vantage USO: {e}")
        
        # Fallback только для расчетных значений (не статичных!)
        if 'silver' not in commodities_data and 'gold' in commodities_data:
            logger.info("🔄 Серебро недоступно, рассчитываем от золота...")
            gold_price = commodities_data['gold']['price']
            silver_fallback = gold_price / 80  # Историческое соотношение
            commodities_data['silver'] = {
                'name': 'Серебро (расчетное)',
                'price': silver_fallback,
                'currency': 'USD'
            }
            logger.info(f"✅ Серебро рассчитано: ${silver_fallback:.2f}")
        
        # Рассчитываем Urals от Brent (российская нефть торгуется с дисконтом)
        if 'brent' in commodities_data:
            logger.info("🔄 Рассчитываем Urals от Brent...")
            brent_price = commodities_data['brent']['price']
            # Urals обычно торгуется с дисконтом $2-5 к Brent
            urals_discount = 3.5  # Средний дисконт
            urals_price = brent_price - urals_discount
            commodities_data['urals'] = {
                'name': 'Нефть Urals (расчетная)',
                'price': urals_price,
                'currency': 'USD'
            }
            logger.info(f"✅ Urals рассчитана: ${urals_price:.2f} (Brent ${brent_price:.2f} - ${urals_discount})")
        
        if 'brent' not in commodities_data:
            logger.warning("⚠️ Нефть недоступна из всех бесплатных источников")
    
    except Exception as e:
        logger.error(f"❌ Общая ошибка получения данных товаров: {e}")
    
    logger.info(f"📊 Итого товаров получено: {len(commodities_data)} - {list(commodities_data.keys())}")
    return commodities_data

async def get_indices_data():
    """Получить данные по индексам: IMOEX, RTS, S&P 500"""
    indices_data = {}
    
    try:
        # 1. Российские индексы через MOEX (работает стабильно)
        logger.info("📊 Запрашиваю российские индексы с MOEX...")
        async with aiohttp.ClientSession() as session:
            # IMOEX
            imoex_url = "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json"
            logger.info(f"📈 Запрашиваю IMOEX: {imoex_url}")
            async with session.get(imoex_url) as resp:
                logger.info(f"📊 IMOEX статус: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"📊 IMOEX структура данных: {list(data.keys()) if isinstance(data, dict) else 'не dict'}")
                    
                    if 'marketdata' in data and 'data' in data['marketdata'] and len(data['marketdata']['data']) > 0:
                        logger.info(f"📊 IMOEX marketdata найден, строк: {len(data['marketdata']['data'])}")
                        logger.info(f"📊 IMOEX колонки: {data['marketdata']['columns']}")
                        logger.info(f"📊 IMOEX первая строка: {data['marketdata']['data'][0]}")
                        
                        row_data = dict(zip(data['marketdata']['columns'], data['marketdata']['data'][0]))
                        logger.info(f"📊 IMOEX распарсенные данные: {row_data}")
                        
                        if 'LASTVALUE' in row_data and row_data['LASTVALUE']:
                            indices_data['imoex'] = {
                                'name': 'IMOEX',
                                'price': row_data['LASTVALUE'],
                                'change_pct': row_data.get('LASTCHANGEPRC', 0)
                            }
                            logger.info(f"✅ IMOEX получен: {row_data['LASTVALUE']}")
                        else:
                            logger.warning(f"❌ IMOEX: нет LASTVALUE или LASTVALUE пустой: {row_data.get('LASTVALUE')}")
                    else:
                        logger.warning("❌ IMOEX: нет marketdata или данных")
                else:
                    response_text = await resp.text()
                    logger.error(f"❌ IMOEX ошибка {resp.status}: {response_text[:200]}...")
            
            # RTS
            rts_url = "https://iss.moex.com/iss/engines/stock/markets/index/securities/RTSI.json"
            logger.info(f"📈 Запрашиваю RTS: {rts_url}")
            async with session.get(rts_url) as resp:
                logger.info(f"📊 RTS статус: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"📊 RTS структура данных: {list(data.keys()) if isinstance(data, dict) else 'не dict'}")
                    
                    if 'marketdata' in data and 'data' in data['marketdata'] and len(data['marketdata']['data']) > 0:
                        logger.info(f"📊 RTS marketdata найден, строк: {len(data['marketdata']['data'])}")
                        logger.info(f"📊 RTS колонки: {data['marketdata']['columns']}")
                        logger.info(f"📊 RTS первая строка: {data['marketdata']['data'][0]}")
                        
                        row_data = dict(zip(data['marketdata']['columns'], data['marketdata']['data'][0]))
                        logger.info(f"📊 RTS распарсенные данные: {row_data}")
                        
                        if 'LASTVALUE' in row_data and row_data['LASTVALUE']:
                            indices_data['rts'] = {
                                'name': 'RTS',
                                'price': row_data['LASTVALUE'],
                                'change_pct': row_data.get('LASTCHANGEPRC', 0)
                            }
                            logger.info(f"✅ RTS получен: {row_data['LASTVALUE']}")
                        else:
                            logger.warning(f"❌ RTS: нет LASTVALUE или LASTVALUE пустой: {row_data.get('LASTVALUE')}")
                    else:
                        logger.warning("❌ RTS: нет marketdata или данных")
                else:
                    response_text = await resp.text() 
                    logger.error(f"❌ RTS ошибка {resp.status}: {response_text[:200]}...")
        
        # 2. S&P 500 через Financial Modeling Prep (бесплатно)
        logger.info(f"📈 Запрашиваю S&P 500 с FMP, ключ: {FMP_API_KEY[:10]}...")
        sp500_response = requests.get(
            f"https://financialmodelingprep.com/api/v3/quote/%5EGSPC?apikey={FMP_API_KEY}",
            timeout=10
        )
        logger.info(f"📊 FMP статус: {sp500_response.status_code}")
        
        if sp500_response.status_code == 200:
            sp500_data = sp500_response.json()
            logger.info(f"📊 FMP ответ: {sp500_data}")
            
            if isinstance(sp500_data, list) and len(sp500_data) > 0:
                sp500_info = sp500_data[0]
                if 'price' in sp500_info:
                    indices_data['sp500'] = {
                        'name': 'S&P 500',
                        'price': sp500_info['price'],
                        'change_pct': sp500_info.get('changesPercentage', 0)
                    }
                    logger.info(f"✅ S&P 500 получен: {sp500_info['price']}")
                else:
                    logger.warning("❌ S&P 500: нет 'price' в ответе FMP")
            else:
                logger.warning("❌ S&P 500: ответ FMP не список или пустой")
        else:
            logger.error(f"❌ FMP ошибка {sp500_response.status_code}: {sp500_response.text}")
        
        # Fallback: попробуем Alpha Vantage для S&P 500 если FMP не работает
        if 'sp500' not in indices_data:
            logger.info(f"🔄 Пробуем fallback Alpha Vantage для S&P 500, ключ: {ALPHA_VANTAGE_KEY[:10]}...")
            try:
                alpha_response = requests.get(
                    f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey={ALPHA_VANTAGE_KEY}",
                    timeout=10
                )
                logger.info(f"📊 Alpha Vantage статус: {alpha_response.status_code}")
                
                if alpha_response.status_code == 200:
                    alpha_data = alpha_response.json()
                    logger.info(f"📊 Alpha Vantage ответ: {alpha_data}")
                    
                    if 'Global Quote' in alpha_data:
                        quote = alpha_data['Global Quote']
                        if '05. price' in quote:
                            price = float(quote['05. price'])
                            change_pct = float(quote['10. change percent'].replace('%', ''))
                            indices_data['sp500'] = {
                                'name': 'S&P 500 (SPY)',
                                'price': price,
                                'change_pct': change_pct
                            }
                            logger.info(f"✅ S&P 500 из Alpha Vantage: {price}")
                        else:
                            logger.warning("❌ Alpha Vantage: нет '05. price'")
                    else:
                        logger.warning("❌ Alpha Vantage: нет 'Global Quote'")
                else:
                    logger.error(f"❌ Alpha Vantage ошибка {alpha_response.status_code}: {alpha_response.text}")
            except Exception as fallback_e:
                logger.error(f"❌ Alpha Vantage fallback ошибка: {fallback_e}")
                    
        # Fallback: если S&P 500 не получен, логируем предупреждение (Alpha Vantage должен работать)
        if 'sp500' not in indices_data:
            logger.warning("⚠️ S&P 500 недоступен даже из Alpha Vantage - проверьте ключ API")
                    
    except Exception as e:
        logger.error(f"❌ Общая ошибка получения данных индексов: {e}")
    
    logger.info(f"📊 Итого индексов получено: {len(indices_data)} - {list(indices_data.keys())}")
    return indices_data

# Функция get_crypto_extended() удалена - заменена на прямые запросы к CoinGecko

# Файлы данных
NOTIFICATION_DATA_FILE = 'notifications.json'
PRICE_HISTORY_FILE = 'price_history.json'
SETTINGS_FILE = 'bot_settings.json'

def load_notification_data():
    """Загрузить данные уведомлений"""
    try:
        if os.path.exists(NOTIFICATION_DATA_FILE):
            with open(NOTIFICATION_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Ошибка загрузки уведомлений: {e}")
        return {}

def save_notification_data(data):
    """Сохранить данные уведомлений"""
    try:
        with open(NOTIFICATION_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения уведомлений: {e}")

def load_price_history():
    """Загрузить историю цен"""
    try:
        if os.path.exists(PRICE_HISTORY_FILE):
            with open(PRICE_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Ошибка загрузки истории: {e}")
        return {}

def save_price_history(data):
    """Сохранить историю цен"""
    try:
        with open(PRICE_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения истории: {e}")

def load_bot_settings():
    """Загрузить настройки бота"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        # Настройки по умолчанию
        return {
            'daily_summary_time': '09:00',  # Время в формате HH:MM
            'timezone': 'Europe/Moscow'
        }
    except Exception as e:
        logger.error(f"Ошибка загрузки настроек: {e}")
        return {
            'daily_summary_time': '09:00',
            'timezone': 'Europe/Moscow'
        }

def save_bot_settings(settings):
    """Сохранить настройки бота"""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Настройки сохранены: {settings}")
    except Exception as e:
        logger.error(f"Ошибка сохранения настроек: {e}")

def validate_time_format(time_str):
    """Проверить корректность формата времени HH:MM"""
    try:
        parts = time_str.split(':')
        if len(parts) != 2:
            return False
        
        hour = int(parts[0])
        minute = int(parts[1])
        
        if not (0 <= hour <= 23):
            return False
        if not (0 <= minute <= 59):
            return False
            
        return True
    except (ValueError, AttributeError):
        return False

# Функции проверки изменений и отправки уведомлений
async def check_price_changes(context: ContextTypes.DEFAULT_TYPE):
    """Проверить изменения цен и отправить уведомления"""
    try:
        # Получаем текущие данные
        current_prices = {}
        
        # Курсы валют
        cbr_response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
        if cbr_response.status_code == 200:
            cbr_data = cbr_response.json()
            current_prices.update({
                'USD': cbr_data.get('Valute', {}).get('USD', {}).get('Value'),
                'EUR': cbr_data.get('Valute', {}).get('EUR', {}).get('Value'),
                'CNY': cbr_data.get('Valute', {}).get('CNY', {}).get('Value'),
                'GBP': cbr_data.get('Valute', {}).get('GBP', {}).get('Value')
            })
        
        # Криптовалюты
        crypto_response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,the-open-network,ripple,cardano,solana,dogecoin&vs_currencies=usd",
            timeout=10
        )
        if crypto_response.status_code == 200:
            crypto_data = crypto_response.json()
            current_prices.update({
                'BTC': crypto_data.get('bitcoin', {}).get('usd'),
                'ETH': crypto_data.get('ethereum', {}).get('usd'),
                'TON': crypto_data.get('the-open-network', {}).get('usd'),
                'XRP': crypto_data.get('ripple', {}).get('usd'),
                'ADA': crypto_data.get('cardano', {}).get('usd'),
                'SOL': crypto_data.get('solana', {}).get('usd'),
                'DOGE': crypto_data.get('dogecoin', {}).get('usd')
            })
        
        # Акции
        moex_data = await get_moex_stocks()
        for ticker, data in moex_data.items():
            current_prices[ticker] = data.get('price')
        
        # Загружаем предыдущие цены
        price_history = load_price_history()
        notifications = load_notification_data()
        
        # Проверяем изменения и отправляем уведомления
        for user_id, user_notifications in notifications.items():
            if not user_notifications.get('subscribed', False):
                continue
            
            threshold = user_notifications.get('threshold', 2.0)
            alerts = user_notifications.get('alerts', {})
            
            notifications_to_send = []
            
            # Проверяем резкие изменения
            for asset, current_price in current_prices.items():
                if current_price is None:
                    continue
                
                previous_price = price_history.get(asset)
                if previous_price is None:
                    continue
                
                change_pct = ((current_price - previous_price) / previous_price) * 100
                
                if abs(change_pct) >= threshold:
                    emoji = "📈" if change_pct > 0 else "📉"
                    notifications_to_send.append(
                        f"{emoji} <b>{asset}</b>: {change_pct:+.2f}% "
                        f"({previous_price:.2f} → {current_price:.2f})"
                    )
            
            # Проверяем пороговые алерты
            for asset, alert_threshold in alerts.items():
                current_price = current_prices.get(asset)
                if current_price is None:
                    continue
                
                if current_price >= alert_threshold:
                    notifications_to_send.append(
                        f"🚨 <b>АЛЕРТ:</b> {asset} достиг {current_price:.2f} "
                        f"(порог: {alert_threshold})"
                    )
            
            # Отправляем уведомления
            if notifications_to_send:
                message = "🔔 <b>УВЕДОМЛЕНИЯ О ЦЕНАХ</b>\n\n" + "\n".join(notifications_to_send)
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id),
                        text=message,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
        
        # Сохраняем текущие цены как историю
        price_history.update({k: v for k, v in current_prices.items() if v is not None})
        save_price_history(price_history)
        
    except Exception as e:
        logger.error(f"Ошибка проверки изменений цен: {e}")

async def daily_summary_job(context: ContextTypes.DEFAULT_TYPE):
    """Отправить ежедневную сводку в 9:00 МСК"""
    logger.info("🌅 Запуск ежедневной сводки...")
    
    try:
        notifications = load_notification_data()
        logger.info(f"📋 Загружено уведомлений: {len(notifications)}")
        
        if not notifications:
            logger.warning("⚠️ Нет подписчиков для ежедневной сводки")
            return
        
        # Подсчитываем активных подписчиков
        active_subscribers = 0
        for user_id, user_notifications in notifications.items():
            if not user_notifications.get('subscribed', False):
                continue
            if not user_notifications.get('daily_summary', True):
                continue
            active_subscribers += 1
        
        logger.info(f"📊 Активных подписчиков на ежедневную сводку: {active_subscribers}")
        
        if active_subscribers == 0:
            logger.warning("⚠️ Нет активных подписчиков на ежедневную сводку")
            return
            
        # Получаем актуальные курсы для сводки
        logger.info("📡 Получаю данные для ежедневной сводки...")
        
        for user_id, user_notifications in notifications.items():
            if not user_notifications.get('subscribed', False):
                continue
            if not user_notifications.get('daily_summary', True):
                continue
            
            try:
                logger.info(f"📤 Отправляю сводку пользователю {user_id}")
                
                # Отправляем заголовок
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text="🌅 **ЕЖЕДНЕВНАЯ СВОДКА**\n\n📊 Получаю актуальные курсы финансовых инструментов...",
                    parse_mode='Markdown'
                )
                
                # Создаем fake Update для вызова rates_command
                # Поскольку rates_command нужен Update объект, создаем минимальный
                class FakeUpdate:
                    def __init__(self, user_id):
                        self.effective_user = type('obj', (object,), {'id': user_id})
                        self.message = type('obj', (object,), {
                            'reply_text': lambda text, parse_mode=None: context.bot.send_message(
                                chat_id=user_id, text=text, parse_mode=parse_mode
                            )
                        })
                
                fake_update = FakeUpdate(int(user_id))
                
                # Вызываем rates_command для получения полной сводки
                await rates_command(fake_update, context)
                
                logger.info(f"✅ Сводка отправлена пользователю {user_id}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка отправки ежедневной сводки пользователю {user_id}: {e}")
        
        logger.info(f"🎉 Ежедневная сводка завершена. Отправлено {active_subscribers} пользователям")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка ежедневной сводки: {e}")
        import traceback
        logger.error(f"📋 Трассировка: {traceback.format_exc()}")

async def set_daily_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Настроить время ежедневной сводки (только для админа)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return
    
    # Проверяем аргументы
    if not context.args:
        await update.message.reply_html(
            "⏰ <b>Настройка времени ежедневной сводки</b>\n\n"
            "<b>Использование:</b>\n"
            "/set_daily_time HH:MM\n\n"
            "<b>Примеры:</b>\n"
            "• /set_daily_time 09:00 - сводка в 9:00 МСК\n"
            "• /set_daily_time 21:30 - сводка в 21:30 МСК\n"
            "• /set_daily_time 06:15 - сводка в 6:15 МСК\n\n"
            "💡 Время указывается в московском часовом поясе"
        )
        return
    
    time_str = context.args[0]
    
    # Валидация формата времени
    if not validate_time_format(time_str):
        await update.message.reply_html(
            "❌ <b>Неверный формат времени!</b>\n\n"
            "Используйте формат <b>HH:MM</b> (24-часовой формат)\n"
            "Например: 09:00, 15:30, 21:45\n\n"
            "Часы: от 00 до 23\n"
            "Минуты: от 00 до 59"
        )
        return
    
    try:
        # Загружаем текущие настройки
        settings = load_bot_settings()
        old_time = settings.get('daily_summary_time', '09:00')
        
        # Обновляем время
        settings['daily_summary_time'] = time_str
        save_bot_settings(settings)
        
        # Пытаемся перезапустить задачу автоматически
        job_queue = get_job_queue(context)
        restart_success = False
        
        if job_queue:
            try:
                # Удаляем существующую задачу
                current_jobs = job_queue.get_jobs_by_name("daily_summary")
                if current_jobs:
                    for job in current_jobs:
                        job.schedule_removal()
                
                # Парсим новое время
                hour, minute = map(int, time_str.split(':'))
                moscow_tz = pytz.timezone('Europe/Moscow')
                daily_time = time(hour=hour, minute=minute, tzinfo=moscow_tz)
                
                # Создаем новую задачу
                job_queue.run_daily(
                    daily_summary_job,
                    time=daily_time,
                    name="daily_summary"
                )
                
                restart_success = True
                logger.info(f"🔄 Задача ежедневной сводки автоматически перезапущена на {time_str}")
                
            except Exception as restart_error:
                logger.error(f"❌ Ошибка автоматического перезапуска: {restart_error}")
        
        if restart_success:
            # Вычисляем время до следующего запуска
            from datetime import datetime
            moscow_tz = pytz.timezone('Europe/Moscow')
            current_moscow_time = datetime.now(moscow_tz)
            hour, minute = map(int, time_str.split(':'))
            next_run = current_moscow_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if current_moscow_time.hour > hour or (current_moscow_time.hour == hour and current_moscow_time.minute >= minute):
                next_run = next_run.replace(day=next_run.day + 1)
            
            time_until = next_run - current_moscow_time
            hours_until = int(time_until.total_seconds() // 3600)
            minutes_until = int((time_until.total_seconds() % 3600) // 60)
            
            await update.message.reply_html(
                f"✅ <b>Время ежедневной сводки обновлено!</b>\n\n"
                f"🕐 <b>Было:</b> {old_time} МСК\n"
                f"🕐 <b>Стало:</b> {time_str} МСК\n\n"
                f"🔄 <b>Задача автоматически перезапущена!</b>\n"
                f"⏰ <b>До следующей сводки:</b> {hours_until}ч {minutes_until}мин\n"
                f"📊 <b>Следующая сводка:</b> {next_run.strftime('%H:%M %d.%m.%Y')}\n\n"
                f"🎉 Изменения вступили в силу немедленно!"
            )
        else:
            await update.message.reply_html(
                f"✅ <b>Время ежедневной сводки обновлено!</b>\n\n"
                f"🕐 <b>Было:</b> {old_time} МСК\n"
                f"🕐 <b>Стало:</b> {time_str} МСК\n\n"
                f"⚠️ <b>Внимание:</b> Не удалось автоматически перезапустить задачу.\n"
                f"🔄 Используйте /restart_daily_job или перезапустите бота на Railway."
            )
        
        logger.info(f"⏰ Админ {user_id} изменил время ежедневной сводки: {old_time} → {time_str}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при сохранении настроек: {e}")
        logger.error(f"Ошибка set_daily_time: {e}")

async def get_daily_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать текущие настройки ежедневной сводки (только для админа)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return
    
    try:
        settings = load_bot_settings()
        notifications = load_notification_data()
        
        # Подсчитываем подписчиков
        total_users = len(notifications)
        active_subscribers = 0
        daily_summary_subscribers = 0
        
        for uid, data in notifications.items():
            if data.get('subscribed', False):
                active_subscribers += 1
            if data.get('daily_summary', True) and data.get('subscribed', False):
                daily_summary_subscribers += 1
        
        # Получаем текущее московское время
        moscow_tz = pytz.timezone(settings.get('timezone', 'Europe/Moscow'))
        current_time = datetime.now(moscow_tz)
        
        # Вычисляем время до следующей сводки
        daily_time_str = settings.get('daily_summary_time', '09:00')
        hour, minute = map(int, daily_time_str.split(':'))
        
        next_run = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if current_time.hour > hour or (current_time.hour == hour and current_time.minute >= minute):
            # Если время уже прошло сегодня, планируем на завтра
            next_run = next_run.replace(day=next_run.day + 1)
        
        time_until = next_run - current_time
        hours_until = int(time_until.total_seconds() // 3600)
        minutes_until = int((time_until.total_seconds() % 3600) // 60)
        
        message = (
            f"⚙️ <b>НАСТРОЙКИ ЕЖЕДНЕВНОЙ СВОДКИ</b>\n\n"
            f"🕐 <b>Время отправки:</b> {daily_time_str} МСК\n"
            f"🌍 <b>Часовой пояс:</b> {settings.get('timezone', 'Europe/Moscow')}\n"
            f"📅 <b>Текущее время:</b> {current_time.strftime('%H:%M:%S %d.%m.%Y')}\n\n"
            f"⏰ <b>До следующей сводки:</b> {hours_until}ч {minutes_until}мин\n"
            f"📊 <b>Следующая сводка:</b> {next_run.strftime('%H:%M %d.%m.%Y')}\n\n"
            f"👥 <b>СТАТИСТИКА ПОДПИСЧИКОВ:</b>\n"
            f"├ Всего пользователей: {total_users}\n"
            f"├ Активных подписчиков: {active_subscribers}\n"
            f"└ Подписано на сводку: {daily_summary_subscribers}\n\n"
            f"🔧 <b>Команды:</b>\n"
            f"• /set_daily_time HH:MM - изменить время\n"
            f"• /restart_daily_job - перезапустить задачу\n"
            f"• /test_daily - тестовый запуск\n"
            f"• /check_subscribers - детали подписчиков"
        )
        
        await update.message.reply_html(message)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка получения настроек: {e}")
        logger.error(f"Ошибка get_daily_settings: {e}")

async def restart_daily_job_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Перезапустить задачу ежедневной сводки с новыми настройками (только для админа)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return
    
    try:
        await update.message.reply_html("🔄 <b>Перезапускаю задачу ежедневной сводки...</b>")
        
        # Получаем job_queue из контекста или глобальной переменной
        job_queue = get_job_queue(context)
        if not job_queue:
            await update.message.reply_html("❌ Система задач недоступна")
            return
        
        logger.info(f"🔧 Используется система задач: {type(job_queue).__name__}")
        
        # Удаляем существующую задачу
        current_jobs = job_queue.get_jobs_by_name("daily_summary")
        if current_jobs:
            for job in current_jobs:
                job.schedule_removal()
            logger.info(f"🗑️ Удалено {len(current_jobs)} существующих задач ежедневной сводки")
        
        # Загружаем новые настройки
        settings = load_bot_settings()
        daily_time_str = settings.get('daily_summary_time', '09:00')
        timezone_str = settings.get('timezone', 'Europe/Moscow')
        
        # Парсим время из настроек
        hour, minute = map(int, daily_time_str.split(':'))
        moscow_tz = pytz.timezone(timezone_str)
        daily_time = time(hour=hour, minute=minute, tzinfo=moscow_tz)
        
        # Создаем новую задачу
        job_queue.run_daily(
            daily_summary_job,
            time=daily_time,
            name="daily_summary"
        )
        
        # Вычисляем время до следующего запуска
        from datetime import datetime
        current_moscow_time = datetime.now(moscow_tz)
        next_run = current_moscow_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if current_moscow_time.hour > hour or (current_moscow_time.hour == hour and current_moscow_time.minute >= minute):
            next_run = next_run.replace(day=next_run.day + 1)
        
        time_until = next_run - current_moscow_time
        hours_until = int(time_until.total_seconds() // 3600)
        minutes_until = int((time_until.total_seconds() % 3600) // 60)
        
        await update.message.reply_html(
            f"✅ <b>Задача ежедневной сводки перезапущена!</b>\n\n"
            f"🕐 <b>Новое время:</b> {daily_time_str} МСК\n"
            f"📅 <b>Текущее время:</b> {current_moscow_time.strftime('%H:%M:%S')}\n"
            f"⏰ <b>До следующей сводки:</b> {hours_until}ч {minutes_until}мин\n"
            f"📊 <b>Следующая сводка:</b> {next_run.strftime('%H:%M %d.%m.%Y')}\n\n"
            f"🎉 Изменения вступили в силу немедленно!"
        )
        
        logger.info(f"🔄 Админ {user_id} перезапустил задачу ежедневной сводки на {daily_time_str}")
        
    except Exception as e:
        await update.message.reply_html(f"❌ <b>Ошибка перезапуска задачи:</b>\n{e}")
        logger.error(f"Ошибка restart_daily_job: {e}")

# Альтернативная реализация задач если JobQueue не работает
class AlternativeJob:
    """Эмуляция Job для совместимости"""
    
    def __init__(self, name, callback, job_queue):
        self.name = name
        self.callback = callback
        self.job_queue = job_queue
        self.removed = False
        logger.debug(f"🔧 Создана альтернативная задача: {name}")
    
    def schedule_removal(self):
        """Помечает задачу для удаления"""
        self.removed = True
        logger.info(f"🗑️ Альтернативная задача {self.name} помечена для удаления")

class AlternativeJobQueue:
    """Простая альтернативная реализация задач через threading"""
    
    def __init__(self, application):
        self.application = application
        self.jobs = {}  # Словарь для хранения задач по именам
        self.running = False
        self.active_timers = {}  # Активные таймеры
        logger.info("🔄 Создана альтернативная система задач")
    
    def run_daily(self, callback, time, name):
        """Запустить ежедневную задачу"""
        import time as time_module
        
        # Удаляем существующую задачу с таким именем
        if name in self.jobs:
            old_job = self.jobs[name]
            old_job.schedule_removal()
            self._stop_timer(name)
        
        # Создаем новую задачу
        job = AlternativeJob(name, callback, self)
        self.jobs[name] = job
        
        time_str = time.strftime('%H:%M')
        logger.info(f"📅 Настраиваю альтернативную ежедневную задачу '{name}' на {time_str}")
        
        if SCHEDULE_AVAILABLE:
            # Удаляем предыдущие schedule задачи
            schedule.clear(name)
            
            # Используем schedule для ежедневных задач
            schedule.every().day.at(time_str).do(self._run_job, callback, name).tag(name)
            
            # Запускаем поток для выполнения задач
            if not self.running:
                self.running = True
                thread = threading.Thread(target=self._schedule_runner, daemon=True)
                thread.start()
                logger.info("✅ Альтернативный планировщик задач запущен (schedule)")
        else:
            # Используем простой Timer для ежедневных задач
            self._setup_timer_daily(callback, time, name)
            logger.info("✅ Альтернативный планировщик задач запущен (timer)")
    
    def run_repeating(self, callback, interval, first, name):
        """Запустить повторяющуюся задачу"""
        logger.info(f"⏰ Настраиваю альтернативную повторяющуюся задачу '{name}' каждые {interval}с")
        
        # Удаляем существующую задачу с таким именем
        if name in self.jobs:
            old_job = self.jobs[name]
            old_job.schedule_removal()
            self._stop_timer(name)
        
        # Создаем новую задачу
        job = AlternativeJob(name, callback, self)
        self.jobs[name] = job
        
        def run_job():
            import asyncio
            try:
                # Проверяем, не была ли задача удалена
                if name in self.jobs and not self.jobs[name].removed:
                    # Создаем контекст для задачи
                    context = type('obj', (object,), {
                        'bot': self.application.bot,
                        'job_queue': self
                    })
                    
                    # Запускаем асинхронную функцию
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(callback(context))
                    loop.close()
            except Exception as e:
                logger.error(f"❌ Ошибка выполнения альтернативной задачи {name}: {e}")
        
        # Первый запуск
        timer = threading.Timer(first, run_job)
        timer.daemon = True
        timer.start()
        self.active_timers[name + "_first"] = timer
        
        # Повторяющиеся запуски
        def repeat_job():
            if name in self.jobs and not self.jobs[name].removed:
                run_job()
                if self.running and name in self.jobs and not self.jobs[name].removed:
                    timer = threading.Timer(interval, repeat_job)
                    timer.daemon = True
                    timer.start()
                    self.active_timers[name + "_repeat"] = timer
        
        # Запускаем повторяющиеся задачи после первого запуска
        repeat_timer = threading.Timer(first + interval, repeat_job)
        repeat_timer.daemon = True
        repeat_timer.start()
        self.active_timers[name + "_repeat_start"] = repeat_timer
    
    def _run_job(self, callback, name):
        """Выполнить задачу"""
        import asyncio
        try:
            # Проверяем, не была ли задача удалена
            if name in self.jobs and self.jobs[name].removed:
                logger.info(f"⏭️ Пропускаю выполнение удаленной задачи: {name}")
                return
                
            logger.info(f"▶️ Выполняю альтернативную задачу: {name}")
            
            # Создаем контекст для задачи
            context = type('obj', (object,), {
                'bot': self.application.bot,
                'job_queue': self
            })
            
            # Запускаем асинхронную функцию
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(callback(context))
            loop.close()
            
            logger.info(f"✅ Альтернативная задача {name} выполнена")
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения альтернативной задачи {name}: {e}")
    
    def _setup_timer_daily(self, callback, target_time, name):
        """Настроить ежедневную задачу через Timer (без schedule)"""
        from datetime import datetime, timedelta
        import time as time_module
        
        def calculate_next_run():
            """Вычислить время до следующего запуска"""
            now = datetime.now()
            
            # Парсим целевое время
            hour = target_time.hour
            minute = target_time.minute
            
            # Создаем время сегодня
            today_target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Если время уже прошло сегодня, планируем на завтра
            if now >= today_target:
                next_run = today_target + timedelta(days=1)
            else:
                next_run = today_target
            
            # Вычисляем секунды до запуска
            time_diff = next_run - now
            return time_diff.total_seconds(), next_run
        
        def run_and_reschedule():
            """Выполнить задачу и запланировать следующую"""
            try:
                # Проверяем, не была ли задача удалена
                if name in self.jobs and not self.jobs[name].removed:
                    self._run_job(callback, name)
            except Exception as e:
                logger.error(f"❌ Ошибка выполнения timer задачи {name}: {e}")
            
            # Планируем следующий запуск
            if self.running and name in self.jobs and not self.jobs[name].removed:
                seconds_until, next_run = calculate_next_run()
                logger.info(f"⏰ Следующий запуск задачи {name}: {next_run.strftime('%H:%M %d.%m.%Y')} (через {int(seconds_until/3600)}ч {int((seconds_until%3600)/60)}мин)")
                
                timer = threading.Timer(seconds_until, run_and_reschedule)
                timer.daemon = True
                timer.start()
                self.active_timers[name + "_daily"] = timer
        
        # Запускаем первую задачу
        seconds_until, next_run = calculate_next_run()
        logger.info(f"⏰ Первый запуск задачи {name}: {next_run.strftime('%H:%M %d.%m.%Y')} (через {int(seconds_until/3600)}ч {int((seconds_until%3600)/60)}мин)")
        
        timer = threading.Timer(seconds_until, run_and_reschedule)
        timer.daemon = True
        timer.start()
        self.active_timers[name + "_daily"] = timer
        
        self.running = True
    
    def _schedule_runner(self):
        """Запускает планировщик задач в отдельном потоке (только если schedule доступен)"""
        if not SCHEDULE_AVAILABLE:
            logger.error("❌ Попытка запустить schedule_runner без модуля schedule")
            return
            
        import time as time_module
        
        logger.info("🔄 Альтернативный планировщик задач запущен")
        while self.running:
            try:
                schedule.run_pending()
                time_module.sleep(60)  # Проверяем каждую минуту
            except Exception as e:
                logger.error(f"❌ Ошибка в планировщике задач: {e}")
                time_module.sleep(60)
    
    def get_jobs_by_name(self, name):
        """Получить задачи по имени"""
        if name in self.jobs and not self.jobs[name].removed:
            return [self.jobs[name]]
        return []

    def _stop_timer(self, name):
        """Остановить активные таймеры для задачи"""
        timers_to_remove = []
        for timer_name, timer in self.active_timers.items():
            if timer_name.startswith(name):
                try:
                    timer.cancel()
                    logger.debug(f"🛑 Остановлен таймер: {timer_name}")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка остановки таймера {timer_name}: {e}")
                timers_to_remove.append(timer_name)
        
        # Удаляем остановленные таймеры из словаря
        for timer_name in timers_to_remove:
            del self.active_timers[timer_name]

def get_job_queue(context=None):
    """Получить доступную систему задач"""
    global GLOBAL_JOB_QUEUE
    
    # Сначала пробуем получить из контекста
    if context and hasattr(context, 'job_queue') and context.job_queue:
        logger.debug("🔧 Используется job_queue из контекста")
        return context.job_queue
    
    # Если не получилось, используем глобальную
    if GLOBAL_JOB_QUEUE:
        logger.debug("🔧 Используется глобальная система задач")
        return GLOBAL_JOB_QUEUE
    
    logger.error("❌ Система задач недоступна")
    return None

def main() -> None:
    """Запуск бота - продвинутая версия с уведомлениями"""
    global GLOBAL_JOB_QUEUE
    
    logger.info("🚀 Запуск продвинутого финансового бота...")
    
    # Загружаем данные пользователей при старте
    load_user_data()
    
    # Создаем приложение с явно включенным JobQueue
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Проверяем доступность JobQueue и выводим детальную диагностику
    job_queue = application.job_queue
    logger.info(f"🔍 Диагностика JobQueue:")
    logger.info(f"   application.job_queue: {job_queue}")
    logger.info(f"   type: {type(job_queue)}")
    logger.info(f"   bool(job_queue): {bool(job_queue)}")
    
    if job_queue is None:
        logger.error("❌ JobQueue is None! Попробуем создать принудительно...")
        try:
            # Пробуем разные способы импорта JobQueue
            job_queue_created = False
            
            # Способ 1: прямой импорт
            try:
                from telegram.ext import JobQueue as TelegramJobQueue
                job_queue = TelegramJobQueue()
                application._job_queue = job_queue
                job_queue_created = True
                logger.info("✅ JobQueue создан (способ 1: прямой импорт)")
            except Exception as e1:
                logger.warning(f"⚠️ Способ 1 не сработал: {e1}")
            
            # Способ 2: через приватный модуль
            if not job_queue_created:
                try:
                    from telegram.ext._jobqueue import JobQueue as PrivateJobQueue
                    job_queue = PrivateJobQueue()
                    application._job_queue = job_queue
                    job_queue_created = True
                    logger.info("✅ JobQueue создан (способ 2: приватный модуль)")
                except Exception as e2:
                    logger.warning(f"⚠️ Способ 2 не сработал: {e2}")
            
            # Способ 3: через Application.builder()
            if not job_queue_created:
                try:
                    new_app = Application.builder().token(BOT_TOKEN).job_queue(None).build()
                    job_queue = new_app.job_queue
                    if job_queue:
                        application._job_queue = job_queue
                        job_queue_created = True
                        logger.info("✅ JobQueue создан (способ 3: через builder)")
                except Exception as e3:
                    logger.warning(f"⚠️ Способ 3 не сработал: {e3}")
            
            if not job_queue_created:
                logger.error("❌ Все способы создания JobQueue не сработали")
                logger.info("🔄 Переходим на альтернативную систему задач...")
                job_queue = AlternativeJobQueue(application)
                GLOBAL_JOB_QUEUE = job_queue
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при создании JobQueue: {e}")
            logger.info("🔄 Используем альтернативную систему задач как fallback...")
            job_queue = AlternativeJobQueue(application)
            GLOBAL_JOB_QUEUE = job_queue
    else:
        logger.info("✅ JobQueue инициализирован успешно")
        # Сохраняем успешную JobQueue в глобальную переменную
        GLOBAL_JOB_QUEUE = job_queue

    # JobQueue уже получен выше в диагностике

    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("rates", rates_command))
    
    # Команды уведомлений
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("set_alert", set_alert_command))
    application.add_handler(CommandHandler("view_alerts", view_alerts_command))
    application.add_handler(CommandHandler("test_daily", test_daily_command))
    application.add_handler(CommandHandler("check_subscribers", check_subscribers_command))
    application.add_handler(CommandHandler("set_daily_time", set_daily_time_command))
    application.add_handler(CommandHandler("get_daily_settings", get_daily_settings_command))
    application.add_handler(CommandHandler("restart_daily_job", restart_daily_job_command))

    # Обработчик всех текстовых сообщений (эхо)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Настройка периодических задач
    if job_queue:
        logger.info(f"🔧 Используется система задач: {type(job_queue).__name__}")
        # Проверка изменений цен каждые 30 минут
        job_queue.run_repeating(
            check_price_changes,
            interval=1800,  # 30 минут в секундах
            first=60,  # Первый запуск через 1 минуту
            name="price_changes_check"
        )
        logger.info("⏰ Настроена проверка изменений цен каждые 30 минут")
        
        # Ежедневная сводка - время из настроек
        settings = load_bot_settings()
        daily_time_str = settings.get('daily_summary_time', '09:00')
        timezone_str = settings.get('timezone', 'Europe/Moscow')
        
        try:
            # Парсим время из настроек
            hour, minute = map(int, daily_time_str.split(':'))
            moscow_tz = pytz.timezone(timezone_str)
            daily_time = time(hour=hour, minute=minute, tzinfo=moscow_tz)
            
            # Получаем текущее московское время для отладки
            from datetime import datetime
            current_moscow_time = datetime.now(moscow_tz)
            logger.info(f"🕐 Текущее московское время: {current_moscow_time.strftime('%H:%M:%S %d.%m.%Y')}")
            logger.info(f"📅 Настраиваю ежедневную сводку на: {daily_time_str} МСК (из настроек)")
            
            job_queue.run_daily(
                daily_summary_job,
                time=daily_time,
                name="daily_summary"
            )
            logger.info(f"✅ Ежедневная сводка в {daily_time_str} МСК настроена успешно")
            
            # Показываем сколько времени до следующего запуска
            next_run = current_moscow_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if current_moscow_time.hour > hour or (current_moscow_time.hour == hour and current_moscow_time.minute >= minute):
                next_run = next_run.replace(day=next_run.day + 1)
            time_until = next_run - current_moscow_time
            hours_until = int(time_until.total_seconds() // 3600)
            minutes_until = int((time_until.total_seconds() % 3600) // 60)
            logger.info(f"⏰ До следующей ежедневной сводки: {hours_until}ч {minutes_until}мин")
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки времени ежедневной сводки: {e}")
            logger.info("🔄 Использую время по умолчанию: 09:00 МСК")
            
            # Fallback на время по умолчанию
            moscow_tz = pytz.timezone('Europe/Moscow')
            daily_time = time(hour=9, minute=0, tzinfo=moscow_tz)
            job_queue.run_daily(
                daily_summary_job,
                time=daily_time,
                name="daily_summary"
            )
            logger.info("✅ Ежедневная сводка в 09:00 МСК настроена (fallback)")
    else:
        logger.warning("⚠️ Система задач недоступна - уведомления отключены")
        logger.error("🚨 Критическая ошибка: job_queue не может быть None на этом этапе!")

    # Запуск бота
    logger.info("✅ Продвинутый финансовый бот запущен и готов к работе")
    logger.info("📊 Доступные функции: курсы валют, криптовалют, акций, товаров, индексов")
    logger.info("🔔 Уведомления: резкие изменения, пороговые алерты, ежедневная сводка")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 