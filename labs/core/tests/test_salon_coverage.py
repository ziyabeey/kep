"""KEP-DATA-019: guards for defects measured while writing the matcher.

Python lowercases 'İ' to 'i' + U+0307 and 'I' to 'i', so Turkish names did not
fold to the same key ('KUAFÖRÜ İREM' vs 'kuaförü irem'). The protocol rule
(drop generic tokens) is read from the frozen file, so a protocol edit that
renames the step must also fail here.
"""
import unittest

from kepcore.salon_coverage import fold, generic_tokens, load_protocol, name_similarity, protocol_sha256


class SalonCoverageGuards(unittest.TestCase):
    def test_turkish_casefold(self):
        self.assertEqual(fold('KUAFÖRÜ İREM'), fold('kuaförü irem'))
        self.assertEqual(fold('KADIKÖY'), 'kadikoy')

    def test_protocol_is_frozen(self):
        self.assertEqual(protocol_sha256(), 'e4b0727a7a951e7511ab6a12af024f31c7c2dcd8d2f6ab431e79ac9c51b4ae99')
        self.assertIn('kuafor', generic_tokens(load_protocol()))

    def test_generic_words_do_not_make_a_match(self):
        g = generic_tokens(load_protocol())
        self.assertLess(name_similarity('Moda Güzellik Salonu', 'Nil Güzellik Salonu', g), 0.80)


if __name__ == '__main__':
    unittest.main()
