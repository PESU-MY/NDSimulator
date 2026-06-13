const DETAIL_SECONDS = 180;

const state = {
  activeSlot: 0,
  activeFormation: 0,
  libraryHidden: false,
  filter: "all",
  catalogFilters: {
    weaponType: "",
    element: "",
    company: "",
    class: ""
  },
  catalog: [],
  statusData: null,
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
  { type: "cooldown_reduction", label: "CT短縮", defaultValue: 5, unit: "sec" },
  { type: "max_ammo_rate", label: "装弾数バフ", defaultValue: 100, unit: "%" },
  { type: "reload_speed_rate", label: "リロード速度バフ", defaultValue: 100, unit: "%" },
  { type: "elemental_buff", label: "有利コードダメージバフ", defaultValue: 10, unit: "%" }
];

const statusPartKeys = ["head", "body", "arms", "legs"];
const statusPartLabels = {
  head: "頭",
  body: "胴",
  arms: "腕",
  legs: "足"
};
const statusClassAliases = {
  Attacker: "Attacker",
  "火力型": "Attacker",
  Defender: "Defender",
  "防御型": "Defender",
  Supporter: "Supporter",
  "支援型": "Supporter"
};

const filterIconMaps = {
  weaponType: {
    AR: "/icons/武器種/ICON_AR_small.png",
    SMG: "/icons/武器種/ICON_SMG_small.png",
    SG: "/icons/武器種/ICON_SG_small.png",
    SR: "/icons/武器種/ICON_SR_small.png",
    RL: "/icons/武器種/ICON_RL_small.png",
    MG: "/icons/武器種/ICON_MG_small.png"
  },
  element: {
    Fire: "/icons/属性/灼熱.png",
    "灼熱": "/icons/属性/灼熱.png",
    Water: "/icons/属性/水冷.png",
    "水冷": "/icons/属性/水冷.png",
    Electric: "/icons/属性/電撃.png",
    "電撃": "/icons/属性/電撃.png",
    Wind: "/icons/属性/風圧.png",
    "風圧": "/icons/属性/風圧.png",
    Iron: "/icons/属性/鉄甲.png",
    "鉄甲": "/icons/属性/鉄甲.png"
  },
  company: {
    Elysion: "/icons/企業/elysion_small.png",
    "エリシオン": "/icons/企業/elysion_small.png",
    Missilis: "/icons/企業/missilis_small.png",
    "ミシリス": "/icons/企業/missilis_small.png",
    Tetra: "/icons/企業/tetraline_small.png",
    "テトラ": "/icons/企業/tetraline_small.png",
    Pilgrim: "/icons/企業/pilgrim_small.png",
    "ピルグリム": "/icons/企業/pilgrim_small.png",
    Abnormal: "/icons/企業/abnormal_small.png",
    "アブノーマル": "/icons/企業/abnormal_small.png"
  },
  class: {
    Attacker: "/icons/型/Attacker.png",
    "火力型": "/icons/型/Attacker.png",
    Defender: "/icons/型/Defender.png",
    "防御型": "/icons/型/Defender.png",
    Supporter: "/icons/型/Supporter.png",
    "支援型": "/icons/型/Supporter.png"
  }
};

function yenNumber(value) {
  return new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 0 }).format(value || 0);
}

function statNumber(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue) || numericValue <= 0) return "-";
  return yenNumber(numericValue);
}

function smallNumber(value) {
  return new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 2 }).format(value || 0);
}

function stageLabel(stage) {
  if (!stage) return "-";
  if (stage === "∀" || stage === "ALL" || stage === "*" || stage === "all") return "ALL";
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

function iconInitial(item) {
  if (!item?.name) return "-";
  return item.name.replace(/^Dummy\s*/i, "D").slice(0, 2);
}

function createCharacterIcon(item, className = "character-icon") {
  const wrap = document.createElement("div");
  wrap.className = `${className}${item?.imageUrl ? "" : " fallback"}`;

  if (item?.imageUrl) {
    const img = document.createElement("img");
    img.src = item.imageUrl;
    img.alt = item.name;
    img.loading = "lazy";
    img.addEventListener("error", () => {
      wrap.classList.add("fallback");
      wrap.textContent = iconInitial(item);
      img.remove();
    });
    wrap.appendChild(img);
  } else {
    wrap.textContent = iconInitial(item);
  }

  return wrap;
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

function defaultEquipmentSettings() {
  return StatusCalc.defaultEquipmentSettings();
}

function defaultIndividualStatusSettings() {
  return StatusCalc.defaultIndividualStatusSettings();
}

function normalizeIndividualStatusSettings(settings) {
  const defaults = defaultIndividualStatusSettings();
  const source = settings && typeof settings === "object" ? settings : {};
  const equipment = source.equipment && typeof source.equipment === "object" ? source.equipment : {};
  const overload = source.overload && typeof source.overload === "object" ? source.overload : {};
  return {
    ...defaults,
    ...source,
    equipment: {
      head: { ...defaults.equipment.head, ...(equipment.head || {}) },
      body: { ...defaults.equipment.body, ...(equipment.body || {}) },
      arms: { ...defaults.equipment.arms, ...(equipment.arms || {}) },
      legs: { ...defaults.equipment.legs, ...(equipment.legs || {}) }
    },
    overload: {
      head: normalizeOverloadPartSettings(overload.head),
      body: normalizeOverloadPartSettings(overload.body),
      arms: normalizeOverloadPartSettings(overload.arms),
      legs: normalizeOverloadPartSettings(overload.legs)
    }
  };
}

function normalizeOverloadPartSettings(partSettings) {
  const defaults = [
    { type: "", rank: 0 },
    { type: "", rank: 0 },
    { type: "", rank: 0 }
  ];
  const source = Array.isArray(partSettings) ? partSettings : [];
  return defaults.map((entryDefaults, index) => {
    const entry = source[index] && typeof source[index] === "object" ? source[index] : {};
    return {
      ...entryDefaults,
      ...entry,
      type: String(entry.type || entry.option || ""),
      rank: Number.isFinite(Number(entry.rank)) ? Number(entry.rank) : 0
    };
  });
}

function selectionFromItem(item) {
  if (!item) return null;
  const selection = { kind: item.kind, file: item.file, id: item.id };
  if (item.kind === "character") {
    selection.statusSettings = defaultIndividualStatusSettings();
  }
  return selection;
}

function inputValue(id, fallback = "") {
  const element = document.getElementById(id);
  return element ? element.value : fallback;
}

function inputChecked(id) {
  const element = document.getElementById(id);
  return element ? element.checked : false;
}

function setInputValue(id, value) {
  const element = document.getElementById(id);
  if (!element || value === undefined || value === null) return;
  element.value = value;
}

function setInputChecked(id, value) {
  const element = document.getElementById(id);
  if (!element) return;
  element.checked = !!value;
}

function collectStatusSettings() {
  return {
    enabled: true,
    level: inputValue("statusLevel", 400),
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
    }
  };
}

function applyStatusSettings(settings) {
  if (!settings || typeof settings !== "object") return;
  setInputValue("statusLevel", settings.level);
  setInputValue("commonResearchLevel", settings.commonResearchLevel);

  const classLevels = settings.classResearchLevels || {};
  setInputValue("classResearchAttacker", classLevels.Attacker);
  setInputValue("classResearchDefender", classLevels.Defender);
  setInputValue("classResearchSupporter", classLevels.Supporter);

  const companyLevels = settings.companyResearchLevels || {};
  setInputValue("companyResearchElysion", companyLevels.Elysion);
  setInputValue("companyResearchMissilis", companyLevels.Missilis);
  setInputValue("companyResearchTetra", companyLevels.Tetra);
  setInputValue("companyResearchPilgrim", companyLevels.Pilgrim);
  setInputValue("companyResearchAbnormal", companyLevels.Abnormal);
}

function collectSharedSettings() {
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
    statusSettings: collectStatusSettings(),
    additionalBuffs: state.additionalBuffs.map(cloneAdditionalBuff)
  };
}

function applySharedSettings(settings) {
  if (!settings || typeof settings !== "object") return;
  setInputValue("skillLevel", settings.skillLevel);
  setInputValue("enemyElement", settings.enemyElement);
  setInputValue("enemyCoreSize", settings.enemyCoreSize);
  setInputValue("enemySize", settings.enemySize);
  setInputValue("enemyCount", settings.enemyCount);
  setInputValue("burstChargeTime", settings.burstChargeTime);
  setInputValue("crustOperationMode", settings.crustOperationMode);
  setInputChecked("partBreakMode", settings.partBreakMode);
  setInputChecked("specialMode", settings.specialMode);
  applyStatusSettings(settings.statusSettings);
  if (Array.isArray(settings.additionalBuffs)) {
    state.additionalBuffs = settings.additionalBuffs.map(cloneAdditionalBuff);
    renderAdditionalBuffs();
  }
}

function calculateSlotStats(selection) {
  if (!selection || selection.kind !== "character") return null;
  return StatusCalc.calculate(
    findCatalogItem(selection),
    collectStatusSettings(),
    selection.statusSettings
  );
}

function selectionWithComputedStats(selection, commonStatusSettings) {
  const cloned = cloneSelection(selection);
  if (!cloned || cloned.kind !== "character") return cloned;

  const item = findCatalogItem(cloned);
  const computedStats = StatusCalc.calculate(item, commonStatusSettings, cloned.statusSettings);
  cloned.statusSettings = {
    ...normalizeIndividualStatusSettings(cloned.statusSettings),
    computedStats
  };
  return cloned;
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

function emptyRotation() {
  return { 1: [], 2: [], 3: [] };
}

function normalizeRotation(rotation) {
  const normalized = emptyRotation();
  if (!rotation) return normalized;

  if (Array.isArray(rotation)) {
    rotation.forEach((stageSet, slotIndex) => {
      if (!stageSet) return;
      const stages = stageSet instanceof Set ? Array.from(stageSet) : Array.from(stageSet || []);
      stages.forEach((stage) => {
        const key = String(stage);
        if (normalized[key]) normalized[key].push(slotIndex);
      });
    });
    return normalized;
  }

  ["1", "2", "3"].forEach((stage) => {
    const values = Array.isArray(rotation[stage]) ? rotation[stage] : [];
    normalized[stage] = values.map((value) => Number(value)).filter((value) => Number.isInteger(value));
  });
  return normalized;
}

function basicRotationForFormation(formation) {
  const rotation = emptyRotation();
  const firstForStage = (stage) => {
    return formation.slots.findIndex((selection, slotIndex) => {
      return stageMatchesSelection(selection, stage, slotIndex, formation.slots);
    });
  };

  const b1 = firstForStage("1");
  const b2 = firstForStage("2");
  if (b1 >= 0) rotation[1].push(b1);
  if (b2 >= 0) rotation[2].push(b2);

  formation.slots.forEach((selection, index) => {
    if (rotation[3].length < 2 && stageMatchesSelection(selection, "3", index, formation.slots)) {
      rotation[3].push(index);
    }
  });
  return rotation;
}

function setBasicRotation(formation) {
  formation.rotation = basicRotationForFormation(formation);
  formation.rotationDetailed = false;
}

function cleanDetailedRotation(formation) {
  const current = normalizeRotation(formation.rotation);
  ["1", "2", "3"].forEach((stage) => {
    current[stage] = current[stage].filter((slotIndex) => {
      return stageMatchesSelection(formation.slots[slotIndex], stage, slotIndex, formation.slots);
    });
  });
  formation.rotation = current;
}

function rotationSequenceLabel(formation, stage) {
  const sequence = normalizeRotation(formation.rotation)[stage] || [];
  if (!sequence.length) return "-";
  return sequence.map((slotIndex) => {
    const item = findCatalogItem(formation.slots[slotIndex]);
    return item ? `${slotIndex + 1}.${item.name}` : `${slotIndex + 1}.Empty`;
  }).join(" -> ");
}

function createFormation(name) {
  return {
    name,
    slots: [null, null, null, null, null],
    rotation: emptyRotation(),
    rotationDetailed: false,
    statusOpenSlot: null,
    statusPanelMode: "equipment",
    result: null
  };
}

function cloneSelection(selection) {
  if (!selection) return null;
  const cloned = { kind: selection.kind, file: selection.file, id: selection.id };
  if (selection.kind === "character") {
    cloned.statusSettings = normalizeIndividualStatusSettings(selection.statusSettings);
  }
  return cloned;
}

function cloneFormation(source, name) {
  return {
    name,
    slots: source.slots.map(cloneSelection),
    rotation: normalizeRotation(source.rotation),
    rotationDetailed: !!source.rotationDetailed,
    statusOpenSlot: source.statusOpenSlot,
    statusPanelMode: source.statusPanelMode || "equipment",
    result: null
  };
}

function cleanStatusSettingsForExport(settings) {
  const normalized = normalizeIndividualStatusSettings(settings);
  delete normalized.computedStats;
  return normalized;
}

function serializeSelection(selection) {
  if (!selection) return null;
  const item = findCatalogItem(selection);
  const serialized = selection.kind === "dummy"
    ? { kind: "dummy", id: selection.id, name: item?.name || selection.id }
    : { kind: "character", file: selection.file, name: item?.name || selection.file };
  if (selection.kind === "character") {
    serialized.statusSettings = cleanStatusSettingsForExport(selection.statusSettings);
  }
  return serialized;
}

function serializeFormation(formation) {
  return {
    name: formation.name,
    slots: formation.slots.map(serializeSelection),
    rotation: normalizeRotation(formation.rotation),
    rotationDetailed: !!formation.rotationDetailed,
    statusPanelMode: formation.statusPanelMode || "equipment"
  };
}

function findCatalogItemForImport(selection) {
  if (!selection || typeof selection !== "object") return null;
  const kind = selection.kind || (selection.file ? "character" : selection.id ? "dummy" : "");
  if (kind === "dummy") {
    return state.catalog.find((item) => item.kind === "dummy" && item.id === selection.id) || null;
  }
  if (kind === "character") {
    return state.catalog.find((item) => item.kind === "character" && item.file === selection.file) ||
      state.catalog.find((item) => item.kind === "character" && item.name === selection.name) ||
      null;
  }
  return null;
}

function importSelection(selection) {
  const item = findCatalogItemForImport(selection);
  if (!item) return null;
  const imported = selectionFromItem(item);
  if (item.kind === "character") {
    imported.statusSettings = cleanStatusSettingsForExport(selection.statusSettings);
  }
  return imported;
}

function importFormation(rawFormation, index) {
  const formation = createFormation(String(rawFormation?.name || `Formation ${index + 1}`));
  const rawSlots = Array.isArray(rawFormation?.slots) ? rawFormation.slots : [];
  formation.slots = Array.from({ length: 5 }, (_, slotIndex) => importSelection(rawSlots[slotIndex]));
  formation.rotation = normalizeRotation(rawFormation?.rotation);
  formation.rotationDetailed = !!rawFormation?.rotationDetailed;
  formation.statusPanelMode = rawFormation?.statusPanelMode === "overload" ? "overload" : "equipment";
  formation.statusOpenSlot = null;
  formation.result = null;

  if (formation.rotationDetailed) {
    cleanDetailedRotation(formation);
  } else {
    setBasicRotation(formation);
  }
  return formation;
}

function collectExportData() {
  return {
    schema: "nikke-simulator-formations-v1",
    exportedAt: new Date().toISOString(),
    activeFormation: state.activeFormation,
    settings: collectSharedSettings(),
    formations: state.formations.map(serializeFormation)
  };
}

function filenameTimestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
}

function exportFormations() {
  const data = collectExportData();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `nikke_formations_${filenameTimestamp()}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  setRunStatus("Exported");
}

function importedFormationList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.formations)) return data.formations;
  if (data?.formation) return [data.formation];
  if (Array.isArray(data?.slots)) return [data];
  return [];
}

function applyImportedData(data) {
  const imported = importedFormationList(data);
  if (!imported.length) {
    throw new Error("編成データが見つかりません");
  }

  const formations = imported.map(importFormation);
  state.formations = formations.length ? formations : [createFormation("編成1")];
  if (!formations.length) applyDefaultSlots(state.formations[0]);
  state.activeFormation = Math.max(0, Math.min(Number(data?.activeFormation) || 0, state.formations.length - 1));
  state.activeSlot = 0;
  state.results = [];
  applySharedSettings(data?.settings || data?.options);
  renderFormationTabs();
  renderFormation();
  renderResults([]);
  setRunStatus(`Imported ${state.formations.length}`);
}

async function importFormationsFromFile(file) {
  if (!file) return;
  const text = await file.text();
  const data = JSON.parse(text);
  applyImportedData(data);
}

function activeFormationState() {
  return state.formations[state.activeFormation];
}

function applyDefaultSlots(formation) {
  defaults.forEach((selection, index) => {
    const item = selection ? findCatalogItem(selection) : null;
    formation.slots[index] = selectionFromItem(item);
  });
  setBasicRotation(formation);
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
  const formation = createFormation(`Formation ${state.formations.length + 1}`);
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
  const formation = cloneFormation(source, `${source.name} Copy`);
  state.formations.push(formation);
  state.activeFormation = state.formations.length - 1;
  state.activeSlot = 0;
  renderFormationTabs();
  renderFormation();
}

function deleteActiveFormation() {
  if (!state.formations.length) return;
  state.formations.splice(state.activeFormation, 1);
  if (!state.formations.length) {
    const formation = createFormation("編成1");
    applyDefaultSlots(formation);
    state.formations.push(formation);
  }
  state.activeFormation = Math.max(0, Math.min(state.activeFormation, state.formations.length - 1));
  state.activeSlot = 0;
  state.results = [];
  renderFormationTabs();
  renderFormation();
  renderResults([]);
}

function toggleLibraryPane() {
  state.libraryHidden = !state.libraryHidden;
  document.body.classList.toggle("library-collapsed", state.libraryHidden);
  const label = state.libraryHidden ? "一覧を表示" : "一覧を隠す";
  document.getElementById("toggleLibraryButton").textContent = label;
  document.getElementById("toggleLibraryWideButton").textContent = label;
}

function openStatusPanelMode(mode) {
  const formation = activeFormationState();
  if (!formation) return;
  formation.statusPanelMode = mode;
  formation.statusOpenSlot = null;
  renderFormation();
}

function updateStatusPanelButtons() {
  const mode = activeFormationState()?.statusPanelMode || "";
  const equipmentButton = document.getElementById("openEquipmentStatusButton");
  const overloadButton = document.getElementById("openOverloadStatusButton");
  if (equipmentButton) equipmentButton.classList.toggle("active", mode === "equipment");
  if (overloadButton) overloadButton.classList.toggle("active", mode === "overload");
}

function setFormation(slotIndex, item) {
  const formation = activeFormationState();
  formation.slots[slotIndex] = selectionFromItem(item);
  if (formation.rotationDetailed) cleanDetailedRotation(formation);
  else setBasicRotation(formation);
  formation.result = null;
  formation.statusOpenSlot = null;
  formation.statusPanelMode = formation.statusPanelMode || "equipment";
  state.activeSlot = Math.min(4, slotIndex + 1);
  renderFormationTabs();
  renderFormation();
}

function filterIconUrl(key, value) {
  return filterIconMaps[key]?.[String(value || "")] || "";
}

function createCatalogFilterButton(container, key, value, labelText, iconUrl = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `catalog-filter-icon${String(state.catalogFilters[key] || "") === String(value) ? " active" : ""}`;
  button.title = labelText;
  button.dataset.value = String(value);
  if (iconUrl) {
    const img = document.createElement("img");
    img.src = iconUrl;
    img.alt = labelText;
    button.appendChild(img);
  } else {
    button.textContent = labelText;
  }
  button.addEventListener("click", () => {
    state.catalogFilters[key] = String(state.catalogFilters[key] || "") === String(value) ? "" : String(value);
    populateCatalogFilters();
    renderCatalog();
  });
  container.appendChild(button);
}

function populateCatalogFilters() {
  document.querySelectorAll(".catalog-filter").forEach((container) => {
    const key = container.dataset.filterKey;
    const label = container.dataset.filterLabel || key;
    container.innerHTML = "";

    const title = document.createElement("span");
    title.className = "catalog-filter-label";
    title.textContent = label;
    container.appendChild(title);

    createCatalogFilterButton(container, key, "", "すべて");

    const values = Array.from(
      new Set(
        state.catalog
          .map((item) => item[key])
          .filter((value) => value !== undefined && value !== null && String(value).trim() !== "")
      )
    ).sort((a, b) => String(a).localeCompare(String(b), "ja", { numeric: true, sensitivity: "base" }));

    values.forEach((value) => {
      createCatalogFilterButton(container, key, value, String(value), filterIconUrl(key, value));
    });
  });
}

function filteredCatalog() {
  const query = normalizeText(inputValue("searchInput", ""));
  return state.catalog.filter((item) => {
    const haystack = normalizeText([
      item.name,
      item.file,
      item.weaponType,
      item.element,
      item.company,
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
    button.title = `${item.name} / ${item.weaponType || "-"} / ${item.element || "-"}`;

    const icon = createCharacterIcon(item);
    const name = document.createElement("div");
    name.className = "character-name";
    name.textContent = item.name;

    const badge = document.createElement("span");
    badge.className = "stage-badge";
    badge.textContent = stageLabel(String(item.burstStage || ""));

    button.append(icon, name, badge);
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
  updateFormationNameInput();
}

function updateFormationNameInput() {
  const input = document.getElementById("formationNameInput");
  if (!input) return;
  input.value = activeFormationState()?.name || "";
}

function renameActiveFormation(value) {
  const formation = activeFormationState();
  if (!formation) return;
  formation.name = String(value || "").trim() || `編成${state.activeFormation + 1}`;
  formation.result = null;
  renderFormationTabs();
}

function markFormationDirty(formation) {
  formation.result = null;
  renderFormationTabs();
}

function refreshSlotMeta(formation, slotIndex) {
  const slot = document.querySelector(`.slot[data-slot-index="${slotIndex}"]`);
  const meta = slot?.querySelector(".slot-meta");
  if (!meta) return;

  const selection = formation.slots[slotIndex];
  const item = findCatalogItem(selection);
  const calculatedStats = item?.kind === "character" ? calculateSlotStats(selection) : null;
  meta.textContent = item
    ? calculatedStats
      ? `ATK ${statNumber(calculatedStats.baseAtk)} / HP ${statNumber(calculatedStats.baseHp)}`
      : `${stageLabel(String(item.burstStage || ""))} / ${item.weaponType || "-"} / ${item.class || "-"}`
    : "Select";
}

function setSlotStatusValue(formation, slotIndex, key, value) {
  const selection = formation.slots[slotIndex];
  if (!selection || selection.kind !== "character") return;
  selection.statusSettings = normalizeIndividualStatusSettings(selection.statusSettings);
  selection.statusSettings[key] = value;
  markFormationDirty(formation);
  refreshSlotMeta(formation, slotIndex);
}

function setSlotEquipmentValue(formation, slotIndex, part, key, value) {
  const selection = formation.slots[slotIndex];
  if (!selection || selection.kind !== "character") return;
  selection.statusSettings = normalizeIndividualStatusSettings(selection.statusSettings);
  selection.statusSettings.equipment[part][key] = value;
  markFormationDirty(formation);
  refreshSlotMeta(formation, slotIndex);
}

function maxStatusPresetSettings(settings) {
  const normalized = normalizeIndividualStatusSettings(settings);
  normalized.collectionRarity = "SR";
  normalized.collectionLevel = 15;
  normalized.cubeLevel = 15;
  statusPartKeys.forEach((part) => {
    normalized.equipment[part] = { tier: "T10", level: 5 };
  });
  return normalized;
}

function applyMaxStatusPresetToActiveFormation() {
  const formation = activeFormationState();
  if (!formation) return;
  let applied = 0;
  formation.slots.forEach((selection) => {
    if (!selection || selection.kind !== "character") return;
    selection.statusSettings = maxStatusPresetSettings(selection.statusSettings);
    applied += 1;
  });
  if (!applied) return;
  formation.statusPanelMode = "equipment";
  formation.result = null;
  setRunStatus("強化プリセット適用");
  renderFormationTabs();
  renderFormation();
}

function overloadOptionNames() {
  return Object.keys(state.statusData?.overload?.options || {});
}

function overloadRanks(optionName) {
  return state.statusData?.overload?.options?.[optionName] || [];
}

function defaultOverloadRank(optionName) {
  const ranks = overloadRanks(optionName);
  return Number((ranks.find((rank) => Number(rank.rank) === 11) || ranks[0] || {}).rank || 0);
}

function classKeyForItem(item) {
  return statusClassAliases[String(item?.class || "")] || "Attacker";
}

function overloadIconUrl(item, part) {
  const classKey = classKeyForItem(item);
  return state.statusData?.overload?.icons?.[classKey]?.[part] || "";
}

function setSlotOverloadValue(formation, slotIndex, part, optionIndex, key, value) {
  const selection = formation.slots[slotIndex];
  if (!selection || selection.kind !== "character") return;
  selection.statusSettings = normalizeIndividualStatusSettings(selection.statusSettings);
  const entry = selection.statusSettings.overload[part][optionIndex];
  entry[key] = key === "rank" ? Number(value) : value;
  if (key === "type") {
    entry.rank = value ? defaultOverloadRank(value) : 0;
  }
  markFormationDirty(formation);
}

function createNumberField(labelText, value, options, onInput) {
  const label = document.createElement("label");
  label.textContent = labelText;
  const input = document.createElement("input");
  input.type = "number";
  input.min = String(options.min ?? 0);
  if (options.max !== undefined) input.max = String(options.max);
  input.step = String(options.step ?? 1);
  input.value = value;
  input.addEventListener("input", () => onInput(input.value));
  label.appendChild(input);
  return label;
}

function createSelectField(labelText, value, values, onChange) {
  const label = document.createElement("label");
  label.textContent = labelText;
  const select = document.createElement("select");
  values.forEach((optionValue) => {
    const option = document.createElement("option");
    option.value = String(optionValue);
    option.textContent = String(optionValue);
    option.selected = String(optionValue) === String(value);
    select.appendChild(option);
  });
  select.addEventListener("change", () => onChange(select.value));
  label.appendChild(select);
  return label;
}

function createCollectionField(settings, formation, slotIndex) {
  const label = document.createElement("label");
  label.textContent = "Collection";
  const select = document.createElement("select");
  [
    ["", "None"],
    ["R", "R"],
    ["SR", "SR"]
  ].forEach(([value, text]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    option.selected = value === String(settings.collectionRarity || "");
    select.appendChild(option);
  });
  select.addEventListener("change", () => setSlotStatusValue(formation, slotIndex, "collectionRarity", select.value));
  label.appendChild(select);
  return label;
}

function cubeDefinitions() {
  return Array.isArray(state.statusData?.cubeSkills) ? state.statusData.cubeSkills : [];
}

function cubeDefinition(name) {
  return cubeDefinitions().find((cube) => cube.name === name) || null;
}

function createCubeField(settings, formation, slotIndex) {
  const wrap = document.createElement("label");
  wrap.className = "cube-field";
  wrap.textContent = "Cube";

  const row = document.createElement("div");
  row.className = "cube-field-row";

  const icon = document.createElement("span");
  icon.className = "cube-icon";
  const selected = cubeDefinition(String(settings.cubeType || ""));
  if (selected?.iconUrl) {
    const img = document.createElement("img");
    img.src = selected.iconUrl;
    img.alt = selected.name;
    icon.appendChild(img);
  } else {
    icon.textContent = "-";
  }

  const select = document.createElement("select");
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "None";
  select.appendChild(none);
  cubeDefinitions().forEach((cube) => {
    const option = document.createElement("option");
    option.value = cube.name;
    option.textContent = cube.name;
    option.selected = cube.name === String(settings.cubeType || "");
    select.appendChild(option);
  });
  select.addEventListener("change", () => {
    setSlotStatusValue(formation, slotIndex, "cubeType", select.value);
    renderFormation();
  });

  row.append(icon, select);
  wrap.appendChild(row);
  return wrap;
}

function createEquipmentField(labelText, part, settings, formation, slotIndex) {
  const label = document.createElement("label");
  label.textContent = labelText;

  const tier = document.createElement("select");
  ["T9", "T10"].forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === String(settings.equipment[part].tier || "T9");
    tier.appendChild(option);
  });
  tier.addEventListener("change", () => setSlotEquipmentValue(formation, slotIndex, part, "tier", tier.value));

  const level = document.createElement("input");
  level.type = "number";
  level.min = "0";
  level.max = "5";
  level.step = "1";
  level.value = settings.equipment[part].level;
  level.addEventListener("input", () => setSlotEquipmentValue(formation, slotIndex, part, "level", level.value));

  label.append(tier, level);
  return label;
}

function createSlotEquipmentStatusPanel(formation, slotIndex, settings) {
  const fragment = document.createDocumentFragment();

  const grid = document.createElement("div");
  grid.className = "slot-status-grid";
  grid.append(
    createNumberField("Limit", settings.limitBreak, { min: 0, max: 10 }, (value) => setSlotStatusValue(formation, slotIndex, "limitBreak", value)),
    createSelectField("Bond", settings.bondLevel, [0, 10, 20, 30, 40], (value) => setSlotStatusValue(formation, slotIndex, "bondLevel", value)),
    createCollectionField(settings, formation, slotIndex),
    createNumberField("Collection Lv", settings.collectionLevel, { min: 0, max: 15 }, (value) => setSlotStatusValue(formation, slotIndex, "collectionLevel", value)),
    createCubeField(settings, formation, slotIndex),
    createNumberField("Cube Lv", settings.cubeLevel, { min: 0, max: 15 }, (value) => setSlotStatusValue(formation, slotIndex, "cubeLevel", value))
  );

  const equipment = document.createElement("div");
  equipment.className = "slot-equipment-grid";
  equipment.append(
    createEquipmentField("Head", "head", settings, formation, slotIndex),
    createEquipmentField("Body", "body", settings, formation, slotIndex),
    createEquipmentField("Arms", "arms", settings, formation, slotIndex),
    createEquipmentField("Legs", "legs", settings, formation, slotIndex)
  );

  fragment.append(grid, equipment);
  return fragment;
}

function createOverloadOptionRow(formation, slotIndex, part, optionIndex, entry) {
  const row = document.createElement("div");
  row.className = "overload-option-row";

  const optionSelect = document.createElement("select");
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "None";
  optionSelect.appendChild(none);
  overloadOptionNames().forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    option.selected = name === String(entry.type || "");
    optionSelect.appendChild(option);
  });
  optionSelect.addEventListener("change", () => {
    setSlotOverloadValue(formation, slotIndex, part, optionIndex, "type", optionSelect.value);
    renderFormation();
  });

  const rankSelect = document.createElement("select");
  const emptyRank = document.createElement("option");
  emptyRank.value = "0";
  emptyRank.textContent = "-";
  rankSelect.appendChild(emptyRank);
  overloadRanks(entry.type).forEach((rank) => {
    const option = document.createElement("option");
    option.value = String(rank.rank);
    option.textContent = `R${rank.rank} ${smallNumber(rank.percent)}%`;
    option.selected = String(rank.rank) === String(entry.rank || 0);
    rankSelect.appendChild(option);
  });
  rankSelect.disabled = !entry.type;
  rankSelect.addEventListener("change", () => {
    setSlotOverloadValue(formation, slotIndex, part, optionIndex, "rank", rankSelect.value);
    renderFormation();
  });

  row.append(optionSelect, rankSelect);
  return row;
}

function createSlotOverloadPanel(formation, slotIndex, item, settings) {
  const grid = document.createElement("div");
  grid.className = "slot-overload-grid";

  statusPartKeys.forEach((part) => {
    const partCard = document.createElement("div");
    partCard.className = "slot-overload-part";

    const head = document.createElement("div");
    head.className = "overload-part-head";
    const icon = document.createElement("div");
    icon.className = "overload-icon";
    const iconUrl = overloadIconUrl(item, part);
    if (iconUrl) {
      const img = document.createElement("img");
      img.src = iconUrl;
      img.alt = `${statusPartLabels[part]} icon`;
      icon.appendChild(img);
    } else {
      icon.textContent = statusPartLabels[part];
    }
    const label = document.createElement("strong");
    label.textContent = statusPartLabels[part];
    head.append(icon, label);
    partCard.appendChild(head);

    const entries = settings.overload[part] || normalizeOverloadPartSettings();
    entries.forEach((entry, optionIndex) => {
      partCard.appendChild(createOverloadOptionRow(formation, slotIndex, part, optionIndex, entry));
    });
    grid.appendChild(partCard);
  });

  return grid;
}

function createSlotStatusPanel(formation, slotIndex, item, mode = "equipment") {
  const selection = formation.slots[slotIndex];
  selection.statusSettings = normalizeIndividualStatusSettings(selection.statusSettings);
  const settings = selection.statusSettings;

  const panel = document.createElement("div");
  panel.className = "slot-status-panel";
  panel.addEventListener("click", (event) => event.stopPropagation());

  const head = document.createElement("div");
  head.className = "slot-status-head";
  const title = document.createElement("strong");
  title.textContent = `${item.name} / ${mode === "overload" ? "オバロOP" : "装備ステータス"}`;
  head.append(title);

  panel.append(head);
  panel.appendChild(
    mode === "overload"
      ? createSlotOverloadPanel(formation, slotIndex, item, settings)
      : createSlotEquipmentStatusPanel(formation, slotIndex, settings)
  );
  return panel;
}

function resultForSlot(formation, item) {
  if (!formation.result || !item) return null;
  return (formation.result.results || []).find((row) => row.name === item.name) || null;
}

function renderFormation() {
  const formation = activeFormationState();
  updateStatusPanelButtons();
  const slots = document.getElementById("formationSlots");
  slots.innerHTML = "";

  const slotRow = document.createElement("div");
  slotRow.className = "formation-slot-row";

  formation.slots.forEach((selection, index) => {
    const item = findCatalogItem(selection);
    const slot = document.createElement("div");
    slot.className = `slot${index === state.activeSlot ? " active" : ""}`;
    slot.dataset.slotIndex = String(index);
    slot.title = item ? item.name : `${index + 1}番目`;

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

    const icon = createCharacterIcon(item, "slot-icon");
    icon.title = item?.kind === "character" ? "Select slot" : "";
    icon.addEventListener("click", (event) => {
      event.stopPropagation();
      state.activeSlot = index;
      renderFormation();
    });
    const body = document.createElement("div");
    body.className = "slot-body";
    const name = document.createElement("div");
    name.className = item ? "slot-name" : "slot-empty";
    name.textContent = item ? item.name : "Empty";
    const meta = document.createElement("div");
    meta.className = "slot-meta";
    const result = resultForSlot(formation, item);
    const calculatedStats = item?.kind === "character" ? calculateSlotStats(selection) : null;
    meta.textContent = item
      ? result
        ? `ATK ${statNumber(result.baseAtk)} / HP ${statNumber(result.baseHp)}`
        : calculatedStats
          ? `ATK ${statNumber(calculatedStats.baseAtk)} / HP ${statNumber(calculatedStats.baseHp)}`
          : `${stageLabel(String(item.burstStage || ""))} / ${item.weaponType || "-"} / ${item.class || "-"}`
      : "Select";
    body.append(name, meta);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "slot-remove";
    remove.textContent = "x";
    remove.title = "Remove";
    remove.disabled = !item;
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      formation.slots[index] = null;
      if (formation.rotationDetailed) cleanDetailedRotation(formation);
      else setBasicRotation(formation);
      formation.result = null;
      renderFormationTabs();
      renderFormation();
    });

    main.append(idx, icon, body, remove);
    slot.append(main);
    const statusMode = formation.statusPanelMode || "equipment";
    const shouldShowStatus = item?.kind === "character";
    if (shouldShowStatus) {
      slot.appendChild(createSlotStatusPanel(formation, index, item, statusMode));
    }
    slotRow.appendChild(slot);
  });

  const rotationPanel = document.createElement("div");
  rotationPanel.className = "formation-rotation-panel";

  const rotationTitle = document.createElement("button");
  rotationTitle.type = "button";
  rotationTitle.className = "rotation-title";
  rotationTitle.setAttribute("aria-expanded", formation.rotationDetailed ? "true" : "false");
  rotationTitle.addEventListener("click", () => {
    if (!formation.rotationDetailed) {
      formation.rotation = normalizeRotation(formation.rotation);
      formation.rotationDetailed = true;
      renderFormation();
    }
  });

  const rotationTitleText = document.createElement("span");
  rotationTitleText.textContent = "Burst order";
  const rotationMode = document.createElement("strong");
  rotationMode.textContent = formation.rotationDetailed ? "Detail" : "Basic";
  rotationTitle.append(rotationTitleText, rotationMode);
  rotationPanel.appendChild(rotationTitle);

  if (!formation.rotationDetailed) {
    const summary = document.createElement("div");
    summary.className = "rotation-basic-summary";
    ["1", "2", "3"].forEach((stage) => {
      const line = document.createElement("div");
      const label = document.createElement("strong");
      label.textContent = `B${stage}`;
      const sequence = document.createElement("span");
      sequence.textContent = rotationSequenceLabel(formation, stage);
      line.append(label, sequence);
      summary.appendChild(line);
    });
    rotationPanel.appendChild(summary);
  } else {
    const tools = document.createElement("div");
    tools.className = "rotation-tools";
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "ghost-button";
    reset.textContent = "Reset basic";
    reset.addEventListener("click", () => {
      setBasicRotation(formation);
      formation.result = null;
      renderFormationTabs();
      renderFormation();
    });
    tools.appendChild(reset);
    rotationPanel.appendChild(tools);

    ["1", "2", "3"].forEach((stage) => {
      const controls = document.createElement("div");
      controls.className = "rotation-controls detailed";

      const head = document.createElement("div");
      head.className = "rotation-stage-head";
      const stageBadge = document.createElement("strong");
      stageBadge.textContent = `B${stage}`;
      const hint = document.createElement("span");
      hint.textContent = "Click to append";
      head.append(stageBadge, hint);

      const sequence = document.createElement("div");
      sequence.className = "rotation-sequence";
      const rotation = normalizeRotation(formation.rotation);
      (rotation[stage] || []).forEach((slotIndex, orderIndex) => {
        const item = findCatalogItem(formation.slots[slotIndex]);
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "rotation-chip";
        chip.title = "Remove this entry";
        const icon = createCharacterIcon(item, "rotation-icon");
        const text = document.createElement("span");
        text.textContent = item ? `${orderIndex + 1}. ${item.name}` : `${orderIndex + 1}. Empty`;
        chip.append(icon, text);
        chip.addEventListener("click", () => {
          formation.rotation = normalizeRotation(formation.rotation);
          formation.rotation[stage].splice(orderIndex, 1);
          formation.result = null;
          renderFormationTabs();
          renderFormation();
        });
        sequence.appendChild(chip);
      });
      if (!(rotation[stage] || []).length) {
        const empty = document.createElement("span");
        empty.className = "rotation-empty";
        empty.textContent = "Empty";
        sequence.appendChild(empty);
      }

      const candidates = document.createElement("div");
      candidates.className = "rotation-candidates";
      formation.slots.forEach((selection, slotIndex) => {
        const item = findCatalogItem(selection);
        if (!stageMatchesSelection(selection, stage, slotIndex, formation.slots)) return;
        const add = document.createElement("button");
        add.type = "button";
        add.className = "rotation-add";
        add.title = `${item.name}をB${stage}に追加`;
        const icon = createCharacterIcon(item, "rotation-icon");
        const text = document.createElement("span");
        text.textContent = `${slotIndex + 1}. ${item.name}`;
        add.append(icon, text);
        add.addEventListener("click", () => {
          formation.rotation = normalizeRotation(formation.rotation);
          formation.rotation[stage].push(slotIndex);
          formation.result = null;
          renderFormationTabs();
          renderFormation();
        });
        candidates.appendChild(add);
      });
      if (!candidates.children.length) {
        const empty = document.createElement("span");
        empty.className = "rotation-empty";
        empty.textContent = `No B${stage} candidates`;
        candidates.appendChild(empty);
      }

      const clear = document.createElement("button");
      clear.type = "button";
      clear.className = "rotation-clear";
      clear.textContent = "Clear";
      clear.addEventListener("click", () => {
        formation.rotation = normalizeRotation(formation.rotation);
        formation.rotation[stage] = [];
        formation.result = null;
        renderFormationTabs();
        renderFormation();
      });

      controls.append(head, sequence, candidates, clear);
      rotationPanel.appendChild(controls);
    });
  }

  slots.append(slotRow, rotationPanel);
}

function renderAdditionalBuffs() {
  const list = document.getElementById("additionalBuffList");
  if (!list) return;
  list.innerHTML = "";

  state.additionalBuffs = state.additionalBuffs.map(cloneAdditionalBuff);
  if (!state.additionalBuffs.length) {
    const empty = document.createElement("div");
    empty.className = "additional-buff-empty";
    empty.textContent = "No additional buffs";
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
    enabled.title = "Enabled";
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
    value.step = definition.unit === "sec" ? "0.1" : "1";
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
    remove.title = "Remove";
    remove.textContent = "x";
    remove.addEventListener("click", () => {
      state.additionalBuffs.splice(index, 1);
      renderAdditionalBuffs();
    });

    row.append(enabled, typeSelect, value, unit, remove);
    list.appendChild(row);
  });
}

function addAdditionalBuff() {
  const type = inputValue("additionalBuffType", additionalBuffTypes[0].type);
  const definition = additionalBuffDefinition(type);
  state.additionalBuffs.push({
    type: definition.type,
    enabled: true,
    value: definition.defaultValue
  });
  renderAdditionalBuffs();
}

function collectPayloadForFormation(formation) {
  const rotation = normalizeRotation(formation.rotation);
  const sharedSettings = collectSharedSettings();
  const statusSettings = sharedSettings.statusSettings;
  ["1", "2", "3"].forEach((stage) => {
    rotation[stage] = rotation[stage].filter((slotIndex) => {
      return formation.slots[slotIndex] && stageMatchesSelection(formation.slots[slotIndex], stage, slotIndex, formation.slots);
    });
  });

  return {
    formation: formation.slots.map((selection) => selectionWithComputedStats(selection, statusSettings)),
    rotation,
    options: sharedSettings
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
    const parts = Object.entries(entry.data.rotation).map(([stage, names]) => `B${stage}: ${names.join(" 竊・")}`);
    div.textContent = `${entry.name} / ${parts.join(" / ")}`;
    rotation.appendChild(div);
  });

  const rows = document.getElementById("resultRows");
  rows.innerHTML = "";

  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "message";
    empty.textContent = "No results";
    rows.appendChild(empty);
    return;
  }

  entries.forEach((entry) => {
    const title = document.createElement("div");
    title.className = "formation-result-title";
    title.textContent = entry.error
      ? `${entry.name} / Error`
      : `${entry.name} / Total ${yenNumber(entry.data.totalPartyDamage)}`;
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
        const nameBlock = document.createElement("div");
        nameBlock.className = "result-name-block";
        const name = document.createElement("strong");
        name.textContent = row.name;
        const stats = document.createElement("span");
        stats.className = "result-stat-line";
        stats.textContent = `ATK ${statNumber(row.baseAtk)} / HP ${statNumber(row.baseHp)}`;
        nameBlock.append(name, stats);
        const damage = document.createElement("button");
        damage.type = "button";
        damage.className = "damage-button";
        damage.textContent = yenNumber(row.totalDamage);
        damage.title = "Show details";
        damage.addEventListener("click", () => openDetail(entry, row));
        head.append(nameBlock, damage);

        const breakdown = document.createElement("div");
        breakdown.className = "breakdown";
        if (!row.breakdown.length) {
          const empty = document.createElement("div");
          empty.className = "breakdown-row";
          empty.textContent = "No damage";
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
              ? `${yenNumber(sourceEntry.damage)} / ${count} hits / avg ${yenNumber(average)}`
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

function resultEntryTotal(entry) {
  return Number(entry?.data?.totalPartyDamage || 0);
}

function resultItemForRow(entry, row) {
  const formation = state.formations[entry.index];
  const selection = formation?.slots.find((slotSelection) => {
    return findCatalogItem(slotSelection)?.name === row.name;
  });
  return findCatalogItem(selection) || state.catalog.find((item) => item.name === row.name) || null;
}

function renderResultModalFormation(entry, index, grandTotal) {
  const card = document.createElement("article");
  card.className = "normal-result-formation";

  const head = document.createElement("div");
  head.className = "normal-result-formation-head";

  const rank = document.createElement("span");
  rank.className = "b3-rank";
  rank.textContent = entry.data && !entry.error ? `#${index + 1}` : "-";

  const icons = document.createElement("div");
  icons.className = "b3-modal-formation-icons";
  const formation = state.formations[entry.index];
  (formation?.slots || []).forEach((selection) => {
    icons.appendChild(createCharacterIcon(findCatalogItem(selection), "b3-result-thumb"));
  });

  const title = document.createElement("div");
  title.className = "b3-modal-result-name";
  const name = document.createElement("strong");
  name.textContent = entry.name;
  const sub = document.createElement("span");
  sub.textContent = entry.error ? "Error" : `編成全体 ${yenNumber(resultEntryTotal(entry))}`;
  title.append(name, sub);

  const total = document.createElement("strong");
  total.className = "b3-result-damage";
  if (entry.error) {
    total.textContent = entry.error;
    total.style.setProperty("--score", "0%");
  } else {
    const value = resultEntryTotal(entry);
    const ratio = grandTotal > 0 ? value / grandTotal : 0;
    total.style.setProperty("--score", `${ratio * 100}%`);
    total.textContent = yenNumber(value);
  }

  head.append(rank, icons, title, total);
  card.appendChild(head);

  if (entry.error || !entry.data) {
    return card;
  }

  const list = document.createElement("div");
  list.className = "normal-result-character-list";
  const topCharacterDamage = entry.data.results.reduce((maxValue, row) => Math.max(maxValue, Number(row.totalDamage || 0)), 0);
  entry.data.results.forEach((row) => {
    const item = resultItemForRow(entry, row);
    const line = document.createElement("div");
    line.className = "normal-result-character-row";

    const nameBlock = document.createElement("div");
    nameBlock.className = "b3-modal-result-name";
    const characterName = document.createElement("strong");
    characterName.textContent = row.name;
    const stats = document.createElement("span");
    stats.textContent = `ATK ${statNumber(row.baseAtk)} / HP ${statNumber(row.baseHp)}`;
    nameBlock.append(characterName, stats);

    const damage = document.createElement("strong");
    damage.className = "b3-result-damage";
    const value = Number(row.totalDamage || 0);
    const ratio = topCharacterDamage > 0 ? value / topCharacterDamage : 0;
    damage.style.setProperty("--score", `${ratio * 100}%`);
    damage.textContent = yenNumber(value);

    line.append(createCharacterIcon(item, "b3-result-thumb"), nameBlock, damage);
    list.appendChild(line);
  });
  card.appendChild(list);
  return card;
}

function setResultModalPage(scroller, pageIndex) {
  const pages = Array.from(scroller.querySelectorAll(".normal-result-page"));
  if (!pages.length) return;
  const clamped = Math.max(0, Math.min(pageIndex, pages.length - 1));
  pages[clamped].scrollIntoView({ behavior: "smooth", inline: "start", block: "nearest" });
}

function updateResultModalPager(container, scroller) {
  const pages = Array.from(scroller.querySelectorAll(".normal-result-page"));
  if (!pages.length) return;
  const pageWidth = Math.max(1, scroller.clientWidth);
  const current = Math.max(0, Math.min(pages.length - 1, Math.round(scroller.scrollLeft / pageWidth)));

  container.querySelectorAll(".normal-result-page-dot").forEach((button, index) => {
    button.classList.toggle("active", index === current);
    button.setAttribute("aria-current", index === current ? "page" : "false");
  });

  const pageText = container.querySelector("[data-result-page-text]");
  if (pageText) pageText.textContent = `${current + 1} / ${pages.length}`;

  const prev = container.querySelector("[data-result-page-prev]");
  const next = container.querySelector("[data-result-page-next]");
  if (prev) prev.disabled = current === 0;
  if (next) next.disabled = current === pages.length - 1;
}

function renderResultModalPages(container, ranked, totalDamage) {
  container.innerHTML = "";

  if (!ranked.length) {
    const empty = document.createElement("div");
    empty.className = "message";
    empty.textContent = "結果がありません";
    container.appendChild(empty);
    return;
  }

  const pager = document.createElement("div");
  pager.className = "normal-result-pager";

  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "ghost-button normal-result-page-arrow";
  prev.textContent = "<";
  prev.dataset.resultPagePrev = "true";

  const pageText = document.createElement("span");
  pageText.className = "normal-result-page-text";
  pageText.dataset.resultPageText = "true";

  const next = document.createElement("button");
  next.type = "button";
  next.className = "ghost-button normal-result-page-arrow";
  next.textContent = ">";
  next.dataset.resultPageNext = "true";

  pager.append(prev, pageText, next);

  const scroller = document.createElement("div");
  scroller.className = "normal-result-page-scroller";
  ranked.forEach((entry, index) => {
    const page = document.createElement("section");
    page.className = "normal-result-page";
    page.setAttribute("aria-label", `${entry.name} result`);
    page.appendChild(renderResultModalFormation(entry, index, totalDamage));
    scroller.appendChild(page);
  });

  const dots = document.createElement("div");
  dots.className = "normal-result-page-dots";
  ranked.forEach((entry, index) => {
    const dot = document.createElement("button");
    dot.type = "button";
    dot.className = "normal-result-page-dot";
    dot.title = entry.name;
    dot.textContent = String(index + 1);
    dot.addEventListener("click", () => setResultModalPage(scroller, index));
    dots.appendChild(dot);
  });

  prev.addEventListener("click", () => {
    const current = Math.round(scroller.scrollLeft / Math.max(1, scroller.clientWidth));
    setResultModalPage(scroller, current - 1);
  });
  next.addEventListener("click", () => {
    const current = Math.round(scroller.scrollLeft / Math.max(1, scroller.clientWidth));
    setResultModalPage(scroller, current + 1);
  });
  scroller.addEventListener("scroll", () => updateResultModalPager(container, scroller), { passive: true });
  window.setTimeout(() => updateResultModalPager(container, scroller), 0);

  container.append(pager, scroller, dots);
}

function showResultModal(entries = state.results) {
  const modal = document.getElementById("resultModal");
  const rows = document.getElementById("resultModalRows");
  const okEntries = entries.filter((entry) => entry.data && !entry.error);
  const totalDamage = okEntries.reduce((sum, entry) => sum + resultEntryTotal(entry), 0);
  const ranked = entries
    .slice()
    .sort((a, b) => resultEntryTotal(b) - resultEntryTotal(a));

  document.getElementById("resultModalTitle").textContent = "シミュレーション結果";
  document.getElementById("resultModalSummary").textContent =
    `${okEntries.length} / ${entries.length}件成功 / トータルダメージ ${okEntries.length ? yenNumber(totalDamage) : "-"}`;
  renderResultModalPages(rows, ranked, totalDamage);

  modal.hidden = false;
}

function closeResultModal() {
  document.getElementById("resultModal").hidden = true;
}

async function postSimulation(formation) {
  const response = await fetch("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectPayloadForFormation(formation))
  });
  const data = await response.json();
  if (!response.ok || data.status !== "ok") {
    throw new Error(data.error || "Simulation failed");
  }
  return data;
}

async function runSimulation(runAll = false) {
  const runButton = document.getElementById("runButton");
  const runAllButton = document.getElementById("runAllButton");
  runButton.disabled = true;
  runAllButton.disabled = true;
  setRunStatus("Running");
  document.getElementById("resultRows").innerHTML = "";

  const targets = runAll
    ? state.formations.map((formation, index) => ({ formation, index }))
    : [{ formation: activeFormationState(), index: state.activeFormation }];
  const entries = [];

  try {
    for (const target of targets) {
      setRunStatus(`${target.formation.name} running`);
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
    setRunStatus(entries.some((entry) => entry.error) ? "Partial error" : "Done", entries.some((entry) => entry.error));
    showResultModal(entries);
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
  document.getElementById("detailSubtitle").textContent = `Total ${yenNumber(row.totalDamage)} / B${row.burstStage}`;
  modal.hidden = false;
  drawDamageChart(row.damageSeries || []);
  drawAmmoChart(row.ammoHistory || []);
  drawAttackEventChart(row.damageEvents || []);
  renderDamageSummary(row.breakdown || []);
  renderBurstTimeline(row.burstEvents || []);
  renderBuffTimeline(row.buffTimeline || []);
}

function closeDetail() {
  document.getElementById("detailModal").hidden = true;
}

const SVG_NS = "http://www.w3.org/2000/svg";

function svgElement(name, attrs = {}, text = "") {
  const element = document.createElementNS(SVG_NS, name);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value !== undefined && value !== null) element.setAttribute(key, String(value));
  });
  if (text !== "") element.textContent = text;
  return element;
}

function prepareSvgChart(id, width, height, emptyMessage = "") {
  const svg = document.getElementById(id);
  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.appendChild(svgElement("rect", { x: 0, y: 0, width, height, fill: "#ffffff" }));
  if (emptyMessage) {
    svg.appendChild(svgElement("text", { x: 18, y: 28, fill: "#60706d", "font-size": 13 }, emptyMessage));
  }
  return svg;
}

function drawSvgTimelineGrid(svg, width, height, pad, ySteps = 4) {
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const grid = svgElement("g", { stroke: "#d8e0df", "stroke-width": 1 });
  const labels = svgElement("g", { fill: "#60706d", "font-size": 12, "font-family": "sans-serif" });

  for (let i = 0; i <= 6; i += 1) {
    const x = pad.left + (plotW * i) / 6;
    grid.appendChild(svgElement("line", { x1: x, y1: pad.top, x2: x, y2: pad.top + plotH }));
    labels.appendChild(svgElement("text", { x: x - 8, y: height - 12 }, String(i * 30)));
  }

  for (let i = 0; i <= ySteps; i += 1) {
    const y = pad.top + (plotH * i) / ySteps;
    grid.appendChild(svgElement("line", { x1: pad.left, y1: y, x2: pad.left + plotW, y2: y }));
  }

  labels.appendChild(svgElement("text", { x: width - 28, y: height - 12 }, "sec"));
  svg.append(grid, labels);
  return { plotW, plotH };
}

function drawDamageChart(series) {
  const width = 920;
  const height = 280;
  const pad = { left: 58, right: 18, top: 18, bottom: 36 };
  const values = Array.from({ length: DETAIL_SECONDS }, (_, index) => Number(series[index] || 0));
  const cumulative = [];
  values.reduce((sum, value, index) => {
    cumulative[index] = sum + value;
    return cumulative[index];
  }, 0);
  const maxPerSecond = Math.max(1, ...values);
  const maxCumulative = Math.max(1, ...cumulative);
  const svg = prepareSvgChart("damageChart", width, height);
  const { plotW, plotH } = drawSvgTimelineGrid(svg, width, height, pad, 4);

  const bars = svgElement("g", { fill: "rgba(11, 107, 100, 0.38)" });
  const barW = Math.max(1, plotW / DETAIL_SECONDS);
  values.forEach((value, index) => {
    const x = pad.left + index * barW;
    const barH = (value / maxPerSecond) * plotH;
    bars.appendChild(svgElement("rect", {
      x,
      y: pad.top + plotH - barH,
      width: Math.max(1, barW - 1),
      height: barH
    }));
  });
  svg.appendChild(bars);

  const cumulativePoints = cumulative
    .map((value, index) => {
      const x = pad.left + (index / (DETAIL_SECONDS - 1)) * plotW;
      const y = pad.top + plotH - (value / maxCumulative) * plotH;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  svg.appendChild(svgElement("polyline", {
    points: cumulativePoints,
    fill: "none",
    stroke: "#ad5b13",
    "stroke-width": 2
  }));

  svg.appendChild(svgElement("text", { x: pad.left, y: 14, fill: "#172322", "font-size": 12 }, `Max/s ${yenNumber(maxPerSecond)}`));
  svg.appendChild(svgElement("text", { x: width - 160, y: 14, fill: "#ad5b13", "font-size": 12 }, `Total ${yenNumber(maxCumulative)}`));
}

function drawAmmoChart(history) {
  const width = 920;
  const height = 220;
  const pad = { left: 58, right: 18, top: 18, bottom: 34 };
  const entries = (history || [])
    .map((entry) => ({
      time: Number(entry.time),
      ammo: Number(entry.ammo),
      maxAmmo: Number(entry.maxAmmo)
    }))
    .filter((entry) => Number.isFinite(entry.time));

  if (!entries.length) {
    prepareSvgChart("ammoChart", width, height, "No ammo history");
    return;
  }

  const maxAmmo = Math.max(1, ...entries.map((entry) => entry.maxAmmo || entry.ammo || 0));
  const svg = prepareSvgChart("ammoChart", width, height);
  const { plotW, plotH } = drawSvgTimelineGrid(svg, width, height, pad, 4);

  const point = (entry, value) => {
    const x = pad.left + (Math.min(DETAIL_SECONDS, Math.max(0, entry.time)) / DETAIL_SECONDS) * plotW;
    const y = pad.top + plotH - (Math.max(0, value) / maxAmmo) * plotH;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  };

  svg.appendChild(svgElement("polyline", {
    points: entries.map((entry) => point(entry, entry.maxAmmo)).join(" "),
    fill: "none",
    stroke: "#8aa39f",
    "stroke-width": 1.5,
    "stroke-dasharray": "5 4"
  }));
  svg.appendChild(svgElement("polyline", {
    points: entries.map((entry) => point(entry, entry.ammo)).join(" "),
    fill: "none",
    stroke: "#0b6b64",
    "stroke-width": 2
  }));

  svg.appendChild(svgElement("text", { x: pad.left, y: 14, fill: "#172322", "font-size": 12 }, `Max ${yenNumber(maxAmmo)}`));
  svg.appendChild(svgElement("line", { x1: width - 186, y1: 10, x2: width - 174, y2: 10, stroke: "#0b6b64", "stroke-width": 3 }));
  svg.appendChild(svgElement("text", { x: width - 168, y: 14, fill: "#0b6b64", "font-size": 12 }, "Current ammo"));
  svg.appendChild(svgElement("line", { x1: width - 92, y1: 10, x2: width - 80, y2: 10, stroke: "#8aa39f", "stroke-width": 3 }));
  svg.appendChild(svgElement("text", { x: width - 74, y: 14, fill: "#8aa39f", "font-size": 12 }, "Max"));
}

function drawAttackEventChart(events) {
  const width = 920;
  const height = 280;
  const pad = { left: 70, right: 18, top: 20, bottom: 36 };
  const entries = (events || [])
    .map((entry) => ({
      time: Number(entry.time),
      damage: Number(entry.damage),
      source: entry.source || "",
      sourceType: entry.sourceType || "",
      category: entry.category || "skill"
    }))
    .filter((entry) => Number.isFinite(entry.time) && Number.isFinite(entry.damage) && entry.damage > 0);

  if (!entries.length) {
    prepareSvgChart("attackEventChart", width, height, "No attack events");
    return;
  }

  const maxDamage = Math.max(1, ...entries.map((entry) => entry.damage));
  const normalCount = entries.filter((entry) => entry.category === "normal").length;
  const skillCount = entries.length - normalCount;
  const svg = prepareSvgChart("attackEventChart", width, height);
  const { plotW, plotH } = drawSvgTimelineGrid(svg, width, height, pad, 4);

  const axisLabels = svgElement("g", { fill: "#60706d", "font-size": 11, "font-family": "sans-serif" });
  for (let i = 0; i <= 4; i += 1) {
    const value = (maxDamage * (4 - i)) / 4;
    const y = pad.top + (plotH * i) / 4;
    axisLabels.appendChild(svgElement("text", { x: 6, y: y + 4 }, yenNumber(value)));
  }
  svg.appendChild(axisLabels);

  const points = svgElement("g");
  entries.forEach((entry) => {
    const x = pad.left + (Math.min(DETAIL_SECONDS, Math.max(0, entry.time)) / DETAIL_SECONDS) * plotW;
    const y = pad.top + plotH - (entry.damage / maxDamage) * plotH;
    const isNormal = entry.category === "normal";
    const circle = svgElement("circle", {
      cx: x,
      cy: y,
      r: isNormal ? 2.6 : 3.4,
      fill: isNormal ? "rgba(11, 107, 100, 0.68)" : "rgba(173, 91, 19, 0.72)"
    });
    circle.appendChild(svgElement(
      "title",
      {},
      `${smallNumber(entry.time)}s / ${entry.sourceType || entry.category} / ${entry.source} / ${yenNumber(entry.damage)}`
    ));
    points.appendChild(circle);
  });
  svg.appendChild(points);

  svg.appendChild(svgElement("text", { x: pad.left, y: 14, fill: "#172322", "font-size": 12 }, `Max ${yenNumber(maxDamage)}`));
  svg.appendChild(svgElement("circle", { cx: width - 190, cy: 11, r: 4, fill: "#0b6b64" }));
  svg.appendChild(svgElement("text", { x: width - 180, y: 14, fill: "#0b6b64", "font-size": 12 }, `Normal ${yenNumber(normalCount)}`));
  svg.appendChild(svgElement("circle", { cx: width - 92, cy: 11, r: 4, fill: "#ad5b13" }));
  svg.appendChild(svgElement("text", { x: width - 82, y: 14, fill: "#ad5b13", "font-size": 12 }, `Skill ${yenNumber(skillCount)}`));
}

function renderDamageSummary(breakdown) {
  const container = document.getElementById("damageSummary");
  container.innerHTML = "";

  if (!breakdown.length) {
    const empty = document.createElement("div");
    empty.className = "detail-empty";
    empty.textContent = "No damage breakdown";
    container.appendChild(empty);
    return;
  }

  const table = document.createElement("table");
  table.className = "damage-summary-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["Source", "Damage", "Count", "Average"].forEach((label) => {
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
      type.textContent = entry.sourceType || "Skill";
      const name = document.createElement("strong");
      name.textContent = entry.source;
      source.append(type, name);

      const damage = document.createElement("td");
      damage.textContent = yenNumber(entry.damage);
      const count = document.createElement("td");
      count.textContent = `${Number(entry.count || 0)} hits`;
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
    empty.textContent = "No burst events";
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
    const bucket = interval.bucket || "Other";
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

  const bucketOrder = [];
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
  StatusCalc.setData(data.statusData);
  state.statusData = data.statusData || null;
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
  document.getElementById("formationNameInput").addEventListener("input", (event) => renameActiveFormation(event.target.value));
  document.getElementById("toggleLibraryButton").addEventListener("click", toggleLibraryPane);
  document.getElementById("toggleLibraryWideButton").addEventListener("click", toggleLibraryPane);
  document.getElementById("runButton").addEventListener("click", () => runSimulation(false));
  document.getElementById("runAllButton").addEventListener("click", () => runSimulation(true));
  document.getElementById("addFormationButton").addEventListener("click", addFormation);
  document.getElementById("copyFormationButton").addEventListener("click", copyActiveFormation);
  document.getElementById("deleteFormationButton").addEventListener("click", deleteActiveFormation);
  document.getElementById("openEquipmentStatusButton").addEventListener("click", () => openStatusPanelMode("equipment"));
  document.getElementById("openOverloadStatusButton").addEventListener("click", () => openStatusPanelMode("overload"));
  document.getElementById("applyMaxStatusPresetButton").addEventListener("click", applyMaxStatusPresetToActiveFormation);
  document.getElementById("clearFormationButton").addEventListener("click", resetActiveFormation);
  document.getElementById("exportFormationsButton").addEventListener("click", exportFormations);
  document.getElementById("importFormationsButton").addEventListener("click", () => {
    document.getElementById("importFormationsInput").click();
  });
  document.getElementById("importFormationsInput").addEventListener("change", async (event) => {
    try {
      await importFormationsFromFile(event.target.files?.[0]);
    } catch (error) {
      setRunStatus(error.message, true);
    } finally {
      event.target.value = "";
    }
  });
  document.getElementById("addBuffButton").addEventListener("click", addAdditionalBuff);
  document.getElementById("closeResultModalButton").addEventListener("click", closeResultModal);
  document.getElementById("closeDetailButton").addEventListener("click", closeDetail);
  document.querySelector("[data-close-detail]").addEventListener("click", closeDetail);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDetail();
      closeResultModal();
    }
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
