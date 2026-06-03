import argparse
import importlib
import importlib.util
import re
from pathlib import Path
from typing import Any, TypedDict, cast
from urllib.parse import parse_qs, urlparse

from markitdown import MarkItDown
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

DEFAULT_OUTPUT_DIR = "output"
YOUTUBE_TITLE_MAX_LENGTH = 30
TRANSCRIPT_LANGUAGES = ["ja", "en"]
VERTICAL_LINE_JOIN_THRESHOLD = 0.7
VERTICAL_PDF_COLUMN_TOLERANCE_RATIO = 0.45
VERTICAL_RUBY_FONT_SIZE_RATIO = 0.78
PUNCTUATION_ONLY_RE = re.compile(r"^[\s、。，．・：；！？,.]+$")


class PdfChar(TypedDict):
    """PDFから取得した1文字分の座標情報。"""

    text: str
    x: float
    y: float
    size: float


class VerticalPdfColumn(TypedDict):
    """縦書きPDFの1列分のテキストと座標情報。"""

    x: float
    text: str
    median_size: float


class VerticalPdfColumnBuilder(TypedDict):
    """列クラスタリング中に使う作業用データ。"""

    x: float
    chars: list[PdfChar]


def ensure_output_dir(output_dir: Path) -> None:
    """出力先ディレクトリが存在しない場合は作成する。"""
    output_dir.mkdir(parents=True, exist_ok=True)


def _median(values: list[float]) -> float:
    """数値リストの中央値を返す。"""
    sorted_values = sorted(values)
    midpoint = len(sorted_values) // 2

    if len(sorted_values) % 2:
        return sorted_values[midpoint]

    return (sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2


def _cluster_vertical_pdf_chars(
    chars: list[PdfChar],
) -> list[VerticalPdfColumn]:
    """PDF文字座標を縦書きの列ごとにまとめ、右から左の読順で返す。"""
    if not chars:
        return []

    base_size = _median([char["size"] for char in chars])
    x_tolerance = max(2.5, base_size * VERTICAL_PDF_COLUMN_TOLERANCE_RATIO)
    columns: list[VerticalPdfColumnBuilder] = []

    for char in sorted(chars, key=lambda item: item["x"], reverse=True):
        matching_column = None
        for column in columns:
            if abs(column["x"] - char["x"]) <= x_tolerance:
                matching_column = column
                break

        if matching_column is None:
            columns.append({"x": char["x"], "chars": [char]})
            continue

        column_chars = matching_column["chars"]
        column_chars.append(char)
        matching_column["x"] = sum(item["x"] for item in column_chars) / len(
            column_chars
        )

    formatted_columns: list[VerticalPdfColumn] = []
    for column in columns:
        column_chars = column["chars"]
        sorted_chars = sorted(column_chars, key=lambda item: item["y"])
        text = "".join(char["text"].strip() for char in sorted_chars).strip()
        if not text:
            continue
        if len(text) <= 5 and PUNCTUATION_ONLY_RE.fullmatch(text):
            continue

        sizes = [char["size"] for char in sorted_chars]
        formatted_columns.append(
            {
                "x": column["x"],
                "text": text,
                "median_size": _median(sizes),
            }
        )

    return sorted(formatted_columns, key=lambda item: item["x"], reverse=True)


def _format_vertical_pdf_columns(
    chars: list[PdfChar],
) -> list[str]:
    """縦書きPDFの文字座標から、右から左へ本文行を組み立てる。"""
    columns = _cluster_vertical_pdf_chars(chars)
    if not columns:
        return []

    base_size = _median([column["median_size"] for column in columns])
    ruby_threshold = base_size * VERTICAL_RUBY_FONT_SIZE_RATIO
    pending_ruby: list[str] = []
    lines: list[str] = []

    for column in columns:
        text = column["text"]
        is_ruby = column["median_size"] < ruby_threshold and len(text) <= 30

        if is_ruby:
            pending_ruby.append(text)
            continue

        if pending_ruby:
            ruby_text = "".join(pending_ruby)
            if len(text) <= 12:
                text = f"{text}{ruby_text}"
            else:
                text = f"{text}（{ruby_text}）"
            pending_ruby = []

        lines.append(text)

    if pending_ruby and lines:
        lines[-1] = f"{lines[-1]}（{''.join(pending_ruby)}）"

    return lines


def extract_vertical_pdf_text(input_file: Path) -> str:
    """
    PDFの文字座標を使い、縦書き本文を右から左の読順で抽出する。

    MarkItDown経由の抽出では縦書き列の順序が崩れることがあるため、PDFの場合は
    文字座標を列にクラスタリングしてから本文を組み立てる。
    """
    if importlib.util.find_spec("fitz") is None:
        return ""

    fitz = importlib.import_module("fitz")

    page_texts: list[str] = []
    with fitz.open(input_file) as doc:
        for page in doc:
            chars: list[PdfChar] = []
            raw_page = cast(dict[str, Any], page.get_text("rawdict"))
            for block in raw_page.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        size = float(span.get("size", 0.0))
                        for char in span.get("chars", []):
                            text = str(char.get("c", "")).strip()
                            if not text:
                                continue

                            x0, y0, x1, y1 = char.get("bbox", (0, 0, 0, 0))
                            chars.append(
                                {
                                    "text": text,
                                    "x": (float(x0) + float(x1)) / 2,
                                    "y": (float(y0) + float(y1)) / 2,
                                    "size": size,
                                }
                            )

            lines = _format_vertical_pdf_columns(chars)
            if lines:
                page_texts.append("\n".join(lines))

    return "\n\n".join(page_texts)


def _is_probable_vertical_text_block(lines: list[str]) -> bool:
    """1文字ごとに改行された縦書き抽出結果らしいブロックか判定する。"""
    stripped_lines = [line.strip() for line in lines if line.strip()]

    if len(stripped_lines) < 3:
        return False

    short_line_count = sum(1 for line in stripped_lines if len(line) <= 2)
    short_line_ratio = short_line_count / len(stripped_lines)

    return short_line_ratio >= VERTICAL_LINE_JOIN_THRESHOLD


def join_vertical_text_lines(content: str) -> str:
    """
    縦書きPDFなどで1文字ごとに改行された本文を、段落単位で連結する。

    空行で区切られたブロックの大半が1〜2文字の行で構成されている場合のみ
    連結するため、通常の横書きMarkdownや箇条書きへの影響を抑える。
    """
    parts = re.split(r"(\n[ \t]*\n+)", content)
    normalized_parts: list[str] = []

    for part in parts:
        if not part or re.fullmatch(r"\n[ \t]*\n+", part):
            normalized_parts.append(part)
            continue

        lines = part.splitlines()
        if _is_probable_vertical_text_block(lines):
            normalized_parts.append(
                "".join(line.strip() for line in lines if line.strip())
            )
        else:
            normalized_parts.append(part)

    return "".join(normalized_parts)


def save_markdown(content: str, output_path: Path) -> None:
    """Markdown文字列をUTF-8で保存する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"保存完了: {output_path}")
    print(f"文字数: {len(content)}")


def sanitize_filename(name: str) -> str:
    """ファイル名に使用できない文字を除去する。"""
    cleaned = re.sub(r'[\\/:*?"<>|]', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "output"


def build_output_path(
    output_dir: str,
    base_name: str,
    output_file: str | None = None,
) -> Path:
    """
    出力ファイルパスを作成する。

    output_file が指定されている場合はその名前を優先し、
    未指定の場合は base_name.md を生成する。
    """
    output_dir_path = Path(output_dir)
    ensure_output_dir(output_dir_path)

    if output_file:
        return output_dir_path / output_file

    return output_dir_path / f"{base_name}.md"


def convert_file_to_markdown(
    input_path: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    output_file: str | None = None,
    join_vertical_lines: bool = False,
) -> None:
    """
    PDF、Excel、WordなどのローカルファイルをMarkdownに変換する。
    """
    input_file = Path(input_path)

    if not input_file.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_file}")

    text_content = ""
    if join_vertical_lines and input_file.suffix.lower() == ".pdf":
        text_content = extract_vertical_pdf_text(input_file)

    if not text_content:
        md = MarkItDown()
        result = md.convert(str(input_file))
        text_content = result.text_content
        if join_vertical_lines:
            text_content = join_vertical_text_lines(text_content)

    base_name = input_file.stem
    output_path = build_output_path(
        output_dir=output_dir,
        base_name=base_name,
        output_file=output_file,
    )

    save_markdown(text_content, output_path)


def extract_video_id(url: str) -> str:
    """YouTube URL から video_id を抽出する。"""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    if "youtube.com" in netloc:
        return parse_qs(parsed.query).get("v", [""])[0]

    if "youtu.be" in netloc:
        return parsed.path.lstrip("/")

    return ""


def fetch_youtube_transcript(video_id: str) -> list[str]:
    """
    YouTube字幕を取得し、Markdown用の行リストを返す。

    優先順:
    1. 手動字幕（ja, en）
    2. 自動生成字幕（ja, en）
    """
    if not video_id:
        raise ValueError(
            "YouTubeのvideo_idを取得できませんでした。URLを確認してください。"
        )

    api = YouTubeTranscriptApi()

    try:
        transcript_list = api.list(video_id)
    except Exception as e:
        raise RuntimeError(f"字幕一覧の取得に失敗しました: {e}") from e

    transcript = None

    try:
        transcript = transcript_list.find_transcript(TRANSCRIPT_LANGUAGES)
    except NoTranscriptFound:
        try:
            transcript = transcript_list.find_generated_transcript(TRANSCRIPT_LANGUAGES)
        except NoTranscriptFound as e:
            raise RuntimeError("日本語または英語の字幕が見つかりませんでした。") from e
    except TranscriptsDisabled as e:
        raise RuntimeError("この動画では字幕が無効化されています。") from e

    try:
        fetched = transcript.fetch()
    except Exception as e:
        raise RuntimeError(f"字幕データの取得に失敗しました: {e}") from e

    transcript_lines = ["## Transcript", ""]
    for item in fetched:
        start = getattr(item, "start", 0.0)
        text = getattr(item, "text", "").strip()
        transcript_lines.append(f"- [{start:.2f}s] {text}")

    return transcript_lines


def convert_youtube_to_markdown(
    url: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    output_file: str | None = None,
) -> None:
    """
    YouTube動画URLをMarkdownに変換する。

    処理内容:
    - MarkItDownで動画タイトルと説明文を取得
    - タイトルをもとに出力ファイル名を自動生成
    - YouTube字幕を取得
    - 説明文と字幕を結合してMarkdown保存
    """
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError("有効なYouTube URLではありません。URLを確認してください。")

    md = MarkItDown()

    # MarkItDown の変換は1回だけ実行
    result = md.convert(url)

    title = getattr(result, "title", None) or "youtube"
    safe_title = sanitize_filename(title)[:YOUTUBE_TITLE_MAX_LENGTH]
    description_md = result.text_content.strip()

    transcript_lines = fetch_youtube_transcript(video_id)

    parts = []
    if description_md:
        parts.append(description_md)
    parts.append("\n".join(transcript_lines))
    full_md = "\n\n".join(parts)

    output_path = build_output_path(
        output_dir=output_dir,
        base_name=safe_title,
        output_file=output_file,
    )

    save_markdown(full_md, output_path)


def create_parser() -> argparse.ArgumentParser:
    """コマンドライン引数パーサーを作成する。"""
    parser = argparse.ArgumentParser(
        description="PDF、Excel、Word、YouTube動画をMarkdownに変換するツール"
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # file モード
    parser_file = subparsers.add_parser(
        "file",
        help="PDF / Excel / Word などのローカルファイルをMarkdownに変換",
    )
    parser_file.add_argument(
        "input",
        help="入力ファイルパス",
    )
    parser_file.add_argument(
        "-o",
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"出力ディレクトリ（デフォルト: {DEFAULT_OUTPUT_DIR}）",
    )
    parser_file.add_argument(
        "--output-file",
        default=None,
        help="出力ファイル名（例: result.md）",
    )
    parser_file.add_argument(
        "--join-vertical-lines",
        action="store_true",
        help="縦書きPDFの列順を右から左へ整え、1文字ごとに改行された本文も段落単位で連結",
    )

    # youtube モード
    parser_youtube = subparsers.add_parser(
        "youtube",
        help="YouTube動画をMarkdownに変換",
    )
    parser_youtube.add_argument(
        "url",
        help="YouTube動画URL",
    )
    parser_youtube.add_argument(
        "-o",
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"出力ディレクトリ（デフォルト: {DEFAULT_OUTPUT_DIR}）",
    )
    parser_youtube.add_argument(
        "--output-file",
        default=None,
        help="出力ファイル名（例: youtube_result.md）",
    )

    return parser


def main() -> None:
    """エントリーポイント。"""
    parser = create_parser()
    args = parser.parse_args()

    if args.mode == "file":
        convert_file_to_markdown(
            input_path=args.input,
            output_dir=args.output_dir,
            output_file=args.output_file,
            join_vertical_lines=args.join_vertical_lines,
        )
        return

    if args.mode == "youtube":
        convert_youtube_to_markdown(
            url=args.url,
            output_dir=args.output_dir,
            output_file=args.output_file,
        )
        return

    parser.error(f"未対応のモードです: {args.mode}")


if __name__ == "__main__":
    main()
