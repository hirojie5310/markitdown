import argparse
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from markitdown import MarkItDown
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled


DEFAULT_OUTPUT_DIR = "output"
YOUTUBE_TITLE_MAX_LENGTH = 30
TRANSCRIPT_LANGUAGES = ["ja", "en"]


def ensure_output_dir(output_dir: Path) -> None:
    """出力先ディレクトリが存在しない場合は作成する。"""
    output_dir.mkdir(parents=True, exist_ok=True)


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
) -> None:
    """
    PDF、Excel、WordなどのローカルファイルをMarkdownに変換する。
    """
    input_file = Path(input_path)

    if not input_file.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_file}")

    md = MarkItDown()
    result = md.convert(str(input_file))

    base_name = input_file.stem
    output_path = build_output_path(
        output_dir=output_dir,
        base_name=base_name,
        output_file=output_file,
    )

    save_markdown(result.text_content, output_path)


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
