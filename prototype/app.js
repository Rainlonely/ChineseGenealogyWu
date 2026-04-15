const apiBase =
  window.localStorage.getItem("genealogyApiBase") ||
  window.location.search.match(/[?&]api=([^&]+)/)?.[1] ||
  "http://127.0.0.1:8000";

const state = {
  activeScreen: "search",
  query: "永昌",
  results: [],
  selectedPerson: null,
};

const resultList = document.getElementById("result-list");
const routeList = document.getElementById("route-list");

function switchScreen(screenName) {
  state.activeScreen = screenName;
  document.querySelectorAll(".screen").forEach((screen) => {
    screen.classList.toggle("active", screen.dataset.screen === screenName);
  });
  document.querySelectorAll(".nav-link").forEach((link) => {
    link.classList.toggle("active", link.dataset.screenTarget === screenName);
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

function updateContributeHeading() {
  const name = state.selectedPerson ? state.selectedPerson.name : "当前人物";
  document.getElementById("contribute-heading").textContent = `为 ${name} 提交现代续修信息`;
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
        <strong>${person.name}</strong>
        <span class="cell-label">整行可点击查看人物详情</span>
      </span>
      <span class="result-cell">
        <span class="cell-label">父名</span>
        <span>${person.father_name || "未识别"}</span>
      </span>
      <span class="result-cell">
        <span class="cell-label">世代</span>
        <span>${person.generation_label}</span>
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

    actions.appendChild(bioButton);
    actions.appendChild(contributeButton);
    card.appendChild(actions);
    resultList.appendChild(card);
  });
}

function renderRoute(items) {
  routeList.innerHTML = "";
  items.forEach((item) => {
    const entry = document.createElement("li");
    entry.innerHTML = `
      <div class="route-generation">${item.generation ? `${item.generation}世` : "现代"}</div>
      <div class="route-person">
        <strong>${item.name}</strong>
        <div class="preview-meta">${item.note}</div>
      </div>
    `;
    routeList.appendChild(entry);
  });
}

async function renderDetail() {
  if (!state.selectedPerson) return;
  const ref = selectedRef();
  const [detail, biography, route] = await Promise.all([
    fetchJson(`/api/v1/persons/${ref}`),
    fetchJson(`/api/v1/persons/${ref}/biography`),
    fetchJson(`/api/v1/persons/${ref}/route`),
  ]);

  const item = detail.item;
  document.getElementById("detail-name").textContent = item.name;
  document.getElementById("detail-generation").textContent = item.generation_label;
  document.getElementById("detail-father").textContent = `父名：${item.father_name || "未识别"}`;
  document.getElementById("detail-source").textContent = `数据来源：${item.source_label}`;
  document.getElementById("detail-biography").textContent =
    biography.available
      ? biography.text_punctuated || biography.text_linear || biography.text_raw || "已收录人物小传"
      : "当前没有可展示的人物小传。";

  renderRoute(route.items);
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
}

async function selectPerson(person) {
  state.selectedPerson = person;
  updateContributeHeading();
  await renderDetail();
  switchScreen("detail");
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

document.querySelectorAll("[data-go-screen]").forEach((button) => {
  button.addEventListener("click", () => switchScreen(button.dataset.goScreen));
});

document.querySelectorAll(".nav-link").forEach((button) => {
  button.addEventListener("click", () => switchScreen(button.dataset.screenTarget));
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

renderResults();
setSearchStatus(`当前 API：${apiBase}。默认示例词可用：永昌`);
updateContributeHeading();
