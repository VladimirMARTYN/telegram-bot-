#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import sys
import os

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импортируем функцию из бота
from admin_bot import get_indices_data

async def test_fixed_indices():
    """Тестируем исправленную функцию получения индексов"""
    
    print("🔍 ТЕСТИРОВАНИЕ ИСПРАВЛЕННОЙ ФУНКЦИИ ПОЛУЧЕНИЯ ИНДЕКСОВ")
    print("=" * 70)
    
    try:
        # Вызываем исправленную функцию
        indices_data = await get_indices_data()
        
        print(f"📊 Получено индексов: {len(indices_data)}")
        print(f"📋 Список индексов: {list(indices_data.keys())}")
        print()
        
        # Проверяем каждый индекс
        for index_id, index_data in indices_data.items():
            print(f"📈 {index_id.upper()}:")
            print(f"   Название: {index_data.get('name', 'Н/Д')}")
            print(f"   Цена: {index_data.get('price', 'Н/Д')}")
            print(f"   Изменение: {index_data.get('change_pct', 'Н/Д')}%")
            print(f"   Живые данные: {'✅ Да' if index_data.get('is_live', False) else '❌ Нет'}")
            
            if 'note' in index_data:
                print(f"   Примечание: {index_data['note']}")
            
            if 'update_time' in index_data:
                print(f"   Время обновления: {index_data['update_time']}")
            
            print()
        
        # Проверяем конкретные значения
        if 'imoex' in indices_data:
            imoex = indices_data['imoex']
            print("🔍 ДЕТАЛЬНАЯ ПРОВЕРКА IMOEX:")
            print(f"   Цена: {imoex.get('price')}")
            print(f"   Изменение: {imoex.get('change_pct')}%")
            print(f"   Тип цены: {type(imoex.get('price'))}")
            print(f"   Тип изменения: {type(imoex.get('change_pct'))}")
            
            # Проверяем валидность данных
            if imoex.get('price') and imoex.get('price') > 0:
                print("   ✅ Цена валидна")
            else:
                print("   ❌ Цена невалидна")
                
            if imoex.get('change_pct') is not None:
                print("   ✅ Изменение валидно")
            else:
                print("   ❌ Изменение невалидно")
        
        if 'rts' in indices_data:
            rts = indices_data['rts']
            print("\n🔍 ДЕТАЛЬНАЯ ПРОВЕРКА RTS:")
            print(f"   Цена: {rts.get('price')}")
            print(f"   Изменение: {rts.get('change_pct')}%")
            print(f"   Тип цены: {type(rts.get('price'))}")
            print(f"   Тип изменения: {type(rts.get('change_pct'))}")
            
            # Проверяем валидность данных
            if rts.get('price') and rts.get('price') > 0:
                print("   ✅ Цена валидна")
            else:
                print("   ❌ Цена невалидна")
                
            if rts.get('change_pct') is not None:
                print("   ✅ Изменение валидно")
            else:
                print("   ❌ Изменение невалидно")
        
        print("\n" + "=" * 70)
        print("✅ Тест завершен успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        import traceback
        print(f"📋 Трассировка: {traceback.format_exc()}")

if __name__ == "__main__":
    asyncio.run(test_fixed_indices())
