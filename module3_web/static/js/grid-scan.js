/**
 * GridScan — 3D 掃描網格背景（vanilla JS / Three.js）
 *
 * 修復記錄 2026-06-21:
 *   - CDN URL 404: three@0.162.0 無 UMD build → 改用 r160
 *   - CDN URL 404: postprocessing.cjs.min.js → 改用 postprocessing.min.js (UMD)
 *   - 雙 tick 循環: _createScene() 內 tick 不執行（_running=false），
 *     start() 內 tick 只更新 iTime 不更新 parallax → 合併為單一 tick
 *   - 加 CDN fallback（jsdelivr → unpkg）
 *   - 加 console 診斷日誌
 */
(function (global) {
  'use strict';

  let renderer, scene, camera, material, composer, bloom, chroma;
  let canvas, container, rafId;
  let _startTime = 0;
  let _running = false;
  let _initialized = false;

  // ── Parallax state（移到外部作用域，供統一 tick 使用）──
  let _lookTarget, _lookCurrent, _lookVel;
  let _tiltTarget = 0, _yawTarget = 0;
  let _tiltCur = 0, _yawCur = 0;
  let _tiltVel = 0, _yawVel = 0;
  let _skewScale, _yBoost, _tiltScale, _yawScale, _smoothTime;
  let _uniforms = null;
  let _onResize = null;
  let _onMouseMove = null;

  // ── Shader sources (ported from ReactBits GridScan) ──
  const VERT = `
varying vec2 vUv;
void main(){
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

  const FRAG = `
precision highp float;
uniform vec3 iResolution;
uniform float iTime;
uniform vec2 uSkew;
uniform float uTilt;
uniform float uYaw;
uniform float uLineThickness;
uniform vec3 uLinesColor;
uniform vec3 uScanColor;
uniform float uGridScale;
uniform float uLineStyle;
uniform float uLineJitter;
uniform float uScanOpacity;
uniform float uScanDirection;
uniform float uNoise;
uniform float uBloomOpacity;
uniform float uScanGlow;
uniform float uScanSoftness;
uniform float uPhaseTaper;
uniform float uScanDuration;
uniform float uScanDelay;
varying vec2 vUv;

float smoother01(float a, float b, float x){
  float t = clamp((x - a) / max(1e-5, (b - a)), 0.0, 1.0);
  return t * t * t * (t * (t * 6.0 - 15.0) + 10.0);
}

void main(){
    vec2 p = (2.0 * vUv - 1.0);
    p.x *= iResolution.x / iResolution.y;

    vec3 ro = vec3(0.0);
    vec3 rd = normalize(vec3(p, 2.0));

    float cR = cos(uTilt), sR = sin(uTilt);
    rd.xy = mat2(cR, -sR, sR, cR) * rd.xy;

    float cY = cos(uYaw), sY = sin(uYaw);
    rd.xz = mat2(cY, -sY, sY, cY) * rd.xz;

    vec2 skew = clamp(uSkew, vec2(-0.7), vec2(0.7));
    rd.xy += skew * rd.z;

    vec3 color = vec3(0.0);
    float minT = 1e20;
    float gridScale = max(1e-5, uGridScale);
    float fadeStrength = 2.0;
    vec2 gridUV = vec2(0.0);
    float hitIsY = 1.0;

    for (int i = 0; i < 4; i++){
        float isY = float(i < 2);
        float pos = mix(-0.2, 0.2, float(i)) * isY + mix(-0.5, 0.5, float(i - 2)) * (1.0 - isY);
        float num = pos - (isY * ro.y + (1.0 - isY) * ro.x);
        float den = isY * rd.y + (1.0 - isY) * rd.x;
        float t = num / den;
        vec3 h = ro + rd * t;
        float depthBoost = smoothstep(0.0, 3.0, h.z);
        h.xy += skew * 0.15 * depthBoost;
        bool use = t > 0.0 && t < minT;
        gridUV = use ? mix(h.zy, h.xz, isY) / gridScale : gridUV;
        minT = use ? t : minT;
        hitIsY = use ? isY : hitIsY;
    }

    vec3 hit = ro + rd * minT;
    float dist = length(hit - ro);

    // Jitter
    if (uLineJitter > 0.0) {
      vec2 j = vec2(
        sin(gridUV.y * 2.7 + iTime * 1.8),
        cos(gridUV.x * 2.3 - iTime * 1.6)
      ) * (0.15 * uLineJitter);
      gridUV += j;
    }

    float fx = fract(gridUV.x);
    float fy = fract(gridUV.y);
    float ax = min(fx, 1.0 - fx);
    float ay = min(fy, 1.0 - fy);
    float wx = fwidth(gridUV.x);
    float wy = fwidth(gridUV.y);

    float halfPx = max(0.0, uLineThickness) * 0.5;
    float tx = halfPx * wx;
    float ty = halfPx * wy;
    float lineX = 1.0 - smoothstep(tx, tx + wx, ax);
    float lineY = 1.0 - smoothstep(ty, ty + wy, ay);

    // Line style
    if (uLineStyle > 0.5 && uLineStyle < 1.5) {
      float dashRepeat = 4.0;
      float vy = fract(gridUV.y * dashRepeat);
      float vx = fract(gridUV.x * dashRepeat);
      float dashMaskY = step(vy, 0.5);
      float dashMaskX = step(vx, 0.5);
      lineX *= dashMaskY;
      lineY *= dashMaskX;
    } else if (uLineStyle >= 1.5) {
      float dotRepeat = 6.0;
      float dotWidth = 0.18;
      float cy = abs(fract(gridUV.y * dotRepeat) - 0.5);
      float cx = abs(fract(gridUV.x * dotRepeat) - 0.5);
      float dotMaskY = 1.0 - smoothstep(dotWidth, dotWidth + fwidth(gridUV.y * dotRepeat), cy);
      float dotMaskX = 1.0 - smoothstep(dotWidth, dotWidth + fwidth(gridUV.x * dotRepeat), cx);
      lineX *= dotMaskY;
      lineY *= dotMaskX;
    }
    float primaryMask = max(lineX, lineY);

    // Secondary grid
    vec2 gridUV2 = (hitIsY > 0.5 ? hit.xz : hit.zy) / gridScale;
    if (uLineJitter > 0.0) {
      vec2 j2 = vec2(cos(gridUV2.y * 2.1 - iTime * 1.4), sin(gridUV2.x * 2.5 + iTime * 1.7)) * (0.15 * uLineJitter);
      gridUV2 += j2;
    }
    float fx2 = fract(gridUV2.x);
    float fy2 = fract(gridUV2.y);
    float ax2 = min(fx2, 1.0 - fx2);
    float ay2 = min(fy2, 1.0 - fy2);
    float wx2 = fwidth(gridUV2.x);
    float wy2 = fwidth(gridUV2.y);
    float tx2 = halfPx * wx2;
    float ty2 = halfPx * wy2;
    float lineX2 = 1.0 - smoothstep(tx2, tx2 + wx2, ax2);
    float lineY2 = 1.0 - smoothstep(ty2, ty2 + wy2, ay2);
    if (uLineStyle > 0.5 && uLineStyle < 1.5) {
      float dr2 = 4.0; float vy2 = fract(gridUV2.y * dr2); float vx2 = fract(gridUV2.x * dr2);
      lineX2 *= step(vy2, 0.5); lineY2 *= step(vx2, 0.5);
    } else if (uLineStyle >= 1.5) {
      float dR2 = 6.0; float dw2 = 0.18;
      float cy2 = abs(fract(gridUV2.y * dR2) - 0.5); float cx2 = abs(fract(gridUV2.x * dR2) - 0.5);
      lineX2 *= 1.0 - smoothstep(dw2, dw2+fwidth(gridUV2.y*dR2), cy2);
      lineY2 *= 1.0 - smoothstep(dw2, dw2+fwidth(gridUV2.x*dR2), cx2);
    }
    float altMask = max(lineX2, lineY2);

    float edgeDistX = min(abs(hit.x - (-0.5)), abs(hit.x - 0.5));
    float edgeDistY = min(abs(hit.y - (-0.2)), abs(hit.y - 0.2));
    float edgeDist = mix(edgeDistY, edgeDistX, hitIsY);
    float edgeGate = 1.0 - smoothstep(gridScale * 0.5, gridScale * 2.0, edgeDist);
    altMask *= edgeGate;

    float lineMask = max(primaryMask, altMask);

    // Fade by distance
    float fade = exp(-dist * fadeStrength);

    // Scan effect
    float dur = max(0.05, uScanDuration);
    float del = max(0.0, uScanDelay);
    float scanZMax = 2.0;
    float widthScale = max(0.1, uScanGlow);
    float sigma = max(0.001, 0.18 * widthScale * uScanSoftness);
    float sigmaA = sigma * 2.0;

    float cycle = dur + del;
    float tCycle = mod(iTime, cycle);
    float scanPhase = clamp((tCycle - del) / dur, 0.0, 1.0);
    float phase = scanPhase;
    if (uScanDirection > 0.5 && uScanDirection < 1.5) phase = 1.0 - phase;
    else if (uScanDirection >= 1.5 && uScanDirection < 2.5) {
      float t2 = mod(max(0.0, iTime - del), 2.0 * dur);
      phase = (t2 < dur) ? (t2 / dur) : (1.0 - (t2 - dur) / dur);
    }
    else if (uScanDirection >= 2.5) {
      float t2 = mod(max(0.0, iTime - del), 2.0 * dur);
      phase = (t2 < dur) ? (1.0 - t2 / dur) : ((t2 - dur) / dur);
    }
    float scanZ = phase * scanZMax;
    float dz = abs(hit.z - scanZ);
    float lineBand = exp(-0.5 * (dz * dz) / (sigma * sigma));

    float taper = clamp(uPhaseTaper, 0.0, 0.49);
    float headFade = smoother01(0.0, taper, phase);
    float tailFade = 1.0 - smoother01(1.0 - taper, 1.0, phase);
    float phaseWindow = headFade * tailFade;

    float combinedPulse = lineBand * phaseWindow * clamp(uScanOpacity, 0.0, 1.0);
    float auraBand = exp(-0.5 * (dz * dz) / (sigmaA * sigmaA)) * phaseWindow * clamp(uScanOpacity, 0.0, 1.0) * 0.25;

    float lineVis = lineMask;
    vec3 gridCol = uLinesColor * lineVis * fade;
    vec3 scanCol = uScanColor * combinedPulse;
    vec3 scanAura = uScanColor * auraBand;

    color = gridCol + scanCol + scanAura;

    // Noise
    float n = fract(sin(dot(gl_FragCoord.xy + vec2(iTime * 123.4), vec2(12.9898,78.233))) * 43758.5453123);
    color += (n - 0.5) * uNoise;
    color = clamp(color, 0.0, 1.0);

    float alpha = clamp(max(lineVis, combinedPulse), 0.0, 1.0);
    float gx = 1.0 - smoothstep(tx * 2.0, tx * 2.0 + wx * 2.0, ax);
    float gy = 1.0 - smoothstep(ty * 2.0, ty * 2.0 + wy * 2.0, ay);
    float halo = max(gx, gy) * fade;
    alpha = max(alpha, halo * clamp(uBloomOpacity, 0.0, 1.0));

    gl_FragColor = vec4(color, alpha);
}
`;

  const DEFAULTS = {
    sensitivity: 0.55,
    lineThickness: 1,
    linesColor: '#2f1067',
    gridScale: 0.12,
    scanColor: '#b511ae',
    scanOpacity: 0.4,
    enablePost: true,
    bloomIntensity: 0.6,
    chromaticAberration: 0.001,
    noiseIntensity: 0.02,
    scanGlow: 0.2,
    scanSoftness: 2.5,
    scanPhaseTaper: 0.9,
    scanDuration: 2.0,
    scanDelay: 2.0,
    scanDirection: 'pingpong'
  };

  let opts = {};

  function srgbColor(hex) {
    var c = new THREE.Color(hex || '#ffffff');
    return c.convertSRGBToLinear();
  }

  // ── CDN loader with fallback ──
  function loadScript(urls) {
    return new Promise(function (resolve, reject) {
      var idx = 0;
      function tryNext() {
        if (idx >= urls.length) {
          reject(new Error('All CDN URLs failed: ' + urls.join(', ')));
          return;
        }
        var url = urls[idx++];
        var s = document.createElement('script');
        s.src = url;
        s.onload = function () {
          console.log('[GridScan] Loaded:', url);
          resolve();
        };
        s.onerror = function () {
          console.warn('[GridScan] Failed, trying next:', url);
          tryNext();
        };
        document.head.appendChild(s);
      }
      tryNext();
    });
  }

  function _createScene() {
    container = document.querySelector(opts._containerSel);
    if (!container) {
      console.error('[GridScan] Container not found:', opts._containerSel);
      return false;
    }

    canvas = document.createElement('canvas');
    canvas.id = 'gridScanCanvas';
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;opacity:0;transition:opacity 0.8s ease;';
    container.appendChild(canvas);

    var w = container.clientWidth || window.innerWidth;
    var h = container.clientHeight || window.innerHeight;
    console.log('[GridScan] Container size:', w, 'x', h);

    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(w, h);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.NoToneMapping;
    renderer.autoClear = false;
    renderer.setClearColor(0x000000, 0);

    scene = new THREE.Scene();
    camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

    var s = THREE.MathUtils.clamp(opts.sensitivity || DEFAULTS.sensitivity, 0, 1);
    _uniforms = {
      iResolution: { value: new THREE.Vector3(w, h, renderer.getPixelRatio()) },
      iTime: { value: 0 },
      uSkew: { value: new THREE.Vector2(0, 0) },
      uTilt: { value: 0 },
      uYaw: { value: 0 },
      uLineThickness: { value: opts.lineThickness || DEFAULTS.lineThickness },
      uLinesColor: { value: srgbColor(opts.linesColor || DEFAULTS.linesColor) },
      uScanColor: { value: srgbColor(opts.scanColor || DEFAULTS.scanColor) },
      uGridScale: { value: opts.gridScale || DEFAULTS.gridScale },
      uLineStyle: { value: 0 },
      uLineJitter: { value: Math.max(0, Math.min(1, opts.lineJitter || 0)) },
      uScanOpacity: { value: opts.scanOpacity || DEFAULTS.scanOpacity },
      uNoise: { value: opts.noiseIntensity || DEFAULTS.noiseIntensity },
      uBloomOpacity: { value: opts.bloomIntensity || DEFAULTS.bloomIntensity },
      uScanGlow: { value: opts.scanGlow || DEFAULTS.scanGlow },
      uScanSoftness: { value: opts.scanSoftness || DEFAULTS.scanSoftness },
      uPhaseTaper: { value: opts.scanPhaseTaper || DEFAULTS.scanPhaseTaper },
      uScanDuration: { value: Math.max(0.05, opts.scanDuration || DEFAULTS.scanDuration) },
      uScanDelay: { value: Math.max(0, opts.scanDelay || DEFAULTS.scanDelay) },
      uScanDirection: {
        value: (opts.scanDirection === 'backward' ? 1 : opts.scanDirection === 'pingpong' ? 2 : opts.scanDirection === 'pingpong-reverse' ? 3 : 0)
      }
    };

    material = new THREE.ShaderMaterial({
      uniforms: _uniforms,
      vertexShader: VERT,
      fragmentShader: FRAG,
      transparent: true,
      depthWrite: false,
      depthTest: false
    });

    var quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
    scene.add(quad);

    // Post-processing (optional)
    // postprocessing v6 UMD build 暴露在 POSTPROCESSING 全域物件下
    if (opts.enablePost !== false && typeof POSTPROCESSING !== 'undefined') {
      try {
        var PP = POSTPROCESSING;
        composer = new PP.EffectComposer(renderer);
        var renderPass = new PP.RenderPass(scene, camera);
        composer.addPass(renderPass);

        bloom = new PP.BloomEffect({
          intensity: 1.0,
          luminanceThreshold: 0,
          luminanceSmoothing: 0
        });
        bloom.blendMode.opacity.value = Math.max(0, opts.bloomIntensity || DEFAULTS.bloomIntensity);

        chroma = new PP.ChromaticAberrationEffect({
          offset: new THREE.Vector2(
            opts.chromaticAberration || DEFAULTS.chromaticAberration,
            opts.chromaticAberration || DEFAULTS.chromaticAberration
          ),
          radialModulation: true,
          modulationOffset: 0.0
        });

        var effectPass = new PP.EffectPass(camera, bloom, chroma);
        effectPass.renderToScreen = true;
        composer.addPass(effectPass);
        console.log('[GridScan] Post-processing enabled (Bloom + ChromaticAberration)');
      } catch (e) {
        console.warn('[GridScan] Post-processing failed, falling back to raw render:', e.message);
        composer = null;
      }
    } else {
      console.log('[GridScan] Post-processing disabled (POSTPROCESSING not available)');
    }

    // Resize handler
    _onResize = function () {
      var cw = container.clientWidth || window.innerWidth;
      var ch = container.clientHeight || window.innerHeight;
      renderer.setSize(cw, ch);
      _uniforms.iResolution.value.set(cw, ch, renderer.getPixelRatio());
      if (composer) composer.setSize(cw, ch);
    };
    window.addEventListener('resize', _onResize);

    // Mouse parallax state
    _lookTarget = new THREE.Vector2(0, 0);
    _lookCurrent = new THREE.Vector2(0, 0);
    _lookVel = new THREE.Vector2(0, 0);
    _tiltTarget = 0; _yawTarget = 0;
    _tiltCur = 0; _yawCur = 0;
    _tiltVel = 0; _yawVel = 0;
    _skewScale = THREE.MathUtils.lerp(0.06, 0.2, s);
    _yBoost = THREE.MathUtils.lerp(1.2, 1.6, s);
    _tiltScale = THREE.MathUtils.lerp(0.12, 0.3, s);
    _yawScale = THREE.MathUtils.lerp(0.1, 0.28, s);
    _smoothTime = THREE.MathUtils.lerp(0.45, 0.12, s);

    _onMouseMove = function (e) {
      var rect = container.getBoundingClientRect();
      var nx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      var ny = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
      _lookTarget.set(nx, ny);
      _tiltTarget = nx * 0.08;
      _yawTarget = ny * 0.06;
    };
    container.addEventListener('mousemove', _onMouseMove);

    _initialized = true;
    console.log('[GridScan] Scene created successfully');
    return true;
  }

  // ── Unified tick (handles both parallax + render) ──
  function _tick() {
    if (!_running || !_uniforms) return;
    var now = performance.now();
    var dt = 0.016; // ~60fps fallback

    // Smooth damp for look
    var omega = 2 / _smoothTime;
    var x = omega * dt;
    var exp = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);

    var change = _lookCurrent.clone().sub(_lookTarget);
    var temp = _lookVel.clone().addScaledVector(change, omega).multiplyScalar(dt);
    _lookVel.sub(temp.clone().multiplyScalar(omega)).multiplyScalar(exp);
    _lookCurrent.copy(_lookTarget.clone().add(change.add(temp).multiplyScalar(exp)));

    // Tilt/Yaw smooth damp
    var ct = _tiltCur - _tiltTarget;
    var tv = (_tiltVel + omega * ct) * dt;
    _tiltVel = (_tiltVel - omega * tv) * exp;
    _tiltCur = _tiltTarget + (ct + tv) * exp;

    var cy_ = _yawCur - _yawTarget;
    var yv = (_yawVel + omega * cy_) * dt;
    _yawVel = (_yawVel - omega * yv) * exp;
    _yawCur = _yawTarget + (cy_ + yv) * exp;

    var skewX = _lookCurrent.x * _skewScale;
    var skewY = -_lookCurrent.y * _yBoost * _skewScale;
    _uniforms.uSkew.value.set(skewX, skewY);
    _uniforms.uTilt.value = _tiltCur * _tiltScale;
    _uniforms.uYaw.value = THREE.MathUtils.clamp(_yawCur * _yawScale, -0.6, 0.6);
    _uniforms.iTime.value = (performance.now() - _startTime) / 1000;

    renderer.clear(true, true, true);
    if (composer) {
      composer.render(dt);
    } else {
      renderer.render(scene, camera);
    }
    rafId = requestAnimationFrame(_tick);
  }

  // ── Public API ──

  global.GridScan = {

    /**
     * 初始化（異步載入 Three.js 後建立場景）
     */
    init: function (containerSel, options) {
      opts = Object.assign({}, DEFAULTS, options || {});
      opts._containerSel = containerSel;

      // Three.js already loaded?
      if (typeof THREE !== 'undefined') {
        console.log('[GridScan] THREE already available');
        return Promise.resolve();
      }

      // CDN URLs with fallback: jsdelivr → unpkg
      var threeUrls = [
        'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js',
        'https://unpkg.com/three@0.160.0/build/three.min.js'
      ];
      var postUrls = [
        'https://cdn.jsdelivr.net/npm/postprocessing@6.35.4/build/postprocessing.min.js',
        'https://unpkg.com/postprocessing@6.35.4/build/postprocessing.min.js'
      ];

      console.log('[GridScan] Loading Three.js from CDN...');
      return loadScript(threeUrls).then(function () {
        console.log('[GridScan] Three.js loaded, loading postprocessing...');
        return loadScript(postUrls).catch(function () {
          console.warn('[GridScan] Postprocessing failed to load, will use raw render');
        });
      }).then(function () {
        // Brief wait for globals to settle
        return new Promise(function (resolve) { setTimeout(resolve, 50); });
      });
    },

    start: function () {
      if (_running) return;
      if (!_initialized) {
        if (!_createScene()) {
          console.error('[GridScan] Failed to create scene');
          return;
        }
      }
      _startTime = performance.now();
      _running = true;
      // 淡入
      requestAnimationFrame(function () {
        if (canvas) canvas.style.opacity = '1';
      });
      console.log('[GridScan] Starting animation loop');
      rafId = requestAnimationFrame(_tick);
    },

    stop: function () {
      // 淡出後再停止
      if (canvas) canvas.style.opacity = '0';
      var self = this;
      setTimeout(function () {
        _running = false;
        if (rafId) cancelAnimationFrame(rafId);
        rafId = null;
      }, 600);
      console.log('[GridScan] Stopping (fade out)');
    },

    destroy: function () {
      this.stop();
      if (_onResize) window.removeEventListener('resize', _onResize);
      if (_onMouseMove && container) container.removeEventListener('mousemove', _onMouseMove);
      if (renderer) {
        try { renderer.dispose(); } catch(e) {}
        try { material.dispose(); } catch(e) {}
        try { scene.children[0].geometry.dispose(); } catch(e) {}
        if (composer) { try { composer.dispose(); } catch(e) {} }
        try { renderer.forceContextLoss(); } catch(e) {}
        if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
        renderer = null; material = null; scene = null; camera = null;
        composer = null; bloom = null; chroma = null; canvas = null;
        _uniforms = null; _initialized = false;
      }
    },

    isRunning: function () { return _running; },
    isInitialized: function () { return _initialized; }
  };

})(window);
