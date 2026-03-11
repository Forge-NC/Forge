<?php
/**
 * Forge V2 Landing Page — Sleek, concise, conversion-focused.
 */
$tiers_file = __DIR__ . '/../Forge/data/tiers_config.json';
$tiers = [];
if (file_exists($tiers_file)) {
    $tiers = json_decode(file_get_contents($tiers_file), true) ?: [];
}
// Strip internal-only tier
unset($tiers['origin']);
$version = '0.9.0';
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Forge — Local AI Coding Assistant</title>
<meta name="description" content="Forge is a local-first AI coding assistant. Runs on your GPU. Your code never leaves your machine.">
<meta property="og:title" content="Forge — Your AI. Your GPU. Your Code.">
<meta property="og:description" content="54,207 lines of fully transparent AI coding infrastructure running entirely on your hardware. No cloud. Telemetry opt-in only. No exceptions.">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preload" href="../Forge/assets/brain.png" as="image" type="image/png">
<link rel="preload" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" as="style">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* ── Reset & Base ─────────────────────────────────────────────── */
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
:root {
    --bg:         #07080c;
    --bg-surface: #0c0d14;
    --bg-card:    #111219;
    --bg-card-up: #16171f;
    --border:     rgba(255,255,255,0.06);
    --border-lit: rgba(255,255,255,0.10);
    --text:       #e4e6ed;
    --text-dim:   #8b8fa2;
    --text-xdim:  #555770;
    --accent:     #00d4ff;
    --accent-dim: rgba(0,212,255,0.10);
    --purple:     #9d7aff;
    --green:      #34d399;
    --amber:      #f59e0b;
    --red:        #f87171;
    --radius:     10px;
    --radius-lg:  16px;
    --font:       'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    --mono:       'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace;
    --max-w:      1120px;
}
html { scroll-behavior: smooth; -webkit-font-smoothing: antialiased; }
body {
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    overflow-x: hidden;
}
/* dot grid */
body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image: radial-gradient(circle at 1px 1px, rgba(255,255,255,0.018) 1px, transparent 0);
    background-size: 28px 28px;
    pointer-events: none;
    z-index: 0;
}
a { color: var(--accent); text-decoration: none; transition: opacity 0.2s; }
a:hover { opacity: 0.8; }
img { max-width: 100%; display: block; }
.container { max-width: var(--max-w); margin: 0 auto; padding: 0 24px; position: relative; z-index: 1; }

/* ── Scroll reveal ────────────────────────────────────────────── */
/* Gated behind JS-added class so content is visible without JS */
html.reveal-ready .reveal {
    opacity: 0;
    transform: translateY(28px);
    transition: opacity 0.7s cubic-bezier(.22,1,.36,1), transform 0.7s cubic-bezier(.22,1,.36,1);
}
html.reveal-ready .reveal.visible {
    opacity: 1;
    transform: none; /* 'none' does NOT establish a containing block unlike translateY(0) */
}

/* ── Nav ──────────────────────────────────────────────────────── */
.nav {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 100;
    padding: 0 24px;
    transition: background 0.3s, backdrop-filter 0.3s;
}
.nav.scrolled {
    background: rgba(7,8,12,0.82);
    backdrop-filter: blur(16px) saturate(1.4);
    -webkit-backdrop-filter: blur(16px) saturate(1.4);
    border-bottom: 1px solid var(--border);
}
.nav-inner {
    max-width: var(--max-w);
    margin: 0 auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 64px;
}
.nav-logo {
    font-weight: 800;
    font-size: 1.15rem;
    letter-spacing: 0.12em;
    color: var(--text);
    text-transform: uppercase;
}
.nav-logo:hover { opacity: 1; color: var(--accent); }
.nav-links { display: flex; align-items: center; gap: 32px; }
.nav-links a { color: var(--text-dim); font-size: 0.875rem; font-weight: 500; }
.nav-links a:hover { color: var(--text); opacity: 1; }
.nav-cta {
    background: var(--accent);
    color: var(--bg) !important;
    padding: 8px 20px;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.8125rem !important;
    letter-spacing: 0.02em;
    transition: transform 0.2s, box-shadow 0.2s;
}
.nav-cta:hover { transform: translateY(-1px); box-shadow: 0 4px 20px rgba(0,212,255,0.25); opacity: 1 !important; }
.nav-toggle {
    display: none;
    flex-direction: column;
    gap: 5px;
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px;
}
.nav-toggle span {
    display: block;
    width: 22px;
    height: 2px;
    background: var(--text-dim);
    border-radius: 2px;
    transition: 0.25s;
}

/* ── Buttons ──────────────────────────────────────────────────── */
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 14px 32px;
    border-radius: var(--radius);
    font-weight: 600;
    font-size: 0.9375rem;
    letter-spacing: 0.01em;
    transition: transform 0.2s, box-shadow 0.2s, background 0.2s;
    cursor: pointer;
    border: none;
    text-decoration: none;
}
.btn-primary {
    background: var(--accent);
    color: var(--bg);
}
.btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(0,212,255,0.3);
    opacity: 1;
}
.btn-ghost {
    background: transparent;
    color: var(--text-dim);
    border: 1px solid var(--border-lit);
}
.btn-ghost:hover {
    border-color: var(--accent);
    color: var(--text);
    opacity: 1;
}
.btn-sm { padding: 10px 24px; font-size: 0.8125rem; }
.btn-block { width: 100%; }

/* ── Hero ─────────────────────────────────────────────────────── */
.hero {
    position: relative;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 120px 24px 80px;
    overflow: hidden;
}
.hero-split {
    display: flex;
    align-items: center;
    gap: 56px;
    max-width: var(--max-w);
    width: 100%;
    position: relative;
    z-index: 1;
}
.hero-text { flex: 1; }
.hero-cortex-wrap { flex-shrink: 0; text-align: center; }
.hero-glow {
    position: absolute;
    inset: 0;
    background:
        radial-gradient(ellipse 60% 50% at 30% 40%, rgba(0,212,255,0.06) 0%, transparent 70%),
        radial-gradient(ellipse 50% 60% at 70% 30%, rgba(157,122,255,0.04) 0%, transparent 70%),
        radial-gradient(ellipse 80% 40% at 50% 90%, rgba(0,212,255,0.03) 0%, transparent 70%);
    animation: aurora 25s ease-in-out infinite alternate;
    pointer-events: none;
}
@keyframes aurora {
    0% { transform: translate(0, 0) scale(1); }
    50% { transform: translate(-3%, 2%) scale(1.03); }
    100% { transform: translate(2%, -2%) scale(0.98); }
}
.hero-content { position: relative; z-index: 1; max-width: 720px; } /* legacy */
.hero-badge {
    display: inline-block;
    font-family: var(--mono);
    font-size: 0.75rem;
    color: var(--accent);
    border: 1px solid var(--accent-dim);
    background: rgba(0,212,255,0.05);
    padding: 6px 16px;
    border-radius: 100px;
    margin-bottom: 32px;
    letter-spacing: 0.06em;
}
.hero-title {
    font-size: clamp(3.5rem, 11vw, 8rem);
    font-weight: 800;
    letter-spacing: -0.045em;
    line-height: 0.95;
    margin-bottom: 24px;
    background: linear-gradient(135deg, #fff 10%, var(--accent) 60%, var(--purple) 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 80px rgba(0,212,255,0.15));
}
.hero-subtitle {
    font-size: clamp(1.125rem, 2.2vw, 1.5rem);
    font-weight: 500;
    color: var(--text);
    margin-bottom: 16px;
    line-height: 1.4;
}
.hero-body {
    font-size: 1.0625rem;
    color: var(--text-dim);
    max-width: 540px;
    margin: 0 auto 40px;
    line-height: 1.7;
}
.hero-actions { display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; }
.scroll-hint {
    position: absolute;
    bottom: 32px;
    left: 50%;
    transform: translateX(-50%);
    animation: bobble 2.5s ease-in-out infinite;
    color: var(--text-xdim);
}
@keyframes bobble { 0%,100% { transform: translateX(-50%) translateY(0); } 50% { transform: translateX(-50%) translateY(8px); } }
.scroll-hint svg { width: 24px; height: 24px; }

/* ── Section Utility ──────────────────────────────────────────── */
.section { padding: 120px 0; }
.section-sm { padding: 80px 0; }
.section-header { text-align: center; margin-bottom: 64px; }
.section-header h2 {
    font-size: clamp(1.75rem, 3.5vw, 2.5rem);
    font-weight: 700;
    letter-spacing: -0.03em;
    margin-bottom: 16px;
}
.section-header p {
    color: var(--text-dim);
    font-size: 1.0625rem;
    max-width: 560px;
    margin: 0 auto;
}
.gradient-rule {
    width: 100%;
    height: 1px;
    background: radial-gradient(ellipse at center, var(--border-lit) 0%, transparent 70%);
    border: none;
    margin: 0;
}

/* ── Pillars ──────────────────────────────────────────────────── */
.pillar-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 24px;
}
.pillar-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 40px 32px;
    transition: border-color 0.3s, transform 0.3s, box-shadow 0.3s;
}
.pillar-card:hover {
    border-color: rgba(0,212,255,0.15);
    transform: translateY(-4px);
    box-shadow: 0 16px 48px rgba(0,0,0,0.3);
}
.pillar-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    background: var(--accent-dim);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 24px;
    color: var(--accent);
}
.pillar-icon svg { width: 24px; height: 24px; }
.pillar-card h3 {
    font-size: 1.25rem;
    font-weight: 700;
    margin-bottom: 12px;
    letter-spacing: -0.01em;
}
.pillar-card p {
    color: var(--text-dim);
    font-size: 0.9375rem;
    line-height: 1.7;
}

/* ── Terminal Demo ────────────────────────────────────────────── */
.terminal {
    background: #0a0c10;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: 0 24px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.02);
    max-width: 820px;
    margin: 0 auto;
}
.terminal-bar {
    background: #13151b;
    padding: 14px 20px;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid var(--border);
}
.terminal-dot { width: 12px; height: 12px; border-radius: 50%; }
.terminal-dot.r { background: #ff5f57; }
.terminal-dot.y { background: #febc2e; }
.terminal-dot.g { background: #28c840; }
.terminal-bar-title {
    flex: 1;
    text-align: center;
    font-family: var(--mono);
    font-size: 0.75rem;
    color: var(--text-xdim);
    margin-right: 44px;
}
.terminal-body {
    padding: 24px 28px;
    font-family: var(--mono);
    font-size: 0.8125rem;
    line-height: 1.8;
    overflow-x: auto;
    white-space: pre;
    color: var(--text-dim);
}
.t-prompt { color: var(--accent); font-weight: 500; }
.t-cmd    { color: var(--text); }
.t-pass   { color: var(--green); }
.t-info   { color: var(--accent); }
.t-warn   { color: var(--amber); }
.t-file   { color: var(--purple); }
.t-dim    { color: var(--text-xdim); }
.t-bold   { color: var(--text); font-weight: 600; }

/* ── Why Local ────────────────────────────────────────────────── */
.why-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 64px;
    align-items: start;
}
.why-grid h2 {
    font-size: clamp(1.5rem, 3vw, 2.25rem);
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.25;
    margin-bottom: 24px;
}
.why-grid p {
    color: var(--text-dim);
    font-size: 0.9375rem;
    line-height: 1.8;
    margin-bottom: 16px;
}
.why-grid p:last-child { margin-bottom: 0; }
.why-highlight {
    color: var(--text);
    font-weight: 500;
}

/* ── Feature Grid (Free tier) ─────────────────────────────────── */
.feat-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
}
.feat-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 20px;
    border-radius: var(--radius);
    background: var(--bg-surface);
    border: 1px solid var(--border);
    font-size: 0.9rem;
    font-weight: 500;
    transition: border-color 0.2s;
}
.feat-item:hover { border-color: var(--border-lit); }
.feat-check {
    color: var(--green);
    font-size: 0.875rem;
    flex-shrink: 0;
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* ── Numbers Strip ────────────────────────────────────────────── */
.numbers-strip {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 48px;
    padding: 64px 0;
}
.stat { text-align: center; }
.stat-num {
    display: block;
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    font-family: var(--mono);
    color: var(--text);
    margin-bottom: 4px;
}
.stat-label {
    font-size: 0.8125rem;
    color: var(--text-xdim);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 500;
}

/* ── Pricing ──────────────────────────────────────────────────── */
.pricing-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 14px;
    margin-bottom: 48px;
}
.toggle-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-xdim);
    cursor: pointer;
    transition: color 0.2s;
}
.toggle-label.active { color: var(--text); }
.toggle-switch {
    width: 48px;
    height: 26px;
    background: var(--bg-card-up);
    border: 1px solid var(--border-lit);
    border-radius: 100px;
    position: relative;
    cursor: pointer;
    transition: background 0.2s;
    padding: 0;
}
.toggle-thumb {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 18px;
    height: 18px;
    background: var(--accent);
    border-radius: 50%;
    transition: transform 0.25s cubic-bezier(.4,0,.2,1);
}
.toggle-switch.on .toggle-thumb { transform: translateX(22px); }
.pricing-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 24px;
    align-items: start;
}
.price-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 40px 32px;
    transition: border-color 0.3s, transform 0.3s;
    position: relative;
}
.price-card:hover {
    border-color: rgba(0,212,255,0.12);
    transform: translateY(-4px);
}
.price-card.featured {
    border-color: rgba(0,212,255,0.2);
    box-shadow: 0 0 60px rgba(0,212,255,0.06);
}
.price-badge {
    position: absolute;
    top: -12px;
    left: 50%;
    transform: translateX(-50%);
    font-family: var(--mono);
    font-size: 0.6875rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--bg);
    background: var(--accent);
    padding: 4px 14px;
    border-radius: 100px;
}
.price-tier {
    font-size: 0.8125rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-dim);
    margin-bottom: 12px;
}
.price-amount {
    font-size: 2.5rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    margin-bottom: 4px;
}
.price-term {
    font-size: 0.8125rem;
    color: var(--text-xdim);
    margin-bottom: 28px;
}
.price-features {
    list-style: none;
    margin-bottom: 32px;
}
.price-features li {
    padding: 8px 0;
    font-size: 0.875rem;
    color: var(--text-dim);
    display: flex;
    align-items: center;
    gap: 10px;
    border-bottom: 1px solid rgba(255,255,255,0.03);
}
.price-features li:last-child { border-bottom: none; }
.price-features .ck { color: var(--green); flex-shrink: 0; }
.price-features .xk { color: var(--text-xdim); flex-shrink: 0; }

/* ── Neural Cortex ───────────────────────────────────────────── */
.cortex-canvas-wrap {
    position: relative;
    display: inline-block;
    border-radius: 50%;
    box-shadow: 0 0 80px rgba(0,212,255,0.2), 0 0 160px rgba(0,212,255,0.06);
}
.cortex-state-label {
    display: block;
    text-align: center;
    margin-top: 12px;
    font-family: var(--mono);
    font-size: 0.82em;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 2px;
}
.cortex-demo {
    display: flex;
    align-items: flex-start;
    gap: 48px;
    max-width: 900px;
    margin: 0 auto;
}
.cortex-panel { flex: 1; min-width: 0; }
.cortex-controls {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-bottom: 20px;
}
.cortex-btn {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 10px 8px;
    color: var(--text-dim);
    font-family: var(--mono);
    font-size: 0.8em;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 8px;
}
.cortex-btn:hover { border-color: var(--border-lit); color: var(--text); }
.cortex-btn.active { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }
.cortex-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}
.cortex-desc {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    color: var(--text-dim);
    line-height: 1.7;
    min-height: 80px;
}
.cortex-desc strong { color: var(--text); }

/* ── Final CTA ────────────────────────────────────────────────── */
.final-cta {
    text-align: center;
    padding: 120px 24px;
    position: relative;
}
.final-cta h2 {
    font-size: clamp(1.75rem, 4vw, 2.75rem);
    font-weight: 700;
    letter-spacing: -0.03em;
    margin-bottom: 16px;
}
.final-cta p {
    color: var(--text-dim);
    font-size: 0.9375rem;
    margin-bottom: 36px;
}
.final-cta .btn-primary { padding: 16px 40px; font-size: 1rem; }

/* ── Footer ───────────────────────────────────────────────────── */
footer {
    border-top: 1px solid var(--border);
    padding: 40px 0;
}
.footer-inner {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
}
.footer-copy {
    font-size: 0.8125rem;
    color: var(--text-xdim);
}
.footer-links { display: flex; gap: 24px; }
.footer-links a {
    font-size: 0.8125rem;
    color: var(--text-xdim);
}
.footer-links a:hover { color: var(--text-dim); }

/* ── Mobile ───────────────────────────────────────────────────── */
@media (max-width: 900px) {
    .pillar-grid { grid-template-columns: 1fr; gap: 16px; }
    .pillar-card { padding: 28px 24px; }
    .why-grid { grid-template-columns: 1fr; gap: 40px; }
    .feat-grid { grid-template-columns: 1fr 1fr; }
    .pricing-grid { grid-template-columns: 1fr; max-width: 400px; margin: 0 auto; }
    .numbers-strip { gap: 32px; }
}
@media (max-width: 900px) {
    .hero-split { flex-direction: column-reverse; gap: 32px; text-align: center; }
    .cortex-demo { flex-direction: column; align-items: center; }
    .cortex-controls { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 640px) {
    .nav-links { display: none; position: absolute; top: 64px; left: 0; right: 0; flex-direction: column; background: rgba(7,8,12,0.96); backdrop-filter: blur(16px); padding: 16px 24px; gap: 16px; border-bottom: 1px solid var(--border); }
    .nav-links.open { display: flex; }
    .nav-toggle { display: flex; }
    .feat-grid { grid-template-columns: 1fr; }
    .hero { padding: 100px 24px 60px; min-height: auto; }
    .section { padding: 80px 0; }
    .hero-actions { flex-direction: column; align-items: center; }
    .terminal-body { font-size: 0.6875rem; padding: 16px 18px; }
    .stat-num { font-size: 1.5rem; }
}
</style>
</head>
<body>

<!-- ── Navigation ─────────────────────────────────────────────── -->
<nav class="nav" id="nav">
    <div class="nav-inner">
        <a href="#hero" class="nav-logo">Forge</a>
        <div class="nav-links" id="navLinks">
            <a href="docs.php">Docs</a>
            <a href="../Forge/matrix.php">Matrix</a>
            <a href="#pricing">Pricing</a>
            <a href="docs.php#install" class="nav-cta">Download</a>
        </div>
        <button class="nav-toggle" id="navToggle" aria-label="Menu">
            <span></span><span></span><span></span>
        </button>
    </div>
</nav>

<!-- ── Hero with Neural Cortex ─────────────────────────────────── -->
<section class="hero" id="hero">
    <div class="hero-glow"></div>
    <div class="hero-split">
        <div class="hero-text">
            <span class="hero-badge">v<?php echo $version; ?> &middot; Fully Transparent &middot; Local-First</span>
            <h1 class="hero-title">FORGE</h1>
            <p class="hero-subtitle">The AI coding assistant that never phones home.</p>
            <p class="hero-body">
                Run state-of-the-art language models on your own GPU. Every prompt,
                every line of code, every tool call &mdash; local, private, and yours.
            </p>
            <div class="hero-actions">
                <a href="docs.php#install" class="btn btn-primary">Get Forge Free</a>
                <a href="docs.php" class="btn btn-ghost">Read the Docs &rarr;</a>
            </div>
        </div>
        <div class="hero-cortex-wrap">
            <div class="cortex-canvas-wrap">
                <canvas id="hero-cortex" style="border-radius:50%"></canvas>
            </div>
            <span class="cortex-state-label" id="hero-state-label">booting</span>
        </div>
    </div>
    <div class="scroll-hint">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M12 5v14M5 12l7 7 7-7"/>
        </svg>
    </div>
</section>

<hr class="gradient-rule">

<!-- ── Pillars ─────────────────────────────────────────────────── -->
<section class="section" id="pillars">
    <div class="container">
        <div class="pillar-grid">
            <div class="pillar-card reveal">
                <div class="pillar-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>
                    </svg>
                </div>
                <h3>100% Local</h3>
                <p>
                    Forge ships with a full model manager &mdash; 80+ curated models across
                    5 categories, live registry search, plus OpenAI and Anthropic API backends.
                    No usage caps. Telemetry is opt-in only.
                    Unlimited tokens, forever.
                </p>
            </div>
            <div class="pillar-card reveal">
                <div class="pillar-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>
                    </svg>
                </div>
                <h3>Gets Smarter Over Time</h3>
                <p>
                    The Forge Genome captures what works across every session &mdash; model quirks,
                    failure patterns, recovery strategies. Encrypted locally. Your Day 100 Forge
                    is measurably better than Day 1.
                </p>
            </div>
            <div class="pillar-card reveal">
                <div class="pillar-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                    </svg>
                </div>
                <h3>9-Layer Security</h3>
                <p>
                    Crucible&trade; scans every prompt and every output through 9 independent layers.
                    Shell gating, sandboxing, semantic analysis, behavioral tripwires,
                    honeypots, output fencing, and more. Under 50ms.
                </p>
            </div>
        </div>
    </div>
</section>

<hr class="gradient-rule">

<!-- ── Terminal Demo ───────────────────────────────────────────── -->
<section class="section" id="demo">
    <div class="container">
        <div class="section-header reveal">
            <h2>See it work.</h2>
            <p>A real Forge session. Natural language in, verified code out.</p>
        </div>
        <div class="terminal reveal">
            <div class="terminal-bar">
                <div class="terminal-dot r"></div>
                <div class="terminal-dot y"></div>
                <div class="terminal-dot g"></div>
                <span class="terminal-bar-title">forge &mdash; terminal</span>
            </div>
            <div class="terminal-body"><span class="t-info">================================================================</span>
<span class="t-bold">  FORGE</span> <span class="t-dim">&mdash; Local AI Coding Assistant</span>
<span class="t-dim">  No tokens. No compaction. No bullshit.</span>
<span class="t-info">================================================================</span>

<span class="t-info">Safety: </span><span class="t-pass">STANDARD</span><span class="t-dim"> | Crucible&trade;: </span><span class="t-pass">ON</span><span class="t-dim"> | Tokenizer: tiktoken</span>
<span class="t-dim">Type /help for commands. /docs or F1 for documentation.</span>

<span class="t-pass">~/myproject &gt;</span> <span class="t-cmd">Add rate limiting middleware to the Express API</span>

I'll add a token bucket rate limiter with Redis backing. Let me
read the existing code first.

<span class="t-dim">&#9484;&#9472; </span><span class="t-file">read_file</span><span class="t-dim">(path='src/routes/api.ts')</span>
<span class="t-dim">&#9474; // Express API routes</span>
<span class="t-dim">&#9474; import express from 'express';</span>
<span class="t-dim">&#9474; ...</span>
<span class="t-dim">&#9492;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;</span>

<span class="t-dim">&#9484;&#9472; </span><span class="t-file">write_file</span><span class="t-dim">(path='src/middleware/rateLimit.ts')</span>
<span class="t-dim">&#9474; Created src/middleware/rateLimit.ts (47 lines)</span>
<span class="t-dim">&#9492;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;</span>

<span class="t-dim">&#9484;&#9472; </span><span class="t-file">edit_file</span><span class="t-dim">(path='src/routes/api.ts')</span>
<span class="t-dim">&#9474; Added import and middleware registration</span>
<span class="t-dim">&#9492;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;&#9472;</span>

Done. I created <span class="t-file">src/middleware/rateLimit.ts</span> with a token
bucket implementation using Redis, and wired it into the API
router with per-route configuration.

<span class="t-pass">~/myproject &gt;</span> <span class="t-cmd">/scan</span>

<span class="t-info">Scanning project: ~/myproject</span>
<span class="t-dim">  142 files scanned in 0.8s</span>
<span class="t-pass">  No threats detected</span></div>
        </div>
    </div>
</section>

<hr class="gradient-rule">

<!-- ── Why Local ───────────────────────────────────────────────── -->
<section class="section" id="why-local">
    <div class="container">
        <div class="why-grid reveal">
            <div>
                <h2>Your code shouldn't live on someone else's server.</h2>
                <p>
                    Cloud AI tools transmit every line you write. Proprietary logic,
                    database schemas, API keys &mdash; sent to servers you don't control,
                    stored in systems you can't audit, potentially used for training
                    models that compete with your product.
                </p>
                <p>
                    When their service goes down, your productivity goes with it.
                    When they change pricing, you pay or you leave.
                </p>
            </div>
            <div>
                <h2>Forge stays on your machine.</h2>
                <p>
                    The AI model runs on <span class="why-highlight">your GPU</span>.
                    Your data stays in <span class="why-highlight">your building</span>.
                    It works <span class="why-highlight">offline</span>. And because there's
                    no metered API, you'll never hit a token limit or see a surprise bill.
                </p>
                <p>
                    Every line of Forge is readable. No obfuscation. Telemetry off by default, opt-in only.
                    No analytics. Just 54,207 lines of transparent, auditable code.
                </p>
            </div>
        </div>
    </div>
</section>

<hr class="gradient-rule">

<!-- ── What You Get Free ──────────────────────────────────────── -->
<section class="section" id="features">
    <div class="container">
        <div class="section-header reveal">
            <h2>Everything you need. Free.</h2>
            <p>Community tier. No trial period. No time limit. No feature walls on core functionality.</p>
        </div>
        <div class="feat-grid reveal">
            <div class="feat-item"><span class="feat-check">&#10003;</span> 80+ models (local, OpenAI, Anthropic)</div>
            <div class="feat-item"><span class="feat-check">&#10003;</span> 59 slash commands</div>
            <div class="feat-item"><span class="feat-check">&#10003;</span> 28 AI-powered tools</div>
            <div class="feat-item"><span class="feat-check">&#10003;</span> 9-layer Crucible&trade; security shield</div>
            <div class="feat-item"><span class="feat-check">&#10003;</span> Continuity Engine (context recovery)</div>
            <div class="feat-item"><span class="feat-check">&#10003;</span> AMI self-healing (auto error recovery)</div>
            <div class="feat-item"><span class="feat-check">&#10003;</span> 14 themes + HUD dashboard</div>
            <div class="feat-item"><span class="feat-check">&#10003;</span> Voice input &amp; output</div>
            <div class="feat-item"><span class="feat-check">&#10003;</span> Web search integration</div>
            <div class="feat-item"><span class="feat-check">&#10003;</span> Plugin system</div>
            <div class="feat-item"><span class="feat-check">&#10003;</span> 31 assurance scenarios</div>
            <div class="feat-item"><span class="feat-check">&#10003;</span> Unlimited tokens forever</div>
        </div>
    </div>
</section>

<hr class="gradient-rule">

<!-- ── Neural Cortex Interactive Demo ─────────────────────────── -->
<section class="section" id="cortex">
    <div class="container">
        <div class="section-header reveal">
            <h2>Watch It Think.</h2>
            <p>The Neural Cortex&trade; is Forge's real-time brain visualization. It responds to what the AI is actually doing &mdash; thinking, writing code, scanning for threats, or recovering from errors. Click a state to see it in action.</p>
        </div>

        <div class="cortex-demo reveal">
            <div style="flex-shrink:0; text-align:center">
                <div class="cortex-canvas-wrap">
                    <canvas id="demo-cortex" style="border-radius:50%"></canvas>
                </div>
                <span class="cortex-state-label" id="demo-state-label">idle</span>
            </div>
            <div class="cortex-panel">
                <div class="cortex-controls" id="cortex-buttons">
                    <button class="cortex-btn" data-state="boot"><span class="cortex-dot" style="background:#0088ff"></span>Boot</button>
                    <button class="cortex-btn active" data-state="idle"><span class="cortex-dot" style="background:#00aacc"></span>Idle</button>
                    <button class="cortex-btn" data-state="thinking"><span class="cortex-dot" style="background:#ff6600"></span>Thinking</button>
                    <button class="cortex-btn" data-state="tool_exec"><span class="cortex-dot" style="background:#00cc88"></span>Executing</button>
                    <button class="cortex-btn" data-state="indexing"><span class="cortex-dot" style="background:#cc88ff"></span>Indexing</button>
                    <button class="cortex-btn" data-state="swapping"><span class="cortex-dot" style="background:#ffffff"></span>Swapping</button>
                    <button class="cortex-btn" data-state="error"><span class="cortex-dot" style="background:#ff4444"></span>Error</button>
                    <button class="cortex-btn" data-state="threat"><span class="cortex-dot" style="background:#ff0000"></span>Threat</button>
                    <button class="cortex-btn" data-state="pass"><span class="cortex-dot" style="background:#34d399"></span>Pass</button>
                </div>
                <div class="cortex-desc" id="cortex-desc">
                    <strong>Idle</strong> &mdash; Waiting for your input. Low power, minimal glow. The brain is listening but not processing.
                </div>
            </div>
        </div>
    </div>
</section>

<!-- ── Numbers ─────────────────────────────────────────────────── -->
<section class="section-sm">
    <div class="container">
        <div class="numbers-strip reveal">
            <div class="stat">
                <span class="stat-num" data-count="54207">0</span>
                <span class="stat-label">Lines of Source</span>
            </div>
            <div class="stat">
                <span class="stat-num" data-count="1318">0</span>
                <span class="stat-label">Tests Passing</span>
            </div>
            <div class="stat">
                <span class="stat-num" data-count="59">0</span>
                <span class="stat-label">Commands</span>
            </div>
            <div class="stat">
                <span class="stat-num" data-count="28">0</span>
                <span class="stat-label">AI Tools</span>
            </div>
            <div class="stat">
                <span class="stat-num static">Off</span>
                <span class="stat-label">Telemetry by Default</span>
            </div>
        </div>
    </div>
</section>

<hr class="gradient-rule">

<!-- ── Pricing ─────────────────────────────────────────────────── -->
<section class="section" id="pricing">
    <div class="container">
        <div class="section-header reveal">
            <h2>Free to start. Pay when your team grows.</h2>
            <p>Community gives you the full engine. Pro and Power add cross-session memory, team sync, and compliance.</p>
        </div>

        <div class="pricing-toggle reveal">
            <span class="toggle-label active" id="togOnetime">One-time</span>
            <button class="toggle-switch" id="billingToggle" aria-label="Switch billing period">
                <span class="toggle-thumb"></span>
            </button>
            <span class="toggle-label" id="togMonthly">Monthly</span>
        </div>

        <div class="pricing-grid reveal">
            <?php
            $display_order = ['community', 'pro', 'power'];
            foreach ($display_order as $tid):
                if (!isset($tiers[$tid])) continue;
                $t = $tiers[$tid];
                $is_featured = $tid === 'pro';
                $price_cents = (int)($t['price_cents'] ?? 0);
                $monthly_cents = (int)($t['price_monthly_cents'] ?? 0);
                $seats = (int)($t['seats'] ?? 1);
            ?>
            <div class="price-card<?php echo $is_featured ? ' featured' : ''; ?>">
                <?php if ($is_featured): ?><span class="price-badge">Most Popular</span><?php endif; ?>
                <div class="price-tier"><?php echo htmlspecialchars($t['label']); ?></div>
                <div class="price-amount">
                    <span class="price-onetime"><?php echo $price_cents === 0 ? 'Free' : '$' . ($price_cents / 100); ?></span>
                    <span class="price-monthly" style="display:none"><?php echo $monthly_cents === 0 ? 'Free' : '$' . ($monthly_cents / 100) . '/mo'; ?></span>
                </div>
                <div class="price-term">
                    <span class="price-onetime"><?php echo $price_cents === 0 ? 'Free forever' : 'One-time payment &middot; ' . $seats . ' seats'; ?></span>
                    <span class="price-monthly" style="display:none"><?php echo $monthly_cents === 0 ? 'Free forever' : 'Cancel anytime &middot; ' . $seats . ' seats'; ?></span>
                </div>
                <ul class="price-features">
                    <?php if ($tid === 'community'): ?>
                        <li><span class="ck">&#10003;</span> Full local AI assistant</li>
                        <li><span class="ck">&#10003;</span> All 59 commands &amp; 28 tools</li>
                        <li><span class="ck">&#10003;</span> 9-layer Crucible&trade; security</li>
                        <li><span class="ck">&#10003;</span> 14 themes + HUD dashboard</li>
                        <li><span class="ck">&#10003;</span> Voice I/O + web search</li>
                        <li><span class="ck">&#10003;</span> Unlimited tokens</li>
                    <?php elseif ($tid === 'pro'): ?>
                        <li><span class="ck">&#10003;</span> Everything in Community</li>
                        <li><span class="ck">&#10003;</span> Genome persistence &amp; sync</li>
                        <li><span class="ck">&#10003;</span> Team genome sharing</li>
                        <li><span class="ck">&#10003;</span> Shipwright release mgmt</li>
                        <li><span class="ck">&#10003;</span> Smart auto-commit</li>
                        <li><span class="ck">&#10003;</span> 3 seats (1 master + 2 puppets)</li>
                    <?php elseif ($tid === 'power'): ?>
                        <li><span class="ck">&#10003;</span> Everything in Pro</li>
                        <li><span class="ck">&#10003;</span> Enterprise mode + audit export</li>
                        <li><span class="ck">&#10003;</span> Fleet analytics dashboard</li>
                        <li><span class="ck">&#10003;</span> HIPAA/SOC2 compliance scenarios</li>
                        <li><span class="ck">&#10003;</span> Priority support</li>
                        <li><span class="ck">&#10003;</span> 10 seats (1 master + 9 puppets)</li>
                    <?php endif; ?>
                </ul>
                <?php if ($price_cents === 0): ?>
                    <a href="docs.php#install" class="btn btn-ghost btn-sm btn-block">Download Free</a>
                <?php else: ?>
                    <a href="../Forge/checkout.php?tier=<?php echo $tid; ?>" class="btn btn-primary btn-sm btn-block price-onetime">Get <?php echo htmlspecialchars($t['label']); ?></a>
                    <a href="../Forge/checkout.php?tier=<?php echo $tid; ?>&billing=monthly" class="btn btn-primary btn-sm btn-block price-monthly" style="display:none">Subscribe <?php echo htmlspecialchars($t['label']); ?></a>
                <?php endif; ?>
            </div>
            <?php endforeach; ?>
        </div>
    </div>
</section>

<hr class="gradient-rule">

<!-- ── Final CTA ───────────────────────────────────────────────── -->
<section class="final-cta">
    <div class="container reveal">
        <h2>Your code. Your AI. Your rules.</h2>
        <p>Fully transparent. Every line readable. Nothing hidden.</p>
        <a href="docs.php#install" class="btn btn-primary">Download Forge Free</a>
    </div>
</section>

<!-- ── Footer ──────────────────────────────────────────────────── -->
<footer>
    <div class="container">
        <div class="footer-inner">
            <span class="footer-copy">&copy; 2026 Forge</span>
            <div class="footer-links">
                <a href="docs.php">Docs</a>
                <a href="../Forge/matrix.php">Matrix</a>
                <a href="../Forge/privacy.php">Privacy</a>
            </div>
        </div>
    </div>
</footer>

<!-- ── Scripts ─────────────────────────────────────────────────── -->
<script>
(function() {
    'use strict';

    // ── Scroll reveal (gated — content visible without JS/IntersectionObserver)
    var reveals = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window)) {
        reveals.forEach(function(el) { el.classList.add('visible'); });
    } else {
        document.documentElement.classList.add('reveal-ready');
        var observer = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
        reveals.forEach(function(el) { observer.observe(el); });
    }

    // ── Nav scroll state
    var nav = document.getElementById('nav');
    window.addEventListener('scroll', function() {
        nav.classList.toggle('scrolled', window.scrollY > 40);
    }, { passive: true });

    // ── Mobile nav toggle
    var toggle = document.getElementById('navToggle');
    var links = document.getElementById('navLinks');
    if (toggle) {
        toggle.addEventListener('click', function() {
            links.classList.toggle('open');
        });
    }

    // ── Number count-up animation
    var counted = false;
    var numObserver = new IntersectionObserver(function(entries) {
        if (counted) return;
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                counted = true;
                animateNumbers();
                numObserver.disconnect();
            }
        });
    }, { threshold: 0.3 });

    var numStrip = document.querySelector('.numbers-strip');
    if (numStrip) numObserver.observe(numStrip);

    function animateNumbers() {
        document.querySelectorAll('.stat-num[data-count]').forEach(function(el) {
            var target = parseInt(el.dataset.count, 10);
            var duration = 1800;
            var start = performance.now();
            function tick(now) {
                var elapsed = now - start;
                var progress = Math.min(elapsed / duration, 1);
                var ease = 1 - Math.pow(1 - progress, 3);
                var current = Math.round(target * ease);
                el.textContent = current.toLocaleString() + (target > 100 ? '+' : '');
                if (progress < 1) requestAnimationFrame(tick);
            }
            requestAnimationFrame(tick);
        });
    }

    // ── Billing toggle
    var billingToggle = document.getElementById('billingToggle');
    var isMonthly = false;
    if (billingToggle) {
        billingToggle.addEventListener('click', function() {
            isMonthly = !isMonthly;
            billingToggle.classList.toggle('on', isMonthly);
            document.getElementById('togOnetime').classList.toggle('active', !isMonthly);
            document.getElementById('togMonthly').classList.toggle('active', isMonthly);
            document.querySelectorAll('.price-onetime').forEach(function(el) {
                el.style.display = isMonthly ? 'none' : '';
            });
            document.querySelectorAll('.price-monthly').forEach(function(el) {
                el.style.display = isMonthly ? '' : 'none';
            });
        });
    }

    // ── Neural Cortex Engine (inlined) ──────────────────────────
    var CORTEX_STATES = {
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
    var CORTEX_BG = [10, 14, 23];

    function cLerp(a, b, t) { return a + (b - a) * t; }
    function cSmoothstep(t) { return t * t * (3.0 - 2.0 * t); }
    function cClamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
    function cHsvToRgb(h, s, v) {
        h = ((h % 1.0) + 1.0) % 1.0;
        var i = Math.floor(h * 6) % 6, f = h * 6 - Math.floor(h * 6);
        var p = v * (1 - s), q = v * (1 - s * f), t2 = v * (1 - s * (1 - f));
        switch (i) {
            case 0: return [v, t2, p]; case 1: return [q, v, p]; case 2: return [p, v, t2];
            case 3: return [p, q, v]; case 4: return [t2, p, v]; default: return [v, p, q];
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
        this.config = this._clone(CORTEX_STATES.boot);
        this.phase = 0;
        this.transitioning = false;
        this.transStart = 0;
        this.transFrom = this.config;
        this.transTo = this.config;
        this.flashStart = 0;
        this.lastFrame = 0;
        this.running = false;
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
        img.src = opts.imageSrc || '../Forge/assets/brain.png';
    }
    NeuralCortex.prototype._clone = function(c) {
        return { waveCount:c.waveCount, speed:c.speed, sigma:c.sigma, hueCenter:c.hueCenter,
                 hueRange:c.hueRange, baseBri:c.baseBri, intensity:c.intensity, fps:c.fps, sat:c.sat, mode:c.mode };
    };
    NeuralCortex.prototype._processImage = function(img) {
        var s = this.renderSize, tc = document.createElement('canvas');
        tc.width = s; tc.height = s;
        var tctx = tc.getContext('2d');
        tctx.drawImage(img, 0, 0, s, s);
        var id = tctx.getImageData(0, 0, s, s), d = id.data, n = s * s;
        this.pathwayMask = new Float32Array(n);
        this.waveDist = new Float32Array(n);
        this.depthMap = new Float32Array(n);
        this.brainRgb = new Float32Array(n * 3);
        this.brainAlpha = new Float32Array(n);
        this.sweepX = new Float32Array(n);
        this.depthDelay = new Float32Array(n);
        this.depthAtten = new Float32Array(n);
        var cy = s / 2.0, cx = s / 2.0, maxDist = Math.sqrt(cy * cy + cx * cx);
        for (var i = 0; i < n; i++) {
            var idx = i * 4;
            var r = d[idx] / 255.0, g = d[idx+1] / 255.0, b = d[idx+2] / 255.0, a = d[idx+3] / 255.0;
            var bri = Math.max(r, g, b), ba = bri * a;
            this.brainRgb[i*3] = d[idx]; this.brainRgb[i*3+1] = d[idx+1]; this.brainRgb[i*3+2] = d[idx+2];
            this.brainAlpha[i] = a;
            this.pathwayMask[i] = Math.pow(cClamp(ba, 0, 1), 0.7);
            this.depthMap[i] = 1.0 - Math.pow(cClamp(ba, 0, 1), 0.5);
            var y = Math.floor(i / s), x = i % s;
            this.waveDist[i] = Math.sqrt((y-cy)*(y-cy) + (x-cx)*(x-cx)) / maxDist;
            this.sweepX[i] = x / s;
            this.depthDelay[i] = this.depthMap[i] * 0.3;
            this.depthAtten[i] = 1.0 - this.depthMap[i] * 0.5;
        }
        this.imgData = this.ctx.createImageData(s, s);
    };
    NeuralCortex.prototype.setState = function(newState) {
        if (!CORTEX_STATES[newState] || (newState === this.state && !this.transitioning)) return;
        this.transFrom = this._getConfig();
        this.transTo = this._clone(CORTEX_STATES[newState]);
        this.transStart = performance.now() / 1000;
        this.transitioning = true;
        this.state = newState;
        if (newState === 'swapping' || newState === 'error' || newState === 'threat') this.flashStart = performance.now() / 1000;
        if (this.onStateChange) this.onStateChange(newState);
    };
    NeuralCortex.prototype._getConfig = function() {
        if (!this.transitioning) return this.config;
        var elapsed = performance.now() / 1000 - this.transStart, t = Math.min(elapsed / 0.5, 1.0);
        if (t >= 1.0) { this.transitioning = false; this.config = this._clone(this.transTo); return this.config; }
        t = cSmoothstep(t);
        this.config = {
            waveCount: Math.round(cLerp(this.transFrom.waveCount, this.transTo.waveCount, t)),
            speed: cLerp(this.transFrom.speed, this.transTo.speed, t),
            sigma: cLerp(this.transFrom.sigma, this.transTo.sigma, t),
            hueCenter: cLerp(this.transFrom.hueCenter, this.transTo.hueCenter, t),
            hueRange: cLerp(this.transFrom.hueRange, this.transTo.hueRange, t),
            baseBri: cLerp(this.transFrom.baseBri, this.transTo.baseBri, t),
            intensity: cLerp(this.transFrom.intensity, this.transTo.intensity, t),
            fps: Math.round(cLerp(this.transFrom.fps, this.transTo.fps, t)),
            sat: cLerp(this.transFrom.sat, this.transTo.sat, t),
            mode: this.transTo.mode
        };
        return this.config;
    };
    NeuralCortex.prototype.start = function() {
        if (this.running) return;
        this.running = true;
        this.lastFrame = performance.now();
        this._tick();
    };
    NeuralCortex.prototype.stop = function() { this.running = false; };
    NeuralCortex.prototype._tick = function() {
        if (!this.running || !this.pathwayMask) return;
        var now = performance.now(), cfg = this._getConfig(), interval = 1000 / cfg.fps;
        if (now - this.lastFrame >= interval) {
            this.phase += (now - this.lastFrame) / 1000;
            this.lastFrame = now;
            this._renderFrame(cfg);
        }
        var self = this;
        requestAnimationFrame(function() { self._tick(); });
    };
    NeuralCortex.prototype._renderFrame = function(cfg) {
        var s = this.renderSize, n = s * s, data = this.imgData.data;
        var waveTotal = new Float32Array(n), hueArr = new Float32Array(n);
        if (cfg.mode === 'spiral') this._calcSpiral(cfg, waveTotal, hueArr, s);
        else if (cfg.mode === 'sweep') this._calcSweep(cfg, waveTotal, hueArr, s);
        else if (cfg.mode === 'threat') this._calcThreat(cfg, waveTotal, hueArr, s);
        else if (cfg.mode === 'flash') {
            this._calcFlash(cfg, waveTotal, hueArr, s, data);
            if (performance.now() / 1000 - this.flashStart < 0.3) { this.ctx.putImageData(this.imgData, 0, 0); return; }
        }
        else this._calcRadial(cfg, waveTotal, hueArr, s);
        for (var i = 0; i < n; i++) {
            var wt = cClamp(waveTotal[i], 0, 1.5), h = ((hueArr[i] % 1.0) + 1.0) % 1.0;
            var rgb = cHsvToRgb(h, cfg.sat, 1.0);
            var gf0 = 1.0 + wt * rgb[0] * 2.0, gf1 = 1.0 + wt * rgb[1] * 2.0, gf2 = 1.0 + wt * rgb[2] * 2.0;
            var br = this.brainRgb[i*3] * cfg.baseBri / 255.0 * gf0;
            var bg2 = this.brainRgb[i*3+1] * cfg.baseBri / 255.0 * gf1;
            var bb = this.brainRgb[i*3+2] * cfg.baseBri / 255.0 * gf2;
            var af = this.brainAlpha[i], idx = i * 4;
            data[idx]   = cClamp(Math.round(br * af * 255 + CORTEX_BG[0] * (1 - af)), 0, 255);
            data[idx+1] = cClamp(Math.round(bg2 * af * 255 + CORTEX_BG[1] * (1 - af)), 0, 255);
            data[idx+2] = cClamp(Math.round(bb * af * 255 + CORTEX_BG[2] * (1 - af)), 0, 255);
            data[idx+3] = 255;
        }
        this.ctx.putImageData(this.imgData, 0, 0);
    };
    NeuralCortex.prototype._calcRadial = function(cfg, waveTotal, hueArr, s) {
        var n = s * s;
        for (var wi = 0; wi < cfg.waveCount; wi++) {
            var offset = wi / Math.max(cfg.waveCount, 1), wp = (this.phase * cfg.speed + offset) % 1.3;
            var sig2 = 2 * cfg.sigma * cfg.sigma;
            var hue = (cfg.hueCenter + cfg.hueRange * Math.sin(this.phase * 0.3 + wi * 2.09)) % 1.0;
            for (var i = 0; i < n; i++) {
                var diff = this.waveDist[i] + this.depthDelay[i] - wp;
                var wave = Math.exp(-(diff * diff) / sig2) * this.pathwayMask[i] * this.depthAtten[i] * cfg.intensity;
                waveTotal[i] += wave; hueArr[i] += wave * hue;
            }
        }
        for (var i = 0; i < n; i++) {
            if (waveTotal[i] > 0.001) hueArr[i] = (hueArr[i] / waveTotal[i]) % 1.0;
            else hueArr[i] = cfg.hueCenter;
        }
    };
    NeuralCortex.prototype._calcSpiral = function(cfg, waveTotal, hueArr, s) {
        var n = s * s, cy = s / 2.0, cx = s / 2.0;
        var sp = (this.phase * cfg.speed) % 1.5, sig2 = 2 * cfg.sigma * cfg.sigma;
        for (var i = 0; i < n; i++) {
            var y = Math.floor(i / s), x = i % s;
            var angle = Math.atan2(y - cy, x - cx) / (2 * Math.PI) + 0.5;
            var sd = (this.waveDist[i] + angle * 0.3) % 1.5;
            var diff = sd - sp;
            var wave = Math.exp(-(diff * diff) / sig2) * this.pathwayMask[i] * this.depthAtten[i] * cfg.intensity;
            waveTotal[i] = cClamp(wave, 0, 1.5);
            hueArr[i] = cfg.hueCenter;
        }
    };
    NeuralCortex.prototype._calcSweep = function(cfg, waveTotal, hueArr, s) {
        var n = s * s;
        for (var wi = 0; wi < cfg.waveCount; wi++) {
            var offset = wi / Math.max(cfg.waveCount, 1), sp = (this.phase * cfg.speed + offset) % 1.4;
            var sig2 = 2 * cfg.sigma * cfg.sigma;
            for (var i = 0; i < n; i++) {
                var diff = this.sweepX[i] - sp;
                waveTotal[i] += Math.exp(-(diff * diff) / sig2) * this.pathwayMask[i] * this.depthAtten[i] * cfg.intensity;
            }
        }
        for (var i = 0; i < n; i++) { waveTotal[i] = cClamp(waveTotal[i], 0, 1.5); hueArr[i] = cfg.hueCenter; }
    };
    NeuralCortex.prototype._calcFlash = function(cfg, waveTotal, hueArr, s, data) {
        var n = s * s, elapsed = performance.now() / 1000 - this.flashStart;
        if (elapsed < 0.3) {
            var flashInt = cfg.intensity * (1.0 - (elapsed / 0.3) * 0.3);
            for (var i = 0; i < n; i++) {
                var wave = this.pathwayMask[i] * this.depthAtten[i] * flashInt;
                var br = this.brainRgb[i*3] / 255.0 * cfg.baseBri, bg2 = this.brainRgb[i*3+1] / 255.0 * cfg.baseBri;
                var bb = this.brainRgb[i*3+2] / 255.0 * cfg.baseBri;
                var gf = 1.0 + cClamp(wave, 0, 1.5) * 2.0, af = this.brainAlpha[i], idx = i * 4;
                data[idx] = cClamp(Math.round((br * gf) * af * 255 + CORTEX_BG[0] * (1-af)), 0, 255);
                data[idx+1] = cClamp(Math.round((bg2 * gf) * af * 255 + CORTEX_BG[1] * (1-af)), 0, 255);
                data[idx+2] = cClamp(Math.round((bb * gf) * af * 255 + CORTEX_BG[2] * (1-af)), 0, 255);
                data[idx+3] = 255;
            }
            return;
        }
        var fade = Math.min((elapsed - 0.3) / 1.0, 1.0);
        this._calcRadial({ waveCount:1, speed:cfg.speed, sigma:cfg.sigma*(2-fade), hueCenter:0.52,
            hueRange:0.02, baseBri:cfg.baseBri, intensity:cfg.intensity*fade, fps:cfg.fps, sat:0.6+0.2*fade, mode:'radial' }, waveTotal, hueArr, s);
    };
    NeuralCortex.prototype._calcThreat = function(cfg, waveTotal, hueArr, s) {
        var n = s * s, sig2 = 2 * cfg.sigma * cfg.sigma;
        for (var wi = 0; wi < cfg.waveCount; wi++) {
            var offset = wi / cfg.waveCount, wp = (this.phase * cfg.speed + offset) % 1.3;
            var hue = cfg.hueCenter + cfg.hueRange * Math.sin(this.phase * 2.0 + wi * 1.26);
            for (var i = 0; i < n; i++) {
                var diff = this.waveDist[i] + this.depthDelay[i] - wp;
                var wave = Math.exp(-(diff * diff) / sig2) * this.pathwayMask[i] * this.depthAtten[i] * cfg.intensity;
                waveTotal[i] += wave; hueArr[i] += wave * hue;
            }
        }
        var throb = 0.6 + 0.4 * Math.abs(Math.sin(this.phase * 9.5));
        var crackle = Math.random() < 0.3 ? 0.2 + Math.random() * 0.3 : 0;
        for (var i = 0; i < n; i++) {
            waveTotal[i] = cClamp(waveTotal[i] * throb + this.pathwayMask[i] * crackle, 0, 2.0);
            if (waveTotal[i] > 0.001) hueArr[i] = (hueArr[i] / (waveTotal[i] / throb + 0.001)) % 1.0;
            else hueArr[i] = cfg.hueCenter;
        }
    };

    // ── Neural Cortex: Hero (auto-cycle) ──
    var AUTO_CYCLE = ['boot','idle','thinking','tool_exec','indexing','pass','idle','swapping','error','threat','idle'];
    var heroCanvas = document.getElementById('hero-cortex');
    if (heroCanvas) {
        var heroCortex = new NeuralCortex(heroCanvas, {
            size: 260, scale: 2, imageSrc: '../Forge/assets/brain.png',
            onStateChange: function(s) {
                var lbl = document.getElementById('hero-state-label');
                if (lbl) lbl.textContent = s.replace('_', ' ');
            }
        });
        var heroIdx = 0;
        setInterval(function() {
            heroIdx = (heroIdx + 1) % AUTO_CYCLE.length;
            heroCortex.setState(AUTO_CYCLE[heroIdx]);
        }, 4000);
    }

    // ── Neural Cortex: Interactive Demo ──
    var STATE_DESCS = {
        boot: '<strong>Boot</strong> — Forge is starting up. Neural pathways initializing with a slow spiral sweep. The brain is loading models, scanning your project, and building context.',
        idle: '<strong>Idle</strong> — Waiting for your input. Low power, minimal glow. The brain is listening but not processing.',
        thinking: '<strong>Thinking</strong> — Generating a response. Multiple rainbow waves cascade through the brain, reflecting parallel reasoning across neural pathways.',
        tool_exec: '<strong>Executing</strong> — Writing files or running shell commands. A directional sweep moves across the brain, showing focused activity.',
        indexing: '<strong>Indexing</strong> — Scanning and embedding your codebase. Purple ripples spread outward as files are processed and mapped.',
        swapping: '<strong>Swapping</strong> — Context window is full. White flash followed by fade as old context is summarized and fresh context loaded.',
        error: '<strong>Error</strong> — Something went wrong. Deep red glow indicates the AI is recovering. AMI auto-recovery is engaging.',
        threat: '<strong>Threat</strong> — Crucible™ detected a security threat. Aggressive red pulses with random crackle. The injection is being quarantined.',
        pass: '<strong>Pass</strong> — All checks passed. Green wash confirms safe operation. Code verified, no threats detected.'
    };
    var demoCortex = null;
    var cortexSection = document.getElementById('cortex');
    if (cortexSection) {
        var demoObserver = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting && !demoCortex) {
                    demoCortex = new NeuralCortex(document.getElementById('demo-cortex'), {
                        size: 220, scale: 2, imageSrc: '../Forge/assets/brain.png',
                        onStateChange: function(s) {
                            document.getElementById('demo-state-label').textContent = s.replace('_', ' ');
                            document.getElementById('cortex-desc').innerHTML = STATE_DESCS[s] || '';
                            var btns = document.querySelectorAll('.cortex-btn');
                            btns.forEach(function(b) { b.classList.toggle('active', b.dataset.state === s); });
                        }
                    });
                    demoObserver.disconnect();
                }
            });
        }, { threshold: 0.1 });
        demoObserver.observe(cortexSection);

        document.getElementById('cortex-buttons').addEventListener('click', function(e) {
            var btn = e.target.closest('.cortex-btn');
            if (btn && demoCortex) demoCortex.setState(btn.dataset.state);
        });
    }
})();
</script>

</body>
</html>
