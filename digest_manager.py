#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Основной модуль для управления AI-дайджестами
Объединяет мониторинг, векторный поиск, AI-обработку и публикацию
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict

from config import (
    DIGEST_ENABLED, DIGEST_DEST_CHANNEL, DIGEST_PUBLISH_SCHEDULE,
    DIGEST_SOURCE_CHANNELS
)
from digest_monitor import (
    init_telegram_client, start_monitoring, set_message_callback,
    get_recent_messages, stop_monitoring
)
from digest_vector import (
    init_collection, find_similar_messages, is_duplicate, store_message
)
from digest_ai import (
    create_embedding, classify_topic, summarize_topic, group_news_by_topic
)

logger = logging.getLogger(__name__)

# Буфер новостей для текущего периода
news_buffer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
processed_message_ids = set()


async def process_new_message(message_data: Dict[str, Any]) -> bool:
    """
    Обработать новое сообщение из канала
    
    Args:
        message_data: Данные сообщения
        
    Returns:
        True если сообщение обработано и добавлено
    """
    # Проверяем, не обрабатывали ли мы уже это сообщение
    msg_id = f"{message_data['source']}_{message_data['message_id']}"
    if msg_id in processed_message_ids:
        return False
    
    try:
        # Создаем эмбеддинг
        text = message_data['text']
        embedding = await create_embedding(text)
        if not embedding:
            logger.warning(f"⚠️ Не удалось создать эмбеддинг для сообщения")
            return False
        
        # Проверяем на дубликаты
        if await is_duplicate(embedding):
            logger.debug(f"🔄 Пропущен дубликат: {text[:50]}...")
            processed_message_ids.add(msg_id)
            return False
        
        # Классифицируем по теме
        topic = await classify_topic(text)
        message_data['topic'] = topic
        message_data['embedding'] = embedding
        
        # Сохраняем в буфер
        news_buffer[topic].append(message_data)
        processed_message_ids.add(msg_id)
        
        # Сохраняем в векторную БД
        await store_message(embedding, {
            'text': text,
            'source': message_data['source'],
            'timestamp': message_data['timestamp'],
            'topic': topic
        })
        
        logger.info(f"✅ Обработано сообщение: {topic} - {text[:50]}...")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обработки сообщения: {e}")
        return False


async def create_digest() -> Optional[str]:
    """
    Создать дайджест из накопленных новостей
    
    Returns:
        Текст дайджеста или None
    """
    if not news_buffer:
        logger.info("📭 Нет новостей для создания дайджеста")
        return None
    
    try:
        # Группируем новости по темам (уже сгруппированы в news_buffer)
        digest_parts = []
        digest_parts.append("📰 Дайджест новостей")
        digest_parts.append(f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        digest_parts.append("")
        
        total_news = sum(len(news_list) for news_list in news_buffer.values())
        
        # Обрабатываем каждую тему
        for topic, news_list in sorted(news_buffer.items(), key=lambda x: len(x[1]), reverse=True):
            if not news_list:
                continue
            
            # Создаем резюме для темы
            summary = await summarize_topic(news_list)
            
            # Эмодзи для тем
            topic_emojis = {
                'IT': '💻',
                'Финансы': '💰',
                'Политика': '🏛️',
                'Экономика': '📊',
                'Технологии': '🔧',
                'Криптовалюты': '₿',
                'Бизнес': '💼',
                'Наука': '🔬',
                'Спорт': '⚽',
                'Культура': '🎭',
                'Другое': '📌'
            }
            
            emoji = topic_emojis.get(topic, '📌')
            
            digest_parts.append(f"{emoji} {topic.upper()} ({len(news_list)} новостей)")
            digest_parts.append(f"📝 {summary}")
            digest_parts.append("")
            digest_parts.append("Ключевые новости:")
            
            # Добавляем ключевые новости (первые 5)
            for news in news_list[:5]:
                text = news['text'][:150] + ('...' if len(news['text']) > 150 else '')
                source = news.get('source', 'Unknown')
                digest_parts.append(f"• {text} ({source})")
            
            if len(news_list) > 5:
                digest_parts.append(f"• ... и еще {len(news_list) - 5} новостей")
            
            digest_parts.append("")
            digest_parts.append("---")
            digest_parts.append("")
        
        digest_parts.append(f"📊 Всего обработано: {total_news} новостей")
        digest_parts.append(f"📁 Групп по темам: {len(news_buffer)}")
        
        digest_text = "\n".join(digest_parts)
        
        # Очищаем буфер после создания дайджеста
        news_buffer.clear()
        processed_message_ids.clear()
        
        return digest_text
    except Exception as e:
        logger.error(f"❌ Ошибка создания дайджеста: {e}")
        return None


async def publish_digest(bot) -> bool:
    """
    Опубликовать дайджест в канал
    
    Args:
        bot: Экземпляр Telegram бота
        
    Returns:
        True если успешно опубликовано
    """
    if not DIGEST_DEST_CHANNEL:
        logger.warning("⚠️ Не указан канал для публикации дайджестов")
        return False
    
    try:
        digest_text = await create_digest()
        if not digest_text:
            logger.info("📭 Нет дайджеста для публикации")
            return False
        
        # Публикуем в канал
        await bot.send_message(
            chat_id=DIGEST_DEST_CHANNEL,
            text=digest_text,
            parse_mode='HTML'
        )
        
        logger.info(f"✅ Дайджест опубликован в {DIGEST_DEST_CHANNEL}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка публикации дайджеста: {e}")
        return False


async def initialize_digest_system() -> bool:
    """Инициализировать систему дайджестов"""
    if not DIGEST_ENABLED:
        logger.info("ℹ️ Система дайджестов отключена")
        return False
    
    try:
        # Инициализируем векторную БД
        if not await init_collection():
            logger.warning("⚠️ Не удалось инициализировать векторную БД")
        
        # Инициализируем Telegram клиент
        if not await init_telegram_client():
            logger.warning("⚠️ Не удалось инициализировать Telegram клиент")
            return False
        
        # Устанавливаем callback для новых сообщений
        set_message_callback(process_new_message)
        
        # Запускаем мониторинг
        if not await start_monitoring():
            logger.warning("⚠️ Не удалось запустить мониторинг каналов")
            return False
        
        logger.info("✅ Система дайджестов инициализирована")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации системы дайджестов: {e}")
        return False


async def load_recent_news(hours: int = 24) -> int:
    """
    Загрузить последние новости из каналов
    
    Args:
        hours: Количество часов назад для загрузки
        
    Returns:
        Количество загруженных новостей
    """
    if not DIGEST_SOURCE_CHANNELS:
        return 0
    
    total_loaded = 0
    for channel in DIGEST_SOURCE_CHANNELS:
        try:
            messages = await get_recent_messages(channel, limit=100)
            for message_data in messages:
                if await process_new_message(message_data):
                    total_loaded += 1
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки новостей из {channel}: {e}")
    
    logger.info(f"✅ Загружено {total_loaded} новостей из каналов")
    return total_loaded

