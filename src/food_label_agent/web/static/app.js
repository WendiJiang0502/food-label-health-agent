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
  reviewTitle: document.querySelector("#review-title"),
  form: document.querySelector("#confirmation-form"),
  fieldList: document.querySelector("#field-list"),
  reviewCount: document.querySelector("#review-count"),
  confirmButton: document.querySelector("#confirm-button"),
  resultState: document.querySelector("#result-state"),
  resultMessage: document.querySelector("#result-message"),
  railError: document.querySelector("#rail-error"),
  railErrorMessage: document.querySelector("#rail-error-message"),
  constraintStep: document.querySelector("#constraint-step"),
  constraintForm: document.querySelector("#constraint-form"),
  constraintError: document.querySelector("#constraint-error"),
  nutritionLimit: document.querySelector("#nutrition-limit"),
  nutritionKey: document.querySelector("#nutrition-key"),
  nutritionThreshold: document.querySelector("#nutrition-threshold"),
  nutritionUnit: document.querySelector("#nutrition-unit"),
  nutritionBasisNote: document.querySelector("#nutrition-basis-note"),
  evaluateButton: document.querySelector("#evaluate-button"),
  safetyResult: document.querySelector("#safety-result"),
  riskSymbol: document.querySelector("#risk-symbol"),
  riskKicker: document.querySelector("#risk-kicker"),
  safetyTitle: document.querySelector("#safety-title"),
  riskSummary: document.querySelector("#risk-summary"),
  matchedText: document.querySelector("#matched-text"),
  matchedConstraint: document.querySelector("#matched-constraint"),
  matchedLocation: document.querySelector("#matched-location"),
  additionalFindings: document.querySelector("#additional-findings"),
  additiveResults: document.querySelector("#additive-results"),
  additiveResultsCount: document.querySelector("#additive-results-count"),
  additiveResultList: document.querySelector("#additive-result-list"),
  claimResults: document.querySelector("#claim-results"),
  claimResultsCount: document.querySelector("#claim-results-count"),
  claimResultList: document.querySelector("#claim-result-list"),
  evidenceDetails: document.querySelector("#evidence-details"),
  evidenceStatus: document.querySelector("#evidence-status"),
  evidenceIntro: document.querySelector("#evidence-intro"),
  citationList: document.querySelector("#citation-list"),
  evidenceEmpty: document.querySelector("#evidence-empty"),
  changeConstraints: document.querySelector("#change-constraints"),
  errorState: document.querySelector("#error-state"),
  errorMessage: document.querySelector("#error-message"),
  retryButton: document.querySelector("#retry-button"),
  liveRegion: document.querySelector("#live-region"),
  ocrStatus: document.querySelector("#ocr-status"),
  ocrProofNote: document.querySelector("#ocr-proof-note"),
  privacyStatuses: document.querySelectorAll("[data-privacy-status]"),
};

elements.heroUploadButton.addEventListener("click", () => elements.fileInput.click());
loadHealthStatus();

const state = {
  file: null,
  previewUrl: null,
  analysis: null,
  confirmedFields: null,
  normalizedLabel: null,
};

const constraintLabels = {
  milk: "乳过敏",
  egg: "蛋过敏",
  peanut: "花生过敏",
  soy: "大豆过敏",
  gluten: "麸质相关过敏",
  tree_nut: "坚果过敏",
  energy: "能量上限",
  protein: "蛋白质上限",
  fat: "脂肪上限",
  saturated_fat: "饱和脂肪酸上限",
  trans_fat: "反式脂肪酸上限",
  carbohydrate: "碳水化合物上限",
  sugars: "糖上限",
  dietary_fiber: "膳食纤维上限",
  sodium: "钠上限",
  calcium: "钙上限",
};

const nutrientNames = {
  energy: "能量", protein: "蛋白质", fat: "脂肪", saturated_fat: "饱和脂肪酸",
  trans_fat: "反式脂肪酸", carbohydrate: "碳水化合物", sugars: "糖",
  dietary_fiber: "膳食纤维", sodium: "钠", calcium: "钙",
};

elements.nutritionKey.addEventListener("change", updateNutritionLimitControl);

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
elements.preview.addEventListener("load", () => {
  if (state.analysis) renderAnnotations(state.analysis.fields);
});

const annotationResizeObserver = new ResizeObserver(() => {
  if (state.analysis) renderAnnotations(state.analysis.fields);
});
annotationResizeObserver.observe(elements.imageStage);

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
  hideRailError();
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
        original_fields: Object.fromEntries(
          state.analysis.fields.map((field) => [field.name, field.raw_text]),
        ),
        nutrition_rows: state.analysis.fields.find((field) => field.name === "nutrition_table")
          ?.nutrition_table?.rows || null,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message || "标签确认失败。");

    if (payload.normalization_issues?.length) {
      const issue = payload.normalization_issues[0];
      throw new Error(`配料结构还需确认：${issue.message}`);
    }

    state.confirmedFields = fields;
    state.normalizedLabel = payload.normalized_label;
    setupNutritionLimit(payload.normalized_label?.nutrition);
    elements.form.hidden = true;
    elements.resultState.hidden = true;
    elements.constraintStep.hidden = false;
    elements.safetyResult.hidden = true;
    elements.reviewTitle.textContent = "设置个人约束";
    elements.reviewCount.textContent = "个人约束";
    elements.proofState.textContent = "标签已确认";
    elements.constraintStep.querySelector("input")?.focus();
    announce("识别文字已确认，请选择需要回避的过敏原");
  } catch (error) {
    showRailError(error.message);
  } finally {
    elements.confirmButton.disabled = false;
    elements.confirmButton.firstChild.textContent = "确认识别文字 ";
  }
});

elements.constraintForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const selected = [...elements.constraintForm.querySelectorAll('input[name="constraint"]:checked')]
    .map((input) => input.value);
  const nutritionOption = elements.nutritionKey.selectedOptions[0];
  const nutritionSelected = Boolean(elements.nutritionKey.value);
  const nutritionThreshold = elements.nutritionThreshold.valueAsNumber;
  if (!selected.length && !nutritionSelected) {
    elements.constraintError.hidden = false;
    elements.constraintForm.querySelector("input")?.focus();
    announce("请至少选择一项需要回避的过敏原");
    return;
  }
  if (nutritionSelected && (!Number.isFinite(nutritionThreshold) || nutritionThreshold < 0)) {
    elements.constraintError.textContent = "请填写有效的非负营养上限。";
    elements.constraintError.hidden = false;
    elements.nutritionThreshold.focus();
    return;
  }
  elements.constraintError.hidden = true;
  hideRailError();
  elements.evaluateButton.disabled = true;
  elements.evaluateButton.firstChild.textContent = "正在核对… ";
  announce("正在检查过敏原并核对官方依据");

  try {
    const response = await fetch("/api/v1/labels/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_id: state.analysis.request_id,
        jurisdiction: "CN",
        applicable_date: new Date().toISOString().slice(0, 10),
        confirmed_fields: state.confirmedFields,
        constraints: [
          ...selected.map((canonicalValue) => ({
          kind: "allergy",
          canonical_value: canonicalValue,
          severity: "severe",
          })),
          ...(nutritionSelected ? [{
            kind: "nutrition_limit",
            canonical_value: elements.nutritionKey.value,
            operator: "max",
            threshold: nutritionThreshold,
            unit: nutritionOption.dataset.unit,
            basis: nutritionOption.dataset.basis,
          }] : []),
        ],
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message || "过敏原检查失败。");
    renderSafetyResult(payload);
  } catch (error) {
    showRailError(error.message);
  } finally {
    elements.evaluateButton.disabled = false;
    elements.evaluateButton.firstChild.textContent = "检查并查看依据 ";
  }
});

elements.constraintForm.addEventListener("change", () => {
  elements.constraintError.textContent = "请至少选择一项。";
  elements.constraintError.hidden = true;
  hideRailError();
});

function setupNutritionLimit(nutrition) {
  elements.nutritionKey.replaceChildren(new Option("不设置", ""));
  const facts = nutrition?.nutrients || [];
  const comparable = facts.filter((fact) => fact.basis !== "unknown");
  elements.nutritionLimit.hidden = comparable.length === 0;
  comparable.forEach((fact) => {
    const option = new Option(
      `${nutrientNames[fact.canonical_name] || fact.raw_name} · 标签 ${fact.value}${fact.unit}`,
      fact.canonical_name,
    );
    option.dataset.unit = fact.unit;
    option.dataset.basis = fact.basis;
    elements.nutritionKey.add(option);
  });
  updateNutritionLimitControl();
}

function updateNutritionLimitControl() {
  const option = elements.nutritionKey.selectedOptions[0];
  const enabled = Boolean(elements.nutritionKey.value);
  elements.nutritionThreshold.disabled = !enabled;
  elements.nutritionThreshold.required = enabled;
  elements.nutritionUnit.textContent = enabled ? option.dataset.unit : "—";
  const basisLabels = { per_100g: "每 100 克", per_100ml: "每 100 毫升", per_serving: "每份" };
  elements.nutritionBasisNote.textContent = enabled
    ? `将按标签的${basisLabels[option.dataset.basis] || "已确认"}口径比较，不自动换算。`
    : "按已确认包装口径比较，不自动换算。";
}

elements.changeConstraints.addEventListener("click", () => {
  elements.safetyResult.hidden = true;
  elements.claimResults.hidden = true;
  elements.claimResultList.replaceChildren();
  elements.additiveResults.hidden = true;
  elements.additiveResultList.replaceChildren();
  elements.constraintStep.hidden = false;
  elements.reviewTitle.textContent = "设置个人约束";
  elements.reviewCount.textContent = "个人约束";
  elements.constraintStep.querySelector("input")?.focus();
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
  hideRailError();
  elements.reviewTitle.textContent = "确认识别文字";
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
  const imageRect = containedImageRect();
  if (!imageRect) return;

  fields.forEach((field) => {
    if (!field.bounding_box) return;
    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = "annotation";
    marker.dataset.fieldName = field.name;
    marker.setAttribute("aria-label", `查看${field.label}识别字段`);
    marker.style.left = `${imageRect.offsetX + field.bounding_box.x * imageRect.width}px`;
    marker.style.top = `${imageRect.offsetY + field.bounding_box.y * imageRect.height}px`;
    marker.style.width = `${field.bounding_box.width * imageRect.width}px`;
    marker.style.height = `${field.bounding_box.height * imageRect.height}px`;
    marker.addEventListener("click", () => {
      activateField(field.name);
      document.querySelector(`#field-${field.name}`)?.focus();
    });
    elements.annotationLayer.append(marker);
  });
}

function containedImageRect() {
  const naturalWidth = elements.preview.naturalWidth;
  const naturalHeight = elements.preview.naturalHeight;
  const stageWidth = elements.imageStage.clientWidth;
  const stageHeight = elements.imageStage.clientHeight;
  if (!naturalWidth || !naturalHeight || !stageWidth || !stageHeight) return null;

  const scale = Math.min(stageWidth / naturalWidth, stageHeight / naturalHeight);
  const width = naturalWidth * scale;
  const height = naturalHeight * scale;
  return {
    width,
    height,
    offsetX: (stageWidth - width) / 2,
    offsetY: (stageHeight - height) / 2,
  };
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
  elements.constraintStep.hidden = true;
  elements.safetyResult.hidden = true;
  elements.constraintForm.reset();
  hideRailError();
  elements.reviewTitle.textContent = "确认识别文字";
  state.confirmedFields = null;
  state.normalizedLabel = null;
  elements.workbench.classList.remove("has-analysis");
  elements.heroLayout.classList.remove("has-analysis");
  elements.fieldList.replaceChildren();
  elements.reviewCount.textContent = "0 项";
}

function renderSafetyResult(payload) {
  const riskOrder = { avoid: 3, caution: 2, unknown: 1, compatible: 0 };
  const primary = [...payload.findings].sort(
    (left, right) => riskOrder[right.risk_level] - riskOrder[left.risk_level],
  )[0];
  const titles = {
    avoid: "不建议食用",
    caution: "需要谨慎确认",
    unknown: "当前信息不足",
    compatible: "未发现约束冲突",
  };
  const symbols = { avoid: "!", caution: "?", unknown: "…", compatible: "✓" };

  elements.constraintStep.hidden = true;
  elements.safetyResult.hidden = false;
  hideRailError();
  elements.reviewTitle.textContent = "个人约束检查结果";
  elements.safetyResult.dataset.risk = payload.overall_risk_level;
  elements.riskSymbol.textContent = symbols[payload.overall_risk_level];
  elements.riskKicker.textContent = `规则评估 · ${payload.findings.length} 项约束`;
  elements.safetyTitle.textContent = titles[payload.overall_risk_level];
  elements.riskSummary.textContent = primary.explanation;
  elements.matchedText.textContent = primary.matched_text || "—";
  elements.matchedConstraint.textContent = constraintLabels[primary.constraint] || primary.constraint;
  elements.matchedLocation.textContent = primary.matched_location;
  elements.reviewCount.textContent = payload.overall_risk_level === "avoid" ? "明确命中" : "评估完成";
  elements.proofState.textContent = "安全规则已评估";

  const secondary = payload.findings.filter((finding) => finding !== primary);
  elements.additionalFindings.replaceChildren();
  elements.additionalFindings.hidden = secondary.length === 0;
  secondary.forEach((finding) => {
    const row = document.createElement("div");
    row.className = "finding-detail";
    const heading = document.createElement("p");
    const label = document.createElement("strong");
    label.textContent = constraintLabels[finding.constraint] || finding.constraint;
    const status = document.createElement("span");
    status.textContent = titles[finding.risk_level];
    heading.append(label, status);
    const evidence = document.createElement("p");
    evidence.className = "finding-evidence";
    evidence.textContent = `${finding.matched_text || "未确认"} · ${finding.matched_location}`;
    const reason = document.createElement("p");
    reason.className = "finding-reason";
    reason.textContent = finding.explanation;
    row.append(heading, evidence, reason);
    elements.additionalFindings.append(row);
  });
  renderClaimResults(payload.evidence);
  renderAdditiveResults(payload.evidence);
  renderRegulatoryEvidence(payload.evidence, primary);
  elements.safetyResult.focus();
  announce(`${titles[payload.overall_risk_level]}，${primary.matched_text || primary.explanation}`);
}

function renderAdditiveResults(evidence) {
  const explanations = (evidence?.interpretations || []).filter(
    (item) => item.explanation_type === "additive",
  );
  elements.additiveResultList.replaceChildren();
  elements.additiveResults.hidden = explanations.length === 0;
  elements.additiveResultsCount.textContent = `${explanations.length} 项`;
  explanations.forEach((item) => {
    const article = document.createElement("article");
    article.className = "additive-result";
    const header = document.createElement("header");
    const name = document.createElement("strong");
    name.textContent = item.ingredient?.canonical_name || item.ingredient?.raw_name || "名称待确认";
    const category = document.createElement("span");
    category.textContent = (item.ingredient?.category || "功能待确认").replace("食品添加剂·", "");
    header.append(name, category);
    const explanation = document.createElement("p");
    explanation.textContent = item.explanation || "当前词典无法确认这个名称，不猜测其功能或影响。";
    if (item.status === "unknown") explanation.className = "additive-unknown";
    const boundary = document.createElement("p");
    boundary.className = "additive-boundary";
    boundary.textContent = item.limitations?.[1] || item.limitations?.[0] || "不能仅凭名称判断实际用量或合规性。";
    article.append(header, explanation, boundary);
    elements.additiveResultList.append(article);
  });
}

function renderClaimResults(evidence) {
  const claims = evidence?.claim_interpretations || [];
  const findings = evidence?.consistency_findings || [];
  elements.claimResultList.replaceChildren();
  elements.claimResults.hidden = claims.length === 0;
  elements.claimResultsCount.textContent = `${claims.length} 项`;
  if (!claims.length) return;

  const statusLabels = {
    consistent: "数值符合",
    inconsistent: "与标签冲突",
    not_contradicted: "未发现直接冲突",
    unknown: "信息不足",
  };
  claims.forEach((claim, index) => {
    const claimIds = new Set(claim.label_evidence_ids || []);
    const finding =
      findings.find((item) =>
        (item.label_evidence_ids || []).some((id) => claimIds.has(id)),
      ) || findings[index];
    const status = finding?.status || "unknown";

    const article = document.createElement("article");
    article.className = "claim-result";
    article.dataset.status = status;

    const heading = document.createElement("div");
    heading.className = "claim-result-heading";
    const names = document.createElement("div");
    const raw = document.createElement("strong");
    raw.textContent = claim.raw_text || "未识别声称";
    const canonical = document.createElement("span");
    canonical.textContent = claim.canonical_name
      ? `按“${claim.canonical_name}”理解`
      : "规范含义待确认";
    names.append(raw, canonical);
    const badge = document.createElement("span");
    badge.className = "claim-status";
    badge.textContent = statusLabels[status] || "信息不足";
    heading.append(names, badge);

    const meaning = document.createElement("p");
    meaning.className = "claim-meaning";
    meaning.textContent = claim.meaning || "当前证据不足，不能确定这项声称的规范含义。";
    const check = document.createElement("p");
    check.className = "claim-check";
    check.textContent = finding?.explanation || "当前没有足够的已确认标签信息完成一致性检查。";

    article.append(heading, meaning, check);
    if (finding?.matched_text) {
      const matched = document.createElement("p");
      matched.className = "claim-match";
      matched.textContent = `冲突成分：${finding.matched_text}`;
      article.append(matched);
    }
    const limitation = claim.limitations?.[0];
    if (limitation) {
      const boundary = document.createElement("p");
      boundary.className = "claim-boundary";
      boundary.textContent = limitation;
      article.append(boundary);
    }
    elements.claimResultList.append(article);
  });
}

function renderRegulatoryEvidence(evidence, primaryFinding) {
  elements.evidenceDetails.open = false;
  elements.citationList.replaceChildren();
  elements.evidenceEmpty.hidden = true;
  elements.evidenceEmpty.textContent = "";
  elements.evidenceIntro.textContent = "";

  if (!evidence || evidence.status === "blocked") {
    elements.evidenceStatus.textContent = "依据暂不可用";
    elements.evidenceEmpty.textContent =
      "过敏原风险仍由已确认标签和确定性规则得出；官方条款暂时无法核对，请稍后重试。";
    elements.evidenceEmpty.hidden = false;
    return;
  }

  const claimInterpretations = evidence.claim_interpretations || [];
  const additiveInterpretations = (evidence.interpretations || []).filter(
    (item) => item.explanation_type === "additive",
  );
  if (evidence.status === "not_required" && !claimInterpretations.length) {
    elements.evidenceStatus.textContent = "未发现冲突";
    elements.evidenceIntro.textContent =
      "当前已确认标签中未发现所选过敏原，但这不是对配方、交叉接触或绝对安全的证明。";
    return;
  }

  const primaryEvidenceIds = new Set(primaryFinding.evidence_ids || []);
  const interpretation = (evidence.interpretations || []).find((item) =>
    (item.label_evidence_ids || []).some((id) => primaryEvidenceIds.has(id)),
  );
  const claimCitations = claimInterpretations.flatMap((item) => item.citations || []);
  const additiveCitations = additiveInterpretations.flatMap((item) => item.citations || []);
  const citations = uniqueCitations([
    ...(interpretation?.citations || []),
    ...additiveCitations,
    ...claimCitations,
  ]);
  const introParts = [
    interpretation?.status === "explained" ? interpretation.explanation : null,
    additiveInterpretations.length
      ? `已识别并解释 ${additiveInterpretations.length} 项添加剂；是否符合使用标准仍需食品类别和用量证据。`
      : null,
    ...claimInterpretations
      .filter((item) => item.status === "interpreted" && item.meaning)
      .map((item) => `“${item.raw_text}”：${item.meaning}`),
  ].filter(Boolean);
  if (!citations.length) {
    elements.evidenceStatus.textContent = claimInterpretations.length ? "声称已核对" : "证据不足";
    elements.evidenceEmpty.textContent =
      claimInterpretations.length
        ? "已检查包装声称与确认标签是否存在直接冲突；当前没有足以支持法规合规结论的适用官方条款。"
        : "当前没有找到足以支持进一步解释的适用官方条款，因此不补充肯定的法规结论。";
    elements.evidenceEmpty.hidden = false;
    return;
  }

  elements.evidenceStatus.textContent = `${citations.length} 条官方依据`;
  elements.evidenceIntro.textContent = introParts.join(" ");
  citations.forEach((citation) => {
    const item = document.createElement("li");
    item.className = "citation-item";

    const heading = document.createElement("p");
    heading.className = "citation-heading";
    const standard = document.createElement("strong");
    standard.textContent = citation.standard_number;
    const location = document.createElement("span");
    const sectionLabel = compactSectionLabel(citation.section);
    location.textContent = citation.page_start
      ? `${sectionLabel} · 第 ${citation.page_start} 页`
      : sectionLabel;
    heading.append(standard, location);

    const excerpt = document.createElement("p");
    excerpt.className = "citation-excerpt";
    excerpt.textContent = citation.evidence_excerpt;

    const source = document.createElement("a");
    source.className = "citation-source";
    source.href = citation.source_url;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    source.textContent = "打开国家卫健委官方来源 ↗";

    item.append(heading, excerpt, source);
    elements.citationList.append(item);
  });
}

function uniqueCitations(citations) {
  const seen = new Set();
  return citations.filter((citation) => {
    const key = citation.evidence_id || `${citation.standard_number}:${citation.section}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function compactSectionLabel(section) {
  const normalized = String(section || "条款未标明").trim();
  const match = normalized.match(/^(\d+(?:\.\d+){1,4})(?:\s+(.+))?$/);
  if (!match) return normalized.length > 36 ? `${normalized.slice(0, 36)}…` : normalized;
  const [, clauseNumber, title = ""] = match;
  return title && title.length <= 16 ? `${clauseNumber} ${title}` : clauseNumber;
}

function showRailError(message) {
  elements.railErrorMessage.textContent = message;
  elements.railError.hidden = false;
  elements.railError.focus();
  announce(message);
}

function hideRailError() {
  elements.railError.hidden = true;
  elements.railErrorMessage.textContent = "";
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
    if (health.synthetic_ocr) {
      elements.ocrStatus.textContent = "演示 OCR";
      elements.ocrProofNote.innerHTML = "<strong>演示版</strong> · OCR 结果仅用于测试交互";
      setPrivacyStatus("图片默认不保存");
    } else if (health.remote_processing) {
      elements.ocrStatus.textContent = "腾讯云 OCR";
      elements.ocrProofNote.innerHTML = "<strong>云端识别</strong> · 结果仍需人工核对";
      setPrivacyStatus("图片发送至腾讯云处理，本平台不保存原图");
    } else {
      elements.ocrStatus.textContent = "本地 PP-OCRv6";
      elements.ocrProofNote.innerHTML = "<strong>本地识别</strong> · 结果仍需人工核对";
      setPrivacyStatus("图片在本机处理，默认不保存");
    }
  } catch {
    // The upload action remains available; request-level errors provide recovery.
  }
}

function setPrivacyStatus(message) {
  elements.privacyStatuses.forEach((element) => {
    element.lastChild.textContent = message;
  });
}
