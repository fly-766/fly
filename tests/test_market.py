import unittest
from market import MarketCache, normalize_candles, positive


class MarketTests(unittest.TestCase):
    def test_invalid_amounts_rejected(self):
        for value in [None, True, 'NaN', 'inf', -1, 0]:
            with self.assertRaises((ValueError, TypeError)):
                positive(value)

    def test_wrong_market_invalid_ohlc_future_candles_rejected(self):
        c = dict(s='BTC', i='1m', t=10000, T=69999, o='100', h='101', l='99', c='100', v='0')
        bad = [dict(c, s='ETH'), dict(c, l='102'), dict(c, t=999999), dict(c, v='NaN')]
        self.assertEqual(normalize_candles(bad, 20000), [])
        self.assertEqual(len(normalize_candles([c, c], 20000)), 1)

    def test_outage_keeps_timestamp_and_marks_stale(self):
        now = [100]
        calls = []
        def loader():
            calls.append(True)
            if len(calls) > 1:
                raise OSError('upstream unavailable')
            return dict(ok=True, providerTime=100, markPrice=100, stale=False)
        cache = MarketCache(loader, lambda: now[0])
        self.assertFalse(cache.get()['stale'])
        self.assertFalse(cache.get()['stale'])
        self.assertEqual(len(calls), 1)
        now[0] = 110
        result = cache.get()
        self.assertTrue(result['stale'])
        self.assertEqual(result['providerTime'], 100)
        self.assertEqual(result['markPrice'], 100)

    def test_first_failure_does_not_invent_balance_or_price(self):
        def fail():
            raise OSError()
        result = MarketCache(fail).get()
        self.assertFalse(result['ok'])
        self.assertNotIn('markPrice', result)
        self.assertFalse(result['executionEnabled'])


if __name__ == '__main__':
    unittest.main()
