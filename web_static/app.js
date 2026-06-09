const DETAIL_SECONDS = 180;

const state = {
  activeSlot: 0,
  activeFormation: 0,
  filter: "all",
  catalogFilters: {
    weaponType: "",
    element: "",
    squad: "",
    class: ""
  },
  catalog: [],
  formations: [],
  results: [],
  additionalBuffs: [
    { type: "cooldown_reduction", enabled: true, value: 5 },
    { type: "max_ammo_rate", enabled: true, value: 100 }
  ]
};

const defaults = [
  { kind: "dummy", id: "dummy_b1" },
  { kind: "dummy", id: "dummy_b2" },
  { kind: "dummy", id: "dummy_b3" },
  { kind: "dummy", id: "dummy_b3_2" },
  null
];

const additionalBuffTypes = [
  { type: "cooldown_reduction", label: "CT短縮", defaultValue: 5, unit: "秒" },
  { type: "max_ammo_rate", label: "装弾数バフ", defaultValue: 100, unit: "%" },
  { type: "reload_speed_rate", label: "リロード速度バフ", defaultValue: 100, unit: "%" },
  { type: "elemental_buff", label: "有利コードダメージバフ", defaultValue: 10, unit: "%" }
];

function yenNumber(value) {
  return new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 0 }).format(value || 0);
}

function smallNumber(value) {
  return new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 2 }).format(value || 0);
}

function stageLabel(stage) {
  if (!stage) return "-";
  if (stage === "∀") return "ALL";
  return `B${stage}`;
}

function normalizeText(value) {
  return String(value || "").toLowerCase();
}

function itemKey(item) {
  return item.kind === "dummy" ? `dummy:${item.id}` : `character:${item.file}`;
}

function selectionEquals(a, b) {
  if (!a || !b) return false;
  if (a.kind !== b.kind) return false;
  return a.kind === "dummy" ? a.id === b.id : a.file === b.file;
}

function findCatalogItem(selection) {
  if (!selection) return null;
  return state.catalog.find((item) => selectionEquals(item, selection)) || null;
}

function additionalBuffDefinition(type) {
  return additionalBuffTypes.find((buff) => buff.type === type) || additionalBuffTypes[0];
}

function cloneAdditionalBuff(buff) {
  const definition = additionalBuffDefinition(buff?.type);
  return {
    type: definition.type,
    enabled: buff?.enabled !== false,
    value: Number.isFinite(Number(buff?.value)) ? Number(buff.value) : definition.defaultValue
  };
}

function defaultStagesForItem(item) {
  const stage = String(item?.burstStage || "");
  if (stage === "1" || stage === "2" || stage === "3") return new Set([stage]);
  if (stage === "∀" || stage === "ALL" || stage === "*" || stage === "all") return new Set(["3"]);
  return new Set();
}

function createFormation(name) {
  return {
    name,
    slots: [null, null, null, null, null],
    rotation: [new Set(["1"]), new Set(["2"]), new Set(["3"]), new Set(["3"]), new Set()],
    result: null
  };
}

function cloneSelection(selection) {
  return selection ? { kind: selection.kind, file: selection.file, id: selection.id } : null;
}

function cloneFormation(source, name) {
  return {
    name,
    slots: source.slots.map(cloneSelection),
    rotation: source.rotation.map((stageSet) => new Set(stageSet)),
    result: null
  };
}

function activeFormationState() {
  return state.formations[state.activeFormation];
}

function applyDefaultSlots(formation) {
  defaults.forEach((selection, index) => {
    const item = selection ? findCatalogItem(selection) : null;
    formation.slots[index] = item ? { kind: item.kind, file: item.file, id: item.id } : null;
    formation.rotation[index] = item ? defaultStagesForItem(item) : new Set();
  });
}

function resetActiveFormation() {
  const formation = activeFormationState();
  applyDefaultSlots(formation);
  formation.result = null;
  state.activeSlot = 0;
  renderFormationTabs();
  renderFormation();
}

function addFormation() {
  const formation = createFormation(`編成${state.formations.length + 1}`);
  applyDefaultSlots(formation);
  state.formations.push(formation);
  state.activeFormation = state.formations.length - 1;
  state.activeSlot = 0;
  renderFormationTabs();
  renderFormation();
}

function copyActiveFormation() {
  const source = activeFormationState();
  if (!source) return;
  const formation = cloneFormation(source, `${source.name} コピー`);
  state.formations.push(formation);
  state.activeFormation = state.formations.length - 1;
  state.activeSlot = 0;
  renderFormationTabs();
  renderFormation();
}

function setFormation(slotIndex, item) {
  const formation = activeFormationState();
  formation.slots[slotIndex] = item ? { kind: item.kind, file: item.file, id: item.id } : null;
  formation.rotation[slotIndex] = item ? defaultStagesForItem(item) : new Set();
  formation.result = null;
  state.activeSlot = Math.min(4, slotIndex + 1);
  renderFormationTabs();
  renderFormation();
}

function populateCatalogFilters() {
  document.querySelectorAll(".catalog-filter").forEach((select) => {
    const key = select.dataset.filterKey;
    const current = state.catalogFilters[key] || "";
    const defaultLabel = select.options[0]?.textContent || "";
    select.innerHTML = "";

    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = defaultLabel;
    select.appendChild(allOption);

    const values = Array.from(
      new Set(
        state.catalog
          .map((item) => item[key])
          .filter((value) => value !== undefined && value !== null && String(value).trim() !== "")
      )
    ).sort((a, b) => String(a).localeCompare(String(b), "ja", { numeric: true, sensitivity: "base" }));

    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      option.selected = value === current;
      select.appendChild(option);
    });
  });
}

function filteredCatalog() {
  const query = normalizeText(document.getElementById("searchInput").value);
  return state.catalog.filter((item) => {
    const haystack = normalizeText([
      item.name,
      item.file,
      item.weaponType,
      item.element,
      item.class,
      item.squad,
      item.burstStage
    ].join(" "));
    const matchesQuery = !query || haystack.includes(query);
    if (!matchesQuery) return false;
    if (state.filter === "all") return true;
    if (state.filter === "dummy") return item.kind === "dummy";
    return String(item.burstStage) === state.filter;
  }).filter((item) => {
    return Object.entries(state.catalogFilters).every(([key, value]) => {
      return !value || String(item[key] || "") === String(value);
    });
  });
}

function renderCatalog() {
  const list = document.getElementById("characterList");
  const items = filteredCatalog();
  list.innerHTML = "";

  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "message";
    empty.textContent = "一致するキャラがありません";
    list.appendChild(empty);
    return;
  }

  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "character-item";
    button.dataset.key = itemKey(item);

    const main = document.createElement("div");
    const name = document.createElement("div");
    name.className = "character-name";
    name.textContent = item.name;
    const meta = document.createElement("div");
    meta.className = "character-meta";
    const cooldown = item.cooldownTime === "" ? "-" : `${smallNumber(item.cooldownTime)}s`;
    meta.textContent = `${item.weaponType || "-"} / ${item.element || "-"} / CT ${cooldown}`;
    main.append(name, meta);

    const badge = document.createElement("span");
    badge.className = "stage-badge";
    badge.textContent = stageLabel(String(item.burstStage || ""));

    button.append(main, badge);
    button.addEventListener("click", () => setFormation(state.activeSlot, item));
    list.appendChild(button);
  });
}

function renderFormationTabs() {
  const tabs = document.getElementById("formationTabs");
  tabs.innerHTML = "";

  state.formations.forEach((formation, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `formation-tab${index === state.activeFormation ? " active" : ""}`;
    const total = formation.result?.totalPartyDamage;
    button.textContent = total ? `${formation.name} ${yenNumber(total)}` : formation.name;
    button.addEventListener("click", () => {
      state.activeFormation = index;
      state.activeSlot = 0;
      renderFormationTabs();
      renderFormation();
    });
    tabs.appendChild(button);
  });
}

function renderFormation() {
  const formation = activeFormationState();
  const slots = document.getElementById("formationSlots");
  slots.innerHTML = "";

  formation.slots.forEach((selection, index) => {
    const item = findCatalogItem(selection);
    const slot = document.createElement("div");
    slot.className = `slot${index === state.activeSlot ? " active" : ""}`;

    const main = document.createElement("div");
    main.className = "slot-main";
    main.tabIndex = 0;
    main.addEventListener("click", () => {
      state.activeSlot = index;
      renderFormation();
    });
    main.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        state.activeSlot = index;
        renderFormation();
      }
    });

    const idx = document.createElement("span");
    idx.className = "slot-index";
    idx.textContent = String(index + 1);

    const body = document.createElement("div");
    const name = document.createElement("div");
    name.className = item ? "slot-name" : "slot-empty";
    name.textContent = item ? item.name : "未設定";
    const meta = document.createElement("div");
    meta.className = "slot-meta";
    meta.textContent = item
      ? `${stageLabel(String(item.burstStage || ""))} / ${item.weaponType || "-"} / ${item.class || "-"}`
      : "クリックして選択先にする";
    body.append(name, meta);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "slot-remove";
    remove.textContent = "外す";
    remove.disabled = !item;
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      formation.slots[index] = null;
      formation.rotation[index] = new Set();
      formation.result = null;
      renderFormationTabs();
      renderFormation();
    });

    main.append(idx, body, remove);

    const controls = document.createElement("div");
    controls.className = "rotation-controls";
    const label = document.createElement("span");
    label.textContent = "バースト";
    controls.appendChild(label);

    ["1", "2", "3"].forEach((stage) => {
      const wrap = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = formation.rotation[index].has(stage);
      checkbox.disabled = !item;
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) formation.rotation[index].add(stage);
        else formation.rotation[index].delete(stage);
        formation.result = null;
        renderFormationTabs();
      });
      wrap.append(checkbox, document.createTextNode(`B${stage}`));
      controls.appendChild(wrap);
    });

    slot.append(main, controls);
    slots.appendChild(slot);
  });
}

function renderAdditionalBuffs() {
  const list = document.getElementById("additionalBuffList");
  if (!list) return;
  list.innerHTML = "";

  state.additionalBuffs = state.additionalBuffs.map(cloneAdditionalBuff);
  if (!state.additionalBuffs.length) {
    const empty = document.createElement("div");
    empty.className = "additional-buff-empty";
    empty.textContent = "追加バフはありません";
    list.appendChild(empty);
    return;
  }

  state.additionalBuffs.forEach((buff, index) => {
    const definition = additionalBuffDefinition(buff.type);
    const row = document.createElement("div");
    row.className = "additional-buff-row";

    const enabled = document.createElement("input");
    enabled.type = "checkbox";
    enabled.checked = buff.enabled;
    enabled.title = "発動";
    enabled.addEventListener("change", () => {
      state.additionalBuffs[index].enabled = enabled.checked;
    });

    const typeSelect = document.createElement("select");
    typeSelect.className = "buff-type";
    additionalBuffTypes.forEach((type) => {
      const option = document.createElement("option");
      option.value = type.type;
      option.textContent = type.label;
      option.selected = type.type === buff.type;
      typeSelect.appendChild(option);
    });
    typeSelect.addEventListener("change", () => {
      const nextDefinition = additionalBuffDefinition(typeSelect.value);
      state.additionalBuffs[index].type = nextDefinition.type;
      state.additionalBuffs[index].value = nextDefinition.defaultValue;
      renderAdditionalBuffs();
    });

    const value = document.createElement("input");
    value.className = "buff-value";
    value.type = "number";
    value.min = "0";
    value.step = definition.unit === "秒" ? "0.1" : "1";
    value.value = buff.value;
    value.addEventListener("input", () => {
      state.additionalBuffs[index].value = value.value;
    });

    const unit = document.createElement("span");
    unit.className = "buff-unit";
    unit.textContent = definition.unit;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "buff-remove";
    remove.title = "削除";
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      state.additionalBuffs.splice(index, 1);
      renderAdditionalBuffs();
    });

    row.append(enabled, typeSelect, value, unit, remove);
    list.appendChild(row);
  });
}

function addAdditionalBuff() {
  const type = document.getElementById("additionalBuffType").value;
  const definition = additionalBuffDefinition(type);
  state.additionalBuffs.push({
    type: definition.type,
    enabled: true,
    value: definition.defaultValue
  });
  renderAdditionalBuffs();
}

function collectPayloadForFormation(formation) {
  const rotation = { 1: [], 2: [], 3: [] };
  formation.rotation.forEach((stageSet, slotIndex) => {
    ["1", "2", "3"].forEach((stage) => {
      if (stageSet.has(stage) && formation.slots[slotIndex]) {
        rotation[stage].push(slotIndex);
      }
    });
  });

  return {
    formation: formation.slots,
    rotation,
    options: {
      skillLevel: document.getElementById("skillLevel").value,
      enemyElement: document.getElementById("enemyElement").value,
      enemyCoreSize: document.getElementById("enemyCoreSize").value,
      enemySize: document.getElementById("enemySize").value,
      enemyCount: document.getElementById("enemyCount").value,
      burstChargeTime: document.getElementById("burstChargeTime").value,
      crustOperationMode: document.getElementById("crustOperationMode").value,
      partBreakMode: document.getElementById("partBreakMode").checked,
      specialMode: document.getElementById("specialMode").checked,
      additionalBuffs: state.additionalBuffs.map(cloneAdditionalBuff)
    }
  };
}

function setRunStatus(text, isError = false) {
  const status = document.getElementById("runStatus");
  status.textContent = text;
  status.classList.toggle("error", isError);
}

function renderResults(entries) {
  state.results = entries;
  const okEntries = entries.filter((entry) => entry.data && !entry.error);
  const totalDamage = okEntries.reduce((sum, entry) => sum + entry.data.totalPartyDamage, 0);
  const totalAmmo = okEntries.reduce((sum, entry) => sum + entry.data.totalAllyAmmoConsumed, 0);
  const elapsed = okEntries.reduce((sum, entry) => sum + entry.data.elapsedSeconds, 0);

  document.querySelector("#summary div:nth-child(1) strong").textContent = okEntries.length
    ? yenNumber(totalDamage)
    : "-";
  document.querySelector("#summary div:nth-child(2) strong").textContent = okEntries.length
    ? yenNumber(totalAmmo)
    : "-";
  document.querySelector("#summary div:nth-child(3) strong").textContent = okEntries.length
    ? `${smallNumber(elapsed)}s`
    : "-";

  const rotation = document.getElementById("rotationSummary");
  rotation.innerHTML = "";
  okEntries.forEach((entry) => {
    const div = document.createElement("div");
    const parts = Object.entries(entry.data.rotation).map(([stage, names]) => `B${stage}: ${names.join(" → ")}`);
    div.textContent = `${entry.name} / ${parts.join(" / ")}`;
    rotation.appendChild(div);
  });

  const rows = document.getElementById("resultRows");
  rows.innerHTML = "";

  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "message";
    empty.textContent = "まだ結果がありません";
    rows.appendChild(empty);
    return;
  }

  entries.forEach((entry) => {
    const title = document.createElement("div");
    title.className = "formation-result-title";
    title.textContent = entry.error
      ? `${entry.name} / エラー`
      : `${entry.name} / 総ダメージ ${yenNumber(entry.data.totalPartyDamage)}`;
    rows.appendChild(title);

    if (entry.error) {
      const message = document.createElement("div");
      message.className = "message";
      message.textContent = entry.error;
      rows.appendChild(message);
      return;
    }

    entry.data.results
      .slice()
      .sort((a, b) => b.totalDamage - a.totalDamage)
      .forEach((row) => {
        const item = document.createElement("div");
        item.className = "result-item";

        const head = document.createElement("div");
        head.className = "result-head";
        const name = document.createElement("strong");
        name.textContent = row.name;
        const damage = document.createElement("button");
        damage.type = "button";
        damage.className = "damage-button";
        damage.textContent = yenNumber(row.totalDamage);
        damage.title = "詳細を表示";
        damage.addEventListener("click", () => openDetail(entry, row));
        head.append(name, damage);

        const breakdown = document.createElement("div");
        breakdown.className = "breakdown";
        if (!row.breakdown.length) {
          const empty = document.createElement("div");
          empty.className = "breakdown-row";
          empty.textContent = "ダメージなし";
          breakdown.appendChild(empty);
        } else {
          row.breakdown.forEach((sourceEntry) => {
            const line = document.createElement("div");
            line.className = "breakdown-row";
            const source = document.createElement("span");
            source.textContent = sourceEntry.source;
            const value = document.createElement("strong");
            const count = Number(sourceEntry.count || 0);
            const average = Number(sourceEntry.averageDamage || 0);
            value.textContent = count
              ? `${yenNumber(sourceEntry.damage)} / ${count}回 / 平均 ${yenNumber(average)}`
              : yenNumber(sourceEntry.damage);
            line.append(source, value);
            breakdown.appendChild(line);
          });
        }

        item.append(head, breakdown);
        rows.appendChild(item);
      });
  });
}

async function postSimulation(formation) {
  const response = await fetch("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectPayloadForFormation(formation))
  });
  const data = await response.json();
  if (!response.ok || data.status !== "ok") {
    throw new Error(data.error || "シミュレーションに失敗しました");
  }
  return data;
}

async function runSimulation(runAll = false) {
  const runButton = document.getElementById("runButton");
  const runAllButton = document.getElementById("runAllButton");
  runButton.disabled = true;
  runAllButton.disabled = true;
  setRunStatus("実行中");
  document.getElementById("resultRows").innerHTML = "";

  const targets = runAll
    ? state.formations.map((formation, index) => ({ formation, index }))
    : [{ formation: activeFormationState(), index: state.activeFormation }];
  const entries = [];

  try {
    for (const target of targets) {
      setRunStatus(`${target.formation.name} 実行中`);
      try {
        const data = await postSimulation(target.formation);
        target.formation.result = data;
        entries.push({ name: target.formation.name, index: target.index, data });
      } catch (error) {
        target.formation.result = null;
        entries.push({ name: target.formation.name, index: target.index, error: error.message });
      }
      renderFormationTabs();
      renderResults(entries);
    }
    setRunStatus(entries.some((entry) => entry.error) ? "一部エラー" : "完了", entries.some((entry) => entry.error));
  } finally {
    runButton.disabled = false;
    runAllButton.disabled = false;
  }
}

function formatBuffValue(value, effect) {
  const numeric = Number(value) || 0;
  const fixedEffects = new Set(["atk_buff_fixed", "max_hp_fixed", "shield", "counter"]);
  if (Math.abs(numeric) <= 5 && !fixedEffects.has(effect)) {
    return `${smallNumber(numeric * 100)}%`;
  }
  return yenNumber(numeric);
}

function openDetail(entry, row) {
  const modal = document.getElementById("detailModal");
  document.getElementById("detailTitle").textContent = `${entry.name} / ${row.name}`;
  document.getElementById("detailSubtitle").textContent = `総ダメージ ${yenNumber(row.totalDamage)} / B${row.burstStage}`;
  modal.hidden = false;
  drawDamageChart(row.damageSeries || []);
  renderDamageSummary(row.breakdown || []);
  renderBurstTimeline(row.burstEvents || []);
  renderBuffTimeline(row.buffTimeline || []);
}

function closeDetail() {
  document.getElementById("detailModal").hidden = true;
}

function drawDamageChart(series) {
  const canvas = document.getElementById("damageChart");
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const pad = { left: 58, right: 18, top: 18, bottom: 36 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const values = Array.from({ length: DETAIL_SECONDS }, (_, index) => Number(series[index] || 0));
  const cumulative = [];
  values.reduce((sum, value, index) => {
    cumulative[index] = sum + value;
    return cumulative[index];
  }, 0);
  const maxPerSecond = Math.max(1, ...values);
  const maxCumulative = Math.max(1, ...cumulative);

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "#d8e0df";
  ctx.lineWidth = 1;
  ctx.font = "12px sans-serif";
  ctx.fillStyle = "#60706d";

  for (let i = 0; i <= 6; i += 1) {
    const x = pad.left + (plotW * i) / 6;
    ctx.beginPath();
    ctx.moveTo(x, pad.top);
    ctx.lineTo(x, pad.top + plotH);
    ctx.stroke();
    ctx.fillText(String(i * 30), x - 8, height - 12);
  }

  for (let i = 0; i <= 4; i += 1) {
    const y = pad.top + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + plotW, y);
    ctx.stroke();
  }

  const barW = Math.max(1, plotW / DETAIL_SECONDS);
  ctx.fillStyle = "rgba(11, 107, 100, 0.38)";
  values.forEach((value, index) => {
    const x = pad.left + index * barW;
    const barH = (value / maxPerSecond) * plotH;
    ctx.fillRect(x, pad.top + plotH - barH, Math.max(1, barW - 1), barH);
  });

  ctx.strokeStyle = "#ad5b13";
  ctx.lineWidth = 2;
  ctx.beginPath();
  cumulative.forEach((value, index) => {
    const x = pad.left + (index / (DETAIL_SECONDS - 1)) * plotW;
    const y = pad.top + plotH - (value / maxCumulative) * plotH;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = "#172322";
  ctx.fillText("秒", width - 22, height - 12);
  ctx.fillText(`秒間最大 ${yenNumber(maxPerSecond)}`, pad.left, 14);
  ctx.fillStyle = "#ad5b13";
  ctx.fillText(`累計 ${yenNumber(maxCumulative)}`, width - 160, 14);
}

function renderDamageSummary(breakdown) {
  const container = document.getElementById("damageSummary");
  container.innerHTML = "";

  if (!breakdown.length) {
    const empty = document.createElement("div");
    empty.className = "detail-empty";
    empty.textContent = "ダメージ内訳はありません";
    container.appendChild(empty);
    return;
  }

  const table = document.createElement("table");
  table.className = "damage-summary-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["種別", "ダメージ", "回数", "1回あたり"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  breakdown
    .slice()
    .sort((a, b) => Number(b.damage || 0) - Number(a.damage || 0))
    .forEach((entry) => {
      const tr = document.createElement("tr");
      const source = document.createElement("td");
      const type = document.createElement("span");
      type.className = "damage-source-type";
      type.textContent = entry.sourceType || "スキル";
      const name = document.createElement("strong");
      name.textContent = entry.source;
      source.append(type, name);

      const damage = document.createElement("td");
      damage.textContent = yenNumber(entry.damage);
      const count = document.createElement("td");
      count.textContent = `${Number(entry.count || 0)}回`;
      const average = document.createElement("td");
      average.textContent = yenNumber(entry.averageDamage);

      tr.append(source, damage, count, average);
      tbody.appendChild(tr);
    });
  table.appendChild(tbody);
  container.appendChild(table);
}

function renderBurstTimeline(events) {
  const container = document.getElementById("burstTimeline");
  container.innerHTML = "";

  if (!events.length) {
    const empty = document.createElement("div");
    empty.className = "detail-empty";
    empty.textContent = "バースト発動はありません";
    container.appendChild(empty);
    return;
  }

  const track = document.createElement("div");
  track.className = "burst-track";
  events.forEach((event) => {
    const marker = document.createElement("div");
    marker.className = "burst-marker";
    marker.style.left = `${Math.min(100, Math.max(0, (event.time / DETAIL_SECONDS) * 100))}%`;
    marker.title = `${smallNumber(event.time)}s / B${event.stage}`;
    const label = document.createElement("span");
    label.textContent = `${smallNumber(event.time)}s`;
    marker.appendChild(label);
    track.appendChild(marker);
  });
  container.appendChild(track);
}

function renderBuffTimeline(intervals) {
  const container = document.getElementById("buffTimeline");
  container.innerHTML = "";

  if (!intervals.length) {
    const empty = document.createElement("div");
    empty.className = "detail-empty";
    empty.textContent = "表示できるバフはありません";
    container.appendChild(empty);
    return;
  }

  const groups = new Map();
  intervals.forEach((interval) => {
    const bucket = interval.bucket || "その他バフ";
    const key = [
      bucket,
      interval.name,
      interval.effect,
      interval.value,
      interval.count,
      interval.tag
    ].join("|");
    if (!groups.has(key)) {
      groups.set(key, {
        bucket,
        label: interval.name,
        effect: interval.effect,
        value: interval.value,
        count: interval.count,
        tag: interval.tag,
        intervals: []
      });
    }
    groups.get(key).intervals.push(interval);
  });

  const bucketOrder = [
    "攻撃力",
    "武器倍率",
    "クリティカル/コア",
    "チャージ",
    "ダメージバフ",
    "被ダメージ",
    "分配/有利コード/特殊",
    "行動/弾管理",
    "耐久/回復",
    "状態/フラグ",
    "その他バフ"
  ];
  const bucketRank = (bucket) => {
    const index = bucketOrder.indexOf(bucket);
    return index === -1 ? bucketOrder.length : index;
  };

  const groupedByBucket = new Map();
  Array.from(groups.values()).forEach((group) => {
    if (!groupedByBucket.has(group.bucket)) groupedByBucket.set(group.bucket, []);
    groupedByBucket.get(group.bucket).push(group);
  });

  Array.from(groupedByBucket.entries())
    .sort(([a], [b]) => bucketRank(a) - bucketRank(b) || a.localeCompare(b, "ja"))
    .forEach(([bucket, bucketGroups]) => {
      const heading = document.createElement("div");
      heading.className = "buff-bucket-head";
      heading.textContent = bucket;
      container.appendChild(heading);

      bucketGroups
        .sort((a, b) => {
      const aStart = Math.min(...a.intervals.map((item) => item.start));
      const bStart = Math.min(...b.intervals.map((item) => item.start));
      return aStart - bStart || a.label.localeCompare(b.label, "ja");
    })
        .forEach((group) => {
      const row = document.createElement("div");
      row.className = "buff-row";

      const label = document.createElement("div");
      label.className = "buff-label";
      const strong = document.createElement("strong");
      const countText = group.count > 1 ? ` x${group.count}` : "";
      strong.textContent = `${group.effect}: ${formatBuffValue(group.value, group.effect)}${countText}`;
      const span = document.createElement("span");
      span.textContent = group.label;
      label.append(strong, span);

      const track = document.createElement("div");
      track.className = "buff-track";
      group.intervals.forEach((interval) => {
        const start = Math.max(0, Math.min(DETAIL_SECONDS, interval.start));
        const end = Math.max(start, Math.min(DETAIL_SECONDS, interval.end));
        const bar = document.createElement("div");
        bar.className = "buff-bar";
        bar.style.left = `${(start / DETAIL_SECONDS) * 100}%`;
        bar.style.width = `${Math.max(0.35, ((end - start) / DETAIL_SECONDS) * 100)}%`;
        bar.title = `${smallNumber(start)}s - ${smallNumber(end)}s`;
        if (end - start >= 8) {
          bar.textContent = `${smallNumber(start)}-${smallNumber(end)}s`;
        }
        track.appendChild(bar);
      });

      row.append(label, track);
      container.appendChild(row);
    });
    });
}

async function loadCatalog() {
  const response = await fetch("/api/characters");
  const data = await response.json();
  state.catalog = [...data.dummies, ...data.characters];
  state.formations = [createFormation("編成1")];
  applyDefaultSlots(state.formations[0]);
  document.getElementById("catalogStatus").textContent = `${data.characters.length} JSON / ${data.dummies.length} ダミー`;
  populateCatalogFilters();
  renderFormationTabs();
  renderFormation();
  renderAdditionalBuffs();
  renderCatalog();
}

function bindEvents() {
  document.getElementById("searchInput").addEventListener("input", renderCatalog);
  document.querySelectorAll(".catalog-filter").forEach((select) => {
    select.addEventListener("change", (event) => {
      const key = event.target.dataset.filterKey;
      state.catalogFilters[key] = event.target.value;
      renderCatalog();
    });
  });
  document.getElementById("runButton").addEventListener("click", () => runSimulation(false));
  document.getElementById("runAllButton").addEventListener("click", () => runSimulation(true));
  document.getElementById("addFormationButton").addEventListener("click", addFormation);
  document.getElementById("copyFormationButton").addEventListener("click", copyActiveFormation);
  document.getElementById("clearFormationButton").addEventListener("click", resetActiveFormation);
  document.getElementById("addBuffButton").addEventListener("click", addAdditionalBuff);
  document.getElementById("closeDetailButton").addEventListener("click", closeDetail);
  document.querySelector("[data-close-detail]").addEventListener("click", closeDetail);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDetail();
  });
  document.querySelectorAll(".filter-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".filter-button").forEach((b) => b.classList.remove("active"));
      button.classList.add("active");
      state.filter = button.dataset.filter;
      renderCatalog();
    });
  });
}

bindEvents();
loadCatalog().catch((error) => {
  document.getElementById("catalogStatus").textContent = "読み込みエラー";
  document.getElementById("characterList").innerHTML = `<div class="message">${error.message}</div>`;
});
