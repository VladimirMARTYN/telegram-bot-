import os
import unittest

os.environ.setdefault("BOT_TOKEN", "000000000:TESTTOKEN")
os.environ.setdefault("ADMIN_USER_ID", "1")

import admin_bot


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
        expected_value = self.stocks["SBER"]["price"] * admin_bot.LTI_SBER_QUANTITY
        initial_value = admin_bot.LTI_SBER_INITIAL_PRICE * admin_bot.LTI_SBER_QUANTITY
        expected_change = expected_value - initial_value
        expected_change_pct = expected_change / initial_value * 100
        self.assertIn(admin_bot.format_price(expected_value), message)
        self.assertIn("12 344 акций Сбера", message)
        self.assertIn(f"{expected_change:+,.2f}".replace(",", " "), message)
        self.assertIn(f"{expected_change_pct:+.2f}%", message)
        self.assertIn(admin_bot.format_price(initial_value), message)

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

            async def set_my_commands(self, commands, scope=None):
                self.calls.append((commands, scope))

        application = type("FakeApplication", (), {"bot": FakeBot()})()

        await admin_bot.setup_bot_commands(application)

        self.assertEqual(len(application.bot.calls), 2)
        for commands, _scope in application.bot.calls:
            self.assertEqual(
                [command.command for command in commands],
                ["start", "help", "rates"],
            )
        self.assertIsNone(application.bot.calls[0][1])
        self.assertEqual(application.bot.calls[1][1].chat_id, admin_bot.ADMIN_USER_ID)


if __name__ == "__main__":
    unittest.main()
