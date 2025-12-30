#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для мониторинга Telegram-каналов
Собирает сообщения из указанных каналов
"""

import logging
import asyncio
import os
import base64
import tempfile
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import Message

from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, DIGEST_SOURCE_CHANNELS

logger = logging.getLogger(__name__)

# Глобальный клиент Telegram
_telegram_client: Optional[TelegramClient] = None
_message_callback: Optional[Callable] = None


def _get_session_file() -> str:
    """
    Получить путь к файлу сессии
    Поддерживает чтение из base64 переменной окружения для Railway
    """
    session_file = 'digest_bot_session.session'
    
    # Проверяем, есть ли сессия в base64 (для Railway)
    session_base64 = os.getenv('DIGEST_SESSION_BASE64')
    if session_base64:
        try:
            # Декодируем base64
            session_data = base64.b64decode(session_base64)
            
            # Создаем временный файл
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.session', prefix='digest_bot_')
            temp_file.write(session_data)
            temp_file.close()
            
            session_file = temp_file.name
            logger.info("✅ Сессия загружена из переменной окружения DIGEST_SESSION_BASE64")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить сессию из base64: {e}, используем файл")
    
    return session_file


async def init_telegram_client() -> bool:
    """Инициализировать Telegram клиент"""
    global _telegram_client
    
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        logger.warning("⚠️ Telegram API не настроен (отсутствуют TELEGRAM_API_ID или TELEGRAM_API_HASH)")
        return False
    
    try:
        session_file = _get_session_file()
        _telegram_client = TelegramClient(session_file, TELEGRAM_API_ID, TELEGRAM_API_HASH)
        
        # Пробуем подключиться
        await _telegram_client.start()
        
        # Проверяем, авторизованы ли мы
        if not await _telegram_client.is_user_authorized():
            logger.error("❌ Telegram клиент не авторизован. Нужно авторизоваться локально и загрузить сессию.")
            logger.info("💡 Инструкция: запустите 'python digest_auth_helper.py' локально, затем загрузите файл сессии на Railway")
            await _telegram_client.disconnect()
            return False
        
        logger.info("✅ Telegram клиент инициализирован и авторизован")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Telegram клиента: {e}")
        logger.info("💡 Убедитесь, что:")
        logger.info("   1. TELEGRAM_API_ID и TELEGRAM_API_HASH установлены правильно")
        logger.info("   2. Файл сессии загружен (digest_bot_session.session) или DIGEST_SESSION_BASE64 установлен")
        logger.info("   3. Для первой авторизации запустите 'python digest_auth_helper.py' локально")
        return False


def set_message_callback(callback: Callable):
    """Установить callback для обработки новых сообщений"""
    global _message_callback
    _message_callback = callback


async def start_monitoring():
    """Начать мониторинг каналов"""
    if not _telegram_client:
        if not await init_telegram_client():
            return False
    
    if not DIGEST_SOURCE_CHANNELS:
        logger.warning("⚠️ Не указаны каналы для мониторинга (DIGEST_SOURCE_CHANNELS)")
        return False
    
    try:
        @_telegram_client.on(events.NewMessage(chats=DIGEST_SOURCE_CHANNELS))
        async def handler(event: events.NewMessage.Event):
            """Обработчик новых сообщений"""
            message: Message = event.message
            
            # Пропускаем служебные сообщения
            if not message.text or len(message.text.strip()) < 10:
                return
            
            message_data = {
                'text': message.text,
                'source': event.chat.username or event.chat.title or 'Unknown',
                'timestamp': datetime.now().isoformat(),
                'message_id': message.id,
                'date': message.date.isoformat() if message.date else None
            }
            
            logger.debug(f"📨 Получено сообщение из {message_data['source']}: {message_data['text'][:50]}...")
            
            # Вызываем callback если установлен
            if _message_callback:
                try:
                    await _message_callback(message_data)
                except Exception as e:
                    logger.error(f"❌ Ошибка в callback обработки сообщения: {e}")
        
        logger.info(f"✅ Мониторинг запущен для каналов: {', '.join(DIGEST_SOURCE_CHANNELS)}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка запуска мониторинга: {e}")
        return False


async def get_recent_messages(channel: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Получить последние сообщения из канала
    
    Args:
        channel: Имя канала (например, @channel)
        limit: Количество сообщений
        
    Returns:
        Список сообщений
    """
    if not _telegram_client:
        if not await init_telegram_client():
            return []
    
    try:
        messages = []
        async for message in _telegram_client.iter_messages(channel, limit=limit):
            if message.text and len(message.text.strip()) >= 10:
                messages.append({
                    'text': message.text,
                    'source': channel,
                    'timestamp': datetime.now().isoformat(),
                    'message_id': message.id,
                    'date': message.date.isoformat() if message.date else None
                })
        
        logger.info(f"✅ Получено {len(messages)} сообщений из {channel}")
        return messages
    except Exception as e:
        logger.error(f"❌ Ошибка получения сообщений из {channel}: {e}")
        return []


async def stop_monitoring():
    """Остановить мониторинг"""
    global _telegram_client
    if _telegram_client:
        try:
            await _telegram_client.disconnect()
            logger.info("✅ Telegram клиент отключен")
        except Exception as e:
            logger.error(f"❌ Ошибка отключения Telegram клиента: {e}")
        finally:
            _telegram_client = None

