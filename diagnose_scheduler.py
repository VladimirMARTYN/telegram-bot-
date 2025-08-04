#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для диагностики проблем с расписанием в Telegram боте
"""

import os
import json
import logging
from datetime import datetime, time
import pytz
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def check_environment():
    """Проверка переменных окружения"""
    print("🔍 Проверка переменных окружения:")
    print("-" * 40)
    
    # Проверяем .env файл
    env_file = '.env'
    if os.path.exists(env_file):
        print(f"✅ Файл {env_file} найден")
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key == 'BOT_TOKEN':
                        print(f"   {key}: {value[:10]}...")
                    else:
                        print(f"   {key}: {value}")
    else:
        print(f"❌ Файл {env_file} не найден")
    
    # Проверяем переменные окружения
    bot_token = os.getenv('BOT_TOKEN')
    admin_id = os.getenv('ADMIN_USER_ID')
    
    print(f"\nПеременные окружения:")
    print(f"   BOT_TOKEN: {'✅ Установлен' if bot_token else '❌ Не установлен'}")
    print(f"   ADMIN_USER_ID: {'✅ Установлен' if admin_id else '❌ Не установлен'}")

def check_data_files():
    """Проверка файлов данных"""
    print("\n📁 Проверка файлов данных:")
    print("-" * 40)
    
    files_to_check = [
        'notifications.json',
        'bot_settings.json', 
        'price_history.json'
    ]
    
    for filename in files_to_check:
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            print(f"✅ {filename}: {file_size} байт")
            
            # Показываем содержимое настроек
            if filename == 'bot_settings.json':
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                    print(f"   Настройки: {settings}")
                except Exception as e:
                    print(f"   ❌ Ошибка чтения: {e}")
            
            # Показываем количество подписчиков
            if filename == 'notifications.json':
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        notifications = json.load(f)
                    active_subscribers = sum(1 for data in notifications.values() 
                                           if data.get('subscribed', False))
                    daily_subscribers = sum(1 for data in notifications.values() 
                                          if data.get('subscribed', False) and data.get('daily_summary', True))
                    print(f"   Подписчиков: {len(notifications)}")
                    print(f"   Активных: {active_subscribers}")
                    print(f"   На ежедневную сводку: {daily_subscribers}")
                except Exception as e:
                    print(f"   ❌ Ошибка чтения: {e}")
        else:
            print(f"❌ {filename}: не найден")

def check_timezone():
    """Проверка часового пояса"""
    print("\n🕐 Проверка часового пояса:")
    print("-" * 40)
    
    try:
        moscow_tz = pytz.timezone('Europe/Moscow')
        current_moscow = datetime.now(moscow_tz)
        current_utc = datetime.now(pytz.UTC)
        
        print(f"Текущее время UTC: {current_utc.strftime('%H:%M:%S %d.%m.%Y')}")
        print(f"Текущее время МСК: {current_moscow.strftime('%H:%M:%S %d.%m.%Y')}")
        print(f"Разница с UTC: {moscow_tz.utcoffset(current_moscow)}")
        
        # Проверяем настройки времени
        if os.path.exists('bot_settings.json'):
            with open('bot_settings.json', 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            daily_time_str = settings.get('daily_summary_time', '09:00')
            print(f"\nНастройки ежедневной сводки:")
            print(f"   Время: {daily_time_str} МСК")
            
            # Вычисляем время до следующего запуска
            hour, minute = map(int, daily_time_str.split(':'))
            next_run = current_moscow.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if current_moscow.hour > hour or (current_moscow.hour == hour and current_moscow.minute >= minute):
                from datetime import timedelta
                next_run = next_run + timedelta(days=1)
            
            time_until = next_run - current_moscow
            hours_until = int(time_until.total_seconds() // 3600)
            minutes_until = int((time_until.total_seconds() % 3600) // 60)
            
            print(f"   Следующий запуск: {next_run.strftime('%H:%M %d.%m.%Y')}")
            print(f"   До запуска: {hours_until}ч {minutes_until}мин")
        
    except Exception as e:
        print(f"❌ Ошибка проверки часового пояса: {e}")

def check_dependencies():
    """Проверка зависимостей"""
    print("\n📦 Проверка зависимостей:")
    print("-" * 40)
    
    dependencies = [
        'telegram',
        'pytz',
        'requests',
        'aiohttp',
        'schedule'
    ]
    
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"✅ {dep}")
        except ImportError:
            print(f"❌ {dep} - не установлен")

def main():
    """Основная функция диагностики"""
    print("🔧 Диагностика системы расписания Telegram бота")
    print("=" * 60)
    
    check_environment()
    check_data_files()
    check_timezone()
    check_dependencies()
    
    print("\n" + "=" * 60)
    print("📋 Рекомендации:")
    print("1. Убедитесь, что файл .env содержит BOT_TOKEN и ADMIN_USER_ID")
    print("2. Проверьте, что все файлы данных созданы")
    print("3. Убедитесь, что есть хотя бы один подписчик")
    print("4. Проверьте, что время в настройках корректное")
    print("5. Запустите бота и используйте /test_daily для проверки")
    print("6. Проверьте логи бота на наличие ошибок")

if __name__ == '__main__':
    main() 