"use strict";

const byId = (id) => document.getElementById(id);
const factors = { px: 1, mm: 96 / 25.4, cm: 96 / 2.54, pt: 96 / 72 };
const palettes = {
  newspaper: ["#22211e", "#34312a", "#161718", "#f8f3e6"],
  magazine: ["#fff9e8", "#1e2426", "#182a25", "#322026", "#27221e"],
  mixed: ["#22211e", "#fff9e8", "#1e2426", "#182a25", "#322026"],
  "black-and-white": ["#000000", "#ffffff"],
  primary: ["#ff0000", "#0000ff", "#ffcc00"],
  rainbow: ["#ff0000", "#ff8000", "#ffdd00", "#00aa00", "#0066ff", "#8800ff"],
  neon: ["#ff00ff", "#00ffff", "#bfff00", "#ffff00", "#ff3300"],
  warm: ["#dd0000", "#ff5500", "#ffaa00", "#990000"],
  cool: ["#0000ff", "#0088ff", "#00aa88", "#6600cc"],
  grayscale: ["#000000", "#444444", "#888888", "#cccccc", "#ffffff"],
};
const legacy = ["newspaper", "magazine", "mixed"];
const originalSwatches = {
  newspaper: ["#ece3ce", "#fffcf4", "#292823"],
  magazine: ["#c44032", "#ecc443", "#253d62", "#a8c5b9", "#f0a3b1"],
  mixed: ["#ece3ce", "#292823", "#c44032", "#ecc443", "#a8c5b9"],
};
let customColors = ["#ff0000", "#0000ff", "#ffcc00"];
let pageUnit = "px";
let fontUnit = "px";
let revision = 0;
let timer;
let controller;
let currentResult = null;
let previewUrl = null;

function newSeed() {
  return crypto.getRandomValues(new Uint32Array(1))[0];
}

function normalizedColor(value) {
  if (!/^#[0-9a-f]{3}([0-9a-f]{3})?$/i.test(value)) return null;
  return value.length === 4
    ? "#" + Array.from(value.slice(1), (char) => char + char).join("").toLowerCase()
    : value.toLowerCase();
}

function selectedPalette() {
  return document.querySelector('input[name="palette"]:checked').value;
}

function selectPalette(value) {
  document.querySelectorAll('input[name="palette"]').forEach((input) => {
    input.checked = input.value === value;
  });
}

function updatePalette() {
  const selected = selectedPalette();
  byId("custom-palette").hidden = selected !== "custom";
  document.querySelectorAll(".palette-card").forEach((card) => {
    const value = card.querySelector("input").value;
    const style = value === "auto" ? byId("preset").value : value;
    const colors = value === "custom"
      ? customColors.map(normalizedColor).filter(Boolean)
      : originalSwatches[style] || palettes[style];
    const preview = card.querySelector(".card-colors");
    preview.replaceChildren();
    for (const color of colors) {
      const swatch = document.createElement("span");
      swatch.className = "color-swatch";
      swatch.style.backgroundColor = color;
      swatch.title = color;
      swatch.setAttribute("aria-hidden", "true");
      preview.appendChild(swatch);
    }
  });
}

function rebuildCustomColors() {
  const container = byId("custom-colors");
  container.replaceChildren();
  customColors.forEach((color, index) => {
    const row = document.createElement("div");
    row.className = "color-row";
    const picker = document.createElement("input");
    picker.type = "color";
    picker.value = normalizedColor(color) || "#000000";
    picker.setAttribute("aria-label", `Pick custom color ${index + 1}`);
    const hex = document.createElement("input");
    hex.type = "text";
    hex.value = color;
    hex.maxLength = 7;
    hex.spellcheck = false;
    hex.setAttribute("aria-label", `Custom color ${index + 1} hex value`);
    picker.addEventListener("input", () => {
      customColors[index] = picker.value;
      hex.value = picker.value;
      updatePalette();
    });
    hex.addEventListener("input", () => {
      customColors[index] = hex.value;
      const valid = normalizedColor(hex.value);
      if (valid) picker.value = valid;
      updatePalette();
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.disabled = customColors.length === 1;
    remove.setAttribute("aria-label", `Remove custom color ${index + 1}`);
    remove.addEventListener("click", () => {
      customColors.splice(index, 1);
      rebuildCustomColors();
      updatePalette();
      schedule();
    });
    row.append(picker, hex, remove);
    container.appendChild(row);
  });
  byId("add-color").disabled = customColors.length >= 16;
}

function updateLabels() {
  byId("character-count").textContent = `${Array.from(byId("text").value).length} / 10,000`;
}

function zoom() {
  const shell = document.querySelector(".note-shell");
  const value = byId("zoom").value;
  if (value === "fit" || !currentResult) {
    shell.style.width = "100%";
    shell.style.maxWidth = currentResult ? `${currentResult.width}px` : "100%";
  } else {
    shell.style.width = `${currentResult.width * Number(value)}px`;
    shell.style.maxWidth = "none";
  }
}

function schedule() {
  revision += 1;
  clearTimeout(timer);
  controller?.abort();
  updateLabels();
  byId("status").textContent = "Rendering…";
  timer = setTimeout(() => render(revision), 250);
}

function dimension(inputId, unit) {
  const input = byId(inputId);
  if (input.value.trim() === "" || !input.validity.valid || Number(input.value) <= 0) {
    throw new Error(`Enter a positive ${inputId === "font-size" ? "letter size" : inputId}.`);
  }
  return `${input.value}${unit}`;
}

async function render(requestRevision) {
  let payload;
  const requestedUnit = pageUnit;
  try {
    const seed = byId("seed");
    if (seed.value.trim() === "" || !seed.validity.valid) {
      throw new Error("Enter a whole-number seed between 0 and 4,294,967,295.");
    }
    payload = {
      text: byId("text").value,
      options: {
        preset: byId("preset").value,
        palette: selectedPalette(),
        colors: selectedPalette() === "custom" ? customColors : [],
        mode: byId("mode").value,
        width: dimension("width", pageUnit),
        height: byId("auto-height").checked ? null : dimension("height", pageUnit),
        font_size: dimension("font-size", fontUnit),
        background: byId("background").value,
        seed: Number(seed.value),
      },
    };
  } catch (error) {
    showError(error.message);
    return;
  }
  controller = new AbortController();
  try {
    const response = await fetch("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const result = await response.json();
    if (requestRevision !== revision) return;
    if (!response.ok) throw new Error(result.error || "Could not render this note.");
    const nextUrl = URL.createObjectURL(new Blob([result.svg], {
      type: "image/svg+xml;charset=utf-8",
    }));
    const image = new Image();
    image.src = nextUrl;
    try {
      await image.decode();
    } catch {
      URL.revokeObjectURL(nextUrl);
      throw new Error("Could not display this SVG.");
    }
    if (requestRevision !== revision) {
      URL.revokeObjectURL(nextUrl);
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = nextUrl;
    byId("preview").src = previewUrl;
    byId("preview").hidden = false;
    byId("empty-preview").hidden = true;
    currentResult = result;
    byId("seed").value = result.seed;
    byId("error").hidden = true;
    byId("status").textContent = "Ready";
    const decimals = requestedUnit === "px" ? 0 : 2;
    const width = (result.width / factors[requestedUnit]).toFixed(decimals);
    const height = (result.height / factors[requestedUnit]).toFixed(decimals);
    byId("dimensions").textContent = `${width} × ${height} ${requestedUnit}`;
    byId("download").disabled = false;
    zoom();
  } catch (error) {
    if (error.name === "AbortError" || requestRevision !== revision) return;
    showError(error.message === "Failed to fetch"
      ? "The editor is not responding. Check that cutnote gui is still running."
      : error.message);
  }
}

function showError(message) {
  byId("error").textContent = message;
  byId("error").hidden = false;
  byId("status").textContent = currentResult ? "Last successful preview" : "Cannot render";
}

function convertInput(id, oldUnit, newUnit) {
  const input = byId(id);
  if (input.value.trim() === "") return;
  const value = Number(input.value) * factors[oldUnit] / factors[newUnit];
  if (!Number.isFinite(value) || value <= 0) return;
  input.value = Number(value.toPrecision(10));
}

byId("editor").addEventListener("submit", (event) => event.preventDefault());
byId("editor").addEventListener("input", (event) => {
  if (["page-unit", "font-unit"].includes(event.target.id)) return;
  schedule();
});
byId("palette-cards").addEventListener("change", () => {
  if (legacy.includes(selectedPalette())) {
    byId("preset").value = selectedPalette();
  }
  updatePalette();
  schedule();
});
byId("preset").addEventListener("change", () => {
  updatePalette();
  schedule();
});
byId("add-color").addEventListener("click", () => {
  if (customColors.length >= 16) return;
  customColors.push("#000000");
  rebuildCustomColors();
  updatePalette();
  schedule();
});
byId("page-unit").addEventListener("change", () => {
  const nextUnit = byId("page-unit").value;
  convertInput("width", pageUnit, nextUnit);
  convertInput("height", pageUnit, nextUnit);
  pageUnit = nextUnit;
  schedule();
});
byId("font-unit").addEventListener("change", () => {
  const nextUnit = byId("font-unit").value;
  convertInput("font-size", fontUnit, nextUnit);
  fontUnit = nextUnit;
  schedule();
});
byId("auto-height").addEventListener("change", () => {
  byId("height").disabled = byId("auto-height").checked;
  if (!byId("auto-height").checked && !byId("height").value) {
    byId("height").value = Number((297 * factors.mm / factors[pageUnit]).toPrecision(10));
  }
  schedule();
});
document.querySelectorAll("[data-page]").forEach((button) => {
  button.addEventListener("click", () => {
    const pages = { a4: [210, 297], a5: [148, 210], letter: [215.9, 279.4] };
    const [width, height] = pages[button.dataset.page];
    pageUnit = "mm";
    byId("page-unit").value = "mm";
    byId("width").value = width;
    byId("height").value = height;
    byId("auto-height").checked = false;
    byId("height").disabled = false;
    schedule();
  });
});
byId("shuffle").addEventListener("click", () => {
  byId("seed").value = newSeed();
  schedule();
});
byId("reset").addEventListener("click", () => {
  byId("text").value = "Meet me at midnight.";
  byId("preset").value = "newspaper";
  selectPalette("newspaper");
  customColors = ["#ff0000", "#0000ff", "#ffcc00"];
  byId("mode").value = "mixed";
  byId("width").value = 1000;
  byId("height").value = "";
  byId("height").disabled = true;
  byId("auto-height").checked = true;
  byId("font-size").value = 48;
  byId("page-unit").value = pageUnit = "px";
  byId("font-unit").value = fontUnit = "px";
  byId("background").value = "paper";
  byId("seed").value = newSeed();
  byId("zoom").value = "fit";
  rebuildCustomColors();
  updatePalette();
  schedule();
});
byId("zoom").addEventListener("change", zoom);
byId("download").addEventListener("click", () => {
  if (!currentResult) return;
  const url = URL.createObjectURL(new Blob([currentResult.svg], {
    type: "image/svg+xml;charset=utf-8",
  }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `cutnote-${currentResult.seed}.svg`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
window.addEventListener("pagehide", () => {
  controller?.abort();
  if (previewUrl) URL.revokeObjectURL(previewUrl);
});
byId("seed").value = newSeed();
rebuildCustomColors();
updatePalette();
schedule();
