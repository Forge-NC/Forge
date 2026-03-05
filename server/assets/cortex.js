/**
 * Neural Cortex — Canvas-based brain animation
 * Port of Forge's AnimationEngine (forge/ui/dashboard.py)
 *
 * Usage:
 *   var cortex = new NeuralCortex(canvas, { autoMode: true });
 *   cortex.setState('thinking');
 */
(function() {
'use strict';

var STATES = {
    boot:      { waveCount:1, speed:0.3, sigma:0.20, hueCenter:0.52, hueRange:0.08, baseBri:0.35, intensity:0.7, fps:12, sat:0.6, mode:'spiral' },
    idle:      { waveCount:1, speed:0.4, sigma:0.18, hueCenter:0.52, hueRange:0.05, baseBri:0.55, intensity:0.4, fps:8,  sat:0.7, mode:'radial' },
    thinking:  { waveCount:3, speed:1.2, sigma:0.12, hueCenter:0.0,  hueRange:0.5,  baseBri:0.50, intensity:0.8, fps:14, sat:0.85,mode:'radial' },
    tool_exec: { waveCount:2, speed:1.5, sigma:0.10, hueCenter:0.42, hueRange:0.10, baseBri:0.50, intensity:0.7, fps:14, sat:0.8, mode:'sweep'  },
    indexing:  { waveCount:4, speed:0.8, sigma:0.08, hueCenter:0.78, hueRange:0.08, baseBri:0.45, intensity:0.6, fps:12, sat:0.75,mode:'radial' },
    swapping:  { waveCount:1, speed:2.0, sigma:0.15, hueCenter:0.52, hueRange:0.02, baseBri:0.45, intensity:1.2, fps:16, sat:0.3, mode:'flash'  },
    error:     { waveCount:2, speed:0.35, sigma:0.30, hueCenter:0.0,  hueRange:0.02, baseBri:0.50, intensity:0.9, fps:12, sat:0.9, mode:'radial' },
    threat:    { waveCount:5, speed:3.0, sigma:0.06, hueCenter:0.0,  hueRange:0.04, baseBri:0.70, intensity:1.5, fps:20, sat:1.0, mode:'threat' },
    pass:      { waveCount:1, speed:0.3, sigma:0.35, hueCenter:0.33, hueRange:0.05, baseBri:0.70, intensity:0.9, fps:10, sat:0.85,mode:'radial' }
};

var TRANS_DUR = 0.5;
var BG_COLOR = [10, 14, 23];

// Auto-cycle order for hero
var AUTO_CYCLE = ['boot','idle','thinking','tool_exec','indexing','pass','idle','swapping','error','threat','idle'];
var AUTO_INTERVAL = 4000;

function lerp(a, b, t) { return a + (b - a) * t; }
function smoothstep(t) { return t * t * (3.0 - 2.0 * t); }
function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

function hsvToRgb(h, s, v) {
    h = ((h % 1.0) + 1.0) % 1.0;
    var i = Math.floor(h * 6) % 6;
    var f = h * 6 - Math.floor(h * 6);
    var p = v * (1 - s);
    var q = v * (1 - s * f);
    var t = v * (1 - s * (1 - f));
    switch (i) {
        case 0: return [v, t, p];
        case 1: return [q, v, p];
        case 2: return [p, v, t];
        case 3: return [p, q, v];
        case 4: return [t, p, v];
        default: return [v, p, q];
    }
}

function NeuralCortex(canvas, opts) {
    opts = opts || {};
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.size = opts.size || 220;
    this.scale = opts.scale || 2;
    this.renderSize = this.size * this.scale;
    canvas.width = this.renderSize;
    canvas.height = this.renderSize;
    canvas.style.width = this.size + 'px';
    canvas.style.height = this.size + 'px';

    this.state = 'boot';
    this.config = this._cloneConfig(STATES.boot);
    this.phase = 0;
    this.transitioning = false;
    this.transStart = 0;
    this.transFrom = this.config;
    this.transTo = this.config;
    this.flashStart = 0;
    this.lastFrame = 0;
    this.running = false;

    this.autoMode = !!opts.autoMode;
    this.autoCycleIdx = 0;
    this.autoTimer = null;

    // Image data (populated after load)
    this.pathwayMask = null;
    this.waveDist = null;
    this.depthMap = null;
    this.brainRgb = null;
    this.brainAlpha = null;
    this.sweepX = null;
    this.depthDelay = null;
    this.depthAtten = null;
    this.imgData = null;

    this.onStateChange = opts.onStateChange || null;

    var self = this;
    var img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = function() { self._processImage(img); self.start(); };
    img.src = opts.imageSrc || 'assets/brain.png';
}

NeuralCortex.prototype._cloneConfig = function(c) {
    return { waveCount:c.waveCount, speed:c.speed, sigma:c.sigma,
             hueCenter:c.hueCenter, hueRange:c.hueRange, baseBri:c.baseBri,
             intensity:c.intensity, fps:c.fps, sat:c.sat, mode:c.mode };
};

NeuralCortex.prototype._processImage = function(img) {
    var s = this.renderSize;
    var tc = document.createElement('canvas');
    tc.width = s; tc.height = s;
    var tctx = tc.getContext('2d');
    tctx.drawImage(img, 0, 0, s, s);
    var id = tctx.getImageData(0, 0, s, s);
    var d = id.data;
    var n = s * s;

    this.pathwayMask = new Float32Array(n);
    this.waveDist = new Float32Array(n);
    this.depthMap = new Float32Array(n);
    this.brainRgb = new Float32Array(n * 3);
    this.brainAlpha = new Float32Array(n);
    this.sweepX = new Float32Array(n);
    this.depthDelay = new Float32Array(n);
    this.depthAtten = new Float32Array(n);

    var cy = s / 2.0, cx = s / 2.0;
    var maxDist = Math.sqrt(cy * cy + cx * cx);

    for (var i = 0; i < n; i++) {
        var idx = i * 4;
        var r = d[idx] / 255.0, g = d[idx+1] / 255.0, b = d[idx+2] / 255.0;
        var a = d[idx+3] / 255.0;
        var bri = Math.max(r, g, b);
        var ba = bri * a;

        this.brainRgb[i*3] = d[idx];
        this.brainRgb[i*3+1] = d[idx+1];
        this.brainRgb[i*3+2] = d[idx+2];
        this.brainAlpha[i] = a;
        this.pathwayMask[i] = Math.pow(clamp(ba, 0, 1), 0.7);
        this.depthMap[i] = 1.0 - Math.pow(clamp(ba, 0, 1), 0.5);

        var y = Math.floor(i / s), x = i % s;
        var dy = y - cy, dx = x - cx;
        this.waveDist[i] = Math.sqrt(dy*dy + dx*dx) / maxDist;
        this.sweepX[i] = x / s;

        this.depthDelay[i] = this.depthMap[i] * 0.3;
        this.depthAtten[i] = 1.0 - this.depthMap[i] * 0.5;
    }

    this.imgData = this.ctx.createImageData(s, s);
};

NeuralCortex.prototype.setState = function(newState) {
    if (!STATES[newState]) return;
    if (newState === this.state && !this.transitioning) return;
    this.transFrom = this._getConfig();
    this.transTo = this._cloneConfig(STATES[newState]);
    this.transStart = performance.now() / 1000;
    this.transitioning = true;
    this.state = newState;
    if (newState === 'swapping' || newState === 'error' || newState === 'threat') {
        this.flashStart = performance.now() / 1000;
    }
    if (this.onStateChange) this.onStateChange(newState);
};

NeuralCortex.prototype._getConfig = function() {
    if (!this.transitioning) return this.config;
    var elapsed = performance.now() / 1000 - this.transStart;
    var t = Math.min(elapsed / TRANS_DUR, 1.0);
    if (t >= 1.0) {
        this.transitioning = false;
        this.config = this._cloneConfig(this.transTo);
        return this.config;
    }
    t = smoothstep(t);
    this.config = {
        waveCount: Math.round(lerp(this.transFrom.waveCount, this.transTo.waveCount, t)),
        speed: lerp(this.transFrom.speed, this.transTo.speed, t),
        sigma: lerp(this.transFrom.sigma, this.transTo.sigma, t),
        hueCenter: lerp(this.transFrom.hueCenter, this.transTo.hueCenter, t),
        hueRange: lerp(this.transFrom.hueRange, this.transTo.hueRange, t),
        baseBri: lerp(this.transFrom.baseBri, this.transTo.baseBri, t),
        intensity: lerp(this.transFrom.intensity, this.transTo.intensity, t),
        fps: Math.round(lerp(this.transFrom.fps, this.transTo.fps, t)),
        sat: lerp(this.transFrom.sat, this.transTo.sat, t),
        mode: this.transTo.mode
    };
    return this.config;
};

NeuralCortex.prototype.start = function() {
    if (this.running) return;
    this.running = true;
    this.lastFrame = performance.now();
    this._tick();
    if (this.autoMode) this._startAutoCycle();
};

NeuralCortex.prototype.stop = function() {
    this.running = false;
    if (this.autoTimer) { clearTimeout(this.autoTimer); this.autoTimer = null; }
};

NeuralCortex.prototype.setAutoMode = function(on) {
    this.autoMode = on;
    if (on) this._startAutoCycle();
    else if (this.autoTimer) { clearTimeout(this.autoTimer); this.autoTimer = null; }
};

NeuralCortex.prototype._startAutoCycle = function() {
    var self = this;
    if (this.autoTimer) clearTimeout(this.autoTimer);
    this.autoTimer = setTimeout(function cycle() {
        if (!self.running || !self.autoMode) return;
        self.autoCycleIdx = (self.autoCycleIdx + 1) % AUTO_CYCLE.length;
        self.setState(AUTO_CYCLE[self.autoCycleIdx]);
        self.autoTimer = setTimeout(cycle, AUTO_INTERVAL);
    }, AUTO_INTERVAL);
};

NeuralCortex.prototype._tick = function() {
    if (!this.running || !this.pathwayMask) return;
    var now = performance.now();
    var cfg = this._getConfig();
    var interval = 1000 / cfg.fps;
    if (now - this.lastFrame >= interval) {
        var dt = (now - this.lastFrame) / 1000;
        this.phase += dt;
        this.lastFrame = now;
        this._renderFrame(cfg);
    }
    var self = this;
    requestAnimationFrame(function() { self._tick(); });
};

NeuralCortex.prototype._renderFrame = function(cfg) {
    var s = this.renderSize;
    var n = s * s;
    var data = this.imgData.data;
    var waveTotal = new Float32Array(n);
    var hueArr = new Float32Array(n);

    // Calculate waves based on render mode
    if (cfg.mode === 'spiral') {
        this._calcSpiral(cfg, waveTotal, hueArr, s);
    } else if (cfg.mode === 'sweep') {
        this._calcSweep(cfg, waveTotal, hueArr, s);
    } else if (cfg.mode === 'threat') {
        this._calcThreat(cfg, waveTotal, hueArr, s);
    } else if (cfg.mode === 'flash') {
        this._calcFlash(cfg, waveTotal, hueArr, s, data);
        // Flash handles its own compositing for the initial burst
        if (performance.now() / 1000 - this.flashStart < 0.3) {
            this.ctx.putImageData(this.imgData, 0, 0);
            return;
        }
    } else if (cfg.mode === 'pulse') {
        this._calcPulse(cfg, waveTotal, hueArr, s);
    } else {
        this._calcRadial(cfg, waveTotal, hueArr, s);
    }

    // Composite: glow over brain
    for (var i = 0; i < n; i++) {
        var wt = clamp(waveTotal[i], 0, 1.5);
        var h = ((hueArr[i] % 1.0) + 1.0) % 1.0;
        var rgb = hsvToRgb(h, cfg.sat, 1.0);
        var gf0 = 1.0 + wt * rgb[0] * 2.0;
        var gf1 = 1.0 + wt * rgb[1] * 2.0;
        var gf2 = 1.0 + wt * rgb[2] * 2.0;
        var br = this.brainRgb[i*3] * cfg.baseBri / 255.0 * gf0;
        var bg = this.brainRgb[i*3+1] * cfg.baseBri / 255.0 * gf1;
        var bb = this.brainRgb[i*3+2] * cfg.baseBri / 255.0 * gf2;
        var af = this.brainAlpha[i];
        var idx = i * 4;
        data[idx]   = clamp(Math.round(br * af * 255 + BG_COLOR[0] * (1 - af)), 0, 255);
        data[idx+1] = clamp(Math.round(bg * af * 255 + BG_COLOR[1] * (1 - af)), 0, 255);
        data[idx+2] = clamp(Math.round(bb * af * 255 + BG_COLOR[2] * (1 - af)), 0, 255);
        data[idx+3] = 255;
    }
    this.ctx.putImageData(this.imgData, 0, 0);
};

NeuralCortex.prototype._calcRadial = function(cfg, waveTotal, hueArr, s) {
    var n = s * s;
    for (var wi = 0; wi < cfg.waveCount; wi++) {
        var offset = wi / Math.max(cfg.waveCount, 1);
        var wp = (this.phase * cfg.speed + offset) % 1.3;
        var sig2 = 2 * cfg.sigma * cfg.sigma;
        var hue = (cfg.hueCenter + cfg.hueRange * Math.sin(this.phase * 0.3 + wi * 2.09)) % 1.0;
        for (var i = 0; i < n; i++) {
            var adj = this.waveDist[i] + this.depthDelay[i];
            var diff = adj - wp;
            var wave = Math.exp(-(diff * diff) / sig2);
            wave *= this.pathwayMask[i] * this.depthAtten[i] * cfg.intensity;
            waveTotal[i] += wave;
            hueArr[i] += wave * hue;
        }
    }
    // Average hue
    for (var i = 0; i < n; i++) {
        if (waveTotal[i] > 0.001) hueArr[i] = (hueArr[i] / waveTotal[i]) % 1.0;
        else hueArr[i] = cfg.hueCenter;
    }
};

NeuralCortex.prototype._calcSpiral = function(cfg, waveTotal, hueArr, s) {
    var n = s * s;
    var cy = s / 2.0, cx = s / 2.0;
    var sp = (this.phase * cfg.speed) % 1.5;
    var sig2 = 2 * cfg.sigma * cfg.sigma;
    var bootP = Math.min(this.phase * cfg.speed / 3.0, 1.0);
    for (var i = 0; i < n; i++) {
        var y = Math.floor(i / s), x = i % s;
        var angle = Math.atan2(y - cy, x - cx) / (2 * Math.PI) + 0.5;
        var sd = (this.waveDist[i] + angle * 0.3) % 1.5;
        var diff = sd - sp;
        var wave = Math.exp(-(diff * diff) / sig2);
        wave *= this.pathwayMask[i] * this.depthAtten[i] * cfg.intensity;
        waveTotal[i] = clamp(wave, 0, 1.5);
        hueArr[i] = cfg.hueCenter;
    }
};

NeuralCortex.prototype._calcSweep = function(cfg, waveTotal, hueArr, s) {
    var n = s * s;
    for (var wi = 0; wi < cfg.waveCount; wi++) {
        var offset = wi / Math.max(cfg.waveCount, 1);
        var sp = (this.phase * cfg.speed + offset) % 1.4;
        var sig2 = 2 * cfg.sigma * cfg.sigma;
        for (var i = 0; i < n; i++) {
            var diff = this.sweepX[i] - sp;
            var wave = Math.exp(-(diff * diff) / sig2);
            wave *= this.pathwayMask[i] * this.depthAtten[i] * cfg.intensity;
            waveTotal[i] += wave;
        }
    }
    for (var i = 0; i < n; i++) {
        waveTotal[i] = clamp(waveTotal[i], 0, 1.5);
        hueArr[i] = cfg.hueCenter;
    }
};

NeuralCortex.prototype._calcFlash = function(cfg, waveTotal, hueArr, s, data) {
    var n = s * s;
    var elapsed = performance.now() / 1000 - this.flashStart;
    if (elapsed < 0.3) {
        var flashInt = cfg.intensity * (1.0 - (elapsed / 0.3) * 0.3);
        for (var i = 0; i < n; i++) {
            var wave = this.pathwayMask[i] * this.depthAtten[i] * flashInt;
            var br = this.brainRgb[i*3] / 255.0 * cfg.baseBri;
            var bg = this.brainRgb[i*3+1] / 255.0 * cfg.baseBri;
            var bb = this.brainRgb[i*3+2] / 255.0 * cfg.baseBri;
            var gf = 1.0 + clamp(wave, 0, 1.5) * 2.0;
            var af = this.brainAlpha[i];
            var idx = i * 4;
            data[idx]   = clamp(Math.round((br * gf) * af * 255 + BG_COLOR[0] * (1-af)), 0, 255);
            data[idx+1] = clamp(Math.round((bg * gf) * af * 255 + BG_COLOR[1] * (1-af)), 0, 255);
            data[idx+2] = clamp(Math.round((bb * gf) * af * 255 + BG_COLOR[2] * (1-af)), 0, 255);
            data[idx+3] = 255;
        }
        return;
    }
    // After flash: fade to radial
    var fade = Math.min((elapsed - 0.3) / 1.0, 1.0);
    var radCfg = {
        waveCount:1, speed:cfg.speed, sigma:cfg.sigma * (2 - fade),
        hueCenter:0.52, hueRange:0.02, baseBri:cfg.baseBri,
        intensity:cfg.intensity * fade, fps:cfg.fps,
        sat:0.6 + 0.2 * fade, mode:'radial'
    };
    this._calcRadial(radCfg, waveTotal, hueArr, s);
};

NeuralCortex.prototype._calcThreat = function(cfg, waveTotal, hueArr, s) {
    // Sustained aggressive red pulses — never stops, never calms down
    var n = s * s;
    var sig2 = 2 * cfg.sigma * cfg.sigma;

    // Multiple overlapping waves continuously expanding outward
    for (var wi = 0; wi < cfg.waveCount; wi++) {
        var offset = wi / cfg.waveCount;
        var wp = (this.phase * cfg.speed + offset) % 1.3;
        // Slight hue variation between deep red and blood red
        var hue = cfg.hueCenter + cfg.hueRange * Math.sin(this.phase * 2.0 + wi * 1.26);
        for (var i = 0; i < n; i++) {
            var adj = this.waveDist[i] + this.depthDelay[i];
            var diff = adj - wp;
            var wave = Math.exp(-(diff * diff) / sig2);
            wave *= this.pathwayMask[i] * this.depthAtten[i] * cfg.intensity;
            waveTotal[i] += wave;
            hueArr[i] += wave * hue;
        }
    }

    // Global throb — entire brain pulses in brightness at ~3Hz
    var throb = 0.6 + 0.4 * Math.abs(Math.sin(this.phase * 9.5));
    // Random crackle spikes
    var crackle = Math.random() < 0.3 ? 0.2 + Math.random() * 0.3 : 0;

    for (var i = 0; i < n; i++) {
        waveTotal[i] = clamp(waveTotal[i] * throb + this.pathwayMask[i] * crackle, 0, 2.0);
        if (waveTotal[i] > 0.001) hueArr[i] = (hueArr[i] / (waveTotal[i] / throb + 0.001)) % 1.0;
        else hueArr[i] = cfg.hueCenter;
    }
};

NeuralCortex.prototype._calcPulse = function(cfg, waveTotal, hueArr, s) {
    var n = s * s;
    var elapsed = performance.now() / 1000 - this.flashStart;
    var decay = Math.max(0, 1.0 - elapsed / 1.5);
    var wp = Math.min(elapsed * 0.8, 1.2);
    var sig2 = 2 * cfg.sigma * cfg.sigma;
    for (var i = 0; i < n; i++) {
        var diff = this.waveDist[i] - wp;
        var wave = Math.exp(-(diff * diff) / sig2);
        wave *= this.pathwayMask[i] * this.depthAtten[i] * cfg.intensity * decay;
        waveTotal[i] = clamp(wave, 0, 1.5);
        hueArr[i] = cfg.hueCenter;
    }
};

window.NeuralCortex = NeuralCortex;
})();
