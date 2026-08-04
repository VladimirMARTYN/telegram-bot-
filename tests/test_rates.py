import os
import unittest

os.environ.setdefault("BOT_TOKEN", "000000000:TESTTOKEN")
os.environ.setdefault("ADMIN_USER_ID", "1")

import admin_bot
from telegram.ext import ApplicationHandlerStop


class RatesMessageTests(unittest.TestCase):
    def setUp(self):
        self.stocks = {
            ticker: {
                "price": 300.0 + index,
                "change_pct": 1.25,
                "is_live": True,
            }
            for index, ticker in enumerate(admin_bot.STOCK_NAMES)
        }
        self.crypto = {
            "bitcoin": "Bitcoin: $120 000 (10 800 000 ₽) (+1.20% за 24ч)",
            "the-open-network": "TON: $3.50 (315.00 ₽) (-0.30% за 24ч)",
            "tether": "USDT: $1.00 (90.00 ₽)",
            "solana": "Solana: $180.00 (16 200.00 ₽) (+2.10% за 24ч)",
        }
        self.commodities = {
            key: {"price": 100.0 + index}
            for index, key in enumerate(admin_bot.COMMODITY_ITEMS)
        }
        self.indices = {
            "imoex": {
                "name": "IMOEX",
                "price": 2900.0,
                "change_pct": 0.5,
                "is_live": True,
            },
            "sp500": {
                "name": "S&P 500",
                "price": 6300.0,
                "change_pct": -0.2,
                "is_live": False,
            },
        }

    def build_message(self, commodities=None):
        return admin_bot.build_rates_message(
            usd_str="90.00 ₽",
            eur_str="100.00 ₽",
            cny_str="12.00 ₽",
            usd_to_rub_rate=90.0,
            crypto_strings=self.crypto,
            stocks_data=self.stocks,
            commodities_data=self.commodities if commodities is None else commodities,
            indices_data=self.indices,
            price_history={},
            current_time="03.08.2026 17:00",
        )

    def test_daily_and_details_are_partitioned(self):
        message = self.build_message()
        daily, remainder = message.split("<blockquote expandable>", 1)
        details, _ = remainder.split("</blockquote>", 1)

        for expected in ("USD", "EUR", "Bitcoin", "TON", "USDT", "ДОМ.РФ", "IMOEX"):
            self.assertIn(expected, daily)
        for hidden in ("CNY", "Solana", "Яндекс", "Газпром", "S&amp;P 500"):
            self.assertIn(hidden, details)
            self.assertNotIn(hidden, daily)

        self.assertNotIn("ДОМ.РФ", details)
        self.assertLess(len(message), 4096)

    def test_lti_uses_current_sber_price(self):
        message = self.build_message()
        sber_price = self.stocks["SBER"]["price"]
        expected_value = sber_price * admin_bot.LTI_SBER_QUANTITY
        expected_change = expected_value - admin_bot.LTI_FIXATION_VALUE
        expected_change_pct = expected_change / admin_bot.LTI_FIXATION_VALUE * 100
        expected_change_str = f"{expected_change:+,.2f}".replace(",", " ")

        self.assertIn("<b>Портфель LTI</b>", message)
        self.assertIn(
            "Фиксация 31.07.2026: 12 344 акций, "
            "275.40 рублей/акция, 3 400 000 рублей",
            message,
        )
        self.assertIn(
            f"Выплата 31.07.2027: {admin_bot.format_price(3_086 * sber_price)} рублей",
            message,
        )
        self.assertIn(
            f"Выплата 31.07.2028: {admin_bot.format_price(3_086 * sber_price)} рублей",
            message,
        )
        self.assertIn(
            f"Выплата 31.07.2029: {admin_bot.format_price(6_172 * sber_price)} рублей",
            message,
        )
        self.assertIn(
            f"Текущая цена акции: <b><i>{admin_bot.format_price(sber_price)} рублей</i></b>",
            message,
        )
        self.assertIn(
            f"Текущий общий объём: {admin_bot.format_price(expected_value)} рублей",
            message,
        )
        self.assertIn(
            f"Изменение: <b><i>{expected_change_str} рублей "
            f"({expected_change_pct:+.2f}%)</i></b>",
            message,
        )

    def test_tradable_funds_use_moex_tickers(self):
        self.assertIn("TGLD", admin_bot.STOCK_NAMES)
        self.assertIn("TOFZ", admin_bot.STOCK_NAMES)
        self.assertNotIn("TGLD@", admin_bot.STOCK_NAMES)
        self.assertNotIn("TOFZ@", admin_bot.STOCK_NAMES)
        self.assertNotIn("MFON", admin_bot.STOCK_NAMES)

    def test_missing_daily_commodities_are_visible(self):
        message = self.build_message(commodities={})
        for name in admin_bot.COMMODITY_NAMES.values():
            self.assertIn(f"{name}: <b>Н/Д</b>", message)


class BotCommandMenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_menu_contains_only_primary_commands_in_all_scopes(self):
        class FakeBot:
            def __init__(self):
                self.calls = []
                self.deleted_scopes = []

            async def set_my_commands(self, commands, scope=None):
                self.calls.append((commands, scope))

            async def delete_my_commands(self, scope=None):
                self.deleted_scopes.append(scope)

        application = type("FakeApplication", (), {"bot": FakeBot()})()

        await admin_bot.setup_bot_commands(application)

        self.assertEqual(application.bot.deleted_scopes, [None])
        self.assertEqual(len(application.bot.calls), 1)
        commands, scope = application.bot.calls[0]
        self.assertEqual(
            [command.command for command in commands],
            ["start", "help", "rates"],
        )
        self.assertEqual(scope.chat_id, admin_bot.ADMIN_USER_ID)


class PrivateAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_update_is_allowed(self):
        update = type(
            "FakeUpdate",
            (),
            {"effective_user": type("FakeUser", (), {"id": admin_bot.ADMIN_USER_ID})()},
        )()

        await admin_bot.private_access_guard(update, None)

    async def test_non_admin_update_stops_all_handlers(self):
        update = type(
            "FakeUpdate",
            (),
            {"effective_user": type("FakeUser", (), {"id": admin_bot.ADMIN_USER_ID + 1})()},
        )()

        with self.assertRaises(ApplicationHandlerStop):
            await admin_bot.private_access_guard(update, None)

    def test_stored_admin_id_is_accepted_as_string(self):
        self.assertTrue(admin_bot.is_admin(str(admin_bot.ADMIN_USER_ID)))
        self.assertFalse(admin_bot.is_admin(str(admin_bot.ADMIN_USER_ID + 1)))


if __name__ == "__main__":
    unittest.main()
