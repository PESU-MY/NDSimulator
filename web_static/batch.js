const state = {
  catalog: [],
  catalogByKey: new Map(),
  matchMap: new Map(),
  formations: [],
  nextFormationId: 1,
  additionalBuffs: [
    { type: "cooldown_reduction", enabled: true, value: 5 },
    { type: "max_ammo_rate", enabled: true, value: 100 }
  ]
};

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

function itemKey(item) {
  return item.kind === "dummy" ? `dummy:${item.id}` : `character:${item.file}`;
}

function selectionKey(selection) {
  if (!selection) return "";
  return selection.kind === "dummy" ? `dummy:${selection.id}` : `character:${selection.file}`;
}

function cloneSelection(selection) {
  if (!selection) return null;
  const cloned = { kind: selection.kind, file: selection.file, id: selection.id };
  if (selection.kind === "character" && selection.statusSettings) {
    cloned.statusSettings = StatusCalc.normalizeIndividualStatusSettings(selection.statusSettings);
  }
  return cloned;
}

function selectionFromItem(item) {
  return item ? { kind: item.kind, file: item.file, id: item.id } : null;
}

function findCatalogItem(selection) {
  return state.catalogByKey.get(selectionKey(selection)) || null;
}

function normalizeLookup(value) {
  return String(value || "")
    .normalize("NFKC")
    .replace(/\.json$/i, "")
    .replace(/[\s_]/g, "")
    .trim()
    .toLowerCase();
}

function addMatchKey(key, item) {
  const normalized = normalizeLookup(key);
  if (!normalized || state.matchMap.has(normalized)) return;
  state.matchMap.set(normalized, item);
}

function buildCatalogIndexes() {
  state.catalogByKey = new Map();
  state.matchMap = new Map();

  state.catalog.forEach((item) => {
    state.catalogByKey.set(itemKey(item), item);
    addMatchKey(item.name, item);
    addMatchKey(item.file, item);

    if (item.file) {
      addMatchKey(item.file.replace(/\.json$/i, ""), item);
    }
    if (item.kind === "dummy") {
      addMatchKey(item.id, item);
      addMatchKey(item.id.replace(/^dummy_/i, "Dummy "), item);
      addMatchKey(item.name.replace(/\s+/g, ""), item);
    }
  });
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

function inputValue(id, fallback = "") {
  const element = document.getElementById(id);
  return element ? element.value : fallback;
}

function inputChecked(id) {
  const element = document.getElementById(id);
  return element ? element.checked : false;
}

function collectStatusSettings() {
  const individualDefaults = StatusCalc.defaultIndividualStatusSettings();
  const equipmentDefaults = individualDefaults.equipment;
  return {
    enabled: true,
    level: inputValue("statusLevel", 400),
    limitBreak: inputValue("statusLimitBreak", individualDefaults.limitBreak),
    bondLevel: inputValue("statusBondLevel", individualDefaults.bondLevel),
    commonResearchLevel: inputValue("commonResearchLevel", 0),
    classResearchLevels: {
      Attacker: inputValue("classResearchAttacker", 0),
      Defender: inputValue("classResearchDefender", 0),
      Supporter: inputValue("classResearchSupporter", 0)
    },
    companyResearchLevels: {
      Elysion: inputValue("companyResearchElysion", 0),
      Missilis: inputValue("companyResearchMissilis", 0),
      Tetra: inputValue("companyResearchTetra", 0),
      Pilgrim: inputValue("companyResearchPilgrim", 0),
      Abnormal: inputValue("companyResearchAbnormal", 0)
    },
    collectionRarity: inputValue("collectionRarity", individualDefaults.collectionRarity),
    collectionLevel: inputValue("collectionLevel", individualDefaults.collectionLevel),
    cubeLevel: inputValue("cubeLevel", individualDefaults.cubeLevel),
    equipment: {
      head: { tier: inputValue("gearHeadTier", equipmentDefaults.head.tier), level: inputValue("gearHeadLevel", equipmentDefaults.head.level) },
      body: { tier: inputValue("gearBodyTier", equipmentDefaults.body.tier), level: inputValue("gearBodyLevel", equipmentDefaults.body.level) },
      arms: { tier: inputValue("gearArmsTier", equipmentDefaults.arms.tier), level: inputValue("gearArmsLevel", equipmentDefaults.arms.level) },
      legs: { tier: inputValue("gearLegsTier", equipmentDefaults.legs.tier), level: inputValue("gearLegsLevel", equipmentDefaults.legs.level) }
    }
  };
}

function stageMatchesItem(item, requestedStage) {
  const itemStage = String(item?.burstStage || "");
  const requested = String(requestedStage);
  if (itemStage === requested) return true;
  return itemStage === "∀" || itemStage === "ALL" || itemStage === "*" || itemStage === "all";
}

function isRapiRedHoodItem(item) {
  return item?.name === "ラピ：レッドフード" || item?.file === "ラピ：レッドフード.json";
}

function hasOtherBaseBurstStage(slots, currentSlotIndex, requestedStage) {
  return slots.some((selection, slotIndex) => {
    if (!selection || slotIndex === currentSlotIndex) return false;
    const item = findCatalogItem(selection);
    return String(item?.burstStage || "") === String(requestedStage);
  });
}

function effectiveBurstStageForSelection(selection, slotIndex, slots) {
  const item = findCatalogItem(selection);
  if (!item) return "";
  if (isRapiRedHoodItem(item)) {
    return hasOtherBaseBurstStage(slots, slotIndex, "1") ? "3" : "1";
  }
  return String(item.burstStage || "");
}

function stageMatchesSelection(selection, requestedStage, slotIndex, slots) {
  const item = findCatalogItem(selection);
  if (!item) return false;
  const effectiveStage = effectiveBurstStageForSelection(selection, slotIndex, slots);
  const requested = String(requestedStage);
  if (effectiveStage === requested) return true;
  return effectiveStage === "∀" || effectiveStage === "ALL" || effectiveStage === "*" || effectiveStage === "all";
}

function basicRotationForSlots(slots) {
  const rotation = { 1: [], 2: [], 3: [] };
  const firstForStage = (stage) => {
    return slots.findIndex((selection, slotIndex) => stageMatchesSelection(selection, stage, slotIndex, slots));
  };

  const b1 = firstForStage("1");
  const b2 = firstForStage("2");
  if (b1 >= 0) rotation[1].push(b1);
  if (b2 >= 0) rotation[2].push(b2);

  slots.forEach((selection, slotIndex) => {
    if (rotation[3].length < 2 && stageMatchesSelection(selection, "3", slotIndex, slots)) {
      rotation[3].push(slotIndex);
    }
  });
  return rotation;
}

function splitFormationLine(line) {
  const values = [];
  let current = "";
  let inQuote = false;

  for (const char of line) {
    if (char === "\"") {
      inQuote = !inQuote;
      continue;
    }
    if (!inQuote && (char === "," || char === "、" || char === "，")) {
      values.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  values.push(current);
  return values.map((value) => value.trim()).filter(Boolean);
}

function cleanFormationBody(line) {
  let body = line.trim();
  const assignIndex = body.indexOf("=");
  let name = "";

  if (assignIndex > 0) {
    name = body.slice(0, assignIndex).trim();
    body = body.slice(assignIndex + 1).trim();
  } else if (body.includes("\t")) {
    const parts = body.split(/\t+/);
    if (parts.length > 1 && !parts[0].includes(",")) {
      name = parts.shift().trim();
      body = parts.join(",").trim();
    }
  }

  if (
    (body.startsWith("(") && body.endsWith(")")) ||
    (body.startsWith("（") && body.endsWith("）")) ||
    (body.startsWith("[") && body.endsWith("]"))
  ) {
    body = body.slice(1, -1).trim();
  }

  return { name, body };
}

function parseFormationText() {
  const text = inputValue("formationText", "");
  const messages = [];
  const formations = [];

  text.split(/\r?\n/).forEach((rawLine, lineIndex) => {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) return;

    const parsed = cleanFormationBody(line);
    const tokens = splitFormationLine(parsed.body);
    const name = parsed.name || `編成${formations.length + 1}`;
    const slots = [null, null, null, null, null];
    const unresolved = [];
    let lineError = "";

    if (tokens.length !== 5) {
      lineError = `5枠ではありません (${tokens.length}件)`;
      messages.push(`${lineIndex + 1}行目: ${lineError}`);
    }

    tokens.slice(0, 5).forEach((token, slotIndex) => {
      const item = state.matchMap.get(normalizeLookup(token));
      if (item) {
        slots[slotIndex] = selectionFromItem(item);
      } else {
        unresolved.push(token);
      }
    });

    if (unresolved.length) {
      messages.push(`${lineIndex + 1}行目: 未一致 ${unresolved.join(" / ")}`);
      lineError = "未一致の入力があります";
    }

    formations.push({
      id: state.nextFormationId,
      index: formations.length,
      name,
      slots,
      result: null,
      error: lineError,
      dirty: false
    });
    state.nextFormationId += 1;
  });

  state.formations = formations;
  renderParseMessages(messages);
  renderResults();
}

function renderParseMessages(messages) {
  const container = document.getElementById("parseMessages");
  container.innerHTML = "";

  if (!messages.length) {
    const ok = document.createElement("div");
    ok.className = "parse-ok";
    ok.textContent = state.formations.length ? `${state.formations.length}編成を読み込みました` : "入力がありません";
    container.appendChild(ok);
    return;
  }

  messages.forEach((message) => {
    const div = document.createElement("div");
    div.className = "parse-error";
    div.textContent = message;
    container.appendChild(div);
  });
}

function populateCatalogSelect(select, selectedKey = "") {
  select.innerHTML = "";

  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "未設定";
  select.appendChild(empty);

  const dummies = document.createElement("optgroup");
  dummies.label = "ダミー";
  const characters = document.createElement("optgroup");
  characters.label = "キャラ";

  state.catalog.forEach((item) => {
    const option = document.createElement("option");
    option.value = itemKey(item);
    option.textContent = item.name;
    option.selected = option.value === selectedKey;
    if (item.kind === "dummy") dummies.appendChild(option);
    else characters.appendChild(option);
  });

  select.append(dummies, characters);
}

function populateBulkCharacterSelect() {
  populateCatalogSelect(document.getElementById("bulkCharacter"));
}

function renderAdditionalBuffs() {
  const list = document.getElementById("additionalBuffList");
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
    enabled.addEventListener("change", () => {
      state.additionalBuffs[index].enabled = enabled.checked;
    });

    const typeSelect = document.createElement("select");
    additionalBuffTypes.forEach((type) => {
      const option = document.createElement("option");
      option.value = type.type;
      option.textContent = type.label;
      option.selected = type.type === buff.type;
      typeSelect.appendChild(option);
    });
    typeSelect.addEventListener("change", () => {
      const next = additionalBuffDefinition(typeSelect.value);
      state.additionalBuffs[index].type = next.type;
      state.additionalBuffs[index].value = next.defaultValue;
      renderAdditionalBuffs();
    });

    const value = document.createElement("input");
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
  const definition = additionalBuffDefinition(inputValue("additionalBuffType", additionalBuffTypes[0].type));
  state.additionalBuffs.push({
    type: definition.type,
    enabled: true,
    value: definition.defaultValue
  });
  renderAdditionalBuffs();
}

function collectOptions() {
  return {
    skillLevel: inputValue("skillLevel", 10),
    enemyElement: inputValue("enemyElement", "None"),
    enemyCoreSize: inputValue("enemyCoreSize", 3.0),
    enemySize: inputValue("enemySize", 1),
    enemyCount: inputValue("enemyCount", 1),
    burstChargeTime: inputValue("burstChargeTime", 5.0),
    crustOperationMode: inputValue("crustOperationMode", "None"),
    partBreakMode: inputChecked("partBreakMode"),
    specialMode: inputChecked("specialMode"),
    summaryOnly: true,
    statusSettings: collectStatusSettings(),
    additionalBuffs: state.additionalBuffs.map(cloneAdditionalBuff)
  };
}

function selectionWithComputedStats(selection, commonStatusSettings) {
  const cloned = cloneSelection(selection);
  if (!cloned || cloned.kind !== "character") return cloned;

  const item = findCatalogItem(cloned);
  const computedStats = StatusCalc.calculate(item, commonStatusSettings, cloned.statusSettings);
  cloned.statusSettings = {
    ...(cloned.statusSettings ? StatusCalc.normalizeIndividualStatusSettings(cloned.statusSettings) : {}),
    computedStats
  };
  return cloned;
}

function collectPayload(formation) {
  const rotation = basicRotationForSlots(formation.slots);
  const statusSettings = collectStatusSettings();

  return {
    formation: formation.slots.map((selection) => selectionWithComputedStats(selection, statusSettings)),
    rotation,
    options: {
      ...collectOptions(),
      statusSettings
    }
  };
}

async function postSimulation(formation) {
  const response = await fetch("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectPayload(formation))
  });
  const data = await response.json();
  if (!response.ok || data.status !== "ok") {
    throw new Error(data.error || "シミュレーションに失敗しました");
  }
  return data;
}

function collectBatchEntry(formation) {
  const payload = collectPayload(formation);
  return {
    id: formation.id,
    index: formation.index,
    name: formation.name,
    formation: payload.formation,
    rotation: payload.rotation
  };
}

async function postBatchSimulation(formations) {
  const response = await fetch("/api/simulate-batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      entries: formations.map(collectBatchEntry),
      options: collectOptions()
    })
  });
  const data = await response.json();
  if (!response.ok || data.status !== "ok") {
    throw new Error(data.error || "一括シミュレーションに失敗しました");
  }
  return data;
}

function resultRankFormations() {
  return state.formations.slice().sort((a, b) => {
    const aOk = a.result && !a.error;
    const bOk = b.result && !b.error;
    if (aOk && bOk) return b.result.totalPartyDamage - a.result.totalPartyDamage;
    if (aOk) return -1;
    if (bOk) return 1;
    if (a.error && !b.error) return 1;
    if (!a.error && b.error) return -1;
    return a.index - b.index;
  });
}

function renderSummary() {
  const okFormations = state.formations.filter((formation) => formation.result && !formation.error);
  const topDamage = okFormations.reduce(
    (maxValue, formation) => Math.max(maxValue, Number(formation.result.totalPartyDamage || 0)),
    0
  );

  document.querySelector("#batchSummary div:nth-child(1) strong").textContent = state.formations.length
    ? yenNumber(state.formations.length)
    : "-";
  document.querySelector("#batchSummary div:nth-child(2) strong").textContent = okFormations.length
    ? yenNumber(okFormations.length)
    : "-";
  document.querySelector("#batchSummary div:nth-child(3) strong").textContent = okFormations.length
    ? yenNumber(topDamage)
    : "-";
}

function renderSlotSelect(formation, slotIndex) {
  const select = document.createElement("select");
  select.className = "batch-slot-select";
  populateCatalogSelect(select, selectionKey(formation.slots[slotIndex]));
  select.addEventListener("change", () => {
    const item = state.catalogByKey.get(select.value) || null;
    formation.slots[slotIndex] = selectionFromItem(item);
    formation.dirty = true;
    formation.error = "";
    renderResults();
  });
  return select;
}

function renderFormationMembers(formation) {
  const list = document.createElement("div");
  list.className = "batch-member-list";

  const damageByName = new Map();
  if (formation.result) {
    formation.result.results.forEach((row) => {
      damageByName.set(row.name, row.totalDamage);
    });
  }

  formation.slots.forEach((selection, slotIndex) => {
    const item = findCatalogItem(selection);
    const member = document.createElement("div");
    member.className = "batch-member";
    const name = document.createElement("span");
    name.textContent = `${slotIndex + 1}. ${item ? item.name : "未設定"}`;
    const damage = document.createElement("strong");
    const value = item ? damageByName.get(item.name) : null;
    damage.textContent = value === undefined || value === null ? "-" : yenNumber(value);
    member.append(name, damage);
    list.appendChild(member);
  });

  return list;
}

function renderResults() {
  renderSummary();
  const rows = document.getElementById("batchRows");
  rows.innerHTML = "";

  if (!state.formations.length) {
    const empty = document.createElement("div");
    empty.className = "message";
    empty.textContent = "編成がありません";
    rows.appendChild(empty);
    return;
  }

  resultRankFormations().forEach((formation, displayIndex) => {
    const card = document.createElement("article");
    card.className = `batch-result-card${formation.dirty ? " dirty" : ""}`;

    const head = document.createElement("header");
    head.className = "batch-result-head";

    const title = document.createElement("div");
    title.className = "batch-result-title";
    const rank = document.createElement("span");
    rank.className = "batch-rank";
    rank.textContent = formation.result && !formation.error ? `#${displayIndex + 1}` : "-";
    const name = document.createElement("strong");
    name.textContent = formation.name;
    title.append(rank, name);

    const stats = document.createElement("div");
    stats.className = "batch-result-stats";
    const total = document.createElement("strong");
    total.textContent = formation.result && !formation.error ? yenNumber(formation.result.totalPartyDamage) : "-";
    const meta = document.createElement("span");
    if (formation.error) {
      meta.textContent = formation.error;
      meta.className = "batch-error-text";
    } else if (formation.dirty) {
      meta.textContent = "変更あり";
    } else if (formation.result) {
      meta.textContent = `${smallNumber(formation.result.elapsedSeconds)}s`;
    } else {
      meta.textContent = "未実行";
    }
    stats.append(total, meta);

    const rerun = document.createElement("button");
    rerun.type = "button";
    rerun.className = "ghost-button";
    rerun.textContent = "再実行";
    rerun.addEventListener("click", () => runOneFormation(formation));

    head.append(title, stats, rerun);

    const slots = document.createElement("div");
    slots.className = "batch-slot-grid";
    formation.slots.forEach((_, slotIndex) => {
      const label = document.createElement("label");
      label.textContent = `${slotIndex + 1}`;
      label.appendChild(renderSlotSelect(formation, slotIndex));
      slots.appendChild(label);
    });

    card.append(head, slots, renderFormationMembers(formation));
    rows.appendChild(card);
  });
}

function setRunStatus(text, isError = false) {
  const status = document.getElementById("runStatus");
  status.textContent = text;
  status.classList.toggle("error", isError);
}

async function runOneFormation(formation) {
  const button = document.getElementById("runAllButton");
  button.disabled = true;
  setRunStatus(`${formation.name} 実行中`);
  try {
    formation.result = await postSimulation(formation);
    formation.error = "";
    formation.dirty = false;
    setRunStatus("完了");
  } catch (error) {
    formation.error = error.message;
    formation.result = null;
    setRunStatus("エラー", true);
  } finally {
    button.disabled = false;
    renderResults();
  }
}

async function runAllFormations() {
  if (!state.formations.length) return;

  const button = document.getElementById("runAllButton");
  button.disabled = true;
  setRunStatus(`${state.formations.length}編成 実行中`);

  try {
    const batchResult = await postBatchSimulation(state.formations);
    const resultMap = new Map(batchResult.results.map((entry) => [entry.id, entry]));
    let errorCount = 0;
    state.formations.forEach((formation) => {
      const entry = resultMap.get(formation.id);
      if (!entry) return;
      if (entry.error) {
        formation.error = entry.error;
        formation.result = null;
        errorCount += 1;
      } else {
        formation.result = entry.data;
        formation.error = "";
        formation.dirty = false;
      }
    });
    setRunStatus(errorCount ? "一部エラー" : "完了", Boolean(errorCount));
    renderResults();
  } catch (error) {
    setRunStatus("エラー", true);
    renderParseMessages([error.message]);
  } finally {
    button.disabled = false;
  }
}

function applyBulkReplace() {
  const slotIndex = Number(inputValue("bulkSlot", -1));
  const item = state.catalogByKey.get(inputValue("bulkCharacter", "")) || null;
  if (!Number.isInteger(slotIndex) || slotIndex < 0 || slotIndex > 4 || !item) return;

  state.formations.forEach((formation) => {
    formation.slots[slotIndex] = selectionFromItem(item);
    formation.dirty = true;
    formation.error = "";
  });
  renderResults();
}

async function loadFormationFile(file) {
  if (!file) return;
  const text = await file.text();
  const textarea = document.getElementById("formationText");
  if (textarea) textarea.value = text;
  parseFormationText();
}

async function loadCatalog() {
  const response = await fetch("/api/characters");
  const data = await response.json();
  StatusCalc.setData(data.statusData);
  state.catalog = [...data.dummies, ...data.characters];
  buildCatalogIndexes();
  populateBulkCharacterSelect();
  renderAdditionalBuffs();
  renderResults();
  document.getElementById("catalogStatus").textContent = `${data.characters.length} JSON / ${data.dummies.length} ダミー`;
}

function bindEvents() {
  document.getElementById("formationFile").addEventListener("change", (event) => {
    loadFormationFile(event.target.files[0]).catch((error) => {
      renderParseMessages([error.message]);
    });
  });
  document.getElementById("parseButton").addEventListener("click", parseFormationText);
  document.getElementById("runAllButton").addEventListener("click", runAllFormations);
  document.getElementById("bulkReplaceButton").addEventListener("click", applyBulkReplace);
  document.getElementById("addBuffButton").addEventListener("click", addAdditionalBuff);
}

bindEvents();
loadCatalog().catch((error) => {
  document.getElementById("catalogStatus").textContent = "読み込みエラー";
  document.getElementById("batchRows").innerHTML = `<div class="message">${error.message}</div>`;
});
