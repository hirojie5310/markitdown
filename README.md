# Markdown変換ツール

PDF・Excel・Wordなどのローカルファイル、およびYouTube動画をMarkdown形式に変換するツールです。

- CLI版: `main.py`（`markitdown` を使用）
- GitHub Pages (WASM) 版: `index.html` + `app.js`（Pyodideを使用）

---

## 1. CLI版（既存）

`MarkItDown` を利用して以下をMarkdownに変換します。

- ローカルファイル（PDF / Excel / Word など）
- YouTube動画（URL）

### セットアップ

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 使い方

```bash
python main.py file <入力ファイルパス>
python main.py youtube <YouTube URL>
```

縦書きの書籍をスキャンしたPDFなどで、OCR結果が1文字ごとに改行されたり、
本文の列順が崩れたりする場合は、`--join-vertical-lines` を付けます。
PDFでは文字座標を使って縦書き列を右から左へ並べ替え、座標抽出が使えない場合は
空行で区切られた段落単位で本文を連結します。

```bash
python main.py file <入力PDFパス> --join-vertical-lines
```

---

## 2. GitHub Pages（WASM）版

ブラウザ上で Pyodide (Python on WebAssembly) を使って変換を行います。

> 注: `markitdown` は `onnxruntime` 依存があるため、Pyodide 上でそのままインストールできません。
> そのため WASM 版では、ブラウザ実行可能な変換ロジックに置き換えています。

### 機能

1. 入力方式を選択
   - ファイル選択
   - YouTube URL入力
2. 出力ファイル名（出力先）を確認
   - `Downloads/<filename>.md`
3. 変換して `.md` をダウンロード

### WASM版のファイル対応形式

- `.txt`
- `.md`
- `.json`
- `.csv`
- `.tsv`
- `.html` / `.htm`
- `.xlsx`（先頭行をヘッダとしてシートごとにMarkdown表へ変換）

### YouTube変換（WASM版）

- oEmbed API でタイトル/チャンネル情報を取得
- 字幕API (`timedtext`) を `ja` / `en`（手動・自動生成）で取得を試行
- CORS 制限に備えて、直接取得に失敗した場合は CORS プロキシ経由で再試行
- 字幕が取れない場合は理由メッセージをMarkdownに出力
- 出力ファイル名は、未指定時に動画タイトルを30文字以内に整形して自動生成

### ローカル確認

静的ファイルとして配信してください（`file://` ではなくHTTP推奨）。

```bash
python -m http.server 8000
# http://localhost:8000 にアクセス
```

### GitHub Pages公開手順

1. このリポジトリに `index.html`, `app.js`, `styles.css` をpush
2. GitHub の `Settings > Pages` を開く
3. `Deploy from a branch` を選択
4. ブランチ（例: `main`）とルート（`/ (root)`）を指定
5. 保存後、公開URLへアクセス

---

## 注意点

- 初回アクセス時は Pyodide のロードで時間がかかります。
- YouTube字幕取得はブラウザ制約/CORSや動画設定により失敗する場合があります。
- 高度なドキュメント変換（PDF / Office）は CLI版（`main.py`）の利用を推奨します。

---

## requirements.txt

```txt
markitdown
youtube-transcript-api
```