#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Утилиты для бота
"""

import logging
import os
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, Awaitable
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)
_rates_file_lock = threading.RLock()

# Глобальный кэш
api_cache: Dict[str, Dict[str, Any]] = {}

# Файл для хранения последних известных значений
from config import LAST_KNOWN_RATES_FILE


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


def save_last_known_rate(asset: str, rate: float) -> None:
    """
    Сохранить последний известный курс
    
    Args:
        asset: Название актива (например, 'USD_RUB', 'GOLD_SILVER_RATIO')
        rate: Значение курса/соотношения
    """
    try:
        with _rates_file_lock:
            if os.path.exists(LAST_KNOWN_RATES_FILE):
                with open(LAST_KNOWN_RATES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {}
            
            data[asset] = {
                'rate': rate,
                'timestamp': datetime.now().isoformat()
            }
            
            temp_path = f"{LAST_KNOWN_RATES_FILE}.tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, LAST_KNOWN_RATES_FILE)
        
        logger.debug(f"Сохранен последний известный курс {asset}: {rate:.2f}")
    except Exception as e:
        logger.error(f"Ошибка сохранения последнего курса {asset}: {e}")


def get_last_known_rate(asset: str, max_age_hours: int = 24) -> Optional[float]:
    """
    Получить последний известный курс (если не старше max_age_hours)
    
    Args:
        asset: Название актива
        max_age_hours: Максимальный возраст данных в часах
    
    Returns:
        Значение курса или None если данных нет или они устарели
    """
    try:
        with _rates_file_lock:
            if not os.path.exists(LAST_KNOWN_RATES_FILE):
                return None
            
            with open(LAST_KNOWN_RATES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        if asset not in data:
            return None
        
        rate_info = data[asset]
        timestamp = datetime.fromisoformat(rate_info['timestamp'])
        age_hours = (datetime.now() - timestamp).total_seconds() / 3600
        
        if age_hours <= max_age_hours:
            rate = rate_info['rate']
            logger.debug(f"Загружен последний известный курс {asset}: {rate:.2f} (возраст: {age_hours:.1f}ч)")
            return rate
        else:
            logger.debug(f"Последний курс {asset} устарел ({age_hours:.1f} часов)")
            return None
    except Exception as e:
        logger.error(f"Ошибка загрузки последнего курса {asset}: {e}")
        return None
