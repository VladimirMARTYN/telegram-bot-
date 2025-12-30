#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Вспомогательный скрипт для авторизации Telethon локально
Используйте этот скрипт для создания файла сессии, который затем можно загрузить на Railway
"""

import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient

# Загружаем переменные из .env
load_dotenv()

async def main():
    """Авторизация в Telegram"""
    api_id = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    
    if not api_id or not api_hash:
        print("❌ Ошибка: TELEGRAM_API_ID и TELEGRAM_API_HASH должны быть в .env файле")
        print("\nДобавьте в .env:")
        print("TELEGRAM_API_ID=ваш_id")
        print("TELEGRAM_API_HASH=ваш_hash")
        return
    
    try:
        api_id = int(api_id)
    except ValueError:
        print("❌ Ошибка: TELEGRAM_API_ID должен быть числом")
        return
    
    print("🔐 Начинаю авторизацию в Telegram...")
    print("📱 Вам понадобится:")
    print("   1. Номер телефона (с кодом страны, например: +79991234567)")
    print("   2. Код из Telegram")
    print("   3. Пароль 2FA (если включен)")
    print()
    
    # Создаем клиент с именем файла сессии
    client = TelegramClient('digest_bot_session', api_id, api_hash)
    
    try:
        await client.start()
        print("\n✅ Авторизация успешна!")
        print(f"📁 Файл сессии создан: digest_bot_session.session")
        print("\n📤 Теперь загрузите этот файл на Railway:")
        print("   1. В Railway Dashboard → Variables")
        print("   2. Добавьте переменную типа 'File' или загрузите через CLI")
        print("   3. Или используйте Railway CLI: railway variables set DIGEST_SESSION_FILE=@digest_bot_session.session")
        print("\n⚠️  ВАЖНО: Файл сессии содержит ваши учетные данные, храните его в безопасности!")
        
        # Проверяем подключение
        me = await client.get_me()
        print(f"\n👤 Авторизован как: {me.first_name} (@{me.username or 'без username'})")
        
    except Exception as e:
        print(f"\n❌ Ошибка авторизации: {e}")
        print("\nВозможные причины:")
        print("  - Неправильный api_id или api_hash")
        print("  - Проблемы с сетью")
        print("  - Telegram требует дополнительной авторизации")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

