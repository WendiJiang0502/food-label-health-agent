const elements = {
  fileInput: document.querySelector("#label-image"),
  dropZone: document.querySelector("#drop-zone"),
  imageStage: document.querySelector("#image-stage"),
  preview: document.querySelector("#label-preview"),
  annotationLayer: document.querySelector("#annotation-layer"),
  replaceImage: document.querySelector("#replace-image"),
  processing: document.querySelector("#processing"),
  heroLayout: document.querySelector("#hero-layout"),
  heroUploadButton: document.querySelector("#hero-upload-button"),
  workbench: document.querySelector("#workspace"),
  proofTitle: document.querySelector("#proof-title"),
  proofState: document.querySelector("#proof-state"),
  reviewRail: document.querySelector("#review-rail"),
  form: document.querySelector("#confirmation-form"),
  fieldList: document.querySelector("#field-list"),
  reviewCount: document.querySelector("#review-count"),
  confirmButton: document.querySelector("#confirm-button"),
  resultState: document.querySelector("#result-state"),
  resultMessage: document.querySelector("#result-message"),
  errorState: document.querySelector("#error-state"),
  errorMessage: document.querySelector("#error-message"),
  retryButton: document.querySelector("#retry-button"),
  liveRegion: document.querySelector("#live-region"),
  ocrStatus: document.querySelector("#ocr-status"),
};

elements.heroUploadButton.addEventListener("click", () => elements.fileInput.click());
loadHealthStatus();

const state = {
  file: null,
  previewUrl: null,
  analysis: null,
};

elements.fileInput.addEventListener("change", (event) => {
  const [file] = event.target.files;
  if (file) selectFile(file);
});

["dragenter", "dragover"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("is-dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  elements.dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.remove("is-dragging");
  });
});

elements.dropZone.addEventListener("drop", (event) => {
  const [file] = event.dataTransfer.files;
  if (file) selectFile(file);
});

elements.replaceImage.addEventListener("click", () => elements.fileInput.click());
elements.retryButton.addEventListener("click", () => {
  hideError();
  if (state.file) analyzeFile(state.file);
});

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.analysis) return;

  const fields = {};
  elements.fieldList.querySelectorAll("textarea[data-field-name]").forEach((field) => {
    fields[field.dataset.fieldName] = field.value.trim();
  });

  elements.confirmButton.disabled = true;
  elements.confirmButton.firstChild.textContent = "正在确认… ";
  announce("正在确认标签文字");

  try {
    const response = await fetch("/api/v1/labels/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_id: state.analysis.request_id,
        jurisdiction: "CN",
        applicable_date: new Date().toISOString().slice(0, 10),
        fields,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message || "标签确认失败。");

    elements.form.hidden = true;
    elements.resultMessage.textContent = "已完成确认。";
    elements.resultState.hidden = false;
    elements.resultState.focus();
    elements.proofState.textContent = "用户已确认";
    announce("识别文字已确认");
  } catch (error) {
    showError(error.message);
  } finally {
    elements.confirmButton.disabled = false;
    elements.confirmButton.firstChild.textContent = "确认识别文字 ";
  }
});

function selectFile(file) {
  const allowedTypes = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
  if (!allowedTypes.includes(file.type)) {
    showError("暂不支持该文件类型，请选择 JPG、PNG、WebP 或 HEIC 图片。");
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showError("图片超过 10 MB，请压缩或重新拍摄后上传。");
    return;
  }

  hideError();
  resetResult();
  state.file = file;
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = URL.createObjectURL(file);
  elements.preview.src = state.previewUrl;
  elements.dropZone.hidden = true;
  elements.imageStage.hidden = false;
  elements.proofTitle.textContent = "标签原图";
  elements.proofState.textContent = "准备识别";
  analyzeFile(file);
}

async function analyzeFile(file) {
  state.analysis = null;
  elements.workbench.classList.remove("has-analysis");
  elements.reviewRail.hidden = true;
  elements.processing.hidden = false;
  elements.form.hidden = true;
  elements.annotationLayer.replaceChildren();
  elements.reviewCount.textContent = "处理中";
  elements.proofState.textContent = "正在识别";
  announce("正在识别标签图片");

  const formData = new FormData();
  formData.append("image", file);

  try {
    const response = await fetch("/api/v1/ocr/analyze", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message || "图片识别失败。");

    state.analysis = payload;
    renderFields(payload.fields);
    renderAnnotations(payload.fields);
    elements.workbench.classList.add("has-analysis");
    elements.heroLayout.classList.add("has-analysis");
    elements.reviewRail.hidden = false;
    elements.form.hidden = false;
    elements.reviewCount.textContent = `${payload.fields.length} 项`;
    const processing = payload.processing || {};
    const speedNote = processing.cache_hit
      ? "已读取缓存"
      : `${((processing.total_ms || 0) / 1000).toFixed(1)} 秒`;
    elements.proofState.textContent = `待人工确认 · ${speedNote}`;
    announce(`识别完成，用时${speedNote}，共 ${payload.fields.length} 个字段，其中低置信度字段需要确认`);
  } catch (error) {
    elements.workbench.classList.remove("has-analysis");
    elements.heroLayout.classList.remove("has-analysis");
    elements.reviewRail.hidden = true;
    elements.reviewCount.textContent = "0 项";
    elements.proofState.textContent = "识别未完成";
    showError(error.message);
  } finally {
    elements.processing.hidden = true;
  }
}

function renderFields(fields) {
  elements.fieldList.replaceChildren();
  fields.forEach((field) => {
    const wrapper = document.createElement("div");
    wrapper.className = "ocr-field";
    wrapper.dataset.fieldName = field.name;

    const meta = document.createElement("div");
    meta.className = "field-meta";

    const label = document.createElement("label");
    const inputId = `field-${field.name}`;
    label.htmlFor = inputId;
    label.textContent = field.label;

    const confidence = document.createElement("span");
    confidence.className = "confidence";
    if (field.requires_confirmation) confidence.classList.add("requires-confirmation");
    confidence.textContent = field.requires_confirmation
      ? `OCR ${Math.round(field.confidence * 100)}% · 需确认`
      : `OCR ${Math.round(field.confidence * 100)}%`;

    const textarea = document.createElement("textarea");
    textarea.id = inputId;
    textarea.dataset.fieldName = field.name;
    textarea.value = field.raw_text;
    textarea.required = field.name === "ingredients";
    textarea.setAttribute("aria-describedby", `${inputId}-help`);
    textarea.addEventListener("focus", () => activateField(field.name));

    const help = document.createElement("p");
    help.className = "field-help";
    help.id = `${inputId}-help`;
    help.textContent = field.requires_confirmation
      ? "请重点对照原图确认。"
      : "请对照原图确认。";

    meta.append(label, confidence);
    wrapper.append(meta, textarea, help);
    elements.fieldList.append(wrapper);
  });
}

function renderAnnotations(fields) {
  elements.annotationLayer.replaceChildren();
  fields.forEach((field) => {
    if (!field.bounding_box) return;
    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = "annotation";
    marker.dataset.fieldName = field.name;
    marker.setAttribute("aria-label", `查看${field.label}识别字段`);
    marker.style.left = `${field.bounding_box.x * 100}%`;
    marker.style.top = `${field.bounding_box.y * 100}%`;
    marker.style.width = `${field.bounding_box.width * 100}%`;
    marker.style.height = `${field.bounding_box.height * 100}%`;
    marker.addEventListener("click", () => {
      activateField(field.name);
      document.querySelector(`#field-${field.name}`)?.focus();
    });
    elements.annotationLayer.append(marker);
  });
}

function activateField(name) {
  document.querySelectorAll(".annotation").forEach((marker) => {
    marker.classList.toggle("is-active", marker.dataset.fieldName === name);
  });
}

function resetResult() {
  if (elements.resultState) elements.resultState.hidden = true;
  if (elements.form) elements.form.hidden = true;
  if (elements.reviewRail) elements.reviewRail.hidden = true;
  elements.workbench.classList.remove("has-analysis");
  elements.heroLayout.classList.remove("has-analysis");
  elements.fieldList.replaceChildren();
  elements.reviewCount.textContent = "0 项";
}

function showError(message) {
  elements.errorMessage.textContent = message;
  elements.errorState.hidden = false;
  announce(message);
}

function hideError() {
  elements.errorState.hidden = true;
  elements.errorMessage.textContent = "";
}

function announce(message) {
  elements.liveRegion.textContent = "";
  window.requestAnimationFrame(() => {
    elements.liveRegion.textContent = message;
  });
}

async function loadHealthStatus() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) return;
    const health = await response.json();
    elements.ocrStatus.textContent = health.synthetic_ocr ? "演示 OCR" : "本地 PP-OCRv6";
  } catch {
    // The upload action remains available; request-level errors provide recovery.
  }
}
