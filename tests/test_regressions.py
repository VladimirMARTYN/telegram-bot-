import asyncio
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone, time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault('BOT_TOKEN', '000000000:TESTTOKEN')
os.environ.setdefault('ADMIN_USER_ID', '1')

import admin_bot as bot
import data_sources as sources
import quotes
import utils
from alerts import new_alert_state, observe_prices
from storage import read_json, write_json, migrate_to_data_dir
from telegram_text import split_html


def fake_update(callback=False):
    status = NS(edit_text=AsyncMock())
    message = NS(reply_text=AsyncMock(return_value=status), reply_html=AsyncMock())
    update = NS(message=None if callback else message, effective_message=message,
                effective_chat=NS(id=bot.ADMIN_USER_ID), effective_user=NS(id=bot.ADMIN_USER_ID))
    if callback:
        update.callback_query = NS(data='subscribe', answer=AsyncMock())
    return update, status


class Response:
    def __init__(self, data, status=200):
        self.data, self.status = data, status
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def json(self): return self.data


class Session:
    def __init__(self, route):
        self.route, self.calls = route, []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        result = self.route(method, url, kwargs)
        if isinstance(result, Exception): raise result
        return result
    def get(self, url, **kwargs): return self.request('GET', url, **kwargs)
    def post(self, url, **kwargs): return self.request('POST', url, **kwargs)


class ContextMixin:
    # unittest.TestCase.enterContext was introduced after Python 3.9.
    def enterContext(self, context):
        if not hasattr(self, '_contexts'):
            self._contexts = ExitStack()
            self.addCleanup(self._contexts.close)
        return self._contexts.enter_context(context)


class IsolatedState(ContextMixin, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.enterContext(patch.dict(os.environ, DATA_DIR=self.temp.name))
        utils.clear_cache()


class CurrencyTests(IsolatedState):
    def test_all_forex_crosses_survive_cbr_exception(self):
        fx = quotes.resolve_currency_rates(RuntimeError('down'), {'rates': {'RUB': 90, 'EUR': .9, 'CNY': 7.5}})
        self.assertEqual(fx['rates'], {'USD': 90, 'EUR': 100, 'CNY': 12})
        self.assertTrue(all('(FOREX)' in text for text in fx['strings'].values()))

    def test_partial_cbr_normalizes_nominal_and_fills_only_missing_currencies(self):
        fx = quotes.resolve_currency_rates({'Valute': {'USD': {'Value': 910, 'Nominal': 10}, 'EUR': None}},
                                          {'rates': {'RUB': 90, 'EUR': .9, 'CNY': 7.5}})
        self.assertEqual(fx['rates'], {'USD': 91, 'EUR': 100, 'CNY': 12})
        self.assertEqual(fx['sources']['USD'], 'CBR')

    def test_saved_rate_timestamp_is_not_refreshed_by_fallback(self):
        old = datetime.now(timezone.utc) - timedelta(hours=23)
        utils.save_last_known_rate('USD_RUB', 91.5, timestamp=old)
        before = read_json('last_known_rates.json')
        fx = quotes.resolve_currency_rates({}, {})
        self.assertEqual(fx['usd_to_rub_rate'], 91.5)
        self.assertIn('сохранённый', fx['conversion_note'])
        self.assertEqual(read_json('last_known_rates.json'), before)
        before['USD_RUB']['timestamp'] = (old - timedelta(hours=2)).isoformat()
        write_json('last_known_rates.json', before)
        self.assertIsNone(utils.get_last_known_rate('USD_RUB'))
        fx = quotes.resolve_currency_rates({}, {})
        self.assertIn('условный', fx['conversion_note'])
        self.assertEqual(read_json('last_known_rates.json'), before)

    def test_cbr_timestamp_preserved_across_refetch(self):
        stamp = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        for _ in range(2):
            quotes.resolve_currency_rates({'Timestamp': stamp, 'Valute': {'USD': {'Value': 90}}}, {})
        self.assertEqual(read_json('last_known_rates.json')['USD_RUB']['timestamp'], stamp)

    def test_nan_inf_zero_are_rejected(self):
        for value in ('nan', 'inf', '-inf', '0', '-1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                utils.validate_positive_number(value)
        self.assertFalse(utils.positive_price(True))


class BotFlowTests(ContextMixin, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.enterContext(patch.dict(os.environ, DATA_DIR=self.temp.name))
        utils.clear_cache()
        bot._price_check_lock = None
        self.enterContext(patch.object(bot, 'get_http_session', AsyncMock(return_value=object())))
        self.fetches = {}
        values = {
            'get_cbr_rates': {'Valute': {'USD': {'Value': 90}, 'EUR': {'Value': 100}, 'CNY': {'Value': 12}}},
            'get_forex_rates': {'rates': {'RUB': 90, 'EUR': .9, 'CNY': 7.5}},
            'get_crypto_data': {}, 'get_moex_stocks': {'SBER': {'price': 310, 'currency': 'RUB'}},
            'get_commodities_data': {}, 'get_indices_data': {},
        }
        for name, value in values.items():
            self.fetches[name] = self.enterContext(patch.object(bot, name, AsyncMock(return_value=value)))
        self.owner = str(bot.ADMIN_USER_ID)
        write_json('notifications.json', {self.owner: {'subscribed': True, 'daily_summary': True,
                                                       'threshold': 2, 'alerts': {'SBER': 305}}})
        write_json('alert_state.json', new_alert_state({'SBER': 300}))
        self.context = NS(bot=NS(send_message=AsyncMock()), args=[])

    async def test_summary_does_not_consume_crossing(self):
        update, _ = fake_update()
        self.assertTrue(await bot.rates_command(update, self.context))
        self.assertEqual(read_json('price_history.json')['SBER'], 310)
        self.assertEqual(read_json('alert_state.json')['prices']['SBER']['price'], 300)
        await bot.check_price_changes(self.context)
        texts = [call.kwargs['text'] for call in self.context.bot.send_message.call_args_list]
        self.assertTrue(any('АЛЕРТ' in text for text in texts))
        self.assertTrue(any('+3.33%' in text for text in texts))
        self.assertFalse(any('за 30 мин' in text for text in texts))

    async def test_failed_delivery_survives_restart_and_retries_same_event(self):
        self.context.bot.send_message.side_effect = TimeoutError('temporary failure')
        await bot.check_price_changes(self.context)
        state = read_json('alert_state.json')
        self.assertEqual(len(state['pending'][self.owner]), 2)
        first_id = state['pending'][self.owner][0]['id']
        bot._price_check_lock = None
        self.context.bot.send_message.side_effect = None
        await bot.check_price_changes(self.context)
        self.assertEqual(read_json('alert_state.json')['pending'][self.owner], [])
        self.assertEqual(self.context.bot.send_message.await_count, 3)
        self.assertIn(first_id, self.context.bot.send_message.call_args_list[1].kwargs['text'])

    async def test_no_send_if_outbox_cannot_be_saved(self):
        with patch.object(bot, 'write_json', side_effect=OSError('disk full')):
            await bot.check_price_changes(self.context)
        self.context.bot.send_message.assert_not_awaited()

    async def test_unsubscribing_discards_pending_delivery(self):
        self.context.bot.send_message.side_effect = TimeoutError()
        await bot.check_price_changes(self.context)
        update, _ = fake_update()
        await bot.unsubscribe_command(update, self.context)
        self.context.bot.send_message.reset_mock()
        await bot.check_price_changes(self.context)
        self.context.bot.send_message.assert_not_awaited()
        self.assertFalse(read_json('alert_state.json')['pending'])

    async def test_estimated_brent_does_not_send_or_replace_real_baseline(self):
        write_json('alert_state.json', new_alert_state({'brent': 100}))
        self.fetches['get_moex_stocks'].return_value = {}
        self.fetches['get_commodities_data'].return_value = {
            'brent': {'price': 135, 'name': 'Нефть Brent (приблиз.)', 'note': 'Рассчитано от USO ETF'}}
        await bot.check_price_changes(self.context)
        self.context.bot.send_message.assert_not_awaited()
        self.assertEqual(read_json('alert_state.json')['prices']['brent']['price'], 100)
        text = bot._format_commodity_html('brent', self.fetches['get_commodities_data'].return_value, 90, {})
        self.assertIn('расчётная', text)

    async def test_callback_subscription_confirms_saved_schedule(self):
        write_json('bot_settings.json', {'daily_summary_time': '18:30', 'timezone': 'Europe/Moscow'})
        update, _ = fake_update(callback=True)
        await bot.button_callback(update, self.context)
        self.assertTrue(read_json('notifications.json')[self.owner]['subscribed'])
        self.assertIn('18:30', update.effective_message.reply_html.call_args.args[0])

    async def test_subscription_does_not_confirm_failed_write(self):
        update, _ = fake_update(callback=True)
        with patch.object(bot, 'save_notification_data', side_effect=OSError('disk full')):
            await bot.subscribe_command(update, self.context)
        update.effective_message.reply_html.assert_not_awaited()
        self.assertIn('Не удалось', update.effective_message.reply_text.call_args.args[0])

    async def test_null_crypto_change_keeps_all_sections(self):
        self.fetches['get_crypto_data'].return_value = {'bitcoin': {'price': 100000, 'change_24h': None, 'source': 'CoinGecko'}}
        update, status = fake_update()
        self.assertTrue(await bot.rates_command(update, self.context))
        text = status.edit_text.call_args.args[0]
        self.assertIn('Bitcoin', text)
        self.assertIn('Портфель LTI', text)
        self.assertNotIn('NoneType', text)

    async def test_corrupt_notification_file_is_not_overwritten(self):
        path = Path(self.temp.name, 'notifications.json')
        path.write_text('{broken')
        update, _ = fake_update()
        await bot.subscribe_command(update, self.context)
        self.assertEqual(path.read_text(), '{broken')
        update.effective_message.reply_html.assert_not_awaited()

    async def test_daily_failure_is_not_logged_as_success(self):
        with patch.object(bot, 'rates_command', AsyncMock(return_value=False)), self.assertLogs(bot.logger, level='INFO') as logs:
            await bot.daily_summary_job(self.context)
        self.assertTrue(any('Отправлено 0 из 1' in text for text in logs.output))
        self.assertFalse(any('✅ Сводка отправлена' in text for text in logs.output))

    async def test_explicit_ping_port_uses_tcp_even_when_ping_binary_exists(self):
        update, _ = fake_update()
        self.context.args = ['127.0.0.1:22']
        writer = NS(close=Mock(), wait_closed=AsyncMock())
        with patch.object(bot.shutil, 'which', return_value='/sbin/ping'), \
             patch.object(bot.asyncio, 'open_connection', AsyncMock(return_value=(None, writer))) as tcp, \
             patch.object(bot.asyncio, 'create_subprocess_exec', AsyncMock()) as icmp:
            await bot.ping_command(update, self.context)
        self.assertEqual(tcp.await_count, 4)
        icmp.assert_not_awaited()
        self.assertIn('port 22', update.effective_message.reply_html.call_args.args[0])

    async def test_pdf_receives_stocks_and_marks_currency_fallback(self):
        from io import BytesIO
        update, _ = fake_update()
        self.fetches['get_cbr_rates'].side_effect = RuntimeError('CBR unavailable')
        self.fetches['get_forex_rates'].return_value = {}
        self.context.bot.send_document = AsyncMock()
        with patch('pdf_report.build_pdf_report', return_value=BytesIO(b'%PDF-test')) as build:
            await bot.export_pdf_command(update, self.context)
        args = build.call_args.args
        self.assertIn('условный', args[0]['conversion_note'])
        self.assertEqual(args[2]['SBER']['price'], 310)
        self.assertIn('SBER', args[6])
        self.context.bot.send_document.assert_awaited_once()


class SourceTests(ContextMixin, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.enterContext(patch.dict(os.environ, DATA_DIR=self.temp.name))
        self.enterContext(patch.object(sources, 'TINVEST_API_TOKEN', ''))

    async def test_partial_crypto_fills_missing_without_overwriting_btc(self):
        def route(method, url, kwargs):
            if 'coingecko' in url: return Response({'bitcoin': {'usd': 100000, 'usd_24h_change': None}})
            self.assertIn('coinbase', url)
            self.assertNotIn('BTC-USD', url)
            return Response({'data': {'amount': '2.5'}})
        session = Session(route)
        result = await sources.get_crypto_data(session)
        self.assertEqual(len(result), 4)
        self.assertEqual(result['bitcoin']['price'], 100000)
        self.assertIsNone(result['bitcoin']['change_24h'])
        self.assertEqual(len(session.calls), 4)

    def moex_response(self):
        return {'securities': {'columns': ['SECID', 'PREVPRICE', 'PREVDATE'],
                               'data': [['SBER', 300, '2026-09-04'], ['YDEX', 5000, '2026-09-04']]},
                'marketdata': {'columns': ['SECID', 'LAST', 'TRADINGSTATUS', 'CHANGEPRCNT'],
                               'data': [['SBER', 310, 'T', 1.2], ['YDEX', None, 'N', None]]}}

    async def test_weekend_queries_market_and_keeps_last_close(self):
        session = Session(lambda *args: Response(self.moex_response()))
        with patch.object(sources, 'datetime') as clock:
            clock.now.return_value = datetime(2026, 9, 6, 12)
            result = await sources.get_moex_stocks(session)
        self.assertEqual(result['SBER']['price'], 310)
        self.assertTrue(result['SBER']['is_live'])
        self.assertEqual(result['YDEX']['price'], 5000)
        self.assertFalse(result['YDEX']['is_live'])
        self.assertEqual(len(session.calls), 1)

    async def test_partial_tinvest_fills_missing_without_overwriting_primary(self):
        def route(method, url, kwargs):
            if 'GetLastPrices' in url:
                return Response({'lastPrices': [{'ticker': 'SBER', 'price': {'units': '315', 'nano': 0}, 'instrumentUid': 'uid'}]})
            if 'GetTradingStatuses' in url: return TimeoutError('status service down')
            self.assertNotIn('SBER', kwargs['params']['securities'].split(','))
            return Response(self.moex_response())
        with patch.object(sources, 'TINVEST_API_TOKEN', 'FAKE_TEST_TOKEN'):
            result = await sources.get_moex_stocks(Session(route))
        self.assertEqual(result['SBER']['price'], 315)
        self.assertEqual(result['YDEX']['price'], 5000)

    async def test_commodity_estimates_are_explicit_and_do_not_train_their_own_ratio(self):
        def route(method, url, kwargs):
            if url.endswith('/XAU'): return Response({'price': 3200})
            if url.endswith('/XAG') or 'eia.gov' in url: return Response({}, 503)
            return Response({'Global Quote': {'05. price': '100'}})
        with patch.object(sources, 'save_last_known_rate') as save:
            result = await sources.get_commodities_data(Session(route))
        for key in ('silver', 'brent', 'urals'):
            self.assertTrue(result[key]['is_estimated'])
        self.assertFalse(result['gold']['is_estimated'])
        self.assertFalse(any(call.args[0] == 'USO_TO_BRENT' for call in save.call_args_list))

    async def test_spy_estimate_and_old_date_do_not_claim_open_market(self):
        def route(method, url, kwargs):
            if 'alphavantage' in url:
                return Response({'Global Quote': {'05. price': '600', '10. change percent': '1%', '07. latest trading day': '2020-01-01'}})
            return Response({})
        with patch('config.FMP_API_KEY', 'demo'):
            result = await sources.get_indices_data(Session(route))
        self.assertTrue(result['sp500']['is_estimated'])
        self.assertIsNone(result['sp500']['is_live'])
        self.assertEqual(result['sp500']['as_of'], '2020-01-01')


class StorageTests(IsolatedState):
    def test_write_failure_retains_previous_file(self):
        write_json('settings.json', {'time': '09:00'})
        with patch('storage.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): write_json('settings.json', {'time': '18:00'})
        self.assertEqual(read_json('settings.json'), {'time': '09:00'})
        self.assertFalse(list(Path(self.temp.name).glob('*.tmp')))

    def test_migration_copies_without_overwriting_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                Path('bot_settings.json').write_text('{"daily_summary_time":"18:30"}')
                migrate_to_data_dir(['bot_settings.json'])
                self.assertEqual(read_json('bot_settings.json')['daily_summary_time'], '18:30')
                Path('bot_settings.json').write_text('{"daily_summary_time":"09:00"}')
                migrate_to_data_dir(['bot_settings.json'])
                self.assertEqual(read_json('bot_settings.json')['daily_summary_time'], '18:30')
            finally:
                os.chdir(previous)


class StateAndFormattingTests(unittest.TestCase):
    def test_moex_local_timestamp_has_explicit_moscow_offset(self):
        self.assertEqual(sources._moex_timestamp('2026-09-07 12:30:00'), '2026-09-07T12:30:00+03:00')

    def test_invalid_previous_prices_cannot_abort_other_alerts(self):
        for old in (0, float('nan'), float('inf'), None):
            state = new_alert_state()
            state['prices']['SBER'] = {'price': old}
            observe_prices(state, {'SBER': {'price': 310}}, {'1': {'subscribed': True, 'alerts': {'SBER': 305}}})
            self.assertEqual(len(state['pending']['1']), 1)

    def test_observation_interval_is_measured(self):
        now = datetime.now(timezone.utc)
        state = new_alert_state({'SBER': 300})
        state['prices']['SBER']['observed_at'] = (now - timedelta(minutes=95)).isoformat()
        observe_prices(state, {'SBER': {'price': 310}}, {'1': {'subscribed': True}}, now=now)
        self.assertIn('95 мин', state['pending']['1'][0]['text'])

    def test_html_splitter_preserves_text_and_balanced_tags(self):
        from html.parser import HTMLParser
        class Inspector(HTMLParser):
            def __init__(self):
                super().__init__(); self.stack=[]; self.text=''
            def handle_starttag(self, tag, attrs): self.stack.append(tag)
            def handle_endtag(self, tag):
                assert self.stack.pop() == tag
            def handle_data(self, text): self.text += text
        raw = '<b>DAILY</b>\n<blockquote expandable>' + ('<i>BTC &amp; 💎</i>\n' * 1000) + '</blockquote>'
        parts = split_html(raw)
        combined = ''
        for part in parts:
            parser = Inspector(); parser.feed(part)
            self.assertFalse(parser.stack)
            self.assertLessEqual(len(parser.text.encode('utf-16-le')) // 2, 3800)
            combined += parser.text
        expected = Inspector(); expected.feed(raw)
        self.assertEqual(combined, expected.text)
        self.assertGreater(len(parts), 1)

    def test_primary_daily_schedule_stays_at_nine_moscow(self):
        import pytz
        from telegram.ext import Application
        # Supply a loop explicitly because Python 3.12 does not create one here.
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            app = Application.builder().token('000000000:TESTTOKEN').build()
            async def callback(context): pass
            job = app.job_queue.run_daily(callback, time=time(9, 0, tzinfo=pytz.timezone('Europe/Moscow')))
            next_run = job.job.trigger.get_next_fire_time(None, datetime(2026, 9, 7, tzinfo=timezone.utc))
            self.assertEqual(next_run.isoformat(), '2026-09-07T09:00:00+03:00')
        finally:
            loop.close(); asyncio.set_event_loop(None)

    def test_compatible_client_parser_in_fresh_process(self):
        env = dict(os.environ, BOT_TOKEN='000000000:TESTTOKEN', ADMIN_USER_ID='1', TINVEST_API_TOKEN='')
        output = subprocess.check_output([sys.executable, '-c', 'import data_sources; from aiohttp.http_parser import HttpResponseParser; print(HttpResponseParser.__module__)'], env=env, text=True)
        expected = 'aiohttp.http_parser' if sys.version_info < (3, 10) else 'aiohttp._http_parser'
        self.assertEqual(output.strip(), expected)


class AlternativeSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_callback_uses_application_loop(self):
        loop = asyncio.get_running_loop()
        queue = bot.AlternativeJobQueue(NS(bot=object()))
        seen = []
        async def callback(context):
            seen.append(asyncio.get_running_loop())
        queue.jobs['daily'] = bot.AlternativeJob('daily', callback, queue)
        await asyncio.to_thread(queue._run_job, callback, 'daily')
        self.assertEqual(seen, [loop])

    async def test_fallback_schedule_retains_moscow_timezone(self):
        import pytz
        queue = bot.AlternativeJobQueue(NS(bot=object()))
        every = Mock()
        with patch.object(bot.schedule, 'every', return_value=every), patch.object(bot.schedule, 'clear'), \
             patch.object(bot.threading, 'Thread'):
            queue.run_daily(AsyncMock(), time=time(9, 0, tzinfo=pytz.timezone('Europe/Moscow')), name='daily')
        every.day.at.assert_called_once_with('09:00', 'Europe/Moscow')


class PdfTests(unittest.TestCase):
    def test_complete_pdf_builds_with_missing_and_estimated_values(self):
        from pdf_report import build_pdf_report, quote_status
        fx = {'rates': {'USD': None, 'EUR': None, 'CNY': None}, 'sources': {},
              'usd_to_rub_rate': 0, 'conversion_note': ''}
        report = build_pdf_report(fx, {}, {'SBER': {'price': 310}},
                                  {'silver': {'price': 40, 'is_estimated': True}}, {},
                                  '07.09.2026 12:00', list(bot.STOCK_NAMES))
        self.assertTrue(report.read().startswith(b'%PDF-'))
        self.assertEqual(quote_status({'is_estimated': True}), 'Estimated')
        self.assertEqual(quote_status({'as_of': '2020-01-01', 'is_live': None}), 'Last quote\nas of 2020-01-01')


if __name__ == '__main__':
    unittest.main()
