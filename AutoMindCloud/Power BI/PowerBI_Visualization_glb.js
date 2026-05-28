(function (global) {
  "use strict";

  const DEFAULTS = {
    container: null,
    height: 520,
    background: "transparent",
    borderRadius: "14px",

    showBadge: true,
    badgeUrl: "https://raw.githubusercontent.com/artemioadaysolvers/AutoMindCloudExperimental/main/AutoMindCloud/AutoMindCloud2.png",
    badgeWidthPx: 180,
    badgeRightPx: 14,
    badgeBottomPx: 14,
    badgeOpacity: 0.95,

    frontFaceRotX: -1.57079632679,
    frontFaceRotY: 3.14159265359,
    frontFaceRotZ: 0.0,

    autoRotate: true,
    rotationsPerSecond: 0.045,

    targetModelSize: 3.2,
    fitPadding: 1.18,

    maxPixelRatio: 1.0,
    antialias: true,

    threeVersion: "0.181.0"
  };

  let depsPromise = null;

  function cleanBase64(b64) {
    b64 = String(b64 || "").trim();
    return b64.includes(",") ? b64.split(",").pop() : b64;
  }

  function base64ToArrayBuffer(b64) {
    b64 = cleanBase64(b64);

    const bin = atob(b64);
    const len = bin.length;
    const bytes = new Uint8Array(len);

    for (let i = 0; i < len; i++) {
      bytes[i] = bin.charCodeAt(i);
    }

    return bytes.buffer;
  }

  function resolveContainer(container) {
    if (!container) return null;

    if (typeof container === "string") {
      return document.querySelector(container) || document.getElementById(container.replace(/^#/, ""));
    }

    if (container instanceof HTMLElement) {
      return container;
    }

    return null;
  }

  function showError(container, msg) {
    container.innerHTML = "";

    const box = document.createElement("div");
    box.style.cssText = `
      width:100%;
      height:100%;
      display:flex;
      align-items:center;
      justify-content:center;
      box-sizing:border-box;
      padding:16px;
      font-family:Arial,sans-serif;
      color:#991b1b;
      background:#fff1f2;
      border:1px solid #fecdd3;
      border-radius:14px;
      font-weight:700;
      text-align:center;
    `;
    box.textContent = msg;
    container.appendChild(box);
  }

  async function loadDependencies(version) {
    if (!depsPromise) {
      depsPromise = Promise.all([
        import("https://esm.sh/three@" + version),
        import("https://esm.sh/three@" + version + "/examples/jsm/loaders/GLTFLoader.js?deps=three@" + version),
        import("https://esm.sh/three@" + version + "/examples/jsm/loaders/DRACOLoader.js?deps=three@" + version)
      ]).then(function (mods) {
        return {
          THREE: mods[0],
          GLTFLoader: mods[1].GLTFLoader,
          DRACOLoader: mods[2].DRACOLoader
        };
      });
    }

    return depsPromise;
  }

  function addBadge(container, options) {
    if (!options.showBadge) return;

    const badge = document.createElement("img");
    badge.src = options.badgeUrl;
    badge.alt = "AutoMindCloud";

    badge.style.position = "absolute";
    badge.style.right = options.badgeRightPx + "px";
    badge.style.bottom = options.badgeBottomPx + "px";
    badge.style.width = options.badgeWidthPx + "px";
    badge.style.maxWidth = "34%";
    badge.style.height = "auto";
    badge.style.zIndex = "20";
    badge.style.pointerEvents = "none";
    badge.style.userSelect = "none";
    badge.style.opacity = String(options.badgeOpacity);
    badge.style.display = "block";

    container.appendChild(badge);
  }

  async function renderGlbBase64Viewer(glbBase64, options) {
    options = Object.assign({}, DEFAULTS, options || {});

    const container = resolveContainer(
      options.container ||
      options.element ||
      options.target ||
      options.containerId
    );

    if (!container) {
      throw new Error("Debes pasar options.container.");
    }

    if (!glbBase64) {
      showError(container, "No se recibió GLB base64.");
      return null;
    }

    if (container.__glbViewerDestroy) {
      try {
        container.__glbViewerDestroy();
      } catch (e) {}
    }

    container.innerHTML = "";
    container.style.width = "100%";
    container.style.height = typeof options.height === "number" ? options.height + "px" : options.height;
    container.style.position = "relative";
    container.style.overflow = "hidden";
    container.style.background = options.background;
    container.style.borderRadius = options.borderRadius;
    container.style.contain = "layout paint size";

    const deps = await loadDependencies(options.threeVersion);
    const THREE = deps.THREE;
    const GLTFLoader = deps.GLTFLoader;
    const DRACOLoader = deps.DRACOLoader;

    const size = {
      w: Math.max(container.clientWidth || 800, 1),
      h: Math.max(container.clientHeight || Number(options.height) || 520, 1)
    };

    const renderer = new THREE.WebGLRenderer({
      antialias: !!options.antialias,
      alpha: true,
      powerPreference: "high-performance",
      preserveDrawingBuffer: false,
      depth: true,
      stencil: false,
      desynchronized: true
    });

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, options.maxPixelRatio));
    renderer.setSize(size.w, size.h, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor(0x000000, 0);

    renderer.domElement.style.position = "absolute";
    renderer.domElement.style.left = "0";
    renderer.domElement.style.top = "0";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";
    renderer.domElement.style.zIndex = "1";

    container.appendChild(renderer.domElement);
    addBadge(container, options);

    const scene = new THREE.Scene();

    const camera = new THREE.PerspectiveCamera(
      32,
      size.w / size.h,
      0.01,
      10000
    );

    camera.position.set(0, 0, 7);
    camera.lookAt(0, 0, 0);

    scene.add(new THREE.AmbientLight(0xffffff, 1.35));

    const keyLight = new THREE.DirectionalLight(0xffffff, 1.25);
    keyLight.position.set(0, 0, 8);
    scene.add(keyLight);

    const fillLight1 = new THREE.DirectionalLight(0xffffff, 0.35);
    fillLight1.position.set(4, 3, 5);
    scene.add(fillLight1);

    const fillLight2 = new THREE.DirectionalLight(0xffffff, 0.25);
    fillLight2.position.set(-4, 2, 4);
    scene.add(fillLight2);

    const spinGroup = new THREE.Group();
    scene.add(spinGroup);

    const poseGroup = new THREE.Group();
    spinGroup.add(poseGroup);

    const loader = new GLTFLoader();

    try {
      const dracoLoader = new DRACOLoader();
      dracoLoader.setDecoderPath("https://www.gstatic.com/draco/v1/decoders/");
      loader.setDRACOLoader(dracoLoader);
    } catch (e) {}

    const arrayBuffer = base64ToArrayBuffer(glbBase64);

    let gltf;

    try {
      gltf = await new Promise(function (resolve, reject) {
        loader.parse(arrayBuffer, "", resolve, reject);
      });
    } catch (e) {
      console.error(e);
      showError(container, "No se pudo leer el archivo GLB desde base64.");
      return null;
    }

    const model = gltf.scene;

    if (!model) {
      showError(container, "El GLB fue leído, pero no contiene escena 3D.");
      return null;
    }

    model.traverse(function (obj) {
      if (!obj.isMesh) return;

      obj.castShadow = false;
      obj.receiveShadow = false;
      obj.frustumCulled = false;

      if (obj.geometry) {
        if (!obj.geometry.attributes.normal) {
          obj.geometry.computeVertexNormals();
        }

        obj.geometry.computeBoundingBox();
        obj.geometry.computeBoundingSphere();
      }

      const mats = Array.isArray(obj.material) ? obj.material : [obj.material];

      mats.forEach(function (m) {
        if (!m) return;
        m.needsUpdate = true;

        if ("flatShading" in m) m.flatShading = false;
        if ("toneMapped" in m) m.toneMapped = true;
      });
    });

    poseGroup.add(model);

    model.rotation.set(
      options.frontFaceRotX,
      options.frontFaceRotY,
      options.frontFaceRotZ
    );

    let box = new THREE.Box3().setFromObject(model);

    if (box.isEmpty()) {
      showError(container, "No se pudo calcular el bounding box del GLB.");
      return null;
    }

    let center = box.getCenter(new THREE.Vector3());
    let modelSize = box.getSize(new THREE.Vector3());
    let maxDim = Math.max(modelSize.x, modelSize.y, modelSize.z) || 1;

    model.position.sub(center);

    const scale = options.targetModelSize / maxDim;
    model.scale.setScalar(scale);

    box = new THREE.Box3().setFromObject(model);
    center = box.getCenter(new THREE.Vector3());
    model.position.sub(center);

    box = new THREE.Box3().setFromObject(poseGroup);

    const sphere = new THREE.Sphere();
    box.getBoundingSphere(sphere);

    const radius = Math.max(sphere.radius, 1e-6);
    const fov = THREE.MathUtils.degToRad(camera.fov);
    const dist = radius / Math.sin(fov / 2) * options.fitPadding;

    camera.position.set(0, 0, dist);
    camera.lookAt(0, 0, 0);
    camera.near = Math.max(radius / 1000, 0.001);
    camera.far = Math.max(radius * 1000, 1000);
    camera.updateProjectionMatrix();

    let disposed = false;
    let frameId = null;
    let startTime = null;
    const TAU = Math.PI * 2;
    let speed = TAU * options.rotationsPerSecond;

    function animate(now) {
      if (disposed) return;

      frameId = requestAnimationFrame(animate);

      if (startTime === null) {
        startTime = now;
      }

      if (options.autoRotate) {
        const elapsed = (now - startTime) * 0.001;
        spinGroup.rotation.y = (elapsed * speed) % TAU;
      }

      renderer.render(scene, camera);
    }

    function resize() {
      if (disposed) return;

      const w = Math.max(container.clientWidth || 800, 1);
      const h = Math.max(container.clientHeight || Number(options.height) || 520, 1);

      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, options.maxPixelRatio));
      renderer.setSize(w, h, false);

      camera.aspect = w / h;
      camera.updateProjectionMatrix();

      renderer.render(scene, camera);
    }

    const resizeObserver = new ResizeObserver(function () {
      requestAnimationFrame(resize);
    });

    resizeObserver.observe(container);

    function destroy() {
      disposed = true;

      if (frameId !== null) {
        cancelAnimationFrame(frameId);
      }

      resizeObserver.disconnect();

      try {
        renderer.dispose();
      } catch (e) {}

      container.innerHTML = "";

      if (container.__glbViewerDestroy === destroy) {
        delete container.__glbViewerDestroy;
      }
    }

    container.__glbViewerDestroy = destroy;

    frameId = requestAnimationFrame(animate);

    return {
      destroy: destroy,
      renderer: renderer,
      scene: scene,
      camera: camera,
      model: model,
      spinGroup: spinGroup,
      resize: resize,
      setSpeed: function (rotationsPerSecond) {
        speed = TAU * Number(rotationsPerSecond || 0);
      },
      setAutoRotate: function (value) {
        options.autoRotate = !!value;
      }
    };
  }

  global.renderGlbBase64Viewer = renderGlbBase64Viewer;
  global.AutoMindGlbViewer = {
    renderGlbBase64Viewer: renderGlbBase64Viewer
  };
})(window);
