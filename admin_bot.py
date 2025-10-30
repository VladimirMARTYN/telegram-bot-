#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import asyncio
from datetime import datetime, time
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, JobQueue
import json
import aiohttp
import threading
from flask import Flask, jsonify

# Импорты конфигурации и утилит
from config import (
    BOT_TOKEN, ADMIN_USER_ID, DEFAULT_THRESHOLD, PRICE_CHECK_INTERVAL,
    DEFAULT_DAILY_TIME, DEFAULT_TIMEZONE, CACHE_TTL_CURRENCIES,
    CACHE_TTL_CRYPTO, CACHE_TTL_STOCKS, CACHE_TTL_COMMODITIES, CACHE_TTL_INDICES,
    SUPPORTED_CURRENCIES, SUPPORTED_CRYPTO, SUPPORTED_STOCKS
)
from utils import (
    is_admin, get_cached_data, fetch_with_retry, validate_positive_number,
    validate_asset, escape_html, format_price, clear_cache
)
from data_sources import (
    get_cbr_rates, get_forex_rates, get_crypto_data, get_moex_stocks,
    get_commodities_data, get_indices_data
)

# Настройка логирования (должна быть перед импортом reportlab)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Безопасный импорт reportlab (может отсутствовать)
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
    logger.info("✅ ReportLab доступен для PDF экспорта")
except ImportError:
    REPORTLAB_AVAILABLE = False
    # Создаем заглушки для типов
    letter = A4 = None
    SimpleDocTemplate = Paragraph = Spacer = Table = TableStyle = None
    getSampleStyleSheet = ParagraphStyle = None
    inch = None
    colors = None
    canvas = None
    logger.warning("⚠️ ReportLab недоступен - PDF экспорт отключен")

import io

# Безопасный импорт schedule (может отсутствовать)
try:
    import schedule
    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False

# Логирование уже настроено выше

# Предупреждение о недоступности schedule
if not SCHEDULE_AVAILABLE:
    logger.warning("⚠️ Модуль 'schedule' не установлен. Альтернативная система задач будет использовать только Timer")

# Глобальная переменная для системы задач
GLOBAL_JOB_QUEUE = None

# Глобальная сессия aiohttp для переиспользования
_http_session: aiohttp.ClientSession = None

def get_http_session() -> aiohttp.ClientSession:
    """Получить или создать глобальную HTTP сессию"""
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session

# Функция для получения московского времени
def get_moscow_time():
    """Возвращает текущее время в московском часовом поясе"""
    moscow_tz = pytz.timezone(DEFAULT_TIMEZONE)
    return datetime.now(moscow_tz)

# Старые функции удалены - используются функции из data_sources.py
    """Получить данные акций с Московской биржи"""
    stocks_data = {}
    
    # Проверяем, является ли сегодня торговым днем
    from datetime import datetime
    moscow_tz = pytz.timezone('Europe/Moscow')
    current_moscow = datetime.now(moscow_tz)
    is_weekend = current_moscow.weekday() >= 5  # 5=суббота, 6=воскресенье
    
    logger.info(f"📅 Проверка торговых дней для акций: {'Выходной' if is_weekend else 'Торговый день'}")
    
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
    
    # Если выходной день, возвращаем пустые данные с пометкой
    if is_weekend:
        logger.info("📅 Выходной день - торги на MOEX закрыты")
        for ticker, info in stocks.items():
            stocks_data[ticker] = {
                'name': info['name'],
                'emoji': info['emoji'],
                'price': None,
                'change': 0,
                'change_pct': 0,
                'is_live': False,
                'note': 'Торги закрыты'
            }
        return stocks_data
    
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

async def get_crypto_data_with_fallback():
    """Получить данные криптовалют с резервными источниками"""
    crypto_data = {}
    
    # Список криптовалют для мониторинга
    crypto_list = [
        {'id': 'bitcoin', 'symbol': 'BTC', 'name': 'Bitcoin'},
        {'id': 'ethereum', 'symbol': 'ETH', 'name': 'Ethereum'},
        {'id': 'the-open-network', 'symbol': 'TON', 'name': 'TON'},
        {'id': 'ripple', 'symbol': 'XRP', 'name': 'XRP'},
        {'id': 'cardano', 'symbol': 'ADA', 'name': 'Cardano'},
        {'id': 'solana', 'symbol': 'SOL', 'name': 'Solana'},
        {'id': 'dogecoin', 'symbol': 'DOGE', 'name': 'Dogecoin'},
        {'id': 'tether', 'symbol': 'USDT', 'name': 'Tether'}
    ]
    
    # 1. Пробуем CoinGecko (основной источник)
    logger.info("🪙 Пробуем получить данные криптовалют с CoinGecko...")
    try:
        crypto_ids = ','.join([crypto['id'] for crypto in crypto_list])
        crypto_response = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_ids}&vs_currencies=usd&include_24hr_change=true",
            timeout=10
        )
        
        if crypto_response.status_code == 200:
            data = crypto_response.json()
            
            for crypto in crypto_list:
                crypto_id = crypto['id']
                if crypto_id in data:
                    price = data[crypto_id].get('usd')
                    change_24h = data[crypto_id].get('usd_24h_change', 0)
                    
                    if price is not None:
                        crypto_data[crypto_id] = {
                            'price': price,
                            'change_24h': change_24h,
                            'source': 'CoinGecko'
                        }
            
            if crypto_data:
                logger.info(f"✅ CoinGecko успешно получены данные для {len(crypto_data)} криптовалют")
                return crypto_data
            else:
                logger.warning("⚠️ CoinGecko вернул пустые данные")
        else:
            logger.warning(f"⚠️ CoinGecko вернул статус {crypto_response.status_code}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка CoinGecko: {e}")
    
    # 2. Пробуем Coinbase API (резервный источник)
    logger.info("🪙 Пробуем получить данные криптовалют с Coinbase...")
    try:
        coinbase_symbols = [crypto['symbol'] for crypto in crypto_list]
        
        for symbol in coinbase_symbols:
            try:
                coinbase_response = requests.get(
                    f"https://api.coinbase.com/v2/prices/{symbol}-USD/spot",
                    timeout=10
                )
                
                if coinbase_response.status_code == 200:
                    data = coinbase_response.json()
                    price = float(data['data']['amount'])
                    
                    # Находим соответствующий crypto_id
                    for crypto in crypto_list:
                        if crypto['symbol'] == symbol:
                            crypto_id = crypto['id']
                            crypto_data[crypto_id] = {
                                'price': price,
                                'change_24h': 0,  # Coinbase не предоставляет изменение за 24ч в этом эндпоинте
                                'source': 'Coinbase'
                            }
                            break
                            
            except Exception as e:
                logger.debug(f"❌ Ошибка получения {symbol} с Coinbase: {e}")
                continue
        
        if crypto_data:
            logger.info(f"✅ Coinbase успешно получены данные для {len(crypto_data)} криптовалют")
            return crypto_data
            
    except Exception as e:
        logger.error(f"❌ Общая ошибка Coinbase: {e}")
    
    # 3. Пробуем Binance API (еще один резервный источник)
    logger.info("🪙 Пробуем получить данные криптовалют с Binance...")
    try:
        binance_symbols = [f"{crypto['symbol']}USDT" for crypto in crypto_list]
        
        for symbol in binance_symbols:
            try:
                binance_response = requests.get(
                    f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}",
                    timeout=10
                )
                
                if binance_response.status_code == 200:
                    data = binance_response.json()
                    price = float(data['price'])
                    
                    # Находим соответствующий crypto_id
                    for crypto in crypto_list:
                        if f"{crypto['symbol']}USDT" == symbol:
                            crypto_id = crypto['id']
                            crypto_data[crypto_id] = {
                                'price': price,
                                'change_24h': 0,  # Binance не предоставляет изменение за 24ч в этом эндпоинте
                                'source': 'Binance'
                            }
                            break
                            
            except Exception as e:
                logger.debug(f"❌ Ошибка получения {symbol} с Binance: {e}")
                continue
        
        if crypto_data:
            logger.info(f"✅ Binance успешно получены данные для {len(crypto_data)} криптовалют")
            return crypto_data
            
    except Exception as e:
        logger.error(f"❌ Общая ошибка Binance: {e}")
    
    # 4. Пробуем CryptoCompare API (последний резервный источник)
    logger.info("🪙 Пробуем получить данные криптовалют с CryptoCompare...")
    try:
        cryptocompare_symbols = [crypto['symbol'] for crypto in crypto_list]
        
        for symbol in cryptocompare_symbols:
            try:
                cryptocompare_response = requests.get(
                    f"https://min-api.cryptocompare.com/data/price?fsym={symbol}&tsyms=USD",
                    timeout=10
                )
                
                if cryptocompare_response.status_code == 200:
                    data = cryptocompare_response.json()
                    price = data.get('USD')
                    
                    if price is not None:
                        # Находим соответствующий crypto_id
                        for crypto in crypto_list:
                            if crypto['symbol'] == symbol:
                                crypto_id = crypto['id']
                                crypto_data[crypto_id] = {
                                    'price': price,
                                    'change_24h': 0,  # CryptoCompare не предоставляет изменение за 24ч в этом эндпоинте
                                    'source': 'CryptoCompare'
                                }
                                break
                            
            except Exception as e:
                logger.debug(f"❌ Ошибка получения {symbol} с CryptoCompare: {e}")
                continue
        
        if crypto_data:
            logger.info(f"✅ CryptoCompare успешно получены данные для {len(crypto_data)} криптовалют")
            return crypto_data
            
    except Exception as e:
        logger.error(f"❌ Общая ошибка CryptoCompare: {e}")
    
    # Если все источники не сработали, возвращаем пустые данные
    logger.error("❌ Все источники криптовалют недоступны")
    return crypto_data

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
        f"🤖 <b>Вас приветствует бот-финансист с актуальными данными!</b>\n"
        f"Пожалуйста, ознакомьтесь:\n\n"
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
    
    # Создаем клавиатуру с основными кнопками
    keyboard = [
        [InlineKeyboardButton("📊 Курсы валют", callback_data="rates")],
        [InlineKeyboardButton("🔔 Подписаться на уведомления", callback_data="subscribe")],
        [InlineKeyboardButton("🌐 Веб-панель", url="https://telegram-bot-admin-web-production.up.railway.app")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(welcome_text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    help_text = (
        "🤖 <b>Справка по боту-финансисту</b>\n\n"
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
    if is_admin(update.effective_user.id):
        help_text += (
            "🔧 <b>Админские команды:</b>\n"
            "/settings - Меню настроек бота\n"
            "/export_pdf - Экспорт отчета в PDF\n"
            "/test_daily - Тестовая ежедневная сводка\n"
            "/check_subscribers - Статус подписчиков\n"
            "/set_daily_time HH:MM - Настроить время сводки\n"
            "/get_daily_settings - Посмотреть настройки\n"
            "/restart_daily_job - Перезапустить задачу сводки\n\n"
        )
    
    help_text += (
        "🔄 <b>Источники данных:</b>\n"
        "• ЦБ РФ - курсы валют\n"
        "• CoinGecko/Coinbase/Binance/CryptoCompare - криптовалюты (с резервными источниками)\n" 
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
        
        session = get_http_session()
        
        # Получаем все данные параллельно с кэшированием
        async def fetch_cbr():
            async def _fetch():
                return await get_cbr_rates(session)
            return await get_cached_data('cbr_rates', _fetch, CACHE_TTL_CURRENCIES)
        
        async def fetch_forex():
            async def _fetch():
                return await get_forex_rates(session)
            return await get_cached_data('forex_rates', _fetch, CACHE_TTL_CURRENCIES)
        
        async def fetch_crypto():
            async def _fetch():
                return await get_crypto_data(session)
            return await get_cached_data('crypto_data', _fetch, CACHE_TTL_CRYPTO)
        
        async def fetch_stocks():
            async def _fetch():
                return await get_moex_stocks(session)
            return await get_cached_data('moex_stocks', _fetch, CACHE_TTL_STOCKS)
        
        async def fetch_commodities():
            async def _fetch():
                return await get_commodities_data(session)
            return await get_cached_data('commodities', _fetch, CACHE_TTL_COMMODITIES)
        
        async def fetch_indices():
            async def _fetch():
                return await get_indices_data(session)
            return await get_cached_data('indices', _fetch, CACHE_TTL_INDICES)
        
        # Параллельный запрос всех данных
        cbr_data, forex_data, crypto_data, stocks_data, commodities_data, indices_data = await asyncio.gather(
            fetch_cbr(), fetch_forex(), fetch_crypto(), fetch_stocks(), fetch_commodities(), fetch_indices(),
            return_exceptions=True
        )
        
        # Обработка курсов валют ЦБ РФ
        try:
            if isinstance(cbr_data, Exception):
                raise cbr_data
            
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
            usd_to_rub_rate = 0
        
        # Обработка курса USD/RUB с FOREX
        try:
            if isinstance(forex_data, Exception):
                raise forex_data
            
            # Получаем курс USD/RUB с FOREX
            forex_usd_rub = forex_data.get('rates', {}).get('RUB', None)
            
            if forex_usd_rub and isinstance(forex_usd_rub, (int, float)):
                # Если ЦБ РФ недоступен, используем FOREX как основной источник
                if usd_to_rub_rate == 0:
                    usd_to_rub_rate = forex_usd_rub
                    usd_str = f"{format_price(forex_usd_rub)} ₽ (FOREX)"
                    logger.debug(f"Используем FOREX как основной источник: {forex_usd_rub:.2f} ₽")
                else:
                    # Вычисляем разницу с курсом ЦБ РФ
                    diff = forex_usd_rub - usd_to_rub_rate
                    diff_pct = (diff / usd_to_rub_rate) * 100
                    diff_str = f" (FOREX: {format_price(forex_usd_rub)} ₽, разница: {diff:+.2f} ₽, {diff_pct:+.2f}%)"
                    usd_str += diff_str
                    logger.debug(f"FOREX USD/RUB: {forex_usd_rub:.2f} ₽")
                
        except Exception as e:
            logger.error(f"Ошибка получения курса FOREX: {e}")
            if usd_to_rub_rate == 0:
                usd_to_rub_rate = 80  # Fallback значение
        
        # Обработка криптовалют
        if isinstance(crypto_data, Exception):
            logger.error(f"Ошибка получения криптовалют: {crypto_data}")
            crypto_data = {}
        
        # Форматируем криптовалютные цены (доллары + рубли)
        crypto_strings = {}
        crypto_list = [
            {'id': 'bitcoin', 'name': 'Bitcoin', 'decimals': 0},
            {'id': 'ethereum', 'name': 'Ethereum', 'decimals': 0},
            {'id': 'the-open-network', 'name': 'TON', 'decimals': 2},
            {'id': 'ripple', 'name': 'XRP', 'decimals': 3},
            {'id': 'cardano', 'name': 'Cardano', 'decimals': 3},
            {'id': 'solana', 'name': 'Solana', 'decimals': 2},
            {'id': 'dogecoin', 'name': 'Dogecoin', 'decimals': 3},
            {'id': 'tether', 'name': 'Tether', 'decimals': 2}
        ]
        
        for crypto in crypto_list:
            crypto_id = crypto['id']
            crypto_name = crypto['name']
            decimals = crypto['decimals']
            
            if crypto_id in crypto_data:
                price = crypto_data[crypto_id]['price']
                change_24h = crypto_data[crypto_id]['change_24h']
                source = crypto_data[crypto_id]['source']
                
                if isinstance(price, (int, float)) and usd_to_rub_rate > 0:
                    rub_price = price * usd_to_rub_rate
                    change_str = f" ({change_24h:+.2f}% за 24ч)" if change_24h != 0 else ""
                    source_str = f" [{source}]" if source != 'CoinGecko' else ""
                    crypto_strings[crypto_id] = f"{crypto_name}: ${format_price(price, decimals)} ({format_price(rub_price, decimals)} ₽){change_str}{source_str}"
                elif isinstance(price, (int, float)):
                    change_str = f" ({change_24h:+.2f}% за 24ч)" if change_24h != 0 else ""
                    source_str = f" [{source}]" if source != 'CoinGecko' else ""
                    crypto_strings[crypto_id] = f"{crypto_name}: ${format_price(price, decimals)}{change_str}{source_str}"
                else:
                    crypto_strings[crypto_id] = f"{crypto_name}: ❌ Н/Д"
            else:
                crypto_strings[crypto_id] = f"{crypto_name}: ❌ Н/Д"
        
        # Обработка акций
        if isinstance(stocks_data, Exception):
            logger.error(f"Ошибка получения акций: {stocks_data}")
            stocks_data = {}
        
        # Обработка товаров
        if isinstance(commodities_data, Exception):
            logger.error(f"Ошибка получения товаров: {commodities_data}")
            commodities_data = {}
        
        # Обработка индексов
        if isinstance(indices_data, Exception):
            logger.error(f"Ошибка получения индексов: {indices_data}")
            indices_data = {}
        
        # Форматируем криптовалютные цены (доллары + рубли)
        crypto_strings = {}
        crypto_list = [
            {'id': 'bitcoin', 'name': 'Bitcoin', 'decimals': 0},
            {'id': 'ethereum', 'name': 'Ethereum', 'decimals': 0},
            {'id': 'the-open-network', 'name': 'TON', 'decimals': 2},
            {'id': 'ripple', 'name': 'XRP', 'decimals': 3},
            {'id': 'cardano', 'name': 'Cardano', 'decimals': 3},
            {'id': 'solana', 'name': 'Solana', 'decimals': 2},
            {'id': 'dogecoin', 'name': 'Dogecoin', 'decimals': 3},
            {'id': 'tether', 'name': 'Tether', 'decimals': 2}
        ]
        
        for crypto in crypto_list:
            crypto_id = crypto['id']
            crypto_name = crypto['name']
            decimals = crypto['decimals']
            
            if crypto_id in crypto_data:
                price = crypto_data[crypto_id]['price']
                change_24h = crypto_data[crypto_id]['change_24h']
                source = crypto_data[crypto_id]['source']
                
                if isinstance(price, (int, float)) and usd_to_rub_rate > 0:
                    rub_price = price * usd_to_rub_rate
                    change_str = f" ({change_24h:+.2f}% за 24ч)" if change_24h != 0 else ""
                    source_str = f" [{source}]" if source != 'CoinGecko' else ""
                    crypto_strings[crypto_id] = f"{crypto_name}: ${format_price(price, decimals)} ({format_price(rub_price, decimals)} ₽){change_str}{source_str}"
                elif isinstance(price, (int, float)):
                    change_str = f" ({change_24h:+.2f}% за 24ч)" if change_24h != 0 else ""
                    source_str = f" [{source}]" if source != 'CoinGecko' else ""
                    crypto_strings[crypto_id] = f"{crypto_name}: ${format_price(price, decimals)}{change_str}{source_str}"
                else:
                    crypto_strings[crypto_id] = f"{crypto_name}: ❌ Н/Д"
            else:
                crypto_strings[crypto_id] = f"{crypto_name}: ❌ Н/Д"
        
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
        crypto_items = ['bitcoin', 'ethereum', 'the-open-network', 'ripple', 'cardano', 'solana', 'dogecoin', 'tether']
        for i, crypto_id in enumerate(crypto_items):
            crypto_key = crypto_id if crypto_id != 'the-open-network' else 'ton'
            if crypto_id in crypto_strings:
                prefix = "├" if i < len(crypto_items) - 1 else "└"
                message += f"{prefix} {crypto_strings[crypto_id]}\n"
        message += "\n"
        
        # Российские акции
        message += "📈 **РОССИЙСКИЕ АКЦИИ (MOEX):**\n"
        stock_names = {
            'SBER': 'Сбер', 'YDEX': 'Яндекс', 'VKCO': 'ВК', 
            'T': 'T-Технологии', 'GAZP': 'Газпром', 'GMKN': 'Норникель',
            'ROSN': 'Роснефть', 'LKOH': 'ЛУКОЙЛ', 'MTSS': 'МТС', 'MFON': 'Мегафон'
        }
        stock_items = list(stock_names.keys())
        
        # Проверяем, есть ли живые данные
        has_live_data = any(
            stocks_data.get(ticker, {}).get('price') is not None 
            for ticker in stock_items
        )
        
        if has_live_data:
            for i, ticker in enumerate(stock_items):
                if ticker in stocks_data and stocks_data[ticker].get('price'):
                    name = stock_names[ticker]
                    price = stocks_data[ticker]['price']
                    change_pct = stocks_data[ticker].get('change_pct', 0)
                    is_live = stocks_data[ticker].get('is_live', True)
                    status_icon = "🟢" if is_live else "🟡"
                    prefix = "├" if i < len(stock_items) - 1 else "└"
                    
                    # Добавляем изменение с открытия для российских акций
                    change_str = f" ({change_pct:+.2f}% с открытия)" if change_pct is not None and change_pct != 0 and is_live else ""
                    message += f"{prefix} {status_icon} {name}: **{format_price(price)} ₽**{change_str}\n"
        else:
            message += "🔴 **Торги закрыты** (выходной день)\n"
        message += "\n"
        
        # Недвижимость
        message += "🏠 **НЕДВИЖИМОСТЬ:**\n"
        real_estate_tickers = ['PIKK', 'SMLT']
        real_estate_names = {'PIKK': 'ПИК', 'SMLT': 'Самолёт'}
        
        has_real_estate_data = any(
            stocks_data.get(ticker, {}).get('price') is not None 
            for ticker in real_estate_tickers
        )
        
        if has_real_estate_data:
            for i, ticker in enumerate(real_estate_tickers):
                if ticker in stocks_data and stocks_data[ticker].get('price'):
                    name = real_estate_names[ticker]
                    price = stocks_data[ticker]['price']
                    change_pct = stocks_data[ticker].get('change_pct', 0)
                    is_live = stocks_data[ticker].get('is_live', True)
                    status_icon = "🟢" if is_live else "🟡"
                    prefix = "├" if i < len(real_estate_tickers) - 1 else "└"
                    
                    # Добавляем изменение с открытия для акций недвижимости
                    change_str = f" ({change_pct:+.2f}% с открытия)" if change_pct is not None and change_pct != 0 and is_live else ""
                    message += f"{prefix} {status_icon} {name}: **{format_price(price)} ₽**{change_str}\n"
        else:
            message += "🔴 **Торги закрыты** (выходной день)\n"
        message += "\n"
        
        # Товары 
        message += "🛠️ **ЗОЛОТО, НЕФТЬ:**\n"
        commodity_items = ['gold', 'silver', 'brent', 'urals']
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
        index_items = ['imoex', 'rts', 'sp500']
        
        for i, index in enumerate(index_items):
            if index in indices_data:
                name = indices_data[index]['name']
                price = indices_data[index]['price']
                change = indices_data[index].get('change_pct', 0)
                is_live = indices_data[index].get('is_live', True)
                note = indices_data[index].get('note', '')
                
                prefix = "├" if i < len(index_items) - 1 else "└"
                
                if price is not None:
                    # Определяем тип изменения для индекса
                    if index in ['imoex', 'rts']:
                        change_period = "с открытия" if is_live else "с закрытия"
                    elif index == 'sp500':
                        change_period = "с закрытия"
                    else:
                        change_period = ""
                    
                    change_str = f"({change:+.2f}% {change_period})" if change != 0 else ""
                    status_icon = "🟢" if is_live else "🟡"
                    note_str = f" ({note})" if note else ""
                    message += f"{prefix} {status_icon} {name}: **{format_price(price)}** {change_str}{note_str}\n"
                else:
                    message += f"{prefix} 🔴 {name}: **Торги закрыты**\n"
        message += "\n"
        
        # Время и источники
        current_time = get_moscow_time().strftime("%d.%m.%Y %H:%M")
        message += f"🕐 **Время:** {current_time}\n"
        message += f"📡 **Источники:** ЦБ РФ, CoinGecko/Coinbase/Binance/CryptoCompare, MOEX, Gold-API, Alpha Vantage"

        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Общая ошибка в rates_command: {e}")
        import traceback
        logger.error(f"Трассировка ошибки: {traceback.format_exc()}")
        await update.message.reply_text(
            f"❌ Ошибка получения курсов: {str(e)}\n\n"
            f"🔄 Попробуйте позже или обратитесь к администратору."
        )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка всех остальных сообщений"""
    message_text = update.message.text
    user_id = update.effective_user.id
    
    # Обновляем активность пользователя
    if user_id in user_data:
        user_data[user_id]['last_activity'] = get_moscow_time().isoformat()
        save_user_data()
    
    # Если пользователь ввел только "/", показываем команды
    if message_text == "/":
        await command_suggestions(update, context)
        return
    
    # Для других сообщений - стандартная обработка
    await update.message.reply_text(
        "🤖 Я не понимаю эту команду. Используйте /help для списка доступных команд."
    )

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подписаться на уведомления о резких изменениях курсов"""
    user_id = update.effective_user.id
    notifications = load_notification_data()
    
    if str(user_id) not in notifications:
        notifications[str(user_id)] = {
            'subscribed': True,
            'threshold': DEFAULT_THRESHOLD,  # 2% по умолчанию
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
            "• Криптовалюты: BTC, ETH, TON, XRP, ADA, SOL, DOGE, USDT\n"
            "• Акции: SBER, YDEX, VKCO, T, GAZP, GMKN, ROSN, LKOH, MTSS, MFON, PIKK, SMLT"
        )
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Укажите актив и пороговое значение")
        return
    
    asset = escape_html(context.args[0].upper())
    
    # Валидация актива
    if not validate_asset(asset):
        await update.message.reply_html(
            f"❌ <b>Неподпираемый актив:</b> {asset}\n\n"
            f"💡 Поддерживаемые активы:\n"
            f"• Валюты: {', '.join(SUPPORTED_CURRENCIES)}\n"
            f"• Криптовалюты: {', '.join(SUPPORTED_CRYPTO)}\n"
            f"• Акции: {', '.join(SUPPORTED_STOCKS)}"
        )
        return
    
    # Валидация порогового значения
    try:
        threshold = validate_positive_number(context.args[1])
    except ValueError as e:
        await update.message.reply_text(f"❌ {str(e)}")
        return
    
    notifications = load_notification_data()
    if str(user_id) not in notifications:
        notifications[str(user_id)] = {
            'subscribed': True,
            'threshold': DEFAULT_THRESHOLD,
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
    if not is_admin(user_id):
        await update.message.reply_text("🚫 Команда доступна только администратору")
        return
    
    await update.message.reply_text("🧪 Запускаю тестовую ежедневную сводку...")
    
    try:
        # Добавляем тестового подписчика если нет подписчиков
        notifications = load_notification_data()
        if not notifications:
            logger.info("📝 Создаю тестового подписчика для проверки...")
            notifications[str(user_id)] = {
                'subscribed': True,
                'daily_summary': True,
                'price_alerts': True,
                'alerts': {}
            }
            save_notification_data(notifications)
            await update.message.reply_text("✅ Добавлен тестовый подписчик")
        
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
    if not is_admin(user_id):
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
    """Получить данные по индексам: IMOEX, RTS, S&P 500 с учетом торговых дней"""
    indices_data = {}
    
    # Проверяем, является ли сегодня торговым днем
    from datetime import datetime
    moscow_tz = pytz.timezone('Europe/Moscow')
    current_moscow = datetime.now(moscow_tz)
    is_weekend = current_moscow.weekday() >= 5  # 5=суббота, 6=воскресенье
    
    logger.info(f"📅 Текущее время МСК: {current_moscow.strftime('%H:%M:%S %d.%m.%Y')}")
    logger.info(f"📅 Выходной день: {'Да' if is_weekend else 'Нет'}")
    
    try:
        # 1. Российские индексы через MOEX (только в торговые дни)
        if not is_weekend:
            logger.info("📊 Запрашиваю российские индексы с MOEX (торговый день)...")
            async with aiohttp.ClientSession() as session:
                # IMOEX
                imoex_url = "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json"
                logger.info(f"📈 Запрашиваю IMOEX: {imoex_url}")
                async with session.get(imoex_url) as resp:
                    logger.info(f"📊 IMOEX статус: {resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if 'marketdata' in data and 'data' in data['marketdata'] and len(data['marketdata']['data']) > 0:
                            row_data = dict(zip(data['marketdata']['columns'], data['marketdata']['data'][0]))
                            
                            if 'LASTVALUE' in row_data and row_data['LASTVALUE']:
                                # Проверяем время последнего обновления
                                update_time = row_data.get('UPDATETIME', '')
                                logger.info(f"📊 IMOEX время обновления: {update_time}")
                                
                                indices_data['imoex'] = {
                                    'name': 'IMOEX',
                                    'price': row_data.get('CURRENTVALUE', row_data['LASTVALUE']),
                                    'change_pct': row_data.get('LASTCHANGETOOPENPRC', row_data.get('LASTCHANGEPRC', 0)),
                                    'update_time': update_time,
                                    'is_live': True
                                }
                                logger.info(f"✅ IMOEX получен: {row_data['LASTVALUE']}")
                            else:
                                logger.warning(f"❌ IMOEX: нет LASTVALUE или LASTVALUE пустой")
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
                        
                        if 'marketdata' in data and 'data' in data['marketdata'] and len(data['marketdata']['data']) > 0:
                            row_data = dict(zip(data['marketdata']['columns'], data['marketdata']['data'][0]))
                            
                            if 'LASTVALUE' in row_data and row_data['LASTVALUE']:
                                update_time = row_data.get('UPDATETIME', '')
                                logger.info(f"📊 RTS время обновления: {update_time}")
                                
                                indices_data['rts'] = {
                                    'name': 'RTS',
                                    'price': row_data.get('CURRENTVALUE', row_data['LASTVALUE']),
                                    'change_pct': row_data.get('LASTCHANGETOOPENPRC', row_data.get('LASTCHANGEPRC', 0)),
                                    'update_time': update_time,
                                    'is_live': True
                                }
                                logger.info(f"✅ RTS получен: {row_data['LASTVALUE']}")
                            else:
                                logger.warning(f"❌ RTS: нет LASTVALUE или LASTVALUE пустой")
                        else:
                            logger.warning("❌ RTS: нет marketdata или данных")
                    else:
                        response_text = await resp.text() 
                        logger.error(f"❌ RTS ошибка {resp.status}: {response_text[:200]}...")
        else:
            logger.info("📅 Выходной день - запрашиваю последние известные значения российских индексов")
            # Пытаемся получить последние известные значения даже в выходные
            async with aiohttp.ClientSession() as session:
                # IMOEX - последнее известное значение
                imoex_url = "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json"
                logger.info(f"📈 Запрашиваю последнее значение IMOEX: {imoex_url}")
                async with session.get(imoex_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if 'marketdata' in data and 'data' in data['marketdata'] and len(data['marketdata']['data']) > 0:
                            row_data = dict(zip(data['marketdata']['columns'], data['marketdata']['data'][0]))
                            
                            # Используем CURRENTVALUE, LASTVALUE или PREVPRICE для последнего известного значения
                            last_value = row_data.get('CURRENTVALUE') or row_data.get('LASTVALUE') or row_data.get('PREVPRICE')
                            if last_value:
                                indices_data['imoex'] = {
                                    'name': 'IMOEX',
                                    'price': last_value,
                                    'change_pct': row_data.get('LASTCHANGETOOPENPRC', row_data.get('LASTCHANGEPRC', 0)),
                                    'update_time': row_data.get('UPDATETIME', ''),
                                    'is_live': False,
                                    'note': 'Последнее известное значение (торги закрыты)'
                                }
                                logger.info(f"✅ IMOEX последнее значение: {last_value}")
                            else:
                                indices_data['imoex'] = {
                                    'name': 'IMOEX',
                                    'price': None,
                                    'change_pct': 0,
                                    'is_live': False,
                                    'note': 'Данные недоступны'
                                }
                        else:
                            indices_data['imoex'] = {
                                'name': 'IMOEX',
                                'price': None,
                                'change_pct': 0,
                                'is_live': False,
                                'note': 'Данные недоступны'
                            }
                    else:
                        indices_data['imoex'] = {
                            'name': 'IMOEX',
                            'price': None,
                            'change_pct': 0,
                            'is_live': False,
                            'note': 'Ошибка получения данных'
                        }
                
                # RTS - последнее известное значение
                rts_url = "https://iss.moex.com/iss/engines/stock/markets/index/securities/RTSI.json"
                logger.info(f"📈 Запрашиваю последнее значение RTS: {rts_url}")
                async with session.get(rts_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if 'marketdata' in data and 'data' in data['marketdata'] and len(data['marketdata']['data']) > 0:
                            row_data = dict(zip(data['marketdata']['columns'], data['marketdata']['data'][0]))
                            
                            # Используем CURRENTVALUE, LASTVALUE или PREVPRICE для последнего известного значения
                            last_value = row_data.get('CURRENTVALUE') or row_data.get('LASTVALUE') or row_data.get('PREVPRICE')
                            if last_value:
                                indices_data['rts'] = {
                                    'name': 'RTS',
                                    'price': last_value,
                                    'change_pct': row_data.get('LASTCHANGETOOPENPRC', row_data.get('LASTCHANGEPRC', 0)),
                                    'update_time': row_data.get('UPDATETIME', ''),
                                    'is_live': False,
                                    'note': 'Последнее известное значение (торги закрыты)'
                                }
                                logger.info(f"✅ RTS последнее значение: {last_value}")
                            else:
                                indices_data['rts'] = {
                                    'name': 'RTS',
                                    'price': None,
                                    'change_pct': 0,
                                    'is_live': False,
                                    'note': 'Данные недоступны'
                                }
                        else:
                            indices_data['rts'] = {
                                'name': 'RTS',
                                'price': None,
                                'change_pct': 0,
                                'is_live': False,
                                'note': 'Данные недоступны'
                            }
                    else:
                        indices_data['rts'] = {
                            'name': 'RTS',
                            'price': None,
                            'change_pct': 0,
                            'is_live': False,
                            'note': 'Ошибка получения данных'
                        }
        
        # 2. S&P 500 через Financial Modeling Prep (работает 24/7)
        logger.info(f"📈 Запрашиваю S&P 500 с FMP, ключ: {FMP_API_KEY[:10]}...")
        sp500_response = requests.get(
            f"https://financialmodelingprep.com/api/v3/quote/%5EGSPC?apikey={FMP_API_KEY}",
            timeout=10
        )
        logger.info(f"📊 FMP статус: {sp500_response.status_code}")
        
        if sp500_response.status_code == 200:
            sp500_data = sp500_response.json()
            
            if isinstance(sp500_data, list) and len(sp500_data) > 0:
                sp500_info = sp500_data[0]
                if 'price' in sp500_info:
                    indices_data['sp500'] = {
                        'name': 'S&P 500',
                        'price': sp500_info['price'],
                        'change_pct': sp500_info.get('changesPercentage', 0),
                        'is_live': True
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
                    
                    if 'Global Quote' in alpha_data:
                        quote = alpha_data['Global Quote']
                        if '05. price' in quote:
                            price = float(quote['05. price'])
                            change_pct = float(quote['10. change percent'].replace('%', ''))
                            indices_data['sp500'] = {
                                'name': 'S&P 500 (SPY)',
                                'price': price,
                                'change_pct': change_pct,
                                'is_live': True
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
                    
        # Fallback: если S&P 500 не получен, логируем предупреждение
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
        session = get_http_session()
        current_prices = {}
        
        # Получаем данные параллельно с кэшированием
        async def fetch_cbr():
            try:
                async def _fetch_cbr():
                    return await get_cbr_rates(session)
                cbr_data = await get_cached_data('cbr_rates_check', _fetch_cbr, CACHE_TTL_CURRENCIES)
                return {
                    'USD': cbr_data.get('Valute', {}).get('USD', {}).get('Value'),
                    'EUR': cbr_data.get('Valute', {}).get('EUR', {}).get('Value'),
                    'CNY': cbr_data.get('Valute', {}).get('CNY', {}).get('Value'),
                    'GBP': cbr_data.get('Valute', {}).get('GBP', {}).get('Value')
                }
            except Exception as e:
                logger.error(f"Ошибка получения курсов валют для проверки: {e}")
                return {}
        
        async def fetch_crypto():
            try:
                async def _fetch_crypto():
                    return await get_crypto_data(session)
                crypto_data = await get_cached_data('crypto_data_check', _fetch_crypto, CACHE_TTL_CRYPTO)
                crypto_mapping = {
                    'bitcoin': 'BTC',
                    'ethereum': 'ETH', 
                    'the-open-network': 'TON',
                    'ripple': 'XRP',
                    'cardano': 'ADA',
                    'solana': 'SOL',
                    'dogecoin': 'DOGE',
                    'tether': 'USDT'
                }
                result = {}
                for crypto_id, price_data in crypto_data.items():
                    if crypto_id in crypto_mapping:
                        symbol = crypto_mapping[crypto_id]
                        result[symbol] = price_data['price']
                return result
            except Exception as e:
                logger.error(f"Ошибка получения криптовалют для проверки: {e}")
                return {}
        
        async def fetch_stocks():
            try:
                async def _fetch_stocks():
                    return await get_moex_stocks(session)
                moex_data = await get_cached_data('moex_stocks_check', _fetch_stocks, CACHE_TTL_STOCKS)
                result = {}
                for ticker, data in moex_data.items():
                    result[ticker] = data.get('price')
                return result
            except Exception as e:
                logger.error(f"Ошибка получения акций для проверки: {e}")
                return {}
        
        # Параллельный запрос данных
        currencies, crypto, stocks = await asyncio.gather(
            fetch_cbr(), fetch_crypto(), fetch_stocks(),
            return_exceptions=True
        )
        
        if not isinstance(currencies, Exception):
            current_prices.update(currencies)
        if not isinstance(crypto, Exception):
            current_prices.update(crypto)
        if not isinstance(stocks, Exception):
            current_prices.update(stocks)
        
        # Загружаем предыдущие цены
        price_history = load_price_history()
        notifications = load_notification_data()
        
        # Проверяем изменения и отправляем уведомления
        for user_id, user_notifications in notifications.items():
            if not user_notifications.get('subscribed', False):
                continue
            
            threshold = user_notifications.get('threshold', DEFAULT_THRESHOLD)
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
                    asset_name = escape_html(str(asset))
                    notifications_to_send.append(
                        f"{emoji} <b>{asset_name}</b>: {change_pct:+.2f}% за 30 мин "
                        f"({previous_price:.2f} → {current_price:.2f})"
                    )
            
            # Проверяем пороговые алерты
            for asset, alert_threshold in alerts.items():
                current_price = current_prices.get(asset)
                if current_price is None:
                    continue
                
                if current_price >= alert_threshold:
                    asset_name = escape_html(str(asset))
                    notifications_to_send.append(
                        f"🚨 <b>АЛЕРТ:</b> {asset_name} достиг {current_price:.2f} "
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
    if not is_admin(user_id):
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
    if not is_admin(user_id):
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
    if not is_admin(user_id):
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

def initialize_data_files():
    """Инициализировать файлы данных при первом запуске"""
    logger.info("🔧 Инициализация файлов данных...")
    
    # Инициализация настроек
    if not os.path.exists(SETTINGS_FILE):
        default_settings = {
            'daily_summary_time': '09:00',
            'timezone': 'Europe/Moscow'
        }
        save_bot_settings(default_settings)
        logger.info(f"✅ Создан файл настроек: {SETTINGS_FILE}")
    
    # Инициализация уведомлений
    if not os.path.exists(NOTIFICATION_DATA_FILE):
        default_notifications = {}
        save_notification_data(default_notifications)
        logger.info(f"✅ Создан файл уведомлений: {NOTIFICATION_DATA_FILE}")
    
    # Инициализация истории цен
    if not os.path.exists(PRICE_HISTORY_FILE):
        default_history = {}
        save_price_history(default_history)
        logger.info(f"✅ Создан файл истории цен: {PRICE_HISTORY_FILE}")
    
    logger.info("🎉 Инициализация файлов данных завершена")

def main() -> None:
    """Запуск бота - продвинутая версия с уведомлениями"""
    global GLOBAL_JOB_QUEUE
    
    logger.info("🚀 Запуск продвинутого финансового бота...")
    
    # Инициализируем файлы данных при первом запуске
    initialize_data_files()
    
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
    
    # Новые команды
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("export_pdf", export_pdf_command))
    application.add_handler(CommandHandler("webadmin", web_admin_command))
    
    # Обработчик callback-запросов для меню настроек
    application.add_handler(CallbackQueryHandler(button_callback))

    # Обработчик всех текстовых сообщений (эхо)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    # Настройка команд для автодополнения
    setup_bot_commands(application)

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
    logger.info("✅ Бот-финансист запущен и готов к работе")
    logger.info("📊 Доступные функции: курсы валют, криптовалют, акций, товаров, индексов")
    logger.info("🔔 Уведомления: резкие изменения, пороговые алерты, ежедневная сводка")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Меню настроек бота"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if not is_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только администратору.")
        return
    
    # Загружаем текущие настройки
    settings = load_bot_settings()
    notifications = load_notification_data()
    user_notifications = notifications.get(str(user_id), {})
    
    # Создаем клавиатуру с настройками
    keyboard = [
        [InlineKeyboardButton("⏰ Время сводки", callback_data="settings_time")],
        [InlineKeyboardButton("⭐ Избранные активы", callback_data="settings_favorites")],
        [InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications")],
        [InlineKeyboardButton("📊 Персональные настройки", callback_data="settings_personal")],
        [InlineKeyboardButton("📋 Текущие настройки", callback_data="settings_current")],
        [InlineKeyboardButton("🌐 Веб-панель", url="https://telegram-bot-admin-web-production.up.railway.app")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="settings_close")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем сообщение с текущими настройками
    current_time = settings.get('daily_summary_time', '09:00')
    timezone = settings.get('timezone', 'Europe/Moscow')
    is_subscribed = user_notifications.get('subscribed', False)
    threshold = user_notifications.get('threshold', 2.0)
    
    message = f"""
⚙️ **МЕНЮ НАСТРОЕК**

⏰ **Время ежедневной сводки:** {current_time} ({timezone})
🔔 **Подписка на уведомления:** {'✅ Включена' if is_subscribed else '❌ Отключена'}
📊 **Порог уведомлений:** {threshold}%

Выберите раздел для настройки:
"""
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки меню"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Обработка кнопок для всех пользователей
    if query.data == "rates":
        await rates_command(update, context)
        return
    elif query.data == "subscribe":
        await subscribe_command(update, context)
        return
    
    # Проверяем права администратора для админских функций
    if str(user_id) != os.getenv('ADMIN_USER_ID'):
        await query.edit_message_text("❌ Эта функция доступна только администратору.")
        return
    
    if query.data == "settings_close":
        await query.edit_message_text("✅ Меню настроек закрыто")
        return
    
    elif query.data == "settings_current":
        # Показываем текущие настройки
        settings = load_bot_settings()
        notifications = load_notification_data()
        user_notifications = notifications.get(str(user_id), {})
        
        current_time = settings.get('daily_summary_time', '09:00')
        timezone = settings.get('timezone', 'Europe/Moscow')
        is_subscribed = user_notifications.get('subscribed', False)
        threshold = user_notifications.get('threshold', 2.0)
        daily_summary = user_notifications.get('daily_summary', True)
        
        message = f"""
📋 **ТЕКУЩИЕ НАСТРОЙКИ**

⏰ **Время ежедневной сводки:** {current_time} ({timezone})
🔔 **Подписка на уведомления:** {'✅ Включена' if is_subscribed else '❌ Отключена'}
📊 **Порог уведомлений:** {threshold}%
📅 **Ежедневная сводка:** {'✅ Включена' if daily_summary else '❌ Отключена'}

Используйте /settings для изменения настроек
"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "settings_back":
        # Возвращаемся в главное меню настроек
        user_id = update.effective_user.id
        
        # Загружаем текущие настройки
        settings = load_bot_settings()
        notifications = load_notification_data()
        user_notifications = notifications.get(str(user_id), {})
        
        # Создаем клавиатуру с настройками
        keyboard = [
            [InlineKeyboardButton("⏰ Время сводки", callback_data="settings_time")],
            [InlineKeyboardButton("⭐ Избранные активы", callback_data="settings_favorites")],
            [InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications")],
            [InlineKeyboardButton("📊 Персональные настройки", callback_data="settings_personal")],
            [InlineKeyboardButton("📋 Текущие настройки", callback_data="settings_current")],
            [InlineKeyboardButton("🌐 Веб-панель", url="https://telegram-bot-admin-web-production.up.railway.app")],
            [InlineKeyboardButton("❌ Закрыть", callback_data="settings_close")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Формируем сообщение с текущими настройками
        current_time = settings.get('daily_summary_time', '09:00')
        timezone = settings.get('timezone', 'Europe/Moscow')
        is_subscribed = user_notifications.get('subscribed', False)
        threshold = user_notifications.get('threshold', 2.0)
        
        message = f"""
⚙️ **МЕНЮ НАСТРОЕК**

⏰ **Время ежедневной сводки:** {current_time} ({timezone})
🔔 **Подписка на уведомления:** {'✅ Включена' if is_subscribed else '❌ Отключена'}
📊 **Порог уведомлений:** {threshold}%

Выберите раздел для настройки:
"""
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "settings_time":
        message = """
⏰ **НАСТРОЙКА ВРЕМЕНИ СВОДКИ**

Используйте команду:
`/set_daily_time HH:MM`

Например:
• `/set_daily_time 09:00` - в 9 утра
• `/set_daily_time 18:30` - в 6:30 вечера

⚠️ Время указывается по Москве (UTC+3)
"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "settings_notifications":
        message = """
🔔 **НАСТРОЙКА УВЕДОМЛЕНИЙ**

Команды для управления:
• `/subscribe` - подписаться на уведомления
• `/unsubscribe` - отписаться от уведомлений
• `/set_alert АКТИВ ЦЕНА` - установить алерт

Примеры алертов:
• `/set_alert USD 85` - доллар выше 85₽
• `/set_alert BTC 115000` - биткоин ниже 115K$
• `/set_alert SBER 200` - Сбер выше 200₽
"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "settings_favorites":
        message = """
⭐ **ИЗБРАННЫЕ АКТИВЫ**

Эта функция находится в разработке.

Планируется:
• Сохранение любимых активов
• Быстрый доступ к избранному
• Персональные дашборды
"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "settings_personal":
        message = """
📊 **ПЕРСОНАЛЬНЫЕ НАСТРОЙКИ**

Эта функция находится в разработке.

Планируется:
• Выбор предпочитаемых валют
• Настройка отображения данных
• Персональные портфели
• Языковые настройки
"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def export_pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Экспорт данных в PDF отчет"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if not is_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только администратору.")
        return
    
    # Проверяем доступность reportlab
    if not REPORTLAB_AVAILABLE:
        await update.message.reply_text(
            "❌ Функция экспорта PDF недоступна.\n\n"
            "Причина: библиотека reportlab не установлена.\n\n"
            "Для установки выполните:\n"
            "`pip install reportlab`"
        )
        return
    
    await update.message.reply_text("📊 Создаю красивый PDF отчет...")
    
    try:
        # Создаем PDF в памяти
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []
        
        # Создаем стили с поддержкой русского языка
        styles = getSampleStyleSheet()
        
        # Стиль для заголовка
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=20,
            alignment=1,  # Центр
            textColor=colors.darkblue,
            fontName='Helvetica-Bold',
            encoding='utf-8'
        )
        
        # Стиль для подзаголовков
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            spaceAfter=10,
            spaceBefore=15,
            textColor=colors.darkgreen,
            fontName='Helvetica-Bold',
            encoding='utf-8'
        )
        
        # Стиль для обычного текста
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=9,
            spaceAfter=5,
            fontName='Helvetica',
            encoding='utf-8'
        )
        
        # Стиль для информации
        info_style = ParagraphStyle(
            'CustomInfo',
            parent=styles['Normal'],
            fontSize=8,
            spaceAfter=3,
            textColor=colors.grey,
            fontName='Helvetica',
            encoding='utf-8'
        )
        
        # Заголовок отчета
        current_time = get_moscow_time().strftime("%d.%m.%Y %H:%M")
        title = Paragraph(f"<b>FINANCIAL REPORT</b><br/>from {current_time}", title_style)
        story.append(title)
        
        # Информация о боте
        bot_info = Paragraph(
            "Financial Bot - current data on currencies, cryptocurrencies, stocks and indices", 
            info_style
        )
        story.append(bot_info)
        story.append(Spacer(1, 20))
        
        # Получаем данные
        await update.message.reply_text("📡 Получаю актуальные данные...")
        
        # Валюты
        try:
            cbr_response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
            cbr_data = cbr_response.json()
            usd_rate = cbr_data.get('Valute', {}).get('USD', {}).get('Value', 0)
            eur_rate = cbr_data.get('Valute', {}).get('EUR', {}).get('Value', 0)
            cny_rate = cbr_data.get('Valute', {}).get('CNY', {}).get('Value', 0)
            gbp_rate = cbr_data.get('Valute', {}).get('GBP', {}).get('Value', 0)
        except:
            usd_rate = eur_rate = cny_rate = gbp_rate = 0
        
        # FOREX курс
        try:
            forex_response = requests.get(
                "https://api.exchangerate-api.com/v4/latest/USD",
                timeout=10
            )
            forex_data = forex_response.json()
            forex_usd_rub = forex_data.get('rates', {}).get('RUB', None)
        except:
            forex_usd_rub = None
        
        # Криптовалюты с резервными источниками
        crypto_data = await get_crypto_data_with_fallback()
        
        # Индексы
        try:
            indices_data = await get_indices_data()
        except:
            indices_data = {}
        
        # Акции
        try:
            stocks_data = await get_moex_stocks()
        except:
            stocks_data = {}
        
        # Товары
        try:
            commodities_data = await get_commodities_data()
        except:
            commodities_data = {}
        
        # Создаем разделы отчета
        
        # 1. КУРСЫ ВАЛЮТ
        currencies_heading = Paragraph("<b>CURRENCY RATES</b>", heading_style)
        story.append(currencies_heading)
        
        currency_data = [
            ['Currency', 'Rate (RUB)', 'Source', 'Status']
        ]
        
        # Добавляем валюты
        currencies = [
            ('USD', usd_rate, 'CBR'),
            ('EUR', eur_rate, 'CBR'),
            ('CNY', cny_rate, 'CBR'),
            ('GBP', gbp_rate, 'CBR')
        ]
        
        for currency, rate, source in currencies:
            if rate and rate > 0:
                status = "Active"
                if currency == 'USD' and forex_usd_rub:
                    diff = forex_usd_rub - rate
                    diff_pct = (diff / rate) * 100
                    status = f"FOREX: {forex_usd_rub:.2f}RUB ({diff:+.2f}, {diff_pct:+.2f}%)"
            else:
                status = "No data"
            
            currency_data.append([currency, f"{format_price(rate)}", source, status])
        
        currency_table = Table(currency_data, colWidths=[1.2*inch, 1.5*inch, 1.2*inch, 2.1*inch])
        currency_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(currency_table)
        story.append(Spacer(1, 15))
        
        # 2. КРИПТОВАЛЮТЫ
        crypto_heading = Paragraph("<b>CRYPTOCURRENCIES</b>", heading_style)
        story.append(crypto_heading)
        
        crypto_names = {
            'bitcoin': 'Bitcoin',
            'ethereum': 'Ethereum', 
            'the-open-network': 'TON',
            'ripple': 'XRP',
            'cardano': 'Cardano',
            'solana': 'Solana',
            'dogecoin': 'Dogecoin',
            'tether': 'Tether'
        }
        
        crypto_data = [['Cryptocurrency', 'Price (USD)', '24h Change', 'Status']]
        
        for crypto_id, crypto_name in crypto_names.items():
            if crypto_id in crypto_data:
                price = crypto_data[crypto_id].get('usd', 0)
                change = crypto_data[crypto_id].get('usd_24h_change', 0)
                
                if price and price > 0:
                    change_str = f"{change:+.2f}%" if change is not None else "N/A"
                    if change and change > 0:
                        status = "Up"
                    elif change and change < 0:
                        status = "Down"
                    else:
                        status = "No change"
                    
                    crypto_data.append([crypto_name, f"${format_price(price)}", change_str, status])
        
        if len(crypto_data) > 1:  # Есть данные
            crypto_table = Table(crypto_data, colWidths=[1.5*inch, 1.5*inch, 1.2*inch, 1.8*inch])
            crypto_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightgreen),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(crypto_table)
        else:
            no_data = Paragraph("Cryptocurrency data temporarily unavailable", normal_style)
            story.append(no_data)
        
        story.append(Spacer(1, 15))
        
        # 3. ФОНДОВЫЕ ИНДЕКСЫ
        if indices_data:
            indices_heading = Paragraph("<b>STOCK INDICES</b>", heading_style)
            story.append(indices_heading)
            
            indices_data_table = [['Index', 'Value', 'Change', 'Status']]
            
            for index_id, index_info in indices_data.items():
                name = index_info.get('name', index_id.upper())
                price = index_info.get('price', 0)
                change = index_info.get('change_pct', 0)
                is_live = index_info.get('is_live', True)
                
                if price and price > 0:
                    change_str = f"{change:+.2f}%" if change != 0 else "0.00%"
                    if is_live:
                        status = "Trading open"
                    else:
                        status = "Trading closed"
                    
                    indices_data_table.append([name, str(price), change_str, status])
            
            if len(indices_data_table) > 1:
                indices_table = Table(indices_data_table, colWidths=[1.5*inch, 1.5*inch, 1.2*inch, 1.8*inch])
                indices_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkred),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.lightcoral),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                story.append(indices_table)
        
        story.append(Spacer(1, 15))
        
        # 4. ДРАГОЦЕННЫЕ МЕТАЛЛЫ
        if commodities_data:
            metals_heading = Paragraph("<b>PRECIOUS METALS</b>", heading_style)
            story.append(metals_heading)
            
            metals_data = [['Metal', 'Price (USD)', 'Price (RUB)', 'Status']]
            
            metals = {
                'gold': ('Gold', 'XAU'),
                'silver': ('Silver', 'XAG')
            }
            
            for metal_id, (metal_name, symbol) in metals.items():
                if metal_id in commodities_data:
                    price_usd = commodities_data[metal_id]['price']
                    price_rub = price_usd * usd_rate if usd_rate > 0 else 0
                    
                    if price_usd and price_usd > 0:
                        metals_data.append([
                            metal_name,
                            f"${format_price(price_usd)}",
                            f"{format_price(price_rub)} RUB",
                            "Active"
                        ])
            
            if len(metals_data) > 1:
                metals_table = Table(metals_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
                metals_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkgoldenrod),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.lightyellow),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                story.append(metals_table)
        
        story.append(Spacer(1, 20))
        
        # 5. ИСТОЧНИКИ ДАННЫХ
        sources_heading = Paragraph("<b>DATA SOURCES</b>", heading_style)
        story.append(sources_heading)
        
        sources_data = [
            ['Source', 'Data', 'Status'],
            ['CBR', 'Currency rates', 'Active'],
            ['CoinGecko', 'Cryptocurrencies', 'Active'],
            ['MOEX', 'Russian indices and stocks', 'Active'],
            ['Gold-API', 'Precious metals', 'Active'],
            ['Alpha Vantage', 'International data', 'Demo key'],
            ['FOREX', 'Interbank rates', 'Active']
        ]
        
        sources_table = Table(sources_data, colWidths=[2*inch, 3*inch, 1*inch])
        sources_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(sources_table)
        
        story.append(Spacer(1, 20))
        
        # 6. ФУТЕР
        footer_text = f"""
        <b>Report generated:</b> {current_time}<br/>
        <b>Financial Bot</b> - your assistant in the world of finance<br/>
        <i>Data updates in real time</i>
        """
        footer = Paragraph(footer_text, info_style)
        story.append(footer)
        
        # Создаем PDF
        doc.build(story)
        buffer.seek(0)
        
        # Отправляем файл
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=buffer,
            filename=f"financial_report_{current_time.replace(' ', '_').replace(':', '-')}.pdf",
            caption="📊 Your beautiful financial report is ready! 🎨"
        )
        
        await update.message.reply_text("✅ Beautiful PDF report successfully created and sent!")
        
    except Exception as e:
        logger.error(f"Ошибка создания PDF: {e}")
        await update.message.reply_text(f"❌ Ошибка создания PDF: {str(e)}")

def setup_bot_commands(application):
    """Настройка команд бота для автодополнения в Telegram"""
    from telegram import BotCommand
    
    # Список команд для обычных пользователей
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("help", "Справка по командам"),
        BotCommand("rates", "Курсы валют и индексы"),
        BotCommand("ping", "Проверка работы бота"),
        BotCommand("subscribe", "Подписаться на уведомления"),
        BotCommand("unsubscribe", "Отписаться от уведомлений"),
        BotCommand("set_alert", "Установить алерт"),
        BotCommand("view_alerts", "Просмотр алертов"),
        BotCommand("settings", "Меню настроек"),
        BotCommand("export_pdf", "Экспорт в PDF")
    ]
    
    try:
        # Устанавливаем команды для бота
        application.bot.set_my_commands(commands)
        logger.info("✅ Команды бота настроены для автодополнения")
    except Exception as e:
        logger.error(f"❌ Ошибка настройки команд: {e}")

async def web_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для доступа к веб-панели"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if is_admin(user_id):
        web_url = os.getenv('WEB_APP_URL', 'https://telegram-bot-web-admin.railway.app')
        
        message = (
            "🌐 <b>Веб-панель администратора</b>\n\n"
            f"🔗 <a href='{web_url}'>Открыть веб-панель</a>\n\n"
            "📊 <b>Возможности:</b>\n"
            "• Управление пользователями\n"
            "• Настройки бота\n"
            "• Просмотр логов\n"
            "• Статистика в реальном времени\n\n"
            "⚠️ <i>Доступно только администраторам</i>"
        )
        
        await update.message.reply_text(message, parse_mode='HTML', disable_web_page_preview=True)
    else:
        await update.message.reply_text("❌ У вас нет прав для доступа к веб-панели.")

async def command_suggestions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывать доступные команды при вводе '/'"""
    user_input = update.message.text
    
    if user_input == "/":
        # Список всех доступных команд
        commands = [
            "/start - Запустить бота",
            "/help - Справка по командам",
            "/rates - Курсы валют и индексы",
            "/ping - Проверка работы бота",
            "/subscribe - Подписаться на уведомления",
            "/unsubscribe - Отписаться от уведомлений",
            "/set_alert - Установить алерт",
            "/view_alerts - Просмотр алертов",
            "/settings - Меню настроек",
            "/export_pdf - Экспорт в PDF"
        ]
        
        # Админские команды
        admin_commands = [
            "/set_daily_time - Установить время сводки",
            "/get_daily_settings - Настройки сводки",
            "/restart_daily_job - Перезапустить сводку",
            "/test_daily - Тест сводки",
            "/check_subscribers - Проверить подписчиков"
        ]
        
        message = "📋 **ДОСТУПНЫЕ КОМАНДЫ:**\n\n"
        
        for cmd in commands:
            message += f"• {cmd}\n"
        
        # Проверяем права администратора
        user_id = update.effective_user.id
        if str(user_id) == os.getenv('ADMIN_USER_ID'):
            message += "\n🔧 **КОМАНДЫ АДМИНИСТРАТОРА:**\n\n"
            for cmd in admin_commands:
                message += f"• {cmd}\n"
        
        message += "\n💡 **Совет:** Введите команду полностью для выполнения"
        
        await update.message.reply_text(message, parse_mode='Markdown')

# Flask сервер для API данных
def create_data_api():
    """Создает Flask сервер для API данных"""
    app = Flask(__name__)
    
    @app.route('/api/users')
    def get_users():
        """API для получения пользователей"""
        try:
            with open('notifications.json', 'r', encoding='utf-8') as f:
                users_data = json.load(f)
                return jsonify(users_data)
        except (FileNotFoundError, json.JSONDecodeError):
            return jsonify([])
    
    @app.route('/api/settings')
    def get_settings():
        """API для получения настроек"""
        try:
            with open('bot_settings.json', 'r', encoding='utf-8') as f:
                settings_data = json.load(f)
                return jsonify(settings_data)
        except (FileNotFoundError, json.JSONDecodeError):
            return jsonify({})
    
    @app.route('/api/status')
    def get_status():
        """API для получения статуса бота"""
        return jsonify({
            'status': 'running',
            'users_count': len(load_user_data()),
            'timestamp': datetime.now().isoformat()
        })
    
    return app

def start_data_api():
    """Запускает API сервер в отдельном потоке"""
    app = create_data_api()
    def run_api():
        app.run(host='0.0.0.0', port=5002, debug=False)
    
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    logger.info("🌐 API сервер запущен на порту 5002")

if __name__ == '__main__':
    # Запускаем API сервер
    start_data_api()
    main() 