const elements = {
  profileOnboarding: document.querySelector("#profile-onboarding"),
  profileForm: document.querySelector("#profile-form"),
  profileName: document.querySelector("#profile-name"),
  noKnownAllergens: document.querySelector("#no-known-allergens"),
  customAllergens: document.querySelector("#custom-allergens"),
  customHealthConcerns: document.querySelector("#custom-health-concerns"),
  rememberProfile: document.querySelector("#remember-profile"),
  profileError: document.querySelector("#profile-error"),
  advicePreview: document.querySelector("#advice-preview"),
  adviceProfileName: document.querySelector("#advice-profile-name"),
  adviceAllergens: document.querySelector("#advice-allergens"),
  adviceFocusList: document.querySelector("#advice-focus-list"),
  editProfileFromAdvice: document.querySelector("#edit-profile-from-advice"),
  continueToScan: document.querySelector("#continue-to-scan"),
  editProfileFromScan: document.querySelector("#edit-profile-from-scan"),
  scanProfileTitle: document.querySelector("#scan-profile-title"),
  scanAllergenSummary: document.querySelector("#scan-allergen-summary"),
  scanHealthSummary: document.querySelector("#scan-health-summary"),
  constraintAllergenSummaryText: document.querySelector("#constraint-allergen-summary-text"),
  healthFocusSummaryText: document.querySelector("#health-focus-summary-text"),
  modifyProfileInReview: document.querySelector("#modify-profile-in-review"),
  fileInput: document.querySelector("#label-image"),
  dropZone: document.querySelector("#drop-zone"),
  imageStage: document.querySelector("#image-stage"),
  proofSheet: document.querySelector("#proof-sheet"),
  preview: document.querySelector("#label-preview"),
  annotationLayer: document.querySelector("#annotation-layer"),
  replaceImage: document.querySelector("#replace-image"),
  viewFullImage: document.querySelector("#view-full-image"),
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
  editLabel: document.querySelector("#edit-label"),
  constraintForm: document.querySelector("#constraint-form"),
  constraintError: document.querySelector("#constraint-error"),
  nutritionLimit: document.querySelector("#nutrition-limit"),
  nutritionKey: document.querySelector("#nutrition-key"),
  nutritionThreshold: document.querySelector("#nutrition-threshold"),
  nutritionUnit: document.querySelector("#nutrition-unit"),
  nutritionBasisNote: document.querySelector("#nutrition-basis-note"),
  rememberConstraints: document.querySelector("#remember-constraints"),
  memorySaved: document.querySelector("#memory-saved"),
  memoryList: document.querySelector("#memory-list"),
  memoryStatus: document.querySelector("#memory-status"),
  revokeMemory: document.querySelector("#revoke-memory"),
  evaluateButton: document.querySelector("#evaluate-button"),
  safetyResult: document.querySelector("#safety-result"),
  riskSymbol: document.querySelector("#risk-symbol"),
  riskKicker: document.querySelector("#risk-kicker"),
  safetyTitle: document.querySelector("#safety-title"),
  riskSummary: document.querySelector("#risk-summary"),
  portionValue: document.querySelector("#portion-value"),
  portionNote: document.querySelector("#portion-note"),
  nutritionBasisLabel: document.querySelector("#nutrition-basis-label"),
  nutritionStatList: document.querySelector("#nutrition-stat-list"),
  nutritionStatEmpty: document.querySelector("#nutrition-stat-empty"),
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
  evidencePanel: document.querySelector("#evidence-panel"),
  evidenceStatus: document.querySelector("#evidence-status"),
  evidenceIntro: document.querySelector("#evidence-intro"),
  citationList: document.querySelector("#citation-list"),
  evidenceEmpty: document.querySelector("#evidence-empty"),
  alternativeDiscovery: document.querySelector("#alternative-discovery"),
  alternativeCategory: document.querySelector("#alternative-category"),
  findAlternatives: document.querySelector("#find-alternatives"),
  alternativeCount: document.querySelector("#alternative-count"),
  alternativeSource: document.querySelector("#alternative-source"),
  alternativeStatus: document.querySelector("#alternative-status"),
  alternativeResults: document.querySelector("#alternative-results"),
  alternativeList: document.querySelector("#alternative-list"),
  alternativeComparison: document.querySelector("#alternative-comparison"),
  alternativeComparisonList: document.querySelector("#alternative-comparison-list"),
  alternativeExclusions: document.querySelector("#alternative-exclusions"),
  alternativeExclusionList: document.querySelector("#alternative-exclusion-list"),
  changeConstraints: document.querySelector("#change-constraints"),
  errorState: document.querySelector("#error-state"),
  errorMessage: document.querySelector("#error-message"),
  retryButton: document.querySelector("#retry-button"),
  liveRegion: document.querySelector("#live-region"),
  ocrStatus: document.querySelector("#ocr-status"),
  ocrProofNote: document.querySelector("#ocr-proof-note"),
  privacyStatuses: document.querySelectorAll("[data-privacy-status]"),
};

const MEMORY_CREDENTIALS_KEY = "food-label-agent.memory-credentials.v1";
const PROFILE_STORAGE_KEY = "food-label-agent.health-profile.v1";

elements.heroUploadButton.addEventListener("click", () => elements.fileInput.click());
loadHealthStatus();

const state = {
  file: null,
  previewUrl: null,
  analysis: null,
  confirmedFields: null,
  normalizedLabel: null,
  checkpointToken: null,
  memoryCredentials: readMemoryCredentials(),
  rememberedItems: [],
  currentConstraints: [],
  profile: readLocalProfile(),
  profileMemoryItem: null,
  profileEditReturn: null,
};

const constraintLabels = {
  milk: "乳过敏",
  egg: "蛋过敏",
  peanut: "花生过敏",
  soy: "大豆过敏",
  gluten: "麸质相关过敏",
  tree_nut: "坚果过敏",
  fish: "鱼类过敏",
  crustacean: "甲壳类过敏",
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

const allergenNames = {
  milk: "乳",
  egg: "蛋",
  peanut: "花生",
  soy: "大豆",
  gluten: "含麸质谷物",
  tree_nut: "坚果",
  fish: "鱼类",
  crustacean: "甲壳类",
};

const healthConcernNames = {
  blood_sugar: "血糖管理",
  blood_lipids: "血脂管理",
  blood_pressure: "血压管理",
  weight: "体重管理",
  uric_acid: "尿酸管理",
  gut: "肠胃敏感",
  sugar_control: "控制糖摄入",
  child: "儿童饮食",
};

const healthFocusAdvice = {
  blood_sugar: ["糖、碳水与膳食纤维", "结合每份大小阅读糖、碳水化合物和膳食纤维，不只看包装正面的“无糖”字样。"],
  blood_lipids: ["脂肪构成", "重点查看饱和脂肪、反式脂肪和每份总脂肪；标签缺项时会明确提示。"],
  blood_pressure: ["钠与实际食用份量", "优先查看每份钠含量，并核对包装标示的一份与你实际食用量是否一致。"],
  weight: ["能量与份量", "结合每份能量和包装份量理解实际摄入，不根据单一营养数字判断食品好坏。"],
  uric_acid: ["配料与食品类别", "仅凭常规标签通常不能完整判断相关风险；系统会整理可见事实，并标出无法确认的部分。"],
  gut: ["配料构成与不耐受线索", "优先呈现复杂配料和你主动填写的回避项，不把肠胃反应推断为食物过敏。"],
  sugar_control: ["糖与碳水化合物", "同时查看糖、碳水化合物和份量，避免只根据“低糖”或“无糖”宣传作决定。"],
  child: ["过敏原、钠、糖与份量", "先检查明确过敏原，再用儿童实际食用份量理解营养成分；不生成儿童医疗建议。"],
};

const nutrientNames = {
  energy: "能量", protein: "蛋白质", fat: "脂肪", saturated_fat: "饱和脂肪酸",
  trans_fat: "反式脂肪酸", carbohydrate: "碳水化合物", sugars: "糖",
  dietary_fiber: "膳食纤维", sodium: "钠", calcium: "钙",
};

const healthNutrientPriorities = {
  blood_sugar: ["sugars", "carbohydrate", "dietary_fiber"],
  blood_lipids: ["saturated_fat", "trans_fat", "fat"],
  blood_pressure: ["sodium"],
  weight: ["energy", "fat", "carbohydrate"],
  uric_acid: [],
  gut: ["dietary_fiber"],
  sugar_control: ["sugars", "carbohydrate"],
  child: ["sodium", "sugars", "energy"],
};

const nutrientUnitNames = { kJ: "千焦", g: "克", mg: "毫克", ml: "毫升" };

initializeProfileFlow();
loadRememberedConstraints();

elements.profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const profile = collectProfileFromForm();
  const hasAllergenAnswer = profile.noKnownAllergens
    || profile.allergens.length > 0
    || profile.customAllergens.length > 0;
  if (!hasAllergenAnswer) {
    showProfileError("请选择已知过敏原、填写其他项目，或选择“没有已知过敏原”。");
    elements.profileForm.querySelector('input[name="profile-allergen"]')?.focus();
    return;
  }
  if (!profile.healthConcerns.length && !profile.customHealthConcerns.length) {
    showProfileError("请至少选择或填写一项健康关注。我们会据此调整标签解释重点。");
    elements.profileForm.querySelector('input[name="health-concern"]')?.focus();
    return;
  }
  hideProfileError();
  state.profile = profile;
  if (state.profileEditReturn === "constraint") {
    try {
      if (elements.rememberProfile.checked) await persistProfile(profile);
      else {
        await deleteStoredProfile();
        localStorage.removeItem(PROFILE_STORAGE_KEY);
      }
    } catch (error) {
      showProfileError(`个人档案没有保存：${error.message}`);
      return;
    }
    state.profileEditReturn = null;
    renderScanProfile(profile);
    applyProfileConstraints();
    showProfileScreen("scan");
    elements.form.hidden = true;
    elements.constraintStep.hidden = false;
    elements.safetyResult.hidden = true;
    elements.reviewRail.hidden = false;
    elements.reviewTitle.textContent = "确认本次设置";
    elements.reviewCount.textContent = "个人档案";
    elements.evaluateButton.focus();
    announce("个人设置已更新，可以继续检查当前标签");
    return;
  }
  renderAdvicePreview(profile);
  showProfileScreen("advice");
  elements.advicePreview.focus?.();
  window.scrollTo({ top: 0, behavior: "smooth" });
  announce("个人分析重点已生成，请确认后开始识别");
});

elements.noKnownAllergens.addEventListener("change", () => {
  if (!elements.noKnownAllergens.checked) return;
  elements.profileForm.querySelectorAll('input[name="profile-allergen"]').forEach((input) => {
    input.checked = false;
  });
  elements.customAllergens.value = "";
  hideProfileError();
});

elements.profileForm.querySelectorAll('input[name="profile-allergen"]').forEach((input) => {
  input.addEventListener("change", () => {
    if (input.checked) elements.noKnownAllergens.checked = false;
    hideProfileError();
  });
});

elements.customAllergens.addEventListener("input", () => {
  if (elements.customAllergens.value.trim()) elements.noKnownAllergens.checked = false;
  hideProfileError();
});

elements.profileForm.querySelectorAll('input[name="health-concern"]').forEach((input) => {
  input.addEventListener("change", hideProfileError);
});
elements.customHealthConcerns.addEventListener("input", hideProfileError);

elements.editProfileFromAdvice.addEventListener("click", () => editProfile());
elements.editProfileFromScan.addEventListener("click", () => editProfile());
elements.modifyProfileInReview.addEventListener("click", () => editProfile("constraint"));
elements.continueToScan.addEventListener("click", async () => {
  if (!state.profile) return;
  elements.continueToScan.disabled = true;
  elements.continueToScan.firstChild.textContent = "正在准备… ";
  try {
    if (elements.rememberProfile.checked) {
      await persistProfile(state.profile);
    } else {
      await deleteStoredProfile();
      localStorage.removeItem(PROFILE_STORAGE_KEY);
    }
    renderScanProfile(state.profile);
    showProfileScreen("scan");
    window.scrollTo({ top: 0, behavior: "smooth" });
    elements.heroUploadButton.focus();
    announce("个人设置已确认，可以拍照或上传食品标签");
  } catch (error) {
    showProfileScreen("profile");
    showProfileError(`个人档案没有保存：${error.message}。你仍可取消保存后继续。`);
  } finally {
    elements.continueToScan.disabled = false;
    elements.continueToScan.firstChild.textContent = "按这些设置开始识别 ";
  }
});

function initializeProfileFlow() {
  if (state.profile) {
    populateProfileForm(state.profile);
    elements.rememberProfile.checked = true;
    renderScanProfile(state.profile);
    showProfileScreen("scan");
    return;
  }
  showProfileScreen("profile");
}

function showProfileScreen(screen) {
  elements.profileOnboarding.hidden = screen !== "profile";
  elements.advicePreview.hidden = screen !== "advice";
  elements.heroLayout.hidden = screen !== "scan";
}

function editProfile(returnTarget = null) {
  if (state.profile) populateProfileForm(state.profile);
  state.profileEditReturn = returnTarget;
  showProfileScreen("profile");
  window.scrollTo({ top: 0, behavior: "smooth" });
  elements.profileName.focus();
  announce("可以修改个人档案");
}

function collectProfileFromForm() {
  return {
    name: elements.profileName.value.trim() || "我的档案",
    allergens: [...elements.profileForm.querySelectorAll('input[name="profile-allergen"]:checked')]
      .map((input) => input.value),
    noKnownAllergens: elements.noKnownAllergens.checked,
    customAllergens: splitEntries(elements.customAllergens.value),
    healthConcerns: [...elements.profileForm.querySelectorAll('input[name="health-concern"]:checked')]
      .map((input) => input.value),
    customHealthConcerns: splitEntries(elements.customHealthConcerns.value),
  };
}

function populateProfileForm(profile) {
  elements.profileName.value = profile.name || "我的档案";
  elements.profileForm.querySelectorAll('input[name="profile-allergen"]').forEach((input) => {
    input.checked = profile.allergens?.includes(input.value) || false;
  });
  elements.noKnownAllergens.checked = Boolean(profile.noKnownAllergens);
  elements.customAllergens.value = (profile.customAllergens || []).join("、");
  elements.profileForm.querySelectorAll('input[name="health-concern"]').forEach((input) => {
    input.checked = profile.healthConcerns?.includes(input.value) || false;
  });
  elements.customHealthConcerns.value = (profile.customHealthConcerns || []).join("、");
}

function splitEntries(value) {
  return [...new Set(value.split(/[，,、；;\n]+/).map((item) => item.trim()).filter(Boolean))].slice(0, 12);
}

function renderAdvicePreview(profile) {
  elements.adviceProfileName.textContent = profile.name;
  elements.adviceAllergens.replaceChildren();
  const known = profile.allergens.map((value) => ({ label: allergenNames[value] || value, support: "supported" }));
  const custom = profile.customAllergens.map((value) => ({ label: `${value} · 需人工确认`, support: "review" }));
  const entries = profile.noKnownAllergens ? [{ label: "没有已知过敏原", support: "supported" }] : [...known, ...custom];
  entries.forEach((entry) => {
    const tag = document.createElement("span");
    tag.className = "profile-tag";
    tag.dataset.support = entry.support;
    tag.textContent = entry.label;
    elements.adviceAllergens.append(tag);
  });

  elements.adviceFocusList.replaceChildren();
  const focusItems = profile.healthConcerns.map((value) => healthFocusAdvice[value]).filter(Boolean);
  profile.customHealthConcerns.forEach((value) => {
    focusItems.push([value, "已记录为自定义关注；系统会整理相关标签事实，但不会据此生成诊断或医疗阈值。"]) ;
  });
  focusItems.slice(0, 5).forEach(([title, description], index) => {
    const item = document.createElement("article");
    item.className = "focus-item";
    const number = document.createElement("span");
    number.textContent = String(index + 1).padStart(2, "0");
    const content = document.createElement("div");
    const heading = document.createElement("strong");
    heading.textContent = title;
    const copy = document.createElement("p");
    copy.textContent = description;
    content.append(heading, copy);
    item.append(number, content);
    elements.adviceFocusList.append(item);
  });
}

function renderScanProfile(profile) {
  const allergenSummary = profile.noKnownAllergens
    ? "没有已知过敏原"
    : [
      ...profile.allergens.map((value) => allergenNames[value] || value),
      ...profile.customAllergens.map((value) => `${value}（需确认）`),
    ].join("、");
  const healthSummary = [
    ...profile.healthConcerns.map((value) => healthConcernNames[value] || value),
    ...profile.customHealthConcerns,
  ].join("、");
  elements.scanProfileTitle.textContent = profile.name;
  elements.scanAllergenSummary.textContent = allergenSummary || "未设置";
  elements.scanHealthSummary.textContent = healthSummary || "未设置";
  elements.constraintAllergenSummaryText.textContent = allergenSummary || "未设置";
  elements.healthFocusSummaryText.textContent = healthSummary || "未设置";
}

function readLocalProfile() {
  try {
    const value = JSON.parse(localStorage.getItem(PROFILE_STORAGE_KEY) || "null");
    if (isValidProfile(value)) return value;
  } catch {
    localStorage.removeItem(PROFILE_STORAGE_KEY);
  }
  return null;
}

function isValidProfile(value) {
  return Boolean(
    value
    && typeof value.name === "string"
    && Array.isArray(value.allergens)
    && Array.isArray(value.customAllergens)
    && Array.isArray(value.healthConcerns)
    && Array.isArray(value.customHealthConcerns)
  );
}

function showProfileError(message) {
  elements.profileError.textContent = message;
  elements.profileError.hidden = false;
}

function hideProfileError() {
  elements.profileError.hidden = true;
  elements.profileError.textContent = "";
}

async function persistProfile(profile) {
  await ensureMemoryConsent();
  const { profileId } = state.memoryCredentials;
  const payload = {
    kind: "response_preference",
    value: { preference: "health_profile", profile },
  };
  const endpoint = state.profileMemoryItem
    ? `/api/v1/memory/items/${state.profileMemoryItem.memory_id}?profile_id=${encodeURIComponent(profileId)}`
    : `/api/v1/memory/items?profile_id=${encodeURIComponent(profileId)}`;
  const response = await fetch(
    endpoint,
    memoryRequestOptions(state.profileMemoryItem ? "PUT" : "POST", payload),
  );
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "无法保存个人档案");
  state.profileMemoryItem = result.item;
  localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profile));
}

async function deleteStoredProfile() {
  if (!state.profileMemoryItem || !state.memoryCredentials) return;
  const { profileId } = state.memoryCredentials;
  const response = await fetch(
    `/api/v1/memory/items/${state.profileMemoryItem.memory_id}?profile_id=${encodeURIComponent(profileId)}`,
    memoryRequestOptions("DELETE"),
  );
  if (!response.ok) throw new Error("无法清除已保存的个人档案");
  state.profileMemoryItem = null;
}

elements.nutritionKey.addEventListener("change", updateNutritionLimitControl);
elements.editLabel.addEventListener("click", returnToLabelEditing);

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
  syncPreviewAspectRatio();
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
        resume_token: state.checkpointToken,
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
    elements.form.hidden = true;
    elements.resultState.hidden = true;
    elements.constraintStep.hidden = false;
    elements.safetyResult.hidden = true;
    elements.reviewTitle.textContent = "确认本次设置";
    elements.reviewCount.textContent = "个人档案";
    elements.proofState.textContent = "标签已确认";
    applyRememberedConstraints();
    applyProfileConstraints();
    elements.evaluateButton.focus();
    announce("识别文字已确认，请确认本次使用的个人设置");
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
  const nutritionSelected = Boolean(elements.nutritionKey.value);
  const nutritionThreshold = elements.nutritionThreshold.valueAsNumber;
  const hasCustomAvoidance = Boolean(state.profile?.customAllergens?.length);
  if (!selected.length && !nutritionSelected && !hasCustomAvoidance) {
    renderHealthFocusOnlyResult();
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
  const constraints = currentConstraintValues();
  state.currentConstraints = constraints;

  try {
    const response = await fetch("/api/v1/labels/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_id: state.analysis.request_id,
        jurisdiction: "CN",
        applicable_date: new Date().toISOString().slice(0, 10),
        confirmed_fields: state.confirmedFields,
        nutrition_rows: state.analysis.fields.find((field) => field.name === "nutrition_table")
          ?.nutrition_table?.rows || null,
        resume_token: state.checkpointToken,
        constraints,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message || "过敏原检查失败。");
    if (payload.checkpoint?.resume_token) {
      state.checkpointToken = payload.checkpoint.resume_token;
    }
    renderSafetyResult(payload);
    if (elements.rememberConstraints.checked) {
      await syncRememberedConstraints();
    }
  } catch (error) {
    showRailError(error.message);
  } finally {
    elements.evaluateButton.disabled = false;
    elements.evaluateButton.firstChild.textContent = "使用这些设置检查 ";
  }
});

elements.constraintForm.addEventListener("change", () => {
  elements.constraintError.textContent = "请至少选择一项。";
  elements.constraintError.hidden = true;
  hideRailError();
});

elements.revokeMemory.addEventListener("click", revokeRememberedConstraints);
elements.findAlternatives.addEventListener("click", findAndRevalidateAlternatives);

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
  editProfile("constraint");
});

function returnToLabelEditing() {
  elements.constraintStep.hidden = true;
  elements.safetyResult.hidden = true;
  elements.form.hidden = false;
  elements.resultState.hidden = true;
  hideRailError();
  state.confirmedFields = null;
  state.normalizedLabel = null;
  state.currentConstraints = [];
  elements.reviewTitle.textContent = "确认识别文字";
  elements.reviewCount.textContent = `${state.analysis?.fields.length || 0} 项`;
  elements.proofState.textContent = "待重新确认";
  elements.fieldList.querySelector("textarea")?.focus();
  announce("已返回标签文字编辑，请修改后重新确认");
}

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
  elements.viewFullImage.href = state.previewUrl;
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
    if (payload.checkpoint?.resume_token) {
      state.checkpointToken = payload.checkpoint.resume_token;
    }
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

function syncPreviewAspectRatio() {
  const width = elements.preview.naturalWidth;
  const height = elements.preview.naturalHeight;
  if (!width || !height) return;
  elements.proofSheet.style.setProperty("--preview-aspect", `${width} / ${height}`);
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
  state.checkpointToken = null;
  state.currentConstraints = [];
  elements.workbench.classList.remove("has-analysis");
  elements.heroLayout.classList.remove("has-analysis");
  elements.fieldList.replaceChildren();
  elements.reviewCount.textContent = "0 项";
}

function readMemoryCredentials() {
  try {
    const value = JSON.parse(localStorage.getItem(MEMORY_CREDENTIALS_KEY) || "null");
    if (value?.profileId && value?.accessToken) return value;
  } catch {
    localStorage.removeItem(MEMORY_CREDENTIALS_KEY);
  }
  return null;
}

function memoryRequestOptions(method = "GET", body = null) {
  const headers = { Authorization: `Bearer ${state.memoryCredentials.accessToken}` };
  if (body) headers["Content-Type"] = "application/json";
  return { method, headers, ...(body ? { body: JSON.stringify(body) } : {}) };
}

async function ensureMemoryConsent() {
  if (state.memoryCredentials) return;
  const profileId = `profile-${crypto.randomUUID()}`;
  const response = await fetch("/api/v1/memory/consents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile_id: profileId,
      purpose: "跨会话保存用户明确填写的个人饮食关注与食品约束",
      explicit_consent: true,
    }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || "无法开启约束记忆。");
  state.memoryCredentials = { profileId, accessToken: payload.access_token };
  localStorage.setItem(MEMORY_CREDENTIALS_KEY, JSON.stringify(state.memoryCredentials));
}

async function loadRememberedConstraints() {
  if (!state.memoryCredentials) return;
  elements.rememberConstraints.checked = true;
  elements.memoryStatus.textContent = "正在读取已保存约束…";
  try {
    const { profileId } = state.memoryCredentials;
    const response = await fetch(
      `/api/v1/memory/items?profile_id=${encodeURIComponent(profileId)}`,
      memoryRequestOptions(),
    );
    const payload = await response.json();
    if (!response.ok) {
      if (response.status === 403) clearMemoryCredentials();
      throw new Error(payload.message || "无法读取已保存约束。");
    }
    state.rememberedItems = payload.items.filter((item) => item.kind === "constraint");
    state.profileMemoryItem = payload.items.find(
      (item) => item.kind === "response_preference" && item.value?.preference === "health_profile",
    ) || null;
    const rememberedProfile = state.profileMemoryItem?.value?.profile;
    if (isValidProfile(rememberedProfile)) {
      state.profile = rememberedProfile;
      localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(rememberedProfile));
      populateProfileForm(rememberedProfile);
      elements.rememberProfile.checked = true;
      renderScanProfile(rememberedProfile);
      if (!state.analysis) showProfileScreen("scan");
    }
    renderRememberedConstraints();
    applyRememberedConstraints();
    elements.memoryStatus.textContent = state.rememberedItems.length
      ? "已从此设备保存的约束预选，请在评估前核对。"
      : "已授权记忆，尚未保存约束。";
  } catch (error) {
    elements.memoryStatus.textContent = error.message;
  }
}

function currentConstraintValues() {
  const allergyValues = [...elements.constraintForm.querySelectorAll('input[name="constraint"]:checked')]
    .map((input) => ({
      kind: "allergy",
      canonical_value: input.value,
      severity: "severe",
    }));
  const customAvoidances = (state.profile?.customAllergens || []).map((value) => ({
    kind: "user_avoidance",
    canonical_value: value,
    severity: "unspecified",
  }));
  if (!elements.nutritionKey.value) return [...allergyValues, ...customAvoidances];
  const option = elements.nutritionKey.selectedOptions[0];
  return [...allergyValues, ...customAvoidances, {
    kind: "nutrition_limit",
    canonical_value: elements.nutritionKey.value,
    operator: "max",
    threshold: elements.nutritionThreshold.valueAsNumber,
    unit: option.dataset.unit,
    basis: option.dataset.basis,
  }];
}

function applyProfileConstraints() {
  if (!state.profile) return;
  elements.constraintForm.querySelectorAll('input[name="constraint"]').forEach((input) => {
    input.checked = state.profile.allergens.includes(input.value);
  });
  renderScanProfile(state.profile);
}

async function syncRememberedConstraints() {
  elements.memoryStatus.textContent = "正在保存你明确选择的约束…";
  try {
    await ensureMemoryConsent();
    const { profileId } = state.memoryCredentials;
    for (const item of state.rememberedItems) {
      const response = await fetch(
        `/api/v1/memory/items/${item.memory_id}?profile_id=${encodeURIComponent(profileId)}`,
        memoryRequestOptions("DELETE"),
      );
      if (!response.ok) throw new Error("无法更新已保存约束。");
    }
    const saved = [];
    for (const value of currentConstraintValues()) {
      const response = await fetch(
        `/api/v1/memory/items?profile_id=${encodeURIComponent(profileId)}`,
        memoryRequestOptions("POST", { kind: "constraint", value }),
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || "无法保存约束。");
      saved.push(payload.item);
    }
    state.rememberedItems = saved;
    renderRememberedConstraints();
    elements.memoryStatus.textContent = `已保存 ${saved.length} 项；可随时单独删除或撤销授权。`;
  } catch (error) {
    elements.memoryStatus.textContent = `本次结果有效，但约束没有保存：${error.message}`;
  }
}

function applyRememberedConstraints() {
  elements.rememberConstraints.checked = Boolean(state.memoryCredentials);
  if (elements.constraintStep.hidden || !state.rememberedItems.length) return;
  state.rememberedItems.forEach((item) => {
    const value = item.value || {};
    if (value.kind === "allergy") {
      const input = [...elements.constraintForm.querySelectorAll('input[name="constraint"]')]
        .find((candidate) => candidate.value === value.canonical_value);
      if (input) input.checked = true;
    } else if (value.kind === "nutrition_limit") {
      const option = [...elements.nutritionKey.options]
        .find((candidate) => candidate.value === value.canonical_value);
      if (option) {
        elements.nutritionKey.value = value.canonical_value;
        elements.nutritionThreshold.value = value.threshold;
        updateNutritionLimitControl();
      }
    }
  });
}

function renderRememberedConstraints() {
  elements.memoryList.replaceChildren();
  elements.memorySaved.hidden = !state.memoryCredentials;
  state.rememberedItems.forEach((item) => {
    const row = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = describeConstraint(item.value);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "memory-delete";
    remove.textContent = "删除";
    remove.setAttribute("aria-label", `删除已保存约束：${name.textContent}`);
    remove.addEventListener("click", () => deleteRememberedConstraint(item));
    row.append(name, remove);
    elements.memoryList.append(row);
  });
}

function describeConstraint(value) {
  if (value.kind === "nutrition_limit") {
    return `${constraintLabels[value.canonical_value] || value.canonical_value} · ${value.threshold}${value.unit}`;
  }
  return constraintLabels[value.canonical_value] || value.canonical_value;
}

async function deleteRememberedConstraint(item) {
  try {
    const { profileId } = state.memoryCredentials;
    const response = await fetch(
      `/api/v1/memory/items/${item.memory_id}?profile_id=${encodeURIComponent(profileId)}`,
      memoryRequestOptions("DELETE"),
    );
    if (!response.ok) throw new Error("删除失败，请重试。");
    state.rememberedItems = state.rememberedItems.filter(
      (candidate) => candidate.memory_id !== item.memory_id,
    );
    renderRememberedConstraints();
    elements.memoryStatus.textContent = "已删除这项保存的约束。";
  } catch (error) {
    elements.memoryStatus.textContent = error.message;
  }
}

async function revokeRememberedConstraints() {
  if (!state.memoryCredentials) return;
  elements.revokeMemory.disabled = true;
  try {
    const { profileId } = state.memoryCredentials;
    const response = await fetch(
      `/api/v1/memory/consents/current?profile_id=${encodeURIComponent(profileId)}`,
      memoryRequestOptions("DELETE"),
    );
    if (!response.ok) throw new Error("撤销授权失败，请重试。");
    clearMemoryCredentials();
    elements.memoryStatus.textContent = "已清除全部保存内容并撤销授权。";
  } catch (error) {
    elements.memoryStatus.textContent = error.message;
  } finally {
    elements.revokeMemory.disabled = false;
  }
}

function clearMemoryCredentials() {
  state.memoryCredentials = null;
  state.rememberedItems = [];
  state.profileMemoryItem = null;
  state.profile = null;
  localStorage.removeItem(MEMORY_CREDENTIALS_KEY);
  localStorage.removeItem(PROFILE_STORAGE_KEY);
  elements.rememberConstraints.checked = false;
  elements.rememberProfile.checked = false;
  renderRememberedConstraints();
  if (!state.analysis) showProfileScreen("profile");
}

function renderSafetyResult(payload) {
  const riskOrder = { avoid: 3, caution: 2, unknown: 1, compatible: 0 };
  const primary = [...payload.findings].sort(
    (left, right) => riskOrder[right.risk_level] - riskOrder[left.risk_level],
  )[0];
  const nutrition = payload.normalized_label?.nutrition || state.normalizedLabel?.nutrition;
  const titles = resultTitles(payload.overall_risk_level, primary, nutrition);
  const findingTitles = {
    avoid: "不建议食用",
    caution: "需要谨慎确认",
    unknown: "信息不足",
    compatible: "未发现冲突",
  };
  const symbols = { avoid: "!", caution: "?", unknown: "…", compatible: "✓" };

  elements.constraintStep.hidden = true;
  elements.safetyResult.hidden = false;
  hideRailError();
  elements.reviewTitle.textContent = "本次食用结论";
  elements.safetyResult.dataset.risk = payload.overall_risk_level;
  elements.evidencePanel.hidden = false;
  elements.riskSymbol.textContent = symbols[payload.overall_risk_level];
  elements.riskKicker.textContent = `已核对 ${payload.findings.length} 项个人设置`;
  elements.safetyTitle.textContent = titles.heading;
  elements.riskSummary.textContent = primary.explanation;
  renderDecisionSupport(payload.overall_risk_level, nutrition, payload.findings);
  elements.matchedText.textContent = primary.matched_text || "—";
  elements.matchedConstraint.textContent = constraintLabels[primary.constraint] || primary.constraint;
  elements.matchedLocation.textContent = primary.matched_location;
  elements.reviewCount.textContent = payload.overall_risk_level === "avoid" ? "明确命中" : "评估完成";
  elements.proofState.textContent = "安全规则已评估";
  resetAlternativeResults();
  const suggestion = payload.alternative_category_suggestion;
  if (suggestion?.status === "suggested" && suggestion.category) {
    elements.alternativeCategory.value = suggestion.category;
    const name = elements.alternativeCategory.selectedOptions[0]?.textContent || suggestion.category;
    elements.alternativeStatus.textContent = `根据已确认标签建议“${name}”，请核对后再查找。`;
  }
  elements.alternativeDiscovery.hidden = false;

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
    status.textContent = findingTitles[finding.risk_level];
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
  announce(`${titles.heading}，${primary.matched_text || primary.explanation}`);
}

function resultTitles(riskLevel, primary, nutrition) {
  if (riskLevel === "avoid") return { heading: "不建议食用" };
  if (riskLevel === "unknown") return { heading: "暂时无法判断" };
  if (riskLevel === "compatible") return { heading: "可以食用（当前设置下）" };
  if (primary?.reason_code === "PRECAUTIONARY_ALLERGEN_STATEMENT") {
    return { heading: "确认过敏风险后再决定" };
  }
  return {
    heading: nutrition?.basis?.type === "per_serving" ? "按包装份量食用" : "谨慎食用，份量待确认",
  };
}

function renderDecisionSupport(riskLevel, nutrition, findings) {
  renderPortionGuidance(riskLevel, nutrition, findings);
  renderNutritionSnapshot(nutrition);
}

function renderPortionGuidance(riskLevel, nutrition, findings) {
  const allergenFinding = findings.find((finding) =>
    finding.risk_level !== "compatible" && Object.hasOwn(allergenNames, finding.constraint),
  );
  if (allergenFinding) {
    elements.portionValue.textContent = "没有可确认的安全份量";
    elements.portionNote.textContent = riskLevel === "avoid"
      ? "标签已明确命中需要避开的成分，不应通过减少份量来降低过敏风险。"
      : "包装提示可能含有相关过敏原；少量食用也不能被视为安全。";
    return;
  }

  const basis = nutrition?.basis;
  if (basis?.type === "per_serving") {
    const amount = basis.unit === "serving"
      ? "包装标示的 1 份"
      : `包装标示的 1 份（${formatNumber(basis.amount)}${nutrientUnitNames[basis.unit] || basis.unit}）`;
    elements.portionValue.textContent = amount;
    elements.portionNote.textContent = "这是包装用于列示营养数值的份量，不是根据个人健康状况生成的每日建议量。";
    return;
  }

  elements.portionValue.textContent = "暂缺可靠的一次食用量";
  elements.portionNote.textContent = basis
    ? `标签仅提供${nutritionBasisText(basis)}口径，无法可靠换算成一次吃多少。`
    : "标签没有确认每份大小，系统不会生成看似精确的克数或频率。";
}

function renderNutritionSnapshot(nutrition) {
  elements.nutritionStatList.replaceChildren();
  const basis = nutrition?.basis;
  elements.nutritionBasisLabel.textContent = basis ? nutritionBasisText(basis) : "口径未确认";

  const healthConcerns = state.profile?.healthConcerns || [];
  const priorities = [...new Set(
    healthConcerns.flatMap((concern) => healthNutrientPriorities[concern] || []),
  )];
  const defaultKeys = healthConcerns.length || state.profile?.customHealthConcerns?.length
    ? []
    : ["energy", "protein", "fat", "carbohydrate", "sodium"];
  const keys = (priorities.length ? priorities : defaultKeys).slice(0, 4);
  const facts = new Map((nutrition?.nutrients || []).map((fact) => [fact.canonical_name, fact]));

  if (!nutrition || keys.length === 0) {
    elements.nutritionStatEmpty.hidden = false;
    elements.nutritionStatEmpty.textContent = "当前健康关注无法仅凭常规营养成分表量化，已保留配料与证据说明供你核对。";
    return;
  }

  elements.nutritionStatEmpty.hidden = true;
  keys.forEach((key) => {
    const fact = facts.get(key);
    const item = document.createElement("div");
    item.className = "nutrition-stat";
    const name = document.createElement("span");
    name.textContent = nutrientNames[key] || key;
    const value = document.createElement("strong");
    value.textContent = fact
      ? `${formatNumber(fact.value)}${nutrientUnitNames[fact.unit] || fact.unit}`
      : "标签未单列";
    const note = document.createElement("small");
    note.textContent = fact ? "包装标示值" : "不等于含量为零";
    item.append(name, value, note);
    elements.nutritionStatList.append(item);
  });
}

function nutritionBasisText(basis) {
  if (basis.type === "per_100g") return "每100克";
  if (basis.type === "per_100ml") return "每100毫升";
  if (basis.type === "per_serving") {
    if (basis.unit === "serving") return "每份";
    return `每份${formatNumber(basis.amount)}${nutrientUnitNames[basis.unit] || basis.unit}`;
  }
  return "包装已确认口径";
}

function formatNumber(value) {
  return Number.isFinite(Number(value))
    ? new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(Number(value))
    : "—";
}

function renderHealthFocusOnlyResult() {
  const healthSummary = [
    ...(state.profile?.healthConcerns || []).map((value) => healthConcernNames[value] || value),
    ...(state.profile?.customHealthConcerns || []),
  ].join("、");
  elements.constraintStep.hidden = true;
  elements.safetyResult.hidden = false;
  elements.safetyResult.dataset.risk = "unknown";
  elements.riskSymbol.textContent = "i";
  elements.riskKicker.textContent = "健康关注的标签信息";
  elements.safetyTitle.textContent = "暂时无法判断";
  elements.riskSummary.textContent = "你没有设置已知过敏原。本次先按健康关注整理标签重点；当前版本不会把健康问题自动换算成医疗阈值或具体食用份量。";
  renderDecisionSupport("unknown", state.normalizedLabel?.nutrition, []);
  elements.matchedText.textContent = "未设置硬性回避项";
  elements.matchedConstraint.textContent = healthSummary || "未设置";
  elements.matchedLocation.textContent = "已确认配料表与营养成分表";
  elements.additionalFindings.hidden = true;
  elements.claimResults.hidden = true;
  elements.additiveResults.hidden = true;
  elements.evidencePanel.hidden = true;
  elements.alternativeDiscovery.hidden = true;
  elements.reviewTitle.textContent = "个人标签重点";
  elements.reviewCount.textContent = "已整理";
  elements.proofState.textContent = "标签已确认";
  elements.safetyResult.focus();
  announce("标签信息已整理；当前没有设置需要自动检查的过敏原");
}

async function findAndRevalidateAlternatives() {
  const category = elements.alternativeCategory.value;
  if (!category) {
    elements.alternativeStatus.textContent = "请先选择与当前商品相同的类别。";
    elements.alternativeCategory.focus();
    return;
  }
  if (!state.checkpointToken || !state.currentConstraints.length) {
    elements.alternativeStatus.textContent = "当前分析会话无法恢复，请重新检查个人约束。";
    return;
  }
  elements.findAlternatives.disabled = true;
  elements.findAlternatives.textContent = "正在逐一复核…";
  elements.alternativeStatus.textContent = "正在检查候选标签完整度，并重新运行全部个人约束。";
  elements.alternativeResults.hidden = true;
  announce("正在查找并逐项复核同类候选");
  try {
    const response = await fetch("/api/v1/alternatives/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_id: state.analysis.request_id,
        jurisdiction: "CN",
        region: "CN",
        applicable_date: new Date().toISOString().slice(0, 10),
        confirmed_fields: state.confirmedFields,
        nutrition_rows: state.analysis.fields.find((field) => field.name === "nutrition_table")
          ?.nutrition_table?.rows || null,
        constraints: state.currentConstraints,
        category,
        resume_token: state.checkpointToken,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message || "替代品复核失败。");
    if (payload.checkpoint?.resume_token) state.checkpointToken = payload.checkpoint.resume_token;
    renderAlternativeResults(payload);
  } catch (error) {
    elements.alternativeStatus.textContent = error.message;
    announce(error.message);
  } finally {
    elements.findAlternatives.disabled = false;
    elements.findAlternatives.textContent = "查找并逐项复核";
  }
}

function resetAlternativeResults() {
  elements.alternativeCount.textContent = "尚未查找";
  elements.alternativeStatus.textContent = "";
  elements.alternativeSource.textContent = "数据来源将在查找后显示。";
  elements.alternativeResults.hidden = true;
  elements.alternativeList.replaceChildren();
  elements.alternativeComparisonList.replaceChildren();
  elements.alternativeComparison.hidden = true;
  elements.alternativeExclusionList.replaceChildren();
  elements.alternativeExclusions.hidden = true;
}

function renderAlternativeResults(payload) {
  elements.alternativeList.replaceChildren();
  elements.alternativeComparisonList.replaceChildren();
  elements.alternativeExclusionList.replaceChildren();
  elements.alternativeResults.hidden = false;
  elements.alternativeCount.textContent = `${payload.eligible.length} 项通过复核`;
  elements.alternativeSource.textContent = alternativeSourceCopy(
    payload.catalog_scope,
    payload.catalog_status,
  );
  if (!payload.eligible.length) {
    const catalogMatches = payload.candidate_count + payload.evidence_rejected.length;
    elements.alternativeStatus.textContent =
      `目录找到 ${catalogMatches} 条同类记录；${payload.revalidated_count} 条进入约束复核，当前没有候选通过全部约束。`;
  } else {
    elements.alternativeStatus.textContent =
      `已逐一复核 ${payload.revalidated_count}/${payload.candidate_count} 项候选；仅展示通过硬约束的结果。`;
  }
  payload.eligible.forEach((item) => {
    const article = document.createElement("article");
    article.className = "alternative-item";
    const header = document.createElement("header");
    const title = document.createElement("h4");
    title.textContent = `${item.rank ? `${item.rank}. ` : ""}${item.display_name}`;
    const status = document.createElement("span");
    status.textContent = "约束复核通过";
    header.append(title, status);
    const useCase = document.createElement("p");
    useCase.textContent = item.use_case;
    const explanation = document.createElement("p");
    explanation.textContent = item.explanation;
    const evidence = document.createElement("p");
    evidence.className = "alternative-evidence";
    evidence.textContent = `标签记录 ${item.label_confirmed_at} · ${sourceAuthorityLabel(item.label_source_authority)} · ${item.evidence_ids.join("、")}`;
    article.append(header, useCase, explanation, evidence);
    if (item.ingredients_image_url?.startsWith("https://")) {
      const source = document.createElement("a");
      source.className = "alternative-source-link";
      source.href = item.ingredients_image_url;
      source.target = "_blank";
      source.rel = "noopener noreferrer";
      source.textContent = "查看配料标签图片证据";
      article.append(source);
    }
    if (item.label_source_url?.startsWith("https://")) {
      const record = document.createElement("a");
      record.className = "alternative-source-link";
      record.href = item.label_source_url;
      record.target = "_blank";
      record.rel = "noopener noreferrer";
      record.textContent = "查看商品源记录";
      article.append(record);
    }
    elements.alternativeList.append(article);
  });

  const comparisons = payload.comparison?.comparisons || [];
  elements.alternativeComparison.hidden = comparisons.length === 0;
  comparisons.forEach((comparison) => {
    const row = document.createElement("dl");
    row.className = "alternative-comparison-row";
    const term = document.createElement("dt");
    term.textContent = nutrientNames[comparison.nutrient] || comparison.nutrient;
    const description = document.createElement("dd");
    description.textContent = comparison.values
      .map((item) => `${item.display_name} ${item.value}${comparison.unit}`)
      .join("；");
    row.append(term, description);
    elements.alternativeComparisonList.append(row);
  });

  const excluded = [
    ...payload.excluded.map((item) => ({
      name: item.display_name,
      reason: `${item.risk_level} · ${item.findings[0]?.matched_text || "未通过个人约束"}`,
    })),
    ...payload.evidence_rejected.map((item) => ({
      name: item.display_name,
      reason: alternativeRejectionLabel(item.reason_code),
    })),
  ];
  elements.alternativeExclusions.hidden = excluded.length === 0;
  excluded.forEach((item) => {
    const row = document.createElement("li");
    row.textContent = `${item.name}：${item.reason}`;
    elements.alternativeExclusionList.append(row);
  });
  announce(elements.alternativeStatus.textContent);
}

function alternativeRejectionLabel(reasonCode) {
  return {
    LIVE_LABEL_EVIDENCE_INCOMPLETE: "实时商品缺少完整配料文字、标签图片或版本信息",
    DUPLICATE_PRODUCT_RECORD: "重复商品记录，已合并",
    LABEL_EVIDENCE_INCOMPLETE: "标签证据不完整，未进入安全复核",
    LABEL_EVIDENCE_EXPIRED: "标签记录已过期，未进入安全复核",
    LABEL_EVIDENCE_STALE: "标签记录过旧，需要重新核对",
    LABEL_EVIDENCE_FROM_FUTURE: "标签日期与当前评估日期不一致",
    LABEL_EVIDENCE_HASH_MISMATCH: "标签证据校验失败，未进入安全复核",
  }[reasonCode] || "证据不足，未进入安全复核";
}

function alternativeSourceCopy(scope, status) {
  if (scope === "open_food_facts") {
    return "本次来自 Open Food Facts 开放商品数据库（ODbL）。这是社区维护数据，页面仅展示具有配料文字、图片和版本记录的候选，仍应与实物包装核对。";
  }
  if (scope === "open_food_facts_with_curated_fallback" || status === "degraded") {
    return "实时商品目录本次未返回可复核证据，已明确降级为项目内置验收目录；其中商品是测试记录，不代表在售。";
  }
  return "本次使用项目内置的人工核验验收目录；其中商品是测试记录，不代表在售。";
}

function sourceAuthorityLabel(authority) {
  return {
    manufacturer: "厂商来源",
    internal_review: "内部人工核验",
    community: "社区数据",
  }[authority] || "来源待核对";
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
    category.textContent = item.unknowns?.includes("declared_additive_not_in_function_dictionary")
      ? "功能待收录"
      : (item.ingredient?.category || "功能待确认").replace("食品添加剂·", "");
    header.append(name, category);
    const explanation = document.createElement("p");
    explanation.textContent = item.explanation || "已识别标签文字，但当前解释词典尚未建立可靠映射。";
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
      setPrivacyStatus(plannerPrivacyCopy(health, "图片默认不保存"));
    } else if (health.remote_processing) {
      elements.ocrStatus.textContent = "腾讯云 OCR";
      elements.ocrProofNote.innerHTML = "<strong>云端识别</strong> · 结果仍需人工核对";
      setPrivacyStatus(
        plannerPrivacyCopy(health, "图片发送至腾讯云处理，本平台不保存原图"),
      );
    } else {
      elements.ocrStatus.textContent = "本地 PP-OCRv6";
      elements.ocrProofNote.innerHTML = "<strong>本地识别</strong> · 结果仍需人工核对";
      setPrivacyStatus(plannerPrivacyCopy(health, "图片在本机处理，默认不保存"));
    }
  } catch {
    // The upload action remains available; request-level errors provide recovery.
  }
}

function plannerPrivacyCopy(health, imageCopy) {
  const notices = [imageCopy];
  if (health.planner?.remote_processing) {
    notices.push("确认后的标签事实会发送至 OpenAI，用于选择下一项证据工具");
  }
  if (health.rag?.remote_processing) {
    notices.push("法规查询和候选条款会发送至 OpenAI，用于语义检索与重排");
  }
  return notices.join("；");
}

function setPrivacyStatus(message) {
  elements.privacyStatuses.forEach((element) => {
    element.lastChild.textContent = message;
  });
}
