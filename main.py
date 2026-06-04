import argparse
import importlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, TypedDict, cast
from urllib.parse import parse_qs, urlparse

from markitdown import MarkItDown
from PIL import Image
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

DEFAULT_OUTPUT_DIR = "output"
YOUTUBE_TITLE_MAX_LENGTH = 30
TRANSCRIPT_LANGUAGES = ["ja", "en"]
VERTICAL_LINE_JOIN_THRESHOLD = 0.7
VERTICAL_RUBY_FONT_SIZE_RATIO = 0.78
OCR_LANGUAGE = "jpn"
OCR_RETRY_DPI_CANDIDATES = (300, 450, 600)
AUTO_FORCE_OCR_MIN_SCORE_GAIN = 25
AUTO_FORCE_OCR_SCORE_RATIO = 1.15
VERTICAL_OCR_BLOCK_SHORT_LINE_RATIO = 0.6
VERTICAL_OCR_BLOCK_MAX_AVERAGE_LINE_LENGTH = 3.5
VERTICAL_OCR_BLOCK_MIN_ASPECT_RATIO = 1.2
VERTICAL_OCR_BLOCK_FALLBACK_SHORT_LINE_RATIO = 0.55
VERTICAL_OCR_BLOCK_FALLBACK_MAX_AVERAGE_LINE_LENGTH = 4.5
VERTICAL_OCR_BLOCK_DENSE_MIN_LINE_COUNT = 8
VERTICAL_OCR_BAND_X_TOLERANCE_RATIO = 0.2
VERTICAL_OCR_BAND_Y_GAP_RATIO = 0.6
PUNCTUATION_ONLY_RE = re.compile(r"^[\s、。，．・：；！？,.]+$")
OCR_PREFERRED_CHAR_RE = re.compile(r"[ぁ-んァ-ヶー一-龠々A-Za-z0-9]")
OCR_JAPANESE_CHAR_RE = re.compile(r"[ぁ-んァ-ヶー一-龠々]")
_HAS_WARNED_PYMUPDF_OCR = False
HOMEBREW_BIN_DIR = Path("/opt/homebrew/bin")
HOMEBREW_TESSDATA_DIR = Path("/opt/homebrew/share/tessdata")
TESSERACT_BIN_PATH = HOMEBREW_BIN_DIR / "tesseract"
TESSERACT_VERTICAL_LANGUAGE = "jpn_vert"
TESSERACT_VERTICAL_PSM = "5"
TESSERACT_ROTATED_LANGUAGE = "jpn"
TESSERACT_ROTATED_PSM = "6"
TESSERACT_VERTICAL_MIN_SCORE_GAIN = 20
TESSERACT_ROTATED_MIN_JAPANESE_RATIO = 0.6
TESSERACT_ROTATED_MIN_SCORE_OVER_VERTICAL = 50
TESSERACT_VERTICAL_CLIP_X_MARGIN_RATIO = 0.12
TESSERACT_VERTICAL_CLIP_Y_MARGIN_RATIO = 0.08


class PdfChar(TypedDict):
    """PDFから取得した1文字分の座標情報。"""

    text: str
    x: float
    y: float
    size: float


class VerticalPdfColumn(TypedDict):
    """縦書きPDFの1列分のテキストと座標情報。"""

    x: float
    y: float
    text: str
    median_size: float


class PdfBlockText(TypedDict):
    """1つのPDFテキストブロックから復元した本文と座標情報。"""

    x0: float
    y0: float
    x1: float
    y1: float
    writing_mode: int
    text: str


class PdfLineFragment(TypedDict):
    """OCR の line を縦書き復元用に持ち回す情報。"""

    text: str
    x: float
    y: float
    width: float
    height: float


class OcrCandidate(TypedDict):
    """1ページ分の OCR 候補。"""

    dpi: int
    raw_page: dict[str, Any]
    text: str
    score: int


class PdfPageDecision(TypedDict):
    """1ページ分のテキスト抽出方法の判定記録。"""

    page_number: int
    source: str
    reason: str
    native_chars: int
    native_score: int
    selected_score: int
    selected_dpi: int | None


class VerticalOcrBand(TypedDict):
    """近接する縦書き OCR 候補ブロックをまとめた帯。"""

    block_indices: list[int]
    x0: float
    y0: float
    x1: float
    y1: float


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


def _configure_pymupdf_ocr_environment() -> None:
    """PyMuPDF OCR が Homebrew の tesseract / tessdata を見つけやすくする。"""
    current_path = os.environ.get("PATH", "")
    path_entries = current_path.split(os.pathsep) if current_path else []

    if HOMEBREW_BIN_DIR.exists() and str(HOMEBREW_BIN_DIR) not in path_entries:
        os.environ["PATH"] = os.pathsep.join([str(HOMEBREW_BIN_DIR), *path_entries])

    if "TESSDATA_PREFIX" not in os.environ and HOMEBREW_TESSDATA_DIR.exists():
        os.environ["TESSDATA_PREFIX"] = str(HOMEBREW_TESSDATA_DIR)


def _count_rawdict_text_chars(raw_page: dict[str, Any]) -> int:
    """rawdict に含まれる本文文字数を概算する。"""
    count = 0

    for block in raw_page.get("blocks", []):
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                chars = span.get("chars", [])
                if chars:
                    count += sum(
                        1 for char in chars if str(char.get("c", "")).strip()
                    )
                    continue

                count += len(str(span.get("text", "")).strip())

    return count


def _extract_rawdict_text(raw_page: dict[str, Any]) -> str:
    """rawdict から簡易テキストを復元する。"""
    blocks: list[str] = []

    for block in raw_page.get("blocks", []):
        if block.get("type") != 0:
            continue

        lines: list[str] = []
        for line in block.get("lines", []):
            line_text = "".join(
                _extract_span_text(span) for span in line.get("spans", [])
            ).strip()
            if line_text:
                lines.append(line_text)

        if lines:
            blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _extract_line_text(line: dict[str, Any]) -> str:
    """line から文字列を復元する。"""
    return "".join(_extract_span_text(span) for span in line.get("spans", [])).strip()


def _score_ocr_text(text: str) -> int:
    """OCR候補テキストの見た目を簡易採点する。"""
    stripped = "".join(char for char in text if not char.isspace())
    if not stripped:
        return -1

    preferred_char_count = sum(
        1 for char in stripped if OCR_PREFERRED_CHAR_RE.fullmatch(char)
    )
    symbol_count = len(stripped) - preferred_char_count
    multi_char_line_count = sum(
        1 for line in text.splitlines() if len(line.strip()) >= 2
    )

    return (
        len(stripped)
        + preferred_char_count * 2
        + multi_char_line_count * 4
        - symbol_count * 2
    )


def _japanese_char_ratio(text: str) -> float:
    """空白除去後テキストに占める日本語文字比率を返す。"""
    stripped = "".join(char for char in text if not char.isspace())
    if not stripped:
        return 0.0

    japanese_char_count = sum(
        1 for char in stripped if OCR_JAPANESE_CHAR_RE.fullmatch(char)
    )
    return japanese_char_count / len(stripped)


def _get_ocr_textpage(page: Any, dpi: int) -> Any:
    """指定 DPI で OCR TextPage を作成する。"""
    return page.get_textpage_ocr(
        language=OCR_LANGUAGE,
        dpi=dpi,
        full=True,
    )


def _get_best_ocr_candidate(page: Any) -> OcrCandidate | None:
    """画像ページに対して複数DPIの OCR を試し、最良候補を返す。"""
    best_candidate: OcrCandidate | None = None
    best_score = -1

    for dpi in OCR_RETRY_DPI_CANDIDATES:
        textpage = _get_ocr_textpage(page, dpi=dpi)
        raw_page = cast(
            dict[str, Any],
            page.get_text("rawdict", textpage=textpage, sort=False),
        )
        text = page.get_text(textpage=textpage)
        score = _score_ocr_text(text)
        if score > best_score:
            best_score = score
            best_candidate = {
                "dpi": dpi,
                "raw_page": raw_page,
                "text": text,
                "score": score,
            }

    return best_candidate


def _get_tesseract_cli_text(
    page: Any,
    dpi: int,
    language: str,
    psm: str,
    clip: Any | None = None,
    rotate_clockwise: bool = False,
) -> str:
    """Tesseract CLI を使ってページ画像を OCR し、プレーンテキストを返す。"""
    if not TESSERACT_BIN_PATH.exists():
        return ""

    pixmap = page.get_pixmap(dpi=dpi, alpha=False, clip=clip)
    with tempfile.TemporaryDirectory() as temp_dir:
        image_path = Path(temp_dir) / "page.png"
        pixmap.save(image_path)
        if rotate_clockwise:
            with Image.open(image_path) as image:
                rotated = image.rotate(-90, expand=True)
                rotated.save(image_path)
        result = subprocess.run(
            [
                str(TESSERACT_BIN_PATH),
                str(image_path),
                "stdout",
                "-l",
                language,
                "--psm",
                psm,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            return ""

        return result.stdout


def _maybe_replace_vertical_block_with_tesseract(
    page: Any,
    block: dict[str, Any],
    block_text: str,
    selected_dpi: int | None,
) -> tuple[str, bool]:
    """縦書き候補ブロックだけを jpn_vert OCR で再評価する。"""
    if selected_dpi is None:
        return block_text, False

    normalized_block_text = join_vertical_text_lines(block_text)
    current_score = _score_ocr_text(normalized_block_text)
    x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
    width = max(1.0, float(x1) - float(x0))
    height = max(1.0, float(y1) - float(y0))
    x_margin = width * TESSERACT_VERTICAL_CLIP_X_MARGIN_RATIO
    y_margin = height * TESSERACT_VERTICAL_CLIP_Y_MARGIN_RATIO
    page_rect = page.rect
    clip = (
        max(page_rect.x0, float(x0) - x_margin),
        max(page_rect.y0, float(y0) - y_margin),
        min(page_rect.x1, float(x1) + x_margin),
        min(page_rect.y1, float(y1) + y_margin),
    )
    vertical_text = _get_tesseract_cli_text(
        page,
        dpi=selected_dpi,
        language=TESSERACT_VERTICAL_LANGUAGE,
        psm=TESSERACT_VERTICAL_PSM,
        clip=clip,
    )
    rotated_text = _get_tesseract_cli_text(
        page,
        dpi=selected_dpi,
        language=TESSERACT_ROTATED_LANGUAGE,
        psm=TESSERACT_ROTATED_PSM,
        clip=clip,
        rotate_clockwise=True,
    )

    candidates = [normalized_block_text]
    if vertical_text:
        candidates.append(join_vertical_text_lines(vertical_text))
    if (
        rotated_text
        and _japanese_char_ratio(rotated_text) >= TESSERACT_ROTATED_MIN_JAPANESE_RATIO
    ):
        candidates.append(join_vertical_text_lines(rotated_text))

    best_text = normalized_block_text
    best_score = current_score
    vertical_candidate_score = (
        _score_ocr_text(candidates[1]) if len(candidates) >= 2 else current_score
    )
    for candidate_text in candidates[1:]:
        candidate_score = _score_ocr_text(candidate_text)
        if candidate_text == candidates[-1] and len(candidates) >= 3:
            if candidate_score < vertical_candidate_score + TESSERACT_ROTATED_MIN_SCORE_OVER_VERTICAL:
                continue
        if candidate_score > best_score:
            best_score = candidate_score
            best_text = candidate_text

    if best_score < current_score + TESSERACT_VERTICAL_MIN_SCORE_GAIN:
        return normalized_block_text, False

    return best_text, True


def _group_vertical_ocr_bands(raw_blocks: list[dict[str, Any]]) -> list[VerticalOcrBand]:
    """近接する縦書き OCR 候補ブロックを帯単位にまとめる。"""
    candidates: list[tuple[int, tuple[float, float, float, float]]] = []

    for index, block in enumerate(raw_blocks):
        if block.get("type") != 0 or not _is_probable_vertical_ocr_block(block):
            continue
        x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
        candidates.append((index, (float(x0), float(y0), float(x1), float(y1))))

    if not candidates:
        return []

    candidates.sort(key=lambda item: item[1][1])
    bands: list[VerticalOcrBand] = []

    for index, (x0, y0, x1, y1) in candidates:
        width = max(1.0, x1 - x0)
        height = max(1.0, y1 - y0)
        block_center_x = (x0 + x1) / 2
        matched_band: VerticalOcrBand | None = None

        for band in bands:
            band_width = max(1.0, band["x1"] - band["x0"])
            band_height = max(1.0, band["y1"] - band["y0"])
            band_center_x = (band["x0"] + band["x1"]) / 2
            x_tolerance = max(width, band_width) * (1.0 + VERTICAL_OCR_BAND_X_TOLERANCE_RATIO)
            y_gap_tolerance = max(height, band_height / max(1, len(band["block_indices"]))) * (
                1.0 + VERTICAL_OCR_BAND_Y_GAP_RATIO
            )
            vertical_gap = y0 - band["y1"]

            if abs(block_center_x - band_center_x) <= x_tolerance and vertical_gap <= y_gap_tolerance:
                matched_band = band
                break

        if matched_band is None:
            bands.append(
                {
                    "block_indices": [index],
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                }
            )
            continue

        matched_band["block_indices"].append(index)
        matched_band["x0"] = min(matched_band["x0"], x0)
        matched_band["y0"] = min(matched_band["y0"], y0)
        matched_band["x1"] = max(matched_band["x1"], x1)
        matched_band["y1"] = max(matched_band["y1"], y1)

    return bands


def _maybe_replace_vertical_band_with_tesseract(
    page: Any,
    band: VerticalOcrBand,
    raw_blocks: list[dict[str, Any]],
    selected_dpi: int | None,
) -> str:
    """近接ブロックをまとめた縦帯に対して OCR 候補を比較し、最良候補を返す。"""
    base_parts: list[str] = []
    for index in band["block_indices"]:
        text = _format_vertical_ocr_block(raw_blocks[index])
        if text:
            base_parts.append(join_vertical_text_lines(text))

    base_text = "\n\n".join(part for part in base_parts if part).strip()
    if selected_dpi is None or not base_text:
        return base_text

    width = max(1.0, band["x1"] - band["x0"])
    height = max(1.0, band["y1"] - band["y0"])
    x_margin = width * TESSERACT_VERTICAL_CLIP_X_MARGIN_RATIO
    y_margin = height * TESSERACT_VERTICAL_CLIP_Y_MARGIN_RATIO
    page_rect = page.rect
    clip = (
        max(page_rect.x0, band["x0"] - x_margin),
        max(page_rect.y0, band["y0"] - y_margin),
        min(page_rect.x1, band["x1"] + x_margin),
        min(page_rect.y1, band["y1"] + y_margin),
    )

    current_score = _score_ocr_text(base_text)
    vertical_text = join_vertical_text_lines(
        _get_tesseract_cli_text(
            page,
            dpi=selected_dpi,
            language=TESSERACT_VERTICAL_LANGUAGE,
            psm=TESSERACT_VERTICAL_PSM,
            clip=clip,
        )
    )
    rotated_text = join_vertical_text_lines(
        _get_tesseract_cli_text(
            page,
            dpi=selected_dpi,
            language=TESSERACT_ROTATED_LANGUAGE,
            psm=TESSERACT_ROTATED_PSM,
            clip=clip,
            rotate_clockwise=True,
        )
    )

    best_text = base_text
    best_score = current_score

    vertical_score = _score_ocr_text(vertical_text) if vertical_text else -1
    if vertical_score > best_score:
        best_text = vertical_text
        best_score = vertical_score

    rotated_score = _score_ocr_text(rotated_text) if rotated_text else -1
    if (
        rotated_text
        and _japanese_char_ratio(rotated_text) >= TESSERACT_ROTATED_MIN_JAPANESE_RATIO
        and rotated_score >= max(best_score + TESSERACT_ROTATED_MIN_SCORE_OVER_VERTICAL, current_score + TESSERACT_VERTICAL_MIN_SCORE_GAIN)
    ):
        best_text = rotated_text
        best_score = rotated_score

    if best_score < current_score + TESSERACT_VERTICAL_MIN_SCORE_GAIN:
        return base_text

    return best_text


def _should_auto_force_ocr(
    native_chars: int,
    native_score: int,
    ocr_score: int,
) -> bool:
    """埋め込みテキストより OCR を優先するか判定する。"""
    if native_chars == 0:
        return ocr_score >= 0

    minimum_gain = max(
        AUTO_FORCE_OCR_MIN_SCORE_GAIN,
        int(native_score * (AUTO_FORCE_OCR_SCORE_RATIO - 1.0)),
    )
    return ocr_score >= native_score + minimum_gain


def _extract_span_text(span: dict[str, Any]) -> str:
    """rawdict span から文字列を復元する。"""
    chars = span.get("chars", [])
    if chars:
        return "".join(str(char.get("c", "")) for char in chars)

    return str(span.get("text", ""))


def _extract_line_chars(line: dict[str, Any]) -> list[PdfChar]:
    """line 内の文字情報を走査し、座標付き文字列として返す。"""
    chars: list[PdfChar] = []

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

    return chars


def _extract_line_fragment(line: dict[str, Any]) -> PdfLineFragment | None:
    """line から縦書き復元用の断片情報を作る。"""
    text = _extract_line_text(line)
    if not text:
        return None

    x0, y0, x1, y1 = line.get("bbox", (0, 0, 0, 0))
    return {
        "text": text,
        "x": (float(x0) + float(x1)) / 2,
        "y": float(y0),
        "width": max(0.0, float(x1) - float(x0)),
        "height": max(0.0, float(y1) - float(y0)),
    }


def _extract_vertical_line(line: dict[str, Any]) -> VerticalPdfColumn | None:
    """縦書き line を1列分の本文へ変換する。"""
    chars = _extract_line_chars(line)
    if not chars:
        return None

    sorted_chars = sorted(chars, key=lambda item: item["y"])
    text = "".join(char["text"] for char in sorted_chars).strip()
    if not text:
        return None
    if len(text) <= 5 and PUNCTUATION_ONLY_RE.fullmatch(text):
        return None

    x0, y0, x1, y1 = line.get("bbox", (0, 0, 0, 0))
    sizes = [char["size"] for char in sorted_chars]
    return {
        "x": (float(x0) + float(x1)) / 2,
        "y": float(y0),
        "text": text,
        "median_size": _median(sizes),
    }


def _format_vertical_pdf_columns(columns: list[VerticalPdfColumn]) -> list[str]:
    """縦書き line 列を右から左へ並べ替え、本文行を組み立てる。"""
    if not columns:
        return []

    ordered_columns = sorted(columns, key=lambda column: (-column["x"], column["y"]))
    base_size = _median([column["median_size"] for column in columns])
    ruby_threshold = base_size * VERTICAL_RUBY_FONT_SIZE_RATIO
    pending_ruby: list[str] = []
    lines: list[str] = []

    for column in ordered_columns:
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


def _is_probable_vertical_ocr_block(block: dict[str, Any]) -> bool:
    """OCR 後に短い横書き行の束として返った縦書きブロックらしいか判定する。"""
    lines = block.get("lines", [])
    if len(lines) < 3:
        return False

    if any(int(line.get("wmode", 0)) == 1 for line in lines):
        return False

    texts = [_extract_line_text(line) for line in lines]
    texts = [text for text in texts if text]
    if len(texts) < 3:
        return False

    short_line_ratio = sum(1 for text in texts if len(text) <= 3) / len(texts)
    average_line_length = sum(len(text) for text in texts) / len(texts)
    x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
    width = max(1.0, float(x1) - float(x0))
    height = max(1.0, float(y1) - float(y0))
    aspect_ratio = height / width

    if (
        short_line_ratio >= VERTICAL_OCR_BLOCK_SHORT_LINE_RATIO
        and average_line_length <= VERTICAL_OCR_BLOCK_MAX_AVERAGE_LINE_LENGTH
        and aspect_ratio >= VERTICAL_OCR_BLOCK_MIN_ASPECT_RATIO
    ):
        return True

    return (
        len(texts) >= VERTICAL_OCR_BLOCK_DENSE_MIN_LINE_COUNT
        and short_line_ratio >= VERTICAL_OCR_BLOCK_FALLBACK_SHORT_LINE_RATIO
        and average_line_length <= VERTICAL_OCR_BLOCK_FALLBACK_MAX_AVERAGE_LINE_LENGTH
    )


def _format_vertical_ocr_block(block: dict[str, Any]) -> str:
    """短い行の束として返った OCR ブロックを縦書き列として再構成する。"""
    fragments = [
        fragment
        for line in block.get("lines", [])
        if (fragment := _extract_line_fragment(line)) is not None
    ]
    if not fragments:
        return ""

    median_width = _median([fragment["width"] for fragment in fragments])
    x_tolerance = max(4.0, median_width * 1.5)
    columns: list[list[PdfLineFragment]] = []

    for fragment in sorted(fragments, key=lambda item: item["x"], reverse=True):
        target_column: list[PdfLineFragment] | None = None
        for column in columns:
            column_x = sum(item["x"] for item in column) / len(column)
            if abs(column_x - fragment["x"]) <= x_tolerance:
                target_column = column
                break

        if target_column is None:
            columns.append([fragment])
            continue

        target_column.append(fragment)

    formatted_columns: list[str] = []
    for column in columns:
        ordered_fragments = sorted(column, key=lambda item: item["y"])
        text = "".join(fragment["text"] for fragment in ordered_fragments).strip()
        if text:
            formatted_columns.append(text)

    return "\n".join(formatted_columns)


def _format_horizontal_pdf_lines(lines: list[dict[str, Any]]) -> str:
    """横書き line 群を上から下へ読み順に整える。"""
    ordered_lines = sorted(
        lines,
        key=lambda line: (
            float(line.get("bbox", (0, 0, 0, 0))[1]),
            float(line.get("bbox", (0, 0, 0, 0))[0]),
        ),
    )
    texts: list[str] = []

    for line in ordered_lines:
        cleaned = _extract_line_text(line)
        if cleaned:
            texts.append(cleaned)

    return "\n".join(texts)


def _extract_pdf_block_text(
    block: dict[str, Any],
    page: Any | None = None,
    selected_dpi: int | None = None,
) -> PdfBlockText | None:
    """PyMuPDF の block / line / wmode を使って1ブロック分の本文を復元する。"""
    if block.get("type") != 0:
        return None

    if _is_probable_vertical_ocr_block(block):
        text = _format_vertical_ocr_block(block)
        if not text:
            return None
        replaced = False
        if page is not None:
            text, replaced = _maybe_replace_vertical_block_with_tesseract(
                page,
                block,
                text,
                selected_dpi,
            )

        x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
        return {
            "x0": float(x0),
            "y0": float(y0),
            "x1": float(x1),
            "y1": float(y1),
            "writing_mode": 1,
            "text": text if replaced else join_vertical_text_lines(text),
        }

    lines = block.get("lines", [])
    if not lines:
        return None

    vertical_columns: list[VerticalPdfColumn] = []
    horizontal_lines: list[dict[str, Any]] = []

    for line in lines:
        wmode = int(line.get("wmode", 0))
        if wmode == 1:
            column = _extract_vertical_line(line)
            if column is not None:
                vertical_columns.append(column)
            continue

        horizontal_lines.append(line)

    x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
    vertical_text = "\n".join(_format_vertical_pdf_columns(vertical_columns)).strip()
    horizontal_text = _format_horizontal_pdf_lines(horizontal_lines).strip()

    text_parts = [part for part in [vertical_text, horizontal_text] if part]
    if not text_parts:
        return None

    writing_mode = 1 if len(vertical_columns) >= len(horizontal_lines) else 0
    text = "\n".join(text_parts) if len(text_parts) == 2 else text_parts[0]
    return {
        "x0": float(x0),
        "y0": float(y0),
        "x1": float(x1),
        "y1": float(y1),
        "writing_mode": writing_mode,
        "text": text,
    }


def _sort_pdf_blocks(blocks: list[PdfBlockText]) -> list[PdfBlockText]:
    """ページの主書字方向に合わせて本文ブロックを並べ替える。"""
    if not blocks:
        return []

    vertical_count = sum(1 for block in blocks if block["writing_mode"] == 1)
    horizontal_count = len(blocks) - vertical_count

    if vertical_count >= horizontal_count:
        return sorted(
            blocks,
            key=lambda block: (-block["x1"], block["y0"], block["x0"]),
        )

    return sorted(
        blocks,
        key=lambda block: (block["y0"], block["x0"], -block["x1"]),
    )


def _get_page_rawdict(
    page: Any,
    page_number: int,
    force_ocr: bool = False,
    auto_force_ocr: bool = False,
) -> tuple[dict[str, Any], PdfPageDecision]:
    """ネイティブテキストを優先し、必要に応じて OCR を使って rawdict を返す。"""
    global _HAS_WARNED_PYMUPDF_OCR

    raw_page = cast(dict[str, Any], page.get_text("rawdict", sort=False))
    native_chars = _count_rawdict_text_chars(raw_page)
    native_text = _extract_rawdict_text(raw_page)
    native_score = _score_ocr_text(native_text)

    default_decision: PdfPageDecision = {
        "page_number": page_number,
        "source": "native",
        "reason": "embedded text preferred",
        "native_chars": native_chars,
        "native_score": native_score,
        "selected_score": native_score,
        "selected_dpi": None,
    }

    if not force_ocr and not auto_force_ocr and native_chars > 0:
        return raw_page, default_decision

    try:
        _configure_pymupdf_ocr_environment()
        best_candidate = _get_best_ocr_candidate(page)
        if best_candidate is not None:
            if force_ocr:
                return best_candidate["raw_page"], {
                    "page_number": page_number,
                    "source": "ocr",
                    "reason": "forced by --force-ocr",
                    "native_chars": native_chars,
                    "native_score": native_score,
                    "selected_score": best_candidate["score"],
                    "selected_dpi": best_candidate["dpi"],
                }

            if native_chars == 0:
                return best_candidate["raw_page"], {
                    "page_number": page_number,
                    "source": "ocr",
                    "reason": "no embedded text",
                    "native_chars": native_chars,
                    "native_score": native_score,
                    "selected_score": best_candidate["score"],
                    "selected_dpi": best_candidate["dpi"],
                }

            if auto_force_ocr and _should_auto_force_ocr(
                native_chars=native_chars,
                native_score=native_score,
                ocr_score=best_candidate["score"],
            ):
                return best_candidate["raw_page"], {
                    "page_number": page_number,
                    "source": "ocr",
                    "reason": "auto-selected: OCR score exceeded embedded text",
                    "native_chars": native_chars,
                    "native_score": native_score,
                    "selected_score": best_candidate["score"],
                    "selected_dpi": best_candidate["dpi"],
                }
    except Exception as exc:
        if not _HAS_WARNED_PYMUPDF_OCR:
            print(
                "PyMuPDF OCR を利用できなかったため、OCRなしのテキスト抽出へフォールバックします: "
                f"{exc}",
                file=sys.stderr,
            )
            _HAS_WARNED_PYMUPDF_OCR = True

    if auto_force_ocr and native_chars > 0:
        default_decision["reason"] = "auto-selected native text"

    return raw_page, default_decision


def _build_ocr_report(decisions: list[PdfPageDecision]) -> str:
    """OCR 判定レポート文字列を作る。"""
    lines = ["# OCR Decision Report", ""]

    for decision in decisions:
        dpi_text = (
            str(decision["selected_dpi"])
            if decision["selected_dpi"] is not None
            else "-"
        )
        lines.append(
            " | ".join(
                [
                    f"page={decision['page_number']}",
                    f"source={decision['source']}",
                    f"reason={decision['reason']}",
                    f"native_chars={decision['native_chars']}",
                    f"native_score={decision['native_score']}",
                    f"selected_score={decision['selected_score']}",
                    f"dpi={dpi_text}",
                ]
            )
        )

    return "\n".join(lines) + "\n"


def extract_vertical_pdf_text(
    input_file: Path,
    force_ocr: bool = False,
    auto_force_ocr: bool = False,
) -> tuple[str, list[PdfPageDecision]]:
    """
    PDFの block / line / wmode 情報を使い、縦横混在本文を抽出する。

    埋め込みテキストが無いページでは PyMuPDF OCR を使い、300 / 450 / 600 DPI の候補から
    結果が良いものを採用する。縦書き line は右から左、横書き line は上から下の読順で
    本文を復元する。
    """
    if importlib.util.find_spec("fitz") is None:
        return ""

    fitz = importlib.import_module("fitz")

    page_texts: list[str] = []
    decisions: list[PdfPageDecision] = []
    with fitz.open(input_file) as doc:
        for page_number, page in enumerate(doc, start=1):
            raw_page, decision = _get_page_rawdict(
                page,
                page_number=page_number,
                force_ocr=force_ocr,
                auto_force_ocr=auto_force_ocr,
            )
            decisions.append(decision)
            blocks: list[PdfBlockText] = []
            raw_blocks = raw_page.get("blocks", [])
            consumed_block_indices: set[int] = set()

            if decision["source"] == "ocr":
                for band in _group_vertical_ocr_bands(raw_blocks):
                    band_text = _maybe_replace_vertical_band_with_tesseract(
                        page,
                        band,
                        raw_blocks,
                        decision["selected_dpi"],
                    )
                    if not band_text:
                        continue

                    consumed_block_indices.update(band["block_indices"])
                    blocks.append(
                        {
                            "x0": band["x0"],
                            "y0": band["y0"],
                            "x1": band["x1"],
                            "y1": band["y1"],
                            "writing_mode": 1,
                            "text": band_text,
                        }
                    )

            for block_index, block in enumerate(raw_blocks):
                if block_index in consumed_block_indices:
                    continue
                extracted = _extract_pdf_block_text(
                    block,
                    page=page if decision["source"] == "ocr" else None,
                    selected_dpi=decision["selected_dpi"],
                )
                if extracted is not None:
                    blocks.append(extracted)

            ordered_blocks = _sort_pdf_blocks(blocks)
            page_text = "\n\n".join(block["text"] for block in ordered_blocks if block["text"])
            if page_text:
                page_texts.append(page_text)

    return "\n\n".join(page_texts), decisions


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


def save_text(content: str, output_path: Path) -> None:
    """テキストファイルをUTF-8で保存する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"保存完了: {output_path}")


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
    force_ocr: bool = False,
    auto_force_ocr: bool = False,
    ocr_report: bool = False,
) -> None:
    """
    PDF、Excel、WordなどのローカルファイルをMarkdownに変換する。
    """
    input_file = Path(input_path)

    if not input_file.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {input_file}")

    text_content = ""
    decisions: list[PdfPageDecision] = []
    use_pymupdf_pdf_path = input_file.suffix.lower() == ".pdf" and (
        join_vertical_lines or force_ocr or auto_force_ocr or ocr_report
    )

    if use_pymupdf_pdf_path:
        text_content, decisions = extract_vertical_pdf_text(
            input_file,
            force_ocr=force_ocr,
            auto_force_ocr=auto_force_ocr,
        )
        if join_vertical_lines or force_ocr or auto_force_ocr:
            text_content = join_vertical_text_lines(text_content)

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

    if ocr_report and decisions:
        report_path = output_path.with_name(f"{output_path.stem}.ocr-report.txt")
        save_text(_build_ocr_report(decisions), report_path)


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
    parser_file.add_argument(
        "--force-ocr",
        action="store_true",
        help="埋め込みテキストがあるPDFでも、PyMuPDF OCRを優先して抽出する",
    )
    parser_file.add_argument(
        "--auto-force-ocr",
        action="store_true",
        help="埋め込みテキストとOCR結果を比較し、OCRの方が良ければ自動で切り替える",
    )
    parser_file.add_argument(
        "--ocr-report",
        action="store_true",
        help="ページごとの native / OCR 判定結果をテキストレポートとして保存する",
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
        if args.force_ocr and args.auto_force_ocr:
            parser.error("--force-ocr と --auto-force-ocr は同時に指定できません。")
        convert_file_to_markdown(
            input_path=args.input,
            output_dir=args.output_dir,
            output_file=args.output_file,
            join_vertical_lines=args.join_vertical_lines,
            force_ocr=args.force_ocr,
            auto_force_ocr=args.auto_force_ocr,
            ocr_report=args.ocr_report,
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
