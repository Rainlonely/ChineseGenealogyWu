const state = {
  data: null,
  graphZoom: 1,
  selectedPersonId: null,
  personMenu: {
    open: false,
    personId: null,
    x: 0,
    y: 0,
    loading: false,
    saving: false,
    detail: null,
    error: "",
    editing: false,
    draftName: "",
  },
};

const fullTreeTitle = document.getElementById("fullTreeTitle");
const fullTreeStatus = document.getElementById("fullTreeStatus");
const fullTreeSummary = document.getElementById("fullTreeSummary");
const fullTreeWrap = document.getElementById("fullTreeWrap");
const fullTreeSvg = document.getElementById("fullTreeSvg");
const fullTreeHint = document.getElementById("fullTreeHint");
const fullTreeZoomOutBtn = document.getElementById("fullTreeZoomOutBtn");
const fullTreeZoomResetBtn = document.getElementById("fullTreeZoomResetBtn");
const fullTreeZoomInBtn = document.getElementById("fullTreeZoomInBtn");
const fullTreeFullscreenBtn = document.getElementById("fullTreeFullscreenBtn");
const personContextMenu = document.getElementById("personContextMenu");

function setStatus(text) {
  fullTreeStatus.textContent = text;
}

async function readJsonResponse(response, actionLabel) {
  const contentType = response.headers.get("content-type") || "";
  const rawText = await response.text();
  if (!contentType.includes("application/json")) {
    const looksLikeHtml = rawText.trim().startsWith("<!DOCTYPE") || rawText.trim().startsWith("<html") || rawText.trim().startsWith("<");
    if (looksLikeHtml) {
      throw new Error(`${actionLabel}接口返回了 HTML，不是 JSON。通常是本地 review server 还没重启，请重启 scripts/run_gen_review_server.py。`);
    }
    throw new Error(`${actionLabel}接口返回了非 JSON 内容。`);
  }
  try {
    return JSON.parse(rawText);
  } catch (error) {
    throw new Error(`${actionLabel}接口返回的 JSON 解析失败：${error.message}`);
  }
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function createSvgNode(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function sortChildrenForTree(children, peopleById) {
  return children.slice().sort((a, b) => {
    const orderA = Number.isFinite(Number(a.birth_order_under_parent)) ? Number(a.birth_order_under_parent) : 999;
    const orderB = Number.isFinite(Number(b.birth_order_under_parent)) ? Number(b.birth_order_under_parent) : 999;
    if (orderA !== orderB) return orderA - orderB;
    const nameA = peopleById.get(a.to_person_id)?.name || "";
    const nameB = peopleById.get(b.to_person_id)?.name || "";
    return nameA.localeCompare(nameB, "zh-Hans-CN");
  });
}

function buildRootOrder(graphNodes, incoming, nodePageMap) {
  return graphNodes
    .filter((person) => !(incoming.get(person.id) || []).length)
    .slice()
    .sort((a, b) => {
      const rootOrderA = Number.isFinite(Number(a.root_order)) ? Number(a.root_order) : null;
      const rootOrderB = Number.isFinite(Number(b.root_order)) ? Number(b.root_order) : null;
      if (rootOrderA !== null || rootOrderB !== null) {
        return (rootOrderA ?? 999) - (rootOrderB ?? 999) || (a.name || "").localeCompare(b.name || "", "zh-Hans-CN");
      }
      const genA = Number(a.generation || 999);
      const genB = Number(b.generation || 999);
      if (genA !== genB) return genA - genB;
      const pageA = nodePageMap.get(a.id) || 999;
      const pageB = nodePageMap.get(b.id) || 999;
      return pageA - pageB || (a.name || "").localeCompare(b.name || "", "zh-Hans-CN");
    });
}

function computeGlobalTreeLayout(graphNodes, graphEdges) {
  const peopleById = new Map(graphNodes.map((person) => [person.id, person]));
  const childMap = new Map();
  const incoming = new Map();
  const nodePageMap = new Map();

  graphEdges.forEach((edge) => {
    if (!childMap.has(edge.from_person_id)) childMap.set(edge.from_person_id, []);
    childMap.get(edge.from_person_id).push(edge);
    if (!incoming.has(edge.to_person_id)) incoming.set(edge.to_person_id, []);
    incoming.get(edge.to_person_id).push(edge);
  });

  childMap.forEach((edges, parentId) => {
    childMap.set(parentId, sortChildrenForTree(edges, peopleById));
  });

  const generations = [...new Set(graphNodes.map((person) => Number(person.generation || 0)).filter(Boolean))].sort((a, b) => a - b);
  const generationIndex = new Map(generations.map((gen, index) => [gen, index]));
  const pages = [...new Set(graphNodes.map((person) => Number(person.primary_page_no || 0)).filter(Boolean))].sort((a, b) => a - b);

  graphNodes.forEach((person) => {
    nodePageMap.set(person.id, Number(person.primary_page_no || pages[0] || 1));
  });

  const roots = buildRootOrder(graphNodes, incoming, nodePageMap).sort((a, b) => {
    const rootOrderA = Number.isFinite(Number(a.root_order)) ? Number(a.root_order) : null;
    const rootOrderB = Number.isFinite(Number(b.root_order)) ? Number(b.root_order) : null;
    if (rootOrderA !== null || rootOrderB !== null) {
      return (rootOrderA ?? 999) - (rootOrderB ?? 999) || (a.name || "").localeCompare(b.name || "", "zh-Hans-CN");
    }
    const genA = Number(a.generation || 999);
    const genB = Number(b.generation || 999);
    if (genA !== genB) return genA - genB;
    return (nodePageMap.get(a.id) || 999) - (nodePageMap.get(b.id) || 999) || (a.name || "").localeCompare(b.name || "", "zh-Hans-CN");
  });

  let slot = 0;
  const slotPositions = new Map();

  function assignSlots(personId) {
    const children = childMap.get(personId) || [];
    if (!children.length) {
      slotPositions.set(personId, slot);
      slot += 1;
      return slotPositions.get(personId);
    }
    const orderedChildren = children.slice().reverse();
    const childSlots = orderedChildren.map((edge) => assignSlots(edge.to_person_id));
    const rightAligned = childSlots[childSlots.length - 1];
    slotPositions.set(personId, rightAligned);
    return rightAligned;
  }

  roots.slice().reverse().forEach((root, index) => {
    assignSlots(root.id);
    if (index !== roots.length - 1) slot += 20 / 76;
  });

  graphNodes.filter((person) => !slotPositions.has(person.id)).forEach((person) => assignSlots(person.id));

  return {
    peopleById,
    childMap,
    incoming,
    generations,
    generationIndex,
    nodePageMap,
    slotPositions,
    maxSlot: Math.max(...[...slotPositions.values(), 0]),
  };
}

function collectSubtreeIds(rootId, childMap) {
  const ids = new Set();
  function walk(personId) {
    if (ids.has(personId)) return;
    ids.add(personId);
    (childMap.get(personId) || []).forEach((edge) => walk(edge.to_person_id));
  }
  walk(rootId);
  return ids;
}

function closePersonMenu() {
  state.personMenu = {
    open: false,
    personId: null,
    x: 0,
    y: 0,
    loading: false,
    saving: false,
    detail: null,
    error: "",
    editing: false,
    draftName: "",
  };
  renderPersonMenu();
}

function repositionPersonMenu() {
  if (!state.personMenu.open || personContextMenu.hidden) return;
  const padding = 12;
  const rect = personContextMenu.getBoundingClientRect();
  let left = state.personMenu.x;
  let top = state.personMenu.y;
  if (left + rect.width > window.innerWidth - padding) {
    left = Math.max(padding, window.innerWidth - rect.width - padding);
  }
  if (top + rect.height > window.innerHeight - padding) {
    top = Math.max(padding, window.innerHeight - rect.height - padding);
  }
  personContextMenu.style.left = `${left}px`;
  personContextMenu.style.top = `${top}px`;
}

function renderPersonMenu() {
  if (!state.personMenu.open) {
    personContextMenu.hidden = true;
    personContextMenu.innerHTML = "";
    return;
  }
  const fallbackPerson = (state.data?.persons || []).find((person) => person.id === state.personMenu.personId);
  const detail = state.personMenu.detail?.person;
  const displayName = state.personMenu.editing ? state.personMenu.draftName : (detail?.name || fallbackPerson?.name || state.personMenu.personId);
  const pages = state.personMenu.detail?.pages || [];
  const glyphImage = detail?.glyph_image || fallbackPerson?.glyph_image || "";
  const currentRefText = detail?.text_ref?.text || detail?.text_ref?.raw_text || "";
  const aliases = (detail?.aliases || []).filter(Boolean).join(" / ");
  const notes = (detail?.notes || []).filter(Boolean).join("；");
  let sourceColumnsPreview = "暂无";
  if (detail?.source_columns_json) {
    try {
      const parsed = typeof detail.source_columns_json === "string"
        ? JSON.parse(detail.source_columns_json)
        : detail.source_columns_json;
      sourceColumnsPreview = JSON.stringify(parsed, null, 2);
    } catch {
      sourceColumnsPreview = String(detail.source_columns_json);
    }
  }

  personContextMenu.hidden = false;
  personContextMenu.innerHTML = `
    <div class="person-menu-header">
      <div>
        <div class="person-menu-title">${escapeHtml(displayName || "未命名人物")}</div>
        <div class="person-menu-subtitle">${escapeHtml(detail?.group_id || fallbackPerson?.source_group_id || "")} · 第${escapeHtml(String(detail?.generation || fallbackPerson?.generation || "?"))}世</div>
      </div>
      <button type="button" class="person-menu-close" data-person-menu-close>关闭</button>
    </div>
    ${state.personMenu.loading ? `<div class="person-menu-empty">正在读取人物信息...</div>` : ""}
    ${state.personMenu.error ? `<div class="person-menu-error">${escapeHtml(state.personMenu.error)}</div>` : ""}
    ${
      !state.personMenu.loading
        ? `
      <div class="person-menu-section">
        <div class="person-menu-section-title">姓名与识别</div>
        ${
          state.personMenu.editing
            ? `<div class="person-menu-edit-row">
                <input id="personMenuNameInput" type="text" value="${escapeHtml(state.personMenu.draftName)}" />
                <button type="button" class="person-menu-primary" data-person-save ${state.personMenu.saving ? "disabled" : ""}>${state.personMenu.saving ? "保存中..." : "保存"}</button>
                <button type="button" data-person-cancel-edit>取消</button>
              </div>`
            : `<div class="person-menu-name-row">
                <span class="person-menu-name">${escapeHtml(displayName)}</span>
                <button type="button" data-person-edit>编辑</button>
              </div>`
        }
        <div class="person-menu-textref">当前文字框：${escapeHtml(currentRefText || "暂无")}</div>
      </div>
      <div class="person-menu-section">
        <div class="person-menu-section-title">名字图片</div>
        ${
          glyphImage
            ? `<div class="person-menu-glyph"><img src="${glyphImage}" alt="人物名字截图" /></div>`
            : `<div class="person-menu-empty">暂无名字截图</div>`
        }
      </div>
      <div class="person-menu-section">
        <div class="person-menu-section-title">数据库属性</div>
        <div class="person-menu-props">
          <div class="person-menu-prop"><span>人物ID</span><strong>${escapeHtml(detail?.id || fallbackPerson?.id || "")}</strong></div>
          <div class="person-menu-prop"><span>所属分组</span><strong>${escapeHtml(detail?.group_id || fallbackPerson?.source_group_id || "")}</strong></div>
          <div class="person-menu-prop"><span>世代</span><strong>第${escapeHtml(String(detail?.generation || fallbackPerson?.generation || "?"))}世</strong></div>
          <div class="person-menu-prop"><span>树状态</span><strong>${escapeHtml(detail?.tree_status || "未知")}</strong></div>
          <div class="person-menu-prop"><span>子数量</span><strong>${escapeHtml(String(detail?.child_count ?? 0))}</strong></div>
          <div class="person-menu-prop"><span>组内父链</span><strong>${escapeHtml(String(detail?.internal_parent_links ?? 0))}</strong></div>
          <div class="person-menu-prop"><span>跨组父链</span><strong>${escapeHtml(String(detail?.bridge_parent_links ?? 0))}</strong></div>
          <div class="person-menu-prop"><span>主页码</span><strong>${escapeHtml(detail?.primary_page_no ? `第${detail.primary_page_no}页` : "暂无")}</strong></div>
          <div class="person-menu-prop"><span>校对状态</span><strong>${escapeHtml(detail?.review_status || "draft")}</strong></div>
          <div class="person-menu-prop"><span>人工关联</span><strong>${escapeHtml(detail?.match_status || "暂无")}</strong></div>
          <div class="person-menu-prop"><span>已验证</span><strong>${detail?.is_verified ? "是" : "否"}</strong></div>
          <div class="person-menu-prop"><span>规范名</span><strong>${escapeHtml(detail?.canonical_name || "暂无")}</strong></div>
          <div class="person-menu-prop"><span>别名</span><strong>${escapeHtml(aliases || "暂无")}</strong></div>
          <div class="person-menu-prop person-menu-prop-wide"><span>备注</span><strong>${escapeHtml(detail?.remark || "暂无")}</strong></div>
          <div class="person-menu-prop person-menu-prop-wide"><span>附记</span><strong>${escapeHtml(notes || "暂无")}</strong></div>
          <div class="person-menu-prop person-menu-prop-wide"><span>拼接文字</span><strong>${escapeHtml(detail?.source_text_linear || "暂无")}</strong></div>
          <div class="person-menu-prop person-menu-prop-wide"><span>OCR原始文字</span><strong>${escapeHtml(detail?.source_text_raw || "暂无")}</strong></div>
          <div class="person-menu-prop person-menu-prop-wide"><span>断句占位</span><strong>${escapeHtml(detail?.source_text_punctuated || "暂无")}</strong></div>
          <div class="person-menu-prop person-menu-prop-wide"><span>白话文占位</span><strong>${escapeHtml(detail?.source_text_baihua || "暂无")}</strong></div>
          <div class="person-menu-prop person-menu-prop-wide"><span>文字块截图与坐标</span><strong class="person-menu-pre">${escapeHtml(sourceColumnsPreview)}</strong></div>
        </div>
      </div>
      <div class="person-menu-section">
        <div class="person-menu-section-title">来源页面</div>
        ${
          pages.length
            ? `<div class="person-menu-pages">
                ${pages
                  .map((page) => {
                    const refs = (page.refs || []).map((ref) => ref.text || ref.raw_text || `#${ref.index}`).filter(Boolean).join(" / ");
                    return `<div class="person-menu-page-item">
                      <div class="person-menu-page-title">第${escapeHtml(String(page.page))}页</div>
                      <div class="person-menu-page-meta">${escapeHtml(refs || "无文字框文本")}</div>
                    </div>`;
                  })
                  .join("")}
              </div>`
            : `<div class="person-menu-empty">暂无页面来源信息</div>`
        }
      </div>
    `
        : ""
    }
  `;
  personContextMenu.style.left = `${state.personMenu.x}px`;
  personContextMenu.style.top = `${state.personMenu.y}px`;
  repositionPersonMenu();
}

async function openPersonMenu(person, event) {
  event.preventDefault();
  event.stopPropagation();
  state.personMenu = {
    open: true,
    personId: person.id,
    x: event.clientX + 8,
    y: event.clientY + 8,
    loading: true,
    saving: false,
    detail: null,
    error: "",
    editing: false,
    draftName: person.name || "",
  };
  renderPersonMenu();
  try {
    const response = await fetch(`/api/person-detail?person_id=${encodeURIComponent(person.id)}`);
    const payload = await readJsonResponse(response, "人物详情");
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "人物详情读取失败");
    }
    if (state.personMenu.personId !== person.id) return;
    state.personMenu.loading = false;
    state.personMenu.detail = payload;
    state.personMenu.draftName = payload.person?.name || person.name || "";
    renderPersonMenu();
  } catch (error) {
    if (state.personMenu.personId !== person.id) return;
    state.personMenu.loading = false;
    state.personMenu.error = error.message;
    renderPersonMenu();
  }
}

async function savePersonName() {
  if (!state.personMenu.personId || !state.personMenu.editing) return;
  const input = document.getElementById("personMenuNameInput");
  const name = input?.value?.trim() || state.personMenu.draftName.trim();
  if (!name) {
    state.personMenu.error = "姓名不能为空";
    renderPersonMenu();
    return;
  }
  state.personMenu.saving = true;
  state.personMenu.error = "";
  renderPersonMenu();
  try {
    const response = await fetch("/api/person-update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_id: state.personMenu.personId, name }),
    });
    const payload = await readJsonResponse(response, "人物保存");
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "姓名保存失败");
    }
    const person = (state.data?.persons || []).find((item) => item.id === state.personMenu.personId);
    if (person) person.name = name;
    state.personMenu.saving = false;
    state.personMenu.editing = false;
    state.personMenu.detail = payload.detail;
    state.personMenu.draftName = name;
    setStatus(`已更新 ${name} 的姓名，并同步到 SQLite。`);
    renderTree();
    renderPersonMenu();
  } catch (error) {
    state.personMenu.saving = false;
    state.personMenu.error = error.message;
    renderPersonMenu();
  }
}

function renderTree() {
  if (!state.data) return;
  const graphNodes = state.data.persons || [];
  const graphEdges = state.data.edges || [];
  const { peopleById, childMap, generations, generationIndex, slotPositions, maxSlot } = computeGlobalTreeLayout(graphNodes, graphEdges);

  const selectedSubtreeIds = state.selectedPersonId ? collectSubtreeIds(state.selectedPersonId, childMap) : new Set();
  const leftMargin = 48;
  const rightMargin = 120;
  const topMargin = 54;
  const rowHeight = 132;
  const nodeWidth = 54;
  const nodeHeightWithGlyph = 94;
  const nodeHeightPlain = 38;
  const slotWidth = 76;
  const height = Math.max(560, topMargin + generations.length * rowHeight + 40);
  const width = Math.max(1800, leftMargin + (maxSlot + 2) * slotWidth + rightMargin);

  fullTreeSvg.innerHTML = "";
  fullTreeSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  fullTreeSvg.style.width = `${Math.round(width * state.graphZoom)}px`;
  fullTreeSvg.style.height = `${Math.round(height * state.graphZoom)}px`;

  const positions = new Map();
  graphNodes.forEach((person) => {
    const x = width - rightMargin - (maxSlot - (slotPositions.get(person.id) ?? 0)) * slotWidth;
    const row = generationIndex.get(Number(person.generation || generations[0] || 0)) ?? 0;
    const y = topMargin + row * rowHeight + rowHeight / 2;
    positions.set(person.id, { x, y });
  });

  generations.forEach((gen, index) => {
    const y = topMargin + index * rowHeight + rowHeight / 2;
    fullTreeSvg.appendChild(createSvgNode("line", {
      x1: String(leftMargin - 20),
      y1: String(y),
      x2: String(width - rightMargin + 10),
      y2: String(y),
      class: "graph-row-guide",
    }));
    const label = createSvgNode("text", {
      x: String(width - 42),
      y: String(y + 6),
      "text-anchor": "middle",
      class: "graph-generation",
    });
    label.textContent = `第${gen}世`;
    fullTreeSvg.appendChild(label);
  });

  childMap.forEach((edges, parentId) => {
    const parent = positions.get(parentId);
    const parentPerson = peopleById.get(parentId);
    if (!parent || !parentPerson) return;
    const parentHeight = parentPerson.glyph_image ? nodeHeightWithGlyph : nodeHeightPlain;
    const startY = parent.y + parentHeight / 2;
    const childEntries = edges
      .map((edge) => {
        const child = positions.get(edge.to_person_id);
        const childPerson = peopleById.get(edge.to_person_id);
        if (!child || !childPerson) return null;
        const childHeight = childPerson.glyph_image ? nodeHeightWithGlyph : nodeHeightPlain;
        return { edge, child, endY: child.y - childHeight / 2 };
      })
      .filter(Boolean);
    if (!childEntries.length) return;
    const busY =
      childEntries.length === 1
        ? startY + (childEntries[0].endY - startY) * 0.5
        : startY + (Math.min(...childEntries.map((item) => item.endY)) - startY) * 0.45;
    const selectedClass = childEntries.some((item) => selectedSubtreeIds.has(parentId) && selectedSubtreeIds.has(item.edge.to_person_id))
      ? " graph-edge-selected"
      : "";

    fullTreeSvg.appendChild(createSvgNode("path", {
      d: `M ${parent.x} ${startY} V ${busY}`,
      class: `graph-edge graph-edge-orth${selectedClass}`,
    }));

    if (childEntries.length > 1) {
      const childXs = childEntries.map((item) => item.child.x);
      fullTreeSvg.appendChild(createSvgNode("path", {
        d: `M ${Math.min(...childXs)} ${busY} H ${Math.max(...childXs)}`,
        class: "graph-edge graph-edge-orth",
      }));
    }

    childEntries.forEach((item) => {
      fullTreeSvg.appendChild(createSvgNode("path", {
        d: `M ${item.child.x} ${busY} V ${item.endY}`,
        class: `graph-edge graph-edge-orth${selectedSubtreeIds.has(parentId) && selectedSubtreeIds.has(item.edge.to_person_id) ? " graph-edge-selected" : ""}`,
      }));
    });
  });

  graphNodes.forEach((person) => {
    const pos = positions.get(person.id);
    if (!pos) return;
    const hasGlyph = Boolean(person.glyph_image);
    const nodeHeight = hasGlyph ? nodeHeightWithGlyph : nodeHeightPlain;
    const nodeGroup = createSvgNode("g", {
      class: `graph-node-group${selectedSubtreeIds.has(person.id) ? " graph-node-group-selected" : ""}${state.selectedPersonId === person.id ? " graph-node-group-active" : ""}`,
    });
    nodeGroup.appendChild(createSvgNode("rect", {
      x: String(pos.x - nodeWidth / 2),
      y: String(pos.y - nodeHeight / 2),
      width: String(nodeWidth),
      height: String(nodeHeight),
      rx: "8",
      class: "graph-node",
    }));
    if (hasGlyph) {
      nodeGroup.appendChild(createSvgNode("image", {
        href: person.glyph_image,
        x: String(pos.x - 18),
        y: String(pos.y - nodeHeight / 2 + 10),
        width: "36",
        height: "36",
        class: "graph-glyph",
      }));
    }
    const text = createSvgNode("text", {
      x: String(pos.x),
      y: String(pos.y + (hasGlyph ? 32 : 6)),
      "text-anchor": "middle",
      class: "graph-label",
    });
    text.textContent = person.name || person.id;
    nodeGroup.appendChild(text);
    nodeGroup.addEventListener("click", () => {
      state.selectedPersonId = state.selectedPersonId === person.id ? null : person.id;
      fullTreeHint.textContent = state.selectedPersonId
        ? `已选中 ${person.name || person.id}，高亮其后代分支。`
        : "点击节点可高亮整支后代";
      renderTree();
    });
    nodeGroup.addEventListener("contextmenu", (event) => openPersonMenu(person, event));
    fullTreeSvg.appendChild(nodeGroup);
  });
}

async function boot() {
  const response = await fetch("/api/full-tree?max_generation=102");
  if (!response.ok) {
    throw new Error((await response.text()) || "完整树加载失败");
  }
  const payload = await readJsonResponse(response, "完整树");
  if (!payload.ok) {
    throw new Error(payload.error || "完整树加载失败");
  }
  state.data = payload;
  fullTreeTitle.textContent = payload.label || "1-102世完整树";
  fullTreeSummary.textContent = `共 ${payload.persons.length} 人，${payload.edges.length} 条父子边，默认展示第1世到第${payload.max_generation}世。右击人物可查看数据库属性。`;
  setStatus("已加载完整树，数据来自数据库。");
  renderTree();
}

fullTreeZoomOutBtn?.addEventListener("click", () => {
  state.graphZoom = Math.max(0.3, Number((state.graphZoom - 0.1).toFixed(2)));
  renderTree();
});

fullTreeZoomResetBtn?.addEventListener("click", () => {
  state.graphZoom = 1;
  renderTree();
});

fullTreeZoomInBtn?.addEventListener("click", () => {
  state.graphZoom = Math.min(3, Number((state.graphZoom + 0.1).toFixed(2)));
  renderTree();
});

fullTreeFullscreenBtn?.addEventListener("click", async () => {
  if (document.fullscreenElement === fullTreeWrap) {
    await document.exitFullscreen();
    return;
  }
  if (fullTreeWrap.requestFullscreen) {
    await fullTreeWrap.requestFullscreen();
  }
});

document.addEventListener("fullscreenchange", () => {
  fullTreeFullscreenBtn.textContent = document.fullscreenElement === fullTreeWrap ? "退出全屏" : "全屏查看";
});

document.addEventListener("click", (event) => {
  if (!state.personMenu.open) return;
  if (event.target.closest("#personContextMenu")) return;
  closePersonMenu();
});

document.addEventListener("scroll", () => {
  if (state.personMenu.open) repositionPersonMenu();
}, true);

window.addEventListener("resize", () => {
  if (state.personMenu.open) repositionPersonMenu();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.personMenu.open) {
    closePersonMenu();
  }
});

personContextMenu?.addEventListener("click", (event) => {
  event.stopPropagation();
  const closeBtn = event.target.closest("[data-person-menu-close]");
  if (closeBtn) {
    closePersonMenu();
    return;
  }
  const editBtn = event.target.closest("[data-person-edit]");
  if (editBtn) {
    state.personMenu.editing = true;
    state.personMenu.error = "";
    renderPersonMenu();
    document.getElementById("personMenuNameInput")?.focus();
    return;
  }
  const cancelBtn = event.target.closest("[data-person-cancel-edit]");
  if (cancelBtn) {
    state.personMenu.editing = false;
    state.personMenu.error = "";
    state.personMenu.draftName = state.personMenu.detail?.person?.name || state.personMenu.draftName;
    renderPersonMenu();
    return;
  }
  const saveBtn = event.target.closest("[data-person-save]");
  if (saveBtn) {
    savePersonName();
    return;
  }
});

personContextMenu?.addEventListener("input", (event) => {
  if (event.target.id === "personMenuNameInput") {
    state.personMenu.draftName = event.target.value;
  }
});

boot().catch((error) => {
  setStatus(`完整树加载失败：${error.message}`);
});
