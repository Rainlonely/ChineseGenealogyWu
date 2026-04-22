const apiBase =
  window.localStorage.getItem("genealogyApiBase") ||
  window.location.search.match(/[?&]api=([^&]+)/)?.[1] ||
  "";
let readOnlyMode = false;

const state = {
  activeScreen: "search",
  query: "永昌",
  results: [],
  selectedPerson: null,
  previewBranch: null,
  fullBranch: null,
};
const historyStateKey = "__prototypeRouteV1";
const routeScreenKey = "screen";
const routePersonSourceKey = "person_source";
const routePersonRefKey = "person_ref";

const resultList = document.getElementById("result-list");
const routeList = document.getElementById("route-list");
const branchPreview = document.getElementById("branch-preview");
const branchPreviewSvg = document.getElementById("branch-preview-svg");
const treeColumns = document.getElementById("tree-columns");
const treeColumnsSvg = document.getElementById("tree-columns-svg");
const upwardRange = document.getElementById("upward-range");
const downwardRange = document.getElementById("downward-range");
const upwardValue = document.getElementById("upward-value");
const downwardValue = document.getElementById("downward-value");
const toggleDaughters = document.getElementById("toggle-daughters");
const toggleSpouses = document.getElementById("toggle-spouses");
const toggleDaughtersWrap = document.getElementById("toggle-daughters-wrap");
const toggleSpousesWrap = document.getElementById("toggle-spouses-wrap");
const detailBranchNote = document.getElementById("detail-branch-note");
const branchScreenNote = document.getElementById("branch-screen-note");
const routeNote = document.getElementById("route-note");
const correctionTargetName = document.getElementById("correction-target-name");
const correctionCurrentValue = document.getElementById("correction-current-value");
const correctionProposedValue = document.getElementById("correction-proposed-value");
const correctionContact = document.getElementById("correction-contact");
const correctionReason = document.getElementById("correction-reason");
const correctionStatus = document.getElementById("correction-status");

function switchScreen(screenName) {
  state.activeScreen = screenName;
  document.querySelectorAll(".screen").forEach((screen) => {
    screen.classList.toggle("active", screen.dataset.screen === screenName);
  });
  document.querySelectorAll(".nav-link").forEach((link) => {
    link.classList.toggle("active", link.dataset.screenTarget === screenName);
  });
}

function isSamePerson(left, right) {
  if (!left || !right) return false;
  return left.person_source === right.person_source && left.person_ref === right.person_ref;
}

function snapshotPerson(person) {
  if (!person) return null;
  return {
    person_source: person.person_source,
    person_ref: person.person_ref,
    name: person.name || "",
    father_name: person.father_name || "",
    generation_label: person.generation_label || "",
    has_biography: Boolean(person.has_biography),
    has_modern_extension: Boolean(person.has_modern_extension),
  };
}

function buildRouteUrl(routeState) {
  const url = new URL(window.location.href);
  const params = url.searchParams;
  if (routeState.screen) {
    params.set(routeScreenKey, routeState.screen);
  } else {
    params.delete(routeScreenKey);
  }
  if (routeState.screen === "detail" && routeState.selectedPerson) {
    params.set(routePersonSourceKey, routeState.selectedPerson.person_source);
    params.set(routePersonRefKey, routeState.selectedPerson.person_ref);
  } else {
    params.delete(routePersonSourceKey);
    params.delete(routePersonRefKey);
  }
  const query = params.toString();
  return `${url.pathname}${query ? `?${query}` : ""}${url.hash}`;
}

function buildRouteState({ screen = state.activeScreen, selectedPerson = state.selectedPerson } = {}) {
  return {
    [historyStateKey]: true,
    screen,
    selectedPerson: screen === "detail" ? snapshotPerson(selectedPerson) : null,
  };
}

function pushRouteState(payload) {
  const nextState = buildRouteState(payload);
  const current = history.state;
  if (current?.[historyStateKey]) {
    if (current.screen === nextState.screen) {
      if (nextState.screen !== "detail" || isSamePerson(current.selectedPerson, nextState.selectedPerson)) {
        return;
      }
    }
  }
  history.pushState(nextState, "", buildRouteUrl(nextState));
}

function replaceRouteState(payload) {
  const nextState = buildRouteState(payload);
  history.replaceState(nextState, "", buildRouteUrl(nextState));
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

function displayedApiBase() {
  return apiBase || window.location.origin;
}

function applyReadOnlyMode() {
  readOnlyMode = true;
  document.querySelectorAll('[data-screen-target="correction"], [data-screen-target="contribute"]').forEach((node) => {
    node.hidden = true;
  });
  document.querySelectorAll('[data-go-screen="correction"], [data-go-screen="contribute"]').forEach((node) => {
    node.hidden = true;
  });
  const correctionSubmit = document.getElementById("correction-submit");
  const contributeSubmit = document.getElementById("contribute-submit");
  if (correctionSubmit) correctionSubmit.disabled = true;
  if (contributeSubmit) contributeSubmit.disabled = true;
  setContributeStatus("当前部署为只读模式，线上不接受新增编辑。");
  setCorrectionStatus("当前部署为只读模式，线上不接受姓名勘误提交。");
}

function selectedRef() {
  return state.selectedPerson
    ? `${state.selectedPerson.person_source}/${state.selectedPerson.person_ref}`
    : null;
}

function setSearchStatus(message) {
  document.getElementById("search-status").textContent = message;
}

function setContributeStatus(message) {
  document.getElementById("contribute-status").textContent = message;
}

function setCorrectionStatus(message) {
  correctionStatus.textContent = message;
}

function setTreeNote(element, message) {
  element.hidden = !message;
  element.textContent = message || "";
}

function buildPersonRef(personSource, personRef, fallback = {}) {
  return {
    person_source: personSource,
    person_ref: personRef,
    name: fallback.name || personRef,
    father_name: fallback.father_name || "",
    generation_label: fallback.generation_label || "",
    has_biography: Boolean(fallback.has_biography),
    has_modern_extension: Boolean(fallback.has_modern_extension),
  };
}

async function jumpToPerson(personSource, personRef, fallback = {}) {
  if (!personSource || !personRef) return;
  const target = buildPersonRef(personSource, personRef, fallback);
  await selectPerson(target);
}

function updateBranchControlsVisibility() {
  const showModernFilters = state.selectedPerson?.person_source === "modern";
  toggleDaughtersWrap.hidden = !showModernFilters;
  toggleSpousesWrap.hidden = !showModernFilters;
}

function updateContributeHeading() {
  const name = state.selectedPerson ? state.selectedPerson.name : "当前人物";
  document.getElementById("contribute-heading").textContent = `为 ${name} 提交现代续修信息`;
}

function updateCorrectionForm() {
  const name = state.selectedPerson ? state.selectedPerson.name : "当前人物";
  document.getElementById("correction-heading").textContent = `为 ${name} 提交姓名校对申请`;
  correctionTargetName.value = state.selectedPerson
    ? `${state.selectedPerson.name}（${state.selectedPerson.generation_label}）`
    : "";
  correctionCurrentValue.value = state.selectedPerson ? state.selectedPerson.name : "";
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

function relationBadge(node) {
  if (node.node_type === "focus") return "本人";
  if (node.node_type === "spouse") return "配偶";
  if (node.node_type === "ancestor") return "上代";
  if (node.relation_type.includes("daughter")) return "女";
  if (node.relation_type.includes("son")) return "子";
  return "后代";
}

function describeColumn(column) {
  if (column.generation) {
    return `${column.label} / 第${column.generation}世`;
  }
  return column.label;
}

function buildTreeLayout(columns, options = {}) {
  const nodeWidth = options.nodeWidth ?? 84;
  const nodeHeight = options.nodeHeight ?? 176;
  const tagWidth = options.tagWidth ?? 56;
  const horizontalGap = options.horizontalGap ?? 24;
  const verticalGap = options.verticalGap ?? 34;
  const padding = options.padding ?? 18;
  const columnGap = options.columnGap ?? 48;

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
    const rowHeight = nodeHeight;
    const rowWidthWithMeta = contentX + rowWidth + padding;
    maxWidth = Math.max(maxWidth, rowWidthWithMeta);

    metrics.push({
      columnIndex,
      label: column.label,
      generation: column.generation,
      rowY: currentY,
      contentX,
      rowWidth,
      rowHeight,
      nodeCount: nodes.length,
    });

    nodes.forEach((node, nodeIndex) => {
      const x = contentX + nodeIndex * (nodeWidth + horizontalGap);
      positions.set(`${columnIndex}:${node.person_source}:${node.person_ref}`, {
        x,
        y: currentY,
        width: nodeWidth,
        height: nodeHeight,
      });
    });

    currentY += rowHeight + verticalGap;
  });

  return {
    positions,
    metrics,
    width: Math.max(maxWidth, 360),
    height: Math.max(currentY - verticalGap + padding, 220),
  };
}

function createSvgNode(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function drawHangTree(svg, canvas, payload, options = {}) {
  svg.innerHTML = "";
  canvas.innerHTML = "";

  if (!payload || !payload.columns?.length) {
    canvas.innerHTML = `<div class="notice-box">当前人物附近暂无可展示的支系结构。</div>`;
    return;
  }

  const { positions, metrics, width, height } = buildTreeLayout(payload.columns, options);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.style.width = `${width}px`;
  svg.style.height = `${height}px`;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;

  metrics.forEach((row) => {
    const tag = document.createElement("div");
    tag.className = "tree-generation-tag";
    tag.style.left = "18px";
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

    const sourceKey = `${index}:${sourceNode.person_source}:${sourceNode.person_ref}`;
    const sourcePosition = positions.get(sourceKey);
    if (!sourcePosition) continue;

    const sourceX = sourcePosition.x + sourcePosition.width / 2;
    const sourceBottom = sourcePosition.y + sourcePosition.height;
    const targetPositions = toColumn.nodes
      .map((node) => positions.get(`${index + 1}:${node.person_source}:${node.person_ref}`))
      .filter(Boolean);
    if (!targetPositions.length) continue;

    const topPoints = targetPositions.map((position) => position.x + position.width / 2);
    const busY = sourceBottom + (options.busOffset ?? 18);
    const busClass = fromColumn.nodes.some((node) => node.node_type === "focus")
      ? "graph-edge-lite is-focus"
      : "graph-edge-lite";

    svg.appendChild(
      createSvgNode("path", {
        d: `M ${sourceX} ${sourceBottom} V ${busY}`,
        class: busClass,
      }),
    );

    if (topPoints.length > 1) {
      svg.appendChild(
        createSvgNode("path", {
          d: `M ${Math.min(...topPoints)} ${busY} H ${Math.max(...topPoints)}`,
          class: "graph-edge-lite",
        }),
      );
    }

    targetPositions.forEach((position) => {
      const childX = position.x + position.width / 2;
      svg.appendChild(
        createSvgNode("path", {
          d: `M ${childX} ${busY} V ${position.y}`,
          class: "graph-edge-lite",
        }),
      );
    });
  }

  payload.columns.forEach((column, columnIndex) => {
    column.nodes.forEach((node) => {
      const key = `${columnIndex}:${node.person_source}:${node.person_ref}`;
      const position = positions.get(key);
      if (!position) return;

      const card = document.createElement("div");
      const relation = relationBadge(node);
      card.className = [
        "tree-node-vertical",
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
        <div class="vertical-meta">${escapeHtml(relation)}</div>
      `;
      card.style.cursor = "pointer";
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-label", `查看人物 ${node.name} 详情`);
      const onJump = async () => {
        try {
          await jumpToPerson(node.person_source, node.person_ref, {
            name: node.name,
          });
        } catch (error) {
          setSearchStatus(`人物详情加载失败：${error.message}`);
        }
      };
      card.addEventListener("click", () => {
        void onJump();
      });
      card.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        void onJump();
      });
      canvas.appendChild(card);
    });
  });
}

function renderResults() {
  resultList.innerHTML = "";
  if (!state.results.length) {
    resultList.innerHTML = `<div class="notice-box">没有找到匹配人物，请换一个姓名继续查询。</div>`;
    return;
  }

  state.results.forEach((person) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "result-card";
    card.innerHTML = `
      <span class="result-name">
        <strong>${escapeHtml(person.name)}</strong>
        <span class="cell-label">整行可点击查看人物详情</span>
      </span>
      <span class="result-cell">
        <span class="cell-label">父名</span>
        <span>${escapeHtml(person.father_name || "未识别")}</span>
      </span>
      <span class="result-cell">
        <span class="cell-label">世代</span>
        <span>${escapeHtml(person.generation_label)}</span>
      </span>
      <span class="result-cell">
        <span class="cell-label">人物小传</span>
        <span class="tag ${person.has_biography ? "success" : "muted"}">${person.has_biography ? "有" : "无"}</span>
      </span>
      <span class="result-cell">
        <span class="cell-label">现代续修</span>
        <span class="tag ${person.has_modern_extension ? "" : "muted"}">${person.has_modern_extension ? "已补录" : "待补录"}</span>
      </span>
    `;
    card.addEventListener("click", () => selectPerson(person));

    const actions = document.createElement("div");
    actions.className = "result-inline-actions";

    const bioButton = document.createElement("button");
    bioButton.type = "button";
    bioButton.className = "inline-action";
    bioButton.textContent = "看小传";
    bioButton.addEventListener("click", (event) => {
      event.stopPropagation();
      selectPerson(person);
    });

    const contributeButton = document.createElement("button");
    contributeButton.type = "button";
    contributeButton.className = "inline-action";
    contributeButton.textContent = "补充后代";
    contributeButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await selectPerson(person);
      switchScreen("contribute");
    });

    const correctionButton = document.createElement("button");
    correctionButton.type = "button";
    correctionButton.className = "inline-action";
    correctionButton.textContent = "姓名勘误";
    correctionButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await selectPerson(person);
      switchScreen("correction");
    });

    actions.appendChild(bioButton);
    actions.appendChild(correctionButton);
    actions.appendChild(contributeButton);
    card.appendChild(actions);
    resultList.appendChild(card);
  });
}

function renderRoute(items) {
  routeList.innerHTML = "";
  items.forEach((item) => {
    const entry = document.createElement("li");
    entry.style.cursor = "pointer";
    entry.tabIndex = 0;
    entry.setAttribute("role", "button");
    entry.setAttribute("aria-label", `查看人物 ${item.name} 详情`);
    entry.innerHTML = `
      <div class="route-generation">${item.generation ? `${item.generation}世` : "现代"}</div>
      <div class="route-person">
        <strong>${escapeHtml(item.name)}</strong>
        <div class="preview-meta">${escapeHtml(item.note)}</div>
      </div>
    `;
    const onJump = async () => {
      try {
        await jumpToPerson(item.person_source, item.person_ref, {
          name: item.name,
          generation_label: item.generation ? `第${item.generation}世` : "现代续修",
        });
      } catch (error) {
        setSearchStatus(`人物详情加载失败：${error.message}`);
      }
    };
    entry.addEventListener("click", () => {
      void onJump();
    });
    entry.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      void onJump();
    });
    routeList.appendChild(entry);
  });
}

async function renderDetail() {
  if (!state.selectedPerson) return;
  const ref = selectedRef();
  const [detail, biography, route, previewBranch] = await Promise.all([
    fetchJson(`/api/v1/persons/${ref}`),
    fetchJson(`/api/v1/persons/${ref}/biography`),
    fetchJson(`/api/v1/persons/${ref}/route`),
    fetchJson(`/api/v1/persons/${ref}/branch?up=1&down=1&include_daughters=true&include_spouses=true`),
  ]);

  const item = detail.item;
  state.selectedPerson = {
    ...state.selectedPerson,
    person_source: item.person_source,
    person_ref: item.person_ref,
    name: item.name,
    father_name: item.father_name,
    generation_label: item.generation_label,
  };
  document.getElementById("detail-name").textContent = item.name;
  document.getElementById("detail-generation").textContent = item.generation_label;
  document.getElementById("detail-father").textContent = `父名：${item.father_name || "未识别"}`;
  document.getElementById("detail-source").textContent = `数据来源：${item.source_label}`;
  const originalText = biography.available
    ? biography.text_punctuated || biography.text_linear || biography.text_raw || "已收录人物小传。"
    : "当前没有可展示的人物小传。";
  const baihuaText = biography.available
    ? biography.text_baihua || "当前暂无白话文版本。"
    : "当前没有可展示的白话文。";
  document.getElementById("detail-biography-baihua").textContent = baihuaText;
  document.getElementById("detail-biography").textContent = originalText;

  renderRoute(route.items);
  setTreeNote(
    routeNote,
    item.person_source === "historical" ? route.modern_extension_note : null,
  );
  state.previewBranch = previewBranch;
  setTreeNote(
    detailBranchNote,
    item.person_source === "historical" ? item.modern_extension_note : null,
  );
  drawHangTree(branchPreviewSvg, branchPreview, previewBranch, {
    nodeWidth: 78,
    nodeHeight: 162,
    tagWidth: 50,
    horizontalGap: 18,
    verticalGap: 28,
    columnGap: 32,
    busOffset: 16,
  });
}

async function renderBranchScreen() {
  if (!state.selectedPerson) {
    treeColumns.innerHTML = `<div class="notice-box">请先在查询结果里选择一个人物。</div>`;
    treeColumnsSvg.innerHTML = "";
    return;
  }
  upwardValue.textContent = `${upwardRange.value} 代`;
  downwardValue.textContent = `${downwardRange.value} 代`;
  updateBranchControlsVisibility();
  const ref = selectedRef();
  const branch = await fetchJson(
    `/api/v1/persons/${ref}/branch?up=${upwardRange.value}&down=${downwardRange.value}&include_daughters=${toggleDaughters.checked}&include_spouses=${toggleSpouses.checked}`,
  );
  state.fullBranch = branch;
  setTreeNote(
    branchScreenNote,
    state.selectedPerson.person_source === "historical" ? branch.focus.modern_extension_note : null,
  );
  drawHangTree(treeColumnsSvg, treeColumns, branch, {
    nodeWidth: 86,
    nodeHeight: 182,
    tagWidth: 58,
    horizontalGap: 24,
    verticalGap: 34,
    columnGap: 44,
    busOffset: 20,
  });
}

async function searchPersons() {
  const q = document.getElementById("search-input").value.trim();
  state.query = q;
  if (!q) {
    setSearchStatus("请输入姓名后再查询。");
    return;
  }
  setSearchStatus("正在查询，请稍候...");
  const payload = await fetchJson(`/api/v1/search/persons?q=${encodeURIComponent(q)}&limit=20`);
  state.results = payload.items;
  document.getElementById("results-heading").textContent = `“${q}” 共 ${payload.total} 条结果`;
  renderResults();
  setSearchStatus(`已找到 ${payload.total} 条可识别结果。`);
  switchScreen("results");
  pushRouteState({ screen: "results", selectedPerson: null });
}

async function selectPerson(person, options = {}) {
  const { pushHistory = true } = options;
  state.selectedPerson = person;
  updateBranchControlsVisibility();
  updateContributeHeading();
  updateCorrectionForm();
  await renderDetail();
  switchScreen("detail");
  if (pushHistory) {
    pushRouteState({ screen: "detail", selectedPerson: state.selectedPerson });
  }
}

async function resolveRoutePerson(personState) {
  if (!personState?.person_source || !personState?.person_ref) return null;
  const found = state.results.find((item) => isSamePerson(item, personState));
  if (found) return found;
  return {
    person_source: personState.person_source,
    person_ref: personState.person_ref,
    name: personState.name || personState.person_ref,
    father_name: personState.father_name || "",
    generation_label: personState.generation_label || "",
    has_biography: Boolean(personState.has_biography),
    has_modern_extension: Boolean(personState.has_modern_extension),
  };
}

async function applyRouteState(routeState) {
  if (routeState?.screen === "detail" && routeState.selectedPerson) {
    const person = await resolveRoutePerson(routeState.selectedPerson);
    if (person) {
      await selectPerson(person, { pushHistory: false });
      replaceRouteState({ screen: "detail", selectedPerson: state.selectedPerson });
      return;
    }
  }
  switchScreen(routeState?.screen || "search");
}

function parseRouteFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const screen = params.get(routeScreenKey) || "search";
  const personSource = params.get(routePersonSourceKey);
  const personRef = params.get(routePersonRefKey);
  if (screen === "detail" && personSource && personRef) {
    return buildRouteState({
      screen,
      selectedPerson: {
        person_source: personSource,
        person_ref: personRef,
      },
    });
  }
  return buildRouteState({ screen, selectedPerson: null });
}

function buildCorrectionPayload() {
  if (!state.selectedPerson) {
    throw new Error("请先选中一个人物，再提交姓名勘误。");
  }
  return {
    target_person_ref: state.selectedPerson.person_ref,
    target_person_source: state.selectedPerson.person_source,
    submitter_name: "原型用户",
    submitter_contact: correctionContact.value.trim() || null,
    field_name: "name",
    current_value: correctionCurrentValue.value.trim() || state.selectedPerson.name,
    proposed_value: correctionProposedValue.value.trim(),
    reason: correctionReason.value.trim(),
    evidence_note: correctionReason.value.trim() || null,
  };
}

function buildSubmissionPayload() {
  if (!state.selectedPerson) {
    throw new Error("请先选中一个人物，再补充续修信息。");
  }
  return {
    target_person_ref: state.selectedPerson.person_ref,
    target_person_source: state.selectedPerson.person_source,
    submitter_name: "原型用户",
    submitter_contact: document.getElementById("contribute-contact").value.trim() || null,
    new_person: {
      display_name: document.getElementById("contribute-name").value.trim(),
      gender: document.getElementById("contribute-gender").value,
      birth_date: document.getElementById("contribute-birth-date").value || null,
      death_date: document.getElementById("contribute-death-date").value || null,
      surname: null,
      living_status: document.getElementById("contribute-living-status").value,
      education: document.getElementById("contribute-education").value.trim() || null,
      occupation: document.getElementById("contribute-occupation").value.trim() || null,
      bio: document.getElementById("contribute-notes").value.trim() || null,
    },
    relation: {
      relation_type: document.getElementById("contribute-relation").value,
    },
    notes: document.getElementById("contribute-notes").value.trim() || null,
  };
}

async function submitContribution() {
  if (readOnlyMode) {
    setContributeStatus("当前部署为只读模式，线上不接受新增编辑。");
    return;
  }
  const payload = buildSubmissionPayload();
  if (!payload.new_person.display_name) {
    setContributeStatus("请先填写人物姓名。");
    return;
  }
  setContributeStatus("正在提交到审核队列...");
  const result = await fetchJson("/api/v1/submissions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setContributeStatus(`提交成功，审核编号 #${result.submission_id}，当前状态：${result.status}。`);
}

async function submitCorrection() {
  if (readOnlyMode) {
    setCorrectionStatus("当前部署为只读模式，线上不接受姓名勘误提交。");
    return;
  }
  const payload = buildCorrectionPayload();
  if (!payload.proposed_value) {
    setCorrectionStatus("请先填写建议更正后的姓名。");
    return;
  }
  if (!payload.reason) {
    setCorrectionStatus("请填写更正依据，便于后台核对。");
    return;
  }
  setCorrectionStatus("正在提交姓名勘误申请...");
  const result = await fetchJson("/api/v1/corrections", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setCorrectionStatus(`提交成功，勘误编号 #${result.correction_id}，当前状态：${result.status}。`);
}

document.querySelectorAll("[data-go-screen]").forEach((button) => {
  button.addEventListener("click", async () => {
    const target = button.dataset.goScreen;
    if (target === "branch") {
      try {
        await renderBranchScreen();
      } catch (error) {
        treeColumns.innerHTML = `<div class="notice-box">支系图加载失败：${escapeHtml(error.message)}</div>`;
      }
    }
    switchScreen(target);
    pushRouteState({ screen: target, selectedPerson: state.selectedPerson });
  });
});

document.querySelectorAll(".nav-link").forEach((button) => {
  button.addEventListener("click", async () => {
    const target = button.dataset.screenTarget;
    if (target === "branch") {
      try {
        await renderBranchScreen();
      } catch (error) {
        treeColumns.innerHTML = `<div class="notice-box">支系图加载失败：${escapeHtml(error.message)}</div>`;
      }
    }
    switchScreen(target);
    pushRouteState({ screen: target, selectedPerson: state.selectedPerson });
  });
});

document.getElementById("search-submit").addEventListener("click", async () => {
  try {
    await searchPersons();
  } catch (error) {
    setSearchStatus(`查询失败：${error.message}`);
  }
});

document.getElementById("search-input").addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  try {
    await searchPersons();
  } catch (error) {
    setSearchStatus(`查询失败：${error.message}`);
  }
});

document.getElementById("contribute-submit").addEventListener("click", async () => {
  try {
    await submitContribution();
  } catch (error) {
    setContributeStatus(`提交失败：${error.message}`);
  }
});

document.getElementById("correction-submit").addEventListener("click", async () => {
  try {
    await submitCorrection();
  } catch (error) {
    setCorrectionStatus(`提交失败：${error.message}`);
  }
});

[upwardRange, downwardRange, toggleDaughters, toggleSpouses].forEach((control) => {
  control.addEventListener("input", async () => {
    upwardValue.textContent = `${upwardRange.value} 代`;
    downwardValue.textContent = `${downwardRange.value} 代`;
    if (state.activeScreen !== "branch" || !state.selectedPerson) return;
    try {
      await renderBranchScreen();
    } catch (error) {
      treeColumns.innerHTML = `<div class="notice-box">支系图加载失败：${escapeHtml(error.message)}</div>`;
    }
  });
});

window.addEventListener("popstate", async (event) => {
  try {
    await applyRouteState(event.state?.[historyStateKey] ? event.state : parseRouteFromLocation());
  } catch (error) {
    setSearchStatus(`页面回退失败：${error.message}`);
  }
});

async function bootstrap() {
  renderResults();
  setSearchStatus(`当前 API：${displayedApiBase()}。默认示例词可用：永昌`);
  updateContributeHeading();
  updateCorrectionForm();
  updateBranchControlsVisibility();
  upwardValue.textContent = `${upwardRange.value} 代`;
  downwardValue.textContent = `${downwardRange.value} 代`;
  await applyRouteState(parseRouteFromLocation());
  replaceRouteState({ screen: state.activeScreen, selectedPerson: state.selectedPerson });
  fetchJson("/health")
    .then((health) => {
      if (health.read_only) {
        applyReadOnlyMode();
      }
    })
    .catch(() => {});
}

bootstrap().catch((error) => {
  setSearchStatus(`页面初始化失败：${error.message}`);
  replaceRouteState({ screen: state.activeScreen, selectedPerson: state.selectedPerson });
});
