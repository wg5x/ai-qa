const APP_BASE_PATH = window.APP_BASE_PATH || "";
const qaConversationHistory = [];
const DISTRIBUTION_ID_STORAGE_KEY = "ai-qa-distribution-id";

function distributionIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("id") || params.get("distributionId") || "";
}

function storedDistributionId() {
  try {
    return sessionStorage.getItem(DISTRIBUTION_ID_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function persistDistributionId(distributionId) {
  if (!distributionId) return;
  try {
    sessionStorage.setItem(DISTRIBUTION_ID_STORAGE_KEY, distributionId);
  } catch {
    // Storage can be unavailable in private or restricted browser contexts.
  }
}

const currentDistributionId = distributionIdFromUrl() || storedDistributionId();
persistDistributionId(currentDistributionId);

function syncDistributionNavigationLinks() {
  if (!currentDistributionId) return;

  document.querySelectorAll("a[href]").forEach((link) => {
    const rawHref = link.getAttribute("href");
    if (!rawHref || rawHref.startsWith("#")) return;

    const url = new URL(rawHref, window.location.origin);
    if (url.origin !== window.location.origin) return;
    if (APP_BASE_PATH && !url.pathname.startsWith(`${APP_BASE_PATH}/`) && url.pathname !== APP_BASE_PATH) return;
    url.searchParams.set("id", currentDistributionId);
    link.href = `${url.pathname}${url.search}${url.hash}`;
  });
}

syncDistributionNavigationLinks();

function appUrl(path) {
  if (
    !path.startsWith("/") ||
    !APP_BASE_PATH ||
    path.startsWith(`${APP_BASE_PATH}/`) ||
    path.startsWith("/dist/")
  ) {
    return path;
  }
  return `${APP_BASE_PATH}${path}`;
}

async function apiRequest(url, options = {}) {
  const response = await fetch(appUrl(url), options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && payload.detail
        ? payload.detail
        : `请求失败 (${response.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return payload;
}

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 2800);
}

async function loadDistributionRuntimeConfig() {
  if (!currentDistributionId) return null;
  return apiRequest(`/dist/api/runtime/distributions/${encodeURIComponent(currentDistributionId)}`);
}

function applyDistributionRuntimeConfig(config) {
  const appName = String(config?.app?.name || "").trim();
  if (!appName) return;

  document.title = document.title.replace("本地销售 AI", appName);
  document.querySelectorAll("[data-app-name]").forEach((node) => {
    node.textContent = appName;
  });
}

async function initDistributionRuntimeConfig() {
  try {
    const config = await loadDistributionRuntimeConfig();
    applyDistributionRuntimeConfig(config);
  } catch (error) {
    showToast(`读取应用配置失败：${error.message}`, true);
  }
}

function renderList(container, items, renderItem) {
  container.innerHTML = "";
  if (!items.length) {
    container.innerHTML = '<p class="card-meta">暂无数据</p>';
    return;
  }
  items.forEach((item) => {
    const node = document.createElement("div");
    node.className = "card-item";
    node.innerHTML = renderItem(item);
    container.appendChild(node);
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function appendChatMessage(thread, role, html) {
  const node = document.createElement("article");
  node.className = `chat-message ${role}`;
  node.innerHTML = `
    <div class="message-avatar">${role === "user" ? "我" : "AI"}</div>
    <div class="message-bubble">${html}</div>
  `;
  thread.appendChild(node);
  thread.scrollTop = thread.scrollHeight;
  return node;
}

function rememberQAMessage(role, content) {
  qaConversationHistory.push({ role, content });
  if (qaConversationHistory.length > 8) {
    qaConversationHistory.splice(0, qaConversationHistory.length - 8);
  }
}

function renderMaterialPreview(material) {
  if (typeof material === "string") {
    return `<li>${escapeHtml(material)}</li>`;
  }

  const fileUrl = material.file_url ? appUrl(material.file_url) : "";
  const media =
    fileUrl && material.material_type === "image"
      ? `<img class="material-preview" src="${escapeHtml(fileUrl)}" alt="${escapeHtml(material.name || "推荐图片")}">`
      : fileUrl && material.material_type === "video"
        ? `<video class="material-preview" src="${escapeHtml(fileUrl)}" controls preload="metadata"></video>`
        : "";
  const openLink = fileUrl
    ? `<a class="btn ghost" href="${escapeHtml(fileUrl)}" target="_blank" rel="noopener">打开素材</a>`
    : "";
  const meta = [material.brand, material.scenario, material.material_type]
    .filter(Boolean)
    .map(escapeHtml)
    .join(" · ");

  return `
    <li class="material-recommendation-card">
      ${media}
      <div>
        <strong>${escapeHtml(material.name || "推荐素材")}</strong>
        <div class="card-meta">${meta}</div>
        <p>${escapeHtml(material.description || "")}</p>
        ${material.recommended_script ? `<p class="hint">建议话术：${escapeHtml(material.recommended_script)}</p>` : ""}
        ${openLink}
      </div>
    </li>
  `;
}

function renderAnswerSections(answer) {
  const references = (answer.references || [])
    .map((item) => `<li>${escapeHtml(typeof item === "string" ? item : JSON.stringify(item))}</li>`)
    .join("");
  const materials = (answer.recommended_materials || [])
    .map((item) => renderMaterialPreview(item))
    .join("");
  const warnings = (answer.warnings || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");

  return `
    <div class="answer-section">
      <h3>标准回复</h3>
      <pre class="result-pre">${escapeHtml(answer.standard_reply || "")}</pre>
      <button type="button" class="btn secondary copy-answer">复制标准回复</button>
    </div>
    <div class="answer-grid">
      <section>
        <h3>回复思路</h3>
        <p>${escapeHtml(answer.reply_thinking || "")}</p>
      </section>
      <section>
        <h3>推荐素材</h3>
        <ul>${materials || "<li>暂无推荐素材</li>"}</ul>
      </section>
      <section>
        <h3>参考依据</h3>
        <ul>${references || "<li>暂无参考依据</li>"}</ul>
      </section>
      <section>
        <h3>注意事项</h3>
        <ul class="warnings">${warnings || "<li>暂无注意事项</li>"}</ul>
      </section>
    </div>
  `;
}

function initQAPage() {
  const form = document.getElementById("qa-form");
  const resultPanel = document.getElementById("qa-result");
  const copyButton = document.getElementById("copy-reply");
  const chatThread = document.getElementById("chat-thread");
  if (!form) return;
  initDistributionRuntimeConfig();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = form.question.value.trim();
    if (!question) return;

    const submitButton = document.getElementById("qa-submit");
    submitButton.disabled = true;
    submitButton.textContent = "生成中";
    appendChatMessage(chatThread, "user", `<p>${escapeHtml(question)}</p>`);
    const pendingMessage = appendChatMessage(
      chatThread,
      "assistant",
      '<p class="card-meta">正在检索知识库并生成回复...</p>'
    );

    try {
      const answer = await apiRequest("/api/qa/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          conversation_history: qaConversationHistory.slice(-8),
          distribution_id: currentDistributionId,
        }),
      });

      document.getElementById("latest-question").textContent = question;
      document.getElementById("reply-thinking").textContent = answer.reply_thinking;
      document.getElementById("standard-reply").textContent = answer.standard_reply;

      const references = document.getElementById("references");
      references.innerHTML = "";
      (answer.references || []).forEach((item) => {
        const li = document.createElement("li");
        li.textContent = typeof item === "string" ? item : JSON.stringify(item);
        references.appendChild(li);
      });

      const materials = document.getElementById("recommended-materials");
      materials.innerHTML = "";
      (answer.recommended_materials || []).forEach((item) => {
        const template = document.createElement("template");
        template.innerHTML = renderMaterialPreview(item).trim();
        materials.appendChild(template.content.firstElementChild);
      });

      const warnings = document.getElementById("warnings");
      warnings.innerHTML = "";
      (answer.warnings || []).forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        warnings.appendChild(li);
      });

      resultPanel.classList.remove("hidden");
      pendingMessage.querySelector(".message-bubble").innerHTML = renderAnswerSections(answer);
      rememberQAMessage("user", question);
      rememberQAMessage("assistant", answer.standard_reply || "");
      showToast("回答已生成");
      form.reset();
    } catch (error) {
      pendingMessage.querySelector(".message-bubble").innerHTML =
        `<p class="warnings">${escapeHtml(error.message)}</p>`;
      showToast(error.message, true);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "发送";
    }
  });

  copyButton?.addEventListener("click", async () => {
    const text = document.getElementById("standard-reply")?.textContent || "";
    if (!text) return;
    await navigator.clipboard.writeText(text);
    showToast("标准回复已复制");
  });

  chatThread?.addEventListener("click", async (event) => {
    if (!event.target.closest(".copy-answer")) return;
    const text = document.getElementById("standard-reply")?.textContent || "";
    if (!text) return;
    await navigator.clipboard.writeText(text);
    showToast("标准回复已复制");
  });
}

async function uploadExcel(form, endpoint) {
  const fileInput = form.querySelector('input[type="file"]');
  if (!fileInput?.files?.length) {
    throw new Error("请选择 Excel 文件");
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  return apiRequest(endpoint, { method: "POST", body: formData });
}

function initKnowledgePage() {
  const openKnowledgeButton = document.getElementById("open-knowledge-modal");
  const knowledgeImportForm = document.getElementById("knowledge-import-form");
  const createKnowledgeButton = document.getElementById("create-knowledge-data");
  const knowledgeModal = document.getElementById("knowledge-modal");
  const closeKnowledgeButton = document.getElementById("close-knowledge-modal");
  const knowledgeEditModal = document.getElementById("knowledge-edit-modal");
  const knowledgeEditForm = document.getElementById("knowledge-edit-form");
  const closeKnowledgeEditButton = document.getElementById("close-knowledge-edit-modal");
  const knowledgeList = document.getElementById("knowledge-list");
  const knowledgePageInfo = document.getElementById("knowledge-page-info");
  const knowledgePrev = document.getElementById("knowledge-prev");
  const knowledgeNext = document.getElementById("knowledge-next");
  const resultPanel = document.getElementById("import-result");
  const resultBody = document.getElementById("import-result-body");
  if (!knowledgeList) return;
  const knowledgePaging = {
    page: 1,
    pageSize: 10,
    pages: 1,
  };

  const knowledgeTypeLabel = (sourceType) => {
    if (sourceType === "quote") return "报价单";
    if (sourceType === "contract") return "合同";
    if (sourceType === "manual") return "谈单手册";
    return "知识";
  };

  const renderKnowledgeCard = (item) => `
      <h3>${escapeHtml(item.title || "未命名知识")}</h3>
      <div class="card-meta">类型：${escapeHtml(knowledgeTypeLabel(item.source_type))}</div>
      <p>${escapeHtml(item.description || "")}</p>
      <div class="card-meta">来源：${escapeHtml(item.source_file || "-")}</div>
      <div class="card-meta">标签：${escapeHtml(item.tags || "-")}</div>
      <div class="card-actions">
        <button type="button" class="btn ghost edit-knowledge" data-knowledge="${escapeHtml(JSON.stringify(item))}">编辑</button>
      </div>
    `;

  const renderKnowledgePagination = (pageData) => {
    if (knowledgePageInfo) {
      knowledgePageInfo.textContent = `共 ${pageData.total} 条 · 第 ${pageData.page} / ${pageData.pages} 页`;
    }
    if (knowledgePrev) knowledgePrev.disabled = pageData.page <= 1;
    if (knowledgeNext) knowledgeNext.disabled = pageData.page >= pageData.pages;
  };

  const loadKnowledgeItems = async (page = knowledgePaging.page) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(knowledgePaging.pageSize),
    });
    const pageData = await apiRequest(`/api/imports/knowledge/items?${params}`);
    knowledgePaging.page = pageData.page;
    knowledgePaging.pages = pageData.pages;
    renderList(knowledgeList, pageData.items, renderKnowledgeCard);
    renderKnowledgePagination(pageData);
  };

  const closeKnowledgeModal = () => {
    knowledgeModal?.classList.add("hidden");
  };
  const closeKnowledgeEditModal = () => {
    knowledgeEditModal?.classList.add("hidden");
  };
  const openKnowledgeEditModal = (item) => {
    if (!knowledgeEditForm) return;
    knowledgeEditForm.elements.id.value = item.raw_id || String(item.id || "").replace(/^manual-/, "");
    knowledgeEditForm.elements.source_type.value = item.source_type || "manual";
    knowledgeEditForm.elements.title.value = item.title || "";
    knowledgeEditForm.elements.description.value = item.description || "";
    knowledgeEditForm.elements.tags.value = item.tags || "";
    knowledgeEditModal?.classList.remove("hidden");
    knowledgeEditForm.elements.title.focus();
  };

  openKnowledgeButton?.addEventListener("click", () => {
    knowledgeModal?.classList.remove("hidden");
  });
  closeKnowledgeButton?.addEventListener("click", closeKnowledgeModal);
  knowledgeModal?.querySelectorAll("[data-close-knowledge-modal]").forEach((node) => {
    node.addEventListener("click", closeKnowledgeModal);
  });

  knowledgeImportForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    createKnowledgeButton.disabled = true;
    createKnowledgeButton.textContent = "导入中";
    try {
      const formData = new FormData(knowledgeImportForm);
      const result = await apiRequest("/api/imports/knowledge/upload", {
        method: "POST",
        body: formData,
      });
      resultPanel.classList.remove("hidden");
      resultBody.textContent = JSON.stringify(result, null, 2);
      await loadKnowledgeItems(1);
      closeKnowledgeModal();
      knowledgeImportForm.reset();
      showToast("知识已导入并解析");
    } catch (error) {
      showToast(error.message, true);
    } finally {
      createKnowledgeButton.disabled = false;
      createKnowledgeButton.textContent = "导入并解析";
    }
  });

  knowledgeList?.addEventListener("click", (event) => {
    const button = event.target.closest(".edit-knowledge");
    if (!button) return;
    openKnowledgeEditModal(JSON.parse(button.dataset.knowledge));
  });
  closeKnowledgeEditButton?.addEventListener("click", closeKnowledgeEditModal);
  knowledgeEditModal?.querySelectorAll("[data-close-knowledge-edit-modal]").forEach((node) => {
    node.addEventListener("click", closeKnowledgeEditModal);
  });
  knowledgeEditForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(knowledgeEditForm).entries());
    const knowledgeId = payload.id;
    const item = { source_type: payload.source_type };
    delete payload.id;
    delete payload.source_type;
    try {
      await apiRequest(`/api/imports/knowledge/${item.source_type}/${knowledgeId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      closeKnowledgeEditModal();
      await loadKnowledgeItems(knowledgePaging.page);
      showToast("知识片段已更新");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  knowledgePrev?.addEventListener("click", () => {
    loadKnowledgeItems(knowledgePaging.page - 1).catch((error) =>
      showToast(error.message, true)
    );
  });

  knowledgeNext?.addEventListener("click", () => {
    loadKnowledgeItems(knowledgePaging.page + 1).catch((error) =>
      showToast(error.message, true)
    );
  });

  loadKnowledgeItems(1).catch((error) => showToast(error.message, true));
}

function materialCard(item) {
  const meta = [
    item.brand,
    item.scenario,
    item.material_type,
    item.material_grade,
  ]
    .filter(Boolean)
    .map(escapeHtml)
    .join(" · ");

  return `
    <h3>${escapeHtml(item.name || "未命名素材")}</h3>
    <div class="card-meta">${meta}</div>
    <p>${escapeHtml(item.description || "暂无描述")}</p>
    <div class="card-meta">路径：${escapeHtml(item.file_path || "-")}</div>
    <div class="card-meta">标签：${escapeHtml(item.tags || "-")}</div>
    <div class="card-actions">
      <button type="button" class="btn ghost edit-material" data-material="${escapeHtml(JSON.stringify(item))}">编辑</button>
    </div>
  `;
}

const materialPaging = {
  query: "",
  page: 1,
  pageSize: 10,
  pages: 1,
};

async function loadMaterials(query = materialPaging.query, page = materialPaging.page) {
  const list = document.getElementById("material-list");
  if (!list) return;

  materialPaging.query = query;
  materialPaging.page = page;
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(materialPaging.pageSize),
  });
  const url = query
    ? `/api/materials/search?q=${encodeURIComponent(query)}&${params}`
    : `/api/materials?${params}`;
  const pageData = await apiRequest(url);
  materialPaging.page = pageData.page;
  materialPaging.pages = pageData.pages;
  renderList(list, pageData.items, materialCard);
  renderMaterialPagination(pageData);
}

function renderMaterialPagination(pageData) {
  const pageInfo = document.getElementById("material-page-info");
  const prevButton = document.getElementById("material-prev");
  const nextButton = document.getElementById("material-next");
  if (pageInfo) {
    pageInfo.textContent = `共 ${pageData.total} 条 · 第 ${pageData.page} / ${pageData.pages} 页`;
  }
  if (prevButton) prevButton.disabled = pageData.page <= 1;
  if (nextButton) nextButton.disabled = pageData.page >= pageData.pages;
}

function initMaterialsPage() {
  const form = document.getElementById("material-form");
  const fileUpload = document.getElementById("material-file-upload");
  const autoTagButton = document.getElementById("material-auto-tag");
  const prevButton = document.getElementById("material-prev");
  const nextButton = document.getElementById("material-next");
  const modal = document.getElementById("material-modal");
  const modalTitle = document.getElementById("material-modal-title");
  const list = document.getElementById("material-list");
  const openModalButton = document.getElementById("open-material-modal");
  const closeModalButton = document.getElementById("close-material-modal");
  if (!form) return;

  const closeModal = () => {
    modal?.classList.add("hidden");
  };
  const fillMaterialForm = (source) => {
    [
      "name",
      "file_path",
      "material_type",
      "product_type",
      "scenario",
      "brand",
      "material_grade",
      "description",
      "recommended_script",
      "tags",
    ].forEach((fieldName) => {
      if (form.elements[fieldName]) {
        form.elements[fieldName].value = source[fieldName] || "";
      }
    });
  };
  const openModal = (material = null) => {
    form.reset();
    form.elements.id.value = material?.id || "";
    form.elements.review_id.value = "";
    if (modalTitle) {
      modalTitle.textContent = material ? "编辑素材" : "新增素材";
    }
    if (material) {
      fillMaterialForm(material);
    }
    modal?.classList.remove("hidden");
    form.querySelector("input[name='name']")?.focus();
  };

  openModalButton?.addEventListener("click", () => openModal());
  list?.addEventListener("click", (event) => {
    const button = event.target.closest(".edit-material");
    if (!button) return;
    openModal(JSON.parse(button.dataset.material));
  });
  closeModalButton?.addEventListener("click", closeModal);
  modal?.querySelectorAll("[data-close-modal]").forEach((node) => {
    node.addEventListener("click", closeModal);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(form).entries());
    const materialId = payload.id;
    delete payload.id;
    delete payload.review_id;
    const endpoint = materialId ? `/api/materials/${materialId}` : "/api/materials";
    const method = materialId ? "PATCH" : "POST";
    try {
      await apiRequest(endpoint, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      form.reset();
      closeModal();
      await loadMaterials(materialPaging.query, materialPaging.page);
      showToast(materialId ? "素材已更新" : "素材已新增");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  async function autoTagCurrentMaterial() {
    let filePath = form.elements.file_path.value.trim();
    const file = fileUpload?.files?.[0];
    if (!filePath && !file) {
      showToast("请先选择文件或填写文件路径", true);
      return false;
    }
    autoTagButton.disabled = true;
    autoTagButton.textContent = file && !fileUpload.dataset.uploadedPath ? "上传并打标中" : "打标中";
    try {
      if (file && !fileUpload.dataset.uploadedPath) {
        const formData = new FormData();
        formData.append("file", file);
        const uploadResult = await apiRequest("/api/materials/upload", {
          method: "POST",
          body: formData,
        });
        filePath = uploadResult.file_path;
        form.elements.file_path.value = filePath;
        fileUpload.dataset.uploadedPath = filePath;
      } else if (fileUpload?.dataset.uploadedPath) {
        filePath = fileUpload.dataset.uploadedPath;
        form.elements.file_path.value = filePath;
      }
      const suggestion = await apiRequest("/api/material-reviews/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_path: filePath,
          product_type: form.elements.product_type.value || "brake_pad",
          distribution_id: currentDistributionId,
        }),
      });
      fillMaterialForm({
        ...suggestion,
        name: form.elements.name.value || suggestion.name,
      });
      showToast("自动打标已填充，请确认后保存");
      return true;
    } catch (error) {
      showToast(error.message, true);
      return false;
    } finally {
      autoTagButton.disabled = false;
      autoTagButton.textContent = "自动打标";
    }
  }

  fileUpload?.addEventListener("change", async () => {
    const nameInput = form.elements.name;
    const file = fileUpload.files?.[0];
    fileUpload.dataset.uploadedPath = "";
    if (!file) return;
    if (!nameInput.value) {
      nameInput.value = file.name.replace(/\.[^.]+$/, "");
    }
    await autoTagCurrentMaterial();
  });

  autoTagButton?.addEventListener("click", async () => {
    await autoTagCurrentMaterial();
  });

  prevButton?.addEventListener("click", () => {
    loadMaterials(materialPaging.query, materialPaging.page - 1).catch((error) =>
      showToast(error.message, true)
    );
  });

  nextButton?.addEventListener("click", () => {
    loadMaterials(materialPaging.query, materialPaging.page + 1).catch((error) =>
      showToast(error.message, true)
    );
  });

  loadMaterials("", 1).catch((error) => showToast(error.message, true));
}

function statusLabel(status) {
  if (status === "confirmed") return "已确认";
  if (status === "disabled") return "已停用";
  return "草稿";
}

function statusClass(status) {
  if (status === "confirmed") return "confirmed";
  if (status === "disabled") return "disabled";
  return "draft";
}

function fillTemplateEditor(template) {
  document.getElementById("template-editor")?.classList.remove("hidden");
  document.getElementById("template-id").value = template.id;
  document.getElementById("template-scenario").value = template.scenario || "";
  document.getElementById("template-question").value = template.customer_question || "";
  document.getElementById("template-style").value = template.style_notes || "";
  document.getElementById("template-reply").value = template.standard_reply || "";
  document.getElementById("template-forbidden").value = template.forbidden_words || "";
  document.getElementById("template-material-ids").value =
    template.recommended_material_ids || "";

  const badge = document.getElementById("template-status");
  if (badge) {
    badge.textContent = statusLabel(template.status);
    badge.className = `status-badge ${statusClass(template.status)}`;
  }
}

async function loadTemplates(selectId = null) {
  const list = document.getElementById("template-list");
  if (!list) return;

  const items = await apiRequest("/api/templates");
  renderList(list, items, (item) => `
    <h3>${escapeHtml(item.scenario || "未命名场景")}</h3>
    <div class="card-meta">状态：<span class="status-badge ${statusClass(item.status)}">${statusLabel(item.status)}</span></div>
    <p>${escapeHtml(item.customer_question || "")}</p>
    <div class="card-actions">
      <button type="button" class="btn secondary" data-template-id="${escapeHtml(item.id)}">查看 / 编辑</button>
    </div>
  `);

  list.querySelectorAll("[data-template-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const template = items.find(
        (item) => String(item.id) === button.getAttribute("data-template-id"),
      );
      if (template) fillTemplateEditor(template);
    });
  });

  if (selectId) {
    const selected = items.find((item) => item.id === selectId);
    if (selected) fillTemplateEditor(selected);
  }
}

function initSpeechTemplatesPage() {
  const openSpeechImportButton = document.getElementById("open-speech-import-modal");
  const speechImportModal = document.getElementById("speech-import-modal");
  const closeSpeechImportButton = document.getElementById("close-speech-import-modal");
  const templateEditor = document.getElementById("template-editor");
  const closeTemplateEditorButton = document.getElementById("close-template-editor");
  const summarizeForm = document.getElementById("chat-summarize-form");
  const editForm = document.getElementById("template-edit-form");
  const confirmButton = document.getElementById("template-confirm");
  const disableButton = document.getElementById("template-disable");
  if (!summarizeForm) return;

  const closeSpeechImportModal = () => {
    speechImportModal?.classList.add("hidden");
  };
  const closeTemplateEditor = () => {
    templateEditor?.classList.add("hidden");
  };

  openSpeechImportButton?.addEventListener("click", () => {
    speechImportModal?.classList.remove("hidden");
    summarizeForm.source_chat?.focus();
  });
  closeSpeechImportButton?.addEventListener("click", closeSpeechImportModal);
  speechImportModal?.querySelectorAll("[data-close-speech-import-modal]").forEach((node) => {
    node.addEventListener("click", closeSpeechImportModal);
  });
  closeTemplateEditorButton?.addEventListener("click", closeTemplateEditor);
  templateEditor?.querySelectorAll("[data-close-template-editor]").forEach((node) => {
    node.addEventListener("click", closeTemplateEditor);
  });

  summarizeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const sourceChat = summarizeForm.source_chat.value.trim();
    if (!sourceChat) return;

    try {
      const template = await apiRequest("/api/templates/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_chat: sourceChat }),
      });
      fillTemplateEditor(template);
      await loadTemplates(template.id);
      summarizeForm.reset();
      closeSpeechImportModal();
      showToast("话术已生成，请确认后进入话术库");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  editForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const templateId = document.getElementById("template-id").value;
    const payload = {
      scenario: editForm.scenario.value,
      customer_question: editForm.customer_question.value,
      style_notes: editForm.style_notes.value,
      standard_reply: editForm.standard_reply.value,
      forbidden_words: editForm.forbidden_words.value,
      recommended_material_ids: editForm.recommended_material_ids.value,
    };

    try {
      const template = await apiRequest(`/api/templates/${templateId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      fillTemplateEditor(template);
      await loadTemplates(template.id);
      showToast("话术已保存");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  confirmButton?.addEventListener("click", async () => {
    const templateId = document.getElementById("template-id").value;
    if (!templateId) return;
    try {
      const template = await apiRequest(`/api/templates/${templateId}/confirm`, {
        method: "POST",
      });
      fillTemplateEditor(template);
      await loadTemplates(template.id);
      showToast("话术已确认，可用于问答");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  disableButton?.addEventListener("click", async () => {
    const templateId = document.getElementById("template-id").value;
    if (!templateId) return;
    try {
      const template = await apiRequest(`/api/templates/${templateId}/disable`, {
        method: "POST",
      });
      fillTemplateEditor(template);
      await loadTemplates(template.id);
      showToast("话术已停用");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  loadTemplates().catch((error) => showToast(error.message, true));
}
