# Markdown変換ツール

PDF・Excel・Wordなどのローカルファイル、およびYouTube動画をMarkdown形式に変換するCLIツールです。

---

## 概要

本ツールは、コマンドライン引数によって処理を切り替え、以下の入力をMarkdownに変換します。

* ローカルファイル（PDF / Excel / Word など）
* YouTube動画（URL）

---

## 主な機能

### 1. ファイル変換（fileモード）

`MarkItDown` を利用して、ローカルファイルをMarkdownに変換します。

* 対応形式：PDF / Excel / Word など
* 出力形式：Markdown（.md）
* 出力ファイル名：元ファイル名を使用

---

### 2. YouTube変換（youtubeモード）

YouTube URLを入力として、以下をMarkdownにまとめます。

* 動画タイトル
* 説明文
* 字幕（日本語 or 英語）

---

## YouTube出力ファイル名の仕様

* `MarkItDown` により取得した動画タイトルを使用
* ファイル名に使用できない文字は自動除去
* 空白は整理（連続スペース → 1つ）
* タイトルは **先頭30文字まで使用**
* `--output-file` 指定時はそちらを優先

### 例

| 動画タイトル                | 出力ファイル                 |
| --------------------- | ---------------------- |
| `Python入門 / データ分析の基本` | `Python入門 データ分析の基本.md` |

---

## ディレクトリ構成例

```
.
├── main.py
├── data/
│   ├── sample.xlsx
│   ├── sample.pdf
│   └── sample.docx
├── output/
└── README.md
```

---

## セットアップ

### 1. 仮想環境（推奨）

```bash
python -m venv venv
```

### 2. 仮想環境の有効化

#### Windows

```bash
venv\Scripts\activate
```

#### macOS / Linux

```bash
source venv/bin/activate
```

### 3. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

---

## requirements.txt

```txt
markitdown
youtube-transcript-api
```

---

## 使い方

## 1. ファイルをMarkdownに変換

```bash
python main.py file <入力ファイルパス>
```

### 例

```bash
python main.py file data/sample.xlsx
python main.py file data/sample.pdf
python main.py file data/sample.docx
```

### 出力例

```
output/sample.md
```

---

## 2. 出力ディレクトリ指定

```bash
python main.py file data/sample.pdf -o output_dir
```

---

## 3. 出力ファイル名指定

```bash
python main.py file data/sample.docx --output-file result.md
```

---

## 4. YouTube動画をMarkdownに変換

```bash
python main.py youtube <YouTube URL>
```

### 例

```bash
python main.py youtube "https://www.youtube.com/watch?v=8mN16cORwkc"
```

### 出力例

```
output/動画タイトル.md
```

---

## 5. YouTube出力ファイル名指定

```bash
python main.py youtube "https://www.youtube.com/watch?v=8mN16cORwkc" --output-file youtube_result.md
```

---

## コマンド仕様

### サブコマンド

| コマンド      | 説明                    |
| --------- | --------------------- |
| `file`    | ローカルファイルをMarkdownに変換  |
| `youtube` | YouTube動画をMarkdownに変換 |

---

### オプション

| オプション                | 説明       | デフォルト    |
| -------------------- | -------- | -------- |
| `-o`, `--output-dir` | 出力ディレクトリ | `output` |
| `--output-file`      | 出力ファイル名  | 自動生成     |

---

## 出力仕様

### fileモード

* 入力ファイル名をそのまま使用
* 拡張子 `.md`

#### 例

```
input: report.pdf
output: report.md
```

---

### youtubeモード

* 動画タイトルを元にファイル名生成
* 使用不可文字を削除
* 30文字で切り詰め
* 拡張子 `.md`

#### 例

```
タイトル: 【初心者向け】Pythonで学ぶ表データ処理入門
出力: 【初心者向け】Pythonで学ぶ表データ処理入門.md
```

---

## 字幕取得仕様

* 対応言語：

  * 日本語（ja）
  * 英語（en）

* 優先順位：

  1. 手動字幕
  2. 自動生成字幕

---

## エラーハンドリング

以下の場合はエラーとなる可能性があります。

* 入力ファイルが存在しない
* 無効なYouTube URL
* 字幕が存在しない
* 字幕が無効化されている動画
* ネットワークエラー

---

## 注意事項

* YouTube字幕は動画の設定に依存します
* 同じタイトルの動画は上書きされる可能性があります
* 長すぎるタイトルは30文字に切り詰められます

---

## 今後の改善案

* ファイル名に `video_id` を追加して重複防止
* 複数ファイル一括変換
* ログ出力の詳細化
* 要約機能（LLM連携）

---

## ライセンス

必要に応じて追記してください。

---
