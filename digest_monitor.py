#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для мониторинга Telegram-каналов
Собирает сообщения из указанных каналов
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import Message

from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, DIGEST_SOURCE_CHANNELS

logger = logging.getLogger(__name__)

# Глобальный клиент Telegram
_telegram_client: Optional[TelegramClient] = None
_message_callback: Optional[Callable] = None


async def init_telegram_client() -> bool:
    """Инициализировать Telegram клиент"""
    global _telegram_client
    
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        logger.warning("⚠️ Telegram API не настроен (отсутствуют TELEGRAM_API_ID или TELEGRAM_API_HASH)")
        return False
    
    try:
        _telegram_client = TelegramClient('digest_bot_session', TELEGRAM_API_ID, TELEGRAM_API_HASH)
        await _telegram_client.start()
        logger.info("✅ Telegram клиент инициализирован")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Telegram клиента: {e}")
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

