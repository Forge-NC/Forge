/**
 * Cyberpunk Visual Effects — Particles + Edge Glow
 * Applied to demo sections only via data-effects attribute.
 *
 * Usage:
 *   <div class="effects-container" data-effects="particles edge-glow">
 *     ...content...
 *   </div>
 */
(function() {
'use strict';

var PARTICLE_COLORS = ['#00ffff', '#ff2d95', '#cc44ff', '#0088ff'];
var EDGE_PALETTE = ['#00ffff', '#0088ff', '#ff2d95', '#cc44ff', '#00ffff'];

// ── Particle Field ──

function ParticleField(container) {
    this.container = container;
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'effects-canvas';
    this.canvas.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;';
    container.style.position = 'relative';
    container.insertBefore(this.canvas, container.firstChild);
    this.ctx = this.canvas.getContext('2d');
    this.particles = [];
    this.running = false;
    this._resize();
    this._initParticles(22);
    var self = this;
    window.addEventListener('resize', function() { self._resize(); });
}

ParticleField.prototype._resize = function() {
    var r = this.container.getBoundingClientRect();
    this.canvas.width = r.width;
    this.canvas.height = r.height;
    this.w = r.width;
    this.h = r.height;
};

ParticleField.prototype._initParticles = function(count) {
    this.particles = [];
    for (var i = 0; i < count; i++) {
        this.particles.push(this._spawn(true));
    }
};

ParticleField.prototype._spawn = function(randomY) {
    return {
        x: Math.random() * this.w,
        y: randomY ? Math.random() * this.h : this.h + 10,
        vx: (Math.random() - 0.5) * 0.6,
        vy: -(0.2 + Math.random() * 0.6),
        size: 1 + Math.random() * 2,
        brightness: 0.3 + Math.random() * 0.7,
        color: PARTICLE_COLORS[Math.floor(Math.random() * PARTICLE_COLORS.length)]
    };
};

ParticleField.prototype.start = function() {
    if (this.running) return;
    this.running = true;
    this._tick();
};

ParticleField.prototype.stop = function() { this.running = false; };

ParticleField.prototype._tick = function() {
    if (!this.running) return;
    var ctx = this.ctx;
    ctx.clearRect(0, 0, this.w, this.h);
    for (var i = 0; i < this.particles.length; i++) {
        var p = this.particles[i];
        p.x += p.vx;
        p.y += p.vy;
        p.brightness *= 0.998;
        if (p.y < -10 || p.brightness < 0.05) {
            this.particles[i] = this._spawn(false);
            continue;
        }
        ctx.globalAlpha = p.brightness * 0.6;
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
    }
    ctx.globalAlpha = 1;
    var self = this;
    requestAnimationFrame(function() { self._tick(); });
};

// ── Edge Glow ──

function EdgeGlow(container) {
    this.container = container;
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'edge-glow-canvas';
    this.canvas.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:1;';
    container.style.position = 'relative';
    container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext('2d');
    this.phase = Math.random() * 100;
    this.crackle = [0, 0, 0, 0]; // top, right, bottom, left
    this.sparks = [];
    this.running = false;
    this._resize();
    var self = this;
    window.addEventListener('resize', function() { self._resize(); });
}

EdgeGlow.prototype._resize = function() {
    var r = this.container.getBoundingClientRect();
    this.canvas.width = r.width;
    this.canvas.height = r.height;
    this.w = r.width;
    this.h = r.height;
};

EdgeGlow.prototype.start = function() {
    if (this.running) return;
    this.running = true;
    this._tick();
};

EdgeGlow.prototype.stop = function() { this.running = false; };

EdgeGlow.prototype._tick = function() {
    if (!this.running) return;
    this.phase += 0.02;
    var ctx = this.ctx;
    ctx.clearRect(0, 0, this.w, this.h);

    // Crackle + base glow for each edge
    for (var e = 0; e < 4; e++) {
        // Random crackle spike
        if (Math.random() < 0.12) this.crackle[e] = 0.6 + Math.random() * 0.4;
        this.crackle[e] *= 0.82;

        var baseBri = 0.25 + 0.25 * Math.sin(this.phase * 1.5 + e * 1.57) + 0.5 * this.crackle[e];
        baseBri = Math.min(baseBri, 1.0);

        // Palette color cycling
        var palIdx = ((this.phase * 0.3 + e * 0.7) % EDGE_PALETTE.length);
        var ci = Math.floor(palIdx) % EDGE_PALETTE.length;
        var cn = (ci + 1) % EDGE_PALETTE.length;
        var frac = palIdx - Math.floor(palIdx);
        frac = frac * frac * (3.0 - 2.0 * frac); // smoothstep

        var c1 = this._parseColor(EDGE_PALETTE[ci]);
        var c2 = this._parseColor(EDGE_PALETTE[cn]);
        var cr = Math.round(c1[0] + (c2[0] - c1[0]) * frac);
        var cg = Math.round(c1[1] + (c2[1] - c1[1]) * frac);
        var cb = Math.round(c1[2] + (c2[2] - c1[2]) * frac);

        // Draw edge glow
        var grad;
        ctx.globalAlpha = baseBri * 0.4;
        if (e === 0) { // top
            grad = ctx.createLinearGradient(0, 0, 0, 3);
            grad.addColorStop(0, 'rgb('+cr+','+cg+','+cb+')');
            grad.addColorStop(1, 'transparent');
            ctx.fillStyle = grad;
            ctx.fillRect(0, 0, this.w, 3);
        } else if (e === 1) { // right
            grad = ctx.createLinearGradient(this.w, 0, this.w - 3, 0);
            grad.addColorStop(0, 'rgb('+cr+','+cg+','+cb+')');
            grad.addColorStop(1, 'transparent');
            ctx.fillStyle = grad;
            ctx.fillRect(this.w - 3, 0, 3, this.h);
        } else if (e === 2) { // bottom
            grad = ctx.createLinearGradient(0, this.h, 0, this.h - 3);
            grad.addColorStop(0, 'rgb('+cr+','+cg+','+cb+')');
            grad.addColorStop(1, 'transparent');
            ctx.fillStyle = grad;
            ctx.fillRect(0, this.h - 3, this.w, 3);
        } else { // left
            grad = ctx.createLinearGradient(0, 0, 3, 0);
            grad.addColorStop(0, 'rgb('+cr+','+cg+','+cb+')');
            grad.addColorStop(1, 'transparent');
            ctx.fillStyle = grad;
            ctx.fillRect(0, 0, 3, this.h);
        }

        // Spawn sparks
        if (Math.random() < 0.15) {
            this.sparks.push({
                edge: e,
                pos: Math.random(),
                speed: (Math.random() - 0.5) * 0.04,
                brightness: 0.8 + Math.random() * 0.2,
                color: [cr, cg, cb]
            });
            if (this.sparks.length > 32) this.sparks.shift();
        }
    }

    // Draw sparks
    for (var si = this.sparks.length - 1; si >= 0; si--) {
        var sp = this.sparks[si];
        sp.pos += sp.speed;
        sp.brightness *= 0.90;
        if (sp.brightness < 0.05 || sp.pos < -0.1 || sp.pos > 1.1) {
            this.sparks.splice(si, 1);
            continue;
        }
        var boosted = [
            Math.min(255, sp.color[0] + Math.round(180 * sp.brightness)),
            Math.min(255, sp.color[1] + Math.round(180 * sp.brightness)),
            Math.min(255, sp.color[2] + Math.round(180 * sp.brightness))
        ];
        ctx.globalAlpha = sp.brightness * 0.8;
        ctx.fillStyle = 'rgb('+boosted[0]+','+boosted[1]+','+boosted[2]+')';
        var sx, sy;
        if (sp.edge === 0) { sx = sp.pos * this.w; sy = 1; }
        else if (sp.edge === 1) { sx = this.w - 1; sy = sp.pos * this.h; }
        else if (sp.edge === 2) { sx = sp.pos * this.w; sy = this.h - 1; }
        else { sx = 1; sy = sp.pos * this.h; }
        ctx.beginPath();
        ctx.arc(sx, sy, 2, 0, Math.PI * 2);
        ctx.fill();
    }
    ctx.globalAlpha = 1;

    var self = this;
    requestAnimationFrame(function() { self._tick(); });
};

EdgeGlow.prototype._parseColor = function(hex) {
    return [
        parseInt(hex.substr(1, 2), 16),
        parseInt(hex.substr(3, 2), 16),
        parseInt(hex.substr(5, 2), 16)
    ];
};

// ── Auto-init via IntersectionObserver ──

function initEffects() {
    var containers = document.querySelectorAll('[data-effects]');
    if (!containers.length) return;

    var observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            var el = entry.target;
            if (entry.isIntersecting) {
                if (el._particles) el._particles.start();
                if (el._edgeGlow) el._edgeGlow.start();
            } else {
                if (el._particles) el._particles.stop();
                if (el._edgeGlow) el._edgeGlow.stop();
            }
        });
    }, { threshold: 0.1 });

    containers.forEach(function(el) {
        var effects = el.getAttribute('data-effects');
        if (effects.indexOf('particles') !== -1) {
            el._particles = new ParticleField(el);
        }
        if (effects.indexOf('edge-glow') !== -1) {
            el._edgeGlow = new EdgeGlow(el);
        }
        observer.observe(el);
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initEffects);
} else {
    initEffects();
}

window.ParticleField = ParticleField;
window.EdgeGlow = EdgeGlow;
})();
