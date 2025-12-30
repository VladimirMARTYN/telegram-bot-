#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для AI-обработки дайджестов
Включает создание эмбеддингов, классификацию и суммаризацию
"""

import logging
from typing import List, Dict, Any, Optional
from collections import defaultdict
from openai import OpenAI

from config import (
    OPENAI_API_KEY, DIGEST_EMBEDDING_MODEL, DIGEST_LLM_MODEL
)

logger = logging.getLogger(__name__)

# Глобальный клиент OpenAI
_openai_client: Optional[OpenAI] = None


def get_openai_client() -> Optional[OpenAI]:
    """Получить или создать клиент OpenAI"""
    global _openai_client
    
    if not OPENAI_API_KEY:
        logger.warning("⚠️ OpenAI API ключ не установлен")
        return None
    
    if _openai_client is None:
        try:
            _openai_client = OpenAI(api_key=OPENAI_API_KEY)
            logger.info("✅ OpenAI клиент инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации OpenAI: {e}")
            return None
    
    return _openai_client


async def create_embedding(text: str) -> Optional[List[float]]:
    """
    Создать эмбеддинг для текста
    
    Args:
        text: Текст для создания эмбеддинга
        
    Returns:
        Вектор эмбеддинга или None при ошибке
    """
    client = get_openai_client()
    if not client:
        return None
    
    try:
        response = client.embeddings.create(
            model=DIGEST_EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"❌ Ошибка создания эмбеддинга: {e}")
        return None


async def classify_topic(text: str) -> str:
    """
    Классифицировать новость по теме
    
    Args:
        text: Текст новости
        
    Returns:
        Название темы (категория)
    """
    client = get_openai_client()
    if not client:
        return "Другое"
    
    try:
        prompt = f"""Определи тему следующей новости. Верни только одно слово - название темы на русском языке.
Доступные темы: IT, Финансы, Политика, Экономика, Технологии, Криптовалюты, Бизнес, Наука, Спорт, Культура, Другое.

Новость: {text[:500]}

Тема:"""
        
        response = client.chat.completions.create(
            model=DIGEST_LLM_MODEL,
            messages=[
                {"role": "system", "content": "Ты помощник для классификации новостей. Отвечай только одним словом - названием темы."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=20
        )
        
        topic = response.choices[0].message.content.strip()
        return topic if topic else "Другое"
    except Exception as e:
        logger.error(f"❌ Ошибка классификации темы: {e}")
        return "Другое"


async def summarize_topic(news_list: List[Dict[str, Any]]) -> str:
    """
    Создать краткое резюме для группы новостей
    
    Args:
        news_list: Список новостей по одной теме
        
    Returns:
        Краткое резюме темы
    """
    client = get_openai_client()
    if not client:
        return "Новости по теме"
    
    try:
        # Формируем список новостей для суммаризации
        news_texts = []
        for news in news_list[:10]:  # Ограничиваем до 10 новостей
            text = news.get('text', '')
            source = news.get('source', '')
            if text:
                news_texts.append(f"[{source}]: {text[:200]}")
        
        news_content = "\n".join(news_texts)
        
        prompt = f"""Создай краткое резюме следующих новостей по одной теме. 
Резюме должно быть на русском языке, 2-3 предложения, выделяющее ключевые моменты.

Новости:
{news_content}

Краткое резюме:"""
        
        response = client.chat.completions.create(
            model=DIGEST_LLM_MODEL,
            messages=[
                {"role": "system", "content": "Ты помощник для создания кратких резюме новостей. Создавай информативные и лаконичные резюме."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=200
        )
        
        summary = response.choices[0].message.content.strip()
        return summary if summary else "Новости по теме"
    except Exception as e:
        logger.error(f"❌ Ошибка создания резюме: {e}")
        return "Новости по теме"


def group_news_by_topic(news_list: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Группировать новости по темам
    
    Args:
        news_list: Список новостей с полем 'topic'
        
    Returns:
        Словарь {тема: [список новостей]}
    """
    grouped = defaultdict(list)
    for news in news_list:
        topic = news.get('topic', 'Другое')
        grouped[topic].append(news)
    return dict(grouped)

