const state = {
  data: null,
  page: 41,
  zoom: 1,
  graphZoom: 1,
  activePersonId: null,
  linkMode: false,
  linkParentPersonId: null,
  linkChildPersonId: null,
  linkDeleteEdgeKey: null,
  dragAction: null,
  fullscreenSelectedPersonId: null,
  fullscreenLayoutMode: "page",
  fullscreenBoundaryMode: true,
  fullscreenParentCandidateQuery: "",
  sqliteMirror: null,
};

const statusText = document.getElementById("statusText");
const groupTitle = document.getElementById("groupTitle");
const workspaceSummaryText = document.getElementById("workspaceSummaryText");
const workspaceSummaryStats = document.getElementById("workspaceSummaryStats");
const groupSwitch = document.getElementById("groupSwitch");
const pageSelect = document.getElementById("pageSelect");
const overlayHint = document.getElementById("overlayHint");
const generationRail = document.getElementById("generationRail");
const imagePanel = document.querySelector(".image-panel");
const imageStage = document.getElementById("imageStage");
const pageImage = document.getElementById("pageImage");
const ocrOverlay = document.getElementById("ocrOverlay");
const linkModeBtn = document.getElementById("linkModeBtn");
const finishLinkBtn = document.getElementById("finishLinkBtn");
const pageRoleInput = document.getElementById("pageRoleInput");
const keepAxisSelect = document.getElementById("keepAxisSelect");
const pageNotesInput = document.getElementById("pageNotesInput");
const personsTable = document.getElementById("personsTable");
const addPersonBtn = document.getElementById("addPersonBtn");
const peopleLockBtn = document.getElementById("peopleLockBtn");
const edgesTable = document.getElementById("edgesTable");
const allPersonsList = document.getElementById("allPersonsList");
const newEdgeFromInput = document.getElementById("newEdgeFromInput");
const newEdgeFromSelect = document.getElementById("newEdgeFromSelect");
const newEdgeToInput = document.getElementById("newEdgeToInput");
const newEdgeToSelect = document.getElementById("newEdgeToSelect");
const addEdgeBtn = document.getElementById("addEdgeBtn");
const graphFullscreenBtn = document.getElementById("graphFullscreenBtn");
const graphZoomOutBtn = document.getElementById("graphZoomOutBtn");
const graphZoomResetBtn = document.getElementById("graphZoomResetBtn");
const graphZoomInBtn = document.getElementById("graphZoomInBtn");
const graphWrap = document.getElementById("graphWrap");
const graphSvg = document.getElementById("graphSvg");
const fullscreenLayoutModeBtn = document.getElementById("fullscreenLayoutModeBtn");
const fullscreenBoundaryModeBtn = document.getElementById("fullscreenBoundaryModeBtn");
const fullscreenLinkModeBtn = document.getElementById("fullscreenLinkModeBtn");
const fullscreenFinishLinkBtn = document.getElementById("fullscreenFinishLinkBtn");
const mergeActionBtn = document.getElementById("mergeActionBtn");
const fullscreenDbSyncHint = document.getElementById("fullscreenDbSyncHint");
const fullscreenGraphHint = document.getElementById("fullscreenGraphHint");
const fullscreenPageImagePanel = document.getElementById("fullscreenPageImagePanel");
const fullscreenPageImageStrip = document.getElementById("fullscreenPageImageStrip");
const fullscreenParentPanel = document.getElementById("fullscreenParentPanel");
const fullscreenParentPanelTitle = document.getElementById("fullscreenParentPanelTitle");
const fullscreenParentPanelCount = document.getElementById("fullscreenParentPanelCount");
const fullscreenParentSearchInput = document.getElementById("fullscreenParentSearchInput");
const fullscreenParentList = document.getElementById("fullscreenParentList");
const undoBtn = document.getElementById("undoBtn");
let autoSaveTimer = null;
let autoSaveInFlight = false;
let graphRenderQueued = false;
let linkDeleteHoverTimer = null;
const dirtyPages = new Set();
const fieldDraftBaseline = new Map();
const PAGE_COOKIE_NAME = "family_genealogy_current_page";
const historyStack = [];
const HISTORY_LIMIT = 50;
const LARGE_WORKSPACE_HISTORY_PERSON_THRESHOLD = 1500;
const MERGE_WORKSPACE_PREFIX = "merge__";
const LINK_EDGE_DELETE_HOVER_MS = 420;
const GROUPS = [
  { id: "gen_001_005", label: "1-5世" },
  { id: "gen_006_010", label: "6-10世" },
  { id: "gen_011_015", label: "11-15世" },
  { id: "gen_016_020", label: "16-20世" },
  { id: "gen_021_025", label: "21-25世" },
  { id: "gen_026_030", label: "26-30世" },
  { id: "gen_031_035", label: "31-35世" },
  { id: "gen_036_040", label: "36-40世" },
  { id: "gen_041_045", label: "41-45世" },
  { id: "gen_046_050", label: "46-50世" },
  { id: "gen_051_055", label: "51-55世" },
  { id: "gen_056_060", label: "56-60世" },
  { id: "gen_061_065", label: "61-65世" },
  { id: "gen_066_070", label: "66-70世" },
  { id: "gen_071_075", label: "71-75世" },
  { id: "gen_076_080", label: "76-80世" },
  { id: "gen_081_085", label: "81-85世" },
  { id: "gen_086_090", label: "86-90世" },
  { id: "gen_091_095", label: "91-95世" },
  { id: "gen_093_097", label: "93-97世" },
  { id: "gen_098_102", label: "98-102世" },
  { id: "gen_103_107", label: "103-107世" },
  { id: "gen_108_112", label: "108-112世" },
];

function renderWorkspaceSummary(summary) {
  if (!workspaceSummaryText || !workspaceSummaryStats) return;
  if (!summary?.ok) {
    workspaceSummaryText.textContent = summary?.error ? `数据库汇总读取失败：${summary.error}` : "数据库汇总暂不可用";
    workspaceSummaryStats.innerHTML = "";
    return;
  }
  workspaceSummaryText.textContent =
    summary.range_ready
      ? "1-107世已连成完整树，数据库状态正常。"
      : `1-107世仍有 ${summary.range_missing_parent_count || 0} 个未接上的父链。`;
  const stats = [
    {
      label: "树状态",
      value: summary.range_ready ? "已完整" : "未完成",
      klass: summary.range_ready ? "is-good" : "is-warn",
    },
    { label: "组数", value: `${summary.group_count || 0}` },
    { label: "人物", value: `${summary.person_count || 0}` },
    { label: "父子边", value: `${summary.relationship_count || 0}` },
    { label: "跨组边", value: `${summary.bridge_relationship_count || 0}` },
    { label: "Bridge段", value: `${summary.bridge_scope_count || 0}` },
  ];
  workspaceSummaryStats.innerHTML = stats
    .map(
      (item) => `<span class="summary-stat${item.klass ? ` ${item.klass}` : ""}">${item.label}<strong>${item.value}</strong></span>`,
    )
    .join("");
}

async function loadWorkspaceSummary() {
  if (workspaceSummaryText) {
    workspaceSummaryText.textContent = "正在读取数据库汇总...";
  }
  try {
    const response = await fetch("/api/summary");
    if (!response.ok) {
      throw new Error(await response.text() || "汇总接口失败");
    }
    const payload = await response.json();
    renderWorkspaceSummary(payload);
  } catch (error) {
    renderWorkspaceSummary({ ok: false, error: error.message });
  }
}

function currentGroupId() {
  return new URLSearchParams(window.location.search).get("group") || "gen_093_097";
}

function isMergeWorkspace() {
  return state.data?.workspace_type === "merge" || String(state.data?.group_id || "").startsWith(MERGE_WORKSPACE_PREFIX);
}

function parseRangeLabel(label) {
  const match = String(label || "").match(/(\d+)\s*-\s*(\d+)世/);
  if (!match) return null;
  return { start: Number(match[1]), end: Number(match[2]) };
}

function groupMetaById(groupId) {
  return GROUPS.find((group) => group.id === groupId) || null;
}

function parseMergeWorkspaceId(groupId) {
  if (!String(groupId || "").startsWith(MERGE_WORKSPACE_PREFIX)) return null;
  const parts = String(groupId).slice(MERGE_WORKSPACE_PREFIX.length).split("__").filter(Boolean);
  return parts.length >= 2 ? parts : null;
}

function buildMergeWorkspaceId(groupIds) {
  return `${MERGE_WORKSPACE_PREFIX}${groupIds.join("__")}`;
}

function sourceGroupIdsForWorkspace(data = state.data) {
  if (!data) return [currentGroupId()];
  if (data.workspace_type === "merge" && Array.isArray(data.source_groups) && data.source_groups.length) {
    return data.source_groups.slice();
  }
  return [data.group_id || currentGroupId()];
}

function mergeBoundaryGroupPair(data = state.data) {
  const groups = sourceGroupIdsForWorkspace(data);
  if (!groups || groups.length < 2) return null;
  return {
    leftGroupId: groups[groups.length - 2],
    rightGroupId: groups[groups.length - 1],
  };
}

function sourcePageForVirtualPage(page) {
  const entry = pageEntry(page);
  return Number(entry?.source_page ?? page);
}

function firstRefPageForPerson(person) {
  const refs = allTextRefs(person).slice().sort((a, b) => Number(a.page) - Number(b.page));
  const page = Number(refs[0]?.page || state.page);
  return Number.isFinite(page) ? page : state.page;
}

function mergeParentCandidates() {
  if (!isMergeWorkspace()) return [];
  const pair = mergeBoundaryGroupPair();
  if (!pair) return [];
  const rightPeople = state.data.persons.filter((person) => person.source_group_id === pair.rightGroupId);
  const rightBoundaryGen = Math.min(...rightPeople.map((person) => Number(person.generation || 0)).filter(Boolean));
  const parentGen = rightBoundaryGen - 1;
  return state.data.persons
    .filter(
      (person) =>
        person.source_group_id === pair.leftGroupId &&
        Number(person.generation || 0) === parentGen,
    )
    .map((person) => {
      const virtualPage = firstRefPageForPerson(person);
      return {
        person,
        virtualPage,
        sourcePage: sourcePageForVirtualPage(virtualPage),
      };
    })
    .sort((a, b) => a.sourcePage - b.sourcePage || (a.person.name || "").localeCompare(b.person.name || "", "zh-Hans-CN"));
}

function scrollFullscreenToPerson(personId) {
  if (!isGraphFullscreen() || !personId) return;
  requestAnimationFrame(() => {
    const node = graphWrap.querySelector(`.graph-node-group[data-person-id="${personId}"]`);
    if (!node) return;
    const wrapRect = graphWrap.getBoundingClientRect();
    const nodeRect = node.getBoundingClientRect();
    graphWrap.scrollLeft += nodeRect.left - wrapRect.left - (wrapRect.width - nodeRect.width) / 2;
    graphWrap.scrollTop += nodeRect.top - wrapRect.top - (wrapRect.height - nodeRect.height) / 2;
  });
}

function groupRangeLabel(groupIds) {
  const metas = groupIds.map((groupId) => groupMetaById(groupId)).filter(Boolean);
  if (!metas.length) return "未知世代";
  const first = parseRangeLabel(metas[0].label);
  const last = parseRangeLabel(metas[metas.length - 1].label);
  if (first && last) {
    return `${first.start}-${last.end}世`;
  }
  return metas[0].label;
}

function nextMergeActionContext(data = state.data) {
  const sourceGroupIds = sourceGroupIdsForWorkspace(data);
  const lastGroupId = sourceGroupIds[sourceGroupIds.length - 1];
  const lastIndex = GROUPS.findIndex((group) => group.id === lastGroupId);
  if (lastIndex < 0) return null;

  if (lastIndex >= GROUPS.length - 1) return null;
  const nextGroupId = GROUPS[lastIndex + 1].id;
  const targetGroupIds = [...sourceGroupIds, nextGroupId];
  return {
    source_group_ids: sourceGroupIds,
    next_group_id: nextGroupId,
    target_group_ids: targetGroupIds,
    target_workspace_id: buildMergeWorkspaceId(targetGroupIds),
    left_label: groupRangeLabel(sourceGroupIds),
    right_label: groupRangeLabel([nextGroupId]),
    target_label: groupRangeLabel(targetGroupIds),
    key: `${sourceGroupIds.join("|")}=>${nextGroupId}`,
  };
}

function setUrlGroup(groupId) {
  const url = new URL(window.location.href);
  url.searchParams.set("group", groupId);
  window.history.replaceState({}, "", url);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function sanitizeDetectedText(text) {
  const compact = String(text || "").replace(/\s+/g, "");
  const cleaned = compact
    .replace(/全圖/g, "")
    .replace(/圖全/g, "")
    .replace(/卷之一系/g, "")
    .replace(/卷之一/g, "")
    .replace(/九十三世至九十七世/g, "")
    .replace(/快德堂/g, "")
    .replace(/无十三世/g, "")
    .replace(/^[一二三四五六七八九十百千兩两廿卅\d]+/, "")
    .replace(/[一二三四五六七八九十百千兩两廿卅\d]+子/g, "")
    .replace(/[一二三四五六七八九十百千兩两廿卅\d]+$/g, "")
    .replace(/止/g, "")
    .replace(/[一二三四五六七八九十百\d]+世/g, "")
    .replace(/.+公支/g, "")
    .trim();
  if (!cleaned || /[世卷系圖堂]/.test(cleaned)) return "";
  return cleaned;
}

function synthesizePagesData(data) {
  const existing = new Map((data.pages_data || []).map((p) => [p.page, p]));
  const groupId = data.group_id || "gen_093_097";
  return data.pages.map((page) => {
    const current = existing.get(page) || {};
    return {
      ...current,
      page,
      image: current.image || `/${groupId}/cropped_jpg/page_${String(page).padStart(3, "0")}.jpg`,
      generation_hint: current.generation_hint || (page === 41 ? [93, 94, 95, 96, 97] : []),
      text_items: current.text_items || [],
      line_items: current.line_items || [],
      raw_markers: current.raw_markers || [],
      manual_notes: current.manual_notes || [],
      people_locked: Boolean(current.people_locked),
      page_role:
        current.page_role ||
        (page === 41 ? "group_title_page+structure_page" : "structure_page"),
      keep_generation_axis:
        current.keep_generation_axis !== undefined ? current.keep_generation_axis : page === 41,
    };
  });
}

function pageEntry(page) {
  return state.data.pages_data.find((item) => item.page === page);
}

function pageDisplayLabel(page) {
  const entry = pageEntry(page);
  if (entry?.page_display_label) return entry.page_display_label;
  if (isMergeWorkspace() && Number.isInteger(entry?.source_page)) {
    return `第${entry.source_page}页`;
  }
  return `第${page}页`;
}

function mergeRowKeyForPage(page) {
  if (isMergeWorkspace()) {
    const pageMembers = state.data?.page_group_members?.[String(page)] || [];
    if (pageMembers.length > 1) return "single";
    const sourceGroups = sourceGroupIdsForWorkspace();
    const rightGroupId = sourceGroups[sourceGroups.length - 1];
    if (pageMembers.includes(rightGroupId)) return "bottom";
    if (pageMembers.length) return "top";
  }
  const entry = pageEntry(page);
  const image = entry?.image || "";
  if (image.includes("/gen_093_097/")) return "top";
  if (image.includes("/gen_098_102/")) return "bottom";
  const hints = (entry?.generation_hint || [])
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
  if (hints.length) {
    return Math.min(...hints) <= 97 ? "top" : "bottom";
  }
  return Number(page) <= 46 ? "top" : "bottom";
}

function pageForPerson(person) {
  if (!person) return state.page;
  const refs = allTextRefs(person).slice().sort((a, b) => Number(a.page) - Number(b.page));
  const exact = refs.find((ref) => Number(ref.page) === Number(state.page));
  return Number(exact?.page || refs[0]?.page || state.page);
}

function textItemsForPage(page) {
  return (pageEntry(page)?.text_items || [])
    .map((item) => ({ ...item, clean_text: sanitizeDetectedText(item.text) }))
    .filter((item) => item.clean_text);
}

function allTextRefs(person) {
  const refs = [];
  if (Array.isArray(person?.text_refs)) {
    refs.push(...person.text_refs);
  }
  if (person?.text_ref && !refs.some((ref) => textRefKey(ref) === textRefKey(person.text_ref))) {
    refs.unshift(person.text_ref);
  }
  return refs.filter(Boolean);
}

function refForPage(person, page) {
  return allTextRefs(person).find((ref) => Number(ref.page) === Number(page)) || null;
}

function peopleForPage(page) {
  return state.data.persons.filter((person) =>
    allTextRefs(person).some((ref) => Number(ref.page) === Number(page)),
  );
}

function pagePeopleLocked(page = state.page) {
  if (isMergeWorkspace()) return true;
  return Boolean(pageEntry(page)?.people_locked);
}

function edgesForPage(page) {
  return state.data.edges.filter((edge) => (edge.page_sources || []).includes(page));
}

function personMap() {
  return new Map(state.data.persons.map((person) => [person.id, person]));
}

function activePerson() {
  return state.data?.persons.find((person) => person.id === state.activePersonId) || null;
}

function linkParentPerson() {
  return state.data?.persons.find((person) => person.id === state.linkParentPersonId) || null;
}

function setActivePerson(personId) {
  if (state.linkMode) {
    state.linkParentPersonId = null;
    state.linkChildPersonId = null;
  }
  state.activePersonId = personId || null;
  updateOverlayHint();
  renderPersons();
  renderOcrOverlay();
  if (personId) {
    requestAnimationFrame(() => {
      document.querySelector(`[data-person-row="${personId}"]`)?.scrollIntoView({
        block: "nearest",
        behavior: "smooth",
      });
    });
  }
}

async function setCurrentPageFromFullscreen(page) {
  const nextPage = Number(page);
  if (!Number.isInteger(nextPage) || nextPage <= 0 || nextPage === state.page) {
    return;
  }
  await navigateToPage(nextPage);
}

function isGraphFullscreen() {
  return document.fullscreenElement === graphWrap;
}

function refreshFullscreenLinkSelectionClasses() {
  if (!isGraphFullscreen()) return false;
  const nodes = graphSvg.querySelectorAll(".graph-node-group[data-person-id]");
  if (!nodes.length) return false;
  nodes.forEach((node) => {
    const personId = node.getAttribute("data-person-id");
    if (!personId) return;
    node.classList.toggle("graph-node-group-link-parent", personId === state.linkParentPersonId);
    node.classList.toggle("graph-node-group-link-child", personId === state.linkChildPersonId);
    node.classList.toggle("graph-node-group-link-candidate", isChildCandidate(personId));
  });
  return true;
}

function shouldKeepFullscreenCrossPageContext() {
  return isGraphFullscreen() && state.linkMode;
}

function setLinkMode(enabled) {
  state.linkMode = enabled;
  state.activePersonId = null;
  clearLinkDeleteControl(document.fullscreenElement === graphWrap);
  if (!enabled) {
    state.linkParentPersonId = null;
    state.linkChildPersonId = null;
  }
  updateOverlayHint();
  renderPersons();
  renderOcrOverlay();
}

function finishCurrentLinkParent() {
  state.linkParentPersonId = null;
  state.linkChildPersonId = null;
  clearLinkDeleteControl(true);
  updateOverlayHint();
  if (isGraphFullscreen()) {
    if (!refreshFullscreenLinkSelectionClasses()) {
      requestGraphRender(true);
    }
  } else {
    renderPersons();
    renderOcrOverlay();
    requestGraphRender(false);
  }
}

function ensureActivePersonForPage() {
  const people = peopleForPage(state.page);
  if (people.some((person) => person.id === state.activePersonId)) {
    return;
  }
  state.activePersonId = people[0]?.id || null;
}

function textRefKey(ref) {
  if (!ref) return "";
  return `${ref.page}:${ref.index}`;
}

function upsertTextRef(person, ref) {
  person.text_refs = allTextRefs(person).filter((item) => Number(item.page) !== Number(ref.page));
  person.text_refs.push(ref);
  person.text_ref = ref;
}

function removeTextRefForPage(person, page) {
  person.text_refs = allTextRefs(person).filter((item) => Number(item.page) !== Number(page));
  person.text_ref = person.text_refs[0] || null;
  if (!person.text_ref) delete person.text_ref;
  if (!person.text_refs.length) delete person.text_refs;
}

function assignedTextRefMapForPage(page) {
  const assigned = new Map();
  state.data.persons.forEach((person) => {
    allTextRefs(person)
      .filter((ref) => Number(ref.page) === page)
      .forEach((ref) => assigned.set(textRefKey(ref), person.id));
  });
  return assigned;
}

function incomingEdgeForChild(childId) {
  return state.data.edges.find((edge) => edge.to_person_id === childId) || null;
}

function generationRangeBounds() {
  const generations = (state.data?.generations || []).map((value) => Number(value)).filter(Boolean);
  if (!generations.length) {
    return { min: null, max: null };
  }
  return {
    min: Math.min(...generations),
    max: Math.max(...generations),
  };
}

function needsParentLink(person) {
  if (!person || !state.data) return false;
  const generation = Number(person.generation || 0);
  const { min, max } = generationRangeBounds();
  if (!generation || min === null || max === null) return false;
  if (generation <= min || generation > max) return false;
  return !incomingEdgeForChild(person.id);
}

function computeCompletionForData(data) {
  const generations = (data?.generations || data?.persons || [])
    .map((value) => (typeof value === "number" ? value : Number(value?.generation || 0)))
    .filter(Boolean);
  if (!generations.length) {
    return { ready: false, min_generation: null, missing_people: [] };
  }
  const minGeneration = Math.min(...generations);
  const incoming = new Set((data?.edges || []).map((edge) => edge.to_person_id));
  const missingPeople = (data?.persons || [])
    .filter((person) => {
      const generation = Number(person.generation || 0);
      return generation > minGeneration && !incoming.has(person.id);
    })
    .map((person) => {
      const refs = allTextRefs(person).slice().sort((a, b) => Number(a.page) - Number(b.page));
      return {
        person_id: person.id,
        group_id: person.source_group_id || data.group_id || null,
        name: person.name || person.id,
        generation: Number(person.generation || 0),
        page: Number(refs[0]?.page || 0) || null,
      };
    })
    .sort((a, b) => (a.page || 9999) - (b.page || 9999) || a.generation - b.generation || a.name.localeCompare(b.name, "zh-Hans-CN"));
  return {
    ready: missingPeople.length === 0,
    min_generation: minGeneration,
    missing_people: missingPeople,
  };
}

async function buildMergeControlClientSide() {
  const action = nextMergeActionContext();
  if (!action) return null;
  const [left, right] = await Promise.all([
    fetchWorkspace(action.source_group_ids.length === 1 ? action.source_group_ids[0] : buildMergeWorkspaceId(action.source_group_ids)),
    fetchWorkspace(action.next_group_id),
  ]);
  const leftCompletion = computeCompletionForData(left);
  const rightCompletion = computeCompletionForData(right);
  let firstMissing = null;
  if (!leftCompletion.ready) {
    firstMissing = { group_id: leftCompletion.missing_people[0].group_id, ...leftCompletion.missing_people[0] };
  } else if (!rightCompletion.ready) {
    firstMissing = { group_id: rightCompletion.missing_people[0].group_id, ...rightCompletion.missing_people[0] };
  }
  return {
    key: action.key,
    workspace_id: action.target_workspace_id,
    ready: leftCompletion.ready && rightCompletion.ready,
    left_group: { group_id: action.source_group_ids[0], group_ids: action.source_group_ids, label: action.left_label, ...leftCompletion },
    right_group: { group_id: action.next_group_id, group_ids: [action.next_group_id], label: action.right_label, ...rightCompletion },
    first_missing: firstMissing,
  };
}

async function ensureMergeControl() {
  const action = nextMergeActionContext();
  if (!action) return null;
  if (state.data?.merge_control && state.data.merge_control.key === action.key) {
    return state.data.merge_control;
  }
  const mergeControl = await buildMergeControlClientSide();
  if (state.data) {
    state.data.merge_control = mergeControl;
  }
  updateOverlayHint();
  return mergeControl;
}

function nextAutoPersonId(generation) {
  const used = new Set(state.data.persons.map((person) => person.id));
  let index = state.data.persons.length + 1;
  let candidate = `p_auto_${generation}_${index}`;
  while (used.has(candidate)) {
    index += 1;
    candidate = `p_auto_${generation}_${index}`;
  }
  return candidate;
}

function nextManualPersonName() {
  const existing = new Set(state.data.persons.map((person) => normalizeName(person.name)));
  let index = 1;
  let candidate = `待补人物${index}`;
  while (existing.has(candidate)) {
    index += 1;
    candidate = `待补人物${index}`;
  }
  return candidate;
}

function normalizeName(value) {
  return (value || "").trim();
}

function isManualPerson(person, page = state.page) {
  const ref = refForPage(person, page);
  return String(ref?.index || "").startsWith("manual_") || (person.notes || []).includes("手动新增");
}

function findPersonByNameAcrossGroup(name) {
  const target = normalizeName(name);
  if (!target) return null;
  return state.data.persons.find((person) => normalizeName(person.name) === target) || null;
}

function setStatus(text) {
  statusText.textContent = text;
}

function snapshotState() {
  return JSON.parse(JSON.stringify(state.data));
}

function isLargeWorkspaceData(data = state.data) {
  return Boolean(data && Array.isArray(data.persons) && data.persons.length >= LARGE_WORKSPACE_HISTORY_PERSON_THRESHOLD);
}

function clearHistoryStack() {
  historyStack.length = 0;
}

function refreshUndoAvailability() {
  if (!undoBtn) return;
  undoBtn.disabled = isLargeWorkspaceData() || historyStack.length === 0;
}

function pushHistorySnapshot() {
  if (!state.data) return;
  if (isLargeWorkspaceData()) {
    clearHistoryStack();
    refreshUndoAvailability();
    return;
  }
  historyStack.push(snapshotState());
  if (historyStack.length > HISTORY_LIMIT) {
    historyStack.shift();
  }
  refreshUndoAvailability();
}

function pushProvidedSnapshot(snapshot) {
  if (!snapshot) return;
  if (isLargeWorkspaceData()) {
    clearHistoryStack();
    refreshUndoAvailability();
    return;
  }
  historyStack.push(snapshot);
  if (historyStack.length > HISTORY_LIMIT) {
    historyStack.shift();
  }
  refreshUndoAvailability();
}

function undoLastChange() {
  if (isLargeWorkspaceData()) {
    setStatus("当前大组已关闭整组回退，避免浏览器内存占用过高。");
    refreshUndoAvailability();
    return;
  }
  if (!historyStack.length) {
    setStatus("没有可回退的操作。");
    return;
  }
  state.data = historyStack.pop();
  if (!state.data.pages_data) {
    state.data.pages_data = synthesizePagesData(state.data);
  }
  ensureActivePersonForPage();
  switchPage(state.page);
  setStatus("已回退一步。");
  refreshUndoAvailability();
  scheduleAutoSave(0);
}

function setCookie(name, value, days = 30) {
  const expires = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

function toChineseNumber(num) {
  const digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"];
  if (num < 10) return digits[num];
  if (num < 20) return num === 10 ? "十" : `十${digits[num % 10]}`;
  if (num < 100) {
    const tens = Math.floor(num / 10);
    const ones = num % 10;
    return `${digits[tens]}十${ones ? digits[ones] : ""}`;
  }
  if (num === 100) return "一百";
  if (num < 110) return `一百零${digits[num % 10]}`;
  if (num < 200) {
    const tens = Math.floor((num % 100) / 10);
    const ones = num % 10;
    return `一百${tens ? digits[tens] + "十" : ""}${ones ? digits[ones] : ""}`;
  }
  return String(num);
}

function updateGroupChrome() {
  const generations = state.data?.generations || [];
  if (groupTitle) {
    if (state.data?.label) {
      groupTitle.textContent = state.data.label;
    } else if (generations.length >= 2) {
      groupTitle.textContent = `${toChineseNumber(generations[0])}世至${toChineseNumber(generations[generations.length - 1])}世校对`;
    } else {
      groupTitle.textContent = "家谱校对";
    }
  }
  if (generationRail) {
    generationRail.innerHTML = generations.map((gen) => `<div>${gen}世</div>`).join("");
  }
  if (groupSwitch) {
    const active = state.data?.group_id || currentGroupId();
    groupSwitch.innerHTML = `
      <label class="group-switch-label" for="groupSwitchSelect">世代分组</label>
      <select id="groupSwitchSelect" class="group-switch-select" aria-label="分组切换">
        ${GROUPS.map((group) => `<option value="${group.id}" ${group.id === active ? "selected" : ""}>${group.label}</option>`).join("")}
      </select>
    `;
    const select = document.getElementById("groupSwitchSelect");
    select?.addEventListener("change", (event) => {
      const nextGroupId = event.target.value;
      if (!nextGroupId || nextGroupId === active) return;
      window.location.href = `/?group=${encodeURIComponent(nextGroupId)}`;
    });
  }
}

function getCookie(name) {
  const prefix = `${name}=`;
  return document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(prefix))
    ?.slice(prefix.length) || "";
}

function markCurrentPageDirty() {
  if (!state.data) return;
  dirtyPages.add(Number(state.page));
}

function currentPageIsDirty() {
  return dirtyPages.has(Number(state.page));
}

async function flushAutoSave() {
  if (!state.data || !currentPageIsDirty() || autoSaveInFlight) return;
  autoSaveInFlight = true;
  try {
    await saveData(true);
  } catch (error) {
    setStatus(`自动保存失败：${error.message}`);
  } finally {
    autoSaveInFlight = false;
    if (currentPageIsDirty()) {
      scheduleAutoSave(1200);
    }
  }
}

function scheduleAutoSave(delayMs = 1200) {
  markCurrentPageDirty();
  if (autoSaveTimer) {
    clearTimeout(autoSaveTimer);
  }
  autoSaveTimer = setTimeout(() => {
    autoSaveTimer = null;
    void flushAutoSave();
  }, Math.max(0, Number(delayMs) || 0));
}

function requestGraphRender(fullGraph = false) {
  if (graphRenderQueued) return;
  graphRenderQueued = true;
  requestAnimationFrame(() => {
    graphRenderQueued = false;
    renderGraph(fullGraph);
  });
}

function fieldDraftKey(target) {
  const field = target?.dataset?.field || target?.dataset?.edgeKey || "";
  const id = target?.dataset?.personId || target?.dataset?.edgeKey || "";
  return `${id}:${field}`;
}

function onEditableFieldFocus(event) {
  const target = event.target;
  fieldDraftBaseline.set(fieldDraftKey(target), target.value);
}

function updateOverlayHint() {
  const person = activePerson();
  const parent = linkParentPerson();
  const expectedChildGeneration = parent ? Number(parent.generation || 0) + 1 : null;
  const locked = pagePeopleLocked();
  if (state.linkMode) {
    overlayHint.textContent = parent
      ? `补链模式：当前父节点是 ${parent.name || parent.id}。只可选择第 ${expectedChildGeneration} 世作为“子”；兄弟顺序按右到左自动编号。`
      : "补链模式：先点图上的父节点，再点子节点；兄弟顺序按右到左自动编号。";
  } else if (locked) {
    overlayHint.textContent = "当前页人物区已锁定。可继续进行父子补链，人物姓名与框位置不再编辑。";
  } else {
    overlayHint.textContent = person
      ? `当前选中：${person.name || person.id}。点左图文字框可绑定；也可直接粘贴截图。`
      : "先选右侧人物，再点左图文字框绑定；也可选中人物后直接粘贴截图。";
  }
  linkModeBtn.classList.toggle("toggle-active", state.linkMode);
  imagePanel.classList.toggle("linking-mode", state.linkMode);
  finishLinkBtn.disabled = !state.linkMode || !state.linkParentPersonId;
  if (fullscreenLinkModeBtn) {
    fullscreenLinkModeBtn.classList.toggle("toggle-active", state.linkMode);
  }
  if (fullscreenFinishLinkBtn) {
    fullscreenFinishLinkBtn.disabled = !state.linkMode || !state.linkParentPersonId;
  }
  if (fullscreenGraphHint) {
    if (state.linkMode) {
      fullscreenGraphHint.textContent = parent
        ? `补链模式：当前父节点是 ${parent.name || parent.id}，只可选第 ${expectedChildGeneration} 世为子。`
        : "补链模式：先点一个父节点，再点子节点。";
    } else {
      fullscreenGraphHint.textContent = state.fullscreenLayoutMode === "page" ? "全屏按页校对" : "全屏按树校对";
    }
  }
  if (fullscreenLayoutModeBtn) {
    fullscreenLayoutModeBtn.textContent = state.fullscreenLayoutMode === "page" ? "按页模式" : "按树模式";
  }
  if (fullscreenBoundaryModeBtn) {
    const mergeMode = isMergeWorkspace();
    const shouldShow = document.fullscreenElement === graphWrap && mergeMode;
    fullscreenBoundaryModeBtn.hidden = !shouldShow;
    fullscreenBoundaryModeBtn.classList.toggle("toggle-active", Boolean(state.fullscreenBoundaryMode));
    fullscreenBoundaryModeBtn.textContent = state.fullscreenBoundaryMode ? "边界视图" : "全量视图";
  }
  graphWrap.classList.toggle("page-layout-mode", state.fullscreenLayoutMode === "page");
  if (fullscreenPageImagePanel) {
    const shouldShow = document.fullscreenElement === graphWrap && state.fullscreenLayoutMode === "page";
    fullscreenPageImagePanel.hidden = !shouldShow;
  }
  if (mergeActionBtn) {
    const mergeAction = nextMergeActionContext();
    const mergeControl = state.data?.merge_control || null;
    const visible = document.fullscreenElement === graphWrap && Boolean(mergeAction);
    mergeActionBtn.hidden = !visible;
    mergeActionBtn.disabled = false;
    if (mergeAction) {
      mergeActionBtn.textContent = mergeControl?.ready
        ? `合并 ${mergeAction.left_label} 与 ${mergeAction.right_label}`
        : `检查后合并 ${mergeAction.left_label} 与 ${mergeAction.right_label}`;
    }
  }
  if (fullscreenDbSyncHint) {
    const shouldShow = document.fullscreenElement === graphWrap && isMergeWorkspace() && Boolean(state.sqliteMirror);
    fullscreenDbSyncHint.hidden = !shouldShow;
    fullscreenDbSyncHint.classList.toggle("is-error", Boolean(state.sqliteMirror && !state.sqliteMirror.ok));
    if (state.sqliteMirror) {
      fullscreenDbSyncHint.textContent = state.sqliteMirror.ok
        ? `数据库已同步 ${state.sqliteMirror.group_count || 0}组/${state.sqliteMirror.person_count || 0}人/${state.sqliteMirror.relationship_count || 0}边`
        : `数据库同步失败：${state.sqliteMirror.error || "未知错误"}`;
    }
  }
  renderFullscreenParentPanel();
}

function updateImage() {
  const entry = pageEntry(state.page);
  updateOverlayHint();
  pageImage.src = entry.image;
  renderOcrOverlay();
}

function renderFullscreenParentPanel() {
  if (!fullscreenParentPanel || !fullscreenParentList) return;
  const mergeMode = isMergeWorkspace();
  const shouldShow =
    document.fullscreenElement === graphWrap &&
    mergeMode &&
    Boolean(state.fullscreenBoundaryMode);
  fullscreenParentPanel.hidden = !shouldShow;
  if (!shouldShow) return;

  const candidates = mergeParentCandidates();
  const query = String(state.fullscreenParentCandidateQuery || "").trim().toLowerCase();
  const filtered = query
    ? candidates.filter((item) => {
        const name = String(item.person.name || "").toLowerCase();
        return name.includes(query) || String(item.sourcePage).includes(query);
      })
    : candidates;

  if (fullscreenParentPanelTitle) {
    fullscreenParentPanelTitle.textContent = "父候选（107世）";
  }
  if (fullscreenParentPanelCount) {
    fullscreenParentPanelCount.textContent = `${filtered.length}/${candidates.length}`;
  }

  const pageGroups = new Map();
  filtered.forEach((item) => {
    const key = item.sourcePage;
    if (!pageGroups.has(key)) pageGroups.set(key, []);
    pageGroups.get(key).push(item);
  });
  const groupEntries = [...pageGroups.entries()].sort((a, b) => Number(a[0]) - Number(b[0]));
  fullscreenParentList.innerHTML = groupEntries
    .map(([sourcePage, items]) => {
      const rows = items
        .map((item) => {
          const active = item.person.id === state.linkParentPersonId ? " active" : "";
          return `
            <button type="button" class="parent-candidate-item${active}" data-parent-candidate="${item.person.id}">
              <span class="parent-candidate-name">${escapeHtml(item.person.name || item.person.id)}</span>
              <span class="parent-candidate-meta">第${sourcePage}页</span>
            </button>
          `;
        })
        .join("");
      return `
        <section class="parent-page-group">
          <div class="parent-page-title">第${sourcePage}页</div>
          ${rows}
        </section>
      `;
    })
    .join("");

  fullscreenParentList.querySelectorAll("[data-parent-candidate]").forEach((button) => {
    button.addEventListener("click", () => {
      const personId = button.dataset.parentCandidate;
      if (!personId) return;
      state.fullscreenSelectedPersonId = personId;
      startLinkParent(personId, "已选父候选");
      renderGraph(true);
    });
  });
}

function renderFullscreenPageImages({ pages, pageWidthMap, width, pageGap, rightMargin }) {
  if (!fullscreenPageImageStrip) return;
  const mergeMode = isMergeWorkspace();
  const shouldShow = document.fullscreenElement === graphWrap && state.fullscreenLayoutMode === "page";
  if (!shouldShow) {
    fullscreenPageImageStrip.innerHTML = "";
    fullscreenPageImageStrip.removeAttribute("style");
    return;
  }
  const zoom = state.graphZoom || 1;
  const visualWidth = Math.round(width * zoom);
  const visualGap = Math.round(pageGap * zoom);
  const visualRightMargin = Math.round(rightMargin * zoom);
  const anchorGroupId = state.data?.anchor_group_id || null;
  let orderedPages = mergeMode
    ? pages
        .filter((page) => {
          if (anchorGroupId) {
            return pageEntry(page)?.source_group_id === anchorGroupId;
          }
          return ["bottom", "single"].includes(mergeRowKeyForPage(page));
        })
        .slice()
        .sort((a, b) => Number(b) - Number(a))
    : pages.slice().reverse();
  if (mergeMode && !orderedPages.length) {
    orderedPages = pages
      .filter((page) => ["bottom", "single"].includes(mergeRowKeyForPage(page)))
      .slice()
      .sort((a, b) => Number(b) - Number(a));
  }
  orderedPages = orderedPages.filter((page) => Boolean(pageEntry(page)?.image));

  fullscreenPageImageStrip.style.width = `${visualWidth}px`;
  fullscreenPageImageStrip.style.gap = `${visualGap}px`;
  fullscreenPageImageStrip.style.paddingRight = `${visualRightMargin}px`;
  fullscreenPageImageStrip.style.justifyContent = "flex-end";
  fullscreenPageImageStrip.innerHTML = orderedPages
    .map((page) => {
      const entry = pageEntry(page);
      const itemWidth = Math.round((pageWidthMap.get(page) || 220) * zoom);
      return `
        <figure class="fullscreen-page-image-item${Number(page) === Number(state.page) ? " active" : ""}" data-fullscreen-page="${page}" style="width:${itemWidth}px">
          <figcaption class="fullscreen-page-image-caption">${mergeMode ? `${pageDisplayLabel(page)}原稿` : pageDisplayLabel(page)}</figcaption>
          <img src="${escapeHtml(entry?.image || "")}" alt="${pageDisplayLabel(page)}完整原图" />
        </figure>
      `;
    })
    .join("");
  fullscreenPageImageStrip.querySelectorAll("[data-fullscreen-page]").forEach((node) => {
    node.addEventListener("click", () => {
      setCurrentPageFromFullscreen(Number(node.dataset.fullscreenPage));
      updateOverlayHint();
      renderGraph(true);
    });
  });
}

function scrollFullscreenToCurrentPage() {
  if (document.fullscreenElement !== graphWrap) return;
  requestAnimationFrame(() => {
    const target =
      graphWrap.querySelector(`[data-page-anchor="${state.page}"]`) ||
      graphWrap.querySelector(`[data-fullscreen-page="${state.page}"]`) ||
      graphWrap.querySelector(`[data-fullscreen-page]`);
    if (!target) return;
    const wrapRect = graphWrap.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const deltaLeft = targetRect.left - wrapRect.left;
    graphWrap.scrollLeft += deltaLeft - (wrapRect.width - targetRect.width) / 2;
  });
}

function updatePageControls() {
  const entry = pageEntry(state.page);
  pageRoleInput.value = entry.page_role || "";
  keepAxisSelect.value = entry.keep_generation_axis ? "true" : "false";
  pageNotesInput.value = (entry.manual_notes || []).join("\n");
  const mergeMode = isMergeWorkspace();
  if (peopleLockBtn) {
    const locked = Boolean(entry.people_locked);
    peopleLockBtn.textContent = mergeMode ? "合并模式仅补父子链" : locked ? "解除人物区锁定" : "锁定人物区";
    peopleLockBtn.classList.toggle("locked", locked || mergeMode);
    peopleLockBtn.disabled = mergeMode;
  }
  if (addPersonBtn) {
    addPersonBtn.disabled = Boolean(entry.people_locked) || mergeMode;
  }
}

function makeGlyphFromBox(item) {
  if (!pageImage.naturalWidth || !pageImage.naturalHeight) {
    return null;
  }
  const [x1, y1, x2, y2] = item.box || [];
  if ([x1, y1, x2, y2].some((value) => !Number.isFinite(value))) {
    return null;
  }
  const padding = 12;
  const sx = Math.max(0, Math.floor(x1 - padding));
  const sy = Math.max(0, Math.floor(y1 - padding));
  const sw = Math.min(pageImage.naturalWidth - sx, Math.ceil(x2 - x1 + padding * 2));
  const sh = Math.min(pageImage.naturalHeight - sy, Math.ceil(y2 - y1 + padding * 2));
  const canvas = document.createElement("canvas");
  canvas.width = sw;
  canvas.height = sh;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(pageImage, sx, sy, sw, sh, 0, 0, sw, sh);
  return canvas.toDataURL("image/png");
}

function makeGlyphFromRawBox(box) {
  if (!pageImage.naturalWidth || !pageImage.naturalHeight) {
    return null;
  }
  const [x1, y1, x2, y2] = box || [];
  if ([x1, y1, x2, y2].some((value) => !Number.isFinite(value))) {
    return null;
  }
  return makeGlyphFromBox({ box });
}

function refreshGlyphImagesForCurrentPage() {
  if (!state.data || !pageImage.naturalWidth || !pageImage.naturalHeight) {
    return 0;
  }
  let updated = 0;
  peopleForPage(state.page).forEach((person) => {
    const ref = refForPage(person, state.page);
    if (!ref?.box) return;
    const nextGlyph = makeGlyphFromRawBox(ref.box);
    if (!nextGlyph || nextGlyph === person.glyph_image) return;
    person.glyph_image = nextGlyph;
    updated += 1;
  });
  return updated;
}

function refCenter(ref) {
  const [x1, y1, x2, y2] = ref.box || [];
  if ([x1, y1, x2, y2].some((value) => !Number.isFinite(value))) {
    return null;
  }
  return {
    x: ((x1 + x2) / 2 / pageImage.naturalWidth) * 100,
    y: ((y1 + y2) / 2 / pageImage.naturalHeight) * 100,
  };
}

function clientToImagePoint(clientX, clientY) {
  const rect = imageStage.getBoundingClientRect();
  if (!rect.width || !rect.height || !pageImage.naturalWidth || !pageImage.naturalHeight) {
    return null;
  }
  const x = ((clientX - rect.left) / rect.width) * pageImage.naturalWidth;
  const y = ((clientY - rect.top) / rect.height) * pageImage.naturalHeight;
  return {
    x: Math.max(0, Math.min(pageImage.naturalWidth, x)),
    y: Math.max(0, Math.min(pageImage.naturalHeight, y)),
  };
}

function defaultManualBox() {
  const width = pageImage.naturalWidth || 1400;
  const height = pageImage.naturalHeight || 1900;
  const boxWidth = Math.max(90, Math.round(width * 0.08));
  const boxHeight = Math.max(120, Math.round(height * 0.12));
  const x1 = Math.round(width * 0.42);
  const y1 = Math.round(height * 0.42);
  return [x1, y1, x1 + boxWidth, y1 + boxHeight];
}

function syncPersonRefBox(person, box) {
  const ref = refForPage(person, state.page);
  if (!ref) return;
  ref.box = box.map((value) => Math.round(value));
  ref.poly = [
    [ref.box[0], ref.box[1]],
    [ref.box[2], ref.box[1]],
    [ref.box[2], ref.box[3]],
    [ref.box[0], ref.box[3]],
  ];
  if (person.text_ref && Number(person.text_ref.page) === state.page) {
    person.text_ref = ref;
  }
  person.position_hints = (person.position_hints || []).filter((hint) => Number(hint.page) !== Number(state.page));
  person.position_hints.push({ page: state.page, box: ref.box });
}

function edgeForPair(fromId, toId) {
  return state.data.edges.find((edge) => edge.from_person_id === fromId && edge.to_person_id === toId) || null;
}

function edgeKey(fromId, toId) {
  return `${fromId}__${toId}`;
}

function clearLinkDeleteHoverTimer() {
  if (linkDeleteHoverTimer) {
    clearTimeout(linkDeleteHoverTimer);
    linkDeleteHoverTimer = null;
  }
}

function setLinkDeleteEdgeKey(nextKey, fullGraph = isGraphFullscreen()) {
  if (state.linkDeleteEdgeKey === nextKey) return;
  state.linkDeleteEdgeKey = nextKey || null;
  requestGraphRender(fullGraph);
}

function clearLinkDeleteControl(fullGraph = isGraphFullscreen()) {
  clearLinkDeleteHoverTimer();
  setLinkDeleteEdgeKey(null, fullGraph);
}

function deleteEdgeFromLinkMode(fromId, toId) {
  const edge = edgeForPair(fromId, toId);
  if (!edge) {
    clearLinkDeleteControl(true);
    return false;
  }
  pushHistorySnapshot();
  if ((edge.page_sources || []).includes(state.page) && (edge.page_sources || []).length > 1) {
    edge.page_sources = (edge.page_sources || []).filter((page) => Number(page) !== Number(state.page));
  } else {
    state.data.edges = state.data.edges.filter(
      (item) => !(item.from_person_id === fromId && item.to_person_id === toId),
    );
  }
  if (state.linkChildPersonId === toId) {
    state.linkChildPersonId = null;
  }
  clearLinkDeleteControl(true);
  const parentName = state.data?.persons.find((person) => person.id === fromId)?.name || fromId;
  const childName = state.data?.persons.find((person) => person.id === toId)?.name || toId;
  setStatus(`已删除父子链：${parentName} -> ${childName}`);
  if (isGraphFullscreen()) {
    requestGraphRender(true);
  } else {
    renderEdges();
    requestGraphRender(false);
  }
  scheduleAutoSave();
  return true;
}

function recomputeSiblingOrderForParent(parentId, page) {
  const children = state.data.edges
    .filter((edge) => edge.from_person_id === parentId)
    .map((edge) => {
      const child = state.data.persons.find((person) => person.id === edge.to_person_id);
      const ref = child ? refForPage(child, page) : null;
      return { edge, ref };
    })
    .filter((item) => item.ref)
    .sort((a, b) => {
      const ax = (a.ref.box[0] + a.ref.box[2]) / 2;
      const bx = (b.ref.box[0] + b.ref.box[2]) / 2;
      return bx - ax;
    });
  children.forEach((item, index) => {
    item.edge.birth_order_under_parent = index + 1;
  });
}

function canSelectAsChild(parentId, childId) {
  const parent = state.data?.persons.find((person) => person.id === parentId) || null;
  const child = state.data?.persons.find((person) => person.id === childId) || null;
  if (!parent || !child) {
    return { ok: false, reason: "未找到父或子人物。" };
  }
  if (parentId === childId) {
    return { ok: false, reason: "父和子不能是同一人物。" };
  }
  const parentGeneration = Number(parent.generation || 0);
  const childGeneration = Number(child.generation || 0);
  if (!parentGeneration || !childGeneration) {
    return { ok: false, reason: "父或子的世代缺失，不能补链。" };
  }
  if (childGeneration !== parentGeneration + 1) {
    return {
      ok: false,
      reason: `当前父节点是第 ${parentGeneration} 世，只能选择第 ${parentGeneration + 1} 世作为子。`,
    };
  }
  return { ok: true };
}

function isChildCandidate(personId) {
  if (!state.linkMode || !state.linkParentPersonId) return false;
  return canSelectAsChild(state.linkParentPersonId, personId).ok;
}

function startLinkParent(personId, statusPrefix = "已选父节点") {
  const parent = state.data?.persons.find((person) => person.id === personId) || null;
  if (!parent) return;
  state.linkParentPersonId = personId;
  state.linkChildPersonId = null;
  clearLinkDeleteControl(true);
  updateOverlayHint();
  if (isGraphFullscreen()) {
    if (!refreshFullscreenLinkSelectionClasses()) {
      requestGraphRender(true);
    }
  } else {
    renderPersons();
    renderOcrOverlay();
    requestGraphRender(false);
  }
  setStatus(`${statusPrefix}：${parent.name || parent.id}。继续点子节点。`);
}

function completeLinkToChild(childId, note = "图上补链", includeCurrentPage = true) {
  const validation = canSelectAsChild(state.linkParentPersonId, childId);
  if (!validation.ok) {
    setStatus(validation.reason);
    return false;
  }
  let edge = edgeForPair(state.linkParentPersonId, childId);
  if (!edge) {
    pushHistorySnapshot();
    edge = {
      from_person_id: state.linkParentPersonId,
      to_person_id: childId,
      relation: "parent_child",
      page_sources: includeCurrentPage ? [state.page] : [],
      confidence: "manual",
      notes: [note],
    };
    state.data.edges.push(edge);
  } else if (includeCurrentPage && !(edge.page_sources || []).includes(state.page)) {
    edge.page_sources = [...new Set([...(edge.page_sources || []), state.page])];
  }
  recomputeSiblingOrderForParent(state.linkParentPersonId, state.page);
  state.linkChildPersonId = childId;
  clearLinkDeleteControl(true);
  const parentName = linkParentPerson()?.name || state.linkParentPersonId;
  const childName =
    state.data?.persons.find((person) => person.id === childId)?.name || childId;
  setStatus(`已补链：${parentName} -> ${childName}，兄弟顺序已按右到左更新。`);
  if (isGraphFullscreen()) {
    requestGraphRender(true);
  } else {
    renderPersons();
    renderEdges();
    renderOcrOverlay();
    requestGraphRender(false);
  }
  scheduleAutoSave();
  return true;
}

function computeGlobalTreeLayout(graphNodes, graphEdges) {
  const peopleById = new Map(graphNodes.map((person) => [person.id, person]));
  const childMap = new Map();
  const incoming = new Map();
  const refMap = new Map();
  graphEdges.forEach((edge) => {
    if (!childMap.has(edge.from_person_id)) {
      childMap.set(edge.from_person_id, []);
    }
    childMap.get(edge.from_person_id).push(edge);
    if (!incoming.has(edge.to_person_id)) {
      incoming.set(edge.to_person_id, []);
    }
    incoming.get(edge.to_person_id).push(edge);
  });

  childMap.forEach((edges, parentId) => {
    childMap.set(parentId, sortChildrenForTree(edges, peopleById));
  });

  const generations = [...new Set(graphNodes.map((person) => Number(person.generation || 0)).filter(Boolean))].sort((a, b) => a - b);
  const generationIndex = new Map(generations.map((gen, index) => [gen, index]));
  const pages = (state.data?.pages || [])
    .filter((page) => graphNodes.some((person) => refForPage(person, page)))
    .sort((a, b) => a - b);
  const nodePageMap = new Map();
  graphNodes.forEach((person) => {
    const refs = allTextRefs(person).slice().sort((a, b) => Number(a.page) - Number(b.page));
    const ref = refs[0] || null;
    refMap.set(person.id, ref);
    nodePageMap.set(person.id, ref?.page && pages.includes(Number(ref.page)) ? Number(ref.page) : pages[0]);
  });

  const roots = buildRootOrder(graphNodes, incoming).sort((a, b) => {
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

  roots
    .slice()
    .reverse()
    .forEach((root, index) => {
      assignSlots(root.id);
      if (index !== roots.length - 1) slot += 20 / 76;
    });

  graphNodes
    .filter((person) => !slotPositions.has(person.id))
    .forEach((person) => assignSlots(person.id));

  const maxSlot = Math.max(...[...slotPositions.values(), 0]);
  const treeOrderByGeneration = new Map();
  generations.forEach((gen) => {
    const generationPeople = graphNodes
      .filter((person) => Number(person.generation) === gen)
      .slice()
      .sort((a, b) => {
        const slotA = slotPositions.get(a.id) ?? -1;
        const slotB = slotPositions.get(b.id) ?? -1;
        return slotB - slotA || (a.name || "").localeCompare(b.name || "", "zh-Hans-CN");
      });
    treeOrderByGeneration.set(gen, generationPeople.map((person) => person.id));
  });

  return {
    peopleById,
    childMap,
    incoming,
    refMap,
    generations,
    generationIndex,
    pages,
    nodePageMap,
    roots,
    slotPositions,
    maxSlot,
    treeOrderByGeneration,
  };
}

function treeOrderedPeopleForPage(page) {
  const fullGraph = buildGraphData(true);
  const layout = computeGlobalTreeLayout(fullGraph.nodes, fullGraph.edges);
  const pageIds = new Set(peopleForPage(page).map((person) => person.id));
  return fullGraph.nodes
    .filter((person) => pageIds.has(person.id))
    .sort((a, b) => {
      const genA = Number(a.generation || 999);
      const genB = Number(b.generation || 999);
      if (genA !== genB) return genA - genB;
      const slotA = layout.slotPositions.get(a.id) ?? -1;
      const slotB = layout.slotPositions.get(b.id) ?? -1;
      return slotB - slotA || (a.name || "").localeCompare(b.name || "", "zh-Hans-CN");
    });
}

function appendGraphRoleBadge(nodeGroup, x, y, label, kind) {
  const badgeGroup = createSvgNode("g", {
    class: `graph-role-badge-group graph-role-badge-group-${kind}`,
  });
  const width = 22;
  const height = 22;
  badgeGroup.appendChild(createSvgNode("rect", {
    x: String(x - width / 2),
    y: String(y - height / 2),
    width: String(width),
    height: String(height),
    rx: "11",
    class: `graph-role-badge graph-role-badge-${kind}`,
  }));
  const text = createSvgNode("text", {
    x: String(x),
    y: String(y + 4),
    "text-anchor": "middle",
    class: "graph-role-badge-text",
  });
  text.textContent = label;
  badgeGroup.appendChild(text);
  nodeGroup.appendChild(badgeGroup);
}

function renderOverlayLines(linesLayer) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${pageImage.naturalWidth} ${pageImage.naturalHeight}`);
  svg.setAttribute("class", "ocr-lines");
  const pagePeople = peopleForPage(state.page);
  const pageIds = new Set(pagePeople.map((person) => person.id));
  state.data.edges
    .filter((edge) => pageIds.has(edge.from_person_id) || pageIds.has(edge.to_person_id))
    .forEach((edge) => {
      const parent = state.data.persons.find((person) => person.id === edge.from_person_id);
      const child = state.data.persons.find((person) => person.id === edge.to_person_id);
      const parentRef = parent ? refForPage(parent, state.page) : null;
      const childRef = child ? refForPage(child, state.page) : null;
      if (!parentRef || !childRef) return;
      const p = refCenter(parentRef);
      const c = refCenter(childRef);
      if (!p || !c) return;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      const pX = (p.x / 100) * pageImage.naturalWidth;
      const pY = (p.y / 100) * pageImage.naturalHeight;
      const cX = (c.x / 100) * pageImage.naturalWidth;
      const cY = (c.y / 100) * pageImage.naturalHeight;
      const midY = pY + (cY - pY) * 0.5;
      const midX = pX + (cX - pX) * 0.5;
      const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
      group.setAttribute("class", "ocr-link-group");
      path.setAttribute("d", `M ${pX} ${pY} C ${pX} ${midY}, ${cX} ${midY}, ${cX} ${cY}`);
      path.setAttribute("class", "ocr-link-line");
      group.appendChild(path);

      const deleteGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
      deleteGroup.setAttribute("class", "ocr-link-delete");
      deleteGroup.setAttribute("transform", `translate(${midX}, ${midY})`);

      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("r", "11");
      circle.setAttribute("class", "ocr-link-delete-circle");
      deleteGroup.appendChild(circle);

      const mark1 = document.createElementNS("http://www.w3.org/2000/svg", "line");
      mark1.setAttribute("x1", "-4");
      mark1.setAttribute("y1", "-4");
      mark1.setAttribute("x2", "4");
      mark1.setAttribute("y2", "4");
      mark1.setAttribute("class", "ocr-link-delete-mark");
      deleteGroup.appendChild(mark1);

      const mark2 = document.createElementNS("http://www.w3.org/2000/svg", "line");
      mark2.setAttribute("x1", "4");
      mark2.setAttribute("y1", "-4");
      mark2.setAttribute("x2", "-4");
      mark2.setAttribute("y2", "4");
      mark2.setAttribute("class", "ocr-link-delete-mark");
      deleteGroup.appendChild(mark2);

      deleteGroup.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        pushHistorySnapshot();
        const before = state.data.edges.length;
        state.data.edges = state.data.edges.filter(
          (item) => !(item.from_person_id === edge.from_person_id && item.to_person_id === edge.to_person_id),
        );
        if (state.data.edges.length !== before) {
          setStatus(`已删除父子链：${parent?.name || edge.from_person_id} -> ${child?.name || edge.to_person_id}`);
          renderEdges();
          renderOcrOverlay();
          requestGraphRender(document.fullscreenElement === graphWrap);
          scheduleAutoSave();
        }
      });

      group.appendChild(deleteGroup);
      svg.appendChild(group);
    });
  const parent = linkParentPerson();
  const parentRef = parent ? refForPage(parent, state.page) : null;
  if (parentRef) {
    const [x1, y1, x2, y2] = parentRef.box;
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", x1);
    rect.setAttribute("y", y1);
    rect.setAttribute("width", x2 - x1);
    rect.setAttribute("height", y2 - y1);
    rect.setAttribute("rx", 12);
    rect.setAttribute("class", "ocr-link-parent");
    svg.appendChild(rect);
  }
  linesLayer.appendChild(svg);
}

function renderPersonOverlayBox(person, ref, assignedClass = "assigned") {
  const [x1, y1, x2, y2] = ref.box || [];
  if ([x1, y1, x2, y2].some((value) => !Number.isFinite(value))) {
    return null;
  }
  const box = document.createElement("button");
  box.type = "button";
  const isManual = String(ref.index || "").startsWith("manual_");
  box.className = `ocr-box ${assignedClass}${isManual ? " manual" : ""}`;
  if (person.id === state.activePersonId || person.id === state.linkParentPersonId) {
    box.classList.add("active");
  }
  if (state.linkChildPersonId === person.id) {
    box.classList.add("linked-child");
  }
  if (isChildCandidate(person.id)) {
    box.classList.add("link-candidate");
  }
  if (needsParentLink(person)) {
    box.classList.add("needs-parent-link");
  }
  box.style.left = `${(x1 / pageImage.naturalWidth) * 100}%`;
  box.style.top = `${(y1 / pageImage.naturalHeight) * 100}%`;
  box.style.width = `${((x2 - x1) / pageImage.naturalWidth) * 100}%`;
  box.style.height = `${((y2 - y1) / pageImage.naturalHeight) * 100}%`;
  box.title = person.name || person.id;
  box.innerHTML = `<span class="ocr-box-label">${escapeHtml(ref.text || person.name || "")}<span class="ocr-box-owner">→ ${escapeHtml(person.name || person.id)}</span></span>`;
  if (state.linkParentPersonId === person.id) {
    const badge = document.createElement("span");
    badge.className = "ocr-role-badge parent";
    badge.textContent = "父";
    box.appendChild(badge);
  } else if (state.linkChildPersonId === person.id) {
    const badge = document.createElement("span");
    badge.className = "ocr-role-badge child";
    badge.textContent = "子";
    box.appendChild(badge);
  } else if (needsParentLink(person)) {
    const badge = document.createElement("span");
    badge.className = "ocr-role-badge missing-parent";
    badge.textContent = "缺父";
    box.appendChild(badge);
  }

  box.addEventListener("mousedown", (event) => {
    if (pagePeopleLocked() && !state.linkMode) {
      event.preventDefault();
      event.stopPropagation();
      setStatus("当前页人物区已锁定，不能再拖动或改框。");
      return;
    }
    if (event.target.closest(".ocr-handle")) {
      state.dragAction = {
        type: "resize",
        personId: person.id,
        start: clientToImagePoint(event.clientX, event.clientY),
        startBox: [...ref.box],
        moved: false,
        snapshot: isLargeWorkspaceData() ? null : snapshotState(),
      };
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (event.button !== 0) return;
    state.dragAction = {
      type: "move",
      personId: person.id,
      start: clientToImagePoint(event.clientX, event.clientY),
      startBox: [...ref.box],
      moved: false,
      snapshot: isLargeWorkspaceData() ? null : snapshotState(),
    };
    box.classList.add("dragging");
    event.preventDefault();
  });

  const handle = document.createElement("span");
  handle.className = "ocr-handle";
  box.appendChild(handle);
  return box;
}

function renderOcrOverlay() {
  ocrOverlay.innerHTML = "";
  if (!pageImage.naturalWidth || !pageImage.naturalHeight) {
    return;
  }
  const linesLayer = document.createElement("div");
  renderOverlayLines(linesLayer);
  ocrOverlay.appendChild(linesLayer);
  const assigned = assignedTextRefMapForPage(state.page);
  const currentActive = activePerson();
  const items = textItemsForPage(state.page);
  const renderedAssigned = new Set();
  items.forEach((item) => {
    const key = `${state.page}:${item.index}`;
    const assignedPersonId = assigned.get(key);
    const owner = assignedPersonId ? state.data.persons.find((person) => person.id === assignedPersonId) : null;
    let box;
    if (owner) {
      const ref = refForPage(owner, state.page) || {
        page: state.page,
        index: item.index,
        text: item.clean_text,
        raw_text: item.text || "",
        box: item.box,
        poly: item.poly || [],
      };
      box = renderPersonOverlayBox(owner, ref, "assigned");
      renderedAssigned.add(owner.id);
    } else {
      const [x1, y1, x2, y2] = item.box || [];
      if ([x1, y1, x2, y2].some((value) => !Number.isFinite(value))) {
        return;
      }
      box = document.createElement("button");
      box.type = "button";
      box.className = "ocr-box unassigned";
      if (currentActive && allTextRefs(currentActive).some((ref) => textRefKey(ref) === key)) {
        box.classList.add("active");
      }
      box.style.left = `${(x1 / pageImage.naturalWidth) * 100}%`;
      box.style.top = `${(y1 / pageImage.naturalHeight) * 100}%`;
      box.style.width = `${((x2 - x1) / pageImage.naturalWidth) * 100}%`;
      box.style.height = `${((y2 - y1) / pageImage.naturalHeight) * 100}%`;
      box.title = item.clean_text;
      box.innerHTML = `<span class="ocr-box-label">${escapeHtml(item.clean_text)}</span>`;
    }
    box.addEventListener("click", () => {
      if (state.linkMode) {
        if (!assignedPersonId) {
          setStatus("补链模式下，请先绑定人物，再点图上节点。");
          return;
        }
        if (!state.linkParentPersonId) {
          startLinkParent(assignedPersonId);
          return;
        }
        if (state.linkParentPersonId === assignedPersonId) {
          finishCurrentLinkParent();
          setStatus("已取消当前父节点选择。");
          return;
        }
        completeLinkToChild(assignedPersonId, "图上补链", true);
        return;
      }
      if (pagePeopleLocked()) {
        setStatus("当前页人物区已锁定，不能再改绑文字框。");
        return;
      }
      const person = activePerson();
      if (assignedPersonId && (!person || assignedPersonId !== owner.id)) {
        setActivePerson(assignedPersonId);
        setStatus(`该文字框已绑定到 ${owner?.name || owner?.id}。`);
        return;
      }
      if (!person) {
        setStatus("请先在右侧选择一个人物，再绑定文字框。");
        return;
      }
      const currentPageRef = refForPage(person, state.page);
      if (currentPageRef && textRefKey(currentPageRef) !== key) {
        const confirmed = window.confirm(
          `当前人物“${person.name || person.id}”已绑定到本页其他方框。\n是否改绑到“${item.clean_text || item.raw_text || "该方框"}”？`,
        );
        if (!confirmed) {
          setStatus("已取消改绑。");
          return;
        }
      }
      state.data.persons.forEach((item) => {
        if (item.id !== person.id && allTextRefs(item).some((ref) => textRefKey(ref) === key)) {
          removeTextRefForPage(item, state.page);
        }
      });
      pushHistorySnapshot();
      const ref = {
        page: state.page,
        index: item.index,
        text: item.clean_text,
        raw_text: item.text || "",
        box: item.box,
        poly: item.poly || [],
      };
      upsertTextRef(person, ref);
      person.glyph_image = makeGlyphFromBox(item) || person.glyph_image || "";
      if (!person.name && item.clean_text) {
        person.name = item.clean_text;
      }
      setStatus(`已将 ${item.clean_text} 绑定到 ${person.name || person.id}，记得保存。`);
      state.activePersonId = null;
      renderPersons();
      updateOverlayHint();
      renderOcrOverlay();
      requestGraphRender(false);
      scheduleAutoSave();
    });
    ocrOverlay.appendChild(box);
  });
  peopleForPage(state.page)
    .filter((person) => !renderedAssigned.has(person.id))
    .forEach((person) => {
      const ref = refForPage(person, state.page);
      if (!ref) return;
      const box = renderPersonOverlayBox(person, ref, "assigned");
      if (!box) return;
      box.addEventListener("click", (event) => {
        event.preventDefault();
        if (state.linkMode) {
          if (!state.linkParentPersonId) {
            startLinkParent(person.id);
            return;
          }
          if (state.linkParentPersonId === person.id) {
            finishCurrentLinkParent();
            setStatus("已取消当前父节点选择。");
            return;
          }
          completeLinkToChild(person.id, "图上补链", true);
          return;
        }
        if (pagePeopleLocked()) {
          setStatus("当前页人物区已锁定，不能再改绑文字框。");
          return;
        }
        setActivePerson(person.id);
      });
      ocrOverlay.appendChild(box);
    });
}

function renderPersons() {
  const people = treeOrderedPeopleForPage(state.page);
  const locked = pagePeopleLocked();
  personsTable.innerHTML = "";
  const groups = new Map();
  people.forEach((person) => {
      const key = Number(person.generation) || 0;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(person);
    });
  [...groups.entries()].forEach(([generation, peopleInGeneration]) => {
    const group = document.createElement("section");
    group.className = "generation-group";
    const header = document.createElement("div");
    header.className = "generation-group-header";
    header.innerHTML = `
      <div class="generation-group-title">${generation || "未知"}世</div>
      <div class="generation-group-count">当前页 ${peopleInGeneration.length} 人</div>
    `;
    group.appendChild(header);
    for (const person of peopleInGeneration) {
      const row = document.createElement("div");
      row.className = `table-row person-row${person.id === state.activePersonId ? " active" : ""}${person.id === state.linkParentPersonId ? " link-parent" : ""}${person.id === state.linkChildPersonId ? " link-child" : ""}${isChildCandidate(person.id) ? " link-candidate" : ""}${needsParentLink(person) ? " needs-parent-link" : ""}${locked ? " locked" : ""}`;
      row.dataset.personRow = person.id;
      const currentRef = refForPage(person, state.page) || person.text_ref;
      const bindingText = currentRef
        ? `第${currentRef.page}页 #${currentRef.index} ${currentRef.text || currentRef.raw_text || ""}`
        : "未绑定文字框";
      const glyph = person.glyph_image
        ? `<div class="glyph-preview"><img src="${person.glyph_image}" alt="字形截图" /></div>`
        : `<div class="glyph-preview"><div class="glyph-empty">未存图</div></div>`;
      const roleBadges = [
        person.id === state.linkParentPersonId ? `<span class="person-role-badge parent">父</span>` : "",
        person.id === state.linkChildPersonId ? `<span class="person-role-badge child">子</span>` : "",
        person.id !== state.linkParentPersonId && person.id !== state.linkChildPersonId && needsParentLink(person)
          ? `<span class="person-role-badge missing-parent">缺父</span>`
          : "",
      ]
        .filter(Boolean)
        .join("");
      row.innerHTML = `
      <label>姓名<input data-person-id="${person.id}" data-field="name" value="${escapeHtml(person.name || "")}" /></label>
      <label class="generation-label">世代<input type="number" min="1" max="200" data-person-id="${person.id}" data-field="generation" value="${person.generation || ""}" /></label>
      <label class="notes-label">备注<input data-person-id="${person.id}" data-field="notes" placeholder="可标记生僻字、待大家帮忙录入" value="${escapeHtml((person.notes || []).join("；"))}" /></label>
      <div class="person-binding">
        <div class="person-binding-meta">
          <div class="person-role-badges">${roleBadges}</div>
          <div class="binding-chip">${escapeHtml(bindingText)}</div>
          <div class="binding-actions">
            <button type="button" class="mini-button danger-button" data-delete-person="${person.id}">删除人物</button>
          </div>
        </div>
        ${glyph}
      </div>
    `;
    row.addEventListener("click", (event) => {
      if (
        event.target.closest("button") ||
        event.target.closest("input") ||
        event.target.closest("label")
      ) {
        return;
      }
      setActivePerson(person.id);
    });
      group.appendChild(row);
    }
    personsTable.appendChild(group);
  });
  personsTable.querySelectorAll("input").forEach((input) => {
    input.disabled = locked;
    input.addEventListener("focus", onEditableFieldFocus);
    if (input.dataset.field === "generation" || input.dataset.field === "page_sources") {
      input.addEventListener("input", onPersonInput);
    } else if (input.dataset.field === "name" || input.dataset.field === "notes") {
      input.addEventListener("input", onPersonDraftInput);
      input.addEventListener("change", onPersonInput);
    } else {
      input.addEventListener("change", onPersonInput);
    }
  });
  personsTable.querySelectorAll("[data-delete-person]").forEach((button) => {
    button.disabled = locked;
    button.addEventListener("click", onDeletePerson);
  });
}

function renderEdges() {
  const people = personMap();
  const edges = edgesForPage(state.page);
  const allOptions = state.data.persons
    .slice()
    .sort((a, b) => (a.generation || 999) - (b.generation || 999) || (a.name || "").localeCompare(b.name || "", "zh-Hans-CN"))
    .map((person) => `<option value="${person.name || person.id}">${person.name || person.id}（${person.generation || "?"}世）</option>`)
    .join("");
  allPersonsList.innerHTML = allOptions;
  const pagePeople = treeOrderedPeopleForPage(state.page);
  const options = pagePeople
    .map((person) => `<option value="${person.id}">${person.name || person.id}（${person.generation || "?"}世）</option>`)
    .join("");
  newEdgeFromSelect.innerHTML = `<option value="">选择父</option>${options}`;
  newEdgeToSelect.innerHTML = `<option value="">选择子</option>${options}`;
  edgesTable.innerHTML = "";
  for (const edge of edges) {
    const father = people.get(edge.from_person_id);
    const child = people.get(edge.to_person_id);
    const upperEdge = incomingEdgeForChild(edge.from_person_id);
    const upperPerson = upperEdge ? state.data.persons.find((person) => person.id === upperEdge.from_person_id) : null;
    const upperGeneration = Math.max(1, Number(father?.generation || 1) - 1);
    const candidateParents = state.data.persons
      .filter((person) => Number(person.generation) === upperGeneration)
      .sort((a, b) => (a.name || "").localeCompare(b.name || "", "zh-Hans-CN"));
    if (upperPerson && !candidateParents.some((person) => person.id === upperPerson.id)) {
      candidateParents.unshift(upperPerson);
    }
    const upperOptions = candidateParents
      .map(
        (person) =>
          `<option value="${escapeHtml(person.name || person.id)}"${upperPerson?.id === person.id ? " selected" : ""}>${escapeHtml(person.name || person.id)}</option>`,
      )
      .join("");
    const row = document.createElement("div");
    row.className = "table-row edge-row";
    row.innerHTML = `
      <label>父的父<select data-parent-link="${edge.from_person_id}"><option value="">未设置</option>${upperOptions}</select></label>
      <label>父<span class="readonly-field">${father?.name || ""}</span></label>
      <div class="muted">→</div>
      <label>子<input data-edge-key="${edge.from_person_id}__${edge.to_person_id}" data-side="to" value="${child?.name || ""}" /></label>
      <button type="button" class="danger-button" data-edge-delete="${edge.from_person_id}__${edge.to_person_id}">删除</button>
    `;
    edgesTable.appendChild(row);
  }
  edgesTable.querySelectorAll("input").forEach((input) => {
    input.addEventListener("focus", onEditableFieldFocus);
    input.addEventListener("input", onEdgeLabelDraftInput);
    input.addEventListener("change", onEdgeLabelInput);
  });
  edgesTable.querySelectorAll("select[data-parent-link]").forEach((select) => {
    select.addEventListener("change", onParentBridgeInput);
  });
  edgesTable.querySelectorAll("button[data-edge-delete]").forEach((button) => {
    button.addEventListener("click", onDeleteEdgeClick);
  });
}

function buildGraphData(fullGraph = false) {
  const allPeople = personMap();
  const currentPeople = peopleForPage(state.page);
  const currentIds = new Set(currentPeople.map((person) => person.id));
  const nodes = new Map();
  let graphEdges = [];

  if (fullGraph) {
    state.data.persons.forEach((person) => nodes.set(person.id, person));
    graphEdges = state.data.edges.slice();
    if (isMergeWorkspace() && state.fullscreenBoundaryMode) {
      const pair = mergeBoundaryGroupPair();
      if (pair) {
        const leftPeople = state.data.persons.filter((person) => person.source_group_id === pair.leftGroupId);
        const rightPeople = state.data.persons.filter((person) => person.source_group_id === pair.rightGroupId);
        const leftBoundaryGen = Math.max(...leftPeople.map((person) => Number(person.generation || 0)).filter(Boolean));
        const rightBoundaryGen = Math.min(...rightPeople.map((person) => Number(person.generation || 0)).filter(Boolean));
        const visibleIds = new Set(
          state.data.persons
            .filter((person) => {
              const generation = Number(person.generation || 0);
              if (!generation) return false;
              if (person.source_group_id === pair.leftGroupId) {
                return generation === leftBoundaryGen || generation === leftBoundaryGen - 1;
              }
              if (person.source_group_id === pair.rightGroupId) {
                return generation === rightBoundaryGen || generation === rightBoundaryGen + 1;
              }
              return false;
            })
            .map((person) => person.id),
        );
        const filteredEdges = graphEdges.filter(
          (edge) => visibleIds.has(edge.from_person_id) && visibleIds.has(edge.to_person_id),
        );
        if (visibleIds.size >= 20 && filteredEdges.length >= 10) {
          graphEdges = filteredEdges;
          nodes.clear();
          state.data.persons.forEach((person) => {
            if (visibleIds.has(person.id)) nodes.set(person.id, person);
          });
        }
      }
    }
  } else {
    currentPeople.forEach((person) => nodes.set(person.id, person));
    graphEdges = state.data.edges.filter(
      (edge) => currentIds.has(edge.from_person_id) && currentIds.has(edge.to_person_id),
    );
  }

  return {
    nodes: [...nodes.values()],
    edges: graphEdges,
  };
}

function createSvgNode(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function appendLinkDeleteControl(edgeAnchorMap) {
  if (!state.linkMode || !state.linkDeleteEdgeKey) return;
  const anchor = edgeAnchorMap.get(state.linkDeleteEdgeKey);
  if (!anchor) return;
  const [fromId, toId] = state.linkDeleteEdgeKey.split("__");
  if (!fromId || !toId || !edgeForPair(fromId, toId)) return;
  const buttonGroup = createSvgNode("g", { class: "graph-action-group graph-edge-delete-action" });
  buttonGroup.appendChild(
    createSvgNode("circle", {
      cx: String(anchor.x),
      cy: String(anchor.y),
      r: "12",
      fill: "#d33",
      stroke: "#fff",
      "stroke-width": "1.5",
    }),
  );
  const label = createSvgNode("text", {
    x: String(anchor.x),
    y: String(anchor.y + 4),
    "text-anchor": "middle",
    fill: "#fff",
    "font-size": "14",
    "font-weight": "700",
    "pointer-events": "none",
  });
  label.textContent = "×";
  buttonGroup.appendChild(label);
  buttonGroup.addEventListener("click", (event) => {
    event.stopPropagation();
    deleteEdgeFromLinkMode(fromId, toId);
  });
  graphSvg.appendChild(buttonGroup);
}

function computeGenerationOrderMaps(graphNodes, graphEdges) {
  const groups = {};
  graphNodes.forEach((person) => {
    const key = String(person.generation || "未知");
    groups[key] ||= [];
    groups[key].push(person);
  });
  const generations = Object.keys(groups).sort((a, b) => Number(a) - Number(b));

  const incomingOrder = new Map();
  const outgoingOrder = new Map();
  graphEdges.forEach((edge, index) => {
    if (!outgoingOrder.has(edge.from_person_id)) {
      outgoingOrder.set(edge.from_person_id, []);
    }
    outgoingOrder.get(edge.from_person_id).push({ child: edge.to_person_id, index });
    if (!incomingOrder.has(edge.to_person_id)) {
      incomingOrder.set(edge.to_person_id, []);
    }
    incomingOrder.get(edge.to_person_id).push({ parent: edge.from_person_id, index });
  });

  const orderByGeneration = new Map();
  generations.forEach((gen, genIndex) => {
    const people = groups[gen];
    if (genIndex === 0) {
      people.sort((a, b) => {
        const outA = Math.min(...((outgoingOrder.get(a.id) || []).map((item) => item.index)));
        const outB = Math.min(...((outgoingOrder.get(b.id) || []).map((item) => item.index)));
        return (Number.isFinite(outA) ? outA : 1e9) - (Number.isFinite(outB) ? outB : 1e9) || a.name.localeCompare(b.name, "zh-Hans-CN");
      });
    } else {
      people.sort((a, b) => {
        const parentA = incomingOrder.get(a.id) || [];
        const parentB = incomingOrder.get(b.id) || [];
        const firstA = parentA[0];
        const firstB = parentB[0];
        if (firstA?.parent && firstB?.parent && firstA.parent === firstB.parent) {
          const orderA = Number.isFinite(Number(graphEdges[firstA.index]?.birth_order_under_parent))
            ? Number(graphEdges[firstA.index].birth_order_under_parent)
            : 999;
          const orderB = Number.isFinite(Number(graphEdges[firstB.index]?.birth_order_under_parent))
            ? Number(graphEdges[firstB.index].birth_order_under_parent)
            : 999;
          if (orderA !== orderB) return orderA - orderB;
        }
        const avgA =
          parentA.length > 0
            ? parentA.reduce((sum, item) => sum + (orderByGeneration.get(String(Number(gen) - 1))?.get(item.parent) ?? 999), 0) / parentA.length
            : 999;
        const avgB =
          parentB.length > 0
            ? parentB.reduce((sum, item) => sum + (orderByGeneration.get(String(Number(gen) - 1))?.get(item.parent) ?? 999), 0) / parentB.length
            : 999;
        const edgeA = Math.min(...parentA.map((item) => item.index));
        const edgeB = Math.min(...parentB.map((item) => item.index));
        return avgA - avgB || (Number.isFinite(edgeA) ? edgeA : 1e9) - (Number.isFinite(edgeB) ? edgeB : 1e9) || a.name.localeCompare(b.name, "zh-Hans-CN");
      });
    }
    orderByGeneration.set(
      gen,
      new Map(people.map((person, index) => [person.id, index])),
    );
  });
  return { groups, generations, orderByGeneration };
}

function sortChildrenForTree(children, peopleById) {
  return children.slice().sort((a, b) => {
    const orderA = Number.isFinite(Number(a.birth_order_under_parent)) ? Number(a.birth_order_under_parent) : 999;
    const orderB = Number.isFinite(Number(b.birth_order_under_parent)) ? Number(b.birth_order_under_parent) : 999;
    if (orderA !== orderB) {
      return orderA - orderB;
    }
    const nameA = peopleById.get(a.to_person_id)?.name || "";
    const nameB = peopleById.get(b.to_person_id)?.name || "";
    return nameA.localeCompare(nameB, "zh-Hans-CN");
  });
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

function findLeftSiblingId(personId, childMap, incoming, peopleById) {
  const parentEdge = (incoming.get(personId) || [])[0];
  if (!parentEdge) return null;
  const siblings = sortChildrenForTree(childMap.get(parentEdge.from_person_id) || [], peopleById).slice().reverse();
  const index = siblings.findIndex((edge) => edge.to_person_id === personId);
  if (index <= 0) return null;
  return siblings[index - 1].to_person_id;
}

function findRightSiblingId(personId, childMap, incoming, peopleById) {
  const parentEdge = (incoming.get(personId) || [])[0];
  if (!parentEdge) return null;
  const siblings = sortChildrenForTree(childMap.get(parentEdge.from_person_id) || [], peopleById).slice().reverse();
  const index = siblings.findIndex((edge) => edge.to_person_id === personId);
  if (index < 0 || index >= siblings.length - 1) return null;
  return siblings[index + 1].to_person_id;
}

function buildRootOrder(graphNodes, incoming) {
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
      const refsA = allTextRefs(a).slice().sort((x, y) => Number(x.page) - Number(y.page));
      const refsB = allTextRefs(b).slice().sort((x, y) => Number(x.page) - Number(y.page));
      const pageA = Number(refsA[0]?.page || 999);
      const pageB = Number(refsB[0]?.page || 999);
      return pageA - pageB || (a.name || "").localeCompare(b.name || "", "zh-Hans-CN");
    });
}

function findLeftRootId(personId, graphNodes, incoming) {
  const roots = buildRootOrder(graphNodes, incoming).reverse();
  const index = roots.findIndex((person) => person.id === personId);
  if (index <= 0) return null;
  return roots[index - 1].id;
}

function findRightRootId(personId, graphNodes, incoming) {
  const roots = buildRootOrder(graphNodes, incoming).reverse();
  const index = roots.findIndex((person) => person.id === personId);
  if (index < 0 || index >= roots.length - 1) return null;
  return roots[index + 1].id;
}

function swapSiblingVisualPosition(personId, direction, childMap, incoming, peopleById, graphNodes = []) {
  const parentEdge = (incoming.get(personId) || [])[0];
  if (!parentEdge) {
    const visualRoots = buildRootOrder(graphNodes, incoming).reverse();
    const index = visualRoots.findIndex((person) => person.id === personId);
    const targetIndex = direction === "left" ? index - 1 : index + 1;
    if (index < 0) {
      setStatus("该节点不在当前树排序中。");
      return;
    }
    if (targetIndex < 0 || targetIndex >= visualRoots.length) {
      setStatus(direction === "left" ? "已经是最左侧根节点，不能再左移。" : "已经是最右侧根节点，不能再右移。");
      return;
    }
    const reordered = visualRoots.slice();
    [reordered[targetIndex], reordered[index]] = [reordered[index], reordered[targetIndex]];
    pushHistorySnapshot();
    reordered.forEach((person, idx) => {
      person.root_order = reordered.length - idx;
    });
    const currentName = peopleById.get(personId)?.name || personId;
    const targetName = reordered[index]?.name || reordered[index]?.id || "";
    setStatus(`已交换整根树顺序：${currentName} 与 ${targetName}`);
    renderGraph(true);
    scheduleAutoSave();
    return;
  }
  const visualSiblings = sortChildrenForTree(childMap.get(parentEdge.from_person_id) || [], peopleById).slice().reverse();
  const index = visualSiblings.findIndex((edge) => edge.to_person_id === personId);
  const targetIndex = direction === "left" ? index - 1 : index + 1;
  if (targetIndex < 0 || targetIndex >= visualSiblings.length) {
    setStatus(direction === "left" ? "已经是最左侧兄弟，不能再左移。" : "已经是最右侧兄弟，不能再右移。");
    return;
  }
  const reordered = visualSiblings.slice();
  [reordered[targetIndex], reordered[index]] = [reordered[index], reordered[targetIndex]];
  pushHistorySnapshot();
  reordered.forEach((edge, idx) => {
    edge.birth_order_under_parent = reordered.length - idx;
  });
  const currentName = peopleById.get(personId)?.name || personId;
  const targetName =
    peopleById.get(visualSiblings[targetIndex].to_person_id)?.name || visualSiblings[targetIndex].to_person_id;
  setStatus(`已交换兄弟顺序：${currentName} 与 ${targetName}`);
  renderGraph(true);
  scheduleAutoSave();
}

function renderClassicFullscreenGraph(graphNodes, graphEdges) {
  renderFullscreenPageImages({ pages: [], pageWidthMap: new Map(), width: 0, pageGap: 0, rightMargin: 0 });
  const { peopleById, childMap, incoming, refMap, generations, generationIndex, pages, nodePageMap, slotPositions, maxSlot } =
    computeGlobalTreeLayout(graphNodes, graphEdges);
  if (state.fullscreenSelectedPersonId && !peopleById.has(state.fullscreenSelectedPersonId)) {
    state.fullscreenSelectedPersonId = null;
  }
  const selectedSubtreeIds = state.fullscreenSelectedPersonId
    ? collectSubtreeIds(state.fullscreenSelectedPersonId, childMap)
    : new Set();
  const edgeAnchorMap = new Map();

  const leftMargin = 48;
  const rightMargin = 120;
  const topMargin = 54;
  const rowHeight = 132;
  const nodeWidth = 54;
  const nodeHeightWithGlyph = 94;
  const nodeHeightPlain = 38;
  const pageGap = 24;
  const slotWidth = 76;
  const rootGap = 20;
  const height = Math.max(560, topMargin + generations.length * rowHeight + 40);

  const width = Math.max(1400, leftMargin + (maxSlot + 2) * slotWidth + rightMargin);

  graphSvg.innerHTML = "";
  graphSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  graphSvg.style.width = `${Math.round(width * state.graphZoom)}px`;
  graphSvg.style.height = `${Math.round(height * state.graphZoom)}px`;

  const positions = new Map();
  graphNodes.forEach((person) => {
    const x = width - rightMargin - (maxSlot - (slotPositions.get(person.id) ?? 0)) * slotWidth;
    const row = generationIndex.get(Number(person.generation || generations[0] || 0)) ?? 0;
    const y = topMargin + row * rowHeight + rowHeight / 2;
    positions.set(person.id, { x, y });
  });

  const pageSpanMap = new Map();
  pages.forEach((page) => {
    const xs = graphNodes
      .filter((person) => nodePageMap.get(person.id) === page)
      .map((person) => positions.get(person.id)?.x)
      .filter((value) => Number.isFinite(value));
    if (!xs.length) return;
    pageSpanMap.set(page, {
      min: Math.min(...xs) - nodeWidth / 2 - 10,
      max: Math.max(...xs) + nodeWidth / 2 + 10,
    });
  });

  pages.forEach((page, index) => {
    const span = pageSpanMap.get(page);
    if (!span) return;
    const pageLeft = span.min;
    const pageWidth = span.max - span.min;
    const divider = createSvgNode("line", {
      x1: String(pageLeft - pageGap / 2),
      y1: String(topMargin - 24),
      x2: String(pageLeft - pageGap / 2),
      y2: String(height - 24),
      class: "graph-page-divider",
    });
    if (index > 0) {
      graphSvg.appendChild(divider);
    }
    const label = createSvgNode("text", {
      x: String(pageLeft + pageWidth / 2),
      y: String(topMargin - 20),
      "text-anchor": "middle",
      class: `graph-page-label${Number(page) === Number(state.page) ? " graph-page-label-active" : ""}`,
      "data-page-anchor": String(page),
    });
    label.textContent = pageDisplayLabel(page);
    label.addEventListener("click", () => {
      setCurrentPageFromFullscreen(page);
      updateOverlayHint();
      renderGraph(true);
    });
    graphSvg.appendChild(label);
  });

  generations.forEach((gen, index) => {
    const y = topMargin + index * rowHeight + rowHeight / 2;
    const line = createSvgNode("line", {
      x1: String(leftMargin - 20),
      y1: String(y),
      x2: String(width - rightMargin + 10),
      y2: String(y),
      class: "graph-row-guide",
    });
    graphSvg.appendChild(line);

    const label = createSvgNode("text", {
      x: String(width - 42),
      y: String(y + 6),
      "text-anchor": "middle",
      class: "graph-generation",
    });
    label.textContent = `第${gen}世`;
    graphSvg.appendChild(label);
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
        return {
          edge,
          child,
          endY: child.y - childHeight / 2,
        };
      })
      .filter(Boolean);
    if (!childEntries.length) return;

    const busY =
      childEntries.length === 1
        ? startY + (childEntries[0].endY - startY) * 0.5
        : startY + (Math.min(...childEntries.map((item) => item.endY)) - startY) * 0.45;
    const highlightedEntries = childEntries.filter(
      (item) => selectedSubtreeIds.has(parentId) && selectedSubtreeIds.has(item.edge.to_person_id),
    );
    const selectedClass = highlightedEntries.length ? " graph-edge-selected" : "";

    const parentStem = createSvgNode("path", {
      d: `M ${parent.x} ${startY} V ${busY}`,
      class: `graph-edge graph-edge-orth${selectedClass}`,
    });
    graphSvg.appendChild(parentStem);

    if (childEntries.length > 1) {
      const childXs = childEntries.map((item) => item.child.x);
      const bus = createSvgNode("path", {
        d: `M ${Math.min(...childXs)} ${busY} H ${Math.max(...childXs)}`,
        class: "graph-edge graph-edge-orth",
      });
      graphSvg.appendChild(bus);
      if (highlightedEntries.length) {
        const highlightXs = highlightedEntries.map((item) => item.child.x);
        const selectedBus = createSvgNode("path", {
          d: `M ${Math.min(parent.x, ...highlightXs)} ${busY} H ${Math.max(parent.x, ...highlightXs)}`,
          class: "graph-edge graph-edge-orth graph-edge-selected",
        });
        graphSvg.appendChild(selectedBus);
      }
    }

    childEntries.forEach((item) => {
      const connector = createSvgNode("path", {
        d: `M ${item.child.x} ${busY} V ${item.endY}`,
        class: `graph-edge graph-edge-orth${
          selectedSubtreeIds.has(parentId) && selectedSubtreeIds.has(item.edge.to_person_id)
            ? " graph-edge-selected"
            : ""
        }`,
      });
      graphSvg.appendChild(connector);
      edgeAnchorMap.set(edgeKey(parentId, item.edge.to_person_id), {
        x: item.child.x,
        y: (busY + item.endY) / 2,
      });
    });
  });

  graphNodes.forEach((person) => {
    const pos = positions.get(person.id);
    if (!pos) return;
    const hasGlyph = Boolean(person.glyph_image);
    const nodeHeight = hasGlyph ? nodeHeightWithGlyph : nodeHeightPlain;
    const nodeGroup = createSvgNode("g", {
      class: `graph-node-group${selectedSubtreeIds.has(person.id) ? " graph-node-group-selected" : ""}${state.fullscreenSelectedPersonId === person.id ? " graph-node-group-active" : ""}${person.id === state.linkParentPersonId ? " graph-node-group-link-parent" : ""}${person.id === state.linkChildPersonId ? " graph-node-group-link-child" : ""}${isChildCandidate(person.id) ? " graph-node-group-link-candidate" : ""}${needsParentLink(person) ? " graph-node-group-needs-parent-link" : ""}`,
      "data-person-id": person.id,
    });
    const rect = createSvgNode("rect", {
      x: String(pos.x - nodeWidth / 2),
      y: String(pos.y - nodeHeight / 2),
      width: String(nodeWidth),
      height: String(nodeHeight),
      rx: "8",
      class: "graph-node",
    });
    nodeGroup.appendChild(rect);

    if (hasGlyph) {
      const image = createSvgNode("image", {
        href: person.glyph_image,
        x: String(pos.x - 18),
        y: String(pos.y - nodeHeight / 2 + 10),
        width: "36",
        height: "36",
        class: "graph-glyph",
      });
      nodeGroup.appendChild(image);
    }

    const text = createSvgNode("text", {
      x: String(pos.x),
      y: String(pos.y + (hasGlyph ? 32 : 6)),
      "text-anchor": "middle",
      class: "graph-label",
    });
    text.textContent = person.name || person.id;
    nodeGroup.appendChild(text);
    if (person.id === state.linkParentPersonId) {
      appendGraphRoleBadge(nodeGroup, pos.x + 22, pos.y - nodeHeight / 2 - 10, "父", "parent");
    } else if (person.id === state.linkChildPersonId) {
      appendGraphRoleBadge(nodeGroup, pos.x + 22, pos.y - nodeHeight / 2 - 10, "子", "child");
    } else if (needsParentLink(person)) {
      appendGraphRoleBadge(nodeGroup, pos.x + 22, pos.y - nodeHeight / 2 - 10, "缺父", "missing-parent");
    }
    nodeGroup.addEventListener("mouseenter", () => {
      if (!state.linkMode) return;
      clearLinkDeleteHoverTimer();
      const incomingEdge = (incoming.get(person.id) || [])[0];
      if (!incomingEdge) return;
      linkDeleteHoverTimer = setTimeout(() => {
        setLinkDeleteEdgeKey(edgeKey(incomingEdge.from_person_id, incomingEdge.to_person_id), true);
      }, LINK_EDGE_DELETE_HOVER_MS);
    });
    nodeGroup.addEventListener("mouseleave", () => {
      clearLinkDeleteHoverTimer();
    });
    nodeGroup.addEventListener("click", () => {
      if (!shouldKeepFullscreenCrossPageContext()) {
        void setCurrentPageFromFullscreen(nodePageMap.get(person.id));
      }
      if (state.linkMode) {
        if (!state.linkParentPersonId) {
          startLinkParent(person.id);
          return;
        }
        if (state.linkParentPersonId === person.id) {
          finishCurrentLinkParent();
          setStatus("已取消当前父节点选择。");
          return;
        }
        completeLinkToChild(person.id, "全屏补链", true);
        return;
      }
      state.fullscreenSelectedPersonId = person.id;
      renderGraph(true);
    });
    graphSvg.appendChild(nodeGroup);
  });

  appendLinkDeleteControl(edgeAnchorMap);

  if (state.fullscreenSelectedPersonId) {
    const leftSiblingId =
      findLeftSiblingId(state.fullscreenSelectedPersonId, childMap, incoming, peopleById) ||
      findLeftRootId(state.fullscreenSelectedPersonId, graphNodes, incoming);
    const rightSiblingId =
      findRightSiblingId(state.fullscreenSelectedPersonId, childMap, incoming, peopleById) ||
      findRightRootId(state.fullscreenSelectedPersonId, graphNodes, incoming);
    const selectedPos = positions.get(state.fullscreenSelectedPersonId);
    if (selectedPos && (leftSiblingId || rightSiblingId)) {
      const actions = [];
      if (leftSiblingId) actions.push({ label: "左移", direction: "left" });
      if (rightSiblingId) actions.push({ label: "右移", direction: "right" });
      const btnWidth = 48;
      const btnHeight = 24;
      const gap = 8;
      const totalWidth = actions.length * btnWidth + (actions.length - 1) * gap;
      actions.forEach((action, index) => {
        const buttonGroup = createSvgNode("g", {
          class: "graph-action-group",
        });
        const btnX = selectedPos.x - totalWidth / 2 + index * (btnWidth + gap);
        const btnY = selectedPos.y - 72;
        const rect = createSvgNode("rect", {
          x: String(btnX),
          y: String(btnY),
          width: String(btnWidth),
          height: String(btnHeight),
          rx: "12",
          class: "graph-action-btn",
        });
        const label = createSvgNode("text", {
          x: String(btnX + btnWidth / 2),
          y: String(btnY + 16),
          "text-anchor": "middle",
          class: "graph-action-label",
        });
        label.textContent = action.label;
        buttonGroup.appendChild(rect);
        buttonGroup.appendChild(label);
        buttonGroup.addEventListener("click", (event) => {
          event.stopPropagation();
          swapSiblingVisualPosition(state.fullscreenSelectedPersonId, action.direction, childMap, incoming, peopleById, graphNodes);
        });
        graphSvg.appendChild(buttonGroup);
      });
    }
  }
}

function renderPageGroupedFullscreenGraph(graphNodes, graphEdges) {
  const { peopleById, childMap, incoming, generations, generationIndex, pages, nodePageMap, slotPositions } =
    computeGlobalTreeLayout(graphNodes, graphEdges);

  const selectedSubtreeIds = state.fullscreenSelectedPersonId
    ? collectSubtreeIds(state.fullscreenSelectedPersonId, childMap)
    : new Set();
  const edgeAnchorMap = new Map();
  const leftMargin = 48;
  const rightMargin = 120;
  const topMargin = 54;
  const rowHeight = 132;
  const nodeWidth = 54;
  const nodeHeightWithGlyph = 94;
  const nodeHeightPlain = 38;
  const pageGap = 24;
  const pagePadding = 20;
  const baseLeafUnit = 64;
  const baseRootGap = 26;
  const mergeMode = isMergeWorkspace();
  const height = Math.max(560, topMargin + generations.length * rowHeight + 40);

  const nodeMeta = graphNodes.map((person) => ({
    person,
    page: nodePageMap.get(person.id),
  }));

  const pageWidthMap = new Map();
  const pageLocalXMap = new Map();
  pages.forEach((page) => {
    const pageNodes = nodeMeta.filter((item) => item.page === page).map((item) => item.person);
    const pageIds = new Set(pageNodes.map((person) => person.id));
    const pageEdges = graphEdges.filter((edge) => pageIds.has(edge.from_person_id) && pageIds.has(edge.to_person_id));
    const pagePeopleById = new Map(pageNodes.map((person) => [person.id, person]));
    const pageChildMap = new Map();
    const pageIncoming = new Map();
    pageEdges.forEach((edge) => {
      if (!pageChildMap.has(edge.from_person_id)) {
        pageChildMap.set(edge.from_person_id, []);
      }
      pageChildMap.get(edge.from_person_id).push(edge);
      if (!pageIncoming.has(edge.to_person_id)) {
        pageIncoming.set(edge.to_person_id, []);
      }
      pageIncoming.get(edge.to_person_id).push(edge);
    });
    pageChildMap.forEach((edges, parentId) => {
      pageChildMap.set(parentId, sortChildrenForTree(edges, pagePeopleById));
    });
    const pageCenterX = new Map();
    pageNodes.forEach((person) => {
      const ref = refForPage(person, page);
      const box = ref?.box || [];
      if (box.length === 4) {
        pageCenterX.set(person.id, (Number(box[0]) + Number(box[2])) / 2);
      }
    });

    const localX = new Map();
    const subtreeVisualRange = new Map();
    let leafUnit = baseLeafUnit;
    let rootGap = baseRootGap;
    if (mergeMode) {
      const count = pageNodes.length;
      if (count >= 140) {
        leafUnit = 20;
        rootGap = 8;
      } else if (count >= 90) {
        leafUnit = 24;
        rootGap = 10;
      } else if (count >= 60) {
        leafUnit = 30;
        rootGap = 14;
      } else if (count >= 40) {
        leafUnit = 38;
        rootGap = 16;
      } else if (count >= 25) {
        leafUnit = 46;
        rootGap = 20;
      }
    }
    function computeVisibleSubtreeRange(personId) {
      if (subtreeVisualRange.has(personId)) {
        return subtreeVisualRange.get(personId);
      }
      const children = pageChildMap.get(personId) || [];
      const selfCenter = pageCenterX.get(personId) ?? 0;
      if (!children.length) {
        const range = { min: selfCenter, max: selfCenter };
        subtreeVisualRange.set(personId, range);
        return range;
      }
      const childRanges = children.map((edge) => computeVisibleSubtreeRange(edge.to_person_id));
      const range = {
        min: Math.min(selfCenter, ...childRanges.map((item) => item.min)),
        max: Math.max(selfCenter, ...childRanges.map((item) => item.max)),
      };
      subtreeVisualRange.set(personId, range);
      return range;
    }

    const roots = pageNodes
      .filter((person) => !(pageIncoming.get(person.id) || []).length)
      .sort((a, b) => {
        const rangeA = computeVisibleSubtreeRange(a.id);
        const rangeB = computeVisibleSubtreeRange(b.id);
        return rangeA.max - rangeB.max || rangeA.min - rangeB.min || (a.name || "").localeCompare(b.name || "", "zh-Hans-CN");
      });

    let cursorX = 0;
    function assignSubtree(personId) {
      const children = pageChildMap.get(personId) || [];
      if (!children.length) {
        localX.set(personId, cursorX);
        cursorX += leafUnit;
        return localX.get(personId);
      }
      const childCenters = [];
      children
        .slice()
        .reverse()
        .forEach((edge) => {
          childCenters.push(assignSubtree(edge.to_person_id));
        });
      const rightAligned = childCenters[childCenters.length - 1];
      localX.set(personId, rightAligned);
      return rightAligned;
    }

    roots.forEach((root, index) => {
      assignSubtree(root.id);
      if (index !== roots.length - 1) {
        cursorX += rootGap;
      }
    });

    pageNodes
      .filter((person) => !localX.has(person.id))
      .forEach((person) => assignSubtree(person.id));

    pageLocalXMap.set(page, localX);
    const rawWidth = Math.max(220, pagePadding * 2 + Math.max(cursorX - leafUnit + nodeWidth, nodeWidth));
    const pageWidthCap = mergeMode ? 760 : 1400;
    pageWidthMap.set(page, Math.min(rawWidth, pageWidthCap));
  });

  const pageRowMap = new Map();
  const rowPagesMap = new Map();
  const rowOrder = mergeMode ? ["top", "bottom", "single"] : ["single"];
  rowOrder.forEach((key) => rowPagesMap.set(key, []));
  pages.forEach((page) => {
    const rowKey = mergeMode ? mergeRowKeyForPage(page) : "single";
    if (!rowPagesMap.has(rowKey)) rowPagesMap.set(rowKey, []);
    rowPagesMap.get(rowKey).push(page);
    pageRowMap.set(page, rowKey);
  });

  const rowWidthMap = new Map();
  rowPagesMap.forEach((rowPages, rowKey) => {
    const totalWidth = rowPages.reduce((sum, page, index) => sum + pageWidthMap.get(page) + (index ? pageGap : 0), 0);
    rowWidthMap.set(rowKey, totalWidth);
  });

  const widestRowWidth = Math.max(...Array.from(rowWidthMap.values()), 0);
  const width = Math.max(1400, leftMargin + widestRowWidth + rightMargin);
  graphSvg.innerHTML = "";
  graphSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  graphSvg.style.width = `${Math.round(width * state.graphZoom)}px`;
  graphSvg.style.height = `${Math.round(height * state.graphZoom)}px`;
  renderFullscreenPageImages({ pages, pageWidthMap, width, pageGap, rightMargin });

  const pageLeftMap = new Map();
  rowPagesMap.forEach((rowPages) => {
    let cursor = width - rightMargin;
    rowPages.forEach((page) => {
      const pageWidth = pageWidthMap.get(page);
      const pageLeft = cursor - pageWidth;
      pageLeftMap.set(page, pageLeft);
      cursor = pageLeft - pageGap;
    });
  });

  function applyNodePositions() {
    const nextPositions = new Map();
    nodeMeta.forEach((item) => {
      const page = item.page;
      const pageLeft = pageLeftMap.get(page);
      const pageWidth = pageWidthMap.get(page);
      const localXMap = pageLocalXMap.get(page) || new Map();
      const localX = localXMap.get(item.person.id) ?? 0;
      const maxLocalX = Math.max(0, ...localXMap.values(), 0);
      const usableWidth = Math.max(nodeWidth, pageWidth - pagePadding * 2 - nodeWidth);
      const normalizedLocalX = maxLocalX > 0 ? localX / maxLocalX : 0;
      const x = pageLeft + pagePadding + nodeWidth / 2 + normalizedLocalX * usableWidth;
      const row = generationIndex.get(Number(item.person.generation || generations[0] || 0)) ?? 0;
      const y = topMargin + row * rowHeight + rowHeight / 2;
      nextPositions.set(item.person.id, { x, y });
    });
    return nextPositions;
  }

  let positions = applyNodePositions();

  if (mergeMode) {
    const crossRowTargetMap = new Map();
    graphEdges.forEach((edge) => {
      const parentPage = nodePageMap.get(edge.from_person_id);
      const childPage = nodePageMap.get(edge.to_person_id);
      if (mergeRowKeyForPage(parentPage) !== "top" || mergeRowKeyForPage(childPage) !== "bottom") return;
      const parentPos = positions.get(edge.from_person_id);
      const childPos = positions.get(edge.to_person_id);
      if (!parentPos || !childPos) return;
      if (!crossRowTargetMap.has(edge.from_person_id)) {
        crossRowTargetMap.set(edge.from_person_id, []);
      }
      crossRowTargetMap.get(edge.from_person_id).push({
        personId: edge.from_person_id,
        sourceX: parentPos.x,
        targetX: childPos.x,
      });
    });

    const anchors = Array.from(crossRowTargetMap.entries())
      .map(([personId, items]) => {
        const current = positions.get(personId);
        if (!current || !items.length) return null;
        const sortedTargets = items.map((item) => item.targetX).sort((a, b) => a - b);
        return {
          personId,
          sourceX: current.x,
          targetX: sortedTargets[Math.floor(sortedTargets.length / 2)],
        };
      })
      .filter(Boolean)
      .sort((a, b) => a.sourceX - b.sourceX);

    const dedupedAnchors = [];
    anchors.forEach((anchor) => {
      const prev = dedupedAnchors[dedupedAnchors.length - 1];
      if (prev && Math.abs(prev.sourceX - anchor.sourceX) < 1) {
        prev.targetX = Math.max(prev.targetX, anchor.targetX);
      } else {
        dedupedAnchors.push({ ...anchor });
      }
    });

    for (let index = 1; index < dedupedAnchors.length; index += 1) {
      dedupedAnchors[index].targetX = Math.max(dedupedAnchors[index].targetX, dedupedAnchors[index - 1].targetX + 4);
    }

    if (dedupedAnchors.length) {
      const warpX = (value) => {
        if (dedupedAnchors.length === 1) {
          return value + (dedupedAnchors[0].targetX - dedupedAnchors[0].sourceX);
        }
        if (value <= dedupedAnchors[0].sourceX) {
          return value + (dedupedAnchors[0].targetX - dedupedAnchors[0].sourceX);
        }
        for (let index = 0; index < dedupedAnchors.length - 1; index += 1) {
          const left = dedupedAnchors[index];
          const right = dedupedAnchors[index + 1];
          if (value <= right.sourceX) {
            const ratio = (value - left.sourceX) / Math.max(1, right.sourceX - left.sourceX);
            return left.targetX + ratio * (right.targetX - left.targetX);
          }
        }
        const last = dedupedAnchors[dedupedAnchors.length - 1];
        return value + (last.targetX - last.sourceX);
      };

      nodeMeta
        .filter((item) => pageRowMap.get(item.page) === "top")
        .forEach((item) => {
          const current = positions.get(item.person.id);
          if (!current) return;
          positions.set(item.person.id, {
            ...current,
            x: warpX(current.x),
          });
        });
    }
  }

  const rowVerticalMap = new Map();
  rowOrder.forEach((rowKey, rowIndex) => {
    const rowPages = rowPagesMap.get(rowKey) || [];
    const indices = rowPages.flatMap((page) => {
      const hints = pageEntry(page)?.generation_hint || [];
      return hints
        .map((gen) => generationIndex.get(Number(gen)))
        .filter((index) => Number.isFinite(index));
    });
    const defaultSplit = Math.floor((generations.length - 1) / 2);
    const minIndex = indices.length ? Math.min(...indices) : rowIndex === 0 ? 0 : defaultSplit + 1;
    const maxIndex = indices.length ? Math.max(...indices) : rowIndex === 0 ? defaultSplit : generations.length - 1;
    rowVerticalMap.set(rowKey, {
      labelY: topMargin + minIndex * rowHeight - 20,
      dividerY1: topMargin + minIndex * rowHeight - 24,
      dividerY2: topMargin + maxIndex * rowHeight + rowHeight / 2 + 24,
    });
  });

  const rowDividerSeen = new Map();
  const pageSpanMap = new Map();
  pages.forEach((page) => {
    const xs = nodeMeta
      .filter((item) => item.page === page)
      .map((item) => positions.get(item.person.id)?.x)
      .filter((value) => Number.isFinite(value));
    if (!xs.length) {
      pageSpanMap.set(page, {
        min: pageLeftMap.get(page),
        max: pageLeftMap.get(page) + pageWidthMap.get(page),
      });
      return;
    }
    pageSpanMap.set(page, {
      min: Math.min(...xs) - nodeWidth / 2 - 10,
      max: Math.max(...xs) + nodeWidth / 2 + 10,
    });
  });
  pages.forEach((page, index) => {
    const span = pageSpanMap.get(page);
    const pageLeft = span?.min ?? pageLeftMap.get(page);
    const pageWidth = Math.max(220, (span?.max ?? pageLeft + pageWidthMap.get(page)) - pageLeft);
    const rowKey = pageRowMap.get(page) || "single";
    const rowVertical = rowVerticalMap.get(rowKey) || {
      labelY: topMargin - 20,
      dividerY1: topMargin - 24,
      dividerY2: height - 24,
    };
    const rowPages = rowPagesMap.get(rowKey) || [];
    const rowIndex = rowPages.indexOf(page);
    if (rowIndex > 0) {
      graphSvg.appendChild(createSvgNode("line", {
        x1: String(pageLeft - pageGap / 2),
        y1: String(rowVertical.dividerY1),
        x2: String(pageLeft - pageGap / 2),
        y2: String(rowVertical.dividerY2),
        class: "graph-page-divider",
      }));
    }
    if (mergeMode && !rowDividerSeen.get(rowKey) && rowIndex === 0) {
      rowDividerSeen.set(rowKey, true);
    }
    const label = createSvgNode("text", {
      x: String(pageLeft + pageWidth / 2),
      y: String(rowVertical.labelY),
      "text-anchor": "middle",
      class: `graph-page-label${Number(page) === Number(state.page) ? " graph-page-label-active" : ""}`,
      "data-page-anchor": String(page),
    });
    label.textContent = pageDisplayLabel(page);
    label.addEventListener("click", () => {
      setCurrentPageFromFullscreen(page);
      updateOverlayHint();
      renderGraph(true);
    });
    graphSvg.appendChild(label);
  });

  generations.forEach((gen, index) => {
    const y = topMargin + index * rowHeight + rowHeight / 2;
    graphSvg.appendChild(createSvgNode("line", {
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
    graphSvg.appendChild(label);
  });

  childMap.forEach((edges, parentId) => {
    const parent = positions.get(parentId);
    const parentPerson = peopleById.get(parentId);
    if (!parent || !parentPerson) return;
    const parentHeight = parentPerson.glyph_image ? nodeHeightWithGlyph : nodeHeightPlain;
    const startY = parent.y + parentHeight / 2;
    const childEntries = edges.map((edge) => {
      const child = positions.get(edge.to_person_id);
      const childPerson = peopleById.get(edge.to_person_id);
      if (!child || !childPerson) return null;
      const childHeight = childPerson.glyph_image ? nodeHeightWithGlyph : nodeHeightPlain;
      return { edge, child, endY: child.y - childHeight / 2 };
    }).filter(Boolean);
    if (!childEntries.length) return;
    const busY = childEntries.length === 1 ? startY + (childEntries[0].endY - startY) * 0.5 : startY + (Math.min(...childEntries.map((item) => item.endY)) - startY) * 0.45;
    const highlightedEntries = childEntries.filter((item) => selectedSubtreeIds.has(parentId) && selectedSubtreeIds.has(item.edge.to_person_id));
    const selectedClass = highlightedEntries.length ? " graph-edge-selected" : "";
    graphSvg.appendChild(createSvgNode("path", {
      d: `M ${parent.x} ${startY} V ${busY}`,
      class: `graph-edge graph-edge-orth${selectedClass}`,
    }));
    if (childEntries.length > 1) {
      const childXs = childEntries.map((item) => item.child.x);
      graphSvg.appendChild(createSvgNode("path", {
        d: `M ${Math.min(...childXs)} ${busY} H ${Math.max(...childXs)}`,
        class: "graph-edge graph-edge-orth",
      }));
      if (highlightedEntries.length) {
        const highlightXs = highlightedEntries.map((item) => item.child.x);
        graphSvg.appendChild(createSvgNode("path", {
          d: `M ${Math.min(parent.x, ...highlightXs)} ${busY} H ${Math.max(parent.x, ...highlightXs)}`,
          class: "graph-edge graph-edge-orth graph-edge-selected",
        }));
      }
    }
    childEntries.forEach((item) => {
      graphSvg.appendChild(createSvgNode("path", {
        d: `M ${item.child.x} ${busY} V ${item.endY}`,
        class: `graph-edge graph-edge-orth${selectedSubtreeIds.has(parentId) && selectedSubtreeIds.has(item.edge.to_person_id) ? " graph-edge-selected" : ""}`,
      }));
      edgeAnchorMap.set(edgeKey(parentId, item.edge.to_person_id), {
        x: item.child.x,
        y: (busY + item.endY) / 2,
      });
    });
  });

  graphNodes.forEach((person) => {
    const pos = positions.get(person.id);
    if (!pos) return;
    const hasGlyph = Boolean(person.glyph_image);
    const nodeHeight = hasGlyph ? nodeHeightWithGlyph : nodeHeightPlain;
    const nodeGroup = createSvgNode("g", {
      class: `graph-node-group${selectedSubtreeIds.has(person.id) ? " graph-node-group-selected" : ""}${state.fullscreenSelectedPersonId === person.id ? " graph-node-group-active" : ""}${person.id === state.linkParentPersonId ? " graph-node-group-link-parent" : ""}${person.id === state.linkChildPersonId ? " graph-node-group-link-child" : ""}${isChildCandidate(person.id) ? " graph-node-group-link-candidate" : ""}${needsParentLink(person) ? " graph-node-group-needs-parent-link" : ""}`,
      "data-person-id": person.id,
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
    if (person.id === state.linkParentPersonId) {
      appendGraphRoleBadge(nodeGroup, pos.x + 22, pos.y - nodeHeight / 2 - 10, "父", "parent");
    } else if (person.id === state.linkChildPersonId) {
      appendGraphRoleBadge(nodeGroup, pos.x + 22, pos.y - nodeHeight / 2 - 10, "子", "child");
    } else if (needsParentLink(person)) {
      appendGraphRoleBadge(nodeGroup, pos.x + 22, pos.y - nodeHeight / 2 - 10, "缺父", "missing-parent");
    }
    nodeGroup.addEventListener("mouseenter", () => {
      if (!state.linkMode) return;
      clearLinkDeleteHoverTimer();
      const incomingEdge = (incoming.get(person.id) || [])[0];
      if (!incomingEdge) return;
      linkDeleteHoverTimer = setTimeout(() => {
        setLinkDeleteEdgeKey(edgeKey(incomingEdge.from_person_id, incomingEdge.to_person_id), true);
      }, LINK_EDGE_DELETE_HOVER_MS);
    });
    nodeGroup.addEventListener("mouseleave", () => {
      clearLinkDeleteHoverTimer();
    });
    nodeGroup.addEventListener("click", () => {
      if (!shouldKeepFullscreenCrossPageContext()) {
        void setCurrentPageFromFullscreen(nodePageMap.get(person.id));
      }
      if (state.linkMode) {
        if (!state.linkParentPersonId) {
          startLinkParent(person.id);
          return;
        }
        if (state.linkParentPersonId === person.id) {
          finishCurrentLinkParent();
          setStatus("已取消当前父节点选择。");
          return;
        }
        completeLinkToChild(person.id, "全屏补链", true);
        return;
      }
      state.fullscreenSelectedPersonId = person.id;
      renderGraph(true);
    });
    graphSvg.appendChild(nodeGroup);
  });

  appendLinkDeleteControl(edgeAnchorMap);

  if (state.fullscreenSelectedPersonId) {
    const leftSiblingId =
      findLeftSiblingId(state.fullscreenSelectedPersonId, childMap, incoming, peopleById) ||
      findLeftRootId(state.fullscreenSelectedPersonId, graphNodes, incoming);
    const rightSiblingId =
      findRightSiblingId(state.fullscreenSelectedPersonId, childMap, incoming, peopleById) ||
      findRightRootId(state.fullscreenSelectedPersonId, graphNodes, incoming);
    const selectedPos = positions.get(state.fullscreenSelectedPersonId);
    if (selectedPos && (leftSiblingId || rightSiblingId)) {
      const actions = [];
      if (leftSiblingId) actions.push({ label: "左移", direction: "left" });
      if (rightSiblingId) actions.push({ label: "右移", direction: "right" });
      const btnWidth = 48;
      const btnHeight = 24;
      const gap = 8;
      const totalWidth = actions.length * btnWidth + (actions.length - 1) * gap;
      actions.forEach((action, index) => {
        const buttonGroup = createSvgNode("g", { class: "graph-action-group" });
        const btnX = selectedPos.x - totalWidth / 2 + index * (btnWidth + gap);
        const btnY = selectedPos.y - 72;
        buttonGroup.appendChild(createSvgNode("rect", {
          x: String(btnX),
          y: String(btnY),
          width: String(btnWidth),
          height: String(btnHeight),
          rx: "12",
          class: "graph-action-btn",
        }));
        const label = createSvgNode("text", {
          x: String(btnX + btnWidth / 2),
          y: String(btnY + 16),
          "text-anchor": "middle",
          class: "graph-action-label",
        });
        label.textContent = action.label;
        buttonGroup.appendChild(label);
        buttonGroup.addEventListener("click", (event) => {
          event.stopPropagation();
          swapSiblingVisualPosition(state.fullscreenSelectedPersonId, action.direction, childMap, incoming, peopleById, graphNodes);
        });
        graphSvg.appendChild(buttonGroup);
      });
    }
  }
}

function renderGraph(fullGraph = false) {
  const { nodes: graphNodes, edges: graphEdges } = buildGraphData(fullGraph);
  if (fullGraph) {
    if (state.fullscreenLayoutMode === "page") {
      renderPageGroupedFullscreenGraph(graphNodes, graphEdges);
    } else {
      renderClassicFullscreenGraph(graphNodes, graphEdges);
    }
    return;
  }
  renderFullscreenPageImages({ pages: [], pageWidthMap: new Map(), width: 0, pageGap: 0, rightMargin: 0 });
  const layout = computeGlobalTreeLayout(graphNodes, graphEdges);
  const groups = {};
  graphNodes.forEach((person) => {
    const key = String(person.generation || "未知");
    groups[key] ||= [];
    groups[key].push(person);
  });
  const generations = Object.keys(groups).sort((a, b) => Number(a) - Number(b));
  generations.forEach((gen) => {
    groups[gen].sort((a, b) => {
      const slotA = layout.slotPositions.get(a.id) ?? -1;
      const slotB = layout.slotPositions.get(b.id) ?? -1;
      return slotB - slotA || (a.name || "").localeCompare(b.name || "", "zh-Hans-CN");
    });
  });

  graphSvg.innerHTML = "";
  const maxCount = Math.max(1, ...generations.map((gen) => groups[gen].length));
  const width = Math.max(900, 240 * generations.length);
  const height = Math.max(520, 100 + maxCount * 96);
  graphSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  graphSvg.style.width = `${Math.round(width * state.graphZoom)}px`;
  graphSvg.style.height = `${Math.round(height * state.graphZoom)}px`;

  const xStep = generations.length > 1 ? (width - 140) / (generations.length - 1) : 1;
  const positions = new Map();

  generations.forEach((gen, gi) => {
    const x = 80 + gi * xStep;
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", x);
    label.setAttribute("y", 28);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "graph-generation");
    label.textContent = `${gen}世`;
    graphSvg.appendChild(label);

    const list = groups[gen];
    const yStep = (height - 90) / (list.length + 1);
    list.forEach((person, index) => {
      const y = 50 + (index + 1) * yStep;
      positions.set(person.id, { x, y });
    });
  });

  graphEdges.forEach((edge) => {
    const a = positions.get(edge.from_person_id);
    const b = positions.get(edge.to_person_id);
    if (!a || !b) return;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const midX = a.x + (b.x - a.x) * 0.5;
    path.setAttribute("d", `M ${a.x} ${a.y} C ${midX} ${a.y}, ${midX} ${b.y}, ${b.x} ${b.y}`);
    path.setAttribute("class", "graph-edge");
    graphSvg.appendChild(path);
  });

  graphNodes.forEach((person) => {
    const pos = positions.get(person.id);
    if (!pos) return;
    const hasGlyph = Boolean(person.glyph_image);
    const nodeHeight = hasGlyph ? 92 : 36;
    const nodeGroup = createSvgNode("g", {
      class: `graph-node-group${person.id === state.linkParentPersonId ? " graph-node-group-link-parent" : ""}${person.id === state.linkChildPersonId ? " graph-node-group-link-child" : ""}${isChildCandidate(person.id) ? " graph-node-group-link-candidate" : ""}${needsParentLink(person) ? " graph-node-group-needs-parent-link" : ""}`,
    });
    nodeGroup.appendChild(createSvgNode("rect", {
      x: String(pos.x - 28),
      y: String(pos.y - nodeHeight / 2),
      width: "56",
      height: String(nodeHeight),
      rx: "8",
      class: "graph-node",
    }));

    if (hasGlyph) {
      nodeGroup.appendChild(createSvgNode("image", {
        href: person.glyph_image,
        x: String(pos.x - 20),
        y: String(pos.y - nodeHeight / 2 + 10),
        width: "40",
        height: "40",
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
    if (person.id === state.linkParentPersonId) {
      appendGraphRoleBadge(nodeGroup, pos.x + 22, pos.y - nodeHeight / 2 - 10, "父", "parent");
    } else if (person.id === state.linkChildPersonId) {
      appendGraphRoleBadge(nodeGroup, pos.x + 22, pos.y - nodeHeight / 2 - 10, "子", "child");
    } else if (needsParentLink(person)) {
      appendGraphRoleBadge(nodeGroup, pos.x + 22, pos.y - nodeHeight / 2 - 10, "缺父", "missing-parent");
    }
    graphSvg.appendChild(nodeGroup);
  });
}

function onPersonInput(event) {
  if (pagePeopleLocked()) {
    setStatus("当前页人物区已锁定，不能编辑人物信息。");
    event.target.blur();
    return;
  }
  const input = event.target;
  const person = state.data.persons.find((item) => item.id === input.dataset.personId);
  if (!person) return;
  const baselineKey = fieldDraftKey(input);
  const baselineValue = fieldDraftBaseline.get(baselineKey);
  let needsPersonRerender = false;
  let needsGraphRerender = false;
  let changed = false;
  if (input.dataset.field === "name") {
    const nextName = input.value.trim();
    if ((baselineValue ?? person.name ?? "") !== nextName) {
      pushHistorySnapshot();
      person.name = nextName;
      changed = true;
      needsPersonRerender = true;
      needsGraphRerender = true;
    }
  } else if (input.dataset.field === "generation") {
    const nextGeneration = Number(input.value);
    const resolvedGeneration = Number.isFinite(nextGeneration) && nextGeneration > 0 ? nextGeneration : person.generation;
    if (person.generation !== resolvedGeneration) {
      pushHistorySnapshot();
      person.generation = resolvedGeneration;
      changed = true;
      needsPersonRerender = true;
      needsGraphRerender = true;
    }
  } else if (input.dataset.field === "page_sources") {
    const nextPageSources = input.value
      .split(",")
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isInteger(item) && item > 0);
    if (JSON.stringify(person.page_sources || []) !== JSON.stringify(nextPageSources)) {
      pushHistorySnapshot();
      person.page_sources = nextPageSources;
      changed = true;
      needsPersonRerender = true;
      needsGraphRerender = true;
    }
  } else if (input.dataset.field === "notes") {
    const nextNotes = input.value
      .split("；")
      .map((item) => item.trim())
      .filter(Boolean);
    const currentNotesText = Array.isArray(person.notes) ? person.notes.join("；") : "";
    if ((baselineValue ?? currentNotesText) !== nextNotes.join("；")) {
      pushHistorySnapshot();
      person.notes = nextNotes;
      changed = true;
    }
  }
  fieldDraftBaseline.delete(baselineKey);
  if (!changed) {
    return;
  }
  if (needsPersonRerender) {
    renderPersons();
  }
  updateOverlayHint();
  if (needsGraphRerender) {
    renderEdges();
    requestGraphRender(document.fullscreenElement === graphWrap);
  }
  renderOcrOverlay();
  scheduleAutoSave();
}

function onPersonDraftInput(event) {
  const input = event.target;
  const person = state.data.persons.find((item) => item.id === input.dataset.personId);
  if (!person) return;
  if (input.dataset.field === "name") {
    person.name = input.value;
  } else if (input.dataset.field === "notes") {
    person.notes = input.value
      .split("；")
      .map((item) => item.trim())
      .filter(Boolean);
  }
}

function addManualPerson() {
  if (pagePeopleLocked()) {
    setStatus("当前页人物区已锁定，不能新增人物。");
    return;
  }
  pushHistorySnapshot();
  const generationHint = pageEntry(state.page)?.generation_hint || [93, 94, 95, 96, 97];
  const fallbackGeneration = generationHint[2] || generationHint[0] || 95;
  const box = defaultManualBox();
  const ref = {
    page: state.page,
    index: `manual_${Date.now()}`,
    text: "",
    raw_text: "",
    box,
    poly: [
      [box[0], box[1]],
      [box[2], box[1]],
      [box[2], box[3]],
      [box[0], box[3]],
    ],
  };
  const person = {
    id: nextAutoPersonId(fallbackGeneration),
    name: nextManualPersonName(),
    generation: fallbackGeneration,
    aliases: [],
    page_sources: [state.page],
    position_hints: [{ page: state.page, box }],
    notes: ["手动新增"],
    text_ref: ref,
    text_refs: [ref],
  };
  state.data.persons.push(person);
  person.glyph_image = makeGlyphFromRawBox(box) || "";
  setActivePerson(person.id);
  setStatus(`已新增 ${person.name}，请修改姓名、世代，并按需绑定图片或截图。`);
  renderPersons();
  renderEdges();
  renderOcrOverlay();
  requestGraphRender(document.fullscreenElement === graphWrap);
  scheduleAutoSave();
}

function onDeletePerson(event) {
  if (pagePeopleLocked()) {
    setStatus("当前页人物区已锁定，不能删除人物。");
    return;
  }
  pushHistorySnapshot();
  const personId = event.target.dataset.deletePerson;
  const before = state.data.persons.length;
  state.data.persons = state.data.persons.filter((person) => person.id !== personId);
  state.data.edges = state.data.edges.filter(
    (edge) => edge.from_person_id !== personId && edge.to_person_id !== personId,
  );
  if (state.activePersonId === personId) {
    state.activePersonId = null;
  }
  if (state.linkParentPersonId === personId) {
    state.linkParentPersonId = null;
  }
  if (state.linkChildPersonId === personId) {
    state.linkChildPersonId = null;
  }
  if (state.data.persons.length !== before) {
    ensureActivePersonForPage();
    setStatus("已删除手动新增人物及其相关关系，记得保存。");
    renderPersons();
    renderEdges();
    renderOcrOverlay();
    requestGraphRender(document.fullscreenElement === graphWrap);
    scheduleAutoSave();
  }
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

async function onPersonImageUpload(event) {
  const input = event.target;
  const person = state.data.persons.find((item) => item.id === input.dataset.uploadInput);
  const file = input.files?.[0];
  if (!person || !file) return;
  pushHistorySnapshot();
  try {
    person.glyph_image = await readFileAsDataUrl(file);
    setActivePerson(person.id);
    setStatus(`已为 ${person.name || person.id} 上传截图，记得保存。`);
    scheduleAutoSave();
  } catch (error) {
    setStatus(`截图读取失败：${error.message}`);
  } finally {
    input.value = "";
  }
}

function onClearTextBinding(event) {
  const person = state.data.persons.find((item) => item.id === event.target.dataset.clearBinding);
  if (!person) return;
  pushHistorySnapshot();
  removeTextRefForPage(person, state.page);
  setActivePerson(person.id);
  setStatus(`已清除 ${person.name || person.id} 的文字框绑定，记得保存。`);
  scheduleAutoSave();
}

function onClearPersonImage(event) {
  const person = state.data.persons.find((item) => item.id === event.target.dataset.clearImage);
  if (!person) return;
  pushHistorySnapshot();
  delete person.glyph_image;
  setActivePerson(person.id);
  setStatus(`已清除 ${person.name || person.id} 的截图，记得保存。`);
  scheduleAutoSave();
}

function onEdgeLabelInput(event) {
  const input = event.target;
  const [, toId] = input.dataset.edgeKey.split("__");
  const person = state.data.persons.find((item) => item.id === toId);
  if (!person) return;
  const nextName = input.value.trim();
  const baselineKey = fieldDraftKey(input);
  const baselineValue = fieldDraftBaseline.get(baselineKey);
  if ((baselineValue ?? person.name ?? "") === nextName) {
    fieldDraftBaseline.delete(baselineKey);
    return;
  }
  pushHistorySnapshot();
  person.name = nextName;
  fieldDraftBaseline.delete(baselineKey);
  renderPersons();
  requestGraphRender(document.fullscreenElement === graphWrap);
  scheduleAutoSave();
}

function onEdgeLabelDraftInput(event) {
  const input = event.target;
  const [, toId] = input.dataset.edgeKey.split("__");
  const person = state.data.persons.find((item) => item.id === toId);
  if (!person) return;
  person.name = input.value;
}

function onParentBridgeInput(event) {
  const input = event.target;
  const childId = input.dataset.parentLink;
  const child = state.data.persons.find((item) => item.id === childId);
  if (!child) return;
  pushHistorySnapshot();

  const name = input.value.trim();
  let edge = incomingEdgeForChild(childId);
  const minPage = Math.min(...state.data.pages);
  const previousPage = Math.max(minPage, state.page - 1);

  if (!name) {
    if (edge) {
      state.data.edges = state.data.edges.filter((item) => item !== edge);
      setStatus(`已移除 ${child.name || child.id} 的上代衔接，记得保存。`);
      renderEdges();
      requestGraphRender(false);
      scheduleAutoSave();
    }
    return;
  }

  let parent = edge ? state.data.persons.find((item) => item.id === edge.from_person_id) : null;
  if (!parent) {
    parent =
      state.data.persons.find(
        (item) => item.name === name && Number(item.generation) === Math.max(1, Number(child.generation) - 1),
      ) || null;
  }

  if (!parent) {
    parent = {
      id: nextAutoPersonId(Math.max(1, Number(child.generation) - 1)),
      name,
      generation: Math.max(1, Number(child.generation) - 1),
      aliases: [],
      page_sources: [...new Set([previousPage, state.page])],
      position_hints: [],
      notes: ["跨页衔接新增"],
    };
    state.data.persons.push(parent);
  }

  if (!edge) {
    edge = {
      from_person_id: parent.id,
      to_person_id: childId,
      relation: "parent_child",
      page_sources: [state.page],
      confidence: "draft",
      notes: ["跨页衔接新增"],
    };
    state.data.edges.push(edge);
  }

  parent.name = name;
  parent.generation = Math.max(1, Number(child.generation) - 1);
  parent.page_sources = [...new Set([...(parent.page_sources || []), previousPage, state.page])];
  setStatus(`已更新 ${child.name || child.id} 的上代衔接，记得保存。`);
  renderPersons();
  renderEdges();
  requestGraphRender(false);
  scheduleAutoSave();
}

function onAddEdgeClick() {
  pushHistorySnapshot();
  const fromName = normalizeName(newEdgeFromInput.value);
  const toName = normalizeName(newEdgeToInput.value);
  let fromId = newEdgeFromSelect.value;
  let toId = newEdgeToSelect.value;

  if (fromName) {
    fromId = findPersonByNameAcrossGroup(fromName)?.id || "";
  }
  if (toName) {
    toId = findPersonByNameAcrossGroup(toName)?.id || "";
  }

  if (fromName && !fromId) {
    setStatus(`未找到父节点人物：${fromName}`);
    return;
  }
  if (toName && !toId) {
    setStatus(`未找到子节点人物：${toName}`);
    return;
  }

  if (!fromId || !toId) {
    setStatus("请先选择或输入父和子。");
    return;
  }
  if (fromId === toId) {
    setStatus("父和子不能是同一人物。");
    return;
  }
  const exists = state.data.edges.some(
    (edge) => edge.from_person_id === fromId && edge.to_person_id === toId && (edge.page_sources || []).includes(state.page),
  );
  if (exists) {
    setStatus("这条父子链已经存在。");
    return;
  }
  const validation = canSelectAsChild(fromId, toId);
  if (!validation.ok) {
    setStatus(validation.reason);
    return;
  }
  state.data.edges.push({
    from_person_id: fromId,
    to_person_id: toId,
    relation: "parent_child",
    page_sources: [state.page],
    confidence: "manual",
    notes: ["人工补链"],
  });
  newEdgeFromInput.value = "";
  newEdgeToInput.value = "";
  newEdgeFromSelect.value = "";
  newEdgeToSelect.value = "";
  setStatus("已新增父子链，记得保存。");
  recomputeSiblingOrderForParent(fromId, state.page);
  renderEdges();
  requestGraphRender(false);
  scheduleAutoSave();
}

function onDeleteEdgeClick(event) {
  pushHistorySnapshot();
  const [fromId, toId] = event.target.dataset.edgeDelete.split("__");
  const before = state.data.edges.length;
  state.data.edges = state.data.edges.filter(
    (edge) => !(edge.from_person_id === fromId && edge.to_person_id === toId && (edge.page_sources || []).includes(state.page)),
  );
  if (state.data.edges.length !== before) {
    setStatus("已删除父子链，记得保存。");
    renderEdges();
    requestGraphRender(false);
    scheduleAutoSave();
  }
}

function onPageMetaChange() {
  const entry = pageEntry(state.page);
  entry.page_role = pageRoleInput.value.trim();
  entry.keep_generation_axis = keepAxisSelect.value === "true";
  entry.manual_notes = pageNotesInput.value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function togglePeopleLock() {
  const entry = pageEntry(state.page);
  if (!entry) return;
  pushHistorySnapshot();
  entry.people_locked = !Boolean(entry.people_locked);
  updatePageControls();
  updateOverlayHint();
  renderPersons();
  renderOcrOverlay();
  setStatus(entry.people_locked ? "已锁定当前页人物区，可继续补父子链。" : "已解除当前页人物区锁定。");
  scheduleAutoSave(0);
}

async function saveData(isAuto = false) {
  onPageMetaChange();
  const refreshedCount = refreshGlyphImagesForCurrentPage();
  setStatus(isAuto ? "自动保存中..." : "正在保存...");
  const response = await fetch(`/api/group?group=${encodeURIComponent(state.data?.group_id || currentGroupId())}&autosave=${isAuto ? "1" : "0"}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.data),
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "保存失败");
  }
  const payload = await response.json();
  if (payload.sqlite_mirror) {
    state.sqliteMirror = payload.sqlite_mirror;
  }
  const saveTarget = payload.path || (Array.isArray(payload.paths) ? payload.paths.join(" , ") : "");
  const dbSummary = payload.sqlite_mirror?.skipped
    ? "；数据库镜像稍后同步"
    : payload.sqlite_mirror?.ok
    ? `；数据库已同步 ${payload.sqlite_mirror.group_count || 0}组/${payload.sqlite_mirror.person_count || 0}人/${payload.sqlite_mirror.relationship_count || 0}边`
    : payload.sqlite_mirror?.error
      ? `；数据库同步失败：${payload.sqlite_mirror.error}`
      : "";
  const glyphSummary = refreshedCount > 0 ? `；当前页已自动更新${refreshedCount}个人物存图` : "";
  updateOverlayHint();
  setStatus((isAuto ? "已自动保存" : saveTarget ? `已保存到 ${saveTarget}` : "已保存") + glyphSummary + dbSummary);
  dirtyPages.delete(Number(state.page));
  if (autoSaveTimer) {
    clearTimeout(autoSaveTimer);
    autoSaveTimer = null;
  }
  if (!isAuto) {
    void loadWorkspaceSummary();
  }
}

function tryBeaconAutoSave() {
  if (!state.data || !currentPageIsDirty() || typeof navigator?.sendBeacon !== "function") {
    return false;
  }
  try {
    onPageMetaChange();
    const url = `/api/group?group=${encodeURIComponent(state.data?.group_id || currentGroupId())}&autosave=1`;
    const body = JSON.stringify(state.data);
    const ok = navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
    if (ok) {
      dirtyPages.delete(Number(state.page));
    }
    return ok;
  } catch (_error) {
    return false;
  }
}

async function fetchWorkspace(groupId) {
  const response = await fetch(`/api/group?group=${encodeURIComponent(groupId)}`);
  if (!response.ok) {
    throw new Error(`加载工作区失败：${groupId}`);
  }
  return response.json();
}

function applyLoadedData(data, preferredPage = null) {
  state.data = data;
  state.fullscreenBoundaryMode = isMergeWorkspace();
  state.fullscreenParentCandidateQuery = "";
  if (fullscreenParentSearchInput) fullscreenParentSearchInput.value = "";
  state.sqliteMirror = null;
  clearHistoryStack();
  state.data.persons = (state.data.persons || []).map((person) => ({
    ...person,
    source_group_id: person.source_group_id || state.data.group_id || currentGroupId(),
  }));
  state.data.pages_data = synthesizePagesData(state.data);
  updateGroupChrome();
  const savedPage = Number(getCookie(PAGE_COOKIE_NAME));
  const pageCandidates = [preferredPage, state.page, savedPage, state.data.pages[0]].filter((value) => Number.isInteger(value));
  state.page = pageCandidates.find((page) => state.data.pages.includes(page)) || state.data.pages[0];
  setUrlGroup(state.data.group_id || currentGroupId());
  pageSelect.innerHTML = state.data.pages
    .map((page) => `<option value="${page}">${pageDisplayLabel(page)}</option>`)
    .join("");
  ensureActivePersonForPage();
  switchPage(state.page);
  refreshUndoAvailability();
  void ensureMergeControl();
}

async function loadWorkspace(groupId, preferredPage = null) {
  if (state.data && currentPageIsDirty()) {
    try {
      await saveData(true);
    } catch (error) {
      setStatus(`切换分组前保存失败：${error.message}`);
      return;
    }
  }
  const data = await fetchWorkspace(groupId);
  applyLoadedData(data, preferredPage);
}

async function goToFirstMissingForMergeControl() {
  const mergeControl = await ensureMergeControl();
  const firstMissing = mergeControl?.first_missing;
  if (!firstMissing) {
    setStatus("两组都已整理完成，可直接进入合并衔接。");
    return;
  }
  await loadWorkspace(firstMissing.group_id, Number(firstMissing.page));
  if (state.page !== Number(firstMissing.page) && state.data?.pages?.includes(Number(firstMissing.page))) {
    switchPage(Number(firstMissing.page));
  }
  state.fullscreenSelectedPersonId = firstMissing.person_id;
  setActivePerson(firstMissing.person_id);
  if (document.fullscreenElement === graphWrap) {
    renderGraph(true);
    scrollFullscreenToCurrentPage();
  }
  setStatus(`还有缺父人物：${firstMissing.name}（第${firstMissing.page}页，第${firstMissing.generation}世）。`);
}

function switchPage(page) {
  state.page = page;
  setCookie(PAGE_COOKIE_NAME, String(page));
  ensureActivePersonForPage();
  pageSelect.value = String(page);
  updateImage();
  updatePageControls();
  renderPersons();
  renderEdges();
  requestGraphRender(false);
}

async function navigateToPage(page) {
  const nextPage = Number(page);
  if (!Number.isInteger(nextPage) || nextPage === Number(state.page)) return;
  if (currentPageIsDirty()) {
    try {
      await saveData(true);
    } catch (error) {
      setStatus(`切页前保存失败：${error.message}`);
      return;
    }
  }
  switchPage(nextPage);
}

async function boot() {
  void loadWorkspaceSummary();
  await loadWorkspace(currentGroupId());
  setStatus("已加载，修改会自动保存。");
  refreshUndoAvailability();
}

document.getElementById("prevPageBtn").addEventListener("click", () => {
  const idx = state.data.pages.indexOf(state.page);
  if (idx > 0) void navigateToPage(state.data.pages[idx - 1]);
});

document.getElementById("nextPageBtn").addEventListener("click", () => {
  const idx = state.data.pages.indexOf(state.page);
  if (idx < state.data.pages.length - 1) void navigateToPage(state.data.pages[idx + 1]);
});

pageSelect.addEventListener("change", (event) => void navigateToPage(Number(event.target.value)));
pageRoleInput.addEventListener("input", onPageMetaChange);
keepAxisSelect.addEventListener("change", onPageMetaChange);
pageNotesInput.addEventListener("input", onPageMetaChange);

linkModeBtn.addEventListener("click", () => {
  setLinkMode(!state.linkMode);
  setStatus(state.linkMode ? "已进入图上补链模式。" : "已退出图上补链模式。");
});

fullscreenLinkModeBtn?.addEventListener("click", () => {
  setLinkMode(!state.linkMode);
  setStatus(state.linkMode ? "已进入图上补链模式。" : "已退出图上补链模式。");
  renderGraph(true);
});

fullscreenLayoutModeBtn?.addEventListener("click", () => {
  state.fullscreenLayoutMode = state.fullscreenLayoutMode === "page" ? "tree" : "page";
  updateOverlayHint();
  renderGraph(true);
  setStatus(state.fullscreenLayoutMode === "page" ? "已切换到按页模式。" : "已切换到按树模式。");
  if (document.fullscreenElement === graphWrap) {
    scrollFullscreenToCurrentPage();
  }
});

fullscreenBoundaryModeBtn?.addEventListener("click", () => {
  if (!isMergeWorkspace()) return;
  state.fullscreenBoundaryMode = !state.fullscreenBoundaryMode;
  updateOverlayHint();
  renderGraph(true);
  setStatus(state.fullscreenBoundaryMode ? "已切换到边界专用视图。" : "已切换到全量视图。");
  if (document.fullscreenElement === graphWrap) {
    scrollFullscreenToCurrentPage();
  }
});

finishLinkBtn.addEventListener("click", () => {
  finishCurrentLinkParent();
  setStatus("已结束当前父节点。");
});

fullscreenFinishLinkBtn?.addEventListener("click", () => {
  finishCurrentLinkParent();
  setStatus("已结束当前父节点。");
});

mergeActionBtn?.addEventListener("click", async () => {
  const mergeAction = nextMergeActionContext();
  if (!mergeAction) return;
  const mergeControl = await ensureMergeControl();
  if (!mergeControl) return;
  if (!mergeControl.ready) {
    await goToFirstMissingForMergeControl();
    return;
  }
  await loadWorkspace(mergeAction.target_workspace_id, state.page);
  setStatus(`已进入 ${mergeAction.target_label} 合并衔接工作区。`);
  if (document.fullscreenElement === graphWrap) {
    renderGraph(true);
    scrollFullscreenToCurrentPage();
  }
});

fullscreenParentSearchInput?.addEventListener("input", () => {
  state.fullscreenParentCandidateQuery = fullscreenParentSearchInput.value || "";
  renderFullscreenParentPanel();
});

pageImage.addEventListener("load", () => {
  renderOcrOverlay();
});

graphFullscreenBtn.addEventListener("click", async () => {
  if (document.fullscreenElement === graphWrap) {
    await document.exitFullscreen();
    return;
  }
  if (graphWrap.requestFullscreen) {
    await graphWrap.requestFullscreen();
  }
});

graphZoomInBtn.addEventListener("click", () => {
  state.graphZoom = Math.min(3, state.graphZoom + 0.15);
  requestGraphRender(document.fullscreenElement === graphWrap);
});

graphZoomOutBtn.addEventListener("click", () => {
  state.graphZoom = Math.max(0.5, state.graphZoom - 0.15);
  requestGraphRender(document.fullscreenElement === graphWrap);
});

graphZoomResetBtn.addEventListener("click", () => {
  state.graphZoom = 1;
  requestGraphRender(document.fullscreenElement === graphWrap);
});

undoBtn.addEventListener("click", undoLastChange);
addPersonBtn.addEventListener("click", addManualPerson);
peopleLockBtn?.addEventListener("click", togglePeopleLock);

addEdgeBtn.addEventListener("click", onAddEdgeClick);
newEdgeFromSelect.addEventListener("change", () => {
  const person = state.data.persons.find((item) => item.id === newEdgeFromSelect.value);
  if (person) newEdgeFromInput.value = person.name || "";
});
newEdgeToSelect.addEventListener("change", () => {
  const person = state.data.persons.find((item) => item.id === newEdgeToSelect.value);
  if (person) newEdgeToInput.value = person.name || "";
});

document.addEventListener("fullscreenchange", () => {
  graphFullscreenBtn.textContent = document.fullscreenElement === graphWrap ? "退出全屏" : "全屏查看";
  if (document.fullscreenElement !== graphWrap) {
    clearLinkDeleteControl(false);
  }
  updateOverlayHint();
  requestGraphRender(document.fullscreenElement === graphWrap);
  if (document.fullscreenElement !== graphWrap) {
    renderPersons();
    renderEdges();
    renderOcrOverlay();
  }
  if (document.fullscreenElement === graphWrap) {
    void ensureMergeControl();
  }
  if (document.fullscreenElement === graphWrap) {
    scrollFullscreenToCurrentPage();
  }
});

graphSvg.addEventListener("click", (event) => {
  const target = event.target;
  const keepVisible =
    target?.closest?.(".graph-node-group") ||
    target?.closest?.(".graph-edge-delete-action");
  if (!keepVisible && state.linkDeleteEdgeKey) {
    setLinkDeleteEdgeKey(null, isGraphFullscreen());
  }
});

document.addEventListener("paste", async (event) => {
  const person = activePerson();
  if (!person) return;
  const item = [...(event.clipboardData?.items || [])].find((entry) => entry.type.startsWith("image/"));
  if (!item) return;
  event.preventDefault();
  const file = item.getAsFile();
  if (!file) return;
  pushHistorySnapshot();
  try {
    person.glyph_image = await readFileAsDataUrl(file);
    setStatus(`已为 ${person.name || person.id} 粘贴截图，记得保存。`);
    renderPersons();
    scheduleAutoSave();
  } catch (error) {
    setStatus(`粘贴截图失败：${error.message}`);
  }
});

document.addEventListener("mousemove", (event) => {
  if (!state.dragAction) return;
  const point = clientToImagePoint(event.clientX, event.clientY);
  if (!point) return;
  const person = state.data.persons.find((item) => item.id === state.dragAction.personId);
  if (!person) return;
  const [x1, y1, x2, y2] = state.dragAction.startBox;
  const dx = point.x - state.dragAction.start.x;
  const dy = point.y - state.dragAction.start.y;
  if (Math.abs(dx) > 2 || Math.abs(dy) > 2) {
    state.dragAction.moved = true;
  }
  let nextBox;
  if (state.dragAction.type === "move") {
    const width = x2 - x1;
    const height = y2 - y1;
    const nx1 = Math.max(0, Math.min(pageImage.naturalWidth - width, x1 + dx));
    const ny1 = Math.max(0, Math.min(pageImage.naturalHeight - height, y1 + dy));
    nextBox = [nx1, ny1, nx1 + width, ny1 + height];
  } else {
    const nx2 = Math.max(x1 + 24, Math.min(pageImage.naturalWidth, x2 + dx));
    const ny2 = Math.max(y1 + 24, Math.min(pageImage.naturalHeight, y2 + dy));
    nextBox = [x1, y1, nx2, ny2];
  }
  syncPersonRefBox(person, nextBox);
  renderOcrOverlay();
});

document.addEventListener("mouseup", () => {
  if (!state.dragAction) return;
  if (!state.dragAction.moved) {
    state.dragAction = null;
    return;
  }
  pushProvidedSnapshot(state.dragAction.snapshot);
  const person = state.data.persons.find((item) => item.id === state.dragAction.personId);
  const incoming = person ? incomingEdgeForChild(person.id) : null;
  if (incoming) {
    recomputeSiblingOrderForParent(incoming.from_person_id, state.page);
  }
  if (person) {
    const ref = refForPage(person, state.page);
    if (ref?.box) {
      person.glyph_image = makeGlyphFromRawBox(ref.box) || person.glyph_image || "";
    }
  }
  state.dragAction = null;
  renderPersons();
  renderOcrOverlay();
  requestGraphRender(document.fullscreenElement === graphWrap);
  scheduleAutoSave();
});

document.addEventListener("keydown", (event) => {
  const isUndo = (event.metaKey || event.ctrlKey) && !event.shiftKey && event.key.toLowerCase() === "z";
  if (!isUndo) return;
  const targetTag = event.target?.tagName?.toLowerCase();
  if (targetTag === "input" || targetTag === "textarea" || event.target?.isContentEditable) {
    return;
  }
  event.preventDefault();
  undoLastChange();
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && currentPageIsDirty()) {
    void flushAutoSave();
  }
});

window.addEventListener("pagehide", () => {
  if (currentPageIsDirty()) {
    tryBeaconAutoSave();
  }
});

boot().catch((error) => {
  setStatus(`加载失败：${error.message}`);
});
