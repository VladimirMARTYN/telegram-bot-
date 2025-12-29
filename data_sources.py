#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для получения данных из различных источников
Все запросы асинхронные с использованием aiohttp
"""

import logging
import aiohttp
import json
from typing import Dict, Any, Optional
from datetime import datetime
import pytz

from config import (
    CACHE_TTL_CURRENCIES, CACHE_TTL_CRYPTO, CACHE_TTL_STOCKS,
    CACHE_TTL_COMMODITIES, CACHE_TTL_INDICES, API_TIMEOUT,
    API_RETRY_ATTEMPTS, API_RETRY_DELAY_MIN, API_RETRY_DELAY_MAX,
    URALS_DISCOUNT, EIA_API_KEY, ALPHA_VANTAGE_KEY,
    GOLD_SILVER_RATIO, USO_TO_BRENT_MULTIPLIER
)
from utils import get_cached_data, fetch_with_retry, save_last_known_rate, get_last_known_rate

logger = logging.getLogger(__name__)

# Используем просто число для таймаута, чтобы избежать проблем с контекстным менеджером
_TIMEOUT = API_TIMEOUT


async def safe_json_response(resp: aiohttp.ClientResponse) -> Any:
    """
    Безопасное получение JSON из ответа с обработкой ошибок Content-Type
    
    Args:
        resp: Объект ответа aiohttp
        
    Returns:
        Распарсенный JSON объект
    """
    try:
        return await resp.json()
    except aiohttp.client_exceptions.ContentTypeError:
        # Если Content-Type неправильный, получаем текст и парсим вручную
        text = await resp.text(encoding='utf-8')
        return json.loads(text)


async def get_cbr_rates(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Получить курсы валют ЦБ РФ"""
    async def _fetch():
        async with session.get(
            "https://www.cbr-xml-daily.ru/daily_json.js",
            timeout=_TIMEOUT
        ) as resp:
            resp.raise_for_status()
            # ЦБ РФ возвращает application/javascript, используем безопасную функцию
            return await safe_json_response(resp)
    
    return await fetch_with_retry(
        _fetch,
        max_attempts=API_RETRY_ATTEMPTS,
        delay_min=API_RETRY_DELAY_MIN,
        delay_max=API_RETRY_DELAY_MAX
    )


async def get_forex_rates(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Получить курсы валют с FOREX"""
    async def _fetch():
        async with session.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=_TIMEOUT
        ) as resp:
            resp.raise_for_status()
            return await safe_json_response(resp)
    
    return await fetch_with_retry(
        _fetch,
        max_attempts=API_RETRY_ATTEMPTS,
        delay_min=API_RETRY_DELAY_MIN,
        delay_max=API_RETRY_DELAY_MAX
    )


async def get_crypto_data(session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
    """Получить данные криптовалют с резервными источниками"""
    crypto_data = {}
    
    # Список криптовалют для мониторинга
    crypto_list = [
        {'id': 'bitcoin', 'symbol': 'BTC', 'name': 'Bitcoin'},
        {'id': 'ethereum', 'symbol': 'ETH', 'name': 'Ethereum'},
        {'id': 'the-open-network', 'symbol': 'TON', 'name': 'TON'},
        {'id': 'ripple', 'symbol': 'XRP', 'name': 'XRP'},
        {'id': 'cardano', 'symbol': 'ADA', 'name': 'Cardano'},
        {'id': 'solana', 'symbol': 'SOL', 'name': 'Solana'},
        {'id': 'dogecoin', 'symbol': 'DOGE', 'name': 'Dogecoin'},
        {'id': 'tether', 'symbol': 'USDT', 'name': 'Tether'}
    ]
    
    # 1. Пробуем CoinGecko (основной источник)
    logger.debug("Пробуем получить данные криптовалют с CoinGecko...")
    try:
        crypto_ids = ','.join([crypto['id'] for crypto in crypto_list])
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_ids}&vs_currencies=usd&include_24hr_change=true"
        
        async with session.get(url, timeout=_TIMEOUT) as resp:
            if resp.status == 200:
                data = await safe_json_response(resp)
                
                for crypto in crypto_list:
                    crypto_id = crypto['id']
                    if crypto_id in data:
                        price = data[crypto_id].get('usd')
                        change_24h = data[crypto_id].get('usd_24h_change', 0)
                        
                        if price is not None:
                            crypto_data[crypto_id] = {
                                'price': price,
                                'change_24h': change_24h,
                                'source': 'CoinGecko'
                            }
                
                if crypto_data:
                    logger.info(f"✅ CoinGecko: получены данные для {len(crypto_data)} криптовалют")
                    return crypto_data
                    
    except Exception as e:
        logger.error(f"❌ Ошибка CoinGecko: {e}")
    
    # 2. Пробуем Coinbase API (резервный источник)
    logger.debug("Пробуем получить данные криптовалют с Coinbase...")
    try:
        for crypto in crypto_list:
            symbol = crypto['symbol']
            try:
                url = f"https://api.coinbase.com/v2/prices/{symbol}-USD/spot"
                async with session.get(url, timeout=_TIMEOUT) as resp:
                    if resp.status == 200:
                        data = await safe_json_response(resp)
                        price = float(data['data']['amount'])
                        
                        crypto_id = crypto['id']
                        crypto_data[crypto_id] = {
                            'price': price,
                            'change_24h': 0,
                            'source': 'Coinbase'
                        }
            except Exception as e:
                logger.debug(f"Ошибка получения {symbol} с Coinbase: {e}")
                continue
        
        if crypto_data:
            logger.info(f"✅ Coinbase: получены данные для {len(crypto_data)} криптовалют")
            return crypto_data
            
    except Exception as e:
        logger.error(f"❌ Общая ошибка Coinbase: {e}")
    
    # 3. Пробуем Binance API
    logger.debug("Пробуем получить данные криптовалют с Binance...")
    try:
        for crypto in crypto_list:
            symbol = f"{crypto['symbol']}USDT"
            try:
                url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
                async with session.get(url, timeout=_TIMEOUT) as resp:
                    if resp.status == 200:
                        data = await safe_json_response(resp)
                        price = float(data['price'])
                        
                        crypto_id = crypto['id']
                        crypto_data[crypto_id] = {
                            'price': price,
                            'change_24h': 0,
                            'source': 'Binance'
                        }
            except Exception as e:
                logger.debug(f"Ошибка получения {symbol} с Binance: {e}")
                continue
        
        if crypto_data:
            logger.info(f"✅ Binance: получены данные для {len(crypto_data)} криптовалют")
            return crypto_data
            
    except Exception as e:
        logger.error(f"❌ Общая ошибка Binance: {e}")
    
    logger.warning("⚠️ Все источники криптовалют недоступны")
    return crypto_data


async def get_moex_stocks(session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
    """Получить данные акций с Московской биржи"""
    stocks_data = {}
    
    # Проверяем, является ли сегодня торговым днем
    moscow_tz = pytz.timezone('Europe/Moscow')
    current_moscow = datetime.now(moscow_tz)
    is_weekend = current_moscow.weekday() >= 5
    
    logger.debug(f"Проверка торговых дней: {'Выходной' if is_weekend else 'Торговый день'}")
    
    # Список акций для мониторинга
    stocks = {
        'SBER': {'name': 'Сбер', 'emoji': '🟢'},
        'YDEX': {'name': 'Яндекс', 'emoji': '🔴'},
        'VKCO': {'name': 'ВК', 'emoji': '🔵'},
        'T': {'name': 'Т-Технологии', 'emoji': '🟡'},
        'GAZP': {'name': 'Газпром', 'emoji': '💎'},
        'GMKN': {'name': 'Норникель', 'emoji': '⚡'},
        'ROSN': {'name': 'Роснефть', 'emoji': '🛢️'},
        'LKOH': {'name': 'ЛУКОЙЛ', 'emoji': '⛽'},
        'MTSS': {'name': 'МТС', 'emoji': '📱'},
        'MFON': {'name': 'Мегафон', 'emoji': '📶'},
        'PIKK': {'name': 'ПИК', 'emoji': '🏗️'},
        'SMLT': {'name': 'Самолёт', 'emoji': '✈️'}
    }
    
    # Если выходной день, возвращаем пустые данные
    if is_weekend:
        logger.debug("Выходной день - торги на MOEX закрыты")
        for ticker, info in stocks.items():
            stocks_data[ticker] = {
                'name': info['name'],
                'emoji': info['emoji'],
                'price': None,
                'change': 0,
                'change_pct': 0,
                'is_live': False,
                'note': 'Торги закрыты'
            }
        return stocks_data
    
    try:
        trading_url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
        params = {
            'securities': ','.join(stocks.keys()),
            'iss.meta': 'off',
            'iss.only': 'securities,marketdata'
        }
        
        async with session.get(
            trading_url,
            params=params,
            timeout=_TIMEOUT
        ) as resp:
            if resp.status == 200:
                data = await safe_json_response(resp)
                
                securities_data = {}
                marketdata = {}
                
                if 'securities' in data and 'data' in data['securities']:
                    securities_cols = data['securities']['columns']
                    for row in data['securities']['data']:
                        row_data = dict(zip(securities_cols, row))
                        secid = row_data.get('SECID')
                        if secid in stocks:
                            securities_data[secid] = {
                                'shortname': row_data.get('SHORTNAME', stocks[secid]['name']),
                                'lotsize': row_data.get('LOTSIZE', 1)
                            }
                
                if 'marketdata' in data and 'data' in data['marketdata']:
                    marketdata_cols = data['marketdata']['columns']
                    for row in data['marketdata']['data']:
                        row_data = dict(zip(marketdata_cols, row))
                        secid = row_data.get('SECID')
                        if secid in stocks:
                            marketdata[secid] = {
                                'last': row_data.get('LAST'),
                                'change': row_data.get('CHANGE'),
                                'changeprcnt': row_data.get('CHANGEPRCNT'),
                                'volume': row_data.get('VALTODAY'),
                                'open': row_data.get('OPEN'),
                                'high': row_data.get('HIGH'),
                                'low': row_data.get('LOW')
                            }
                
                # Объединяем данные
                for ticker in stocks:
                    if ticker in securities_data or ticker in marketdata:
                        stocks_data[ticker] = {
                            'name': stocks[ticker]['name'],
                            'emoji': stocks[ticker]['emoji'],
                            'shortname': securities_data.get(ticker, {}).get('shortname', stocks[ticker]['name']),
                            'price': marketdata.get(ticker, {}).get('last'),
                            'change': marketdata.get(ticker, {}).get('change'),
                            'change_pct': marketdata.get(ticker, {}).get('changeprcnt'),
                            'volume': marketdata.get(ticker, {}).get('volume'),
                            'open': marketdata.get(ticker, {}).get('open'),
                            'high': marketdata.get(ticker, {}).get('high'),
                            'low': marketdata.get(ticker, {}).get('low')
                        }
    
    except Exception as e:
        logger.error(f"Ошибка получения данных MOEX: {e}")
    
    return stocks_data


async def get_commodities_data(session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
    """Получить данные по товарам"""
    commodities_data = {}
    
    try:
        # Золото
        logger.debug("Запрашиваю золото с Gold-API.com...")
        try:
            async with session.get(
                "https://api.gold-api.com/price/XAU",
                timeout=_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    gold_data = await safe_json_response(resp)
                    if 'price' in gold_data:
                        gold_price = gold_data['price']
                        commodities_data['gold'] = {
                            'name': 'Золото',
                            'price': gold_price,
                            'currency': 'USD'
                        }
                        logger.info(f"✅ Золото получено: ${gold_price:.2f}")
                        
                        # Сохраняем цену золота для расчета соотношений
                        save_last_known_rate('GOLD_PRICE', gold_price)
        except Exception as e:
            logger.error(f"Ошибка запроса золота: {e}")
        
        # Серебро
        logger.debug("Запрашиваю серебро с Gold-API.com...")
        try:
            async with session.get(
                "https://api.gold-api.com/price/XAG",
                timeout=_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    silver_data = await safe_json_response(resp)
                    if 'price' in silver_data:
                        silver_price = silver_data['price']
                        commodities_data['silver'] = {
                            'name': 'Серебро',
                            'price': silver_price,
                            'currency': 'USD'
                        }
                        logger.info(f"✅ Серебро получено: ${silver_price:.2f}")
                        
                        # Сохраняем цену серебра и соотношение с золотом
                        save_last_known_rate('SILVER_PRICE', silver_price)
                        if 'gold' in commodities_data:
                            gold_price = commodities_data['gold']['price']
                            ratio = gold_price / silver_price
                            save_last_known_rate('GOLD_SILVER_RATIO', ratio)
                            logger.debug(f"Соотношение золото/серебро: {ratio:.2f}:1")
        except Exception as e:
            logger.error(f"Ошибка запроса серебра: {e}")
        
        # Нефть Brent из EIA API
        logger.debug("Запрашиваю нефть Brent из EIA API...")
        try:
            url = f"https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key={EIA_API_KEY}&facets[product][]=EPCBRENT&data[0]=value&sort[0][column]=period&sort[0][direction]=desc&length=1"
            async with session.get(url, timeout=_TIMEOUT) as resp:
                if resp.status == 200:
                    brent_data = await safe_json_response(resp)
                    if 'response' in brent_data and 'data' in brent_data['response'] and len(brent_data['response']['data']) > 0:
                        brent_price = float(brent_data['response']['data'][0]['value'])
                        commodities_data['brent'] = {
                            'name': 'Нефть Brent',
                            'price': brent_price,
                            'currency': 'USD'
                        }
                        logger.info(f"✅ Нефть Brent получена: ${brent_price:.2f}")
                        
                        # Сохраняем цену Brent для расчета соотношений
                        save_last_known_rate('BRENT_PRICE', brent_price)
        except Exception as e:
            logger.error(f"Ошибка запроса Brent из EIA: {e}")
        
        # Fallback: Alpha Vantage для нефти через USO ETF
        if 'brent' not in commodities_data:
            logger.debug("EIA не сработал, пробуем Alpha Vantage USO ETF...")
            try:
                url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=USO&apikey={ALPHA_VANTAGE_KEY}"
                async with session.get(url, timeout=_TIMEOUT) as resp:
                    if resp.status == 200:
                        oil_data = await safe_json_response(resp)
                        if 'Global Quote' in oil_data and '05. price' in oil_data['Global Quote']:
                            uso_price = float(oil_data['Global Quote']['05. price'])
                            
                            # Получаем последнее известное соотношение или используем константу
                            last_multiplier = get_last_known_rate('USO_TO_BRENT', max_age_hours=24)
                            
                            if last_multiplier:
                                estimated_brent = uso_price * last_multiplier
                                logger.debug(f"Используется последнее известное соотношение USO→Brent: {last_multiplier:.3f}")
                            else:
                                # Используем константу из config (правильное значение ~1.3-1.5)
                                estimated_brent = uso_price * USO_TO_BRENT_MULTIPLIER
                                logger.debug(f"Используется константа соотношения USO→Brent: {USO_TO_BRENT_MULTIPLIER:.3f}")
                            
                            commodities_data['brent'] = {
                                'name': 'Нефть Brent (приблиз.)',
                                'price': estimated_brent,
                                'currency': 'USD',
                                'note': 'Рассчитано от USO ETF'
                            }
                            logger.info(f"✅ Нефть Brent (USO fallback): ${estimated_brent:.2f}")
                            
                            # Сохраняем соотношение для будущего использования (если есть реальная цена Brent)
                            if 'brent' in commodities_data and 'price' in commodities_data['brent']:
                                actual_brent = commodities_data['brent']['price']
                                if actual_brent > 0 and uso_price > 0:
                                    actual_multiplier = actual_brent / uso_price
                                    save_last_known_rate('USO_TO_BRENT', actual_multiplier)
            except Exception as e:
                logger.error(f"Ошибка Alpha Vantage USO: {e}")
        
        # Fallback для серебра
        if 'silver' not in commodities_data and 'gold' in commodities_data:
            logger.debug("Серебро недоступно, рассчитываем от золота...")
            gold_price = commodities_data['gold']['price']
            
            # Пробуем получить последнее известное соотношение (не старше недели)
            last_ratio = get_last_known_rate('GOLD_SILVER_RATIO', max_age_hours=168)
            
            if last_ratio:
                silver_fallback = gold_price / last_ratio
                logger.debug(f"Используется последнее известное соотношение золото/серебро: {last_ratio:.2f}:1")
            else:
                # Используем константу из config
                silver_fallback = gold_price / GOLD_SILVER_RATIO
                logger.debug(f"Используется константа соотношения золото/серебро: {GOLD_SILVER_RATIO:.2f}:1")
            
            commodities_data['silver'] = {
                'name': 'Серебро (расчетное)',
                'price': silver_fallback,
                'currency': 'USD',
                'note': 'Рассчитано от золота'
            }
            logger.info(f"✅ Серебро рассчитано: ${silver_fallback:.2f}")
        
        # Рассчитываем Urals от Brent
        if 'brent' in commodities_data:
            logger.debug("Рассчитываем Urals от Brent...")
            brent_price = commodities_data['brent']['price']
            urals_price = brent_price - URALS_DISCOUNT
            commodities_data['urals'] = {
                'name': 'Нефть Urals (расчетная)',
                'price': urals_price,
                'currency': 'USD'
            }
            logger.info(f"✅ Urals рассчитана: ${urals_price:.2f}")
    
    except Exception as e:
        logger.error(f"Общая ошибка получения данных товаров: {e}")
    
    return commodities_data


async def get_indices_data(session: aiohttp.ClientSession) -> Dict[str, Dict[str, Any]]:
    """Получить данные фондовых индексов"""
    indices_data = {}
    
    try:
        # IMOEX и RTS с MOEX (запрашиваем всегда, проверяем данные)
        logger.debug("Запрашиваю индексы MOEX...")
        try:
            async with session.get(
                "https://iss.moex.com/iss/engines/stock/markets/index/boards/SNDX/securities.json",
                params={'iss.meta': 'off', 'iss.only': 'securities,marketdata'},
                timeout=_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    data = await safe_json_response(resp)
                    
                    # Парсим IMOEX и RTS
                    if 'marketdata' in data and 'data' in data['marketdata']:
                        marketdata_cols = data['marketdata']['columns']
                        for row in data['marketdata']['data']:
                            row_data = dict(zip(marketdata_cols, row))
                            secid = row_data.get('SECID')
                            
                            if secid == 'IMOEX':
                                last_value = row_data.get('LAST')
                                # Используем LAST, CURRENTVALUE или PREVPRICE
                                price = last_value or row_data.get('CURRENTVALUE') or row_data.get('PREVPRICE')
                                if price:
                                    indices_data['imoex'] = {
                                        'name': 'IMOEX',
                                        'price': price,
                                        'change_pct': row_data.get('CHANGEPRCNT', 0),
                                        'is_live': last_value is not None  # Live если есть LAST
                                    }
                            elif secid == 'RTSI':
                                last_value = row_data.get('LAST')
                                price = last_value or row_data.get('CURRENTVALUE') or row_data.get('PREVPRICE')
                                if price:
                                    indices_data['rts'] = {
                                        'name': 'RTS',
                                        'price': price,
                                        'change_pct': row_data.get('CHANGEPRCNT', 0),
                                        'is_live': last_value is not None
                                    }
        except Exception as e:
            logger.error(f"Ошибка получения индексов MOEX: {e}")
        
        # S&P 500 через FMP (основной источник) или Alpha Vantage
        logger.debug("Запрашиваю S&P 500...")
        try:
            # Пробуем FMP сначала
            from config import FMP_API_KEY
            if FMP_API_KEY and FMP_API_KEY != 'demo':
                url = f"https://financialmodelingprep.com/api/v3/quote/%5EGSPC?apikey={FMP_API_KEY}"
                async with session.get(url, timeout=_TIMEOUT) as resp:
                    if resp.status == 200:
                        sp500_data = await safe_json_response(resp)
                        if isinstance(sp500_data, list) and len(sp500_data) > 0:
                            sp500_info = sp500_data[0]
                            if 'price' in sp500_info:
                                indices_data['sp500'] = {
                                    'name': 'S&P 500',
                                    'price': sp500_info['price'],
                                    'change_pct': sp500_info.get('changesPercentage', 0),
                                    'is_live': True  # FMP дает актуальные данные
                                }
                                logger.info(f"✅ S&P 500 получен из FMP: {sp500_info['price']:.2f}")
                                # Не возвращаем здесь, чтобы можно было вернуть все индексы вместе
        except Exception as e:
            logger.debug(f"Ошибка получения S&P 500 из FMP: {e}")
        
        # Fallback: Alpha Vantage SPY
        try:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey={ALPHA_VANTAGE_KEY}"
            async with session.get(url, timeout=_TIMEOUT) as resp:
                if resp.status == 200:
                    sp500_data = await safe_json_response(resp)
                    if 'Global Quote' in sp500_data and '05. price' in sp500_data['Global Quote']:
                        spy_price = float(sp500_data['Global Quote']['05. price'])
                        # Приблизительная конвертация SPY в S&P 500
                        sp500_price = spy_price * 10
                        change_pct = float(sp500_data['Global Quote'].get('10. change percent', '0%').replace('%', ''))
                        
                        # Проверяем, открыт ли рынок (если есть время торговли в данных)
                        trading_status = sp500_data['Global Quote'].get('07. latest trading day', '')
                        is_live = bool(trading_status)  # Если есть дата торговли, считаем что это актуальные данные
                        
                        indices_data['sp500'] = {
                            'name': 'S&P 500',
                            'price': sp500_price,
                            'change_pct': change_pct,
                            'is_live': is_live
                        }
                        logger.info(f"✅ S&P 500 получен из Alpha Vantage: {sp500_price:.2f}")
        except Exception as e:
            logger.error(f"Ошибка получения S&P 500: {e}")
    
    except Exception as e:
        logger.error(f"Общая ошибка получения индексов: {e}")
    
    return indices_data

