#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Утилиты для бота
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, Awaitable
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)

# Глобальный кэш
api_cache: Dict[str, Dict[str, Any]] = {}


def is_admin(user_id: int) -> bool:
    """Проверка прав администратора"""
    from config import ADMIN_USER_ID
    return user_id == ADMIN_USER_ID


async def get_cached_data(
    cache_key: str,
    fetch_func: Callable[[], Awaitable[Any]],
    ttl: int = 60
) -> Any:
    """
    Получить данные с кэшированием
    
    Args:
        cache_key: Ключ кэша
        fetch_func: Асинхронная функция для получения данных
        ttl: Время жизни кэша в секундах
    
    Returns:
        Данные из кэша или результат fetch_func
    """
    now = datetime.now()
    
    # Проверяем кэш
    if cache_key in api_cache:
        cached_data = api_cache[cache_key]
        cache_timestamp = cached_data.get('timestamp')
        
        if cache_timestamp and (now - cache_timestamp).total_seconds() < ttl:
            logger.debug(f"Кэш попадание для ключа: {cache_key}")
            return cached_data['data']
    
    # Получаем свежие данные
    logger.debug(f"Кэш промах для ключа: {cache_key}, запрашиваем свежие данные")
    data = await fetch_func()
    
    # Сохраняем в кэш
    api_cache[cache_key] = {
        'data': data,
        'timestamp': now
    }
    
    return data


def clear_cache(cache_key: Optional[str] = None):
    """
    Очистить кэш
    
    Args:
        cache_key: Если указан, очищает только этот ключ, иначе весь кэш
    """
    if cache_key:
        if cache_key in api_cache:
            del api_cache[cache_key]
            logger.debug(f"Очищен кэш для ключа: {cache_key}")
    else:
        api_cache.clear()
        logger.info("Весь кэш очищен")


async def fetch_with_retry(
    fetch_func: Callable[[], Awaitable[Any]],
    max_attempts: int = 3,
    delay_min: int = 2,
    delay_max: int = 10
) -> Any:
    """
    Выполнить запрос с повторными попытками при ошибке
    
    Args:
        fetch_func: Асинхронная функция для выполнения
        max_attempts: Максимальное количество попыток
        delay_min: Минимальная задержка между попытками (секунды)
        delay_max: Максимальная задержка между попытками (секунды)
    
    Returns:
        Результат выполнения функции
    
    Raises:
        Exception: Если все попытки неудачны
    """
    last_exception = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            return await fetch_func()
        except Exception as e:
            last_exception = e
            if attempt < max_attempts:
                # Экспоненциальная задержка
                delay = min(delay_min * (2 ** (attempt - 1)), delay_max)
                logger.warning(f"Попытка {attempt}/{max_attempts} неудачна, повтор через {delay}с: {e}")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Все {max_attempts} попыток неудачны")
    
    raise last_exception


def validate_positive_number(value: str, min_value: float = 0.01) -> float:
    """
    Валидация положительного числа
    
    Args:
        value: Строковое значение для проверки
        min_value: Минимальное допустимое значение
    
    Returns:
        Проверенное числовое значение
    
    Raises:
        ValueError: Если значение невалидно
    """
    try:
        num = float(value)
        if num < min_value:
            raise ValueError(f"Значение должно быть больше {min_value}")
        return num
    except (ValueError, TypeError) as e:
        if isinstance(e, ValueError) and "больше" in str(e):
            raise
        raise ValueError(f"Значение должно быть числом: {value}")


def validate_asset(asset: str) -> bool:
    """
    Валидация актива
    
    Args:
        asset: Символ актива
    
    Returns:
        True если актив поддерживается
    """
    from config import SUPPORTED_CURRENCIES, SUPPORTED_CRYPTO, SUPPORTED_STOCKS
    
    asset_upper = asset.upper()
    all_assets = SUPPORTED_CURRENCIES + SUPPORTED_CRYPTO + SUPPORTED_STOCKS
    
    return asset_upper in all_assets


def escape_html(text: str) -> str:
    """
    Экранирование HTML символов
    
    Args:
        text: Текст для экранирования
    
    Returns:
        Экранированный текст
    """
    from html import escape
    return escape(str(text))


def format_price(price: float, decimal_places: int = 2) -> str:
    """
    Форматирование цены с разделителями тысяч
    
    Args:
        price: Цена для форматирования
        decimal_places: Количество знаков после запятой
    
    Returns:
        Отформатированная строка
    """
    if isinstance(price, (int, float)):
        return f"{price:,.{decimal_places}f}".replace(',', ' ')
    return str(price)

