import unittest

from main import _format_vertical_pdf_columns, join_vertical_text_lines


def _chars_for_column(text, x, size=10):
    return [
        {"text": char, "x": x, "y": index * 12, "size": size}
        for index, char in enumerate(text)
    ]


class JoinVerticalTextLinesTests(unittest.TestCase):
    def test_joins_one_character_lines_in_paragraphs(self):
        source = "「 \n近\n江\nか\nら\n」\n\nふ\nる\nさ\nと\n。"

        self.assertEqual(
            join_vertical_text_lines(source),
            "「近江から」\n\nふるさと。",
        )

    def test_preserves_normal_markdown_blocks(self):
        source = "# 見出し\n\n- 項目1\n- 項目2\n\n通常の横書き本文です。"

        self.assertEqual(join_vertical_text_lines(source), source)

    def test_formats_pdf_columns_from_right_to_left(self):
        chars = []
        chars.extend(_chars_for_column("というこの国名", 300))
        chars.extend(_chars_for_column("国が好きである", 280))
        chars.extend(_chars_for_column("あるいま近江の国は", 260))
        chars.extend(_chars_for_column("ふるさとである", 240))
        chars.extend(_chars_for_column("「近江からはじめましょう」", 220))
        chars.extend(_chars_for_column("、", 210))

        self.assertEqual(
            _format_vertical_pdf_columns(chars),
            [
                "というこの国名",
                "国が好きである",
                "あるいま近江の国は",
                "ふるさとである",
                "「近江からはじめましょう」",
            ],
        )

    def test_attaches_ruby_column_to_following_main_column(self):
        chars = []
        chars.extend(_chars_for_column("おうみ", 320, size=5))
        chars.extend(_chars_for_column("「近江」", 300, size=10))

        self.assertEqual(_format_vertical_pdf_columns(chars), ["「近江」おうみ"])


if __name__ == "__main__":
    unittest.main()
