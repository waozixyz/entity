"""Provisioning failures must not masquerade as working Google Play packs."""
import importlib.util
from pathlib import Path
import unittest
import contextlib
import io
from decimal import Decimal
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    'play_dew_products', Path(__file__).resolve().parents[1] / 'tools/play_dew_products.py')
products = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(products)


class ProvisionTest(unittest.TestCase):
    def publish(self, responses):
        play = Mock(package='xyz.waozi.inbe')
        play.call.side_effect = responses
        products.publish_product(play, {'productId': 'dew_100'}, '2022/02')
        return play

    def test_failed_save_stops_before_activation(self):
        with self.assertRaisesRegex(RuntimeError, 'save: HTTP 400'):
            self.publish([(400, 'invalid price')])

    def test_failed_activation_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, 'activate: HTTP 403'):
            self.publish([(200, {}), (403, 'forbidden')])

    def test_inactive_product_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError, 'active buy option'):
            self.publish([(200, {}), (200, {}), (200, {'purchaseOptions': [
                {'purchaseOptionId': 'buy', 'state': 'INACTIVE'}]})])

    def test_active_product_is_read_back(self):
        play = self.publish([(200, {}), (200, {}), (200, {'purchaseOptions': [
            {'purchaseOptionId': 'buy', 'state': 'ACTIVE'}]})])
        self.assertEqual(play.call.call_args.args, ('GET', '/oneTimeProducts/dew_100'))

    def test_prices_have_bulk_savings_and_do_not_undercut_monero(self):
        for currency, rate in [('USD', '1'), ('EUR', '1.04'), ('PYG', '5900'),
                               ('JPY', '156'), ('KRW', '1370'), ('BRL', '5.4'), ('XAF', '703')]:
            previous = None
            for pack in products.PACKS:
                baseline = Decimal('0.06') * pack * Decimal(rate)
                price = products.clean(baseline * products.PREMIUM[pack], currency, baseline)
                self.assertGreaterEqual(price, baseline)
                unit = price / pack
                if previous is not None:
                    self.assertLess(unit, previous, currency)
                previous = unit
                if currency in products.WHOLE_CURRENCIES:
                    self.assertEqual(price, price.to_integral_value())
                else:
                    self.assertEqual(price * 100, (price * 100).to_integral_value())

    def test_ten_dew_product_preserves_regional_price_and_credit_identity(self):
        rates = ({'US': ('USD', Decimal(1)), 'PY': ('PYG', Decimal(5900))}, {}, '2022/02')
        body, _, version = products.product('xyz.waozi.inbe', 10, Decimal('0.06'), rates)
        self.assertEqual(body['productId'], 'dew_10')
        self.assertEqual(body['listings'][0]['title'], '10 Dew')
        self.assertEqual(version, '2022/02')
        self.assertEqual(len(body['purchaseOptions'][0]['regionalPricingAndAvailabilityConfigs']), 2)
        self.assertFalse(body['purchaseOptions'][0]['buyOption']['multiQuantityEnabled'])

    def test_selected_small_pack_does_not_reprice_existing_products(self):
        rates = ({'US': ('USD', Decimal(1))}, {}, '2022/02')
        with patch.object(products, 'Play') as play, \
             patch.object(products, 'rates', return_value=(Decimal('0.06'), {'xmr_usd_cents': 60000})), \
             patch.object(products, 'exchange', return_value=rates), \
             patch.object(products, 'publish_product') as publish, contextlib.redirect_stdout(io.StringIO()):
            products.main(['fixture.json', 'xyz.waozi.shovey', '--pack', '10', '--apply'])
        self.assertEqual(publish.call_count, 1)
        self.assertEqual(publish.call_args.args[0], play.return_value)
        self.assertEqual(publish.call_args.args[1]['productId'], 'dew_10')

    def test_familiar_endings_preserve_the_target_premium(self):
        for amount, expected in [('6.91', '6.99'), ('33.07', '32.99'),
                                 ('63.13', '62.99'), ('0.50', '0.49')]:
            self.assertEqual(products.clean(Decimal(amount)), Decimal(expected))
        self.assertEqual(products.clean(Decimal('300'), minimum=Decimal('300')),
                         Decimal('300.99'))


if __name__ == '__main__':
    unittest.main()
