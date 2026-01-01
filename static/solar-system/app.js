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

// ✅ Tone mapping / exposure belongs here (you already had it — just relocated)
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.25; // try 1.15 - 1.6

wrap.appendChild(renderer.domElement);

const scene = new THREE.Scene();

const _v3a = new THREE.Vector3();
const _v3b = new THREE.Vector3();

let moonGroup = null;
let moonPivot = null;

let saturnRings = null;

const camera = new THREE.PerspectiveCamera(55, wrap.clientWidth / wrap.clientHeight, 0.1, 5000);
camera.position.set(0, 180, 360);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 40;
controls.maxDistance = 1500;
controls.target.set(0, 0, 0);
controls.update();


/* -----------------------------------------------------
   Textures
----------------------------------------------------- */
const textureLoader = new THREE.TextureLoader();

function loadPlanetTexture(name) {
  try {
    const tex = textureLoader.load(
      `/static/solar-system/textures/${name.toLowerCase()}.jpg`
    );
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  } catch (e) {
    console.warn(`Texture missing for ${name}`);
    return null;
  }
}

/* -----------------------------------------------------
   Lighting
----------------------------------------------------- */
scene.add(new THREE.AmbientLight(0xffffff, 0.25));

// Sun light (acts like the Sun)
const sunLight = new THREE.PointLight(0xffffff, 4.0, 0, 2);
sunLight.position.set(0, 0, 0);
scene.add(sunLight);

// Soft directional fill (so nightside isn’t pitch black)
const fillLight = new THREE.DirectionalLight(0xffffff, 0.7);
fillLight.position.set(300, 250, 200);
scene.add(fillLight);

// Subtle rim light for separation
const rimLight = new THREE.DirectionalLight(0xffffff, 0.35);
rimLight.position.set(-400, 100, -250);
scene.add(rimLight);


/* -----------------------------------------------------
   Starfield
----------------------------------------------------- */
function makeStarfield() {
  const count = 12000;
  const positions = new Float32Array(count * 3);

  for (let i = 0; i < count; i++) {
    const r = 2200 + Math.random() * 1600;
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
    size: 1.2,
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
makeSun();

/* -----------------------------------------------------
   Helpers
----------------------------------------------------- */
function makeOrbit(radius) {
  const curve = new THREE.EllipseCurve(0, 0, radius, radius, 0, Math.PI * 2);
  const points = curve.getPoints(160).map(p => new THREE.Vector3(p.x, 0, p.y));
  const geom = new THREE.BufferGeometry().setFromPoints(points);
  const mat = new THREE.LineBasicMaterial({ color: 0x6fa8ff, opacity: 0.25, transparent: true });
  const line = new THREE.LineLoop(geom, mat);
  return line;
}

function makePlanet({ name, radius, distance, speed, color, axialTiltDeg = 0, orbitInclinationDeg = 0 }) {

  const texture = loadPlanetTexture(name);

  const material = texture
    ? new THREE.MeshStandardMaterial({
        map: texture,
        roughness: 0.55,
        metalness: 0.0
      })
    : new THREE.MeshStandardMaterial({
        color,
        roughness: 0.6,
        metalness: 0.0
      });

  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 48, 48),
    material
  );

  mesh.userData = {
    name,
    radius,
    distance,
    speed,
    angle: Math.random() * Math.PI * 2,
    spin: 0.25 / Math.max(radius, 1),
    axialTiltDeg,
    orbitInclinationDeg
  };

  // Planet tilt group (axial tilt)
  const group = new THREE.Object3D();
  group.rotation.z = THREE.MathUtils.degToRad(axialTiltDeg); // axial tilt around Z
  group.add(mesh);

  // Orbit group (tilts the ORBIT PLANE once)
  const orbitGroup = new THREE.Object3D();
  orbitGroup.rotation.x = THREE.MathUtils.degToRad(orbitInclinationDeg); // orbit inclination around X
  orbitGroup.add(group);

  scene.add(orbitGroup);

  const orbit = makeOrbit(distance);

  // IMPORTANT: orbit line should live in the same orbitGroup plane
  orbitGroup.add(orbit);

  return { mesh, group, orbitGroup, orbit };

  }

function addSpinMarker(mesh) {
  // Tiny bright dot on the “surface” so rotation is obvious
  const marker = new THREE.Mesh(
    new THREE.SphereGeometry(Math.max(mesh.userData.radius * 0.12, 0.35), 12, 12),
    new THREE.MeshBasicMaterial({ color: 0xffffff })
  );

  // Put it on the +X “equator” of the planet
  marker.position.set(mesh.userData.radius * 1.05, 0, 0);
  mesh.add(marker);
}

/* -----------------------------------------------------
   Moons
----------------------------------------------------- */

function makeMoon({ name, radius, parentMesh, distance, speed, color }) {
  const texture = loadPlanetTexture(name); // optional: moon.jpg if you add it later

  const material = texture
    ? new THREE.MeshStandardMaterial({ map: texture, roughness: 0.55, metalness: 0.0 })
    : new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.0 });

  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 32, 32),
    material
  );

  mesh.userData = {
    name,
    radius,
    distance,
    speed,
    angle: Math.random() * Math.PI * 2,
    parent: parentMesh,
    spin: 0.3
  };

  // ❌ IMPORTANT: do NOT scene.add(mesh) anymore
  // We will attach it to a moon pivot group instead.

  return mesh;
}



/* -----------------------------------------------------
   Planets
----------------------------------------------------- */
const planets = [
  makePlanet({ name: "Mercury", radius: 2.2, distance: 55,  speed: 1.25, color: 0xb7b0a7, axialTiltDeg: 0.03,  orbitInclinationDeg: 7.005 }),
  makePlanet({ name: "Venus",   radius: 5.2, distance: 85,  speed: 0.95, color: 0xd8c08a, axialTiltDeg: 177.4, orbitInclinationDeg: 3.394 }),
  makePlanet({ name: "Earth",   radius: 5.6, distance: 120, speed: 0.80, color: 0x4b83ff, axialTiltDeg: 23.44, orbitInclinationDeg: 0.000 }),
  makePlanet({ name: "Mars",    radius: 3.0, distance: 155, speed: 0.70, color: 0xc46a4a, axialTiltDeg: 25.19, orbitInclinationDeg: 1.850 }),
  makePlanet({ name: "Jupiter", radius: 14,  distance: 230, speed: 0.35, color: 0xd2b08c, axialTiltDeg: 3.13,  orbitInclinationDeg: 1.305 }),
  makePlanet({ name: "Saturn",  radius: 12,  distance: 300, speed: 0.28, color: 0xe0d2a4, axialTiltDeg: 26.73, orbitInclinationDeg: 2.485 }),
  makePlanet({ name: "Uranus",  radius: 9,   distance: 360, speed: 0.20, color: 0x8bd7e5, axialTiltDeg: 97.77, orbitInclinationDeg: 0.773 }),
  makePlanet({ name: "Neptune", radius: 9,   distance: 420, speed: 0.16, color: 0x4f6dff, axialTiltDeg: 28.32, orbitInclinationDeg: 1.770 })
];

// Moon orbital inclination relative to the ecliptic (degrees)
const MOON_INCLINATION = THREE.MathUtils.degToRad(5.145);

// ----- Create Moons -----
const earthObj = planets.find(p => p.mesh.userData.name === "Earth");

const moon = earthObj
  ? (() => {
      // 1) Group that carries the tilt (inclination)
      moonGroup = new THREE.Object3D();
      moonGroup.rotation.x = MOON_INCLINATION;

      // Attach moon system to Earth's *group* so it follows Earth properly
      earthObj.group.add(moonGroup);

      // 2) Pivot that rotates to create the orbit
      moonPivot = new THREE.Object3D();
      moonGroup.add(moonPivot);

      // 3) Create the moon mesh (not added to scene anymore)
      const m = makeMoon({
        name: "Moon",
        radius: 1.6,
        parentMesh: earthObj.mesh, // just for metadata
        distance: 16,
        speed: 2.2,
        color: 0xcfd6df
      });

      // 4) Put the moon at a fixed distance from the pivot
      m.position.set(m.userData.distance, 0, 0);

      // 5) Attach moon to the pivot
      moonPivot.add(m);

      return m;
    })()
  : null;


const moonObj = moon ? { mesh: moon, orbit: null } : null;
const planetMeshes = planets.map(p => p.mesh);
if (moon) planetMeshes.push(moon);

/* -----------------------------------------------------
   Rings (Particle version)
----------------------------------------------------- */

function addSaturnRingsParticles(saturnMesh) {
  const r = saturnMesh.userData.radius || 12;

  // Real-ish ratios: outer radius ~2.3x planet radius
  const inner = r * 1.25;   // ~D ring region (stylised)
  const outer = r * 2.30;   // closer to real outer edge

  // Cassini Division (gap between B and A rings)
  const cassiniInner = r * 1.72;
  const cassiniOuter = r * 1.87;

  const count = 90000; // 60k–150k is a good range (perf dependent)

  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const sizes = new Float32Array(count);

  // Helper: weighted band sampling so we get visible "ring structure"
  // We'll bias towards certain radial bands to look more realistic.
  function sampleRadius() {
    const u = Math.random();

    // Band weights (tweak these if you want)
    if (u < 0.18) return THREE.MathUtils.lerp(inner, r * 1.55, Math.random());     // C
    if (u < 0.62) return THREE.MathUtils.lerp(r * 1.55, r * 1.72, Math.random()); // B
    return THREE.MathUtils.lerp(r * 1.87, outer, Math.random());                  // A

  }

  function smoothstep01(x, edge) {
    const t = THREE.MathUtils.clamp(1.0 - x / edge, 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
  }

  let i = 0;
  while (i < count) {
    const rad = sampleRadius();

    // Enforce Cassini gap (extra safety in case sampling lands inside)
    if (rad > cassiniInner && rad < cassiniOuter) continue;

    const theta = Math.random() * Math.PI * 2;

    // Small thickness: rings are extremely thin IRL, but we need a tiny visual thickness
    const thickness = r * 0.012;
    const y = (Math.random() - 0.5) * thickness;

    const x = Math.cos(theta) * rad;
    const z = Math.sin(theta) * rad;

    const p3 = i * 3;
    positions[p3 + 0] = x;
    positions[p3 + 1] = y;
    positions[p3 + 2] = z;

    // Color: mostly icy white with slight warm tint + radial variation
    const t = (rad - inner) / (outer - inner);
    const base = 0.85 + 0.15 * Math.random(); // 0.85..1.0

    // Softer "grain" so it isn't perfectly flat
    const bandNoise = 0.92 + 0.08 * Math.sin(t * Math.PI * 10.0 + Math.random() * 0.3);

    // Add a couple of ring bands (thin darker stripes)
    const band1 = smoothstep01(Math.abs(t - 0.18), 0.03);
    const band2 = smoothstep01(Math.abs(t - 0.55), 0.02);
    const bandBoost = 1.0 - 0.10 * band1 - 0.18 * band2;

    const c = base * bandNoise * bandBoost;

    // Warm-ish tint (tiny)
    colors[p3 + 0] = c * 1.00; // R
    colors[p3 + 1] = c * 0.98; // G
    colors[p3 + 2] = c * 0.92; // B

    // Size: mix of dust and chunks
    // sizeAttenuation makes these shrink with distance (good)
    const chunk = Math.random() < 0.12; // 12% bigger chunks
    sizes[i] = chunk ? (1.8 + Math.random() * 1.4) : (0.6 + Math.random() * 0.9);

    i++;
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geom.setAttribute("size", new THREE.BufferAttribute(sizes, 1));

  // Shader so we can use per-particle size attribute
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

        // Distance from camera (positive)
         float dist = -mvPosition.z;

        // Fade out when far away (tweak these numbers)
        float fadeStart = 700.0;
        float fadeEnd   = 1700.0;
        vFade = 1.0 - smoothstep(fadeStart, fadeEnd, dist);

        // size attenuation
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

        // soft round particles
        float alpha = smoothstep(0.25, 0.0, d);

        gl_FragColor = vec4(vColor, alpha * uOpacity * vFade);
      }
  `
  });

  const points = new THREE.Points(geom, mat);

  // Group lets us tilt the rings to Saturn's equator AND rotate them slowly
  const group = new THREE.Object3D();

  group.rotation.z = 0;

  group.add(points);

  // Attach to Saturn so it follows Saturn around
  saturnMesh.add(group);

  // Make raycasting ignore rings (so clicks still hit Saturn)
  points.raycast = () => {};

  return { group, points };
}

// ----- Saturn Rings (Particle) attach -----
const saturnObj = planets.find(p => p.mesh.userData.name === "Saturn");
if (saturnObj) {
  saturnRings = addSaturnRingsParticles(saturnObj.mesh);
}


/* -----------------------------------------------------
   Labels (HTML overlay)
----------------------------------------------------- */
const stage = document.querySelector(".solar-stage") || document.body;
const labelEls = new Map(); // mesh.uuid -> div

function createLabelForPlanet(p) {
  const el = document.createElement("div");
  el.className = "planet-label";
  el.textContent = p.mesh.userData.name;

  // Make it focusable + clickable
  el.tabIndex = 0;
  el.setAttribute("role", "button");
  el.setAttribute("aria-label", `Focus ${p.mesh.userData.name}`);

  // Keep a reference to the planet object
  el.__body = p;

  const activate = () => {
    setSelected(p);
    focusOn(p.mesh); // same focus behavior as clicking the planet
  };

  el.addEventListener("click", (e) => {
    e.stopPropagation(); // don’t let it count as a canvas click
    activate();
  });

  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      activate();
    }
  });

  stage.appendChild(el);
  labelEls.set(p.mesh.uuid, el);
}

for (const p of planets) createLabelForPlanet(p);
if (moonObj) createLabelForPlanet(moonObj);

const toggleLabels = document.getElementById("toggleLabels");
let labelsOn = toggleLabels ? toggleLabels.checked : true;

toggleLabels?.addEventListener("change", (e) => {
  labelsOn = e.target.checked;
  for (const el of labelEls.values()) {
    el.style.display = labelsOn ? "" : "none";
  }
});

// set initial label visibility
for (const el of labelEls.values()) {
  el.style.display = labelsOn ? "" : "none";
}

function updateLabels() {
  if (!labelsOn) return;

  const rect = renderer.domElement.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;

  for (const p of planets) {
    const el = labelEls.get(p.mesh.uuid);
    if (!el) continue;

    // Get world position of planet, project to screen
    p.mesh.getWorldPosition(_v3a);
    const v = _v3a.clone().project(camera);


    // If behind camera, hide
    if (v.z > 1) {
      el.style.display = "none";
      continue;
    }

    const x = (v.x * 0.5 + 0.5) * w;
    const y = (-v.y * 0.5 + 0.5) * h;

    // Hide if offscreen (with small padding)
    const pad = 20;
    if (x < -pad || x > w + pad || y < -pad || y > h + pad) {
      el.style.display = "none";
      continue;
    }

    // Ensure visible (if toggled on)
    if (el.style.display === "none") el.style.display = "";

    // Place label over the canvas
    // Because labels are in .solar-stage, we position relative to the canvas rect offset:
    el.style.left = `${rect.left + x}px`;
    el.style.top = `${rect.top + y}px`;
    el.style.transform = "translate(-50%, -140%)";
  }

    if (moonObj) {
    const el = labelEls.get(moonObj.mesh.uuid);
    if (el) {
      moonObj.mesh.getWorldPosition(_v3a);
      const v = _v3a.clone().project(camera);

      if (v.z > 1) {
        el.style.display = "none";
      } else {
        const x = (v.x * 0.5 + 0.5) * w;
        const y = (-v.y * 0.5 + 0.5) * h;

        const pad = 20;
        if (x < -pad || x > w + pad || y < -pad || y > h + pad) {
          el.style.display = "none";
        } else {
          if (el.style.display === "none") el.style.display = "";
          el.style.left = `${rect.left + x}px`;
          el.style.top = `${rect.top + y}px`;
        }
      }
    }
  }

}


/* -----------------------------------------------------
   UI
----------------------------------------------------- */
const toggleOrbits = document.getElementById("toggleOrbits");
toggleOrbits?.addEventListener("change", e => {
  for (const p of planets) p.orbit.visible = e.target.checked;
});
if (toggleOrbits) {
  for (const p of planets) p.orbit.visible = toggleOrbits.checked;
}

const timeSpeed = document.getElementById("timeSpeed");
let timeScale = timeSpeed ? Number(timeSpeed.value) : 1;
timeSpeed?.addEventListener("input", e => (timeScale = Number(e.target.value)));

if (timeSpeed) {
  timeSpeed.value = timeScale;
}

const selName = document.getElementById("selName");
const selMeta = document.getElementById("selMeta");
const btnFocus = document.getElementById("btnFocus");
const btnReset = document.getElementById("btnReset");
const btnClose = document.getElementById("btnClose");
const panel = document.querySelector(".solar-panel");

btnReset?.addEventListener("click", () => resetView());
btnClose?.addEventListener("click", () => {
  if (!panel) return;
  panel.style.display = (panel.style.display === "none") ? "" : "none";
});

/* -----------------------------------------------------
   Selection + Focus
----------------------------------------------------- */
let selected = null;
let focusTween = null;
let followMode = false;
let followOffset = new THREE.Vector3(0, 0, 0);
let followAllowUserControl = true;

function setSelected(planetObjOrNull) {
  // remove highlight from previous
  if (selected?.mesh) selected.mesh.scale.setScalar(1);

  selected = planetObjOrNull;

  followMode = false;
  focusTween = null;

  if (!selected) {
    if (selName) selName.textContent = "Select a body";
    if (selMeta) {
      selMeta.textContent =
        "Click a planet to focus the camera and show details here.\n\n" +
        "• Focus: follow this body\n" +
        "• Reset: stop following";
    }
    return;
  }


  // highlight new
  selected.mesh.scale.setScalar(1.12);

  if (selName) selName.textContent = selected.mesh.userData.name;

  if (selMeta) {
    const d = selected.mesh.userData.distance;
    const r = selected.mesh.userData.radius;
    const sp = selected.mesh.userData.speed;
    selMeta.textContent =
      `Stylised values (for visuals):\n` +
      `• Radius: ${r}\n` +
      `• Orbit distance: ${d}\n` +
      `• Orbit speed: ${sp}\n\n` +
      `Tip: click Focus to snap the camera to ${selected.mesh.userData.name}.`;
  }
}

function resetView() {
  followMode = false;
  focusTween = null;
  selected = null;
  controls.target.set(0, 0, 0);
  camera.position.set(0, 180, 360);
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

  // Direction from origin towards planet (fallback if too small)
  let dir = target.clone().normalize();
  if (dir.lengthSq() < 1e-6) dir = new THREE.Vector3(1, 0, 0);

  const planetRadius = mesh.userData.radius || 5;
  const camDist = Math.max(planetRadius * 10, 55);

  // Desired camera position
  const desiredPos = target.clone()
    .add(dir.clone().multiplyScalar(camDist))
    .add(new THREE.Vector3(0, camDist * 0.35, 0));

  // This is the key: offset from planet -> camera
  followOffset.copy(desiredPos).sub(target);

  // Tween into position, then we’ll “lock” followMode on
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
  // Ignore if user is dragging a lot (OrbitControls)
  // We'll still keep it simple: small movement threshold
  updatePointerFromEvent(ev);
  raycaster.setFromCamera(pointer, camera);

  const hits = raycaster.intersectObjects(planetMeshes, false);
  if (!hits.length) return;

  const hitMesh = hits[0].object;
  const hitPlanet = planets.find(p => p.mesh === hitMesh) || null;

  if (hitPlanet) {
    setSelected(hitPlanet);
  } else if (moonObj && hitMesh === moonObj.mesh) {
    setSelected(moonObj);
  }

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

function animate() {
  const dt = clock.getDelta();

  // subtle star drift
  stars.rotation.y += dt * 0.01;

  for (const p of planets) {
    p.mesh.userData.angle += p.mesh.userData.speed * dt * timeScale;

    // orbit position is now inside the orbitGroup plane (local space)
    const x = Math.cos(p.mesh.userData.angle) * p.mesh.userData.distance;
    const z = Math.sin(p.mesh.userData.angle) * p.mesh.userData.distance;

    // move the planet's tilt-group along the orbit (Y stays 0 in local orbit plane)
    p.group.position.set(x, 0, z);

    // self-rotation (axial spin)
    p.mesh.rotation.y += (p.mesh.userData.spin || 0.1) * dt * timeScale;
  }

  // Moon motion (runs once per frame)
  if (moon && moonPivot) {
    // orbit by rotating the pivot
    moonPivot.rotation.y += moon.userData.speed * dt * timeScale;

    // self-rotation
    moon.rotation.y += (moon.userData.spin || 0.15) * dt * timeScale;
  }

 // Saturn ring rotation (subtle)
 if (saturnRings?.group) {
   saturnRings.group.rotation.y += dt * 0.15 * timeScale;
 }


  // camera focus tween
  if (focusTween) {
    focusTween.t += dt / focusTween.duration;
    const t = Math.min(Math.max(focusTween.t, 0), 1);
    const e = t * t * (3 - 2 * t);

    camera.position.lerpVectors(focusTween.fromPos, focusTween.toPos, e);
    controls.target.lerpVectors(focusTween.fromTarget, focusTween.toTarget, e);

    if (t >= 1) {
      // After tween, set initial offset from the final snapped view
      followOffset.copy(camera.position).sub(controls.target);
      focusTween = null;
    }

  }

  // follow selected planet (locked target, BUT user can pan/zoom)
  if (followMode && selected?.mesh && !focusTween) {
    selected.mesh.getWorldPosition(_v3b);
    const target = _v3b;
  
    // Track how the user has moved the camera relative to the current target
    // (this changes when they zoom/pan/orbit)
    if (followAllowUserControl) {
      followOffset.copy(camera.position).sub(controls.target);
    }
  
    // Move the target with the planet...
    controls.target.copy(target);
  
    // ...and keep the same relative camera offset
    camera.position.copy(target).add(followOffset);
  }


  controls.update();
  updateLabels();
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}

animate();
setSelected(null);

console.log("🌌 Solar System running (click planets to select)");
