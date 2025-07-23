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

# Файл для сохранения настроек бота
BOT_SETTINGS_FILE = "bot_settings.json"

# Словарь пользователей (будет загружен из файла)
user_data = {}

# Настройки бота (шаблоны сообщений и т.д.)
bot_settings = {
    'message_template': '📢 <b>Сообщение от администратора:</b>\n\n{message}'
}

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

def save_bot_settings():
    """Сохранение настроек бота в файл"""
    try:
        with open(BOT_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(bot_settings, f, ensure_ascii=False, indent=2)
        logger.info(f"⚙️ Настройки бота сохранены в {BOT_SETTINGS_FILE}")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения настроек: {e}")

def load_bot_settings():
    """Загрузка настроек бота из файла"""
    global bot_settings
    try:
        if os.path.exists(BOT_SETTINGS_FILE):
            with open(BOT_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                loaded_settings = json.load(f)
                bot_settings.update(loaded_settings)
                logger.info(f"⚙️ Настройки бота загружены из {BOT_SETTINGS_FILE}")
        else:
            logger.info(f"⚙️ Файл {BOT_SETTINGS_FILE} не найден, используем настройки по умолчанию")
            # Сохраняем настройки по умолчанию
            save_bot_settings()
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки настроек: {e}")
        # Используем настройки по умолчанию
        bot_settings = {
            'message_template': '📢 <b>Сообщение от администратора:</b>\n\n{message}'
        }

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
        welcome_text += f"/broadcast [текст] - Рассылка всем пользователям\n"
        welcome_text += f"/send_message [ID] [текст] - Личное сообщение\n"
        welcome_text += f"/fix_admin_id - Исправить права администратора\n"
        welcome_text += f"/users_info - Информация о пользователях\n"
        welcome_text += f"/add_user [ID] [имя] - Добавить пользователя\n"
        welcome_text += f"/remove_user [ID] - Удалить пользователя\n"
        welcome_text += f"/set_template [шаблон] - Настроить шаблон\n"
        welcome_text += f"/get_template - Просмотр шаблона\n"
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
        help_text += "/broadcast [текст] - Рассылка всем пользователям\n"
        help_text += "/send_message [ID] [текст] - Личное сообщение\n"
        help_text += "/fix_admin_id - Исправить права администратора\n"
        help_text += "/users_info - Информация о пользователях\n"
        help_text += "/add_user [ID] [имя] - Добавить пользователя\n"
        help_text += "/remove_user [ID] - Удалить пользователя\n"
        help_text += "/set_template [шаблон] - Настроить шаблон\n"
        help_text += "/get_template - Просмотр шаблона\n"
    elif ADMIN_USER_ID == 0:
        # Если ADMIN_USER_ID не настроен, показываем команду исправления всем
        help_text += "/fix_admin_id - Стать администратором (не настроен)\n"
    
    help_text += (
        "\n💱 <b>Функции:</b>\n"
        "• Курсы валют ЦБ РФ (USD, EUR, CNY)\n"
        "• Курсы криптовалют (Bitcoin, Ethereum, Dogecoin, TON)\n"
        "• Топ российских акций (Московская биржа)\n"
    )
    
    if is_admin:
        help_text += "• Массовая рассылка с настраиваемыми шаблонами (только админ)\n"
        help_text += "• Личные сообщения пользователям (только админ)\n"
        help_text += "• Управление базой пользователей (только админ)\n"
    
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
        f"/broadcast [текст] - Рассылка всем пользователям\n"
        f"/send_message [ID] [текст] - Личное сообщение пользователю\n"
        f"/fix_admin_id - Исправить права администратора\n"
        f"/users_info - Информация о пользователях бота\n"
        f"/add_user [ID] [имя] - Добавить пользователя вручную\n"
        f"/remove_user [ID] - Удалить пользователя из базы\n"
        f"/set_template [шаблон] - Настроить шаблон сообщений\n"
        f"/get_template - Просмотр текущего шаблона\n\n"
        
        f"💱 <b>Доступные функции:</b>\n"
        f"• Курсы валют ЦБ РФ (USD, EUR, CNY)\n"
        f"• Курсы криптовалют (BTC, ETH, DOGE, TON)\n"
        f"• Топ российских акций (Московская биржа)\n"
        f"• Массовая рассылка сообщений\n"
        f"• Личные сообщения пользователям\n"
        f"• Управление базой пользователей\n"
        f"• Настраиваемые шаблоны сообщений\n\n"
        
        f"👥 <b>База пользователей:</b>\n"
        f"• Всего пользователей: {len(user_data)}\n"
        f"• Добавлено через /start: {sum(1 for u in user_data.values() if not u.get('added_by_admin'))}\n"
        f"• Добавлено админом: {sum(1 for u in user_data.values() if u.get('added_by_admin'))}\n\n"
        
        f"📢 <b>Система сообщений:</b>\n"
        f"👥 Получателей для рассылки: {len(user_data)}\n"
        f"📋 Текущий шаблон: <code>{bot_settings.get('message_template', 'не установлен')[:50]}{'...' if len(bot_settings.get('message_template', '')) > 50 else ''}</code>\n"
        f"💡 Используй: <code>/broadcast Текст</code> или <code>/send_message ID Текст</code>\n\n"
        
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

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Массовая рассылка сообщений всем пользователям (только админ)"""
    user_id = update.effective_user.id
    
    # ВРЕМЕННАЯ ОТЛАДКА - покажем реальные значения
    debug_info = (
        f"🐛 <b>ОТЛАДОЧНАЯ ИНФОРМАЦИЯ:</b>\n"
        f"• Ваш ID: <code>{user_id}</code>\n"
        f"• ADMIN_USER_ID: <code>{ADMIN_USER_ID}</code>\n"
        f"• Совпадают: {'✅ Да' if user_id == ADMIN_USER_ID else '❌ Нет'}\n\n"
    )
    
    # Если ADMIN_USER_ID = 0, показываем инструкцию по настройке
    if ADMIN_USER_ID == 0:
        await update.message.reply_html(
            debug_info +
            f"⚠️ <b>ПРОБЛЕМА НАСТРОЙКИ!</b>\n\n"
            f"🔧 <b>ADMIN_USER_ID не установлен!</b>\n"
            f"• Текущее значение: {ADMIN_USER_ID} (неправильно)\n"
            f"• Ваш ID: {user_id}\n\n"
            f"🛠️ <b>Для исправления:</b>\n"
            f"1. Установить переменную окружения ADMIN_USER_ID = {user_id}\n"
            f"2. Или я могу временно использовать ваш ID\n\n"
            f"💡 Используйте: /fix_admin_id чтобы исправить"
        )
        return
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_html(
            debug_info +
            f"❌ <b>Доступ запрещен!</b>\n"
            f"Только администратор может использовать эту команду.\n\n"
            f"💡 Если это ошибка, используйте: /fix_admin_id"
        )
        return
    
    # Проверяем наличие текста для рассылки
    if not context.args:
        await update.message.reply_html(
            "📢 <b>МАССОВАЯ РАССЫЛКА</b>\n\n"
            "🔍 <b>Использование:</b>\n"
            "<code>/broadcast [сообщение]</code>\n\n"
            "💡 <b>Примеры:</b>\n"
            "• <code>/broadcast Привет всем!</code>\n"
            "• <code>/broadcast 🎉 Новое обновление бота!</code>\n"
            "• <code>/broadcast Техническое обслуживание с 15:00 до 16:00</code>\n\n"
            "📊 <b>Статистика:</b>\n"
            f"👥 Пользователей для рассылки: <b>{len(user_data)}</b>\n\n"
            "⚠️ <b>Внимание:</b> Сообщение будет отправлено ВСЕМ пользователям бота!"
        )
        return
    
    # Получаем текст сообщения
    broadcast_text = " ".join(context.args)
    
    # Подтверждение рассылки
    confirm_msg = await update.message.reply_html(
        f"📢 <b>ПОДТВЕРЖДЕНИЕ РАССЫЛКИ</b>\n\n"
        f"📝 <b>Сообщение для рассылки:</b>\n"
        f"<code>{broadcast_text}</code>\n\n"
        f"👥 <b>Получателей:</b> {len(user_data)} пользователей\n\n"
        f"🚀 Начинаю рассылку..."
    )
    
    # Счетчики для статистики
    sent_count = 0
    error_count = 0
    errors = []
    
    # Отправляем сообщение каждому пользователю
    for target_user_id, user_info in user_data.items():
        try:
            # Формируем сообщение с использованием шаблона
            template = bot_settings.get('message_template', '{message}')
            admin_message = template.format(message=broadcast_text)
            
            await context.bot.send_message(
                chat_id=target_user_id,
                text=admin_message,
                parse_mode='HTML'
            )
            sent_count += 1
            
            # Небольшая задержка, чтобы не превысить лимиты Telegram
            await asyncio.sleep(0.1)
            
        except Exception as e:
            error_count += 1
            user_name = user_info.get('name', 'Неизвестно')
            error_msg = str(e)
            
            # Сокращаем сообщение об ошибке для отчета
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            
            errors.append(f"👤 {user_name} (ID: {target_user_id}): {error_msg}")
            
            logger.warning(f"Ошибка отправки рассылки пользователю {target_user_id}: {e}")
    
    # Формируем отчет о рассылке
    report_text = f"📊 <b>ОТЧЕТ О РАССЫЛКЕ</b>\n\n"
    report_text += f"✅ <b>Успешно отправлено:</b> {sent_count}\n"
    report_text += f"❌ <b>Ошибок:</b> {error_count}\n"
    report_text += f"📋 <b>Всего пользователей:</b> {len(user_data)}\n\n"
    
    if sent_count > 0:
        success_rate = (sent_count / len(user_data)) * 100
        report_text += f"📈 <b>Успешность:</b> {success_rate:.1f}%\n\n"
    
    report_text += f"📝 <b>Отправленное сообщение:</b>\n<code>{broadcast_text}</code>\n\n"
    
    # Добавляем детали ошибок (только первые 5)
    if errors:
        report_text += f"🔍 <b>Детали ошибок:</b>\n"
        for error in errors[:5]:
            report_text += f"• {error}\n"
        
        if len(errors) > 5:
            report_text += f"• ... и еще {len(errors) - 5} ошибок\n"
        
        report_text += f"\n💡 <b>Причины ошибок:</b>\n"
        report_text += f"• Пользователь заблокировал бота\n"
        report_text += f"• Пользователь удалил аккаунт\n"
        report_text += f"• Временные проблемы сети\n"
    
    report_text += f"\n⏰ <b>Время рассылки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    
    # Отправляем отчет
    await confirm_msg.edit_text(report_text, parse_mode='HTML')
    
    # Логируем результаты
    logger.info(f"📢 Рассылка завершена: {sent_count} успешно, {error_count} ошибок")

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

async def users_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Информация о пользователях бота (только админ)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен! Только администратор может использовать эту команду.")
        return
    
    if not user_data:
        await update.message.reply_html(
            "👥 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЯХ</b>\n\n"
            "📊 <b>Статистика:</b>\n"
            "• Пользователей в базе: <b>0</b>\n\n"
            "💡 <b>Возможные причины:</b>\n"
            "• Никто еще не использовал команду /start\n"
            "• Данные не сохранились из файла\n"
            "• Файл user_data.json отсутствует\n\n"
            "🔧 <b>Для исправления:</b>\n"
            "Попросите пользователей выполнить /start"
        )
        return
    
    # Сортируем пользователей по времени последней активности
    sorted_users = sorted(
        user_data.items(), 
        key=lambda x: x[1].get('last_activity', ''), 
        reverse=True
    )
    
    info_text = f"👥 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЯХ</b>\n\n"
    info_text += f"📊 <b>Статистика:</b>\n"
    info_text += f"• Всего пользователей: <b>{len(user_data)}</b>\n"
    info_text += f"• Файл данных: <code>{USER_DATA_FILE}</code>\n\n"
    
    info_text += f"👤 <b>Список пользователей:</b>\n"
    
    # Показываем первых 10 пользователей
    for i, (uid, info) in enumerate(sorted_users[:10], 1):
        name = info.get('name', 'Неизвестно')
        username = info.get('username', 'нет')
        last_activity = info.get('last_activity', 'никогда')
        
        # Форматируем дату если она есть
        try:
            if last_activity != 'никогда':
                dt = datetime.fromisoformat(last_activity)
                last_activity = dt.strftime('%d.%m.%Y %H:%M')
        except:
            pass
        
        username_text = f"@{username}" if username and username != 'нет' else "без username"
        
        # Добавляем метку для пользователей добавленных админом
        admin_mark = " 👨‍💻" if info.get('added_by_admin') else ""
        
        info_text += f"{i}. <b>{name}</b>{admin_mark} ({username_text})\n"
        info_text += f"   ID: <code>{uid}</code>\n"
        info_text += f"   Активен: {last_activity}\n\n"
    
    if len(user_data) > 10:
        info_text += f"... и еще {len(user_data) - 10} пользователей\n\n"
    
    info_text += f"💾 <b>Сохранение данных:</b>\n"
    info_text += f"• Автосохранение при каждом /start\n"
    info_text += f"• Загрузка при запуске бота\n"
    info_text += f"• Защита от потери при редеплое\n\n"
    
    info_text += f"💡 <b>Обозначения:</b>\n"
    info_text += f"👨‍💻 - добавлен администратором\n"
    info_text += f"• Без метки - присоединился через /start\n\n"
    
    info_text += f"🔧 <b>Управление:</b>\n"
    info_text += f"/add_user [ID] [имя] - добавить пользователя\n"
    info_text += f"/remove_user [ID] - удалить пользователя"
    
    await update.message.reply_html(info_text)

async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ручное добавление пользователя по ID (только админ)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен! Только администратор может использовать эту команду.")
        return
    
    # Проверяем аргументы
    if not context.args:
        await update.message.reply_html(
            "➕ <b>ДОБАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            "🔍 <b>Использование:</b>\n"
            "<code>/add_user [ID] [имя]</code>\n\n"
            "💡 <b>Примеры:</b>\n"
            "• <code>/add_user 123456789</code>\n"
            "• <code>/add_user 123456789 Анна</code>\n"
            "• <code>/add_user 987654321 Иван Петров</code>\n\n"
            "📊 <b>Текущая база:</b>\n"
            f"👥 Пользователей: <b>{len(user_data)}</b>\n\n"
            "⚠️ <b>Примечание:</b>\n"
            "• ID должен быть числом\n"
            "• Имя опционально\n"
            "• Если пользователь уже есть - данные обновятся"
        )
        return
    
    # Получаем ID пользователя
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_html(
            "❌ <b>ОШИБКА ФОРМАТА!</b>\n\n"
            f"'{context.args[0]}' не является числом.\n\n"
            "💡 <b>Правильный формат:</b>\n"
            "<code>/add_user 123456789 Имя</code>"
        )
        return
    
    # Получаем имя пользователя (если указано)
    if len(context.args) > 1:
        user_name = " ".join(context.args[1:])
    else:
        user_name = "Пользователь (добавлен админом)"
    
    # Проверяем, существует ли уже пользователь
    is_existing = target_user_id in user_data
    
    # Пытаемся получить информацию о пользователе через Telegram API
    real_user_info = None
    try:
        # Попытка получить информацию через getChat
        chat_info = await context.bot.get_chat(target_user_id)
        if chat_info:
            real_user_info = {
                'first_name': chat_info.first_name or user_name,
                'username': chat_info.username,
                'type': chat_info.type
            }
    except Exception as e:
        logger.info(f"Не удалось получить информацию о пользователе {target_user_id}: {e}")
    
    # Формируем данные пользователя
    current_time = datetime.now().isoformat()
    
    if is_existing:
        # Обновляем существующего пользователя
        if real_user_info:
            user_data[target_user_id]['name'] = real_user_info['first_name']
            if real_user_info['username']:
                user_data[target_user_id]['username'] = real_user_info['username']
        else:
            user_data[target_user_id]['name'] = user_name
        
        user_data[target_user_id]['last_activity'] = current_time
        user_data[target_user_id]['updated_by_admin'] = current_time
        
        status = "обновлен"
    else:
        # Добавляем нового пользователя
        user_data[target_user_id] = {
            'name': real_user_info['first_name'] if real_user_info else user_name,
            'username': real_user_info['username'] if real_user_info and real_user_info['username'] else None,
            'first_seen': current_time,
            'last_activity': current_time,
            'added_by_admin': True,
            'added_by_admin_time': current_time
        }
        status = "добавлен"
    
    # Сохраняем изменения
    save_user_data()
    
    # Формируем ответ
    result_text = f"✅ <b>ПОЛЬЗОВАТЕЛЬ {status.upper()}!</b>\n\n"
    result_text += f"👤 <b>Информация:</b>\n"
    result_text += f"• ID: <code>{target_user_id}</code>\n"
    result_text += f"• Имя: <b>{user_data[target_user_id]['name']}</b>\n"
    
    if user_data[target_user_id].get('username'):
        result_text += f"• Username: @{user_data[target_user_id]['username']}\n"
    else:
        result_text += f"• Username: не указан\n"
    
    result_text += f"• Статус: {status}\n"
    
    if real_user_info:
        result_text += f"• Источник данных: Telegram API ✅\n"
    else:
        result_text += f"• Источник данных: ручной ввод 📝\n"
    
    result_text += f"\n📊 <b>Статистика базы:</b>\n"
    result_text += f"• Всего пользователей: <b>{len(user_data)}</b>\n"
    result_text += f"• Добавлено админом: <b>{sum(1 for u in user_data.values() if u.get('added_by_admin'))}</b>\n"
    
    result_text += f"\n💡 <b>Что теперь доступно:</b>\n"
    result_text += f"• Пользователь включен в рассылки (/broadcast)\n"
    result_text += f"• Отображается в /users_info\n"
    result_text += f"• Может использовать команды бота\n"
    
    if not is_existing:
        result_text += f"\n🎯 <b>Рекомендация:</b>\n"
        result_text += f"Отправьте пользователю сообщение о том, что он добавлен в бота!"
    
    await update.message.reply_html(result_text)
    
    # Логируем действие
    logger.info(f"👨‍💻 Админ {user_id} {status} пользователя {target_user_id}: {user_data[target_user_id]['name']}")

async def remove_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаление пользователя по ID (только админ)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен! Только администратор может использовать эту команду.")
        return
    
    # Проверяем аргументы
    if not context.args:
        await update.message.reply_html(
            "🗑️ <b>УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            "🔍 <b>Использование:</b>\n"
            "<code>/remove_user [ID]</code>\n\n"
            "💡 <b>Примеры:</b>\n"
            "• <code>/remove_user 123456789</code>\n\n"
            "📊 <b>Текущая база:</b>\n"
            f"👥 Пользователей: <b>{len(user_data)}</b>\n\n"
            "⚠️ <b>Внимание:</b>\n"
            "• Пользователь будет полностью удален из базы\n"
            "• Не сможет получать рассылки\n"
            "• Отменить действие нельзя\n\n"
            "💡 <b>Для просмотра пользователей:</b> /users_info"
        )
        return
    
    # Получаем ID пользователя
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_html(
            "❌ <b>ОШИБКА ФОРМАТА!</b>\n\n"
            f"'{context.args[0]}' не является числом.\n\n"
            "💡 <b>Правильный формат:</b>\n"
            "<code>/remove_user 123456789</code>"
        )
        return
    
    # Проверяем, существует ли пользователь
    if target_user_id not in user_data:
        await update.message.reply_html(
            f"❌ <b>ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН!</b>\n\n"
            f"Пользователь с ID <code>{target_user_id}</code> не найден в базе.\n\n"
            f"📊 <b>Текущая база:</b> {len(user_data)} пользователей\n\n"
            f"💡 <b>Для просмотра всех пользователей:</b> /users_info"
        )
        return
    
    # Защита от удаления самого администратора
    if target_user_id == ADMIN_USER_ID:
        await update.message.reply_html(
            "🛡️ <b>ОПЕРАЦИЯ ЗАПРЕЩЕНА!</b>\n\n"
            "Вы не можете удалить самого себя из базы пользователей.\n\n"
            "👨‍💻 <b>Вы администратор</b> - ваши данные защищены от удаления."
        )
        return
    
    # Сохраняем информацию о пользователе для отчета
    removed_user = user_data[target_user_id].copy()
    
    # Удаляем пользователя
    del user_data[target_user_id]
    
    # Сохраняем изменения
    save_user_data()
    
    # Формируем отчет
    result_text = f"✅ <b>ПОЛЬЗОВАТЕЛЬ УДАЛЕН!</b>\n\n"
    result_text += f"🗑️ <b>Удаленный пользователь:</b>\n"
    result_text += f"• ID: <code>{target_user_id}</code>\n"
    result_text += f"• Имя: <b>{removed_user.get('name', 'Неизвестно')}</b>\n"
    
    if removed_user.get('username'):
        result_text += f"• Username: @{removed_user['username']}\n"
    else:
        result_text += f"• Username: не указан\n"
    
    # Показываем дополнительную информацию
    if removed_user.get('added_by_admin'):
        result_text += f"• Был добавлен: админом\n"
    else:
        result_text += f"• Был добавлен: через /start\n"
    
    if removed_user.get('first_seen'):
        try:
            dt = datetime.fromisoformat(removed_user['first_seen'])
            result_text += f"• Первый визит: {dt.strftime('%d.%m.%Y %H:%M')}\n"
        except:
            pass
    
    result_text += f"\n📊 <b>Обновленная статистика:</b>\n"
    result_text += f"• Пользователей осталось: <b>{len(user_data)}</b>\n"
    result_text += f"• Добавлено админом: <b>{sum(1 for u in user_data.values() if u.get('added_by_admin'))}</b>\n"
    
    result_text += f"\n❌ <b>Что изменилось:</b>\n"
    result_text += f"• Пользователь исключен из рассылок\n"
    result_text += f"• Не отображается в /users_info\n"
    result_text += f"• Может снова присоединиться через /start\n"
    
    result_text += f"\n💡 <b>Для восстановления:</b>\n"
    result_text += f"Используйте <code>/add_user {target_user_id} {removed_user.get('name', '')}</code>"
    
    await update.message.reply_html(result_text)
    
    # Логируем действие
    logger.info(f"👨‍💻 Админ {user_id} удалил пользователя {target_user_id}: {removed_user.get('name', 'Неизвестно')}")

async def send_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка сообщения конкретному пользователю (только админ)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен! Только администратор может использовать эту команду.")
        return
    
    # Проверяем аргументы
    if not context.args or len(context.args) < 2:
        await update.message.reply_html(
            "📨 <b>ОТПРАВКА ЛИЧНОГО СООБЩЕНИЯ</b>\n\n"
            "🔍 <b>Использование:</b>\n"
            "<code>/send_message [ID] [текст сообщения]</code>\n\n"
            "💡 <b>Примеры:</b>\n"
            "• <code>/send_message 123456789 Привет!</code>\n"
            "• <code>/send_message 987654321 Как дела? Напиши мне</code>\n"
            "• <code>/send_message 555666777 🎉 Поздравляю с днем рождения!</code>\n\n"
            f"📊 <b>Доступно пользователей:</b> {len(user_data)}\n\n"
            f"📋 <b>Текущий шаблон:</b>\n"
            f"<code>{bot_settings.get('message_template', 'не установлен')}</code>\n\n"
            "⚙️ <b>Настройки:</b>\n"
            "/set_template [шаблон] - изменить шаблон\n"
            "/users_info - список пользователей"
        )
        return
    
    # Получаем ID получателя
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_html(
            "❌ <b>ОШИБКА ФОРМАТА!</b>\n\n"
            f"'{context.args[0]}' не является числом.\n\n"
            "💡 <b>Правильный формат:</b>\n"
            "<code>/send_message 123456789 Текст сообщения</code>"
        )
        return
    
    # Получаем текст сообщения
    message_text = " ".join(context.args[1:])
    
    # Проверяем, существует ли получатель в базе
    if target_user_id not in user_data:
        await update.message.reply_html(
            f"❌ <b>ПОЛУЧАТЕЛЬ НЕ НАЙДЕН!</b>\n\n"
            f"Пользователь с ID <code>{target_user_id}</code> не найден в базе.\n\n"
            f"📊 <b>База содержит:</b> {len(user_data)} пользователей\n\n"
            f"💡 <b>Варианты решения:</b>\n"
            f"1. Добавить пользователя: <code>/add_user {target_user_id} Имя</code>\n"
            f"2. Посмотреть список: /users_info\n"
            f"3. Попробовать отправить напрямую (может не сработать)"
        )
        return
    
    # Получаем информацию о получателе
    recipient_info = user_data[target_user_id]
    recipient_name = recipient_info.get('name', 'Неизвестно')
    
    # Формируем сообщение с использованием шаблона
    template = bot_settings.get('message_template', '{message}')
    formatted_message = template.format(message=message_text)
    
    # Подтверждение отправки
    confirm_text = (
        f"📨 <b>ОТПРАВКА ЛИЧНОГО СООБЩЕНИЯ</b>\n\n"
        f"📤 <b>Получатель:</b>\n"
        f"• Имя: <b>{recipient_name}</b>\n"
        f"• ID: <code>{target_user_id}</code>\n"
    )
    
    if recipient_info.get('username'):
        confirm_text += f"• Username: @{recipient_info['username']}\n"
    
    confirm_text += f"\n📝 <b>Сообщение:</b>\n{formatted_message}\n\n🚀 Отправляю..."
    
    confirm_msg = await update.message.reply_html(confirm_text)
    
    # Отправляем сообщение
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=formatted_message,
            parse_mode='HTML'
        )
        
        # Успешная отправка
        success_text = (
            f"✅ <b>СООБЩЕНИЕ ОТПРАВЛЕНО!</b>\n\n"
            f"📤 <b>Получатель:</b> {recipient_name} (ID: {target_user_id})\n"
            f"📝 <b>Содержание:</b>\n{formatted_message}\n\n"
            f"⏰ <b>Время отправки:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            f"💡 <b>Что дальше:</b>\n"
            f"• Пользователь получил ваше сообщение\n"
            f"• Может ответить в боте\n"
            f"• Вы увидите ответ в чате бота"
        )
        
        await confirm_msg.edit_text(success_text, parse_mode='HTML')
        
        # Логируем успешную отправку
        logger.info(f"📨 Личное сообщение от админа {user_id} отправлено пользователю {target_user_id}")
        
    except Exception as e:
        # Ошибка отправки
        error_text = (
            f"❌ <b>ОШИБКА ОТПРАВКИ!</b>\n\n"
            f"📤 <b>Получатель:</b> {recipient_name} (ID: {target_user_id})\n"
            f"📝 <b>Сообщение:</b> {message_text}\n\n"
            f"🚫 <b>Причина ошибки:</b>\n{str(e)}\n\n"
            f"💡 <b>Возможные причины:</b>\n"
            f"• Пользователь заблокировал бота\n"
            f"• Пользователь удалил аккаунт\n"
            f"• Проблемы с сетью\n"
            f"• Неверный ID пользователя\n\n"
            f"🔧 <b>Что можно сделать:</b>\n"
            f"• Проверить ID через /users_info\n"
            f"• Попробовать позже\n"
            f"• Связаться другим способом"
        )
        
        await confirm_msg.edit_text(error_text, parse_mode='HTML')
        
        # Логируем ошибку
        logger.warning(f"❌ Ошибка отправки личного сообщения {target_user_id}: {e}")

async def set_template_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Настройка шаблона сообщений (только админ)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен! Только администратор может использовать эту команду.")
        return
    
    # Проверяем аргументы
    if not context.args:
        current_template = bot_settings.get('message_template', 'не установлен')
        await update.message.reply_html(
            "⚙️ <b>НАСТРОЙКА ШАБЛОНА СООБЩЕНИЙ</b>\n\n"
            "🔍 <b>Использование:</b>\n"
            "<code>/set_template [новый шаблон]</code>\n\n"
            f"📋 <b>Текущий шаблон:</b>\n"
            f"<code>{current_template}</code>\n\n"
            "💡 <b>Примеры шаблонов:</b>\n"
            "• <code>/set_template 📢 От администратора: {message}</code>\n"
            "• <code>/set_template 🎯 Важное сообщение:\\n\\n{message}</code>\n"
            "• <code>/set_template {message}</code> (без оформления)\n"
            "• <code>/set_template 💌 <b>Личное сообщение:</b>\\n{message}</code>\n\n"
            "🔑 <b>Важно:</b>\n"
            "• Обязательно используйте <code>{message}</code> - сюда подставится текст\n"
            "• Поддерживается HTML разметка (<b>, <i>, <code>)\n"
            "• Используйте \\n для переноса строки\n\n"
            "👀 <b>Просмотр:</b> /get_template"
        )
        return
    
    # Получаем новый шаблон
    new_template = " ".join(context.args)
    
    # Проверяем наличие плейсхолдера {message}
    if '{message}' not in new_template:
        await update.message.reply_html(
            "❌ <b>ОШИБКА ШАБЛОНА!</b>\n\n"
            f"Шаблон должен содержать <code>{{message}}</code> - место для вставки текста.\n\n"
            f"🚫 <b>Ваш шаблон:</b>\n"
            f"<code>{new_template}</code>\n\n"
            f"✅ <b>Исправленный вариант:</b>\n"
            f"<code>{new_template} {{message}}</code>\n\n"
            f"💡 <b>Попробуйте снова с правильным шаблоном.</b>"
        )
        return
    
    # Сохраняем старый шаблон для отчета
    old_template = bot_settings.get('message_template', 'не установлен')
    
    # Устанавливаем новый шаблон
    bot_settings['message_template'] = new_template
    
    # Сохраняем настройки
    save_bot_settings()
    
    # Тестируем шаблон
    test_message = "Тестовое сообщение"
    test_result = new_template.format(message=test_message)
    
    # Формируем отчет
    result_text = (
        f"✅ <b>ШАБЛОН ОБНОВЛЕН!</b>\n\n"
        f"🔄 <b>Изменения:</b>\n"
        f"• Старый: <code>{old_template}</code>\n"
        f"• Новый: <code>{new_template}</code>\n\n"
        f"🧪 <b>Тестовый пример:</b>\n"
        f"{test_result}\n\n"
        f"💡 <b>Применяется к:</b>\n"
        f"• /broadcast - массовая рассылка\n"
        f"• /send_message - личные сообщения\n\n"
        f"📝 <b>Настройки сохранены в:</b> {BOT_SETTINGS_FILE}\n\n"
        f"🔧 <b>Управление шаблонами:</b>\n"
        f"/get_template - просмотр текущего шаблона\n"
        f"/set_template [шаблон] - изменить"
    )
    
    await update.message.reply_html(result_text)
    
    # Логируем изменение
    logger.info(f"⚙️ Админ {user_id} изменил шаблон сообщений")

async def get_template_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Просмотр текущего шаблона сообщений (только админ)"""
    user_id = update.effective_user.id
    
    # Проверяем права администратора
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Доступ запрещен! Только администратор может использовать эту команду.")
        return
    
    current_template = bot_settings.get('message_template', 'не установлен')
    
    # Тестируем шаблон с примером
    test_examples = [
        "Привет! Как дела?",
        "🎉 Поздравляю с праздником!",
        "Техническое обслуживание с 15:00 до 16:00"
    ]
    
    info_text = (
        f"📋 <b>ТЕКУЩИЙ ШАБЛОН СООБЩЕНИЙ</b>\n\n"
        f"⚙️ <b>Шаблон:</b>\n"
        f"<code>{current_template}</code>\n\n"
        f"🧪 <b>Примеры с этим шаблоном:</b>\n"
    )
    
    for i, example in enumerate(test_examples, 1):
        try:
            formatted = current_template.format(message=example)
            info_text += f"\n{i}. <b>Исходный текст:</b> {example}\n"
            info_text += f"   <b>Результат:</b>\n{formatted}\n"
        except Exception as e:
            info_text += f"\n{i}. ❌ Ошибка форматирования: {e}\n"
    
    info_text += (
        f"\n💾 <b>Статус сохранения:</b>\n"
        f"• Файл настроек: {BOT_SETTINGS_FILE}\n"
        f"• Автосохранение: включено\n"
        f"• Загрузка при старте: да\n\n"
        f"🔧 <b>Управление:</b>\n"
        f"/set_template [новый шаблон] - изменить\n"
        f"/send_message [ID] [текст] - протестировать\n"
        f"/broadcast [текст] - массовая рассылка"
    )
    
    await update.message.reply_html(info_text)

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
    
    # Загружаем настройки бота при старте
    load_bot_settings()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("my_id", my_id_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("rates", rates_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("fix_admin_id", fix_admin_id_command))
    application.add_handler(CommandHandler("users_info", users_info_command))
    application.add_handler(CommandHandler("add_user", add_user_command))
    application.add_handler(CommandHandler("remove_user", remove_user_command))
    application.add_handler(CommandHandler("send_message", send_message_command))
    application.add_handler(CommandHandler("set_template", set_template_command))
    application.add_handler(CommandHandler("get_template", get_template_command))
    application.add_handler(CommandHandler("stocks", stocks_command))

    # Обработчик всех текстовых сообщений (эхо)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Запуск бота
    logger.info("✅ Бот запущен и готов к работе")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 