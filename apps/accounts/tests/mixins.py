import json
from json import JSONDecodeError


class HTMXAssertionsMixin:
    def assert_hx_location(self, response, path, *, target=None, swap=None):
        header = response.headers.get('HX-Location')
        self.assertIsNotNone(header)
        if target or swap:
            try:
                payload = json.loads(header)
            except JSONDecodeError:
                self.assertEqual(header, path)
                return header
            self.assertEqual(payload['path'], path)
            if target:
                self.assertEqual(payload.get('target'), target)
            if swap:
                self.assertEqual(payload.get('swap'), swap)
            return payload
        self.assertEqual(header, path)
        return header
