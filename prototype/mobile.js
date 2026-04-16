const apiBase =
  window.localStorage.getItem("genealogyApiBase") ||
  window.location.search.match(/[?&]api=([^&]+)/)?.[1] ||
  "http://127.0.0.1:8000";

const mobileScreenTitles = {
  search: "搜索首页",
  results: "查询结果页",
  detail: "人物详情页",
  branch: "支系展开页",
  contribute: "补充后代页",
};

const mobileState = {
  activeScreen: "search",
  query: "永昌",
  results: [],
  selectedPerson: null,
  previewBranch: null,
  fullBranch: null,
};

const mobileUpwardRange = document.getElementById("mobile-upward-range");
const mobileDownwardRange = document.getElementById("mobile-downward-range");
const mobileUpwardValue = document.getElementById("mobile-upward-value");
const mobileDownwardValue = document.getElementById("mobile-downward-value");
const mobileToggleDaughters = document.getElementById("mobile-toggle-daughters");
const mobileToggleSpouses = document.getElementById("mobile-toggle-spouses");
const mobilePreviewCanvas = document.getElementById("mobile-branch-preview");
const mobilePreviewSvg = document.getElementById("mobile-branch-preview-svg");
const mobileTreeCanvas = document.getElementById("mobile-tree-columns");
const mobileTreeSvg = document.getElementById("mobile-tree-columns-svg");
const mobileToggleDaughtersWrap = document.getElementById("mobile-toggle-daughters-wrap");
const mobileToggleSpousesWrap = document.getElementById("mobile-toggle-spouses-wrap");
const mobileDetailBranchNote = document.getElementById("mobile-detail-branch-note");
const mobileBranchScreenNote = document.getElementById("mobile-branch-screen-note");
const mobileRouteNote = document.getElementById("mobile-route-note");

function switchMobileScreen(screenName) {
  mobileState.activeScreen = screenName;
  document.getElementById("mobile-title").textContent = mobileScreenTitles[screenName];
  document.querySelectorAll(".mobile-screen").forEach((screen) => {
    screen.classList.toggle("active", screen.dataset.mobileView === screenName);
  });
  document.querySelectorAll("[data-mobile-screen]").forEach((button) => {
    if (button.classList.contains("bottom-link")) {
      button.classList.toggle("active", button.dataset.mobileScreen === screenName);
    }
  });
}

async function fetchJson(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Request failed: ${response.status}`);
  }
  return body;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function mobileSelectedRef() {
  return mobileState.selectedPerson
    ? `${mobileState.selectedPerson.person_source}/${mobileState.selectedPerson.person_ref}`
    : null;
}

function setMobileSearchStatus(message) {
  document.getElementById("mobile-search-status").textContent = message;
}

function setMobileContributeStatus(message) {
  document.getElementById("mobile-contribute-status").textContent = message;
}

function setMobileTreeNote(element, message) {
  element.hidden = !message;
  element.textContent = message || "";
}

function updateMobileBranchControlsVisibility() {
  const showModernFilters = mobileState.selectedPerson?.person_source === "modern";
  mobileToggleDaughtersWrap.hidden = !showModernFilters;
  mobileToggleSpousesWrap.hidden = !showModernFilters;
}

function updateMobileContributeHeading() {
  const name = mobileState.selectedPerson ? mobileState.selectedPerson.name : "当前人物";
  document.getElementById("mobile-contribute-heading").textContent = `为 ${name} 提交现代续修线索`;
}

function mobileRelationBadge(node) {
  if (node.node_type === "focus") return "本人";
  if (node.node_type === "spouse") return "配偶";
  if (node.node_type === "ancestor") return "上代";
  if (node.relation_type.includes("daughter")) return "女";
  if (node.relation_type.includes("son")) return "子";
  return "后代";
}

function mobileBuildTreeLayout(columns, options = {}) {
  const nodeWidth = options.nodeWidth ?? 72;
  const nodeHeight = options.nodeHeight ?? 154;
  const tagWidth = options.tagWidth ?? 48;
  const horizontalGap = options.horizontalGap ?? 14;
  const verticalGap = options.verticalGap ?? 24;
  const padding = options.padding ?? 14;
  const columnGap = options.columnGap ?? 26;

  const positions = new Map();
  const metrics = [];
  let currentY = padding;
  let maxWidth = 0;

  columns.forEach((column, columnIndex) => {
    const nodes = column.nodes || [];
    const rowWidth = nodes.length
      ? nodes.length * nodeWidth + Math.max(0, nodes.length - 1) * horizontalGap
      : nodeWidth;
    const contentX = padding + tagWidth + columnGap;
    maxWidth = Math.max(maxWidth, contentX + rowWidth + padding);

    metrics.push({
      columnIndex,
      label: column.label,
      generation: column.generation,
      rowY: currentY,
      contentX,
      rowHeight: nodeHeight,
    });

    nodes.forEach((node, nodeIndex) => {
      positions.set(`${columnIndex}:${node.person_source}:${node.person_ref}`, {
        x: contentX + nodeIndex * (nodeWidth + horizontalGap),
        y: currentY,
        width: nodeWidth,
        height: nodeHeight,
      });
    });

    currentY += nodeHeight + verticalGap;
  });

  return {
    positions,
    metrics,
    width: Math.max(maxWidth, 280),
    height: Math.max(currentY - verticalGap + padding, 220),
  };
}

function createSvgNode(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function drawMobileHangTree(svg, canvas, payload, options = {}) {
  svg.innerHTML = "";
  canvas.innerHTML = "";

  if (!payload || !payload.columns?.length) {
    canvas.innerHTML = `<div class="notice-card">当前人物附近暂无可展示的支系结构。</div>`;
    return;
  }

  const { positions, metrics, width, height } = mobileBuildTreeLayout(payload.columns, options);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.style.width = `${width}px`;
  svg.style.height = `${height}px`;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;

  metrics.forEach((row) => {
    const tag = document.createElement("div");
    tag.className = "mobile-generation-tag";
    tag.style.left = "12px";
    tag.style.top = `${row.rowY}px`;
    tag.style.height = `${row.rowHeight}px`;
    tag.innerHTML = `
      <strong>${escapeHtml(row.label)}</strong>
      <span>${escapeHtml(row.generation ? `第${row.generation}世` : "现代续修")}</span>
    `;
    canvas.appendChild(tag);
  });

  for (let index = 0; index < payload.columns.length - 1; index += 1) {
    const fromColumn = payload.columns[index];
    const toColumn = payload.columns[index + 1];
    if (!fromColumn.nodes?.length || !toColumn.nodes?.length) continue;

    const sourceNode =
      fromColumn.nodes.find((node) => node.node_type === "focus") ||
      fromColumn.nodes.find((node) => node.node_type === "ancestor") ||
      fromColumn.nodes[0];

    const source = positions.get(`${index}:${sourceNode.person_source}:${sourceNode.person_ref}`);
    if (!source) continue;

    const sourceX = source.x + source.width / 2;
    const sourceBottom = source.y + source.height;
    const targets = toColumn.nodes
      .map((node) => positions.get(`${index + 1}:${node.person_source}:${node.person_ref}`))
      .filter(Boolean);
    if (!targets.length) continue;

    const busY = sourceBottom + (options.busOffset ?? 14);
    const targetXs = targets.map((position) => position.x + position.width / 2);
    svg.appendChild(
      createSvgNode("path", {
        d: `M ${sourceX} ${sourceBottom} V ${busY}`,
        class: fromColumn.nodes.some((node) => node.node_type === "focus")
          ? "mobile-graph-edge-lite is-focus"
          : "mobile-graph-edge-lite",
      }),
    );
    if (targetXs.length > 1) {
      svg.appendChild(
        createSvgNode("path", {
          d: `M ${Math.min(...targetXs)} ${busY} H ${Math.max(...targetXs)}`,
          class: "mobile-graph-edge-lite",
        }),
      );
    }
    targets.forEach((target) => {
      const childX = target.x + target.width / 2;
      svg.appendChild(
        createSvgNode("path", {
          d: `M ${childX} ${busY} V ${target.y}`,
          class: "mobile-graph-edge-lite",
        }),
      );
    });
  }

  payload.columns.forEach((column, columnIndex) => {
    column.nodes.forEach((node) => {
      const position = positions.get(`${columnIndex}:${node.person_source}:${node.person_ref}`);
      if (!position) return;
      const card = document.createElement("div");
      card.className = [
        "mobile-tree-node-vertical",
        node.node_type === "focus" ? "is-focus" : "",
        node.node_type === "spouse" ? "is-spouse" : "",
        node.person_source === "modern" ? "is-modern" : "",
        node.relation_type.includes("daughter") ? "is-daughter" : "",
      ]
        .filter(Boolean)
        .join(" ");
      card.style.left = `${position.x}px`;
      card.style.top = `${position.y}px`;
      card.style.width = `${position.width}px`;
      card.style.height = `${position.height}px`;
      card.innerHTML = `
        <div class="vertical-name">${escapeHtml(node.name)}</div>
        <div class="vertical-meta">${escapeHtml(mobileRelationBadge(node))}</div>
      `;
      canvas.appendChild(card);
    });
  });
}

function renderMobileResults() {
  const list = document.getElementById("mobile-result-list");
  list.innerHTML = "";
  if (!mobileState.results.length) {
    list.innerHTML = `<div class="notice-card">没有找到匹配人物，请换一个姓名继续查询。</div>`;
    return;
  }
  mobileState.results.forEach((person) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "result-mobile-card";
    card.innerHTML = `
      <div class="result-mobile-top">
        <div>
          <strong>${escapeHtml(person.name)}</strong>
          <p class="helper-copy">父名：${escapeHtml(person.father_name || "未识别")}</p>
        </div>
        <span class="pill ${person.has_modern_extension ? "" : "muted"}">${escapeHtml(person.generation_label)}</span>
      </div>
      <div class="result-mobile-meta">
        <span>人物小传：${person.has_biography ? "有" : "无"}</span>
        <span>现代续修：${person.has_modern_extension ? "已补录" : "待补录"}</span>
      </div>
      <div class="result-mobile-actions">
        <span class="result-action-label">看小传</span>
        <span class="result-action-label">补充后代</span>
      </div>
    `;
    card.addEventListener("click", () => selectMobilePerson(person));
    list.appendChild(card);
  });
}

function renderMobileRoute(items) {
  const routeList = document.getElementById("mobile-route-list");
  routeList.innerHTML = "";
  items.forEach((item) => {
    const li = document.createElement("li");
    li.className = "timeline-item";
    li.innerHTML = `
      <div class="timeline-gen">${item.generation ? `${item.generation}世` : "现代"}</div>
      <div class="timeline-copy">
        <strong>${escapeHtml(item.name)}</strong>
        <p>${escapeHtml(item.note)}</p>
      </div>
    `;
    routeList.appendChild(li);
  });
}

async function renderMobileDetail() {
  if (!mobileState.selectedPerson) return;
  const ref = mobileSelectedRef();
  const [detail, biography, route, previewBranch] = await Promise.all([
    fetchJson(`/api/v1/persons/${ref}`),
    fetchJson(`/api/v1/persons/${ref}/biography`),
    fetchJson(`/api/v1/persons/${ref}/route`),
    fetchJson(`/api/v1/persons/${ref}/branch?up=1&down=1&include_daughters=true&include_spouses=true`),
  ]);
  const item = detail.item;
  document.getElementById("mobile-detail-name").textContent = item.name;
  document.getElementById("mobile-detail-generation").textContent = item.generation_label;
  document.getElementById("mobile-detail-father").textContent = `父名：${item.father_name || "未识别"}`;
  document.getElementById("mobile-detail-source").textContent = item.source_label;
  document.getElementById("mobile-detail-biography").textContent =
    biography.available
      ? biography.text_punctuated || biography.text_linear || biography.text_raw || "已收录人物小传"
      : "当前没有可展示的人物小传。";
  renderMobileRoute(route.items);
  setMobileTreeNote(
    mobileRouteNote,
    item.person_source === "historical" ? route.modern_extension_note : null,
  );
  mobileState.previewBranch = previewBranch;
  setMobileTreeNote(
    mobileDetailBranchNote,
    item.person_source === "historical" ? item.modern_extension_note : null,
  );
  drawMobileHangTree(mobilePreviewSvg, mobilePreviewCanvas, previewBranch, {
    nodeWidth: 66,
    nodeHeight: 148,
    tagWidth: 42,
    horizontalGap: 12,
    verticalGap: 22,
    columnGap: 24,
    busOffset: 12,
  });
}

async function renderMobileBranchScreen() {
  if (!mobileState.selectedPerson) {
    mobileTreeCanvas.innerHTML = `<div class="notice-card">请先在查询结果里选择一个人物。</div>`;
    mobileTreeSvg.innerHTML = "";
    return;
  }
  mobileUpwardValue.textContent = `${mobileUpwardRange.value} 代`;
  mobileDownwardValue.textContent = `${mobileDownwardRange.value} 代`;
  updateMobileBranchControlsVisibility();
  const ref = mobileSelectedRef();
  const branch = await fetchJson(
    `/api/v1/persons/${ref}/branch?up=${mobileUpwardRange.value}&down=${mobileDownwardRange.value}&include_daughters=${mobileToggleDaughters.checked}&include_spouses=${mobileToggleSpouses.checked}`,
  );
  mobileState.fullBranch = branch;
  setMobileTreeNote(
    mobileBranchScreenNote,
    mobileState.selectedPerson.person_source === "historical" ? branch.focus.modern_extension_note : null,
  );
  drawMobileHangTree(mobileTreeSvg, mobileTreeCanvas, branch, {
    nodeWidth: 72,
    nodeHeight: 154,
    tagWidth: 48,
    horizontalGap: 14,
    verticalGap: 24,
    columnGap: 26,
    busOffset: 14,
  });
}

async function searchMobilePersons() {
  const q = document.getElementById("mobile-search-input").value.trim();
  mobileState.query = q;
  if (!q) {
    setMobileSearchStatus("请输入姓名后再查询。");
    return;
  }
  setMobileSearchStatus("正在查询，请稍候...");
  const payload = await fetchJson(`/api/v1/search/persons?q=${encodeURIComponent(q)}&limit=20`);
  mobileState.results = payload.items;
  document.getElementById("mobile-results-heading").textContent = `“${q}” 共 ${payload.total} 条`;
  renderMobileResults();
  setMobileSearchStatus(`已找到 ${payload.total} 条可识别结果。`);
  switchMobileScreen("results");
}

async function selectMobilePerson(person) {
  mobileState.selectedPerson = person;
  updateMobileBranchControlsVisibility();
  updateMobileContributeHeading();
  await renderMobileDetail();
  switchMobileScreen("detail");
}

function buildMobileSubmissionPayload() {
  if (!mobileState.selectedPerson) {
    throw new Error("请先选中一个人物，再补充续修信息。");
  }
  return {
    target_person_ref: mobileState.selectedPerson.person_ref,
    target_person_source: mobileState.selectedPerson.person_source,
    submitter_name: "原型用户",
    submitter_contact: document.getElementById("mobile-contribute-contact").value.trim() || null,
    new_person: {
      display_name: document.getElementById("mobile-contribute-name").value.trim(),
      gender: document.getElementById("mobile-contribute-gender").value,
      birth_date: document.getElementById("mobile-contribute-birth-date").value || null,
      death_date: document.getElementById("mobile-contribute-death-date").value || null,
      surname: null,
      living_status: document.getElementById("mobile-contribute-living-status").value,
      education: document.getElementById("mobile-contribute-education").value.trim() || null,
      occupation: document.getElementById("mobile-contribute-occupation").value.trim() || null,
      bio: document.getElementById("mobile-contribute-notes").value.trim() || null,
    },
    relation: {
      relation_type: document.getElementById("mobile-contribute-relation").value,
    },
    notes: document.getElementById("mobile-contribute-notes").value.trim() || null,
  };
}

async function submitMobileContribution() {
  const payload = buildMobileSubmissionPayload();
  if (!payload.new_person.display_name) {
    setMobileContributeStatus("请先填写人物姓名。");
    return;
  }
  setMobileContributeStatus("正在提交到审核队列...");
  const result = await fetchJson("/api/v1/submissions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setMobileContributeStatus(`提交成功，审核编号 #${result.submission_id}，当前状态：${result.status}。`);
}

document.querySelectorAll("[data-mobile-screen]").forEach((button) => {
  button.addEventListener("click", async () => {
    const target = button.dataset.mobileScreen;
    if (target === "branch") {
      try {
        await renderMobileBranchScreen();
      } catch (error) {
        mobileTreeCanvas.innerHTML = `<div class="notice-card">支系图加载失败：${escapeHtml(error.message)}</div>`;
      }
    }
    switchMobileScreen(target);
  });
});

document.getElementById("mobile-search-submit").addEventListener("click", async () => {
  try {
    await searchMobilePersons();
  } catch (error) {
    setMobileSearchStatus(`查询失败：${error.message}`);
  }
});

document.getElementById("mobile-search-input").addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  try {
    await searchMobilePersons();
  } catch (error) {
    setMobileSearchStatus(`查询失败：${error.message}`);
  }
});

document.getElementById("mobile-contribute-submit").addEventListener("click", async () => {
  try {
    await submitMobileContribution();
  } catch (error) {
    setMobileContributeStatus(`提交失败：${error.message}`);
  }
});

[mobileUpwardRange, mobileDownwardRange, mobileToggleDaughters, mobileToggleSpouses].forEach((control) => {
  control.addEventListener("input", async () => {
    mobileUpwardValue.textContent = `${mobileUpwardRange.value} 代`;
    mobileDownwardValue.textContent = `${mobileDownwardRange.value} 代`;
    if (mobileState.activeScreen !== "branch" || !mobileState.selectedPerson) return;
    try {
      await renderMobileBranchScreen();
    } catch (error) {
      mobileTreeCanvas.innerHTML = `<div class="notice-card">支系图加载失败：${escapeHtml(error.message)}</div>`;
    }
  });
});

setMobileSearchStatus(`当前 API：${apiBase}。默认示例词可用：永昌`);
renderMobileResults();
updateMobileContributeHeading();
updateMobileBranchControlsVisibility();
mobileUpwardValue.textContent = `${mobileUpwardRange.value} 代`;
mobileDownwardValue.textContent = `${mobileDownwardRange.value} 代`;
