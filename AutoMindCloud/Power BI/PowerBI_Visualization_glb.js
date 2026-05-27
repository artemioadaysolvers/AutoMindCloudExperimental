// ============================================================
// AutoMindCloud - GLB Base64 Viewer
// Funcion global para jsDelivr:
// window.renderGlbBase64Viewer(glbBase64, options)
// ============================================================

(function (global) {
  "use strict";

  const DEFAULTS = {
    container: null,

    height: 520,
    background: "transparent",
    borderRadius: "14px",

    // Logo inferior derecho
    showBadge: true,
    badgeUrl: "https://raw.githubusercontent.com/artemioadaysolvers/AutoMindCloudExperimental/main/AutoMindCloud/AutoMindCloud2.png",
    badgeWidthPx: 180,
    badgeRightPx: 14,
    badgeBottomPx: 14,
    badgeOpacity: 0.95,

    // Orientacion base del GLB
    frontFaceRotX: -1.57079632679, // -pi/2
    frontFaceRotY: 3.14159265359,  // pi
    frontFaceRotZ: 0.0,

    // Giro
    autoRotate: true,
    rotationsPerSecond: 0.045,

    // Tamaño visual
    targetModelSize: 3.2,
    fitPadding: 1.18,

    // Performance
    maxPixelRatio: 1.0,
    antialias: true,
    preserveDrawingBuffer: false,

    // Render
    alpha: true,
    clearContainer: true,

    // Camara
    cameraFov: 32,

    // Luces
    ambientIntensity: 1.35,
    keyLightIntensity: 1.25,
    fillLight1Intensity: 0.35,
    fillLight2Intensity: 0.25,

    // Draco
    useDraco: true,
    dracoDecoderPath: "https://www.gstatic.com/draco/v1/decoders/",

    // Three.js
    threeVersion: "0.181.0"
  };

  let threePromise = null;

  function mergeOptions(options) {
    return Object.assign({}, DEFAULTS, options || {});
  }

  function resolveContainer(container) {
    if (!container) return null;

    if (typeof container === "string") {
      return (
        document.querySelector(container) ||
        document.getElementById(container.replace(/^#/, ""))
      );
    }

    if (container instanceof HTMLElement) {
      return container;
    }

    return null;
  }

  function cssSize(value) {
    if (typeof value === "number") return value + "px";
    if (typeof value === "string") return value;
    return "520px";
  }

  function cleanBase64(b64) {
    b64 = String(b64 || "").trim();
    return b64.includes(",") ? b64.split(",").pop() : b64;
  }

  function base64ToArrayBuffer(b64) {
    b64 = cleanBase64(b64);

    const binary = atob(b64);
    const len = binary.length;
    const bytes = new Uint8Array(len);

    for (let i = 0; i < len; i++) {
      bytes[i] = binary.charCodeAt(i);
    }

    return bytes.buffer;
  }

  function showError(container, msg) {
    container.innerHTML = "";

    const box = document.createElement("div");
    box.style.width = "100%";
    box.style.height = "100%";
    box.style.display = "flex";
    box.style.alignItems = "center";
    box.style.justifyContent = "center";
    box.style.padding = "16px";
    box.style.boxSizing = "border-box";
    box.style.fontFamily = "Arial, sans-serif";
    box.style.color = "#991b1b";
    box.style.background = "#fff1f2";
    box.style.border = "1px solid #fecdd3";
    box.style.borderRadius = "14px";
    box.style.fontWeight = "700";
    box.style.textAlign = "center";
    box.textContent = msg;

    container.appendChild(box);
  }

  async function loadThree(version) {
    if (!threePromise) {
      threePromise = Promise.all([
        import(`https://esm.sh/three@${version}`),
        import(`https://esm.sh/three@${version}/examples/jsm/loaders/GLTFLoader.js?deps=three@${version}`),
        import(`https://esm.sh/three@${version}/examples/jsm/loaders/DRACOLoader.js?deps=three@${version}`)
      ]).then(([THREE, gltfModule, dracoModule]) => {
        return {
          THREE,
          GLTFLoader: gltfModule.GLTFLoader,
          DRACOLoader: dracoModule.DRACOLoader
        };
      });
    }

    return threePromise;
  }

  function prepareContainer(container, options) {
    if (options.clearContainer) {
      container.innerHTML = "";
    }

    container.style.width = container.style.width || "100%";
    container.style.height = cssSize(options.height);
    container.style.position = "relative";
    container.style.overflow = "hidden";
    container.style.background = options.background;
    container.style.borderRadius = options.borderRadius;
    container.style.contain = "layout paint size";
  }

  function addBadge(container, options) {
    if (!options.showBadge || !options.badgeUrl) return null;

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

    return badge;
  }

  function disposeObject3D(root) {
    if (!root) return;

    root.traverse((obj) => {
      if (obj.geometry) {
        obj.geometry.dispose();
      }

      if (obj.material) {
        const materials = Array.isArray(obj.material) ? obj.material : [obj.material];

        materials.forEach((mat) => {
          if (!mat) return;

          for (const key in mat) {
            const value = mat[key];

            if (value && typeof value === "object" && typeof value.dispose === "function") {
              value.dispose();
            }
          }

          if (typeof mat.dispose === "function") {
            mat.dispose();
          }
        });
      }
    });
  }

  async function renderGlbBase64Viewer(glbBase64, options) {
    const opts = mergeOptions(options);
    const container = resolveContainer(opts.container || opts.element || opts.target || opts.containerId);

    if (!container) {
      throw new Error(
        "renderGlbBase64Viewer: debes pasar options.container como selector, id o elemento HTML."
      );
    }

    if (!glbBase64 || typeof glbBase64 !== "string") {
      showError(container, "No se recibió un GLB en base64.");
      throw new Error("renderGlbBase64Viewer: glbBase64 vacío o inválido.");
    }

    if (container.__glbViewerDestroy) {
      try {
        container.__glbViewerDestroy();
      } catch (e) {}
    }

    prepareContainer(container, opts);

    const {
      THREE,
      GLTFLoader,
      DRACOLoader
    } = await loadThree(opts.threeVersion);

    let disposed = false;
    let frameId = null;
    let resizeObserver = null;
    let logo = null;
    let ready = false;
    let startTime = null;

    const TAU = Math.PI * 2;
    let speed = TAU * opts.rotationsPerSecond;

    function getSize() {
      return {
        w: Math.max(container.clientWidth || 800, 1),
        h: Math.max(container.clientHeight || Number(opts.height) || 520, 1)
      };
    }

    const size0 = getSize();

    const renderer = new THREE.WebGLRenderer({
      antialias: !!opts.antialias,
      alpha: !!opts.alpha,
      powerPreference: "high-performance",
      preserveDrawingBuffer: !!opts.preserveDrawingBuffer,
      depth: true,
      stencil: false,
      desynchronized: true
    });

    renderer.setPixelRatio(Math.min(global.devicePixelRatio || 1, opts.maxPixelRatio));
    renderer.setSize(size0.w, size0.h, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor(0x000000, 0);

    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";
    renderer.domElement.style.position = "absolute";
    renderer.domElement.style.left = "0";
    renderer.domElement.style.top = "0";
    renderer.domElement.style.zIndex = "1";
    renderer.domElement.style.transform = "translate3d(0,0,0)";
    renderer.domElement.style.backfaceVisibility = "hidden";
    renderer.domElement.style.willChange = "transform";

    container.appendChild(renderer.domElement);
    addBadge(container, opts);

    const scene = new THREE.Scene();

    const camera = new THREE.PerspectiveCamera(
      opts.cameraFov,
      size0.w / size0.h,
      0.01,
      10000
    );

    camera.position.set(0, 0, 7);
    camera.lookAt(0, 0, 0);

    scene.add(new THREE.AmbientLight(0xffffff, opts.ambientIntensity));

    const keyLight = new THREE.DirectionalLight(0xffffff, opts.keyLightIntensity);
    keyLight.position.set(0, 0, 8);
    scene.add(keyLight);

    const fillLight1 = new THREE.DirectionalLight(0xffffff, opts.fillLight1Intensity);
    fillLight1.position.set(4, 3, 5);
    scene.add(fillLight1);

    const fillLight2 = new THREE.DirectionalLight(0xffffff, opts.fillLight2Intensity);
    fillLight2.position.set(-4, 2, 4);
    scene.add(fillLight2);

    const spinGroup = new THREE.Group();
    scene.add(spinGroup);

    const poseGroup = new THREE.Group();
    spinGroup.add(poseGroup);

    const loader = new GLTFLoader();

    if (opts.useDraco) {
      try {
        const dracoLoader = new DRACOLoader();
        dracoLoader.setDecoderPath(opts.dracoDecoderPath);
        loader.setDRACOLoader(dracoLoader);
      } catch (e) {}
    }

    function resizeRenderer() {
      if (disposed) return;

      const s = getSize();

      renderer.setPixelRatio(Math.min(global.devicePixelRatio || 1, opts.maxPixelRatio));
      renderer.setSize(s.w, s.h, false);

      camera.aspect = s.w / s.h;
      camera.updateProjectionMatrix();

      renderer.render(scene, camera);
    }

    function animate(now) {
      if (disposed) return;

      frameId = requestAnimationFrame(animate);

      if (startTime === null) {
        startTime = now;
      }

      if (ready && opts.autoRotate) {
        const elapsed = (now - startTime) * 0.001;
        const angle = (elapsed * speed) % TAU;
        spinGroup.rotation.y = angle;
      }

      renderer.render(scene, camera);
    }

    function destroy() {
      disposed = true;

      if (frameId !== null) {
        cancelAnimationFrame(frameId);
        frameId = null;
      }

      if (resizeObserver) {
        resizeObserver.disconnect();
        resizeObserver = null;
      }

      disposeObject3D(scene);

      try {
        renderer.dispose();
      } catch (e) {}

      if (renderer.domElement && renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement);
      }

      if (container.__glbViewerDestroy === destroy) {
        delete container.__glbViewerDestroy;
      }
    }

    container.__glbViewerDestroy = destroy;

    let arrayBuffer;

    try {
      arrayBuffer = base64ToArrayBuffer(glbBase64);
    } catch (e) {
      showError(container, "No se pudo convertir el GLB base64 a ArrayBuffer.");
      destroy();
      throw e;
    }

    let gltf;

    try {
      gltf = await new Promise((resolve, reject) => {
        loader.parse(arrayBuffer, "", resolve, reject);
      });
    } catch (e) {
      console.error(e);
      showError(container, "No se pudo leer el archivo GLB desde base64.");
      destroy();
      throw e;
    }

    logo = gltf.scene;

    if (!logo) {
      showError(container, "El GLB fue leído, pero no contiene escena 3D.");
      destroy();
      throw new Error("GLB sin escena 3D.");
    }

    logo.traverse((obj) => {
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

      mats.forEach((m) => {
        if (!m) return;

        m.needsUpdate = true;

        if ("flatShading" in m) {
          m.flatShading = false;
        }

        if ("toneMapped" in m) {
          m.toneMapped = true;
        }
      });
    });

    poseGroup.add(logo);

    logo.rotation.set(
      opts.frontFaceRotX,
      opts.frontFaceRotY,
      opts.frontFaceRotZ
    );

    let box = new THREE.Box3().setFromObject(logo);

    if (box.isEmpty()) {
      showError(container, "No se pudo calcular el bounding box del GLB.");
      destroy();
      throw new Error("Bounding box vacío.");
    }

    let center = box.getCenter(new THREE.Vector3());
    let modelSize = box.getSize(new THREE.Vector3());
    let maxDim = Math.max(modelSize.x, modelSize.y, modelSize.z) || 1;

    logo.position.sub(center);

    const scale = opts.targetModelSize / maxDim;
    logo.scale.setScalar(scale);

    box = new THREE.Box3().setFromObject(logo);
    center = box.getCenter(new THREE.Vector3());
    logo.position.sub(center);

    box = new THREE.Box3().setFromObject(poseGroup);

    const sphere = new THREE.Sphere();
    box.getBoundingSphere(sphere);

    const radius = Math.max(sphere.radius, 1e-6);
    const fov = THREE.MathUtils.degToRad(camera.fov);
    const dist = radius / Math.sin(fov / 2) * opts.fitPadding;

    camera.position.set(0, 0, dist);
    camera.lookAt(0, 0, 0);
    camera.near = Math.max(radius / 1000, 0.001);
    camera.far = Math.max(radius * 1000, 1000);
    camera.updateProjectionMatrix();

    spinGroup.rotation.set(0, 0, 0);
    spinGroup.position.set(0, 0, 0);
    poseGroup.position.set(0, 0, 0);

    ready = true;

    resizeObserver = new ResizeObserver(() => {
      requestAnimationFrame(resizeRenderer);
    });

    resizeObserver.observe(container);

    frameId = requestAnimationFrame(animate);

    return {
      destroy,

      renderer,
      scene,
      camera,
      container,

      setSpeed(rotationsPerSecond) {
        speed = TAU * Number(rotationsPerSecond || 0);
      },

      setAutoRotate(value) {
        opts.autoRotate = !!value;
      },

      setRotationY(radians) {
        spinGroup.rotation.y = Number(radians || 0);
        renderer.render(scene, camera);
      },

      getObject() {
        return logo;
      },

      getSpinGroup() {
        return spinGroup;
      },

      resize() {
        resizeRenderer();
      }
    };
  }

  global.renderGlbBase64Viewer = renderGlbBase64Viewer;
})(window);
