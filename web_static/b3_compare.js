const state = {
  catalog: [],
  b3Candidates: [],
  catalogByKey: new Map(),
  statusData: null,
  formations: [],
  selectedAutoKeys: new Set(),
  globalBuffs: [],
  filters: {
    weaponType: "",
    element: "",
    company: "",
    class: ""
  },
  nextFormationId: 1
};

const DEFAULT_BUFFS = [
  { type: "cooldown_reduction", enabled: true, value: 5 },
  { type: "max_ammo_rate", enabled: true, value: 100 }
];

state.globalBuffs = DEFAULT_BUFFS.map(cloneInitialBuff);

const ADDITIONAL_BUFF_TYPES = [
  { type: "cooldown_reduction", label: "CT短縮", defaultValue: 5, unit: "秒" },
  { type: "max_ammo_rate", label: "装弾数バフ", defaultValue: 100, unit: "%" },
  { type: "reload_speed_rate", label: "リロード速度バフ", defaultValue: 100, unit: "%" },
  { type: "elemental_buff", label: "有利コードダメージバフ", defaultValue: 10, unit: "%" }
];

const STATUS_PART_KEYS = ["head", "body", "arms", "legs"];
const STATUS_PART_LABELS = {
  head: "頭",
  body: "胴",
  arms: "腕",
  legs: "足"
};
const STATUS_CLASS_ALIASES = {
  Attacker: "Attacker",
  "火力型": "Attacker",
  Defender: "Defender",
  "防御型": "Defender",
  Supporter: "Supporter",
  "支援型": "Supporter"
};

function cloneInitialBuff(buff) {
  return {
    type: buff.type,
    enabled: buff.enabled !== false,
    value: Number(buff.value || 0)
  };
}

function yenNumber(value) {
  return new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 0 }).format(value || 0);
}

function smallNumber(value) {
  return new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 2 }).format(value || 0);
}

function itemKey(item) {
  return item?.kind === "dummy" ? `dummy:${item.id}` : `character:${item?.file}`;
}

function selectionKey(selection) {
  if (!selection) return "";
  return selection.kind === "dummy" ? `dummy:${selection.id}` : `character:${selection.file}`;
}

function stageMatchesItem(item, requestedStage) {
  const stage = String(item?.burstStage || "");
  const requested = String(requestedStage);
  return stage === requested || stage === "∀" || stage === "竏" || stage === "ALL" || stage === "*" || stage === "all";
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
  const stage = effectiveBurstStageForSelection(selection, slotIndex, slots);
  const requested = String(requestedStage);
  return stageMatchesItem({ burstStage: stage }, requested);
}

function cloneAdditionalBuff(buff) {
  const definition = ADDITIONAL_BUFF_TYPES.find((type) => type.type === buff?.type) || ADDITIONAL_BUFF_TYPES[0];
  return {
    type: definition.type,
    enabled: buff?.enabled !== false,
    value: Number.isFinite(Number(buff?.value)) ? Number(buff.value) : definition.defaultValue
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

function normalizeOverloadSettings(settings) {
  const source = settings && typeof settings === "object" ? settings : {};
  return {
    head: normalizeOverloadPartSettings(source.head),
    body: normalizeOverloadPartSettings(source.body),
    arms: normalizeOverloadPartSettings(source.arms),
    legs: normalizeOverloadPartSettings(source.legs)
  };
}

function defaultTargetStatusSettings() {
  const defaults = StatusCalc.defaultIndividualStatusSettings();
  return {
    ...defaults,
    overload: normalizeOverloadSettings(defaults.overload)
  };
}

function normalizeTargetStatusSettings(settings) {
  const normalized = StatusCalc.normalizeIndividualStatusSettings(settings || defaultTargetStatusSettings());
  return {
    ...normalized,
    overload: normalizeOverloadSettings(normalized.overload)
  };
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
  return STATUS_CLASS_ALIASES[String(item?.class || "")] || "Attacker";
}

function overloadIconUrl(item, part) {
  return state.statusData?.overload?.icons?.[classKeyForItem(item)]?.[part] || "";
}

function cloneSelection(selection) {
  if (!selection) return null;
  const cloned = { kind: selection.kind, file: selection.file, id: selection.id };
  if (selection.statusSettings) {
    cloned.statusSettings = StatusCalc.normalizeIndividualStatusSettings(selection.statusSettings);
  }
  return cloned;
}

function selectionFromItem(item) {
  if (!item) return null;
  return item.kind === "dummy"
    ? { kind: "dummy", id: item.id }
    : { kind: "character", file: item.file };
}

function findCatalogItem(selection) {
  return state.catalogByKey.get(selectionKey(selection)) || null;
}

function imageWrap(item, className = "b3-thumb") {
  const wrap = document.createElement("div");
  wrap.className = `${className}${item?.imageUrl ? "" : " fallback"}`;
  if (item?.imageUrl) {
    const img = document.createElement("img");
    img.src = item.imageUrl;
    img.alt = item.name;
    wrap.appendChild(img);
  } else {
    const fallback = document.createElement("span");
    fallback.textContent = item?.name ? item.name.slice(0, 2) : "-";
    wrap.appendChild(fallback);
  }
  return wrap;
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

function collectSharedOptions() {
  return {
    skillLevel: inputValue("skillLevel", 10),
    enemyElement: inputValue("enemyElement", "None"),
    enemyCoreSize: inputValue("enemyCoreSize", 3.0),
    enemySize: inputValue("enemySize", 100),
    enemyCount: inputValue("enemyCount", 1),
    burstChargeTime: inputValue("burstChargeTime", 5.0),
    partBreakMode: inputChecked("partBreakMode"),
    specialMode: inputChecked("specialMode"),
    summaryOnly: true,
    statusSettings: collectStatusSettings()
  };
}

function selectionWithComputedStats(selection, commonStatusSettings, individualSettings = null) {
  const cloned = cloneSelection(selection);
  if (!cloned || cloned.kind !== "character") return cloned;

  const item = findCatalogItem(cloned);
  const individual = normalizeTargetStatusSettings(individualSettings || StatusCalc.defaultIndividualStatusSettings());
  const computedStats = StatusCalc.calculate(item, commonStatusSettings, individual);
  cloned.statusSettings = {
    ...individual,
    computedStats
  };
  return cloned;
}

function buildCatalogIndexes() {
  state.catalogByKey = new Map();
  state.catalog.forEach((item) => {
    state.catalogByKey.set(itemKey(item), item);
  });
}

function dummySelection(id) {
  return { kind: "dummy", id };
}

function candidateSelection(item) {
  return { kind: "character", file: item.file };
}

function defaultRotation() {
  return { 1: [0], 2: [1], 3: [2, 3] };
}

function emptyRotation() {
  return { 1: [], 2: [], 3: [] };
}

function stageSlotIndexes(formation, stage) {
  return formation.slots
    .map((selection, index) => ({ selection, index, item: findCatalogItem(selection) }))
    .filter((entry) => entry.item && stageMatchesSelection(entry.selection, stage, entry.index, formation.slots))
    .map((entry) => entry.index);
}

function normalizeFormationRotation(formation) {
  if (formation.rotationDetailed) {
    cleanDetailedRotation(formation);
    return;
  }
  setBasicRotation(formation);
}

function setBasicRotation(formation) {
  const rotation = emptyRotation();
  ["1", "2", "3"].forEach((stage) => {
    const valid = stageSlotIndexes(formation, stage);
    if (stage === "1" || stage === "2") {
      if (valid.length) rotation[stage] = [valid[0]];
    } else {
      if (valid.includes(2)) rotation[stage].push(2);
      valid.forEach((slot) => {
        if (rotation[stage].length < 2 && !rotation[stage].includes(slot)) {
          rotation[stage].push(slot);
        }
      });
    }
  });
  formation.rotation = rotation;
  formation.rotationDetailed = false;
}

function cleanDetailedRotation(formation) {
  const rotation = emptyRotation();
  const source = formation.rotation || {};
  ["1", "2", "3"].forEach((stage) => {
    const valid = stageSlotIndexes(formation, stage);
    const current = Array.isArray(source[stage]) ? source[stage] : Array.isArray(source[Number(stage)]) ? source[Number(stage)] : [];
    rotation[stage] = current
      .map((slot) => Number(slot))
      .filter((slot) => valid.includes(slot));
  });
  formation.rotation = rotation;
}

function rotationSequenceLabel(formation, stage) {
  const rotation = formation.rotationDetailed ? (formation.rotation || emptyRotation()) : defaultRotationForFormation(formation);
  const sequence = rotation[String(stage)] || [];
  if (!sequence.length) return "-";
  return sequence.map((slotIndex) => {
    const item = findCatalogItem(formation.slots[slotIndex]);
    return item ? `${slotIndex + 1}.${item.name}` : `${slotIndex + 1}.Empty`;
  }).join(" -> ");
}

function defaultRotationForFormation(formation) {
  const wasDetailed = formation.rotationDetailed;
  const current = formation.rotation;
  const temp = { ...formation, rotation: current, rotationDetailed: false };
  setBasicRotation(temp);
  formation.rotationDetailed = wasDetailed;
  return temp.rotation;
}

function createFormation(item, manual = false) {
  return {
    id: state.nextFormationId++,
    name: item.name,
    targetKey: itemKey(item),
    targetName: item.name,
    targetFile: item.file,
    manual,
    expanded: false,
    dirty: false,
    error: "",
    result: null,
    slots: [
      dummySelection("dummy_b1"),
      dummySelection("dummy_b2"),
      candidateSelection(item),
      dummySelection("dummy_b3"),
      dummySelection("dummy_b3_2")
    ],
    rotation: defaultRotation(),
    rotationDetailed: false,
    specialMode: false,
    additionalBuffs: state.globalBuffs.map(cloneAdditionalBuff),
    targetStatusSettings: defaultTargetStatusSettings()
  };
}

function cloneTargetStatusSettings(settings) {
  return normalizeTargetStatusSettings(JSON.parse(JSON.stringify(settings || defaultTargetStatusSettings())));
}

function cloneFormation(formation) {
  return {
    id: state.nextFormationId++,
    name: `${formation.name || formation.targetName} Copy`,
    targetKey: formation.targetKey,
    targetName: formation.targetName,
    targetFile: formation.targetFile,
    manual: true,
    expanded: true,
    dirty: true,
    error: "",
    result: null,
    slots: formation.slots.map(cloneSelection),
    rotation: {
      1: [...(formation.rotation?.[1] || formation.rotation?.["1"] || [])],
      2: [...(formation.rotation?.[2] || formation.rotation?.["2"] || [])],
      3: [...(formation.rotation?.[3] || formation.rotation?.["3"] || [])]
    },
    rotationDetailed: !!formation.rotationDetailed,
    specialMode: !!formation.specialMode,
    additionalBuffs: formation.additionalBuffs.map(cloneAdditionalBuff),
    targetStatusSettings: cloneTargetStatusSettings(formation.targetStatusSettings)
  };
}

function addFormationForItem(item, manual = false) {
  if (!item) return;
  if (!manual && state.formations.some((formation) => !formation.manual && formation.targetKey === itemKey(item))) {
    return;
  }
  state.formations.push(createFormation(item, manual));
  if (!manual) state.selectedAutoKeys.add(itemKey(item));
  renderCandidates();
  renderFormations();
  renderResults();
}

function copyFormation(formation) {
  state.formations.push(cloneFormation(formation));
  renderCandidates();
  renderFormations();
  renderResults();
}

function removeAutoFormationForItem(item) {
  const key = itemKey(item);
  state.formations = state.formations.filter((formation) => formation.manual || formation.targetKey !== key);
  state.selectedAutoKeys.delete(key);
  renderCandidates();
  renderFormations();
  renderResults();
}

function filteredCandidates() {
  const search = String(inputValue("searchInput", "")).trim().toLowerCase();
  return state.b3Candidates.filter((item) => {
    if (state.filters.weaponType && String(item.weaponType || "") !== state.filters.weaponType) return false;
    if (state.filters.element && String(item.element || "") !== state.filters.element) return false;
    if (state.filters.company && String(item.company || "") !== state.filters.company) return false;
    if (state.filters.class && String(item.class || "") !== state.filters.class) return false;
    if (!search) return true;
    return [item.name, item.weaponType, item.element, item.company, item.class]
      .some((value) => String(value || "").toLowerCase().includes(search));
  });
}

function populateFilter(selectId, key) {
  const select = document.getElementById(selectId);
  const current = select.value;
  const first = select.options[0]?.textContent || "";
  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = first;
  select.appendChild(empty);

  const values = [...new Set(state.b3Candidates.map((item) => item[key]).filter(Boolean))]
    .sort((a, b) => String(a).localeCompare(String(b), "ja"));
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === current;
    select.appendChild(option);
  });
}

function populateManualSelect() {
  const select = document.getElementById("manualCharacterSelect");
  select.innerHTML = "";
  state.b3Candidates.forEach((item) => {
    const option = document.createElement("option");
    option.value = itemKey(item);
    option.textContent = item.name;
    select.appendChild(option);
  });
}

function populateMemberSelect(select, selectedKey) {
  select.innerHTML = "";

  const dummies = document.createElement("optgroup");
  dummies.label = "Dummy";
  const characters = document.createElement("optgroup");
  characters.label = "Characters";

  state.catalog.forEach((item) => {
    const option = document.createElement("option");
    option.value = itemKey(item);
    option.textContent = item.name;
    option.selected = itemKey(item) === selectedKey;
    if (item.kind === "dummy") dummies.appendChild(option);
    else characters.appendChild(option);
  });

  select.append(dummies, characters);
}

function populateBulkMemberSelect() {
  populateMemberSelect(document.getElementById("bulkMemberSelect"), "");
}

function renderCandidates() {
  const list = document.getElementById("candidateList");
  list.innerHTML = "";
  const candidates = filteredCandidates();

  if (!candidates.length) {
    const empty = document.createElement("div");
    empty.className = "message";
    empty.textContent = "条件に一致するB3キャラクターがありません";
    list.appendChild(empty);
    return;
  }

  candidates.forEach((item) => {
    const row = document.createElement("label");
    row.className = "b3-candidate";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selectedAutoKeys.has(itemKey(item));
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) addFormationForItem(item, false);
      else removeAutoFormationForItem(item);
    });

    const meta = document.createElement("div");
    meta.className = "b3-candidate-meta";
    const name = document.createElement("strong");
    name.textContent = item.name;
    const line = document.createElement("span");
    line.textContent = `${item.weaponType || "-"} / ${item.element || "-"} / ${item.company || "-"} / ${item.class || "-"}`;
    meta.append(name, line);

    row.append(checkbox, imageWrap(item), meta);
    list.appendChild(row);
  });
}

function slotLabel(selection, index) {
  const item = findCatalogItem(selection);
  return item ? `${index + 1}. ${item.name}` : `${index + 1}. Empty`;
}

function populateSlotSelect(select, formation, stage, selectedIndex) {
  select.innerHTML = "";
  formation.slots.forEach((selection, index) => {
    const item = findCatalogItem(selection);
    if (!item || !stageMatchesSelection(selection, stage, index, formation.slots)) return;
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = slotLabel(selection, index);
    option.selected = Number(selectedIndex) === index;
    select.appendChild(option);
  });
}

function setRotationValue(formation, stage, position, value) {
  const next = Number(value);
  if (!Number.isInteger(next)) return;
  const key = String(stage);
  formation.rotation[key] = formation.rotation[key] || [];
  formation.rotation[key][position] = next;
  formation.rotation[key] = formation.rotation[key].filter((slot) => Number.isInteger(Number(slot)));
  normalizeFormationRotation(formation);
  formation.dirty = true;
}

function renderMemberControls(formation) {
  const wrap = document.createElement("div");
  wrap.className = "b3-member-grid";

  formation.slots.forEach((selection, slotIndex) => {
    const label = document.createElement("label");
    label.textContent = slotIndex === 2 ? `${slotIndex + 1}. 比較対象` : `${slotIndex + 1}. メンバー`;
    const select = document.createElement("select");
    populateMemberSelect(select, selectionKey(selection));
    select.disabled = slotIndex === 2;
    select.addEventListener("change", () => {
      const item = state.catalogByKey.get(select.value) || null;
      formation.slots[slotIndex] = selectionFromItem(item);
      formation.dirty = true;
      formation.error = "";
      normalizeFormationRotation(formation);
      renderFormations();
      renderResults();
    });
    label.appendChild(select);
    wrap.appendChild(label);
  });

  return wrap;
}

function renderNameControl(formation) {
  const wrap = document.createElement("div");
  wrap.className = "b3-name-control";
  const label = document.createElement("label");
  label.textContent = "編成名";
  const input = document.createElement("input");
  input.type = "text";
  input.value = formation.name || formation.targetName;
  input.addEventListener("input", () => {
    formation.name = input.value.trim() || formation.targetName;
    formation.dirty = true;
    renderResults();
  });
  label.appendChild(input);
  wrap.appendChild(label);
  return wrap;
}

function renderFormationTools(formation) {
  const wrap = document.createElement("div");
  wrap.className = "b3-formation-tools";

  const specialLabel = document.createElement("label");
  specialLabel.className = "check-label b3-special-toggle";
  const special = document.createElement("input");
  special.type = "checkbox";
  special.checked = !!formation.specialMode;
  special.addEventListener("change", () => {
    formation.specialMode = special.checked;
    formation.dirty = true;
    formation.error = "";
    renderFormations();
    renderResults();
  });
  specialLabel.append(special, document.createTextNode(" Special"));

  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "ghost-button";
  copyButton.textContent = "この編成をコピー";
  copyButton.addEventListener("click", () => copyFormation(formation));
  wrap.append(specialLabel, copyButton);
  return wrap;
}

function renderRotationControlsLegacy(formation) {
  normalizeFormationRotation(formation);
  const wrap = document.createElement("div");
  wrap.className = "b3-detail-grid";

  [
    ["1", 0, "B1"],
    ["2", 0, "B2"],
    ["3", 0, "B3 1人目"],
    ["3", 1, "B3 2人目"]
  ].forEach(([stage, position, labelText]) => {
    const label = document.createElement("label");
    label.textContent = labelText;
    const select = document.createElement("select");
    populateSlotSelect(select, formation, stage, formation.rotation[stage]?.[position]);
    select.addEventListener("change", () => {
      setRotationValue(formation, stage, position, select.value);
      renderFormations();
    });
    label.appendChild(select);
    wrap.appendChild(label);
  });

  return wrap;
}

function renderRotationControls(formation) {
  normalizeFormationRotation(formation);
  const panel = document.createElement("div");
  panel.className = "formation-rotation-panel b3-rotation-panel";

  const title = document.createElement("button");
  title.type = "button";
  title.className = "rotation-title";
  title.setAttribute("aria-expanded", formation.rotationDetailed ? "true" : "false");
  title.addEventListener("click", () => {
    if (!formation.rotationDetailed) {
      formation.rotationDetailed = true;
      cleanDetailedRotation(formation);
      formation.dirty = true;
      renderFormations();
      renderResults();
    }
  });

  const titleText = document.createElement("span");
  titleText.textContent = "Burst order";
  const mode = document.createElement("strong");
  mode.textContent = formation.rotationDetailed ? "Detail" : "Basic";
  title.append(titleText, mode);
  panel.appendChild(title);

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
    panel.appendChild(summary);
    return panel;
  }

  const tools = document.createElement("div");
  tools.className = "rotation-tools";
  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "ghost-button";
  reset.textContent = "Reset basic";
  reset.addEventListener("click", () => {
    setBasicRotation(formation);
    formation.dirty = true;
    formation.error = "";
    renderFormations();
    renderResults();
  });
  tools.appendChild(reset);
  panel.appendChild(tools);

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
    const rotation = formation.rotation || emptyRotation();
    (rotation[stage] || []).forEach((slotIndex, orderIndex) => {
      const item = findCatalogItem(formation.slots[slotIndex]);
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "rotation-chip";
      chip.title = "Remove this entry";
      const icon = imageWrap(item, "rotation-icon");
      const text = document.createElement("span");
      text.textContent = item ? `${orderIndex + 1}. ${item.name}` : `${orderIndex + 1}. Empty`;
      chip.append(icon, text);
      chip.addEventListener("click", () => {
        cleanDetailedRotation(formation);
        formation.rotation[stage].splice(orderIndex, 1);
        formation.dirty = true;
        formation.error = "";
        renderFormations();
        renderResults();
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
      add.title = `${item.name} B${stage}`;
      const icon = imageWrap(item, "rotation-icon");
      const text = document.createElement("span");
      text.textContent = `${slotIndex + 1}. ${item.name}`;
      add.append(icon, text);
      add.addEventListener("click", () => {
        cleanDetailedRotation(formation);
        formation.rotation[stage].push(slotIndex);
        formation.dirty = true;
        formation.error = "";
        renderFormations();
        renderResults();
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
      cleanDetailedRotation(formation);
      formation.rotation[stage] = [];
      formation.dirty = true;
      formation.error = "";
      renderFormations();
      renderResults();
    });

    controls.append(head, sequence, candidates, clear);
    panel.appendChild(controls);
  });

  return panel;
}

function renderBuffControls(formation) {
  const wrap = document.createElement("div");
  wrap.className = "b3-buff-list";

  formation.additionalBuffs = formation.additionalBuffs.map(cloneAdditionalBuff);
  formation.additionalBuffs.forEach((buff, index) => {
    const definition = ADDITIONAL_BUFF_TYPES.find((type) => type.type === buff.type) || ADDITIONAL_BUFF_TYPES[0];
    const row = document.createElement("div");
    row.className = "b3-buff-row";

    const enabled = document.createElement("input");
    enabled.type = "checkbox";
    enabled.checked = buff.enabled;
    enabled.addEventListener("change", () => {
      formation.additionalBuffs[index].enabled = enabled.checked;
      formation.dirty = true;
    });

    const name = document.createElement("span");
    name.textContent = definition.label;

    const value = document.createElement("input");
    value.type = "number";
    value.min = "0";
    value.step = definition.type === "cooldown_reduction" ? "0.1" : "1";
    value.value = buff.value;
    value.addEventListener("input", () => {
      formation.additionalBuffs[index].value = Number(value.value);
      formation.dirty = true;
    });

    const unit = document.createElement("span");
    unit.className = "buff-unit";
    unit.textContent = definition.unit;
    row.append(enabled, name, value, unit);
    wrap.appendChild(row);
  });

  return wrap;
}

function setTargetOverloadValue(formation, part, optionIndex, key, value) {
  formation.targetStatusSettings = normalizeTargetStatusSettings(formation.targetStatusSettings);
  const entry = formation.targetStatusSettings.overload[part][optionIndex];
  entry[key] = key === "rank" ? Number(value) : value;
  if (key === "type") {
    entry.rank = value ? defaultOverloadRank(value) : 0;
  }
  formation.dirty = true;
  formation.error = "";
}

function renderOverloadOptionRow(formation, part, optionIndex, entry) {
  const row = document.createElement("div");
  row.className = "overload-option-row";

  const optionSelect = document.createElement("select");
  const emptyOption = document.createElement("option");
  emptyOption.value = "";
  emptyOption.textContent = "None";
  optionSelect.appendChild(emptyOption);
  overloadOptionNames().forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    option.selected = name === String(entry.type || "");
    optionSelect.appendChild(option);
  });
  optionSelect.addEventListener("change", () => {
    setTargetOverloadValue(formation, part, optionIndex, "type", optionSelect.value);
    renderFormations();
    renderResults();
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
    setTargetOverloadValue(formation, part, optionIndex, "rank", rankSelect.value);
    renderFormations();
    renderResults();
  });

  row.append(optionSelect, rankSelect);
  return row;
}

function renderTargetOverloadControls(formation) {
  formation.targetStatusSettings = normalizeTargetStatusSettings(formation.targetStatusSettings);
  const targetItem = findCatalogItem(formation.slots[2]);
  const wrap = document.createElement("div");
  wrap.className = "b3-overload-grid";

  STATUS_PART_KEYS.forEach((part) => {
    const partCard = document.createElement("div");
    partCard.className = "slot-overload-part";

    const head = document.createElement("div");
    head.className = "overload-part-head";
    const icon = document.createElement("div");
    icon.className = "overload-icon";
    const iconUrl = overloadIconUrl(targetItem, part);
    if (iconUrl) {
      const img = document.createElement("img");
      img.src = iconUrl;
      img.alt = `${STATUS_PART_LABELS[part]} icon`;
      icon.appendChild(img);
    } else {
      icon.textContent = STATUS_PART_LABELS[part];
    }
    const label = document.createElement("strong");
    label.textContent = STATUS_PART_LABELS[part];
    head.append(icon, label);
    partCard.appendChild(head);

    formation.targetStatusSettings.overload[part].forEach((entry, optionIndex) => {
      partCard.appendChild(renderOverloadOptionRow(formation, part, optionIndex, entry));
    });
    wrap.appendChild(partCard);
  });

  return wrap;
}

function renderGlobalBuffControls() {
  const wrap = document.getElementById("globalBuffList");
  if (!wrap) return;
  wrap.innerHTML = "";
  state.globalBuffs = state.globalBuffs.map(cloneAdditionalBuff);

  state.globalBuffs.forEach((buff, index) => {
    const definition = ADDITIONAL_BUFF_TYPES.find((type) => type.type === buff.type) || ADDITIONAL_BUFF_TYPES[0];
    const row = document.createElement("div");
    row.className = "b3-buff-row";

    const enabled = document.createElement("input");
    enabled.type = "checkbox";
    enabled.checked = buff.enabled;
    enabled.addEventListener("change", () => {
      state.globalBuffs[index].enabled = enabled.checked;
      syncGlobalBuffsToFormations();
    });

    const name = document.createElement("span");
    name.textContent = definition.label;

    const value = document.createElement("input");
    value.type = "number";
    value.min = "0";
    value.step = definition.type === "cooldown_reduction" ? "0.1" : "1";
    value.value = buff.value;
    value.addEventListener("input", () => {
      state.globalBuffs[index].value = Number(value.value);
      syncGlobalBuffsToFormations();
    });

    const unit = document.createElement("span");
    unit.className = "buff-unit";
    unit.textContent = definition.unit;
    row.append(enabled, name, value, unit);
    wrap.appendChild(row);
  });
}

function syncGlobalBuffsToFormations() {
  state.formations.forEach((formation) => {
    formation.additionalBuffs = state.globalBuffs.map(cloneAdditionalBuff);
    formation.dirty = true;
  });
  renderFormations();
  renderResults();
}

function targetDamage(formation) {
  const row = formation.result?.results?.find((entry) => entry.name === formation.targetName);
  return Number(row?.totalDamage || 0);
}

function renderFormationIcons(formation) {
  const icons = document.createElement("div");
  icons.className = "b3-formation-icons";
  formation.slots.forEach((selection) => {
    icons.appendChild(imageWrap(findCatalogItem(selection), "b3-mini-thumb"));
  });
  return icons;
}

function renderFormations() {
  document.getElementById("formationCount").textContent = `${state.formations.length}件`;
  const rows = document.getElementById("formationRows");
  rows.innerHTML = "";

  if (!state.formations.length) {
    const empty = document.createElement("div");
    empty.className = "message";
    empty.textContent = "比較対象をチェックすると編成が追加されます";
    rows.appendChild(empty);
    return;
  }

  state.formations.forEach((formation) => {
    const card = document.createElement("article");
    card.className = `b3-formation-card${formation.expanded ? " expanded" : ""}`;

    const head = document.createElement("button");
    head.type = "button";
    head.className = "b3-formation-head";
    head.addEventListener("click", () => {
      formation.expanded = !formation.expanded;
      renderFormations();
    });

    const item = state.catalogByKey.get(formation.targetKey);
    const title = document.createElement("div");
    title.className = "b3-formation-title";
    const name = document.createElement("strong");
    name.textContent = formation.name || formation.targetName;
    const meta = document.createElement("span");
    meta.textContent = `${item?.weaponType || "-"} / ${item?.element || "-"}${formation.dirty ? " / 変更あり" : ""}`;
    title.append(name, meta);

    const damage = document.createElement("strong");
    damage.className = "b3-formation-damage";
    damage.textContent = formation.result ? yenNumber(targetDamage(formation)) : "-";
    head.append(renderFormationIcons(formation), title, damage);
    card.appendChild(head);

    if (formation.expanded) {
      const detail = document.createElement("div");
      detail.className = "b3-formation-detail";
      const nameTitle = document.createElement("h3");
      nameTitle.textContent = "編成名";
      const memberTitle = document.createElement("h3");
      memberTitle.textContent = "編成メンバー";
      const rotationTitle = document.createElement("h3");
      rotationTitle.textContent = "バースト選択";
      const buffTitle = document.createElement("h3");
      buffTitle.textContent = "常時バフ";
      const overloadTitle = document.createElement("h3");
      overloadTitle.textContent = "比較対象オバロOP";
      detail.append(
        nameTitle,
        renderNameControl(formation),
        renderFormationTools(formation),
        memberTitle,
        renderMemberControls(formation),
        rotationTitle,
        renderRotationControls(formation),
        buffTitle,
        renderBuffControls(formation),
        overloadTitle,
        renderTargetOverloadControls(formation)
      );
      card.appendChild(detail);
    }

    rows.appendChild(card);
  });
}

function collectEntry(formation) {
  const statusSettings = collectStatusSettings();
  return {
    id: formation.id,
    index: formation.id,
    name: formation.name || formation.targetName,
    formation: formation.slots.map((selection, index) => {
      const individual = index === 2 ? formation.targetStatusSettings : null;
      return selectionWithComputedStats(selection, statusSettings, individual);
    }),
    rotation: formation.rotation,
    options: {
      specialMode: !!formation.specialMode,
      additionalBuffs: formation.additionalBuffs.map(cloneAdditionalBuff)
    }
  };
}

function successfulFormations() {
  return state.formations.filter((formation) => formation.result && !formation.error);
}

function renderSummary() {
  const ok = successfulFormations();
  const top = ok.reduce((maxValue, formation) => Math.max(maxValue, targetDamage(formation)), 0);
  document.querySelector("#b3Summary div:nth-child(1) strong").textContent = state.formations.length ? yenNumber(state.formations.length) : "-";
  document.querySelector("#b3Summary div:nth-child(2) strong").textContent = ok.length ? yenNumber(ok.length) : "-";
  document.querySelector("#b3Summary div:nth-child(3) strong").textContent = ok.length ? yenNumber(top) : "-";
}

function renderResults() {
  renderSummary();
  const rows = document.getElementById("resultRows");
  rows.innerHTML = "";

  const topDamage = state.formations.reduce((maxValue, formation) => {
    return Math.max(maxValue, targetDamage(formation));
  }, 0);
  const ranked = state.formations
    .slice()
    .sort((a, b) => {
      const ad = targetDamage(a);
      const bd = targetDamage(b);
      if (ad !== bd) return bd - ad;
      return a.id - b.id;
    });

  if (!ranked.length) {
    const empty = document.createElement("div");
    empty.className = "message";
    empty.textContent = "まだ結果がありません";
    rows.appendChild(empty);
    return;
  }

  ranked.forEach((formation, index) => {
    const item = state.catalogByKey.get(formation.targetKey);
    const row = document.createElement("div");
    row.className = "b3-result-row";
    const rank = document.createElement("span");
    rank.className = "b3-rank";
    rank.textContent = formation.result && !formation.error ? `#${index + 1}` : "-";
    const name = document.createElement("strong");
    name.textContent = formation.name || formation.targetName;
    name.title = formation.targetName;
    const damage = document.createElement("strong");
    damage.className = "b3-result-damage";
    if (formation.error) {
      damage.textContent = formation.error;
    } else if (formation.result) {
      const value = targetDamage(formation);
      const ratio = topDamage > 0 ? value / topDamage : 0;
      const percent = ratio * 100;
      const hue = 18 + ratio * 150;
      damage.style.setProperty("--score", `${percent}%`);
      damage.style.color = `hsl(${hue}, 70%, 30%)`;
      damage.textContent = yenNumber(value);
    } else {
      damage.textContent = "-";
      damage.style.setProperty("--score", "0%");
    }
    row.append(rank, imageWrap(item, "b3-result-thumb"), name, damage);
    rows.appendChild(row);
  });
}

function showResultModal() {
  const modal = document.getElementById("resultModal");
  const modalRows = document.getElementById("resultModalRows");
  const ranked = state.formations
    .slice()
    .sort((a, b) => {
      const ad = targetDamage(a);
      const bd = targetDamage(b);
      if (ad !== bd) return bd - ad;
      return a.id - b.id;
    });
  const topDamage = ranked.reduce((maxValue, formation) => Math.max(maxValue, targetDamage(formation)), 0);
  document.getElementById("resultModalTitle").textContent = inputValue("comparisonTitle", "B3 Compare") || "B3 Compare";
  document.getElementById("resultModalSummary").textContent =
    `${successfulFormations().length} / ${state.formations.length}件成功`;
  modalRows.innerHTML = "";
  ranked.forEach((formation, index) => {
    modalRows.appendChild(renderModalResultRow(formation, index, topDamage));
  });
  modal.hidden = false;
}

function renderModalResultRow(formation, index, topDamage) {
  const row = document.createElement("div");
  row.className = "b3-result-row b3-result-row-modal";

  const rank = document.createElement("span");
  rank.className = "b3-rank";
  rank.textContent = formation.result && !formation.error ? `#${index + 1}` : "-";

  const icons = document.createElement("div");
  icons.className = "b3-modal-formation-icons";
  formation.slots.forEach((selection) => {
    icons.appendChild(imageWrap(findCatalogItem(selection), "b3-result-thumb"));
  });

  const nameBlock = document.createElement("div");
  nameBlock.className = "b3-modal-result-name";
  const name = document.createElement("strong");
  name.textContent = formation.name || formation.targetName;
  const target = document.createElement("span");
  target.textContent = formation.targetName;
  nameBlock.append(name, target);

  const damage = document.createElement("strong");
  damage.className = "b3-result-damage";
  if (formation.error) {
    damage.textContent = formation.error;
  } else if (formation.result) {
    const value = targetDamage(formation);
    const ratio = topDamage > 0 ? value / topDamage : 0;
    const percent = ratio * 100;
    const hue = 18 + ratio * 150;
    damage.style.setProperty("--score", `${percent}%`);
    damage.style.color = `hsl(${hue}, 70%, 30%)`;
    damage.textContent = `${yenNumber(value)} / ${smallNumber(percent)}%`;
  } else {
    damage.textContent = "-";
    damage.style.setProperty("--score", "0%");
  }

  row.append(rank, icons, nameBlock, damage);
  return row;
}

function closeResultModal() {
  document.getElementById("resultModal").hidden = true;
}

function setRunStatus(text, isError = false) {
  const status = document.getElementById("runStatus");
  status.textContent = text;
  status.classList.toggle("error", isError);
}

async function runComparison() {
  if (!state.formations.length) return;
  const button = document.getElementById("runButton");
  button.disabled = true;
  setRunStatus(`${state.formations.length}件 実行中`);

  let completed = false;

  try {
    const response = await fetch("/api/simulate-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        entries: state.formations.map(collectEntry),
        options: collectSharedOptions()
      })
    });
    const data = await response.json();
    if (!response.ok || data.status !== "ok") {
      throw new Error(data.error || "比較に失敗しました");
    }

    const resultMap = new Map(data.results.map((entry) => [entry.id, entry]));
    state.formations.forEach((formation) => {
      const entry = resultMap.get(formation.id);
      if (!entry) return;
      if (entry.error) {
        formation.error = entry.error;
        formation.result = null;
      } else {
        formation.error = "";
        formation.result = entry.data;
        formation.dirty = false;
      }
    });
    setRunStatus(`完了 ${smallNumber(data.elapsedSeconds)}s`);
    completed = true;
  } catch (error) {
    setRunStatus(error.message, true);
  } finally {
    button.disabled = false;
    renderFormations();
    renderResults();
    if (completed) showResultModal();
  }
}

function selectVisible() {
  filteredCandidates().forEach((item) => addFormationForItem(item, false));
}

function clearVisible() {
  filteredCandidates().forEach((item) => removeAutoFormationForItem(item));
}

function applyBulkReplace() {
  const slotIndex = Number(inputValue("bulkSlotSelect", -1));
  const item = state.catalogByKey.get(inputValue("bulkMemberSelect", "")) || null;
  if (![0, 1, 3, 4].includes(slotIndex) || !item) return;

  state.formations.forEach((formation) => {
    formation.slots[slotIndex] = selectionFromItem(item);
    formation.dirty = true;
    formation.error = "";
    normalizeFormationRotation(formation);
  });
  renderFormations();
  renderResults();
}

function bindEvents() {
  document.getElementById("searchInput").addEventListener("input", renderCandidates);
  document.querySelectorAll(".catalog-filter").forEach((select) => {
    select.addEventListener("change", () => {
      state.filters[select.dataset.filterKey] = select.value;
      renderCandidates();
    });
  });
  document.getElementById("selectVisibleButton").addEventListener("click", selectVisible);
  document.getElementById("clearVisibleButton").addEventListener("click", clearVisible);
  document.getElementById("manualAddButton").addEventListener("click", () => {
    addFormationForItem(state.catalogByKey.get(inputValue("manualCharacterSelect", "")), true);
  });
  document.getElementById("bulkReplaceButton").addEventListener("click", applyBulkReplace);
  document.getElementById("closeResultModalButton").addEventListener("click", closeResultModal);
  document.getElementById("resultModal").addEventListener("click", (event) => {
    if (event.target.id === "resultModal") closeResultModal();
  });
  document.getElementById("runButton").addEventListener("click", runComparison);
}

async function loadCatalog() {
  const response = await fetch("/api/characters");
  const data = await response.json();
  StatusCalc.setData(data.statusData);
  state.statusData = data.statusData || null;
  state.catalog = [...data.dummies, ...data.characters];
  state.b3Candidates = data.characters
    .filter((item) => stageMatchesItem(item, "3"))
    .sort((a, b) => String(a.name).localeCompare(String(b.name), "ja"));
  buildCatalogIndexes();
  populateFilter("weaponFilter", "weaponType");
  populateFilter("elementFilter", "element");
  populateFilter("companyFilter", "company");
  populateFilter("classFilter", "class");
  populateManualSelect();
  populateBulkMemberSelect();
  renderGlobalBuffControls();
  renderCandidates();
  renderFormations();
  renderResults();
  document.getElementById("catalogStatus").textContent = `${state.b3Candidates.length} B3 / ${data.characters.length} JSON`;
}

bindEvents();
loadCatalog().catch((error) => {
  document.getElementById("catalogStatus").textContent = "読み込みエラー";
  document.getElementById("candidateList").innerHTML = `<div class="message">${error.message}</div>`;
});
