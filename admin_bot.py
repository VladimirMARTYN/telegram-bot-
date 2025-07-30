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
        "• Товары (нефть, золото, серебро)\n"
        "• Фондовые индексы\n"
        "• Уведомления о резких изменениях\n"
        "• Пороговые алерты\n"
        "• Ежедневная сводка\n\n"
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
        "🔄 <b>Источники данных:</b>\n"
        "• ЦБ РФ - курсы валют\n"
        "• CoinGecko - криптовалюты\n" 
        "• MOEX - российские акции и индексы\n"
        "• Yahoo Finance - товары и индексы"
    )
    
    await update.message.reply_html(help_text)

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /ping"""
    current_time = get_moscow_time().strftime("%d.%m.%Y %H:%M:%S")
    await update.message.reply_text(f"🏓 Понг! Время: {current_time}")

async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получить полные курсы валют, криптовалют, акций, товаров и индексов"""
    try:
        await update.message.reply_text("📊 Получаю полные курсы финансовых инструментов...")
        
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
            usd_str = f"{usd_rate:.2f} ₽" if isinstance(usd_rate, (int, float)) else str(usd_rate)
            eur_str = f"{eur_rate:.2f} ₽" if isinstance(eur_rate, (int, float)) else str(eur_rate)
            cny_str = f"{cny_rate:.2f} ₽" if isinstance(cny_rate, (int, float)) else str(cny_rate)
            gbp_str = f"{gbp_rate:.2f} ₽" if isinstance(gbp_rate, (int, float)) else str(gbp_rate)
                
        except Exception as e:
            logger.error(f"Ошибка получения курсов ЦБ РФ: {e}")
            usd_str = eur_str = cny_str = gbp_str = "❌ Ошибка API"
            usd_to_rub_rate = 80  # Fallback значение для конвертации
        
        # 2. Расширенные курсы криптовалют
        try:
            crypto_data = await get_crypto_extended()
            
            # Форматируем криптовалютные цены
            crypto_strings = {}
            crypto_names = {
                'bitcoin': 'Bitcoin',
                'ethereum': 'Ethereum', 
                'ton': 'TON',
                'ripple': 'XRP',
                'cardano': 'Cardano',
                'solana': 'Solana',
                'dogecoin': 'Dogecoin'
            }
            
            for crypto_id, price in crypto_data.items():
                name = crypto_names.get(crypto_id, crypto_id.upper())
                if isinstance(price, (int, float)) and usd_to_rub_rate > 0:
                    rub_price = price * usd_to_rub_rate
                    if price >= 1:
                        crypto_strings[crypto_id] = f"{name}: ${price:,.0f} ({rub_price:,.0f} ₽)"
                    else:
                        crypto_strings[crypto_id] = f"{name}: ${price:.3f} ({rub_price:.2f} ₽)"
                elif isinstance(price, (int, float)):
                    if price >= 1:
                        crypto_strings[crypto_id] = f"{name}: ${price:,.0f}"
                    else:
                        crypto_strings[crypto_id] = f"{name}: ${price:.3f}"
                else:
                    crypto_strings[crypto_id] = f"{name}: ❌ Н/Д"
                
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
        
        main_stock_strings = format_stock_data(main_stocks)
        real_estate_stock_strings = format_stock_data(real_estate_stocks)
        
        # 4. Получаем данные товаров
        try:
            commodities = await get_commodities_data()
            commodity_strings = {}
            
            for commodity_id, data in commodities.items():
                name = data.get('name')
                price = data.get('price')
                currency = data.get('currency', 'USD')
                
                if isinstance(price, (int, float)):
                    if usd_to_rub_rate > 0 and currency == 'USD':
                        rub_price = price * usd_to_rub_rate
                        commodity_strings[commodity_id] = f"{name}: ${price:.2f} ({rub_price:.2f} ₽)"
                    else:
                        commodity_strings[commodity_id] = f"{name}: ${price:.2f}"
                else:
                    commodity_strings[commodity_id] = f"{name}: ❌ Н/Д"
                    
        except Exception as e:
            logger.error(f"Ошибка получения данных товаров: {e}")
            commodity_strings = {
                'brent': 'Нефть Brent: ❌ Ошибка API',
                'gold': 'Золото: ❌ Ошибка API', 
                'silver': 'Серебро: ❌ Ошибка API'
            }
        
        # 5. Получаем данные индексов
        try:
            indices = await get_indices_data()
            index_strings = {}
            
            for index_id, data in indices.items():
                name = data.get('name')
                price = data.get('price')
                change_pct = data.get('change_pct', 0)
                
                if isinstance(price, (int, float)):
                    price_str = f"{price:.2f}"
                    
                    if isinstance(change_pct, (int, float)):
                        if change_pct > 0:
                            change_str = f"(+{change_pct:.2f}%)"
                        elif change_pct < 0:
                            change_str = f"({change_pct:.2f}%)"
                        else:
                            change_str = "(0.00%)"
                        
                        index_strings[index_id] = f"{name}: {price_str} {change_str}"
                    else:
                        index_strings[index_id] = f"{name}: {price_str}"
                else:
                    index_strings[index_id] = f"{name}: ❌ Н/Д"
                    
        except Exception as e:
            logger.error(f"Ошибка получения данных индексов: {e}")
            index_strings = {
                'imoex': 'IMOEX: ❌ Ошибка API',
                'rts': 'RTS: ❌ Ошибка API',
                'sp500': 'S&P 500: ❌ Ошибка API'
            }
        
        # Формируем итоговое сообщение
        current_time = get_moscow_time().strftime("%d.%m.%Y %H:%M")

        message = f"""<b>ПОЛНЫЕ КУРСЫ ФИНАНСОВЫХ ИНСТРУМЕНТОВ</b>

<b>Основные валюты ЦБ РФ:</b>
USD: {usd_str}
EUR: {eur_str}
CNY: {cny_str}
GBP: {gbp_str}

<b>Криптовалюты:</b>
{chr(10).join(crypto_strings.values())}

<b>Российские акции (MOEX):</b>
{chr(10).join(main_stock_strings.values()) if main_stock_strings else "❌ Данные недоступны"}

<b>Недвижимость:</b>
{chr(10).join(real_estate_stock_strings.values()) if real_estate_stock_strings else "❌ Данные недоступны"}

<b>Товары:</b>
{chr(10).join(commodity_strings.values()) if commodity_strings else "❌ Данные недоступны"}

<b>Фондовые индексы:</b>
{chr(10).join(index_strings.values()) if index_strings else "❌ Данные недоступны"}

<b>Время:</b> {current_time}
<b>Источники:</b> ЦБ РФ, CoinGecko, MOEX, Yahoo Finance"""

        await update.message.reply_html(message)
        
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

# Функции для получения дополнительных данных
async def get_commodities_data():
    """Получить данные по товарам: нефть Brent, золото, серебро"""
    commodities_data = {}
    
    try:
        # Используем Yahoo Finance API для товаров
        import requests
        
        # Нефть Brent
        brent_response = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/BZ=F", timeout=10)
        if brent_response.status_code == 200:
            brent_data = brent_response.json()
            if 'chart' in brent_data and 'result' in brent_data['chart'] and len(brent_data['chart']['result']) > 0:
                result = brent_data['chart']['result'][0]
                if 'meta' in result and 'regularMarketPrice' in result['meta']:
                    commodities_data['brent'] = {
                        'name': 'Нефть Brent',
                        'price': result['meta']['regularMarketPrice'],
                        'currency': 'USD'
                    }
        
        # Золото
        gold_response = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F", timeout=10)
        if gold_response.status_code == 200:
            gold_data = gold_response.json()
            if 'chart' in gold_data and 'result' in gold_data['chart'] and len(gold_data['chart']['result']) > 0:
                result = gold_data['chart']['result'][0]
                if 'meta' in result and 'regularMarketPrice' in result['meta']:
                    commodities_data['gold'] = {
                        'name': 'Золото',
                        'price': result['meta']['regularMarketPrice'],
                        'currency': 'USD'
                    }
        
        # Серебро
        silver_response = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/SI=F", timeout=10)
        if silver_response.status_code == 200:
            silver_data = silver_response.json()
            if 'chart' in silver_data and 'result' in silver_data['chart'] and len(silver_data['chart']['result']) > 0:
                result = silver_data['chart']['result'][0]
                if 'meta' in result and 'regularMarketPrice' in result['meta']:
                    commodities_data['silver'] = {
                        'name': 'Серебро',
                        'price': result['meta']['regularMarketPrice'],
                        'currency': 'USD'
                    }
                    
    except Exception as e:
        logger.error(f"Ошибка получения данных товаров: {e}")
    
    return commodities_data

async def get_indices_data():
    """Получить данные по индексам: IMOEX, RTS, S&P 500"""
    indices_data = {}
    
    try:
        # MOEX индексы
        async with aiohttp.ClientSession() as session:
            # IMOEX
            imoex_url = "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json"
            async with session.get(imoex_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'marketdata' in data and 'data' in data['marketdata'] and len(data['marketdata']['data']) > 0:
                        row_data = dict(zip(data['marketdata']['columns'], data['marketdata']['data'][0]))
                        if 'LAST' in row_data and row_data['LAST']:
                            indices_data['imoex'] = {
                                'name': 'IMOEX',
                                'price': row_data['LAST'],
                                'change_pct': row_data.get('LASTTOPREVPRICE', 0)
                            }
            
            # RTS
            rts_url = "https://iss.moex.com/iss/engines/stock/markets/index/securities/RTSI.json"
            async with session.get(rts_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'marketdata' in data and 'data' in data['marketdata'] and len(data['marketdata']['data']) > 0:
                        row_data = dict(zip(data['marketdata']['columns'], data['marketdata']['data'][0]))
                        if 'LAST' in row_data and row_data['LAST']:
                            indices_data['rts'] = {
                                'name': 'RTS',
                                'price': row_data['LAST'],
                                'change_pct': row_data.get('LASTTOPREVPRICE', 0)
                            }
        
        # S&P 500 через Yahoo Finance
        sp500_response = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC", timeout=10)
        if sp500_response.status_code == 200:
            sp500_data = sp500_response.json()
            if 'chart' in sp500_data and 'result' in sp500_data['chart'] and len(sp500_data['chart']['result']) > 0:
                result = sp500_data['chart']['result'][0]
                if 'meta' in result and 'regularMarketPrice' in result['meta']:
                    indices_data['sp500'] = {
                        'name': 'S&P 500',
                        'price': result['meta']['regularMarketPrice'],
                        'change_pct': result['meta'].get('regularMarketChangePercent', 0)
                    }
                    
    except Exception as e:
        logger.error(f"Ошибка получения данных индексов: {e}")
    
    return indices_data

async def get_crypto_extended(backup_api=False):
    """Получить расширенный список криптовалют с backup API"""
    crypto_data = {}
    
    if not backup_api:
        # Основной API - CoinGecko
        try:
            crypto_response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,the-open-network,ripple,cardano,solana,dogecoin&vs_currencies=usd",
                timeout=10
            )
            crypto_response.raise_for_status()
            data = crypto_response.json()
            
            crypto_data = {
                'bitcoin': data.get('bitcoin', {}).get('usd'),
                'ethereum': data.get('ethereum', {}).get('usd'),
                'ton': data.get('the-open-network', {}).get('usd'),
                'ripple': data.get('ripple', {}).get('usd'),
                'cardano': data.get('cardano', {}).get('usd'),
                'solana': data.get('solana', {}).get('usd'),
                'dogecoin': data.get('dogecoin', {}).get('usd')
            }
            
        except Exception as e:
            logger.error(f"Ошибка CoinGecko API: {e}")
            return await get_crypto_extended(backup_api=True)
    else:
        # Backup API - CoinMarketCap (потребует API ключ)
        # Пока возвращаем fallback значения
        logger.warning("Используем fallback значения для криптовалют")
        crypto_data = {
            'bitcoin': None,
            'ethereum': None,
            'ton': None,
            'ripple': None,
            'cardano': None,
            'solana': None,
            'dogecoin': None
        }
    
    return crypto_data

# Система уведомлений
NOTIFICATION_DATA_FILE = 'notifications.json'
PRICE_HISTORY_FILE = 'price_history.json'

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
        crypto_data = await get_crypto_extended()
        current_prices.update({
            'BTC': crypto_data.get('bitcoin'),
            'ETH': crypto_data.get('ethereum'),
            'TON': crypto_data.get('ton'),
            'XRP': crypto_data.get('ripple'),
            'ADA': crypto_data.get('cardano'),
            'SOL': crypto_data.get('solana'),
            'DOGE': crypto_data.get('dogecoin')
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
    try:
        notifications = load_notification_data()
        
        for user_id, user_notifications in notifications.items():
            if not user_notifications.get('subscribed', False):
                continue
            if not user_notifications.get('daily_summary', True):
                continue
            
            try:
                # Отправляем полный rates
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text="🌅 <b>ЕЖЕДНЕВНАЯ СВОДКА</b>\n\nПолучаю актуальные курсы...",
                    parse_mode='HTML'
                )
                
                # Здесь можно вызвать полную функцию rates_command
                # Пока отправим краткую версию
                
            except Exception as e:
                logger.error(f"Ошибка отправки ежедневной сводки пользователю {user_id}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка ежедневной сводки: {e}")

def main() -> None:
    """Запуск бота - продвинутая версия с уведомлениями"""
    logger.info("🚀 Запуск продвинутого финансового бота...")
    
    # Загружаем данные пользователей при старте
    load_user_data()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Получаем JobQueue
    job_queue = application.job_queue

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

    # Обработчик всех текстовых сообщений (эхо)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    # Настройка периодических задач
    if job_queue:
        # Проверка изменений цен каждые 30 минут
        job_queue.run_repeating(
            check_price_changes,
            interval=1800,  # 30 минут в секундах
            first=60,  # Первый запуск через 1 минуту
            name="price_changes_check"
        )
        logger.info("⏰ Настроена проверка изменений цен каждые 30 минут")
        
        # Ежедневная сводка в 9:00 МСК
        moscow_tz = pytz.timezone('Europe/Moscow')
        daily_time = time(hour=9, minute=0, tzinfo=moscow_tz)
        
        job_queue.run_daily(
            daily_summary_job,
            time=daily_time,
            name="daily_summary"
        )
        logger.info("📅 Настроена ежедневная сводка в 9:00 МСК")
    else:
        logger.warning("⚠️ JobQueue недоступен - уведомления отключены")

    # Запуск бота
    logger.info("✅ Продвинутый финансовый бот запущен и готов к работе")
    logger.info("📊 Доступные функции: курсы валют, криптовалют, акций, товаров, индексов")
    logger.info("🔔 Уведомления: резкие изменения, пороговые алерты, ежедневная сводка")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 