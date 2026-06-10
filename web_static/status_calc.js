(function attachStatusCalc(global) {
  const CLASS_ALIASES = {
    Attacker: "Attacker",
    "火力型": "Attacker",
    Defender: "Defender",
    "防御型": "Defender",
    Supporter: "Supporter",
    "支援型": "Supporter"
  };

  const COMPANY_ALIASES = {
    Elysion: "Elysion",
    "エリシオン": "Elysion",
    Missilis: "Missilis",
    "ミシリス": "Missilis",
    Tetra: "Tetra",
    "テトラ": "Tetra",
    Pilgrim: "Pilgrim",
    "ピルグリム": "Pilgrim",
    Abnormal: "Abnormal",
    "アブノーマル": "Abnormal"
  };

  const PART_KEYS = ["head", "body", "arms", "legs"];

  let statusData = null;

  function numberValue(value, fallback = 0) {
    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue : fallback;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function defaultEquipmentSettings() {
    return {
      head: { tier: "T9", level: 5 },
      body: { tier: "T9", level: 5 },
      arms: { tier: "T9", level: 5 },
      legs: { tier: "T9", level: 5 }
    };
  }

  function defaultIndividualStatusSettings() {
    return {
      limitBreak: 10,
      bondLevel: 30,
      collectionRarity: "",
      collectionLevel: 0,
      cubeLevel: 0,
      equipment: defaultEquipmentSettings()
    };
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

  function mergeStatusSettings(commonSettings, individualSettings) {
    const defaults = defaultIndividualStatusSettings();
    const common = commonSettings && typeof commonSettings === "object" ? commonSettings : {};
    const individual = individualSettings && typeof individualSettings === "object"
      ? normalizeIndividualStatusSettings(individualSettings)
      : {};
    const commonEquipment = common.equipment && typeof common.equipment === "object" ? common.equipment : {};
    const individualEquipment = individual.equipment && typeof individual.equipment === "object" ? individual.equipment : {};
    return {
      ...defaults,
      ...common,
      ...individual,
      enabled: true,
      equipment: {
        head: { ...defaults.equipment.head, ...(commonEquipment.head || {}), ...(individualEquipment.head || {}) },
        body: { ...defaults.equipment.body, ...(commonEquipment.body || {}), ...(individualEquipment.body || {}) },
        arms: { ...defaults.equipment.arms, ...(commonEquipment.arms || {}), ...(individualEquipment.arms || {}) },
        legs: { ...defaults.equipment.legs, ...(commonEquipment.legs || {}), ...(individualEquipment.legs || {}) }
      }
    };
  }

  function lookupLevel(table, level) {
    const rows = Array.isArray(table) ? table : [];
    if (!rows.length) return { hp: 0, atk: 0 };
    const targetLevel = numberValue(level);
    let selected = rows[0];
    rows.forEach((row) => {
      if (numberValue(row.level) <= targetLevel && numberValue(row.level) >= numberValue(selected.level)) {
        selected = row;
      }
    });
    return { hp: numberValue(selected.hp), atk: numberValue(selected.atk) };
  }

  function lookupEquipment(table, tier, level) {
    const rows = Array.isArray(table) ? table.filter((row) => String(row.tier) === String(tier)) : [];
    return lookupLevel(rows, level);
  }

  function classKeyFor(value) {
    return CLASS_ALIASES[String(value || "")] || "Attacker";
  }

  function companyKeyFor(value) {
    return COMPANY_ALIASES[String(value || "")] || String(value || "");
  }

  function researchLevel(levels, key) {
    if (!levels || typeof levels !== "object") return 0;
    return numberValue(levels[key], 0);
  }

  function calculate(item, commonSettings, individualSettings) {
    if (!statusData || !item || item.kind !== "character") return null;

    const settings = mergeStatusSettings(commonSettings, individualSettings);
    const classKey = classKeyFor(item.class);
    const classData = statusData.classes?.[classKey];
    if (!classData) return null;

    const base = lookupLevel(classData.base, settings.level ?? 400);
    const limitBreak = clamp(Math.trunc(numberValue(settings.limitBreak, 10)), 0, 10);
    const fixed = statusData.limitBreakFixed || { hp: 0, atk: 0 };

    let hp = base.hp;
    let atk = base.atk;
    const firstLimitBreaks = Math.min(limitBreak, 3);
    hp += ((base.hp * 0.02) + numberValue(fixed.hp)) * firstLimitBreaks;
    atk += ((base.atk * 0.02) + numberValue(fixed.atk)) * firstLimitBreaks;

    const bond = lookupLevel(classData.bond, settings.bondLevel ?? 30);
    const research = statusData.research || {};
    const companyKey = companyKeyFor(item.company);
    const classResearchLevel = researchLevel(settings.classResearchLevels, classKey);
    const companyResearchLevel = researchLevel(settings.companyResearchLevels, companyKey);
    const commonResearchLevel = numberValue(settings.commonResearchLevel, 0);
    hp += bond.hp;
    atk += bond.atk;
    hp += numberValue(research.class?.hp) * classResearchLevel;
    atk += numberValue(research.class?.atk) * classResearchLevel;
    hp += numberValue(research.company?.hp) * companyResearchLevel;
    atk += numberValue(research.company?.atk) * companyResearchLevel;
    hp += numberValue(research.common?.hp) * commonResearchLevel;
    atk += numberValue(research.common?.atk) * commonResearchLevel;

    if (limitBreak > 3) {
      const extraRate = 0.02 * (limitBreak - 3);
      hp *= 1 + extraRate;
      atk *= 1 + extraRate;
    }

    PART_KEYS.forEach((partKey) => {
      const part = settings.equipment?.[partKey] || {};
      const equipment = lookupEquipment(classData.equipment?.[partKey], part.tier || "T9", part.level ?? 5);
      hp += equipment.hp;
      atk += equipment.atk;
    });

    const collectionRarity = String(settings.collectionRarity || "").trim();
    if (collectionRarity && collectionRarity.toLowerCase() !== "none") {
      const collection = lookupLevel(statusData.collection?.[collectionRarity], settings.collectionLevel ?? 0);
      hp += collection.hp;
      atk += collection.atk;
    }

    const cubeLevel = numberValue(settings.cubeLevel, 0);
    if (cubeLevel > 0) {
      const cube = lookupLevel(statusData.cube, cubeLevel);
      hp += cube.hp;
      atk += cube.atk;
    }

    return {
      baseAtk: Math.round(atk),
      baseHp: Math.round(hp),
      base_atk: Math.round(atk),
      base_hp: Math.round(hp)
    };
  }

  function setData(data) {
    statusData = data || null;
  }

  global.StatusCalc = {
    setData,
    calculate,
    defaultEquipmentSettings,
    defaultIndividualStatusSettings,
    normalizeIndividualStatusSettings,
    mergeStatusSettings
  };
})(window);
