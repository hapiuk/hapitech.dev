// static/solar-system/app.js
import * as THREE from "three";
import { OrbitControls } from "https://unpkg.com/three@0.160.0/examples/jsm/controls/OrbitControls.js";

/* -----------------------------------------------------
   Setup
----------------------------------------------------- */
const wrap = document.getElementById("solar-canvas-wrap");
if (!wrap) throw new Error("Missing #solar-canvas-wrap");

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setSize(wrap.clientWidth, wrap.clientHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;

renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.25;

wrap.appendChild(renderer.domElement);

const scene = new THREE.Scene();

const _v3a = new THREE.Vector3();
const _v3b = new THREE.Vector3();

let saturnRings = null;

const camera = new THREE.PerspectiveCamera(55, wrap.clientWidth / wrap.clientHeight, 0.1, 20000);
camera.position.set(0, 500, 1200);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 25;
controls.maxDistance = 12000;
controls.target.set(0, 0, 0);
controls.update();

/* -----------------------------------------------------
   Textures
----------------------------------------------------- */
const _texCache = new Map();

function loadPlanetTexture(name) {
  if (!name) return null;

  const key = String(name).toLowerCase();
  if (_texCache.has(key)) return _texCache.get(key);

  // Create the texture immediately so materials can reference it
  const tex = new THREE.Texture();
  tex.colorSpace = THREE.SRGBColorSpace;
  _texCache.set(key, tex);

  // --- Procedural fallback generator (deterministic per name) ---
  function hashString(str) {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function makeRng(seed) {
    // Mulberry32
    let t = seed >>> 0;
    return function () {
      t += 0x6D2B79F5;
      let r = Math.imul(t ^ (t >>> 15), 1 | t);
      r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
      return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
    };
  }

  function clamp01(x) { return Math.min(1, Math.max(0, x)); }

  function hexToRgb(hex) {
    const h = hex.replace("#", "");
    const n = parseInt(h.length === 3 ? h.split("").map(c => c + c).join("") : h, 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }

  function lerp(a, b, t) { return a + (b - a) * t; }

  function mixRgb(c1, c2, t) {
    return {
      r: Math.round(lerp(c1.r, c2.r, t)),
      g: Math.round(lerp(c1.g, c2.g, t)),
      b: Math.round(lerp(c1.b, c2.b, t)),
    };
  }

  function pickPalette(body) {
    // Basic “vibe” palettes for some famous moons
    const palettes = {
      io:        ["#d6b23a", "#b86a1f", "#f2d36b"], // sulphur-ish
      europa:    ["#e9eef2", "#b9cde1", "#f7f9fb"], // icy
      ganymede:  ["#7b6f63", "#4a4038", "#a69b90"], // rocky/gray-brown
      callisto:  ["#4b3f37", "#2b2622", "#6a5b52"], // dark cratered
      titan:     ["#c9782c", "#7a3f1b", "#e3a15a"], // orange haze
      triton:    ["#b8d8e6", "#5aa3c6", "#e8f4fb"], // icy blue
      phobos:    ["#6a615b", "#3a3431", "#8b817a"],
      deimos:    ["#7a6f67", "#463f3a", "#9c9188"],
      enceladus: ["#f3f7fb", "#cfe3f2", "#ffffff"],
      rhea:      ["#c7cbd2", "#8c919a", "#e3e6eb"],
      dione:     ["#d3d7df", "#9097a3", "#f1f3f7"],
      tethys:    ["#e3e8ef", "#aab1bd", "#ffffff"],
      iapetus:   ["#cfc6b8", "#2d2621", "#f0eadf"], // two-tone-ish
      miranda:   ["#a6a0a7", "#6f6a73", "#d6d0d9"],
      ariel:     ["#c9d4df", "#8698ab", "#eef3f8"],
      umbriel:   ["#3a3740", "#1f1d23", "#5b5663"],
      titania:   ["#c1c6cf", "#7b8390", "#e7eaef"],
      oberon:    ["#7d736c", "#3a3532", "#a59b92"],
      moon:      ["#b9b9b9", "#6c6c6c", "#e5e5e5"],
      default:   ["#9aa3ad", "#4f5964", "#cfd6df"],
    };

    return palettes[body] || palettes.default;
  }

  function generatePlaceholderTexture(bodyName) {
    const seed = hashString(bodyName);
    const rnd = makeRng(seed);

    const w = 512, h = 256; // equirectangular-ish
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const ctx = c.getContext("2d", { willReadFrequently: false });

    const body = bodyName.toLowerCase();
    const palHex = pickPalette(body);
    const p0 = hexToRgb(palHex[0]);
    const p1 = hexToRgb(palHex[1]);
    const p2 = hexToRgb(palHex[2] || palHex[0]);

    // Base gradient
    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, `rgb(${p2.r},${p2.g},${p2.b})`);
    g.addColorStop(1, `rgb(${p1.r},${p1.g},${p1.b})`);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);

    // Soft noise bands
    for (let y = 0; y < h; y++) {
      const t = y / (h - 1);
      const band = (Math.sin(t * Math.PI * (2 + rnd() * 4) + rnd() * 10) * 0.5 + 0.5);
      const m = mixRgb(p0, p2, band * 0.6);
      ctx.fillStyle = `rgba(${m.r},${m.g},${m.b},0.18)`;
      ctx.fillRect(0, y, w, 1);
    }

    // Craters / spots
    const craterCount = 80 + Math.floor(rnd() * 120);
    for (let i = 0; i < craterCount; i++) {
      const x = rnd() * w;
      const y = rnd() * h;
      const r = 2 + rnd() * 18;

      const shade = rnd();
      const dark = mixRgb(p1, { r: 0, g: 0, b: 0 }, 0.7);
      const light = mixRgb(p2, { r: 255, g: 255, b: 255 }, 0.25);

      // crater shadow
      ctx.beginPath();
      ctx.arc(x + r * 0.18, y + r * 0.12, r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${dark.r},${dark.g},${dark.b},${0.18 + shade * 0.18})`;
      ctx.fill();

      // crater rim
      ctx.beginPath();
      ctx.arc(x, y, r * 0.9, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(${light.r},${light.g},${light.b},0.25)`;
      ctx.lineWidth = Math.max(1, r * 0.08);
      ctx.stroke();

      // crater core
      ctx.beginPath();
      ctx.arc(x, y, r * 0.75, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${p0.r},${p0.g},${p0.b},0.15)`;
      ctx.fill();
    }

    // Iapetus: add a darker hemisphere for fun
    if (body === "iapetus") {
      ctx.fillStyle = "rgba(0,0,0,0.25)";
      ctx.fillRect(0, 0, w * 0.48, h);
    }

    // Return canvas for texture patching
    return c;
  }

  // Attempt to load file texture; if it fails, patch tex.image with generated canvas
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    tex.image = img;
    tex.needsUpdate = true;
  };
  img.onerror = () => {
    console.warn(`⚠️ Missing texture: /static/solar-system/textures/${key}.jpg — using generated placeholder`);
    const canvas = generatePlaceholderTexture(key);
    tex.image = canvas;
    tex.needsUpdate = true;
  };
  img.src = `/static/solar-system/textures/${key}.jpg`;

  return tex;
}

/* -----------------------------------------------------
   Real-time orbit helpers (Kepler)
----------------------------------------------------- */
const DEG = Math.PI / 180;
const AU_TO_UNITS = 200; // 1 AU => 200 units (scaled orbits)

// "True Scale" mode — real relative sizes, using the SAME km-to-units
// conversion as orbital distances (so this is genuinely physically
// consistent, not just a nicer-looking fudge). Fair warning: this makes
// Earth about the size of a large pixel next to its own 200-unit orbit —
// that's not a bug, it's the actual, famously humbling scale of the solar
// system. Scoped to Sun + planets + the Moon for now, not the other moons.
const KM_PER_AU = 149597870.7;
const KM_TO_UNITS = AU_TO_UNITS / KM_PER_AU;
const TRUE_SCALE_RADII = {
  Sun: 696340 * KM_TO_UNITS,
  Mercury: 2439.7 * KM_TO_UNITS,
  Venus: 6051.8 * KM_TO_UNITS,
  Earth: 6371.0 * KM_TO_UNITS,
  Mars: 3389.5 * KM_TO_UNITS,
  Jupiter: 69911 * KM_TO_UNITS,
  Saturn: 58232 * KM_TO_UNITS,
  Uranus: 25362 * KM_TO_UNITS,
  Neptune: 24622 * KM_TO_UNITS,
  Moon: 1737.4 * KM_TO_UNITS
};

let trueScaleEnabled = false;

function setBodyRadius(mesh, radius, segments = 48) {
  if (!mesh || !Number.isFinite(radius) || radius <= 0) return;
  mesh.geometry.dispose();
  mesh.geometry = new THREE.SphereGeometry(radius, segments, segments);
}

function daysSinceJ2000(msUtc) {
  const J2000 = Date.UTC(2000, 0, 1, 12, 0, 0); // 2000-01-01 12:00 UTC
  return (msUtc - J2000) / 86400000;
}

function normRad(a) {
  a = a % (Math.PI * 2);
  return a < 0 ? a + Math.PI * 2 : a;
}

// Kepler's equation: E - e*sin(E) = M
function solveKepler(M, e) {
  M = normRad(M);
  let E = e < 0.8 ? M : Math.PI;
  for (let k = 0; k < 8; k++) {
    const f = E - e * Math.sin(E) - M;
    const fp = 1 - e * Math.cos(E);
    E -= f / fp;
  }
  return E;
}

// Orbital elements -> heliocentric position (scene coords)
function orbitPositionScene(el, days) {
  const n = (2 * Math.PI) / el.period_days; // rad/day
  const M = (el.M0_deg * DEG) + n * days;
  const E = solveKepler(M, el.e);

  const cosE = Math.cos(E), sinE = Math.sin(E);
  const r = el.a_AU * (1 - el.e * cosE);

  const nu = Math.atan2(Math.sqrt(1 - el.e * el.e) * sinE, cosE - el.e);

  // orbital plane (perifocal)
  const xOrb = r * Math.cos(nu);
  const yOrb = r * Math.sin(nu);

  const Ω = el.Omega_deg * DEG;
  const i = el.i_deg * DEG;
  const ω = el.omega_deg * DEG;

  const cosΩ = Math.cos(Ω), sinΩ = Math.sin(Ω);
  const cosi = Math.cos(i), sini = Math.sin(i);
  const cosω = Math.cos(ω), sinω = Math.sin(ω);

  // rotate by ω
  const x1 = xOrb * cosω - yOrb * sinω;
  const y1 = xOrb * sinω + yOrb * cosω;

  // rotate by i
  const x2 = x1;
  const y2 = y1 * cosi;
  const z2 = y1 * sini;

  // rotate by Ω
  const x = x2 * cosΩ - y2 * sinΩ;
  const y = x2 * sinΩ + y2 * cosΩ;
  const z = z2;

  // Map to scene axes: (x, z, y)
  return new THREE.Vector3(x * AU_TO_UNITS, z * AU_TO_UNITS, y * AU_TO_UNITS);
}

/* -----------------------------------------------------
   Moons (Keplerian, data-driven)
----------------------------------------------------- */

// Keep Moon @ ~16 units like before.
// 384,400 km (Earth–Moon avg) => 16 units
const MOON_KM_TO_UNITS = 16 / 384400;
const MOON_PARENT_SCALE = new Map(); // parentNameLower -> scale multiplier

// Local (planet-centered) Kepler position. Returns Vector3 in parent-local scene axes.
function orbitPositionLocal(el, days, distScale = 1) {
  // Bodies whose orbital elements are epoched somewhere other than J2000
  // (currently just the Moon, re-epoched to 2026-01-01 for accuracy around
  // the present era) carry epoch_offset_days = days from J2000 to their
  // own epoch. Everything below is then relative to THAT epoch.
  const effectiveDays = days - (el.epoch_offset_days || 0);

  const n = (2 * Math.PI) / el.period_days; // rad/day
  const dir = (typeof el.orbit_dir === "number") ? el.orbit_dir : 1;
  const M = (el.M0_deg * DEG) + (dir * n * effectiveDays);
  const E = solveKepler(M, el.e);

  const cosE = Math.cos(E), sinE = Math.sin(E);
  const r = (el.a * distScale) * (1 - el.e * cosE);

  const nu = Math.atan2(
    Math.sqrt(1 - el.e * el.e) * sinE,
    cosE - el.e
  );

  // orbital plane (perifocal)
  const xOrb = r * Math.cos(nu);
  const yOrb = r * Math.sin(nu);

  // Secular precession — real moon nodes/apsides shift substantially over
  // years (nodal regression ~18.6yr cycle, apsidal advance ~8.85yr cycle).
  // Both default to 0 for bodies that don't need it (i.e. all the planets).
  const OmegaDeg = el.Omega_deg + (el.Omega_dot_deg_per_day || 0) * effectiveDays;
  const omegaDeg = el.omega_deg + (el.omega_dot_deg_per_day || 0) * effectiveDays;

  const Ω = (OmegaDeg ?? 0) * DEG;
  const i = (el.i_deg ?? 0) * DEG;
  const ω = (omegaDeg ?? 0) * DEG;

  const cosΩ = Math.cos(Ω), sinΩ = Math.sin(Ω);
  const cosi = Math.cos(i), sini = Math.sin(i);
  const cosω = Math.cos(ω), sinω = Math.sin(ω);

  // rotate by ω
  const x1 = xOrb * cosω - yOrb * sinω;
  const y1 = xOrb * sinω + yOrb * cosω;

  // rotate by i
  const x2 = x1;
  const y2 = y1 * cosi;
  const z2 = y1 * sini;

  // rotate by Ω
  const x = x2 * cosΩ - y2 * sinΩ;
  const y = x2 * sinΩ + y2 * cosΩ;
  const z = z2;

  // SAME mapping as everything else: (x, z, y)
  return new THREE.Vector3(x, z, y);
}

function currentTrueAnomaly(el, days, dir = 1) {
  const n = (2 * Math.PI) / el.period_days;
  const M = (el.M0_deg * DEG) + (dir * n * days);
  const E = solveKepler(M, el.e);
  return Math.atan2(
    Math.sqrt(1 - el.e * el.e) * Math.sin(E),
    Math.cos(E) - el.e
  );
}

// Glowing comet-tail trail for orbit lines — brightest right at the body's
// current position, fading out going backward along its direction of
// travel. Geometry is parameterized by true anomaly swept linearly across
// segments, so "how far behind the current position" maps directly to
// vertex index without needing to touch the actual position math at all.
function updateOrbitTrailColors(line, currentNu, segments, baseColor, dir = 1) {
  if (!line?.geometry?.attributes?.color) return;

  const colors = line.geometry.attributes.color.array;
  const twoPi = Math.PI * 2;
  const currentFrac = (((currentNu % twoPi) + twoPi) % twoPi) / twoPi;
  const trailFrac = 0.32; // fraction of the orbit the glow trail covers

  for (let s = 0; s <= segments; s++) {
    const pointFrac = s / segments;
    // Distance behind the current position, going backward against travel direction.
    let behind = dir >= 0 ? (currentFrac - pointFrac) : (pointFrac - currentFrac);
    behind = ((behind % 1) + 1) % 1;

    const brightness = behind <= trailFrac
      ? Math.pow(1 - behind / trailFrac, 1.6)
      : 0;

    const idx = s * 3;
    colors[idx] = baseColor.r * brightness;
    colors[idx + 1] = baseColor.g * brightness;
    colors[idx + 2] = baseColor.b * brightness;
  }

  line.geometry.attributes.color.needsUpdate = true;
}

function makeMoonOrbitLine(el, distScale = 1, segments = 256) {
  const pts = [];
  for (let s = 0; s <= segments; s++) {
    const nu = (s / segments) * Math.PI * 2;

    const a = el.a * distScale;
    const e = el.e;

    const r = (a * (1 - e * e)) / (1 + e * Math.cos(nu));
    const xOrb = r * Math.cos(nu);
    const yOrb = r * Math.sin(nu);

    const Ω = (el.Omega_deg ?? 0) * DEG;
    const i = (el.i_deg ?? 0) * DEG;
    const ω = (el.omega_deg ?? 0) * DEG;

    const cosΩ = Math.cos(Ω), sinΩ = Math.sin(Ω);
    const cosi = Math.cos(i), sini = Math.sin(i);
    const cosω = Math.cos(ω), sinω = Math.sin(ω);

    const x1 = xOrb * cosω - yOrb * sinω;
    const y1 = xOrb * sinω + yOrb * cosω;

    const x2 = x1;
    const y2 = y1 * cosi;
    const z2 = y1 * sini;

    const x = x2 * cosΩ - y2 * sinΩ;
    const y = x2 * sinΩ + y2 * cosΩ;
    const z = z2;

    pts.push(new THREE.Vector3(x, z, y));
  }

  const geom = new THREE.BufferGeometry().setFromPoints(pts);

  const colors = new Float32Array((segments + 1) * 3);
  geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));

  const mat = new THREE.LineBasicMaterial({
    color: 0xffffff,
    vertexColors: true,
    transparent: true,
    opacity: 1.0,
    blending: THREE.AdditiveBlending,
    depthWrite: false
  });

  const line = new THREE.LineLoop(geom, mat);
  line.frustumCulled = false;
  line.userData.segments = segments;
  line.userData.baseColor = new THREE.Color(0x6fa8ff);
  return line;
}

function makeMoonMesh(m) {
  const texture = loadPlanetTexture(m.name);

  const material = texture
    ? new THREE.MeshStandardMaterial({ map: texture, roughness: 0.55, metalness: 0.0 })
    : new THREE.MeshStandardMaterial({ color: m.color ?? 0xcfd6df, roughness: 0.55, metalness: 0.0 });

  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(m.radius, 28, 28),
    material
  );

  mesh.userData = {
    name: m.name,
    radius: m.radius,
    visualRadius: m.radius,
    trueRadius: TRUE_SCALE_RADII[m.name] ?? m.radius,
    moonEl: null,      // filled in setup
    parentName: m.parent,
    spin: 0.15         // fallback only
  };

  return mesh;
}

// Created moons live here (for clicking + labels + animation)
let moons = [];      // { mesh, parentObj, orbitLine, el, meta }

function applyTrueScale(enabled) {
  trueScaleEnabled = enabled;

  if (sunMesh) {
    const r = enabled ? sunMesh.userData.trueRadius : sunMesh.userData.visualRadius;
    setBodyRadius(sunMesh, r, 48);
    sunMesh.userData.radius = r;
  }

  for (const p of planets) {
    const ud = p.mesh.userData;
    const r = enabled ? ud.trueRadius : ud.visualRadius;
    setBodyRadius(p.mesh, r, 48);
    ud.radius = r;
  }

  for (const m of moons) {
    if (m.mesh.userData.name !== "Moon") continue; // scoped to the Moon only for now
    const ud = m.mesh.userData;
    const r = enabled ? ud.trueRadius : ud.visualRadius;
    setBodyRadius(m.mesh, r, 28);
    ud.radius = r;

    // The orbit line's shape is baked in at a fixed distance scale — an
    // ellipse scales uniformly, so rather than rebuilding the geometry,
    // just scale the whole line to match wherever the Moon's actual
    // position currently is (visual vs true distance).
    if (m.orbitLine) {
      const baseDistScale = MOON_KM_TO_UNITS * (m.parentScale || 1);
      m.orbitLine.scale.setScalar(enabled ? (KM_TO_UNITS / baseDistScale) : 1);
    }
  }

  // The camera's minimum distance needs to track whatever's CURRENTLY
  // focused, not a single blanket value — a blanket "true scale minDistance"
  // would be wrong for, say, true-scale Jupiter vs true-scale Earth, and
  // would go stale if the user toggles without re-focusing afterward.
  if (selected?.mesh) {
    const r = selected.mesh.userData.radius || 5;
    controls.minDistance = Math.max(r * 1.05, 0.00005);
  } else {
    controls.minDistance = enabled ? 0.001 : 25;
  }
}
window.applyTrueScale = applyTrueScale;
let moonMeshes = []; // for raycast + labels + animation

function setupMoonsFromData(data) {
  moons = [];
  moonMeshes = [];

  if (!data?.moons || !Array.isArray(data.moons)) return;

  // --- Compute per-parent visual scaling so moons don't render inside their planet ---
  // Goal: innermost moon orbit radius >= parentRadius * MIN_ORBIT_MULT
  // Was 1.8 — that's barely enough to avoid clipping into the parent, not
  // enough to actually SEE a moon as a separate body (Earth's Moon ended up
  // only ~2.86 Earth-radii out, versus the real ~60). Bumped to give a
  // genuinely visible gap; harmless for any moon system already well
  // separated, since scale only ever increases from the Math.max(1, ...) below.
  const MIN_ORBIT_MULT = 6;

  // Gather moons by parent
  const byParent = new Map(); // parentLower -> [moonMeta...]
  for (const m of data.moons) {
    const parentLower = String(m.parent || "").toLowerCase();
    if (!parentLower) continue;
    if (!byParent.has(parentLower)) byParent.set(parentLower, []);
    byParent.get(parentLower).push(m);
  }

  MOON_PARENT_SCALE.clear();

  for (const [parentLower, list] of byParent.entries()) {
    // Find the planet object for this parent
    const parentObj = planets.find(p => String(p.mesh.userData.name || "").toLowerCase() === parentLower);
    if (!parentObj) continue;

    const parentRadius = Number(parentObj.mesh.userData.radius) || 1;

    // Innermost semi-major axis in km
    const minAkm = Math.min(...list.map(x => Number(x.a_km)).filter(Number.isFinite));
    if (!Number.isFinite(minAkm) || minAkm <= 0) continue;

    // Current visual radius in units using the global km->units factor
    const minUnits = minAkm * MOON_KM_TO_UNITS;

    // If it's already outside, scale = 1, else boost it
    const desiredMinUnits = parentRadius * MIN_ORBIT_MULT;
    const scale = (minUnits > 0) ? Math.max(1, desiredMinUnits / minUnits) : 1;

    MOON_PARENT_SCALE.set(parentLower, scale);
  }

  for (const m of data.moons) {
    const parentObj = planets.find(p => p.mesh.userData.name === m.parent);
    if (!parentObj) continue;

    const mesh = makeMoonMesh(m);

    const el = {
      a: m.a_km,
      e: m.e ?? 0,
      i_deg: m.i_deg ?? 0,
      Omega_deg: m.Omega_deg ?? 0,
      omega_deg: m.omega_deg ?? 0,
      M0_deg: m.M0_deg ?? 0,
      period_days: m.period_days,
      orbit_dir: m.orbit_dir ?? 1,
      epoch_offset_days: m.epoch_offset_days ?? 0,
      Omega_dot_deg_per_day: m.Omega_dot_deg_per_day ?? 0,
      omega_dot_deg_per_day: m.omega_dot_deg_per_day ?? 0
    };

    mesh.userData.moonEl = el;

    // Orbit line local to parent
    const parentLower = String(m.parent || "").toLowerCase();
    const parentScale = MOON_PARENT_SCALE.get(parentLower) || 1;

    const orbitLine = makeMoonOrbitLine(el, MOON_KM_TO_UNITS * parentScale);

    parentObj.orbitAnchor.add(orbitLine);

    // Attach moon to parent's orbital-position anchor — NOT the tilt group,
    // so the moon's orbit doesn't inherit the parent's axial tilt rotation.
    parentObj.orbitAnchor.add(mesh);

    moons.push({ mesh, parentObj, orbitLine, el, meta: m, parentScale });
    moonMeshes.push(mesh);
  }

  // add moons into raycast list
  for (const mm of moonMeshes) planetMeshes.push(mm);
}

/* -----------------------------------------------------
   Lighting
----------------------------------------------------- */
scene.add(new THREE.AmbientLight(0xffffff, 0.25));

const sunLight = new THREE.PointLight(0xffffff, 4.0, 0, 2);
sunLight.position.set(0, 0, 0);
scene.add(sunLight);

const fillLight = new THREE.DirectionalLight(0xffffff, 0.7);
fillLight.position.set(300, 250, 200);
scene.add(fillLight);

const rimLight = new THREE.DirectionalLight(0xffffff, 0.35);
rimLight.position.set(-400, 100, -250);
scene.add(rimLight);

/* -----------------------------------------------------
   Starfield
----------------------------------------------------- */
function makeStarfield() {
  const count = 18000;
  const positions = new Float32Array(count * 3);

  for (let i = 0; i < count; i++) {
    // Neptune ~ 30 AU, so keep stars beyond that
    const base = AU_TO_UNITS * 30;
    const span = AU_TO_UNITS * 25;
    const r = base + Math.random() * span;
    const t = Math.random() * Math.PI * 2;
    const p = Math.acos(2 * Math.random() - 1);

    positions[i * 3 + 0] = r * Math.sin(p) * Math.cos(t);
    positions[i * 3 + 1] = r * Math.cos(p);
    positions[i * 3 + 2] = r * Math.sin(p) * Math.sin(t);
  }

  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(positions, 3));

  const m = new THREE.PointsMaterial({
    color: 0xffffff,
    size: 1.6,
    transparent: true,
    opacity: 0.85,
    depthWrite: false
  });

  const stars = new THREE.Points(g, m);
  scene.add(stars);
  return stars;
}
const stars = makeStarfield();

/* -----------------------------------------------------
   Sun
----------------------------------------------------- */
function makeSun() {
  const sun = new THREE.Mesh(
    new THREE.SphereGeometry(28, 48, 48),
    new THREE.MeshStandardMaterial({
      emissive: 0xffffff,
      emissiveIntensity: 2.2,
      roughness: 0.35,
      metalness: 0.0
    })
  );

  sun.userData = { name: "Sun", visualRadius: 28, trueRadius: TRUE_SCALE_RADII.Sun };

  // Simple glow sprite
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const ctx = c.getContext("2d");

  const g = ctx.createRadialGradient(128, 128, 10, 128, 128, 120);
  g.addColorStop(0, "rgba(255,255,255,.9)");
  g.addColorStop(0.3, "rgba(170,210,255,.35)");
  g.addColorStop(0.6, "rgba(180,120,255,.16)");
  g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 256, 256);

  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;

  const glow = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: tex,
      transparent: true,
      depthWrite: false,
      opacity: 0.95
    })
  );
  glow.scale.set(180, 180, 1);
  sun.add(glow);

  scene.add(sun);
  return sun;
}
const sunMesh = makeSun();

/* -----------------------------------------------------
   Helpers
----------------------------------------------------- */
function makeOrbitFromElements(el, segments = 512) {
  const points = [];
  const a = el.a_AU;
  const e = el.e;
  const Ω = el.Omega_deg * DEG;
  const i = el.i_deg * DEG;
  const ω = el.omega_deg * DEG;

  const cosΩ = Math.cos(Ω), sinΩ = Math.sin(Ω);
  const cosi = Math.cos(i), sini = Math.sin(i);
  const cosω = Math.cos(ω), sinω = Math.sin(ω);

  for (let s = 0; s <= segments; s++) {
    const nu = (s / segments) * Math.PI * 2;

    const r = (a * (1 - e * e)) / (1 + e * Math.cos(nu));
    const xOrb = r * Math.cos(nu);
    const yOrb = r * Math.sin(nu);

    const x1 = xOrb * cosω - yOrb * sinω;
    const y1 = xOrb * sinω + yOrb * cosω;

    const x2 = x1;
    const y2 = y1 * cosi;
    const z2 = y1 * sini;

    const x = x2 * cosΩ - y2 * sinΩ;
    const y = x2 * sinΩ + y2 * cosΩ;
    const z = z2;

    points.push(new THREE.Vector3(
      x * AU_TO_UNITS,
      z * AU_TO_UNITS,
      y * AU_TO_UNITS
    ));
  }

  const geom = new THREE.BufferGeometry().setFromPoints(points);

  const colors = new Float32Array((segments + 1) * 3);
  geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));

  const mat = new THREE.LineBasicMaterial({
    color: 0xffffff,
    vertexColors: true,
    opacity: 1.0,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false
  });

  const line = new THREE.LineLoop(geom, mat);
  line.frustumCulled = false;
  line.userData.segments = segments;
  line.userData.baseColor = new THREE.Color(0x6fa8ff);
  return line;
}

function makePlanet({ name, radius, distance, color, axialTiltDeg = 0, orbitInclinationDeg = 0, orbitEl = null }) {
  const texture = loadPlanetTexture(name);

  const material = texture
    ? new THREE.MeshStandardMaterial({ map: texture, roughness: 0.55, metalness: 0.0 })
    : new THREE.MeshStandardMaterial({ color, roughness: 0.6, metalness: 0.0 });

  const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 48, 48), material);

  mesh.userData = {
    name,
    radius,
    visualRadius: radius,
    trueRadius: TRUE_SCALE_RADII[name] ?? radius,
    distance,
    spin: 0.25 / Math.max(radius, 1), // fallback only
    axialTiltDeg,
    orbitInclinationDeg,
    orbitEl
  };

  // Planet tilt group (axial tilt) — this rotation should apply to the
  // planet's own mesh only, never to anything positioned relative to it.
  const group = new THREE.Object3D();
  group.rotation.z = THREE.MathUtils.degToRad(axialTiltDeg);
  group.add(mesh);

  // Orbital-position anchor — carries ONLY the planet's orbital position,
  // no rotation at all. Moons attach here (not to `group`), so a parent's
  // axial tilt never gets spuriously applied to its moons' orbital
  // positions. This was a real, pre-existing bug: Earth's 23.44° tilt was
  // rotating the Moon's already-correct ecliptic-frame position before
  // this fix, which is why the Moon wasn't lining up for the eclipse even
  // though the underlying orbital elements were right.
  const orbitAnchor = new THREE.Object3D();
  orbitAnchor.add(group);

  // Orbit group:
  // If orbitEl exists, DO NOT tilt orbitGroup — Kepler math already includes inclination.
  const orbitGroup = new THREE.Object3D();
  orbitGroup.rotation.x = orbitEl ? 0 : THREE.MathUtils.degToRad(orbitInclinationDeg);
  orbitGroup.add(orbitAnchor);
  scene.add(orbitGroup);

  // Orbit line:
  const orbit = orbitEl
    ? makeOrbitFromElements(orbitEl)
    : (() => {
        const curve = new THREE.EllipseCurve(0, 0, distance, distance, 0, Math.PI * 2);
        const pts = curve.getPoints(220).map(p => new THREE.Vector3(p.x, 0, p.y));
        const geom = new THREE.BufferGeometry().setFromPoints(pts);
        const mat = new THREE.LineBasicMaterial({ color: 0x6fa8ff, opacity: 0.25, transparent: true });
        return new THREE.LineLoop(geom, mat);
      })();

  scene.add(orbit);

  return { mesh, group, orbitAnchor, orbitGroup, orbit };
}

function makeMoon({ name, radius, parentMesh, distance, color }) {
  const texture = loadPlanetTexture(name);

  const material = texture
    ? new THREE.MeshStandardMaterial({ map: texture, roughness: 0.55, metalness: 0.0 })
    : new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.0 });

  const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 32, 32), material);

  mesh.userData = {
    name,
    radius,
    distance,
    parent: parentMesh,
    spin: 0.3
  };

  return mesh;
}

/* -----------------------------------------------------
   Planets + Moon (loaded from JSON)
----------------------------------------------------- */
let planets = [];
let planetMeshes = [];
let moon = null;
let moonObj = null;

async function loadBodiesAndBuildPlanets() {
  const res = await fetch("/static/solar-system/data/bodies.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load bodies.json (${res.status})`);
  const data = await res.json();

  planets = [];

  for (const b of data.bodies) {
    const p = makePlanet({
      name: b.name,
      radius: b.radius,
      distance: b.a_AU * AU_TO_UNITS, // used only for fallback circle
      color: 0xffffff,
      axialTiltDeg: b.axialTiltDeg ?? 0,
      orbitInclinationDeg: 0,
      orbitEl: b
    });

    planets.push(p);
  }

  planetMeshes = planets.map(p => p.mesh);
  return data;
}

function setupMoon() {
  const earthObj = planets.find(p => p.mesh.userData.name === "Earth");
  if (!earthObj) return;

  moon = makeMoon({
    name: "Moon",
    radius: 1.6,
    parentMesh: earthObj.mesh,
    distance: 16,
    color: 0xcfd6df
  });

  earthObj.group.add(moon);

  moonObj = { mesh: moon, orbit: null };
  planetMeshes.push(moon);
}

/* -----------------------------------------------------
   Rings (Particle version)
----------------------------------------------------- */
function addSaturnRingsParticles(saturnMesh) {
  const r = saturnMesh.userData.radius || 12;

  const inner = r * 1.25;
  const outer = r * 2.30;

  const cassiniInner = r * 1.72;
  const cassiniOuter = r * 1.87;

  const count = 90000;

  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const sizes = new Float32Array(count);

  function sampleRadius() {
    const u = Math.random();
    if (u < 0.18) return THREE.MathUtils.lerp(inner, r * 1.55, Math.random());
    if (u < 0.62) return THREE.MathUtils.lerp(r * 1.55, r * 1.72, Math.random());
    return THREE.MathUtils.lerp(r * 1.87, outer, Math.random());
  }

  function smoothstep01(x, edge) {
    const t = THREE.MathUtils.clamp(1.0 - x / edge, 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
  }

  let i = 0;
  while (i < count) {
    const rad = sampleRadius();
    if (rad > cassiniInner && rad < cassiniOuter) continue;

    const theta = Math.random() * Math.PI * 2;

    const thickness = r * 0.012;
    const y = (Math.random() - 0.5) * thickness;

    const x = Math.cos(theta) * rad;
    const z = Math.sin(theta) * rad;

    const p3 = i * 3;
    positions[p3 + 0] = x;
    positions[p3 + 1] = y;
    positions[p3 + 2] = z;

    const t = (rad - inner) / (outer - inner);
    const base = 0.85 + 0.15 * Math.random();
    const bandNoise = 0.92 + 0.08 * Math.sin(t * Math.PI * 10.0 + Math.random() * 0.3);

    const band1 = smoothstep01(Math.abs(t - 0.18), 0.03);
    const band2 = smoothstep01(Math.abs(t - 0.55), 0.02);
    const bandBoost = 1.0 - 0.10 * band1 - 0.18 * band2;

    const c = base * bandNoise * bandBoost;

    colors[p3 + 0] = c * 1.00;
    colors[p3 + 1] = c * 0.98;
    colors[p3 + 2] = c * 0.92;

    const chunk = Math.random() < 0.12;
    sizes[i] = chunk ? (1.8 + Math.random() * 1.4) : (0.6 + Math.random() * 0.9);

    i++;
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geom.setAttribute("size", new THREE.BufferAttribute(sizes, 1));

  const mat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    vertexColors: true,
    blending: THREE.NormalBlending,
    uniforms: {
      uOpacity: { value: 0.35 },
      uScale: { value: 1.0 }
    },
    vertexShader: `
      attribute float size;
      varying vec3 vColor;
      varying float vFade;
      uniform float uScale;

      void main() {
        vColor = color;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        float dist = -mvPosition.z;

        float fadeStart = 700.0;
        float fadeEnd   = 1700.0;
        vFade = 1.0 - smoothstep(fadeStart, fadeEnd, dist);

        float atten = clamp(1200.0 / dist, 0.0, 3.0);

        gl_PointSize = size * uScale * atten;
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying vec3 vColor;
      varying float vFade;
      uniform float uOpacity;

      void main() {
        vec2 uv = gl_PointCoord.xy - vec2(0.5);
        float d = dot(uv, uv);
        float alpha = smoothstep(0.25, 0.0, d);
        gl_FragColor = vec4(vColor, alpha * uOpacity * vFade);
      }
    `
  });

  const points = new THREE.Points(geom, mat);

  const group = new THREE.Object3D();
  group.add(points);

  saturnMesh.add(group);

  points.raycast = () => {};

  return { group, points };
}

/* -----------------------------------------------------
   Labels (HTML overlay)
----------------------------------------------------- */
const stage = document.querySelector(".solar-stage") || document.body;
const labelEls = new Map(); // mesh.uuid -> div

function createLabelForPlanet(body) {
  // body: { mesh, kind: "planet"|"moon", parentMesh?: THREE.Object3D }
  const mesh = body.mesh;
  const kind = body.kind || "planet";
  const parentMesh = body.parentMesh || null;

  const el = document.createElement("div");
  el.className = `planet-label kind-${kind}`;
  el.textContent = mesh.userData?.name || "Body";

  el.tabIndex = 0;
  el.setAttribute("role", "button");
  el.setAttribute("aria-label", `Focus ${el.textContent}`);

  // store refs for updateLabels()
  el.__body = { mesh, kind, parentMesh };

  const activate = () => {
    selectBodyByMesh(mesh);
    focusOn(mesh);
  };

  el.addEventListener("click", (e) => { e.stopPropagation(); activate(); });
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); }
  });

  stage.appendChild(el);
  labelEls.set(mesh.uuid, el);
}

const toggleLabels = document.getElementById("toggleLabels");
let labelsOn = toggleLabels ? toggleLabels.checked : true;

toggleLabels?.addEventListener("change", (e) => {
  labelsOn = e.target.checked;
  for (const el of labelEls.values()) {
    el.style.display = labelsOn ? "" : "none";
  }
});

function updateLabels() {
  if (!labelsOn) return;

  const rect = renderer.domElement.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;

  // Tuning knobs
  const MOON_SHOW_MAX_CAM_DIST = 2200; // show moon labels when camera is reasonably close
  const MIN_SCREEN_SEPARATION_PX = 26; // hide moon label if too close to parent label on-screen

  // Precompute screen positions for planet meshes (for separation checks)
  const planetScreen = new Map(); // mesh.uuid -> {x,y,visible}
  for (const p of planets) {
    const mesh = p.mesh;
    mesh.getWorldPosition(_v3a);
    const v = _v3a.clone().project(camera);

    const visible = !(v.z > 1);
    if (!visible) {
      planetScreen.set(mesh.uuid, { x: 0, y: 0, visible: false });
      continue;
    }

    const x = (v.x * 0.5 + 0.5) * w;
    const y = (-v.y * 0.5 + 0.5) * h;
    planetScreen.set(mesh.uuid, { x, y, visible: true });
  }

  // Iterate all labels (planets + moons)
  for (const el of labelEls.values()) {
    const info = el.__body;
    const mesh = info?.mesh;
    if (!mesh) continue;

    mesh.getWorldPosition(_v3a);
    const v = _v3a.clone().project(camera);

    // behind camera
    if (v.z > 1) {
      el.style.display = "none";
      continue;
    }

    const x = (v.x * 0.5 + 0.5) * w;
    const y = (-v.y * 0.5 + 0.5) * h;

    // offscreen padding
    const pad = 20;
    if (x < -pad || x > w + pad || y < -pad || y > h + pad) {
      el.style.display = "none";
      continue;
    }

    // --- Moon label gating ---
    if (info.kind === "moon") {
      // hide if too far zoomed out
      const camDist = camera.position.distanceTo(_v3a);
      if (camDist > MOON_SHOW_MAX_CAM_DIST) {
        el.style.display = "none";
        continue;
      }

      // hide if too close to its parent planet on screen
      const parentMesh = info.parentMesh;
      if (parentMesh) {
        const parent = planetScreen.get(parentMesh.uuid);
        if (parent?.visible) {
          const dx = x - parent.x;
          const dy = y - parent.y;
          const sep = Math.hypot(dx, dy);
          if (sep < MIN_SCREEN_SEPARATION_PX) {
            el.style.display = "none";
            continue;
          }
        }
      }
    }

    // show + position
    if (el.style.display === "none") el.style.display = "";
    el.style.left = `${rect.left + x}px`;
    el.style.top = `${rect.top + y}px`;
    el.style.transform = "translate(-50%, -140%)";
  }
}

const toggleOrbits = document.getElementById("toggleOrbits");

toggleOrbits?.addEventListener("change", (e) => {
  const on = e.target.checked;
  for (const p of planets) if (p.orbit) p.orbit.visible = on;
  for (const m of moons) if (m.orbitLine) m.orbitLine.visible = on;
});

/* -----------------------------------------------------
   Sim Time UI (date + play/pause + speed)
----------------------------------------------------- */
const simDate = document.getElementById("simDate");
const simSpeed = document.getElementById("simSpeed");
const btnNow = document.getElementById("btnNow");
const btnPlay = document.getElementById("btnPlay");

const btnBackHour = document.getElementById("btnBackHour");
const btnFwdHour  = document.getElementById("btnFwdHour");
const btnBackDay  = document.getElementById("btnBackDay");
const btnFwdDay   = document.getElementById("btnFwdDay");

let simTimeMs = Date.now();
let simRate = 1;     // seconds of sim time per real second (1 = realtime)
let simPlaying = true;

function toDatetimeLocalValue(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function syncInputsFromSimTime() {
  if (simDate) simDate.value = toDatetimeLocalValue(new Date(simTimeMs));
}

function setSimTimeFromInput() {
  if (!simDate || !simDate.value) return;
  const t = new Date(simDate.value).getTime();
  if (!Number.isFinite(t)) return;
  simTimeMs = t;
  syncInputsFromSimTime();
}

function stepSim(ms) {
  simTimeMs += ms;
  syncInputsFromSimTime();
}

btnNow?.addEventListener("click", () => {
  simTimeMs = Date.now();
  syncInputsFromSimTime();
});

btnPlay?.addEventListener("click", () => {
  simPlaying = !simPlaying;
  btnPlay.textContent = simPlaying ? "Pause" : "Play";
});

simDate?.addEventListener("change", () => {
  setSimTimeFromInput();
});

simSpeed?.addEventListener("change", (e) => {
  const v = Number(e.target.value);
  simRate = Number.isFinite(v) ? v : 1;
  if (simRate === 0) {
    simPlaying = false;
    if (btnPlay) btnPlay.textContent = "Play";
  }
});

btnBackHour?.addEventListener("click", () => stepSim(-3600 * 1000));
btnFwdHour?.addEventListener("click",  () => stepSim( 3600 * 1000));
btnBackDay?.addEventListener("click",  () => stepSim(-86400 * 1000));
btnFwdDay?.addEventListener("click",   () => stepSim( 86400 * 1000));

syncInputsFromSimTime();
if (btnPlay) btnPlay.textContent = simPlaying ? "Pause" : "Play";
if (simSpeed) simSpeed.value = String(simRate);

/* -----------------------------------------------------
   Modals (generic) + Disclaimer modal
----------------------------------------------------- */
const _openModals = []; // stack of modal elements

function isModalOpen(modal) {
  return !!modal && modal.classList.contains("is-open");
}

function openModal(modal) {
  if (!modal) return;
  if (!isModalOpen(modal)) {
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    _openModals.push(modal);
  }
}

function closeModal(modal) {
  if (!modal) return;
  modal.classList.remove("is-open");
  modal.setAttribute("aria-hidden", "true");
  // remove from stack (last match)
  for (let i = _openModals.length - 1; i >= 0; i--) {
    if (_openModals[i] === modal) {
      _openModals.splice(i, 1);
      break;
    }
  }
}

function closeTopModal() {
  const top = _openModals[_openModals.length - 1];
  if (top) closeModal(top);
}

function wireModal(modal) {
  if (!modal) return;
  modal.addEventListener("click", (e) => {
    const close = e.target?.getAttribute?.("data-close");
    if (close) closeModal(modal);
  });
  // prevent click inside panel closing
  const panel = modal.querySelector(".modal__panel");
  panel?.addEventListener("click", (e) => e.stopPropagation());
  // close buttons inside modal
  modal.querySelectorAll("[data-close='1']").forEach(btn => {
    btn.addEventListener("click", () => closeModal(modal));
  });
}

// --- Disclaimer modal wiring ---
const btnDisclaimer = document.getElementById("btnDisclaimer");
const disclaimerModal = document.getElementById("disclaimerModal");
const btnDisclaimerClose = document.getElementById("btnDisclaimerClose");

wireModal(disclaimerModal);

btnDisclaimer?.addEventListener("click", () => openModal(disclaimerModal));
btnDisclaimerClose?.addEventListener("click", () => closeModal(disclaimerModal));

// ESC: close topmost modal if any, else reset view
window.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (_openModals.length) {
    closeTopModal();
    return;
  }
  resetView();
});

/* -----------------------------------------------------
   Selection + Focus
----------------------------------------------------- */
const selName = document.getElementById("selName");
const selMeta = document.getElementById("selMeta");
const journalTitle = document.getElementById("journalTitle");
const journalStatus = document.getElementById("journalStatus");
const journalList = document.getElementById("journalList");
const btnFocus = document.getElementById("btnFocus");
const btnReset = document.getElementById("btnReset");
const btnClose = document.getElementById("btnClose");
const panel = document.querySelector(".solar-panel");

btnReset?.addEventListener("click", () => resetView());
btnClose?.addEventListener("click", () => {
  if (!panel) return;
  panel.style.display = (panel.style.display === "none") ? "" : "none";
});

let selected = null;
let focusTween = null;
let followMode = false;
let followOffset = new THREE.Vector3(0, 0, 0);
let followAllowUserControl = true;

function getPlanetByMesh(mesh) {
  return planets.find(p => p.mesh === mesh) || null;
}
function getMoonByMesh(mesh) {
  return moons.find(m => m.mesh === mesh) || null;
}

function selectBodyByMesh(mesh) {
  const p = getPlanetByMesh(mesh);
  if (p) {
    setSelected({
      kind: "planet",
      mesh: p.mesh,
      orbitEl: p.mesh.userData.orbitEl,
      meta: null
    });
    return;
  }

  const m = getMoonByMesh(mesh);
  if (m) {
    setSelected({
      kind: "moon",
      mesh: m.mesh,
      orbitEl: null,
      moonEl: m.mesh.userData.moonEl,
      meta: m.meta,
      parent: m.parentObj?.mesh?.userData?.name || m.meta?.parent || null
    });
  }
}

function fmtDate(iso){
  try{
    const d = new Date(iso);
    return d.toLocaleString();
  }catch{
    return iso || "";
  }
}

function setJournalStatus(msg){
  if (journalStatus) journalStatus.textContent = msg || "";
}

let _journalLastItems = []; // last rendered items for click-to-open

function renderJournalItems(items, { targetEl = journalList } = {}) {
  if (!targetEl) return;

  _journalLastItems = Array.isArray(items) ? items : [];

  if (!_journalLastItems.length) {
    targetEl.innerHTML = `<div class="journal-empty">No entries yet.</div>`;
    return;
  }

  targetEl.innerHTML = _journalLastItems.map((it, idx) => {
    const title = it.title || "Untitled";
    const body = it.body || "";
    const when = fmtDate(it.created_at);
    const tags = (it.tags && it.tags.length) ? ` • ${it.tags.join(", ")}` : "";
    return `
      <button class="journal-item journal-item--btn" data-jidx="${idx}" type="button">
        <div class="journal-item__title">${escapeHtml(title)}</div>
        <div class="journal-item__meta">${escapeHtml(when)}${escapeHtml(tags)}</div>
        <div class="journal-item__body">${escapeHtml(body)}</div>
      </button>
    `;
  }).join("");

  // click -> open entry modal
  targetEl.querySelectorAll("[data-jidx]").forEach(btn => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.getAttribute("data-jidx"));
      const item = _journalLastItems[idx];
      if (item) openJournalEntry(item);
    });
  });
}

// basic HTML escaping (safe rendering)
function escapeHtml(s){
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function fetchJournalRecent(limit = 10){
  setJournalStatus("Loading…");
  try{
    const res = await fetch(`/api/journal/recent?limit=${encodeURIComponent(limit)}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data?.ok) throw new Error("API returned ok=false");
    renderJournalItems(data.items || []);
    setJournalStatus(`${(data.items || []).length} recent`);
  }catch(e){
    console.warn("Journal recent failed:", e);
    if (journalList) journalList.innerHTML = `<div class="journal-empty">Couldn’t load journal.</div>`;
    setJournalStatus("Error");
  }
}

async function fetchJournalForEntity(kind, name, limit = 25){
  setJournalStatus("Loading…");
  try{
    const qs = new URLSearchParams({
      kind: String(kind || ""),
      name: String(name || ""),
      limit: String(limit)
    });
    const res = await fetch(`/api/journal/entity?${qs.toString()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data?.ok) throw new Error("API returned ok=false");
    renderJournalItems(data.items || []);
    setJournalStatus(`${(data.items || []).length} items`);
  }catch(e){
    console.warn("Journal entity failed:", e);
    if (journalList) journalList.innerHTML = `<div class="journal-empty">Couldn’t load journal.</div>`;
    setJournalStatus("Error");
  }
}

/* -----------------------------------------------------
   Human-readable formatting for Focus UI
----------------------------------------------------- */
const _nf0 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
const _nf1 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });
const _nf2 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const _nf3 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 });

function _fmtNum(x, nf = _nf2) {
  if (x === null || x === undefined) return "—";
  const n = Number(x);
  if (!Number.isFinite(n)) return "—";
  return nf.format(n);
}

function _fmtDeg(x, digits = 1) {
  const nf = digits === 0 ? _nf0 : digits === 1 ? _nf1 : _nf2;
  return `${_fmtNum(x, nf)}°`;
}

function _fmtKm(km, digits = 0) {
  const nf = digits === 0 ? _nf0 : digits === 1 ? _nf1 : _nf2;
  return `${_fmtNum(km, nf)} km`;
}

function _fmtAu(au, digits = 3) {
  const nf = digits === 3 ? _nf3 : _nf2;
  return `${_fmtNum(au, nf)} AU`;
}

function _fmtAuFromKm(km, digits = 3) {
  const n = Number(km);
  if (!Number.isFinite(n)) return "—";
  return _fmtAu(n / KM_PER_AU, digits);
}

function _fmtDays(days) {
  const d = Number(days);
  if (!Number.isFinite(d)) return "—";
  if (d >= 365) return `${_fmtNum(d / 365, _nf2)} years`;
  if (d >= 2) return `${_fmtNum(d, _nf1)} days`;
  return `${_fmtNum(d * 24, _nf1)} hours`;
}

function _fmtHours(hours) {
  const h = Number(hours);
  if (!Number.isFinite(h)) return "—";
  if (h >= 48) return _fmtDays(h / 24);
  return `${_fmtNum(h, _nf1)} hours`;
}

function _tip(name) {
  return `\n\nTip: click Focus to follow ${name}.`;
}

function buildPlanetFocusText(name, ud, el) {
  const lines = [];
  lines.push(`Planet:`);

  // Your "radius" is in scene units (not km), so label it clearly
  if (Number.isFinite(ud?.radius)) lines.push(`• Radius (visual units): ${_fmtNum(ud.radius, _nf2)}`);

  if (Number.isFinite(ud?.axialTiltDeg)) lines.push(`• Axial tilt: ${_fmtDeg(ud.axialTiltDeg)}`);

  if (el) {
    lines.push(``);
    lines.push(`Orbit (Kepler):`);
    if (Number.isFinite(el.a_AU)) lines.push(`• Semi-major axis: ${_fmtAu(el.a_AU)} (${_fmtKm(el.a_AU * KM_PER_AU, 0)})`);
    if (Number.isFinite(el.e)) lines.push(`• Eccentricity: ${_fmtNum(el.e, _nf3)}`);
    if (Number.isFinite(el.i_deg)) lines.push(`• Inclination: ${_fmtDeg(el.i_deg)}`);
    if (Number.isFinite(el.period_days)) lines.push(`• Year length: ${_fmtDays(el.period_days)}`);

    // Rotation
    if (Number.isFinite(el.rot_hours) && el.rot_hours > 0) {
      lines.push(`• Day length: ${_fmtHours(el.rot_hours)}`);
    }
  }

  return lines.join("\n") + _tip(name);
}

function buildMoonFocusText(name, parent, ud, meta, moonEl) {
  const lines = [];
  lines.push(`Moon:`);
  lines.push(`• Orbits: ${parent || "—"}`);

  // Distance a_km
  const aKm =
    Number.isFinite(meta?.a_km) ? meta.a_km :
    Number.isFinite(moonEl?.a) ? moonEl.a :
    null;

  // Orbit period
  const periodDays =
    Number.isFinite(meta?.period_days) ? meta.period_days :
    Number.isFinite(moonEl?.period_days) ? moonEl.period_days :
    null;

  // ecc + inc
  const e =
    Number.isFinite(meta?.e) ? meta.e :
    Number.isFinite(moonEl?.e) ? moonEl.e :
    null;

  const iDeg =
    Number.isFinite(meta?.i_deg) ? meta.i_deg :
    Number.isFinite(moonEl?.i_deg) ? moonEl.i_deg :
    null;

  // rotation
  const rotHours =
    Number.isFinite(meta?.rot_hours) ? meta.rot_hours :
    Number.isFinite(ud?.rot_hours) ? ud.rot_hours :
    null;

  if (aKm !== null) lines.push(`• Orbit distance (a): ${_fmtKm(aKm, 0)} (${_fmtAuFromKm(aKm)})`);
  if (periodDays !== null) lines.push(`• Orbital period: ${_fmtDays(periodDays)}`);
  if (e !== null) lines.push(`• Eccentricity: ${_fmtNum(e, _nf3)}`);
  if (iDeg !== null) lines.push(`• Inclination: ${_fmtDeg(iDeg)}`);
  if (rotHours !== null) lines.push(`• Rotation: ${_fmtHours(rotHours)}`);

  // Visual radius note
  if (Number.isFinite(ud?.radius)) lines.push(`• Radius (visual units): ${_fmtNum(ud.radius, _nf2)}`);

  return lines.join("\n") + _tip(name);
}

/* -----------------------------------------------------
   Journal Modals (browser + entry view + editor)
----------------------------------------------------- */
const btnJournal = document.getElementById("btnJournal");
const btnJournalAdd = document.getElementById("btnJournalAdd");

const journalBrowserModal = document.getElementById("journalBrowserModal");
const journalBrowserList = document.getElementById("journalBrowserList");
const journalBrowserStatus = document.getElementById("journalBrowserStatus");
const journalBrowserContext = document.getElementById("journalBrowserContext");
const btnJournalBrowserAll = document.getElementById("btnJournalBrowserAll");
const btnJournalBrowserThis = document.getElementById("btnJournalBrowserThis");
const btnJournalBrowserGeneral = document.getElementById("btnJournalBrowserGeneral");

const journalEntryModal = document.getElementById("journalEntryModal");
const journalEntryModalTitle = document.getElementById("journalEntryModalTitle");
const journalEntryMeta = document.getElementById("journalEntryMeta");
const journalEntryBody = document.getElementById("journalEntryBody");
const journalEntrySnap = document.getElementById("journalEntrySnap");
const journalEntryImages = document.getElementById("journalEntryImages");
const btnJournalEntryEdit = document.getElementById("btnJournalEntryEdit");

const journalEditorModal = document.getElementById("journalEditorModal");
const journalEditorTitle = document.getElementById("journalEditorTitle");
const journalEditorForm = document.getElementById("journalEditorForm");
const journalEditorStatus = document.getElementById("journalEditorStatus");

const jf_id = document.getElementById("jf_id");
const jf_kind = document.getElementById("jf_kind");
const jf_name = document.getElementById("jf_name");
const jf_parent = document.getElementById("jf_parent");
const jf_snapshot = document.getElementById("jf_snapshot");
const jf_title = document.getElementById("jf_title");
const jf_body = document.getElementById("jf_body");
const jf_tags = document.getElementById("jf_tags");
const jf_images = document.getElementById("jf_images");
const journalEditorContext = document.getElementById("journalEditorContext");

wireModal(journalBrowserModal);
wireModal(journalEntryModal);
wireModal(journalEditorModal);

let _entryCurrentlyOpen = null; // item currently displayed in entry modal

function getSelectionContext() {
  // General if no selection
  if (!selected?.mesh) {
    return { kind: "general", name: "General", parent: "" };
  }
  const ud = selected.mesh.userData || {};
  const name = ud.name || selected.meta?.name || "Unknown";
  const kind = selected.kind || "general";
  const parent =
    (kind === "moon") ? (selected.parent || selected.meta?.parent || ud.parentName || "") : "";
  return { kind, name, parent };
}
window.getSelectionContext = getSelectionContext;

function makeSnapshot() {
  // Captures “current state” you’ll likely want later
  const ctx = getSelectionContext();
  return {
    captured_at: new Date().toISOString(),
    sim: {
      simTimeMs,
      simIso: new Date(simTimeMs).toISOString(),
      simRate,
      simPlaying
    },
    selection: ctx,
    camera: {
      position: { x: camera.position.x, y: camera.position.y, z: camera.position.z },
      target: { x: controls.target.x, y: controls.target.y, z: controls.target.z },
      followMode
    }
  };
}

async function loadBrowserRecent(limit = 200) {
  if (!journalBrowserList) return;
  journalBrowserStatus.textContent = "Loading…";
  journalBrowserList.innerHTML = `<div class="journal-empty">Loading…</div>`;
  try {
    const res = await fetch(`/api/journal/recent?limit=${encodeURIComponent(limit)}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data?.ok) throw new Error("API returned ok=false");

    renderJournalItems(data.items || [], { targetEl: journalBrowserList });
    journalBrowserStatus.textContent = `${(data.items || []).length} entries`;
  } catch (e) {
    console.warn("Journal browser recent failed:", e);
    journalBrowserList.innerHTML = `<div class="journal-empty">Couldn’t load journal.</div>`;
    journalBrowserStatus.textContent = "Error";
  }
}

async function loadBrowserForSelection() {
  const ctx = getSelectionContext();
  if (ctx.kind === "general") {
    journalBrowserContext.textContent = "General entries";
    // If your backend doesn’t support “general” yet, this will return empty — fine for now.
    await loadBrowserGeneral();
    return;
  }
  journalBrowserContext.textContent = `${ctx.kind.toUpperCase()} • ${ctx.name}`;
  await loadBrowserEntity(ctx.kind, ctx.name);
}

async function loadBrowserGeneral() {
  // Uses entity endpoint with kind=general, name=General (simple convention)
  await loadBrowserEntity("general", "General");
}

async function loadBrowserEntity(kind, name, limit = 500) {
  if (!journalBrowserList) return;
  journalBrowserStatus.textContent = "Loading…";
  journalBrowserList.innerHTML = `<div class="journal-empty">Loading…</div>`;
  try {
    const qs = new URLSearchParams({ kind: String(kind || ""), name: String(name || ""), limit: String(limit) });
    const res = await fetch(`/api/journal/entity?${qs.toString()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data?.ok) throw new Error("API returned ok=false");

    renderJournalItems(data.items || [], { targetEl: journalBrowserList });
    journalBrowserStatus.textContent = `${(data.items || []).length} entries`;
  } catch (e) {
    console.warn("Journal browser entity failed:", e);
    journalBrowserList.innerHTML = `<div class="journal-empty">Couldn’t load journal.</div>`;
    journalBrowserStatus.textContent = "Error";
  }
}

function openJournalBrowser(mode = "all") {
  openModal(journalBrowserModal);

  if (mode === "this") {
    loadBrowserForSelection();
    return;
  }
  if (mode === "general") {
    journalBrowserContext.textContent = "General entries";
    loadBrowserGeneral();
    return;
  }
  journalBrowserContext.textContent = "All entries (recent)";
  loadBrowserRecent(250);
}

btnJournal?.addEventListener("click", () => openJournalBrowser("all"));
btnJournalBrowserAll?.addEventListener("click", () => openJournalBrowser("all"));
btnJournalBrowserThis?.addEventListener("click", () => openJournalBrowser("this"));
btnJournalBrowserGeneral?.addEventListener("click", () => openJournalBrowser("general"));

function openJournalEntry(item) {
  _entryCurrentlyOpen = item || null;

  const title = item?.title || "Untitled";
  const when = fmtDate(item?.created_at);
  const tags = (item?.tags && item.tags.length) ? item.tags.join(", ") : "";
  const kind = item?.kind || "";
  const name = item?.name || "";

  journalEntryModalTitle.textContent = `📌 ${title}`;
  journalEntryMeta.textContent = `${when}${tags ? " • " + tags : ""}${(kind && name) ? ` • ${kind}:${name}` : ""}`;
  journalEntryBody.textContent = item?.body || "";

  // Snapshot (if backend returns it)
  const snap = item?.snapshot;
  if (snap) {
    journalEntrySnap.style.display = "";
    journalEntrySnap.textContent = `Snapshot:\n${JSON.stringify(snap, null, 2)}`;
  } else {
    journalEntrySnap.style.display = "none";
    journalEntrySnap.textContent = "";
  }

  // Images (if backend returns URLs)
  const imgs = item?.images;
  if (Array.isArray(imgs) && imgs.length) {
    journalEntryImages.style.display = "";
    journalEntryImages.innerHTML = imgs.map(src => (
      `<a class="journal-img" href="${escapeHtml(src)}" target="_blank" rel="noopener">
        <img src="${escapeHtml(src)}" alt="journal image">
      </a>`
    )).join("");
  } else {
    journalEntryImages.style.display = "none";
    journalEntryImages.innerHTML = "";
  }

  // Enable edit only if an id exists
  const canEdit = !!(item && (item.id || item.entry_id));
  btnJournalEntryEdit.disabled = !canEdit;

  openModal(journalEntryModal);
}

btnJournalEntryEdit?.addEventListener("click", () => {
  if (!_entryCurrentlyOpen) return;
  openJournalEditor({ mode: "edit", item: _entryCurrentlyOpen });
});

function openJournalEditor({ mode = "create", item = null } = {}) {
  const ctx = getSelectionContext();
  const isEdit = mode === "edit";

  journalEditorTitle.textContent = isEdit ? "✏️ Edit entry" : "➕ New entry";
  journalEditorStatus.textContent = "";

  // Fill hidden context
  jf_kind.value = (item?.kind ?? ctx.kind ?? "general");
  jf_name.value = (item?.name ?? ctx.name ?? "General");
  jf_parent.value = (item?.parent ?? ctx.parent ?? "");
  jf_snapshot.value = JSON.stringify(makeSnapshot());

  // Fill fields
  jf_id.value = isEdit ? String(item?.id ?? item?.entry_id ?? "") : "";
  jf_title.value = String(item?.title ?? "");
  jf_body.value = String(item?.body ?? "");
  jf_tags.value = Array.isArray(item?.tags) ? item.tags.join(", ") : String(item?.tags ?? "");

  // File input should be cleared on open
  if (jf_images) jf_images.value = "";

  // Context label
  const ctxLabel =
    (jf_kind.value === "general")
      ? "General"
      : `${jf_kind.value.toUpperCase()} • ${jf_name.value}${jf_parent.value ? ` (Parent: ${jf_parent.value})` : ""}`;
  journalEditorContext.textContent = ctxLabel;

  openModal(journalEditorModal);
}

btnJournalAdd?.addEventListener("click", () => openJournalEditor({ mode: "create" }));

// Submit (create/update)
journalEditorForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  journalEditorStatus.textContent = "Saving…";

  const isEdit = !!jf_id.value;
  const endpoint = isEdit ? "/api/journal/update" : "/api/journal/create";

  try {
    const fd = new FormData();
    fd.set("id", jf_id.value);
    fd.set("kind", jf_kind.value);
    fd.set("name", jf_name.value);
    fd.set("parent", jf_parent.value);
    fd.set("title", jf_title.value);
    fd.set("body", jf_body.value);
    fd.set("tags", jf_tags.value);
    fd.set("snapshot", jf_snapshot.value);

    // images
    const files = jf_images?.files ? Array.from(jf_images.files) : [];
    for (const f of files) fd.append("images", f, f.name);

    const res = await fetch(endpoint, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json().catch(() => null);
    if (data && data.ok === false) throw new Error(data.error || "API returned ok=false");

    journalEditorStatus.textContent = "Saved ✅";
    closeModal(journalEditorModal);

    // Refresh the side panel list for current selection
    if (!selected) fetchJournalRecent(10);
    else {
      const ctx = getSelectionContext();
      if (ctx.kind === "general") fetchJournalRecent(10);
      else fetchJournalForEntity(ctx.kind, ctx.name, 25);
    }

    // Refresh browser modal if open
    if (isModalOpen(journalBrowserModal)) {
      // keep current mode simple: reload recent
      loadBrowserRecent(250);
    }

  } catch (err) {
    console.warn("Journal save failed:", err);
    journalEditorStatus.textContent = `Error: ${err.message || err}`;
  }
});

function setSelected(bodyOrNull) {
  if (selected?.mesh) selected.mesh.scale.setScalar(1);

  selected = bodyOrNull;

  followMode = false;
  focusTween = null;

  // If you want selecting to always reveal the panel:
  if (selected && panel) panel.style.display = "";

  if (!selected) {
    if (selName) selName.textContent = "Select a body";
    if (selMeta) {
      selMeta.textContent =
        "Click a body to show details.\n\n" +
        "• Focus: follow this body\n" +
        "• Reset: stop following\n" +
        "• Time: date + play/pause + rate";
    }
    if (journalTitle) journalTitle.textContent = "Journal";
    fetchJournalRecent(10);
    window.dispatchEvent(new CustomEvent("solarBodySelected", { detail: { kind: "general", name: "General" } }));
    return;
  }

  // Highlight selected
  selected.mesh.scale.setScalar(1.12);

  const ud = selected.mesh.userData || {};
  const name = ud.name || selected.meta?.name || "Unknown";
  if (journalTitle) journalTitle.textContent = `Journal • ${name}`;
  fetchJournalForEntity(selected.kind, name, 25);
  window.dispatchEvent(new CustomEvent("solarBodySelected", { detail: { kind: selected.kind || "general", name } }));

  if (selName) selName.textContent = name;

  // Planet branch (NOW human-readable)
  if (selected.kind === "planet") {
    const el = selected.orbitEl || ud.orbitEl;
    if (selMeta) selMeta.textContent = buildPlanetFocusText(name, ud, el);
    return;
  }

  // Moon branch (NOW human-readable)
  if (selected.kind === "moon") {
    const meta = selected.meta || {};
    const moonEl = selected.moonEl || ud.moonEl || null;
    const parent = selected.parent || meta.parent || ud.parentName || "Unknown";
    if (selMeta) selMeta.textContent = buildMoonFocusText(name, parent, ud, meta, moonEl);
    return;
  }

  // Fallback if kind isn't set (safe)
  if (selMeta) {
    selMeta.textContent =
      `Body:\n` +
      `• Radius: ${ud.radius ?? "—"}\n\n` +
      `Tip: click Focus to follow ${name}.`;
  }
}

function resetView() {
  followMode = false;
  focusTween = null;
  selected = null;
  controls.target.set(0, 0, 0);
  camera.position.set(0, 500, 1200);
  controls.update();
  setSelected(null);
}

btnFocus?.addEventListener("click", () => {
  if (!selected) return;
  focusOn(selected.mesh);
});

function focusOn(mesh) {
  const target = new THREE.Vector3();
  mesh.getWorldPosition(target);

  let dir = target.clone().normalize();
  if (dir.lengthSq() < 1e-6) dir = new THREE.Vector3(1, 0, 0);

  const planetRadius = mesh.userData.radius || 5;

  // Camera minimum distance MUST track whichever body is actually focused —
  // a single blanket value can't work across wildly different scales (a
  // true-scale Earth's radius, ~0.0085 units, is literally smaller than the
  // old flat minDistance floor, which is exactly what let the camera end up
  // inside the sphere: OrbitControls only clamps distance-to-target, it has
  // no collision detection with the mesh's actual surface). Small margin
  // (1.05x) keeps the camera just outside the surface while still allowing
  // a close, immersive zoom — this is also what future HD textures and an
  // ISS-style close-up camera will need.
  controls.minDistance = Math.max(planetRadius * 1.05, 0.00005);

  // The 55-unit floor exists to keep the camera from sitting uncomfortably
  // close to small visual-scale bodies — but it's a fixed absolute value,
  // so in true-scale mode (where even Jupiter is ~0.09 units) it would
  // dominate completely and place the camera nowhere near close enough to
  // actually see anything.
  const camDist = trueScaleEnabled
    ? Math.max(planetRadius * 6, planetRadius + 0.002)
    : Math.max(planetRadius * 10, 55);

  const desiredPos = target.clone()
    .add(dir.clone().multiplyScalar(camDist))
    .add(new THREE.Vector3(0, camDist * 0.35, 0));

  followOffset.copy(desiredPos).sub(target);

  followMode = true;
  focusTween = {
    t: 0,
    duration: 0.65,
    fromPos: camera.position.clone(),
    toPos: desiredPos,
    fromTarget: controls.target.clone(),
    toTarget: target
  };
}

/* -----------------------------------------------------
   Raycasting (click to select)
----------------------------------------------------- */
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

function updatePointerFromEvent(ev) {
  const rect = renderer.domElement.getBoundingClientRect();
  const x = (ev.clientX - rect.left) / rect.width;
  const y = (ev.clientY - rect.top) / rect.height;
  pointer.x = x * 2 - 1;
  pointer.y = -(y * 2 - 1);
}

renderer.domElement.addEventListener("pointerdown", (ev) => {
  updatePointerFromEvent(ev);
  raycaster.setFromCamera(pointer, camera);

  const hits = raycaster.intersectObjects(planetMeshes, false);

  // ✅ Don't clear selection/focus when clicking empty space
  // This lets you keep "follow mode" and rotate the camera while attached.
  if (!hits.length) return;

  selectBodyByMesh(hits[0].object);
});

/* -----------------------------------------------------
   Resize
----------------------------------------------------- */
window.addEventListener("resize", () => {
  const w = wrap.clientWidth;
  const h = wrap.clientHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
});

/* -----------------------------------------------------
   Animate
----------------------------------------------------- */
const clock = new THREE.Clock();
const rotAngle = new Map(); // name -> radians (planet spin accumulator)

// Earth's rotation, anchored to real UTC (GMST) rather than an accumulator —
// this is what lets the Greenwich meridian (and so the UK) actually face the
// correct real-world direction at any given date, including the 2026-08-12
// eclipse, instead of drifting based on how long the sim has been running.
const EARTH_GMST_AT_J2000_DEG = 280.46061837; // Greenwich Mean Sidereal Time at J2000.0
const EARTH_SIDEREAL_RATE_DEG_PER_DAY = 360.98564736629;
// Standard equirectangular Earth textures place Greenwich (0° longitude) at
// the texture's horizontal center. This is the one constant worth nudging if,
// once actually viewed live, the UK isn't quite facing where it should —
// each 1 here shifts the visible prime meridian by 1° of longitude.
const EARTH_TEXTURE_MERIDIAN_OFFSET_DEG = 0;

function earthAbsoluteRotationRad(simDays) {
  const deg = EARTH_GMST_AT_J2000_DEG
    + EARTH_SIDEREAL_RATE_DEG_PER_DAY * simDays
    + EARTH_TEXTURE_MERIDIAN_OFFSET_DEG;
  return normRad(deg * DEG);
}

function animate() {
  const dt = clock.getDelta();

  // subtle star drift
  stars.rotation.y += dt * 0.01;

  // Advance sim clock
  const dSimSeconds = (simPlaying ? simRate : 0) * dt;

  if (dSimSeconds !== 0) {
    simTimeMs += dSimSeconds * 1000;

    // update UI ~4 times/sec, unless user is editing the input
    if ((performance.now() | 0) % 250 < 16) {
      const active = document.activeElement;
      if (active !== simDate) syncInputsFromSimTime();
    }
  }

  const simDays = daysSinceJ2000(simTimeMs);

  // Planets (Kepler orbit + rotation from rot_hours)
  for (const p of planets) {
    const el = p.mesh.userData.orbitEl;
    if (!el) continue;

    const pos = orbitPositionScene(el, simDays);
    p.orbitAnchor.position.copy(pos);

    if (p.orbit?.userData?.segments) {
      const nu = currentTrueAnomaly(el, simDays, 1);
      updateOrbitTrailColors(p.orbit, nu, p.orbit.userData.segments, p.orbit.userData.baseColor, 1);
    }

    if (p.mesh.userData.name === "Earth") {
      p.mesh.rotation.y = earthAbsoluteRotationRad(simDays);
    } else if (Number.isFinite(el.rot_hours) && el.rot_hours > 0) {
      const dir = (el.rot_dir ?? 1);
      const omega = dir * (2 * Math.PI) / (el.rot_hours * 3600); // rad/sec

      const name = p.mesh.userData.name;
      const prev = rotAngle.get(name) ?? 0;
      const next = prev + omega * dSimSeconds;
      rotAngle.set(name, next);

      p.mesh.rotation.y = next;
    } else {
      p.mesh.rotation.y += 0.1 * dt;
    }
  }

  // Moons (Kepler local orbits)
  for (const m of moons) {
    const el = m.mesh.userData.moonEl;
    if (!el) continue;

    // In True Scale mode, distance needs the SAME consistent conversion as
    // everything else, not the compressed visual-mode distance — otherwise
    // a true-to-life-tiny Moon ends up at an inconsistent (relatively much
    // closer) old visual distance, making it an invisible speck regardless
    // of its now-correct size. Scoped to the Moon only, matching the radius
    // scoping above.
    const useTrueDistance = trueScaleEnabled && m.mesh.userData.name === "Moon";
    const scale = m.parentScale || 1;
    const distScale = useTrueDistance ? KM_TO_UNITS : (MOON_KM_TO_UNITS * scale);
    const localPos = orbitPositionLocal(el, simDays, distScale);

    m.mesh.position.copy(localPos);

    if (m.orbitLine?.userData?.segments) {
      const dir = el.orbit_dir ?? 1;
      const nu = currentTrueAnomaly(el, simDays, dir);
      updateOrbitTrailColors(m.orbitLine, nu, m.orbitLine.userData.segments, m.orbitLine.userData.baseColor, dir);
    }

    const mh = m.meta?.rot_hours;
    if (Number.isFinite(mh) && mh > 0) {
      const dir = (m.meta?.rot_dir ?? 1);
      const omega = dir * (2 * Math.PI) / (mh * 3600);
      m.mesh.rotation.y += omega * dSimSeconds;
    }
  }

  // Saturn ring rotation (subtle)
  if (saturnRings?.group) {
    saturnRings.group.rotation.y += dt * 0.15;
  }

  // camera focus tween
  if (focusTween) {
    focusTween.t += dt / focusTween.duration;
    const t = Math.min(Math.max(focusTween.t, 0), 1);
    const e = t * t * (3 - 2 * t);

    camera.position.lerpVectors(focusTween.fromPos, focusTween.toPos, e);
    controls.target.lerpVectors(focusTween.fromTarget, focusTween.toTarget, e);

    if (t >= 1) {
      followOffset.copy(camera.position).sub(controls.target);
      focusTween = null;
    }
  }

  // follow selected body
  if (followMode && selected?.mesh && !focusTween) {
    selected.mesh.getWorldPosition(_v3b);
    const target = _v3b;

    if (followAllowUserControl) {
      followOffset.copy(camera.position).sub(controls.target);
    }

    controls.target.copy(target);
    camera.position.copy(target).add(followOffset);
  }

  controls.update();
  updateLabels();
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}

/* -----------------------------------------------------
   Init (build everything in correct order)
----------------------------------------------------- */
const data = await loadBodiesAndBuildPlanets();

// Add moons (ALL of them) after planets exist
setupMoonsFromData(data);

// Saturn rings attach AFTER planets exist
const saturnObj = planets.find(p => p.mesh.userData.name === "Saturn");
if (saturnObj) saturnRings = addSaturnRingsParticles(saturnObj.mesh);

// Labels AFTER planets/moons exist
for (const p of planets) createLabelForPlanet({ mesh: p.mesh, kind: "planet" });

for (const m of moons) {
  createLabelForPlanet({
    mesh: m.mesh,
    kind: "moon",
    parentMesh: m.parentObj?.mesh || null
  });
}

// Apply initial label visibility
for (const el of labelEls.values()) el.style.display = labelsOn ? "" : "none";

// Apply initial orbit visibility (planet orbits + moon orbits)
if (toggleOrbits) {
  const on = toggleOrbits.checked;
  for (const p of planets) if (p.orbit) p.orbit.visible = on;
  for (const m of moons) if (m.orbitLine) m.orbitLine.visible = on;
}

// True Scale is now the default view.
applyTrueScale(true);

animate();
setSelected(null);

console.log("🌌 Solar System running (real-time Kepler + moons)");