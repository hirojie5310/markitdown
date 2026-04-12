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

  const url = youtubeInput.value.trim();
  if (!url) return "youtube.md";
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
  setStatus("Pyodide をロードしています...");
  pyodide = await loadPyodide();

  setStatus("markitdown をインストールしています (初回のみ時間がかかります)...");
  await pyodide.loadPackage("micropip");
  await pyodide.runPythonAsync(`
import micropip
await micropip.install("markitdown")
from markitdown import MarkItDown
`);
  ready = true;
  setStatus("準備完了: 変換できます。");
};

const convertFile = async () => {
  const file = fileInput.files?.[0];
  if (!file) {
    throw new Error("ファイルを選択してください。");
  }

  const arrayBuf = await file.arrayBuffer();
  const bytes = new Uint8Array(arrayBuf);
  pyodide.FS.writeFile(`/tmp/${file.name}`, bytes);

  const safeName = file.name.replace(/'/g, "");
  const result = await pyodide.runPythonAsync(`
from markitdown import MarkItDown
md = MarkItDown()
result = md.convert('/tmp/${safeName}')
result.text_content
`);
  return String(result);
};

const convertYoutube = async () => {
  const url = youtubeInput.value.trim();
  if (!url) {
    throw new Error("YouTube URL を入力してください。");
  }

  const result = await pyodide.runPythonAsync(`
from markitdown import MarkItDown
md = MarkItDown()
result = md.convert('${url.replace(/'/g, "")}')
result.text_content
`);
  return String(result);
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
