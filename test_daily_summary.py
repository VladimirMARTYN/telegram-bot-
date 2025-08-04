#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для тестирования ежедневной сводки
"""

import os
import json
import asyncio
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Импортируем функции из admin_bot.py
import sys
sys.path.append('.')

# Импортируем функции из admin_bot
from admin_bot import (
    load_notification_data, 
    save_notification_data,
    daily_summary_job,
    load_bot_settings
)

async def test_daily_summary():
    """Тестирование ежедневной сводки"""
    print("🧪 Тестирование ежедневной сводки")
    print("=" * 50)
    
    # Проверяем настройки
    settings = load_bot_settings()
    print(f"📋 Настройки: {settings}")
    
    # Проверяем подписчиков
    notifications = load_notification_data()
    print(f"👥 Подписчиков: {len(notifications)}")
    
    # Добавляем тестового подписчика если нет
    admin_id = os.getenv('ADMIN_USER_ID')
    if not notifications:
        print("📝 Создаю тестового подписчика...")
        notifications[str(admin_id)] = {
            'subscribed': True,
            'daily_summary': True,
            'price_alerts': True,
            'alerts': {}
        }
        save_notification_data(notifications)
        print("✅ Тестовый подписчик создан")
    
    # Создаем mock context для тестирования
    class MockBot:
        async def send_message(self, chat_id, text, parse_mode=None):
            print(f"📤 Сообщение для {chat_id}:")
            print(f"   {text}")
            print("-" * 40)
    
    class MockContext:
        def __init__(self):
            self.bot = MockBot()
    
    mock_context = MockContext()
    
    # Запускаем ежедневную сводку
    print("\n🚀 Запуск ежедневной сводки...")
    try:
        await daily_summary_job(mock_context)
        print("✅ Ежедневная сводка выполнена успешно!")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        print(f"📋 Трассировка: {traceback.format_exc()}")

def main():
    """Основная функция"""
    print("🔧 Тестирование системы ежедневной сводки")
    print("=" * 60)
    
    # Запускаем тест
    asyncio.run(test_daily_summary())
    
    print("\n" + "=" * 60)
    print("📋 Результаты тестирования:")
    print("1. Проверьте вывод выше на наличие ошибок")
    print("2. Если есть ошибки, исправьте их")
    print("3. Если все работает, бот готов к использованию")

if __name__ == '__main__':
    main() 