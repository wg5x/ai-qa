async function apiRequest(url, options = {}) {
  const response = await fetch(url, options);
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

function renderAnswerSections(answer) {
  const references = (answer.references || [])
    .map((item) => `<li>${escapeHtml(typeof item === "string" ? item : JSON.stringify(item))}</li>`)
    .join("");
  const materials = (answer.recommended_materials || [])
    .map((item) => {
      const text =
        typeof item === "string"
          ? item
          : [item.name, item.file_path, item.description].filter(Boolean).join(" · ");
      return `<li>${escapeHtml(text)}</li>`;
    })
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
        body: JSON.stringify({ question }),
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
        const li = document.createElement("li");
        if (typeof item === "string") {
          li.textContent = item;
        } else {
          li.textContent = [item.name, item.file_path, item.description]
            .filter(Boolean)
            .join(" · ");
        }
        materials.appendChild(li);
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
  const quoteForm = document.getElementById("quote-import-form");
  const contractForm = document.getElementById("contract-import-form");
  const resultPanel = document.getElementById("import-result");
  const resultBody = document.getElementById("import-result-body");
  if (!quoteForm || !contractForm) return;

  const handleImport = (form, endpoint, label) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("button[type='submit']");
      button.disabled = true;
      button.textContent = "上传中...";

      try {
        const result = await uploadExcel(form, endpoint);
        resultPanel.classList.remove("hidden");
        resultBody.textContent = JSON.stringify(result, null, 2);
        showToast(`${label}导入完成`);
        form.reset();
      } catch (error) {
        showToast(error.message, true);
      } finally {
        button.disabled = false;
        button.textContent = label === "报价单" ? "上传报价单" : "上传合同";
      }
    });
  };

  handleImport(quoteForm, "/api/imports/quotes", "报价单");
  handleImport(contractForm, "/api/imports/contracts", "合同");
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
  const searchForm = document.getElementById("material-search-form");
  const refreshButton = document.getElementById("material-refresh");
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
  const openModal = (material = null) => {
    form.reset();
    form.elements.id.value = material?.id || "";
    if (modalTitle) modalTitle.textContent = material ? "编辑素材" : "新增素材";
    if (material) {
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
          form.elements[fieldName].value = material[fieldName] || "";
        }
      });
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

  searchForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = new FormData(searchForm).get("q")?.toString().trim() || "";
    try {
      await loadMaterials(query, 1);
    } catch (error) {
      showToast(error.message, true);
    }
  });

  refreshButton?.addEventListener("click", () => {
    if (searchForm) searchForm.reset();
    loadMaterials("", 1).catch((error) => showToast(error.message, true));
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
  const summarizeForm = document.getElementById("chat-summarize-form");
  const editForm = document.getElementById("template-edit-form");
  const confirmButton = document.getElementById("template-confirm");
  const disableButton = document.getElementById("template-disable");
  if (!summarizeForm) return;

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
      showToast("模板已生成，请确认后生效");
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
      showToast("模板已保存");
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
      showToast("模板已确认，可用于问答");
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
      showToast("模板已停用");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  loadTemplates().catch((error) => showToast(error.message, true));
}
