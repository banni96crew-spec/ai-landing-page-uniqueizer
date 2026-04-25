import unittest

from backend.worker.mutator_js_regex import JS_REPLACE_PATTERNS, mutate_js_string


class MutatorJsRegexTests(unittest.TestCase):
    def test_mutates_all_six_supported_patterns(self) -> None:
        js = """
        document.querySelector('.btn');
        document.querySelectorAll(".btn");
        element.classList.add('btn');
        document.getElementsByClassName("btn");
        document.getElementById('hero');
        $('.btn');
        element.setAttribute('class', 'btn');
        """

        mutated = mutate_js_string(js, {"btn": "x1234"}, {"hero": "x9999"})

        self.assertEqual(len(JS_REPLACE_PATTERNS), 6)
        self.assertIn("document.querySelector('.x1234');", mutated)
        self.assertIn('document.querySelectorAll(".x1234");', mutated)
        self.assertIn("element.classList.add('x1234');", mutated)
        self.assertIn('document.getElementsByClassName("x1234");', mutated)
        self.assertIn("document.getElementById('x9999');", mutated)
        self.assertIn("$('.x1234');", mutated)
        self.assertIn("element.setAttribute('class', 'x1234');", mutated)

    def test_preserves_quote_style_spacing_and_case_insensitive_matches(self) -> None:
        js = """
        document.QUERYSELECTOR( ".BTN" );
        element.classList.REMOVE( "BTN" );
        """

        mutated = mutate_js_string(js, {"btn": "x1234"}, {})

        self.assertIn('document.QUERYSELECTOR( ".x1234" );', mutated)
        self.assertIn('element.classList.REMOVE( "x1234" );', mutated)
        self.assertNotIn(".BTN", mutated)

    def test_leaves_unsupported_concatenation_and_partial_values_unchanged(self) -> None:
        js = """
        document.querySelector('.' + className);
        element.setAttribute('class', 'btn active');
        const text = 'btn';
        """

        mutated = mutate_js_string(js, {"btn": "x1234"}, {})

        self.assertIn("document.querySelector('.' + className);", mutated)
        self.assertIn("element.setAttribute('class', 'btn active');", mutated)
        self.assertIn("const text = 'btn';", mutated)

    def test_keeps_class_and_id_maps_separate_for_same_name(self) -> None:
        js = """
        document.querySelector('.same');
        document.getElementById('same');
        """

        mutated = mutate_js_string(js, {"same": "xclass"}, {"same": "xid"})

        self.assertIn("document.querySelector('.xclass');", mutated)
        self.assertIn("document.getElementById('xid');", mutated)
        self.assertNotIn("document.querySelector('.xid');", mutated)
        self.assertNotIn("document.getElementById('xclass');", mutated)


if __name__ == "__main__":
    unittest.main()
