const DETAIL_SECONDS = 180;

const state = {
  activeSlot: 0,
  activeFormation: 0,
  filter: "all",
  catalogFilters: {
    weaponType: "",
    element: "",
    company: "",
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
  { type: "cooldown_reduction", label: "CT短縮", defaultValue: 5, unit: "sec" },
  { type: "max_ammo_rate", label: "装弾数バフ", defaultValue: 100, unit: "%" },
  { type: "reload_speed_rate", label: "リロード速度バフ", defaultValue: 100, unit: "%" },
  { type: "elemental_buff", label: "有利コードダメージバフ", defaultValue: 10, unit: "%" }
];

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
  return {
    ...defaults,
    ...source,
    equipment: {
      head: { ...defaults.equipment.head, ...(equipment.head || {}) },
      body: { ...defaults.equipment.body, ...(equipment.body || {}) },
      arms: { ...defaults.equipment.arms, ...(equipment.arms || {}) },
      legs: { ...defaults.equipment.legs, ...(equipment.legs || {}) }
    }
  };
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
    return formation.slots.findIndex((selection) => stageMatchesItem(findCatalogItem(selection), stage));
  };

  const b1 = firstForStage("1");
  const b2 = firstForStage("2");
  if (b1 >= 0) rotation[1].push(b1);
  if (b2 >= 0) rotation[2].push(b2);

  formation.slots.forEach((selection, index) => {
    if (rotation[3].length < 2 && stageMatchesItem(findCatalogItem(selection), "3")) {
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
      return stageMatchesItem(findCatalogItem(formation.slots[slotIndex]), stage);
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
    result: null
  };
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

function setFormation(slotIndex, item) {
  const formation = activeFormationState();
  formation.slots[slotIndex] = selectionFromItem(item);
  if (formation.rotationDetailed) cleanDetailedRotation(formation);
  else setBasicRotation(formation);
  formation.result = null;
  formation.statusOpenSlot = item?.kind === "character" ? slotIndex : null;
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

function createSlotStatusPanel(formation, slotIndex, item) {
  const selection = formation.slots[slotIndex];
  selection.statusSettings = normalizeIndividualStatusSettings(selection.statusSettings);
  const settings = selection.statusSettings;

  const panel = document.createElement("div");
  panel.className = "slot-status-panel";
  panel.addEventListener("click", (event) => event.stopPropagation());

  const head = document.createElement("div");
  head.className = "slot-status-head";
  const title = document.createElement("strong");
  title.textContent = item.name;
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Close";
  close.addEventListener("click", () => {
    formation.statusOpenSlot = null;
    renderFormation();
  });
  head.append(title, close);

  const grid = document.createElement("div");
  grid.className = "slot-status-grid";
  grid.append(
    createNumberField("Limit", settings.limitBreak, { min: 0, max: 10 }, (value) => setSlotStatusValue(formation, slotIndex, "limitBreak", value)),
    createSelectField("Bond", settings.bondLevel, [0, 10, 20, 30, 40], (value) => setSlotStatusValue(formation, slotIndex, "bondLevel", value)),
    createCollectionField(settings, formation, slotIndex),
    createNumberField("Collection Lv", settings.collectionLevel, { min: 0, max: 15 }, (value) => setSlotStatusValue(formation, slotIndex, "collectionLevel", value)),
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

  panel.append(head, grid, equipment);
  return panel;
}

function resultForSlot(formation, item) {
  if (!formation.result || !item) return null;
  return (formation.result.results || []).find((row) => row.name === item.name) || null;
}

function renderFormation() {
  const formation = activeFormationState();
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
    icon.title = item?.kind === "character" ? "Status settings" : "";
    icon.addEventListener("click", (event) => {
      if (item?.kind !== "character") return;
      event.stopPropagation();
      state.activeSlot = index;
      formation.statusOpenSlot = formation.statusOpenSlot === index ? null : index;
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
    if (formation.statusOpenSlot === index && item?.kind === "character") {
      slot.appendChild(createSlotStatusPanel(formation, index, item));
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
        if (!stageMatchesItem(item, stage)) return;
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
  const rotation = normalizeRotation(formation.rotation);
  const statusSettings = collectStatusSettings();
  ["1", "2", "3"].forEach((stage) => {
    rotation[stage] = rotation[stage].filter((slotIndex) => {
      return formation.slots[slotIndex] && stageMatchesItem(findCatalogItem(formation.slots[slotIndex]), stage);
    });
  });

  return {
    formation: formation.slots.map((selection) => selectionWithComputedStats(selection, statusSettings)),
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
      statusSettings,
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
  ctx.fillText("sec", width - 28, height - 12);
  ctx.fillText(`Max/s ${yenNumber(maxPerSecond)}`, pad.left, 14);
  ctx.fillStyle = "#ad5b13";
  ctx.fillText(`Total ${yenNumber(maxCumulative)}`, width - 160, 14);
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
