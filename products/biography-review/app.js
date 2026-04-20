let bundle = null;
let state = null;
let currentPageIndex = 0;
let currentOcrMap = new Map();
let activePersonId = null;
let activePersonLabel = "";
let selectedBlockKeys = new Set();
let editingBiographyIndex = null;
let manualPickerOpen = false;
let saveTimer = null;
let manualPickerTarget = null;
let projects = [];
let crossPageMode = false;
let crossPageDirection = "next";
const SIDEBAR_STATE_KEY = "biography-review.sidebar-collapsed";
const LAST_PAGE_KEY_PREFIX = "biography-review.last-page.";
let resizeRenderTimer = null;

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`请求失败: ${url}`);
  return res.json();
}

function updateSaveStatus(text) {
  const el = document.getElementById("saveStatus");
  if (el) el.textContent = text;
}

function applySidebarState(collapsed) {
  const appRoot = document.getElementById("appRoot");
  const toggle = document.getElementById("sidebarToggle");
  if (!appRoot || !toggle) return;
  appRoot.classList.toggle("sidebar-collapsed", collapsed);
  toggle.textContent = collapsed ? "▶" : "◀";
  toggle.title = collapsed ? "展开侧栏" : "最小化侧栏";
  toggle.setAttribute("aria-label", toggle.title);
}

function lastPageKey(projectId) {
  return `${LAST_PAGE_KEY_PREFIX}${projectId || "default"}`;
}

function rememberCurrentPage() {
  if (!bundle || !currentPage()) return;
  window.localStorage.setItem(lastPageKey(bundle.project_id), String(currentPage().page));
}

function rememberedPageIndex(projectId, pages) {
  const stored = Number(window.localStorage.getItem(lastPageKey(projectId)));
  if (!Number.isFinite(stored)) return 0;
  const idx = pages.findIndex((page) => Number(page.page) === stored);
  return idx >= 0 ? idx : 0;
}

function initSidebarToggle() {
  const toggle = document.getElementById("sidebarToggle");
  const prefersCollapsed = window.localStorage.getItem(SIDEBAR_STATE_KEY) === "1";
  applySidebarState(prefersCollapsed);
  toggle.onclick = () => {
    const nextCollapsed = !document.getElementById("appRoot")?.classList.contains("sidebar-collapsed");
    applySidebarState(nextCollapsed);
    window.localStorage.setItem(SIDEBAR_STATE_KEY, nextCollapsed ? "1" : "0");
  };
}

async function saveState() {
  await fetchJson(`/api/save-state?project_id=${encodeURIComponent(bundle.project_id)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state),
  });
}

function scheduleAutoSave() {
  updateSaveStatus("正在自动保存...");
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try {
      await saveState();
      updateSaveStatus("已自动保存");
    } catch (error) {
      console.error(error);
      updateSaveStatus("自动保存失败");
    }
  }, 250);
}

function currentPage() {
  return bundle.pages[currentPageIndex];
}

function assetUrl(path) {
  if (!path) return "";
  if (path.startsWith("/")) return path;
  return `/${bundle.project_id}/${path.replace(/^\/+/, "")}`;
}

function blockKey(pageNo, index) {
  return `${pageNo}:${index}`;
}

function parseBlockKey(key) {
  const [pageNo, index] = String(key).split(":");
  return { pageNo: Number(pageNo), index: Number(index) };
}

function pageByNo(pageNo) {
  return bundle.pages.find((page) => Number(page.page) === Number(pageNo)) || null;
}

function displayedPages() {
  const current = currentPage();
  if (!crossPageMode) return [current];
  const adjacentIndex = crossPageDirection === "prev" ? currentPageIndex - 1 : currentPageIndex + 1;
  const adjacent = bundle.pages[adjacentIndex];
  if (!adjacent) return [current];
  return crossPageDirection === "prev" ? [adjacent, current] : [current, adjacent];
}

function ensurePageState(pageNo) {
  const key = String(pageNo);
  if (!state.pages[key]) {
    state.pages[key] = { deleted_ocr_indexes: [], title_assignments: {}, manual_matches: [], biographies: [] };
  }
  return state.pages[key];
}

function currentPageState() {
  return ensurePageState(currentPage().page);
}

function clearBiographyEditing() {
  editingBiographyIndex = null;
}

function renderStats() {
  const projectMeta = document.getElementById("projectMeta");
  const pageRange = (bundle.page_range || []).join("-");
  projectMeta.innerHTML = `
    <label class="project-select-label" for="projectSelect">项目</label>
    <select id="projectSelect" class="project-select">
      ${projects
        .map((item) => `<option value="${item.project_id}" ${item.project_id === bundle.project_id ? "selected" : ""}>${item.label}</option>`)
        .join("")}
    </select>
    <div class="project-range">页码 ${pageRange || "-"}</div>
  `;
  document.getElementById("projectSelect").onchange = async (event) => {
    await loadProject(event.target.value);
  };
  const stats = bundle.stats || {};
  document.getElementById("stats").innerHTML = `
    <div>标题候选：${stats.title_count ?? "-"}</div>
    <div>自动可挂接：${stats.auto_match_count ?? "-"}</div>
    <div>人工复核：${stats.manual_review_count ?? "-"}</div>
    <div>疑似噪音：${stats.noise_count ?? "-"}</div>
  `;
}

function renderPageList() {
  const container = document.getElementById("pageList");
  container.innerHTML = "";
  bundle.pages.forEach((page, index) => {
    const button = document.createElement("button");
    button.className = `page-button${index === currentPageIndex ? " active" : ""}`;
    const biographyCount = ensurePageState(page.page).biographies.length;
    button.textContent = `第 ${page.page} 页${biographyCount ? ` | 传记 ${biographyCount}` : ""}`;
    button.onclick = async () => {
      currentPageIndex = index;
      activePersonId = null;
      activePersonLabel = "";
      selectedBlockKeys = new Set();
      await renderCurrentPage();
    };
    container.appendChild(button);
  });
}

async function loadOcr(page) {
  return fetchJson(assetUrl(page.ocr_json));
}

async function loadDisplayedOcr() {
  const pages = displayedPages();
  const entries = await Promise.all(
    pages.map(async (page) => [String(page.page), await loadOcr(page)]),
  );
  currentOcrMap = new Map(entries);
}

function selectedBlockEntries() {
  const pageOrder = displayedPages().map((page) => Number(page.page));
  const pageRank = new Map(pageOrder.map((pageNo, idx) => [pageNo, idx]));
  const entries = [];
  selectedBlockKeys.forEach((key) => {
    const { pageNo, index } = parseBlockKey(key);
    const ocr = currentOcrMap.get(String(pageNo));
    const item = ocr?.ordered_items?.find((candidate) => Number(candidate.index) === index);
    if (!item) return;
    entries.push({ pageNo, ...item });
  });
  return entries.sort((a, b) => {
    const pageDelta = (pageRank.get(a.pageNo) ?? 0) - (pageRank.get(b.pageNo) ?? 0);
    if (pageDelta !== 0) return pageDelta;
    const ax = a.box[0];
    const bx = b.box[0];
    if (Math.abs(ax - bx) > 30) return bx - ax;
    return a.box[1] - b.box[1];
  });
}

function currentLinearText() {
  return selectedBlockEntries().map((item) => item.text).join("");
}

function collectedLinkedBlockKeys() {
  const linked = new Set();
  Object.entries(state.pages || {}).forEach(([pageNo, pageState]) => {
    (pageState.biographies || []).forEach((biography) => {
      if (Array.isArray(biography.selected_block_keys) && biography.selected_block_keys.length) {
        biography.selected_block_keys.forEach((key) => linked.add(String(key)));
        return;
      }
      (biography.selected_ocr_indexes || []).forEach((ocrIndex) => {
        linked.add(blockKey(pageNo, ocrIndex));
      });
    });
  });
  return linked;
}

function scorePersonSearch(name, query) {
  if (!query) return 1;
  if (name === query) return 100;
  if (name.includes(query)) return 80 - (name.length - query.length);
  let overlap = 0;
  for (const ch of query) {
    if (name.includes(ch)) overlap += 1;
  }
  return overlap > 0 ? overlap : -1;
}

function openManualPicker(target) {
  manualPickerTarget = target;
  manualPickerOpen = true;
  const searchInput = document.getElementById("manualSearch");
  if (searchInput) searchInput.value = target?.query || "";
  renderManualPicker();
}

function setActivePerson(personId, label) {
  activePersonId = personId;
  activePersonLabel = label;
  selectedBlockKeys = new Set();
  clearBiographyEditing();
  renderMatches();
  renderDraftPanel();
  renderViewers();
}

function renderViewers() {
  const container = document.getElementById("viewerMulti");
  const pages = displayedPages();
  const linkedBlockKeys = collectedLinkedBlockKeys();
  container.classList.toggle("cross-page", pages.length > 1);
  container.innerHTML = "";

  pages.forEach((page) => {
    const ocr = currentOcrMap.get(String(page.page));

    const card = document.createElement("div");
    card.className = "viewer-page";
    card.innerHTML = `<div class="viewer-page-title">第 ${page.page} 页</div>`;

    const wrap = document.createElement("div");
    wrap.className = "viewer-wrap";
    const canvas = document.createElement("div");
    canvas.className = "viewer-canvas";
    const image = document.createElement("img");
    image.className = "page-image";
    image.alt = `第 ${page.page} 页 OCR 校对图`;
    const overlay = document.createElement("div");
    overlay.className = "page-overlay";
    canvas.appendChild(image);
    canvas.appendChild(overlay);
    wrap.appendChild(canvas);
    card.appendChild(wrap);
    container.appendChild(card);

    const renderBoxes = () => {
      const naturalWidth = image.naturalWidth || 1;
      const naturalHeight = image.naturalHeight || 1;
      const shownWidth = image.clientWidth || naturalWidth;
      const shownHeight = image.clientHeight || naturalHeight;
      const scaleX = shownWidth / naturalWidth;
      const scaleY = shownHeight / naturalHeight;

      overlay.innerHTML = "";
      canvas.style.width = `${shownWidth}px`;
      canvas.style.height = `${shownHeight}px`;
      overlay.style.width = `${shownWidth}px`;
      overlay.style.height = `${shownHeight}px`;

      (ocr?.ordered_items || []).forEach((item) => {
        const key = blockKey(page.page, item.index);
        const isLinked = linkedBlockKeys.has(key);
        const hideLabel = isLinked || selectedBlockKeys.has(key);
        const x1 = item.box[0] * scaleX;
        const y1 = item.box[1] * scaleY;
        const x2 = item.box[2] * scaleX;
        const y2 = item.box[3] * scaleY;
        const box = document.createElement("div");
        box.className = "ocr-box";
        if (selectedBlockKeys.has(key)) box.classList.add("selected");
        if (isLinked) box.classList.add("linked");
        box.style.left = `${x1}px`;
        box.style.top = `${y1}px`;
        box.style.width = `${Math.max(24, x2 - x1)}px`;
        box.style.height = `${Math.max(24, y2 - y1)}px`;
        box.onclick = (event) => {
          event.stopPropagation();
          if (!activePersonId) {
            alert("先点击顶部人物卡片，把它设为当前人物。");
            return;
          }
          if (selectedBlockKeys.has(key)) selectedBlockKeys.delete(key);
          else selectedBlockKeys.add(key);
          renderDraftPanel();
          renderViewers();
        };

        if (!hideLabel) {
          const label = document.createElement("div");
          label.className = "ocr-label";
          label.textContent = `${item.index} ${item.text}`;
          box.appendChild(label);
        }
        overlay.appendChild(box);
      });
    };

    const scheduleRenderBoxes = () => {
      requestAnimationFrame(() => {
        requestAnimationFrame(renderBoxes);
      });
    };

    image.onload = scheduleRenderBoxes;
    image.src = assetUrl(page.raw_image);
    if (image.complete) scheduleRenderBoxes();
    if (typeof image.decode === "function") {
      image.decode().then(scheduleRenderBoxes).catch(() => {});
    }
  });
}

function renderManualPicker() {
  const picker = document.getElementById("manualPicker");
  const generationSelect = document.getElementById("manualGeneration");
  const searchInput = document.getElementById("manualSearch");
  const resultWrap = document.getElementById("manualSearchResults");

  picker.classList.toggle("hidden", !manualPickerOpen);
  if (!manualPickerOpen) return;

  const generations = [...new Set(bundle.person_catalog.map((item) => item.generation))].sort((a, b) => a - b);
  if (!generationSelect.dataset.ready) {
    generationSelect.innerHTML = generations.map((g) => `<option value="${g}">${g}世</option>`).join("");
    generationSelect.dataset.ready = "1";
  }
  const generation = Number(generationSelect.value || generations[0] || 1);
  if (!generationSelect.value && generations.length) generationSelect.value = String(generations[0]);
  const query = (searchInput.value || "").trim();

  const results = bundle.person_catalog
    .filter((item) => item.generation === generation)
    .map((item) => ({ ...item, score: scorePersonSearch(item.name, query) }))
    .filter((item) => item.score >= 0)
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name, "zh-Hans-CN"))
    .slice(0, 20);

  resultWrap.innerHTML = "";
  results.forEach((item) => {
    const row = document.createElement("div");
    row.className = "manual-search-item";
    row.innerHTML = `<div><strong>${item.name}</strong><div>${item.person_id} | ${item.generation}世</div></div>`;
    const btn = document.createElement("button");
    btn.textContent = "选择此人物";
    btn.onclick = () => {
      const label = manualPickerTarget?.ocrTitle ? `${manualPickerTarget.ocrTitle} -> ${item.name}` : `${item.name} -> ${item.name}`;
      if (manualPickerTarget?.type === "ocr") {
        currentPageState().title_assignments[String(manualPickerTarget.ocrIndex)] = {
          ocr_title: manualPickerTarget.ocrTitle,
          selected_person_id: item.person_id,
          match_status: "manual_override",
        };
        setActivePerson(item.person_id, label);
      } else {
        currentPageState().manual_matches.push({
          ocr_title: item.name,
          selected_person_id: item.person_id,
          match_status: "manual",
        });
        setActivePerson(item.person_id, label);
      }
      manualPickerTarget = null;
      manualPickerOpen = false;
      renderManualPicker();
      renderMatches();
      scheduleAutoSave();
    };
    row.appendChild(btn);
    resultWrap.appendChild(row);
  });
}

function renderMatches() {
  const pageState = currentPageState();
  const container = document.getElementById("matches");
  container.innerHTML = "";

  const renderedMatches = [
    ...currentPage().matches,
    ...(pageState.manual_matches || []).map((item, idx) => ({
      ...item,
      _manual: true,
      _manualIndex: idx,
      ocr_index: item.ocr_index ?? null,
      ocr_score: item.ocr_score ?? 1,
      match_status: item.match_status || "manual",
    })),
  ];

  renderedMatches.forEach((item) => {
    const chosenPersonId = item._manual
      ? pageState.manual_matches[item._manualIndex]?.selected_person_id
      : pageState.title_assignments?.[String(item.ocr_index)]?.selected_person_id ?? item.recommended_person_id;
    const chosenPerson = bundle.person_catalog.find((x) => x.person_id === chosenPersonId);

    const wrap = document.createElement("div");
    wrap.className = "match-item";
    if (chosenPersonId && activePersonId === chosenPersonId) wrap.classList.add("active");

    if (item._manual) {
      const head = document.createElement("div");
      head.innerHTML = `<strong>${item.ocr_title || "手动补录人物"}</strong><span class="status">manual</span>`;
      wrap.appendChild(head);
    } else {
      wrap.innerHTML = `
        <div class="match-title">
          <strong>${item.ocr_title}</strong>
          <span class="status">${item.match_status}</span>
        </div>
      `;
    }

    if (!item._manual) {
      const currentValue = pageState.title_assignments?.[String(item.ocr_index)]?.selected_person_id ?? item.recommended_person_id ?? "";
      if (!item.candidates?.length) {
        const empty = document.createElement("div");
        empty.textContent = "无候选";
        wrap.appendChild(empty);
      } else {
        item.candidates.forEach((candidate) => {
          const label = document.createElement("label");
          label.className = "candidate-option";
          const input = document.createElement("input");
          input.type = "radio";
          input.name = `title-${item.ocr_index}`;
          input.checked = currentValue === candidate.person_id;
          input.onchange = (event) => {
            event.stopPropagation();
            pageState.title_assignments[String(item.ocr_index)] = {
              ocr_title: item.ocr_title,
              selected_person_id: candidate.person_id,
              match_status: item.match_status,
            };
            renderMatches();
            scheduleAutoSave();
          };
          label.appendChild(input);
          label.append(` ${candidate.name} (${candidate.person_id}, ${candidate.generation}世)`);
          wrap.appendChild(label);
        });
      }
    }

    const overrideBtn = document.createElement("button");
    overrideBtn.textContent = item._manual ? "从人物库重选" : "从人物库补选人物";
    overrideBtn.onclick = (event) => {
      event.stopPropagation();
      openManualPicker({
        type: item._manual ? "manual" : "ocr",
        ocrIndex: item.ocr_index,
        ocrTitle: item.ocr_title,
        query: item.ocr_title || "",
      });
    };
    wrap.appendChild(overrideBtn);

    if (chosenPersonId) {
      wrap.onclick = () => setActivePerson(chosenPersonId, `${item.ocr_title} -> ${chosenPerson?.name || chosenPersonId}`);
    }

    if (item._manual) {
      const actions = document.createElement("div");
      actions.className = "match-actions";
      const clearBtn = document.createElement("button");
      clearBtn.textContent = "清空人物";
      clearBtn.onclick = (event) => {
        event.stopPropagation();
        pageState.manual_matches[item._manualIndex].selected_person_id = null;
        if (activePersonId === chosenPersonId) {
          activePersonId = null;
          activePersonLabel = "";
          selectedBlockKeys = new Set();
        }
        renderMatches();
        renderDraftPanel();
        renderViewers();
        scheduleAutoSave();
      };
      actions.appendChild(clearBtn);

      const deleteBtn = document.createElement("button");
      deleteBtn.textContent = "删除";
      deleteBtn.onclick = (event) => {
        event.stopPropagation();
        if (activePersonId === chosenPersonId) {
          activePersonId = null;
          activePersonLabel = "";
          selectedBlockKeys = new Set();
        }
        pageState.manual_matches.splice(item._manualIndex, 1);
        renderMatches();
        renderDraftPanel();
        renderViewers();
        scheduleAutoSave();
      };
      actions.appendChild(deleteBtn);
      wrap.appendChild(actions);
    }

    container.appendChild(wrap);
  });
}

function renderDraftPanel() {
  const pageState = currentPageState();
  document.getElementById("activePerson").textContent = activePersonId ? activePersonLabel : "未选择";
  const addButton = document.getElementById("addBiographyBtn");
  addButton.textContent = editingBiographyIndex === null ? "写入当前人物传记" : "更新当前人物传记";

  const selectedList = document.getElementById("selectedList");
  selectedList.innerHTML = "";
  selectedBlockEntries().forEach((item) => {
    const chip = document.createElement("div");
    chip.className = "selected-chip";
    chip.innerHTML = `<small>第${item.pageNo}页</small>${item.index} ${item.text}`;
    selectedList.appendChild(chip);
  });

  document.getElementById("linearText").value = currentLinearText();

  const container = document.getElementById("biographyList");
  container.innerHTML = "";
  if (!pageState.biographies.length) {
    container.textContent = "本页尚未保存传记记录";
    return;
  }
  pageState.biographies.forEach((item, index) => {
    const pageText = (item.source_pages || [currentPage().page]).map((pageNo) => `第${pageNo}页`).join(" + ");
    const div = document.createElement("div");
    div.className = "biography-item";
    if (editingBiographyIndex === index) div.classList.add("active");
    div.innerHTML = `
      <div><strong>${item.person_name || item.person_id || "未关联人物"}</strong></div>
      <div>来源页: ${pageText}</div>
      <div>块: ${(item.selected_block_keys || item.selected_ocr_indexes || []).join(", ")}</div>
      <div>拼接文本: ${item.linear_text || ""}</div>
    `;
    const useBtn = document.createElement("button");
    useBtn.textContent = "载入";
    useBtn.onclick = () => {
      activePersonId = item.person_id || null;
      activePersonLabel = item.person_name || item.person_id || "";
      editingBiographyIndex = index;
      const blockKeys = item.selected_block_keys || (item.selected_ocr_indexes || []).map((ocrIndex) => blockKey(currentPage().page, ocrIndex));
      selectedBlockKeys = new Set(blockKeys);
      renderMatches();
      renderDraftPanel();
      renderViewers();
    };
    div.appendChild(useBtn);

    const delBtn = document.createElement("button");
    delBtn.textContent = "删除";
    delBtn.onclick = () => {
      pageState.biographies.splice(index, 1);
      if (editingBiographyIndex === index) clearBiographyEditing();
      else if (editingBiographyIndex !== null && editingBiographyIndex > index) editingBiographyIndex -= 1;
      renderDraftPanel();
      renderPageList();
      renderViewers();
      scheduleAutoSave();
    };
    div.appendChild(delBtn);
    container.appendChild(div);
  });
}

function addBiography() {
  if (!activePersonId) {
    alert("先点击人物卡片，设为当前人物。");
    return;
  }
  const selectedEntries = selectedBlockEntries();
  const linear = currentLinearText().trim();
  if (!linear || !selectedEntries.length) {
    alert("当前人物还没有挂上传记文字块。");
    return;
  }
  const person = bundle.person_catalog.find((x) => x.person_id === activePersonId);
  const sourcePages = [...new Set(selectedEntries.map((item) => item.pageNo))];
  const biographyRecord = {
    person_id: activePersonId,
    person_name: person?.name || activePersonLabel,
    selected_block_keys: selectedEntries.map((item) => blockKey(item.pageNo, item.index)),
    selected_ocr_indexes: selectedEntries.filter((item) => item.pageNo === currentPage().page).map((item) => item.index).sort((a, b) => a - b),
    source_pages: sourcePages,
    linear_text: linear,
    baihua_text: "",
  };
  if (editingBiographyIndex !== null && currentPageState().biographies[editingBiographyIndex]) {
    currentPageState().biographies[editingBiographyIndex] = biographyRecord;
  } else {
    currentPageState().biographies.push(biographyRecord);
  }
  selectedBlockKeys = new Set();
  clearBiographyEditing();
  renderDraftPanel();
  renderPageList();
  renderViewers();
  scheduleAutoSave();
}

async function renderCurrentPage() {
  await loadDisplayedOcr();
  document.getElementById("pageTitle").textContent = `第 ${currentPage().page} 页`;
  document.getElementById("crossPageToggle").checked = crossPageMode;
  document.getElementById("crossPageDirection").value = crossPageDirection;
  document.getElementById("crossPageDirection").disabled = !crossPageMode;
  document.getElementById("prevPageBtn").disabled = currentPageIndex <= 0;
  document.getElementById("nextPageBtn").disabled = currentPageIndex >= bundle.pages.length - 1;
  renderPageList();
  renderManualPicker();
  renderMatches();
  renderDraftPanel();
  renderViewers();
  rememberCurrentPage();
}

async function loadProject(projectId) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  const payload = await fetchJson(`/api/review-data${query}`);
  bundle = payload.bundle;
  state = payload.state;
  projects = payload.projects || [];
  currentPageIndex = rememberedPageIndex(bundle.project_id, bundle.pages);
  currentOcrMap = new Map();
  activePersonId = null;
  activePersonLabel = "";
  selectedBlockKeys = new Set();
  clearBiographyEditing();
  manualPickerOpen = false;
  manualPickerTarget = null;
  crossPageMode = false;
  crossPageDirection = "next";
  renderStats();
  updateSaveStatus("自动保存");
  await renderCurrentPage();
}

async function main() {
  initSidebarToggle();
  window.addEventListener("resize", () => {
    if (!bundle) return;
    if (resizeRenderTimer) clearTimeout(resizeRenderTimer);
    resizeRenderTimer = setTimeout(() => {
      renderViewers();
    }, 80);
  });
  document.getElementById("addManualMatchBtn").onclick = () => {
    if (manualPickerOpen && manualPickerTarget?.type === "manual_new") {
      manualPickerOpen = false;
      manualPickerTarget = null;
      renderManualPicker();
      return;
    }
    manualPickerTarget = { type: "manual_new", query: "" };
    manualPickerOpen = true;
    renderManualPicker();
  };
  document.getElementById("manualGeneration").onchange = renderManualPicker;
  document.getElementById("manualSearch").oninput = renderManualPicker;
  document.getElementById("clearSelectionBtn").onclick = () => {
    selectedBlockKeys = new Set();
    clearBiographyEditing();
    renderDraftPanel();
    renderViewers();
  };
  document.getElementById("addBiographyBtn").onclick = addBiography;
  document.getElementById("crossPageToggle").onchange = async (event) => {
    crossPageMode = event.target.checked;
    selectedBlockKeys = new Set();
    clearBiographyEditing();
    await renderCurrentPage();
  };
  document.getElementById("crossPageDirection").onchange = async (event) => {
    crossPageDirection = event.target.value;
    selectedBlockKeys = new Set();
    clearBiographyEditing();
    await renderCurrentPage();
  };
  document.getElementById("prevPageBtn").onclick = async () => {
    if (currentPageIndex <= 0) return;
    currentPageIndex -= 1;
    activePersonId = null;
    activePersonLabel = "";
    selectedBlockKeys = new Set();
    clearBiographyEditing();
    await renderCurrentPage();
  };
  document.getElementById("nextPageBtn").onclick = async () => {
    if (currentPageIndex >= bundle.pages.length - 1) return;
    currentPageIndex += 1;
    activePersonId = null;
    activePersonLabel = "";
    selectedBlockKeys = new Set();
    clearBiographyEditing();
    await renderCurrentPage();
  };
  const initialProjectId = new URLSearchParams(window.location.search).get("project_id");
  await loadProject(initialProjectId);
}

main().catch((error) => {
  document.body.innerHTML = `<pre>${error.stack}</pre>`;
});
