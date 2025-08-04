#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для тестирования работы с выходными днями
"""

import asyncio
import os
from datetime import datetime
import pytz
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Импортируем функции из admin_bot
import sys
sys.path.append('.')

from admin_bot import (
    get_indices_data,
    get_moex_stocks,
    get_commodities_data
)

async def test_weekend_data():
    """Тестирование работы с выходными днями"""
    print("🧪 Тестирование работы с выходными днями")
    print("=" * 50)
    
    # Проверяем текущий день недели
    moscow_tz = pytz.timezone('Europe/Moscow')
    current_moscow = datetime.now(moscow_tz)
    is_weekend = current_moscow.weekday() >= 5
    
    print(f"📅 Текущее время: {current_moscow.strftime('%H:%M:%S %d.%m.%Y')}")
    print(f"📅 День недели: {current_moscow.strftime('%A')}")
    print(f"📅 Выходной: {'Да' if is_weekend else 'Нет'}")
    print()
    
    # Тестируем индексы
    print("📊 Тестирование индексов:")
    print("-" * 30)
    indices_data = await get_indices_data()
    
    for index_name, data in indices_data.items():
        name = data.get('name', index_name)
        price = data.get('price')
        is_live = data.get('is_live', True)
        note = data.get('note', '')
        
        if price is not None:
            status = "🟢 Живые данные" if is_live else "🟡 Устаревшие данные"
            print(f"   {name}: {price} {status}")
        else:
            print(f"   {name}: 🔴 Торги закрыты {note}")
    
    print()
    
    # Тестируем акции
    print("📈 Тестирование акций:")
    print("-" * 30)
    stocks_data = await get_moex_stocks()
    
    # Показываем только несколько акций для примера
    sample_stocks = ['SBER', 'YDEX', 'GAZP', 'PIKK']
    
    for ticker in sample_stocks:
        if ticker in stocks_data:
            data = stocks_data[ticker]
            name = data.get('name', ticker)
            price = data.get('price')
            is_live = data.get('is_live', True)
            note = data.get('note', '')
            
            if price is not None:
                status = "🟢 Живые данные" if is_live else "🟡 Устаревшие данные"
                print(f"   {name}: {price} ₽ {status}")
            else:
                print(f"   {name}: 🔴 Торги закрыты {note}")
    
    print()
    
    # Тестируем товары (должны работать всегда)
    print("🛠️ Тестирование товаров:")
    print("-" * 30)
    commodities_data = await get_commodities_data()
    
    for commodity_name, data in commodities_data.items():
        name = data.get('name', commodity_name)
        price = data.get('price')
        if price is not None:
            print(f"   {name}: ${price}")
        else:
            print(f"   {name}: ❌ Н/Д")
    
    print()
    print("✅ Тестирование завершено!")

def main():
    """Основная функция"""
    print("🔧 Тестирование работы с выходными днями")
    print("=" * 60)
    
    # Запускаем тест
    asyncio.run(test_weekend_data())
    
    print("\n" + "=" * 60)
    print("📋 Результаты:")
    print("• Индексы должны показывать статус торгов")
    print("• Акции должны быть недоступны по выходным")
    print("• Товары должны работать всегда")
    print("• S&P 500 должен работать всегда")

if __name__ == '__main__':
    main() 