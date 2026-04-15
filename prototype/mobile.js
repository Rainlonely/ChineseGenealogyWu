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
};

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

function updateMobileContributeHeading() {
  const name = mobileState.selectedPerson ? mobileState.selectedPerson.name : "当前人物";
  document.getElementById("mobile-contribute-heading").textContent = `为 ${name} 提交现代续修线索`;
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
          <strong>${person.name}</strong>
          <p class="helper-copy">父名：${person.father_name || "未识别"}</p>
        </div>
        <span class="pill ${person.has_modern_extension ? "" : "muted"}">${person.generation_label}</span>
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
        <strong>${item.name}</strong>
        <p>${item.note}</p>
      </div>
    `;
    routeList.appendChild(li);
  });
}

async function renderMobileDetail() {
  if (!mobileState.selectedPerson) return;
  const ref = mobileSelectedRef();
  const [detail, biography, route] = await Promise.all([
    fetchJson(`/api/v1/persons/${ref}`),
    fetchJson(`/api/v1/persons/${ref}/biography`),
    fetchJson(`/api/v1/persons/${ref}/route`),
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
  button.addEventListener("click", () => switchMobileScreen(button.dataset.mobileScreen));
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

setMobileSearchStatus(`当前 API：${apiBase}。默认示例词可用：永昌`);
renderMobileResults();
updateMobileContributeHeading();
