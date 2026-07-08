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

function initQAPage() {
  const form = document.getElementById("qa-form");
  const resultPanel = document.getElementById("qa-result");
  const copyButton = document.getElementById("copy-reply");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = form.question.value.trim();
    if (!question) return;

    const submitButton = document.getElementById("qa-submit");
    submitButton.disabled = true;
    submitButton.textContent = "生成中...";

    try {
      const answer = await apiRequest("/api/qa/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

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
      showToast("回答已生成");
    } catch (error) {
      showToast(error.message, true);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "提交问题";
    }
  });

  copyButton?.addEventListener("click", async () => {
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
  `;
}

async function loadMaterials(query = "") {
  const list = document.getElementById("material-list");
  if (!list) return;

  const url = query
    ? `/api/materials/search?q=${encodeURIComponent(query)}`
    : "/api/materials";
  const items = await apiRequest(url);
  renderList(list, items, materialCard);
}

function initMaterialsPage() {
  const form = document.getElementById("material-form");
  const searchForm = document.getElementById("material-search-form");
  const refreshButton = document.getElementById("material-refresh");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(form).entries());
    try {
      await apiRequest("/api/materials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      form.reset();
      await loadMaterials();
      showToast("素材已新增");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  searchForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = new FormData(searchForm).get("q")?.toString().trim() || "";
    try {
      await loadMaterials(query);
    } catch (error) {
      showToast(error.message, true);
    }
  });

  refreshButton?.addEventListener("click", () => {
    if (searchForm) searchForm.reset();
    loadMaterials().catch((error) => showToast(error.message, true));
  });

  loadMaterials().catch((error) => showToast(error.message, true));
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
