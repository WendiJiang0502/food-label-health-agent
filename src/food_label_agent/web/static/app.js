const elements = {
  fileInput: document.querySelector("#label-image"),
  dropZone: document.querySelector("#drop-zone"),
  imageStage: document.querySelector("#image-stage"),
  preview: document.querySelector("#label-preview"),
  annotationLayer: document.querySelector("#annotation-layer"),
  replaceImage: document.querySelector("#replace-image"),
  processing: document.querySelector("#processing"),
  proofState: document.querySelector("#proof-state"),
  emptyReview: document.querySelector("#empty-review"),
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
};

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
    elements.resultMessage.textContent = `${payload.message} 下一路由：${payload.next_route}`;
    elements.resultState.hidden = false;
    elements.resultState.focus();
    elements.proofState.textContent = "用户已确认";
    setWorkflowStep("confirm", true);
    announce("标签事实已确认，可以进入配料规范化");
  } catch (error) {
    showError(error.message);
  } finally {
    elements.confirmButton.disabled = false;
    elements.confirmButton.firstChild.textContent = "确认标签并继续 ";
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
  elements.proofState.textContent = "准备识别";
  analyzeFile(file);
}

async function analyzeFile(file) {
  state.analysis = null;
  elements.processing.hidden = false;
  elements.form.hidden = true;
  elements.emptyReview.hidden = true;
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
    elements.form.hidden = false;
    elements.reviewCount.textContent = `${payload.fields.length} 项`;
    elements.proofState.textContent = "待人工确认";
    setWorkflowStep("confirm");
    announce(`识别完成，共 ${payload.fields.length} 个字段，其中低置信度字段需要确认`);
  } catch (error) {
    elements.emptyReview.hidden = false;
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
      ? "置信度不足：请对照左侧原图逐字确认。"
      : "仍请对照原图确认，系统不会把高置信度等同于绝对正确。";

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

function setWorkflowStep(step, complete = false) {
  document.querySelectorAll(".workflow li").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.step === step && !complete);
    if (item.dataset.step === step && complete) item.classList.add("is-complete");
  });
}

function resetResult() {
  elements.resultState.hidden = true;
  elements.form.hidden = true;
  elements.emptyReview.hidden = false;
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
