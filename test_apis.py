#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Диагностический скрипт для тестирования всех API
Используем те же ключи, что в API_KEYS_SETUP.md
"""

import requests
import json
import asyncio
import aiohttp
import os

# API ключи из вашего файла API_KEYS_SETUP.md
METALPRICEAPI_KEY = "0ffbfc712d62b83c3b468dc8825d5996"
API_NINJAS_KEY = "Tw5FaoqA8cwozmB1LwwpPg==iAh7DmlllQsEdCP2" 
FMP_API_KEY = "nDUH3x20LtRAXJbWegUsDmBn0tyGvBxv"
ALPHA_VANTAGE_KEY = "HI5HFCXVYJDLEKIC"

def test_metalpriceapi():
    """Тест MetalpriceAPI для золота и серебра"""
    print("🥇 === ТЕСТ METALPRICEAPI ===")
    try:
        url = f"https://api.metalpriceapi.com/v1/latest?access_key={METALPRICEAPI_KEY}&base=USD&symbols=XAU,XAG"
        print(f"URL: {url}")
        
        response = requests.get(url, timeout=10)
        print(f"Статус: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Ответ: {json.dumps(data, indent=2)}")
            
            if 'rates' in data:
                rates = data['rates']
                print(f"Доступные металлы: {list(rates.keys())}")
                
                # Золото
                if 'USDXAU' in rates:
                    gold_price = 1 / rates['USDXAU']
                    print(f"✅ Золото: ${gold_price:.2f}")
                else:
                    print("❌ USDXAU не найден")
                
                # Серебро
                if 'USDXAG' in rates:
                    silver_price = 1 / rates['USDXAG']
                    print(f"✅ Серебро: ${silver_price:.2f}")
                else:
                    print("❌ USDXAG не найден")
            else:
                print("❌ 'rates' не найдены в ответе")
        else:
            print(f"❌ Ошибка: {response.text}")
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
    
    print()

def test_api_ninjas():
    """Тест API Ninjas для нефти"""
    print("🛢️ === ТЕСТ API NINJAS ===")
    try:
        url = "https://api.api-ninjas.com/v1/commodityprice?name=brent_crude_oil"
        headers = {'X-Api-Key': API_NINJAS_KEY}
        print(f"URL: {url}")
        print(f"Headers: {headers}")
        
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Статус: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Ответ: {json.dumps(data, indent=2)}")
            
            if 'price' in data:
                print(f"✅ Нефть Brent: ${data['price']:.2f}")
            else:
                print("❌ 'price' не найден в ответе")
        else:
            print(f"❌ Ошибка: {response.text}")
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
    
    print()

async def test_moex():
    """Тест MOEX для российских индексов"""
    print("📊 === ТЕСТ MOEX ===")
    try:
        async with aiohttp.ClientSession() as session:
            # IMOEX
            imoex_url = "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json"
            print(f"IMOEX URL: {imoex_url}")
            
            async with session.get(imoex_url) as resp:
                print(f"IMOEX статус: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    print(f"IMOEX структура: {list(data.keys()) if isinstance(data, dict) else 'не dict'}")
                    
                    if 'marketdata' in data:
                        print(f"IMOEX marketdata найден")
                        if 'data' in data['marketdata'] and len(data['marketdata']['data']) > 0:
                            print(f"IMOEX колонки: {data['marketdata']['columns']}")
                            print(f"IMOEX первая строка: {data['marketdata']['data'][0]}")
                            
                            row_data = dict(zip(data['marketdata']['columns'], data['marketdata']['data'][0]))
                            if 'LAST' in row_data and row_data['LAST']:
                                print(f"✅ IMOEX: {row_data['LAST']}")
                            else:
                                print(f"❌ IMOEX: нет LAST или пустой: {row_data.get('LAST')}")
                        else:
                            print("❌ IMOEX: нет данных")
                    else:
                        print("❌ IMOEX: нет marketdata")
                else:
                    text = await resp.text()
                    print(f"❌ IMOEX ошибка {resp.status}: {text[:200]}...")
            
            # RTS  
            rts_url = "https://iss.moex.com/iss/engines/stock/markets/index/securities/RTSI.json"
            print(f"RTS URL: {rts_url}")
            
            async with session.get(rts_url) as resp:
                print(f"RTS статус: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    print(f"RTS структура: {list(data.keys()) if isinstance(data, dict) else 'не dict'}")
                    
                    if 'marketdata' in data:
                        print(f"RTS marketdata найден")
                        if 'data' in data['marketdata'] and len(data['marketdata']['data']) > 0:
                            print(f"RTS колонки: {data['marketdata']['columns']}")
                            print(f"RTS первая строка: {data['marketdata']['data'][0]}")
                            
                            row_data = dict(zip(data['marketdata']['columns'], data['marketdata']['data'][0]))
                            if 'LAST' in row_data and row_data['LAST']:
                                print(f"✅ RTS: {row_data['LAST']}")
                            else:
                                print(f"❌ RTS: нет LAST или пустой: {row_data.get('LAST')}")
                        else:
                            print("❌ RTS: нет данных")
                    else:
                        print("❌ RTS: нет marketdata")
                else:
                    text = await resp.text()
                    print(f"❌ RTS ошибка {resp.status}: {text[:200]}...")
                    
    except Exception as e:
        print(f"❌ MOEX исключение: {e}")
    
    print()

def test_fmp():
    """Тест FMP для S&P 500"""
    print("📈 === ТЕСТ FMP ===")
    try:
        url = f"https://financialmodelingprep.com/api/v3/quote/%5EGSPC?apikey={FMP_API_KEY}"
        print(f"URL: {url}")
        
        response = requests.get(url, timeout=10)
        print(f"Статус: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Ответ: {json.dumps(data, indent=2)}")
            
            if isinstance(data, list) and len(data) > 0:
                sp500_info = data[0]
                if 'price' in sp500_info:
                    print(f"✅ S&P 500: {sp500_info['price']}")
                else:
                    print("❌ 'price' не найден")
            else:
                print("❌ Ответ не список или пустой")
        else:
            print(f"❌ Ошибка: {response.text}")
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
    
    print()

def test_coingecko():
    """Тест CoinGecko для криптовалют"""
    print("💰 === ТЕСТ COINGECKO ===")
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,the-open-network,ripple,cardano,solana,dogecoin&vs_currencies=usd"
        print(f"URL: {url}")
        
        response = requests.get(url, timeout=10)
        print(f"Статус: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Криптовалюты найдены: {list(data.keys())}")
            
            for crypto, info in data.items():
                if 'usd' in info:
                    print(f"✅ {crypto}: ${info['usd']}")
                else:
                    print(f"❌ {crypto}: нет usd цены")
        else:
            print(f"❌ Ошибка: {response.text}")
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
    
    print()

async def main():
    """Запуск всех тестов"""
    print("🔍 === ДИАГНОСТИКА API ===")
    print("Тестируем все API с реальными ключами\n")
    
    test_metalpriceapi()
    test_api_ninjas()
    await test_moex()
    test_fmp()
    test_coingecko()
    
    print("🎯 === ЗАКЛЮЧЕНИЕ ===")
    print("Если какой-то API не работает, проверьте:")
    print("1. Правильность API ключей")
    print("2. Лимиты бесплатного плана")
    print("3. Статус сервисов API")
    print("4. Правильность URL и параметров")

if __name__ == "__main__":
    asyncio.run(main()) 