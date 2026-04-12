const statusEl = document.getElementById("status");
const previewEl = document.getElementById("preview-text");
const outputNameEl = document.getElementById("output-name");
const outputPreviewEl = document.getElementById("output-preview");
const fileWrap = document.getElementById("file-input-wrap");
const youtubeWrap = document.getElementById("youtube-input-wrap");
const fileInput = document.getElementById("file-input");
const youtubeInput = document.getElementById("youtube-url");
const convertBtn = document.getElementById("convert-btn");

let pyodide;
let ready = false;

const sanitizeFileName = (name) => {
  const sanitized = name.replace(/[\\/:*?"<>|]/g, "").replace(/\s+/g, " ").trim();
  return sanitized || "output";
};

const setStatus = (message) => {
  statusEl.textContent = message;
};

const selectedMode = () =>
  document.querySelector('input[name="mode"]:checked')?.value ?? "file";

const refreshMode = () => {
  const mode = selectedMode();
  fileWrap.classList.toggle("hidden", mode !== "file");
  youtubeWrap.classList.toggle("hidden", mode !== "youtube");
};

const refreshOutputPreview = () => {
  const current = (outputNameEl.value || "output.md").trim();
  outputPreviewEl.textContent = `出力先: Downloads/${current}`;
};

const defaultOutputName = () => {
  const mode = selectedMode();

  if (mode === "file") {
    const file = fileInput.files?.[0];
    if (!file) return "output.md";
    const base = file.name.replace(/\.[^/.]+$/, "");
    return `${sanitizeFileName(base)}.md`;
  }

  return "youtube.md";
};

const writeDownload = (filename, text) => {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
};

const initPyodideRuntime = async () => {
  setStatus("WASMランタイム (Pyodide) をロードしています...");
  pyodide = await loadPyodide();
  ready = true;
  setStatus("準備完了: 変換できます。");
};

const convertFile = async () => {
  const file = fileInput.files?.[0];
  if (!file) {
    throw new Error("ファイルを選択してください。");
  }

  const bytes = new Uint8Array(await file.arrayBuffer());
  const safeName = sanitizeFileName(file.name).replace(/\s/g, "_");
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const tmpPath = `/tmp/${Date.now()}_${safeName}`;

  pyodide.FS.writeFile(tmpPath, bytes);
  pyodide.globals.set("input_path", tmpPath);
  pyodide.globals.set("input_ext", ext);

  const result = await pyodide.runPythonAsync(`
from pathlib import Path
import csv
import json
import re
from html.parser import HTMLParser

path = Path(input_path)
ext = f".{input_ext}" if input_ext else path.suffix.lower()
raw = path.read_bytes()

def to_md_table(rows):
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    padded = [r + [""] * (width - len(r)) for r in rows]
    header = padded[0]
    sep = ["---"] * width
    body = padded[1:] or [[""] * width]

    def row_to_line(r):
        escaped = [c.replace("|", "\\|") for c in r]
        return "| " + " | ".join(escaped) + " |"

    lines = [row_to_line(header), row_to_line(sep)]
    lines += [row_to_line(r) for r in body]
    return "\n".join(lines)

if ext in {".txt", ".md"}:
    output = raw.decode("utf-8", errors="replace")
elif ext == ".json":
    data = json.loads(raw.decode("utf-8", errors="replace"))
    output = "~~~json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n~~~"
elif ext in {".csv", ".tsv"}:
    delimiter = "\t" if ext == ".tsv" else ","
    text = raw.decode("utf-8", errors="replace")
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    output = to_md_table(rows)
elif ext in {".html", ".htm"}:
    text = raw.decode("utf-8", errors="replace")

    class Extractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            stripped = data.strip()
            if stripped:
                self.parts.append(stripped)

    parser = Extractor()
    parser.feed(text)
    output = "\n\n".join(parser.parts)
else:
    raise ValueError(
        "WASM版で未対応の拡張子です。対応: txt, md, json, csv, tsv, html, htm"
    )

output
`);

  pyodide.FS.unlink(tmpPath);
  return String(result);
};

const extractVideoId = (url) => {
  try {
    const parsed = new URL(url);
    if (parsed.hostname.includes("youtu.be")) {
      return parsed.pathname.replace("/", "");
    }
    if (parsed.hostname.includes("youtube.com")) {
      return parsed.searchParams.get("v") || "";
    }
  } catch {
    return "";
  }
  return "";
};

const decodeHtml = (text) => {
  const parser = new DOMParser();
  const doc = parser.parseFromString(`<!doctype html><body>${text}`, "text/html");
  return doc.body.textContent || "";
};

const fetchTranscript = async (videoId) => {
  for (const lang of ["ja", "en"]) {
    const endpoint = `https://www.youtube.com/api/timedtext?lang=${lang}&v=${videoId}`;
    try {
      const response = await fetch(endpoint);
      if (!response.ok) continue;
      const xmlText = await response.text();
      if (!xmlText.includes("<text")) continue;

      const xml = new DOMParser().parseFromString(xmlText, "application/xml");
      const nodes = [...xml.querySelectorAll("text")];
      if (!nodes.length) continue;

      return nodes
        .map((node) => {
          const sec = Number(node.getAttribute("start") || "0").toFixed(2);
          const line = decodeHtml(node.textContent || "").trim();
          return line ? `- [${sec}s] ${line}` : "";
        })
        .filter(Boolean)
        .join("\n");
    } catch {
      // ignore and try next language
    }
  }

  return "字幕を取得できませんでした（CORSまたは字幕未公開の可能性があります）。";
};

const convertYoutube = async () => {
  const url = youtubeInput.value.trim();
  if (!url) {
    throw new Error("YouTube URL を入力してください。");
  }

  const videoId = extractVideoId(url);
  if (!videoId) {
    throw new Error("有効な YouTube URL ではありません。");
  }

  const oembedUrl = `https://www.youtube.com/oembed?url=${encodeURIComponent(url)}&format=json`;
  const metaRes = await fetch(oembedUrl);
  if (!metaRes.ok) {
    throw new Error("YouTubeメタデータの取得に失敗しました。");
  }

  const meta = await metaRes.json();
  const transcriptMd = await fetchTranscript(videoId);

  return [
    `# ${meta.title || "YouTube Video"}`,
    "",
    `- URL: ${url}`,
    `- チャンネル: ${meta.author_name || "不明"}`,
    "",
    "## Transcript",
    transcriptMd,
  ].join("\n");
};

const onConvert = async () => {
  if (!ready) {
    setStatus("まだ初期化中です。少し待ってから再実行してください。");
    return;
  }

  const mode = selectedMode();
  const outputName = (outputNameEl.value || defaultOutputName()).trim();
  setStatus("変換中...");
  convertBtn.disabled = true;

  try {
    const markdown = mode === "file" ? await convertFile() : await convertYoutube();
    previewEl.value = markdown;
    writeDownload(outputName, markdown);
    setStatus(`変換完了: Downloads/${outputName} に保存しました。`);
  } catch (error) {
    setStatus(`エラー: ${error?.message ?? String(error)}`);
  } finally {
    convertBtn.disabled = false;
  }
};

fileInput.addEventListener("change", () => {
  outputNameEl.value = defaultOutputName();
  refreshOutputPreview();
});

youtubeInput.addEventListener("input", refreshOutputPreview);

outputNameEl.addEventListener("input", refreshOutputPreview);

for (const radio of document.querySelectorAll('input[name="mode"]')) {
  radio.addEventListener("change", () => {
    refreshMode();
    outputNameEl.value = defaultOutputName();
    refreshOutputPreview();
  });
}

convertBtn.addEventListener("click", onConvert);

outputNameEl.value = "output.md";
refreshMode();
refreshOutputPreview();
initPyodideRuntime().catch((error) => {
  setStatus(`初期化失敗: ${error?.message ?? String(error)}`);
});
