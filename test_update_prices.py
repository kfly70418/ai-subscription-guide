import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import update_prices as u


def source(price='125', shown='125', quoted='10-29', note='', plan='Plus 月卡', snapshot='2026-10-29'):
    return f'''<main><article class="xc" data-price="{price}" data-tier="Plus"><div class="t"><div><b>测试商家</b><span>{plan}</span></div><div class="pzr"><span class="p">¥{shown}</span></div></div><div class="tags"><span class="tag">充自己账号</span></div><div class="note">{note}</div><div class="ft"><span>报价 <span class="num">{quoted}</span></span></div></article></main><footer>AI 会员数据抓取日期 {snapshot}</footer>'''


class ParserTests(unittest.TestCase):
    def parse(self, **kwargs):
        return u.parse_page(source(**kwargs), 'chatgpt', date(2026, 10, 29))[0][0]

    def test_original_date_not_collection_date(self):
        row = self.parse(quoted='09-06')
        self.assertEqual(row['quote_date'], '2026-09-06')
        self.assertTrue(row['historical'])

    def test_source_historical_flag_wins(self):
        self.assertTrue(self.parse(note='历史报价')['historical'])

    def test_no_invented_cycle(self):
        self.assertEqual(self.parse(plan='Pro', note='30 天订阅质保')['period'], '周期未注明')

    def test_price_consistency(self):
        with self.assertRaises(ValueError):
            self.parse(price='1', shown='125')

    def test_invalid_numeric_and_future_dates(self):
        for kwargs in [{'price': 'nan'}, {'price': '-1', 'shown': '-1'}, {'snapshot': '2027-01-01'}, {'quoted': '2026-10-30'}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.parse(**kwargs)

    def test_year_rollover(self):
        self.assertEqual(u.resolve_date('12-31', date(2027, 1, 1)), date(2026, 12, 31))

    def test_missing_cards_fails(self):
        with self.assertRaises(ValueError):
            u.parse_page('<p>Service unavailable</p>', 'chatgpt', date(2026, 10, 29))

    def test_duplicate_rows_fail(self):
        raw = source()
        with self.assertRaises(ValueError):
            u.parse_page(raw + raw, 'chatgpt', date(2026, 10, 29))

    def test_suspicious_changes_fail(self):
        old = {'offers': [self.parse()]}
        new = copy.deepcopy(old)
        new['offers'][0]['price'] = 1
        with self.assertRaises(ValueError):
            u.validate_changes(old, new)
        with self.assertRaises(ValueError):
            u.validate_changes(old, {'offers': []})

    def test_partial_fetch_failure_preserves_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data').mkdir()
            path = root / 'data' / 'prices.json'
            old_text = json.dumps({'offers': [self.parse()]})
            path.write_text(old_text)
            (root / 'index.html').write_text('previous page')
            with patch.object(u, 'ROOT', root), patch('sys.argv', ['update_prices.py']), patch.object(u, 'fetch', side_effect=['User-agent: *\nAllow: /', source(snapshot='2020-01-01', quoted='01-01'), RuntimeError('network failure')]):
                with self.assertRaises(RuntimeError):
                    u.main()
            self.assertEqual(path.read_text(), old_text)
            self.assertEqual((root / 'index.html').read_text(), 'previous page')

    def test_same_day_retry_is_idempotent(self):
        with patch.object(u, 'fetch', side_effect=['User-agent: *\nAllow: /', source(), source()]):
            old = u.collect(date(2026, 10, 29))
        with patch.object(u, 'fetch', side_effect=['User-agent: *\nAllow: /', source(), source()]):
            self.assertIs(u.collect(date(2026, 10, 29), old), old)

    def test_concurrent_publisher_is_not_overwritten(self):
        with patch.object(u, 'token', return_value='test'), patch.object(u, 'api', return_value={'object': {'sha': 'new-head'}}) as api:
            with self.assertRaises(RuntimeError):
                u.publish({}, expected_head='old-head')
            self.assertEqual(api.call_count, 1)

    def test_source_text_is_escaped(self):
        row = self.parse()
        row['note'] = '<script>alert(1)</script>'
        self.assertNotIn('<script>', u.card_html(row))

    def test_robots_denial(self):
        with patch.object(u, 'fetch', return_value='User-agent: *\nDisallow: /') as fetch:
            with self.assertRaises(ValueError):
                u.collect(date(2026, 10, 29))
            self.assertEqual(fetch.call_count, 1)


if __name__ == '__main__':
    unittest.main()
