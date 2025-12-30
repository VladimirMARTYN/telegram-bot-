#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для работы с векторной базой данных Qdrant
Используется для поиска дубликатов и похожих сообщений
"""

import logging
from typing import List, Dict, Optional, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
import uuid

from config import (
    QDRANT_URL, QDRANT_API_KEY, DIGEST_COLLECTION_NAME, DIGEST_SIMILARITY_THRESHOLD
)

logger = logging.getLogger(__name__)

# Глобальный клиент Qdrant
_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> Optional[QdrantClient]:
    """Получить или создать клиент Qdrant"""
    global _qdrant_client
    
    if not QDRANT_URL or not QDRANT_API_KEY:
        logger.warning("⚠️ Qdrant не настроен (отсутствуют QDRANT_URL или QDRANT_API_KEY)")
        return None
    
    if _qdrant_client is None:
        try:
            _qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            logger.info("✅ Qdrant клиент инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Qdrant: {e}")
            return None
    
    return _qdrant_client


async def init_collection():
    """Инициализировать коллекцию в Qdrant, если её нет"""
    client = get_qdrant_client()
    if not client:
        return False
    
    try:
        collections = client.get_collections().collections
        collection_names = [col.name for col in collections]
        
        if DIGEST_COLLECTION_NAME not in collection_names:
            client.create_collection(
                collection_name=DIGEST_COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=1536,  # Размерность для text-embedding-3-small
                    distance=Distance.COSINE
                )
            )
            logger.info(f"✅ Создана коллекция {DIGEST_COLLECTION_NAME}")
        else:
            logger.debug(f"✅ Коллекция {DIGEST_COLLECTION_NAME} уже существует")
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации коллекции: {e}")
        return False


async def find_similar_messages(embedding: List[float], limit: int = 5) -> List[Dict[str, Any]]:
    """
    Найти похожие сообщения по эмбеддингу
    
    Args:
        embedding: Векторное представление сообщения
        limit: Максимальное количество результатов
        
    Returns:
        Список похожих сообщений с их метаданными
    """
    client = get_qdrant_client()
    if not client:
        return []
    
    try:
        search_results = client.search(
            collection_name=DIGEST_COLLECTION_NAME,
            query_vector=embedding,
            limit=limit,
            score_threshold=1.0 - DIGEST_SIMILARITY_THRESHOLD  # Конвертируем в расстояние
        )
        
        similar_messages = []
        for result in search_results:
            if result.score >= DIGEST_SIMILARITY_THRESHOLD:
                similar_messages.append({
                    'id': result.id,
                    'score': result.score,
                    'payload': result.payload
                })
        
        return similar_messages
    except Exception as e:
        logger.error(f"❌ Ошибка поиска похожих сообщений: {e}")
        return []


async def is_duplicate(embedding: List[float], threshold: Optional[float] = None) -> bool:
    """
    Проверить, является ли сообщение дубликатом
    
    Args:
        embedding: Векторное представление сообщения
        threshold: Порог схожести (если None, используется из конфига)
        
    Returns:
        True если найдено похожее сообщение
    """
    if threshold is None:
        threshold = DIGEST_SIMILARITY_THRESHOLD
    
    similar = await find_similar_messages(embedding, limit=1)
    return len(similar) > 0 and similar[0]['score'] >= threshold


async def store_message(embedding: List[float], message_data: Dict[str, Any]) -> bool:
    """
    Сохранить сообщение в векторную БД
    
    Args:
        embedding: Векторное представление сообщения
        message_data: Метаданные сообщения (текст, источник, время и т.д.)
        
    Returns:
        True если успешно сохранено
    """
    client = get_qdrant_client()
    if not client:
        return False
    
    try:
        # Генерируем уникальный ID
        point_id = str(uuid.uuid4())
        
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload=message_data
        )
        
        client.upsert(
            collection_name=DIGEST_COLLECTION_NAME,
            points=[point]
        )
        
        logger.debug(f"✅ Сообщение сохранено в Qdrant: {point_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения сообщения в Qdrant: {e}")
        return False

