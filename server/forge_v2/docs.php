<?php
$version = '0.9.0';
header('Cache-Control: no-cache, no-store, must-revalidate');
header('Pragma: no-cache');
header('Expires: 0');
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Forge &mdash; Documentation</title>
<meta name="description" content="Forge documentation. 59 commands, 28 AI tools, 9 security layers. Install, configure, and master your local AI coding assistant.">
<meta property="og:title" content="Forge &mdash; Documentation">
<meta property="og:description" content="Everything you need to install, configure, and master Forge. 59 commands. 28 AI tools. 9 security layers. Full local control.">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
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

/* ── Scroll reveal ────────────────────────────────────────────── */
/* JS adds .reveal-ready to html when IntersectionObserver is set up */
html.reveal-ready .reveal {
    opacity: 0;
    transform: translateY(28px);
    transition: opacity 0.7s cubic-bezier(.22,1,.36,1), transform 0.7s cubic-bezier(.22,1,.36,1);
}
html.reveal-ready .reveal.visible {
    opacity: 1;
    transform: none; /* 'none' unlike translateY(0) does NOT establish a containing block */
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

/* ── Docs Layout ──────────────────────────────────────────────── */
.docs-layout {
    display: flex;
    max-width: 1320px;
    margin: 0 auto;
    padding-top: 80px;
    min-height: 100vh;
    position: relative;
    z-index: 1;
}

/* ── Sidebar ──────────────────────────────────────────────────── */
.docs-sidebar {
    position: fixed;
    top: 80px;
    left: max(0px, calc((100vw - 1320px) / 2));
    width: 260px;
    height: calc(100vh - 80px);
    overflow-y: auto;
    padding: 32px 24px;
    border-right: 1px solid var(--border);
    background: var(--bg);
    z-index: 50;
}
.docs-sidebar::-webkit-scrollbar { width: 4px; }
.docs-sidebar::-webkit-scrollbar-track { background: transparent; }
.docs-sidebar::-webkit-scrollbar-thumb { background: var(--border-lit); border-radius: 4px; }
.sidebar-group { margin-bottom: 28px; }
.sidebar-group-label {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--text-xdim);
    font-weight: 600;
    margin-bottom: 10px;
    padding-left: 12px;
}
.docs-sidebar a {
    display: block;
    padding: 6px 12px;
    font-size: 0.82rem;
    color: var(--text-dim);
    border-left: 2px solid transparent;
    transition: color 0.2s, border-color 0.2s;
    text-decoration: none;
    border-radius: 0 4px 4px 0;
}
.docs-sidebar a:hover { color: var(--text); }
.docs-sidebar a.active {
    color: var(--accent);
    border-left-color: var(--accent);
    background: rgba(0,212,255,0.04);
}

/* ── Main Content ─────────────────────────────────────────────── */
.docs-main {
    margin-left: 260px;
    flex: 1;
    padding: 48px 48px 120px;
    max-width: 860px;
}

/* ── Docs Hero ────────────────────────────────────────────────── */
.docs-hero {
    margin-bottom: 64px;
    padding-bottom: 48px;
    border-bottom: 1px solid var(--border);
}
.docs-hero-badge {
    display: inline-block;
    font-family: var(--mono);
    font-size: 0.75rem;
    color: var(--accent);
    border: 1px solid var(--accent-dim);
    background: rgba(0,212,255,0.05);
    padding: 5px 14px;
    border-radius: 100px;
    margin-bottom: 20px;
    letter-spacing: 0.04em;
}
.docs-hero-title {
    font-size: clamp(2rem, 5vw, 3rem);
    font-weight: 800;
    letter-spacing: -0.04em;
    margin-bottom: 12px;
    background: linear-gradient(135deg, #fff 30%, var(--accent) 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}
.docs-hero-desc {
    font-size: 1.0625rem;
    color: var(--text-dim);
    max-width: 560px;
    line-height: 1.7;
}

/* ── Section Dividers ─────────────────────────────────────────── */
.section-divider {
    margin: 96px 0 48px;
    text-align: center;
    border-top: 2px solid #3d4478;
    padding-top: 32px;
}
.section-divider::before {
    display: none;
}
.section-divider-label {
    display: inline-block;
    font-size: 1.1rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 4px;
    color: #00d4ff;
    background: linear-gradient(135deg, #00d4ff, #7b8fff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    position: static;
    transform: none;
    padding: 0;
}

/* ── Feature Sections ─────────────────────────────────────────── */
.feature-section {
    margin-bottom: 56px;
    scroll-margin-top: 96px;
    background: #1a1e35;
    border: 2px solid #3d4478;
    border-left: 6px solid #00b8e6;
    border-radius: var(--radius-lg);
    padding: 44px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.04);
    transition: border-color 0.3s, background 0.3s, box-shadow 0.3s;
}
.feature-section:hover {
    border-color: #5560a0;
    border-left-color: #00d4ff;
    background: #1f2340;
    box-shadow: 0 6px 32px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.06);
}
.section-break {
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 12px 0;
    padding: 0 32px;
}
.section-break-line {
    flex: 1;
    height: 2px;
    background: linear-gradient(90deg, transparent, #777 25%, #777 75%, transparent);
}
.section-break-dot {
    width: 8px;
    height: 8px;
    background: #999;
    border-radius: 50%;
    margin: 0 18px;
    box-shadow: none;
    flex-shrink: 0;
}
.feature-section h2 {
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin-bottom: 12px;
    color: var(--text);
}
.feature-badge {
    display: inline-block;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    padding: 3px 10px;
    border-radius: 100px;
    background: var(--accent-dim);
    color: var(--accent);
    font-weight: 600;
    vertical-align: middle;
    margin-left: 10px;
}
.feature-what {
    font-size: 1rem;
    color: var(--text);
    margin-bottom: 8px;
    line-height: 1.7;
}
.feature-why {
    font-size: 0.92rem;
    color: var(--text-dim);
    margin-bottom: 24px;
    line-height: 1.7;
    padding-left: 16px;
    border-left: 2px solid rgba(0,212,255,0.2);
}

/* ── Doc Cards ────────────────────────────────────────────────── */
.doc-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 28px 32px;
    margin-bottom: 20px;
    transition: border-color 0.3s;
}
.doc-card:hover {
    border-color: var(--border-lit);
}
.doc-card h3 {
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 12px;
    color: var(--text);
}

/* ── Tables ───────────────────────────────────────────────────── */
.table-wrap {
    border-radius: var(--radius);
    overflow: hidden;
    border: 1px solid var(--border);
    margin: 16px 0;
}
.table-wrap table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
}
.table-wrap th {
    background: var(--bg-card);
    padding: 12px 16px;
    text-align: left;
    font-weight: 600;
    color: var(--text-dim);
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    border-bottom: 1px solid var(--border);
}
.table-wrap td {
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
}
.table-wrap tbody tr:last-child td { border-bottom: none; }
.table-wrap tbody tr:hover { background: rgba(255,255,255,0.015); }
.table-wrap code {
    font-family: var(--mono);
    font-size: 0.85em;
    color: var(--accent);
    background: rgba(0,212,255,0.06);
    padding: 2px 6px;
    border-radius: 4px;
}

/* ── Code Blocks ──────────────────────────────────────────────── */
.code-block {
    position: relative;
    margin: 16px 0;
    border-radius: var(--radius);
    overflow: hidden;
    border: 1px solid var(--border);
}
.code-block pre {
    background: var(--bg-surface);
    padding: 20px 24px;
    overflow-x: auto;
    font-family: var(--mono);
    font-size: 0.85rem;
    line-height: 1.7;
    color: var(--text-dim);
    margin: 0;
}
.code-block code { font-family: inherit; color: inherit; background: none; padding: 0; }
.copy-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    color: var(--text-dim);
    padding: 4px 12px;
    border-radius: 6px;
    font-size: 0.72rem;
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.2s, background 0.2s;
}
.code-block:hover .copy-btn { opacity: 1; }
.copy-btn:hover { background: var(--bg-card-up); color: var(--text); }

/* ── Callout Boxes ────────────────────────────────────────────── */
.callout {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius);
    padding: 16px 20px;
    margin: 16px 0;
    font-size: 0.92rem;
    color: var(--text-dim);
    line-height: 1.7;
}
.callout strong { color: var(--text); }
.callout.callout-warn {
    border-left-color: var(--amber);
}

/* ── Command Modal ────────────────────────────────────────────── */
.cmd-row { cursor: pointer; transition: background 0.15s; }
.cmd-row:hover { background: var(--bg-card-up) !important; }
.cmd-row td:first-child::after { content: ''; display: inline-block; width: 6px; height: 6px; border-right: 1.5px solid var(--text-dim); border-bottom: 1.5px solid var(--text-dim); transform: rotate(-45deg); margin-left: 8px; opacity: 0; transition: opacity 0.15s; vertical-align: middle; }
.cmd-row:hover td:first-child::after { opacity: 1; }
.cmd-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(4px); z-index: 9000; justify-content: center; align-items: center; animation: cmdFadeIn 0.15s ease; }
.cmd-modal-overlay.active { display: flex; }
.cmd-modal { background: var(--bg-card); border: 1px solid var(--border-lit); border-radius: var(--radius-lg); width: min(680px, 92vw); max-height: 85vh; overflow-y: auto; box-shadow: 0 24px 80px rgba(0,0,0,0.6), 0 0 1px var(--accent-dim); animation: cmdSlideUp 0.2s ease; }
.cmd-modal-head { display: flex; align-items: center; justify-content: space-between; padding: 20px 24px 16px; border-bottom: 1px solid var(--border); }
.cmd-modal-head h3 { margin: 0; font-size: 1.15em; color: var(--accent); font-family: var(--mono); }
.cmd-modal-close { background: none; border: none; color: var(--text-dim); font-size: 1.4em; cursor: pointer; padding: 4px 8px; border-radius: 6px; transition: color 0.15s, background 0.15s; line-height: 1; }
.cmd-modal-close:hover { color: var(--text); background: rgba(255,255,255,0.06); }
.cmd-modal-body { padding: 24px; }
.cmd-modal-desc { color: var(--text-dim); font-size: 0.92em; margin-bottom: 20px; line-height: 1.6; }
.cmd-modal-label { font-size: 0.72em; text-transform: uppercase; letter-spacing: 1.5px; color: var(--text-xdim); font-weight: 600; margin-bottom: 8px; }
.cmd-modal-term { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 20px; font-family: var(--mono); font-size: 0.88em; line-height: 1.7; white-space: pre; overflow-x: auto; margin-bottom: 20px; color: var(--text); }
.cmd-modal-term .prompt { color: var(--accent); }
.cmd-modal-term .output { color: var(--text-dim); }
.cmd-modal-term .highlight { color: #4ade80; }
.cmd-modal-term .warn { color: #f59e0b; }
.cmd-modal-term .dim { color: #4a5568; }
.cmd-modal-variants { margin-top: 4px; }
.cmd-modal-variants h4 { font-size: 0.82em; color: var(--text-dim); margin: 0 0 8px; text-transform: uppercase; letter-spacing: 1px; }
.cmd-modal-variants code { display: inline-block; background: var(--bg); border: 1px solid var(--border); padding: 3px 10px; border-radius: 6px; font-size: 0.88em; margin: 0 6px 6px 0; color: var(--accent); cursor: pointer; transition: background 0.15s, border-color 0.15s; user-select: none; }
.cmd-modal-variants code:hover { background: var(--accent-dim); border-color: rgba(0,212,255,0.2); }
.cmd-modal-variants code.active { background: rgba(0,212,255,0.15); border-color: var(--accent); }
.cmd-modal-tag { display: inline-block; padding: 2px 10px; border-radius: 100px; font-size: 0.72em; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; margin-left: 12px; }
.cmd-modal-tag.cat-system { background: rgba(0,212,255,0.12); color: var(--accent); }
.cmd-modal-tag.cat-model { background: rgba(139,92,246,0.12); color: #a78bfa; }
.cmd-modal-tag.cat-context { background: rgba(59,130,246,0.12); color: #60a5fa; }
.cmd-modal-tag.cat-search { background: rgba(16,185,129,0.12); color: #34d399; }
.cmd-modal-tag.cat-safety { background: rgba(239,68,68,0.12); color: #f87171; }
.cmd-modal-tag.cat-intel { background: rgba(251,191,36,0.12); color: #fbbf24; }
.cmd-modal-tag.cat-diag { background: rgba(156,163,175,0.12); color: #9ca3af; }
.cmd-modal-tag.cat-reliability { background: rgba(34,211,238,0.12); color: #22d3ee; }
.cmd-modal-tag.cat-fleet { background: rgba(244,114,182,0.12); color: #f472b6; }
@keyframes cmdFadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes cmdSlideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }

/* ── Theme Grid ───────────────────────────────────────────────── */
.theme-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 12px;
    margin: 20px 0;
}
.theme-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    cursor: pointer;
    transition: border-color 0.2s;
}
.theme-badge:hover { border-color: var(--border-lit); }
.theme-swatch {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid var(--border-lit);
    flex-shrink: 0;
}
.theme-name { font-size: 0.78rem; color: var(--text-dim); }
.fx-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
    margin-left: auto;
}

/* ── Filter Inputs ────────────────────────────────────────────── */
.filter-input {
    width: 100%;
    padding: 12px 16px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-family: var(--font);
    font-size: 0.88rem;
    margin-bottom: 16px;
    transition: border-color 0.2s;
}
.filter-input:focus {
    outline: none;
    border-color: var(--accent);
}
.filter-input::placeholder { color: var(--text-xdim); }

/* ── Command Table Category Headers ───────────────────────────── */
.cmd-cat-header td {
    background: var(--bg-card-up) !important;
    color: var(--accent);
    font-weight: 600;
    font-size: 0.78rem;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 10px 16px !important;
}

/* ── Lists ────────────────────────────────────────────────────── */
.docs-main ul, .docs-main ol {
    padding-left: 24px;
    margin-bottom: 16px;
    line-height: 2;
    color: var(--text-dim);
}
.docs-main li strong { color: var(--text); }

/* ── Tooltips for jargon ─────────────────────────────────────── */
.jargon {
    border-bottom: 1px dashed var(--text-xdim);
    cursor: help;
    position: relative;
}
.jargon::after {
    content: attr(data-tip);
    position: absolute;
    bottom: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%);
    background: var(--bg-card-up);
    color: var(--text);
    border: 1px solid var(--border-lit);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 0.78rem;
    line-height: 1.5;
    white-space: normal;
    width: max-content;
    max-width: 280px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s;
    z-index: 200;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    font-weight: 400;
    text-transform: none;
    letter-spacing: 0;
}
.jargon:hover::after { opacity: 1; }

/* ── "Solves" callout ────────────────────────────────────────── */
.solves {
    background: rgba(52,211,153,0.06);
    border: 1px solid rgba(52,211,153,0.15);
    border-left: 3px solid var(--green);
    border-radius: var(--radius);
    padding: 14px 20px;
    margin: 16px 0;
    font-size: 0.88rem;
    color: var(--text-dim);
    line-height: 1.7;
}
.solves strong { color: var(--green); }

/* ── Mobile ───────────────────────────────────────────────────── */
@media (max-width: 900px) {
    .docs-sidebar { display: none; }
    .docs-main { margin-left: 0; padding: 32px 20px 80px; }
}
@media (max-width: 640px) {
    .nav-links { display: none; position: absolute; top: 64px; left: 0; right: 0; flex-direction: column; background: rgba(7,8,12,0.96); backdrop-filter: blur(16px); padding: 16px 24px; gap: 16px; border-bottom: 1px solid var(--border); }
    .nav-links.open { display: flex; }
    .nav-toggle { display: flex; }
}
</style>
</head>
<body>

<!-- ── Navigation ─────────────────────────────────────────────── -->
<nav class="nav" id="nav">
    <div class="nav-inner">
        <a href="/ForgeV2/" class="nav-logo">Forge</a>
        <div class="nav-links" id="navLinks">
            <a href="/ForgeV2/docs.php" style="color:var(--accent)">Docs</a>
            <a href="/ForgeV2/#pricing">Pricing</a>
            <a href="/Forge/matrix.php">Matrix</a>
            <a href="/ForgeV2/#install" class="nav-cta">Get Started</a>
        </div>
        <button class="nav-toggle" id="navToggle" aria-label="Menu">
            <span></span><span></span><span></span>
        </button>
    </div>
</nav>

<!-- ── Docs Layout ────────────────────────────────────────────── -->
<div class="docs-layout">

    <!-- ── Sidebar ────────────────────────────────────────────── -->
    <aside class="docs-sidebar" id="docsSidebar">
        <div class="sidebar-group">
            <div class="sidebar-group-label">Getting Started</div>
            <a href="#install">Installation &amp; Setup</a>
            <a href="#requirements">System Requirements</a>
            <a href="#quickstart">Quick Start</a>
            <a href="#models">Model Manager</a>
        </div>
        <div class="sidebar-group">
            <div class="sidebar-group-label">Core Capabilities</div>
            <a href="#commands">Commands (59)</a>
            <a href="#tools">Tool System (28)</a>
            <a href="#routing">Multi-Model Routing</a>
            <a href="#context">Context Management</a>
        </div>
        <div class="sidebar-group">
            <div class="sidebar-group-label">AI Intelligence</div>
            <a href="#ami">Self-Healing AI</a>
            <a href="#continuity">Session Health</a>
            <a href="#genome">Learning Memory</a>
            <a href="#reliability">Reliability Tracking</a>
        </div>
        <div class="sidebar-group">
            <div class="sidebar-group-label">Security</div>
            <a href="#security">9-Layer Architecture</a>
            <a href="#safety-levels">Safety Levels</a>
            <a href="#threat-intel">Threat Intelligence</a>
            <a href="#forensics">Forensics &amp; Audit</a>
        </div>
        <div class="sidebar-group">
            <div class="sidebar-group-label">Voice &amp; Interaction</div>
            <a href="#voice">Voice I/O</a>
            <a href="#themes">Themes &amp; Dashboard</a>
            <a href="#plugins">Plugin System</a>
        </div>
        <div class="sidebar-group">
            <div class="sidebar-group-label">Licensing &amp; Fleet</div>
            <a href="#licensing">Tiers &amp; Pricing</a>
            <a href="#activation">Activation</a>
            <a href="#fleet">Master/Puppet Fleet</a>
            <a href="#bpos">Behavioral Proof of Stake</a>
        </div>
        <div class="sidebar-group">
            <div class="sidebar-group-label">Advanced</div>
            <a href="#config">Configuration (97)</a>
            <a href="#enterprise">Enterprise Mode</a>
            <a href="#benchmark">Benchmark Suite</a>
            <a href="#shipwright">Shipwright</a>
            <a href="#autoforge">AutoForge</a>
            <a href="#telemetry">Telemetry</a>
        </div>
    </aside>

    <!-- ── Main Content ───────────────────────────────────────── -->
    <main class="docs-main">

        <!-- Hero area -->
        <div class="docs-hero">
            <div class="docs-hero-badge">v<?php echo $version; ?> &mdash; 54,207 lines</div>
            <h1 class="docs-hero-title">Documentation</h1>
            <p class="docs-hero-desc">Everything you need to install, configure, and master Forge. 59 commands. 28 AI tools. 9 security layers. Full local control.</p>
        </div>

        <!-- ═══════════════════════════════════════════════════════ -->
        <!-- GETTING STARTED                                        -->
        <!-- ═══════════════════════════════════════════════════════ -->

        <div class="feature-section reveal" id="install">
          <h2>Installation &amp; Setup</h2>
          <p class="feature-what">Get Forge running on your machine in under 5 minutes. Everything runs locally — no API keys to manage, no cloud bills, no data leaving your network.</p>
          <p class="feature-why">Your code stays on your hardware. Period. No cloud provider ever sees your proprietary codebase, your prompts, or your AI's responses.</p>

          <div class="doc-card">
            <h3>Prerequisites</h3>
            <ul>
              <li>Python 3.10 or newer</li>
              <li><a href="https://ollama.com">Ollama</a> installed and running (manages AI models locally)</li>
              <li>GPU with 4GB+ VRAM recommended (see <a href="#requirements">System Requirements</a>)</li>
              <li>Windows 10/11, Linux (Ubuntu 20.04+), or macOS 12+</li>
            </ul>
          </div>

          <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code># Clone the repository
git clone https://github.com/yourusername/forge.git
cd forge

# Create virtual environment
python -m venv venv
source venv/bin/activate    # Linux/Mac
venv\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt</code></pre>
          </div>

          <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code># Pull your first model (~10GB VRAM)
ollama pull qwen2.5-coder:14b

# Embedding model for semantic search
ollama pull nomic-embed-text</code></pre>
          </div>

          <div class="callout">
            <strong>How it works:</strong> Ollama manages AI models locally (downloading, loading, inference). Forge connects to Ollama's local API (localhost:11434) and sends your requests to the model. Nothing leaves your machine. You can also use OpenAI-compatible or Anthropic API backends if you prefer cloud models.
          </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="requirements">
          <h2>System Requirements</h2>
          <p class="feature-what">Hardware needed to run Forge at different performance levels.</p>
          <p class="feature-why">Larger models produce better code but need more VRAM. This helps you pick the right model for your hardware — from a GTX 1650 to an RTX 5090.</p>

          <div class="table-wrap">
            <table>
              <thead><tr><th>Component</th><th>Minimum</th><th>Recommended</th><th>Optimal</th></tr></thead>
              <tbody>
                <tr><td><strong>GPU</strong></td><td>4GB VRAM (GTX 1650+)</td><td>12GB+ (RTX 3060/4060)</td><td>16GB+ (RTX 4070 Ti / 5070 Ti)</td></tr>
                <tr><td><strong>RAM</strong></td><td>8 GB</td><td>16 GB</td><td>32 GB</td></tr>
                <tr><td><strong>Storage</strong></td><td>10 GB (models)</td><td>20 GB</td><td>50 GB (multiple models)</td></tr>
                <tr><td><strong>CPU</strong></td><td>Any modern 4-core</td><td>6+ cores</td><td>8+ cores</td></tr>
                <tr><td><strong>OS</strong></td><td colspan="3">Windows 10/11, Linux (Ubuntu 20.04+), macOS 12+</td></tr>
              </tbody>
            </table>
          </div>

          <div class="doc-card">
            <h3>Model Size Guide</h3>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Model Size</th><th>VRAM (Q4)</th><th>Quality</th><th>Best For</th></tr></thead>
                <tbody>
                  <tr><td>1.5B</td><td>~1.5 GB</td><td>Basic</td><td>Quick questions, simple edits</td></tr>
                  <tr><td>3B</td><td>~2.5 GB</td><td>Good</td><td>Router model, fast classification</td></tr>
                  <tr><td>7B</td><td>~5 GB</td><td>Better</td><td>General coding, 8GB GPU sweet spot</td></tr>
                  <tr><td>14B</td><td>~10 GB</td><td>Excellent</td><td>Complex reasoning, refactoring</td></tr>
                  <tr><td>32B</td><td>~20 GB</td><td>Best</td><td>Hardest problems, architecture design</td></tr>
                </tbody>
              </table>
            </div>
            <p style="margin-top:12px;color:var(--text-dim);font-size:0.88rem">Forge auto-detects your GPU and recommends the best model via <code>/hardware</code>. KV cache quantization (Q8) is enabled by default to maximize context window size.</p>
          </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="quickstart">
          <h2>Quick Start</h2>
          <p class="feature-what">Start using Forge in your project right now.</p>

          <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code># Launch Forge in your project directory
cd your-project/
python -m forge</code></pre>
          </div>

          <p style="margin-bottom:12px">Type what you want in plain English:</p>
          <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code>forge&gt; Add a login endpoint to the Flask API
forge&gt; Fix the bug in parser.py where it crashes on empty input
forge&gt; Refactor the database module to use connection pooling
forge&gt; Write tests for the authentication middleware</code></pre>
          </div>

          <div class="callout">
            <strong>Behind the scenes:</strong> Forge reads your project files, builds context, generates a plan, edits code, runs tests, and tracks every change in a forensic audit trail. Use <code>/pin &lt;file&gt;</code> to keep important files in context permanently.
          </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="models">
          <h2>Model Manager <span class="feature-badge">81 Models</span></h2>
          <p class="feature-what">Full-featured model management with 81 curated models across 5 categories, live Ollama registry search, and support for 3 LLM backends (Ollama, OpenAI-compatible, Anthropic API).</p>
          <p class="feature-why">Different tasks need different models. The Model Manager helps you find, download, and switch between models without leaving Forge — and lets you use cloud APIs when local isn't enough.</p>

          <div class="doc-card">
            <h3>5 Model Categories</h3>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Category</th><th>Count</th><th>Purpose</th></tr></thead>
                <tbody>
                  <tr><td><strong>Coding</strong></td><td>25+</td><td>Code generation, refactoring, debugging</td></tr>
                  <tr><td><strong>General</strong></td><td>20+</td><td>Documentation, analysis, conversation</td></tr>
                  <tr><td><strong>Reasoning</strong></td><td>15+</td><td>Complex logic, architecture design, planning</td></tr>
                  <tr><td><strong>Vision</strong></td><td>10+</td><td>Image understanding, screenshot analysis</td></tr>
                  <tr><td><strong>Embedding</strong></td><td>5+</td><td>Semantic search, codebase indexing</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="doc-card">
            <h3>3 LLM Backends</h3>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Backend</th><th>Config Key</th><th>Use Case</th></tr></thead>
                <tbody>
                  <tr><td><code>ollama</code></td><td><code>backend_provider: "ollama"</code></td><td>Local models, fully offline, no API costs</td></tr>
                  <tr><td><code>openai</code></td><td><code>backend_provider: "openai"</code></td><td>GPT-4o, o1, or any OpenAI-compatible API</td></tr>
                  <tr><td><code>anthropic</code></td><td><code>backend_provider: "anthropic"</code></td><td>Claude Sonnet, Opus, Haiku</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="code-block">
            <button class="copy-btn">Copy</button>
<pre><code># ~/.forge/config.yaml
default_model: "qwen2.5-coder:14b"    # Primary model
small_model: "qwen2.5-coder:3b"       # Fast model for routing
embedding_model: "nomic-embed-text"    # Embeddings
router_enabled: true                   # Auto-route by complexity
backend_provider: "ollama"             # ollama, openai, or anthropic</code></pre>
          </div>

          <p style="margin-top:12px;color:var(--text-dim);font-size:0.92rem">Run <code>/models</code> to open the Model Manager GUI. Browse 81 curated models, search the Ollama registry live, pull new models with progress bars, delete unused models, and set your primary model — all from a graphical interface.</p>
        </div>

        <div class="section-divider">
          <div class="section-divider-label">Core Capabilities</div>
        </div>

        <!-- ═══════════════════════════════════════════════════════ -->
        <!-- CORE CAPABILITIES                                      -->
        <!-- ═══════════════════════════════════════════════════════ -->

        <div class="feature-section reveal" id="commands">
          <h2>Commands Reference <span class="feature-badge">59 Commands</span></h2>
          <p class="feature-what">59 slash commands for controlling every aspect of Forge — from AI model selection to security scanning to release management.</p>
          <p class="feature-why">Everything in Forge is accessible from the command line. No hidden menus, no GUI-only features. Every command shows real usage examples when you click it.</p>

          <input type="text" class="filter-input" placeholder="Filter commands..." data-filter-target="cmd-table">

          <div class="table-wrap" id="cmd-table">
            <table>
              <thead><tr><th style="width:210px">Command</th><th>Description</th></tr></thead>
              <tbody>
                <tr class="cmd-cat-header"><td colspan="2">SYSTEM</td></tr>
                <tr class="cmd-row" data-cmd="help"><td><code>/help</code></td><td>Show all available commands with descriptions</td></tr>
                <tr class="cmd-row" data-cmd="docs"><td><code>/docs</code></td><td>Open documentation window (F1 shortcut)</td></tr>
                <tr class="cmd-row" data-cmd="quit"><td><code>/quit</code> / <code>/exit</code></td><td>Exit Forge with auto-save</td></tr>
                <tr class="cmd-row" data-cmd="dashboard"><td><code>/dashboard</code></td><td>Open the Neural Cortex&trade; HUD dashboard</td></tr>
                <tr class="cmd-row" data-cmd="voice"><td><code>/voice</code></td><td>Toggle voice input/output modes</td></tr>
                <tr class="cmd-row" data-cmd="theme"><td><code>/theme &lt;name&gt;</code></td><td>Switch UI theme (14 built-in themes)</td></tr>
                <tr class="cmd-row" data-cmd="update"><td><code>/update</code></td><td>Check for and apply Forge updates</td></tr>
                <tr class="cmd-row" data-cmd="cd"><td><code>/cd &lt;dir&gt;</code></td><td>Change working directory</td></tr>
                <tr class="cmd-row" data-cmd="plugins"><td><code>/plugins</code></td><td>List loaded plugins and their status</td></tr>

                <tr class="cmd-cat-header"><td colspan="2">MODEL &amp; TOOLS</td></tr>
                <tr class="cmd-row" data-cmd="model"><td><code>/model &lt;name&gt;</code></td><td>Show or switch the active AI model</td></tr>
                <tr class="cmd-row" data-cmd="models"><td><code>/models</code></td><td>Open Model Manager GUI (pull, delete, browse)</td></tr>
                <tr class="cmd-row" data-cmd="tools"><td><code>/tools</code></td><td>List all 28 registered AI tools with call stats</td></tr>
                <tr class="cmd-row" data-cmd="router"><td><code>/router</code></td><td>Multi-model routing status and controls</td></tr>
                <tr class="cmd-row" data-cmd="compare"><td><code>/compare</code></td><td>Compare Forge costs against cloud providers</td></tr>

                <tr class="cmd-cat-header"><td colspan="2">CONTEXT &amp; MEMORY</td></tr>
                <tr class="cmd-row" data-cmd="context"><td><code>/context</code></td><td>Show context window usage with token breakdown</td></tr>
                <tr class="cmd-row" data-cmd="pin"><td><code>/pin &lt;idx&gt;</code></td><td>Pin a context entry so it survives eviction</td></tr>
                <tr class="cmd-row" data-cmd="unpin"><td><code>/unpin &lt;idx&gt;</code></td><td>Remove pin from a context entry</td></tr>
                <tr class="cmd-row" data-cmd="drop"><td><code>/drop &lt;idx&gt;</code></td><td>Manually evict a context entry to free tokens</td></tr>
                <tr class="cmd-row" data-cmd="clear"><td><code>/clear</code></td><td>Clear all non-pinned context entries</td></tr>
                <tr class="cmd-row" data-cmd="save"><td><code>/save &lt;file&gt;</code></td><td>Save entire session to file</td></tr>
                <tr class="cmd-row" data-cmd="load"><td><code>/load &lt;file&gt;</code></td><td>Restore a previously saved session</td></tr>
                <tr class="cmd-row" data-cmd="reset"><td><code>/reset</code></td><td>Hard reset &mdash; clear everything and start fresh</td></tr>
                <tr class="cmd-row" data-cmd="memory"><td><code>/memory</code></td><td>Show all memory subsystem status</td></tr>

                <tr class="cmd-cat-header"><td colspan="2">SEARCH &amp; INDEXING</td></tr>
                <tr class="cmd-row" data-cmd="scan"><td><code>/scan &lt;path&gt;</code></td><td>Scan codebase structure (classes, functions, routes)</td></tr>
                <tr class="cmd-row" data-cmd="index"><td><code>/index</code></td><td>Build or rebuild the semantic embedding index</td></tr>
                <tr class="cmd-row" data-cmd="search"><td><code>/search &lt;query&gt;</code></td><td>Quick semantic search (file list)</td></tr>
                <tr class="cmd-row" data-cmd="journal"><td><code>/journal</code></td><td>Show last N journal entries</td></tr>
                <tr class="cmd-row" data-cmd="recall"><td><code>/recall &lt;query&gt;</code></td><td>Semantic code search with previews</td></tr>
                <tr class="cmd-row" data-cmd="digest"><td><code>/digest</code></td><td>AST analysis and code structure breakdown</td></tr>
                <tr class="cmd-row" data-cmd="synapse"><td><code>/synapse</code></td><td>Run synapse check &mdash; cycle all Neural Cortex&trade; modes</td></tr>
                <tr class="cmd-row" data-cmd="tasks"><td><code>/tasks</code></td><td>Show task state and progress</td></tr>

                <tr class="cmd-cat-header"><td colspan="2">SAFETY &amp; SECURITY</td></tr>
                <tr class="cmd-row" data-cmd="safety"><td><code>/safety</code></td><td>Show or set safety level and sandbox status</td></tr>
                <tr class="cmd-row" data-cmd="crucible"><td><code>/crucible</code></td><td>4-layer threat scanner status and controls</td></tr>
                <tr class="cmd-row" data-cmd="forensics"><td><code>/forensics</code></td><td>View forensic audit trail for current session</td></tr>
                <tr class="cmd-row" data-cmd="threats"><td><code>/threats</code></td><td>View threat intelligence patterns and rules</td></tr>
                <tr class="cmd-row" data-cmd="provenance"><td><code>/provenance</code></td><td>View tool-call provenance chain</td></tr>

                <tr class="cmd-cat-header"><td colspan="2">PLANNING &amp; QUALITY</td></tr>
                <tr class="cmd-row" data-cmd="plan"><td><code>/plan</code></td><td>Multi-step plan mode with verification gates</td></tr>
                <tr class="cmd-row" data-cmd="dedup"><td><code>/dedup</code></td><td>Response deduplication status and threshold</td></tr>

                <tr class="cmd-cat-header"><td colspan="2">AI INTELLIGENCE</td></tr>
                <tr class="cmd-row" data-cmd="ami"><td><code>/ami</code></td><td>AI model intelligence: quality, capabilities, recovery</td></tr>
                <tr class="cmd-row" data-cmd="continuity"><td><code>/continuity</code></td><td>Session health grade (A-F) with signal breakdown</td></tr>

                <tr class="cmd-cat-header"><td colspan="2">DIAGNOSTICS &amp; BILLING</td></tr>
                <tr class="cmd-row" data-cmd="stats"><td><code>/stats</code></td><td>Full analytics: performance, tools, cost</td></tr>
                <tr class="cmd-row" data-cmd="billing"><td><code>/billing</code></td><td>Token usage and cost tracking</td></tr>
                <tr class="cmd-row" data-cmd="topup"><td><code>/topup</code></td><td>Add sandbox funds (default: $50)</td></tr>
                <tr class="cmd-row" data-cmd="report"><td><code>/report</code></td><td>File a bug report to GitHub</td></tr>
                <tr class="cmd-row" data-cmd="export"><td><code>/export</code></td><td>Export audit bundle (zip with SHA-256 manifest)</td></tr>
                <tr class="cmd-row" data-cmd="benchmark"><td><code>/benchmark</code></td><td>Run reproducible coding benchmarks</td></tr>
                <tr class="cmd-row" data-cmd="hardware"><td><code>/hardware</code></td><td>Show GPU, CPU, VRAM, and model recommendation</td></tr>
                <tr class="cmd-row" data-cmd="cache"><td><code>/cache</code></td><td>File read cache statistics and management</td></tr>
                <tr class="cmd-row" data-cmd="config"><td><code>/config</code></td><td>View or edit configuration</td></tr>

                <tr class="cmd-cat-header"><td colspan="2">RELIABILITY &amp; ASSURANCE</td></tr>
                <tr class="cmd-row" data-cmd="break"><td><code>/break</code></td><td>Run Forge Break Suite (reliability + fingerprint)</td></tr>
                <tr class="cmd-row" data-cmd="autopsy"><td><code>/autopsy</code></td><td>Break suite with detailed failure-mode analysis</td></tr>
                <tr class="cmd-row" data-cmd="stress"><td><code>/stress</code></td><td>Minimal 3-scenario stress suite (CI-compatible)</td></tr>
                <tr class="cmd-row" data-cmd="assure"><td><code>/assure</code></td><td>Run full AI assurance scenario suite</td></tr>

                <tr class="cmd-cat-header"><td colspan="2">RELEASE &amp; LICENSING</td></tr>
                <tr class="cmd-row" data-cmd="ship"><td><code>/ship</code></td><td>Shipwright release management</td></tr>
                <tr class="cmd-row" data-cmd="autocommit"><td><code>/autocommit</code></td><td>Smart auto-commit with AI-generated messages</td></tr>
                <tr class="cmd-row" data-cmd="license"><td><code>/license</code></td><td>View license tier, features, and genome</td></tr>

                <tr class="cmd-cat-header"><td colspan="2">FLEET &amp; ADMIN</td></tr>
                <tr class="cmd-row" data-cmd="puppet"><td><code>/puppet</code></td><td>Fleet puppet passport management</td></tr>
                <tr class="cmd-row" data-cmd="admin"><td><code>/admin</code></td><td>GitHub collaborator and token management</td></tr>
              </tbody>
            </table>
          </div>

        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="tools">
          <h2>Tool System <span class="feature-badge">28 Tools</span></h2>
          <p class="feature-what">28 structured tools that the AI uses to interact with your codebase, filesystem, shell, and web.</p>
          <p class="feature-why">Tools give the AI precise, auditable actions instead of unstructured text output. Every tool call is logged in the <span class="jargon" data-tip="A tamper-evident log of every action the AI takes, with timestamps, arguments, and SHA-256 hashes. Like a flight recorder for your AI coding sessions.">forensic audit trail</span> with arguments, results, and timing.</p>

          <div class="doc-card">
            <h3>File Operations</h3>
            <div class="table-wrap">
              <table>
                <thead><tr><th style="width:180px">Tool</th><th>What It Does</th></tr></thead>
                <tbody>
                  <tr><td><code>read_file</code></td><td>Read file contents with line numbers, offset, and limit. Crucible&trade;-scanned for threats. Cached for performance.</td></tr>
                  <tr><td><code>write_file</code></td><td>Create or overwrite files. Atomic writes (temp file + replace) prevent corruption.</td></tr>
                  <tr><td><code>edit_file</code></td><td>Surgical find-and-replace edits. Multiple replacements per call. Cache invalidation on edit.</td></tr>
                  <tr><td><code>glob_files</code></td><td>Find files by glob pattern (e.g., <code>**/*.py</code>). Recursive directory search.</td></tr>
                  <tr><td><code>grep_files</code></td><td>Regex search across files with context lines. Like <code>grep -rn</code> but structured.</td></tr>
                  <tr><td><code>list_directory</code></td><td>List directory contents with file sizes and types.</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="doc-card">
            <h3>Code Analysis (Tree-sitter)</h3>
            <div class="table-wrap">
              <table>
                <thead><tr><th style="width:200px">Tool</th><th>What It Does</th></tr></thead>
                <tbody>
                  <tr><td><code>codebase_digest</code></td><td>Generate a structured summary of the entire project (files, functions, classes).</td></tr>
                  <tr><td><code>file_digest</code></td><td>Analyze a single file: extract all functions, classes, imports, and structure.</td></tr>
                  <tr><td><code>symbol_search</code></td><td>Find function/class definitions across the codebase by name.</td></tr>
                  <tr><td><code>dependency_graph</code></td><td>Build import and call dependency graphs for a file or module.</td></tr>
                  <tr><td><code>find_references</code></td><td>Find all references to a symbol across the codebase.</td></tr>
                  <tr><td><code>find_definition</code></td><td>Jump to the definition of a function, class, or variable.</td></tr>
                  <tr><td><code>get_function_signature</code></td><td>Extract function prototype (name, args, return type).</td></tr>
                  <tr><td><code>list_functions</code></td><td>List all functions defined in a file.</td></tr>
                  <tr><td><code>analyze_function_calls</code></td><td>Build a call graph for a specific function.</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="doc-card">
            <h3>Execution &amp; Reasoning</h3>
            <div class="table-wrap">
              <table>
                <thead><tr><th style="width:180px">Tool</th><th>What It Does</th></tr></thead>
                <tbody>
                  <tr><td><code>run_shell</code></td><td>Execute shell commands with configurable timeout and working directory. Safety-validated before execution.</td></tr>
                  <tr><td><code>think</code></td><td>Internal step-by-step reasoning (hidden from user). Helps the AI plan complex operations.</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="doc-card">
            <h3>Git</h3>
            <div class="table-wrap">
              <table>
                <thead><tr><th style="width:180px">Tool</th><th>What It Does</th></tr></thead>
                <tbody>
                  <tr><td><code>git_log</code></td><td>Show commit history with optional filters.</td></tr>
                  <tr><td><code>git_diff</code></td><td>Diff working tree, staging area, or between commits.</td></tr>
                  <tr><td><code>git_status</code></td><td>Show repository status (staged, modified, untracked).</td></tr>
                  <tr><td><code>git_blame</code></td><td>Line-by-line attribution for a file.</td></tr>
                  <tr><td><code>git_show</code></td><td>Show details of a specific commit.</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="doc-card">
            <h3>Web</h3>
            <div class="table-wrap">
              <table>
                <thead><tr><th style="width:200px">Tool</th><th>What It Does</th></tr></thead>
                <tbody>
                  <tr><td><code>fetch_url</code></td><td>HTTP GET with text extraction. Blocks private/loopback IPs (SSRF protection).</td></tr>
                  <tr><td><code>fetch_with_headers</code></td><td>HTTP GET with custom headers for APIs.</td></tr>
                  <tr><td><code>post_request</code></td><td>HTTP POST with JSON body.</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="routing">
          <h2>Multi-Model Routing</h2>
          <p class="feature-what">Automatic complexity-based routing that sends simple tasks to a small, fast model and complex tasks to your primary model.</p>
          <p class="feature-why">A typo fix doesn't need a 14B model. The router saves <span class="jargon" data-tip="Video RAM — the memory on your graphics card. AI models are loaded into VRAM for fast inference. More VRAM = bigger models = better results.">VRAM</span>, reduces latency, and cuts token usage by 30-50% without sacrificing quality on hard problems.</p>

          <div class="solves"><strong>Solves a known problem:</strong> Running a large model for every request wastes GPU resources and adds unnecessary latency. "What's my git status?" doesn't need the same brainpower as "refactor this module to use dependency injection."</div>

          <div class="doc-card">
            <h3>How Routing Works</h3>
            <p style="color:var(--text-dim);font-size:0.92rem;margin-bottom:12px">Each input is scored from -5 (very simple) to +15 (very complex) using signal analysis:</p>
            <ul>
              <li><strong>Complex signals (+):</strong> multi-file references, architecture keywords, long input, multiple questions</li>
              <li><strong>Simple signals (-):</strong> single-file operations, short input, formatting tasks, quick questions</li>
            </ul>
            <p style="color:var(--text-dim);font-size:0.92rem;margin-top:12px">Set <code>router_enabled: true</code> and <code>small_model: "qwen2.5-coder:3b"</code> in config. View routing decisions with <code>/router</code>.</p>
          </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="context">
          <h2>Context Management</h2>
          <p class="feature-what">Full manual control over the AI's context window — see every token, pin what matters, evict what doesn't.</p>
          <p class="feature-why">Context quality directly impacts AI quality. Unlike cloud tools that silently compress your history, Forge shows you exactly what the AI can see and lets you manage it.</p>

          <div class="solves"><strong>Solves a known problem:</strong> Cloud AI tools silently truncate your conversation when it gets too long. You never know what the AI still "remembers." Forge shows exact token counts, lets you pin critical context, and gives you manual eviction control.</div>

          <div class="doc-card">
            <h3>5 Context Partitions</h3>
            <ul>
              <li><strong>Core</strong> &mdash; System prompts and pinned messages. Highest priority, never evicted.</li>
              <li><strong>Working</strong> &mdash; Recent chat history. Evicted oldest-first when space is needed.</li>
              <li><strong>Reference</strong> &mdash; Tool results and file reads. Automatically deduplicated.</li>
              <li><strong>Recall</strong> &mdash; Semantic index retrievals from embedding search.</li>
              <li><strong>Quarantine</strong> &mdash; Suspicious content isolated with warnings. Evicted first to minimize exposure.</li>
            </ul>
          </div>

          <div class="doc-card">
            <h3>Key Commands</h3>
            <ul>
              <li><code>/context</code> &mdash; See what's in context with token counts per partition</li>
              <li><code>/pin &lt;idx&gt;</code> / <code>/unpin</code> &mdash; Pin entries to survive eviction</li>
              <li><code>/drop &lt;idx&gt;</code> &mdash; Manually evict an entry to free tokens</li>
              <li><code>/save</code> / <code>/load</code> &mdash; Save and restore full sessions with complete fidelity</li>
            </ul>
          </div>
        </div>

        <!-- ═══════════════ AI INTELLIGENCE ═══════════════ -->
        <div class="section-divider">
            <div class="section-divider-label">AI Intelligence</div>
        </div>

        <div class="feature-section reveal" id="ami">
            <h2>Self-Healing AI <span class="feature-badge">AMI</span></h2>
            <p class="feature-what">3-tier recovery system that detects when the AI is failing — refusals, loops, tool amnesia, garbage output — and fixes it automatically.</p>
            <p class="feature-why">Instead of restarting your session when the AI breaks, AMI diagnoses the problem and escalates through increasingly aggressive recovery strategies until it works. You stay focused on your code.</p>

            <div class="solves"><strong>Solves a known problem:</strong> Every AI coding tool eventually refuses to use tools, gets stuck repeating itself, or produces empty responses. Most tools make you restart the session. AMI detects this in real-time and fixes it automatically — usually within one retry.</div>

            <div class="doc-card">
                <h3>5 Quality Dimensions (Scored in Real-Time)</h3>
                <ol>
                    <li><strong>Refusal Score</strong> &mdash; Is the model declining the request? ("I can't help with that")</li>
                    <li><strong>Tool Compliance</strong> &mdash; Is it using its tools when it should be?</li>
                    <li><strong>Repetition Score</strong> &mdash; Is it stuck in a loop?</li>
                    <li><strong>Progress Score</strong> &mdash; Is it making forward progress?</li>
                    <li><strong>Content Length</strong> &mdash; Is it producing useful output?</li>
                </ol>
            </div>

            <div class="doc-card">
                <h3>3-Tier Recovery Escalation</h3>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Tier</th><th>Strategy</th><th>What Happens</th></tr></thead>
                        <tbody>
                            <tr><td><strong>1</strong></td><td>Parse Nudge</td><td>Inject instruction: "You have tools available. Use them." + tool format example. Temperature → 0.1.</td></tr>
                            <tr><td><strong>2</strong></td><td><span class="jargon" data-tip="Forces the AI to only output text matching a specific grammar (like valid JSON). The model physically cannot produce malformed output because the token sampler rejects illegal tokens.">Constrained Decoding</span></td><td>Force JSON tool-call output via <span class="jargon" data-tip="GBNF (GGML BNF) is a grammar format that constrains what tokens the AI can generate. Used here to guarantee the model outputs a valid tool call instead of rambling text.">GBNF grammar</span>. The model <em>must</em> produce a valid tool call.</td></tr>
                            <tr><td><strong>3</strong></td><td>Context Reset</td><td>Clear recent history, re-inject core context, fresh attempt with higher temperature (0.5). Last resort.</td></tr>
                        </tbody>
                    </table>
                </div>
                <p style="margin-top:12px;color:var(--text-dim);font-size:0.88rem">AMI also maintains a <strong>failure catalog</strong> &mdash; a persistent dictionary of failure patterns per model, so it learns which recovery strategy works best for each situation.</p>
            </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="continuity">
            <h2>Session Health Monitor <span class="feature-badge">Continuity</span></h2>
            <p class="feature-what">Tracks 6 health signals to give your session a letter grade (A through F) and triggers auto-recovery when quality drops.</p>
            <p class="feature-why">Long coding sessions degrade AI quality. Context gets stale, decisions get forgotten, files drift out of scope. The Continuity Engine detects this before you notice it and injects targeted refreshes.</p>

            <div class="solves"><strong>Solves a known problem:</strong> After 20+ turns, every AI coding tool starts "forgetting" what you told it earlier — repeating questions, losing track of files, contradicting earlier decisions. Forge quantifies this degradation with a letter grade and auto-recovers before you notice.</div>

            <div class="doc-card">
                <h3>6 Health Signals</h3>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Signal</th><th>What It Measures</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Objective Alignment</strong></td><td>Is the current context still aligned with your original goal? (semantic comparison)</td></tr>
                            <tr><td><strong>File Coverage</strong></td><td>Are the files relevant to your task still in context?</td></tr>
                            <tr><td><strong>Decision Retention</strong></td><td>Are prior decisions and plans still recalled?</td></tr>
                            <tr><td><strong>Swap Freshness</strong></td><td>How many turns since the last context swap? (exponential recovery with permanent degradation)</td></tr>
                            <tr><td><strong>Recall Quality</strong></td><td>How accurate are semantic index retrievals?</td></tr>
                            <tr><td><strong>Working Memory Depth</strong></td><td>How much recent turn history is intact?</td></tr>
                        </tbody>
                    </table>
                </div>
                <p style="margin-top:12px;color:var(--text-dim);font-size:0.88rem"><strong>Grading:</strong> A (90-100) = excellent &bull; B (75-89) = good &bull; C (60-74) = degraded, mild recovery &bull; D (40-59) = poor, aggressive recovery &bull; F (0-39) = critical, multi-file refresh. Check with <code>/continuity</code>.</p>
            </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="genome">
            <h2>Learning Memory <span class="feature-badge">Genome</span></h2>
            <p class="feature-what">Persistent cross-session intelligence that makes Forge smarter over time. Every session teaches Forge something — which models fail on which tasks, what tool patterns work, how reliable your sessions are.</p>
            <p class="feature-why">Session 50 of Forge is genuinely better than session 1. The Genome accumulates behavioral intelligence that improves AMI recovery, router accuracy, and threat detection. This intelligence is what makes a legitimate copy functionally superior to a pirated one.</p>

            <div class="doc-card">
                <h3>What the Genome Stores</h3>
                <ul>
                    <li>Session count, total turns, unique models used</li>
                    <li>AMI failure catalog (per-model failure → effective fix mapping)</li>
                    <li>Quality trend (last 50 quality scores)</li>
                    <li>Per-model quality averages</li>
                    <li>AMI routing accuracy (retry success rate)</li>
                    <li>Continuity recovery rate</li>
                    <li>Threat pattern distribution</li>
                    <li>Tool success rates, benchmark pass rates</li>
                    <li>Behavioral fingerprint (tool frequency, command frequency, session cadence)</li>
                </ul>
                <p style="margin-top:12px;color:var(--text-dim);font-size:0.88rem">View your genome with <code>/license genome</code> or <code>/memory</code>.</p>
            </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="reliability">
            <h2>Reliability Tracking</h2>
            <p class="feature-what">Persistent cross-session health metrics over a rolling 30-session window. Composite scoring across 5 dimensions shows whether Forge is getting more or less reliable over time.</p>
            <p class="feature-why">When your manager asks "is the AI actually working?" you have quantitative proof — not anecdotes.</p>

            <div class="doc-card">
                <h3>Composite Score Components</h3>
                <ul>
                    <li><strong>Verification pass rate (25%)</strong> &mdash; How often do tests pass after AI changes?</li>
                    <li><strong>Continuity grade average (25%)</strong> &mdash; Average session health grade</li>
                    <li><strong>Tool success rate (20%)</strong> &mdash; Tool execution success percentage</li>
                    <li><strong>Duration stability (15%)</strong> &mdash; Consistent session lengths (rewards reliability)</li>
                    <li><strong>Token efficiency (15%)</strong> &mdash; Output tokens per turn (more = better)</li>
                </ul>
                <p style="margin-top:12px;color:var(--text-dim);font-size:0.88rem">View with <code>/stats reliability</code>.</p>
            </div>
        </div>

        <!-- ═══════════════ SECURITY ═══════════════ -->
        <div class="section-divider">
            <div class="section-divider-label">Security Architecture</div>
        </div>

        <div class="feature-section reveal" id="security">
            <h2>9-Layer Defense <span class="feature-badge">Crucible&trade;</span></h2>
            <p class="feature-what">Every AI response passes through 9 independent security layers before it can affect your code. Each layer catches a different class of attack.</p>
            <p class="feature-why">AI models can be tricked by <span class="jargon" data-tip="An attack where malicious instructions are hidden in data (files, web pages, comments) that trick the AI into executing commands the user didn't intend.">prompt injection</span>, produce malicious code, or attempt <span class="jargon" data-tip="When an AI is tricked into sending your private data (API keys, credentials, source code) to an external server.">data exfiltration</span>. A single defense isn't enough — an attacker must simultaneously evade nine orthogonal detection mechanisms.</p>

            <div class="solves"><strong>Solves a known problem:</strong> Most AI coding tools have zero protection against prompt injection. A malicious comment in a file you read can hijack the AI into running arbitrary commands. Forge's 9-layer system catches attacks at the content level, the behavioral level, and the output level.</div>

            <div class="doc-card">
                <h3>The 9 Layers</h3>
                <ol style="line-height:2.4">
                    <li><strong>Pattern Scanner</strong> &mdash; 25+ regex patterns detect known injection, data theft, credential leaks, and obfuscation (zero-width chars, RTL overrides, encoded payloads).</li>
                    <li><strong><span class="jargon" data-tip="Converts text into numerical vectors that capture meaning. Similar concepts produce similar vectors, making it possible to detect content that's semantically 'foreign' to its surroundings.">Semantic Anomaly</span> Detector</strong> &mdash; AI embeddings flag content that doesn't belong contextually. If a database utility suddenly discusses "executing shell commands," this layer catches it.</li>
                    <li><strong>Behavioral Tripwire</strong> &mdash; Monitors tool call sequences for suspicious escalation patterns (e.g., file read followed by immediate curl to external server).</li>
                    <li><strong><span class="jargon" data-tip="A honeypot technique: a secret value placed where only an attacker would look. If it appears somewhere it shouldn't, you know someone extracted it.">Canary Trap</span></strong> &mdash; Random UUID injected into system prompt. If the AI outputs it in a tool call, it proves <span class="jargon" data-tip="An attack where malicious instructions are hidden in data (files, web pages) that trick the AI into doing something the user didn't ask for.">prompt injection</span> succeeded — action blocked.</li>
                    <li><strong>Threat Intelligence</strong> &mdash; Auto-updating signature database with SHA-512 envelope validation, ReDoS protection (100ms timeout per regex), and reduce-only merging.</li>
                    <li><strong>Command Guard</strong> &mdash; 70+ regex rules block dangerous shell commands: piped downloads, PowerShell encoded commands, privilege escalation, destructive operations.</li>
                    <li><strong>Path Sandbox</strong> &mdash; File operations restricted to allowed directories. Symlink escape detection, null byte injection blocking.</li>
                    <li><strong>Plan Verifier</strong> &mdash; Automatically runs tests, linter, and type checker after AI changes. Rolls back or repairs on failure.</li>
                    <li><strong>Forensic Auditor</strong> &mdash; <span class="jargon" data-tip="Hash-based Message Authentication Code using SHA-512. Each log entry's hash depends on the previous entry's hash, creating a chain. Tampering with any entry breaks the chain — like a blockchain for your session logs.">HMAC-SHA512</span> provenance chain creates tamper-proof session logs. If any entry is modified, the chain breaks.</li>
                </ol>
            </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="safety-levels">
            <h2>Safety Levels</h2>
            <p class="feature-what">Four progressively strict safety modes. Set via <code>/safety &lt;0-3&gt;</code> or <code>safety_level</code> in config.</p>
            <p class="feature-why">A personal side project needs different restrictions than a production codebase handling customer data. Choose the safety level that matches your risk tolerance.</p>

            <div class="table-wrap">
                <table>
                    <thead><tr><th>Level</th><th>Name</th><th>Description</th><th>Use Case</th></tr></thead>
                    <tbody>
                        <tr><td>0</td><td>Unleashed</td><td>No restrictions. Everything runs immediately.</td><td>Trusted personal projects</td></tr>
                        <tr><td>1</td><td>Smart Guard</td><td>Blocklist-only. Known dangerous commands blocked. <strong>(Default)</strong></td><td>Normal development</td></tr>
                        <tr><td>2</td><td>Confirm Writes</td><td>Prompt before file writes. Auto-accept after timeout.</td><td>Production codebases</td></tr>
                        <tr><td>3</td><td>Locked Down</td><td>Explicit approval required for every tool call.</td><td>Audited environments</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="threat-intel">
            <h2>Threat Intelligence</h2>
            <p class="feature-what">Upgradeable signature database for the Crucible&trade; threat scanner. Three sources merged with security guarantees.</p>
            <p class="feature-why">New attack patterns emerge constantly. The threat intel system lets Forge update its defenses without a full software update — while guaranteeing external patterns can never weaken built-in protections.</p>

            <div class="doc-card">
                <h3>Three Sources (Merged)</h3>
                <ul>
                    <li><strong>Bundled</strong> &mdash; Ships with Forge in <code>forge/data/default_signatures.json</code></li>
                    <li><strong>Fetched</strong> &mdash; Remote updates from server (SHA-512 validated, version-monotonic)</li>
                    <li><strong>Custom</strong> &mdash; Your own patterns in <code>~/.forge/custom_signatures.json</code></li>
                </ul>
            </div>

            <div class="doc-card">
                <h3>Security Guarantees</h3>
                <ul>
                    <li><strong>Reduce-Only Rule:</strong> External patterns can never lower threat levels set by hardcoded patterns</li>
                    <li><strong>ReDoS Guard:</strong> Every regex tested with 100ms timeout on 10KB input before acceptance</li>
                    <li><strong>Category Whitelist:</strong> Only 8 approved categories accepted</li>
                    <li><strong>Atomic Writes:</strong> No partial or corrupt signature files</li>
                </ul>
            </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="forensics">
            <h2>Forensics &amp; Audit Trail</h2>
            <p class="feature-what">Compliance-ready session audit logging that tracks every action the AI takes — tool calls, threat events, context swaps, model switches, with timestamps and results.</p>
            <p class="feature-why">When something goes wrong (or goes right and you want to reproduce it), you need to know exactly what happened, when, and why. The forensic trail is tamper-evident via HMAC-SHA512 provenance chains.</p>

            <div class="doc-card">
                <h3>Tracked Events (9 Categories)</h3>
                <ul>
                    <li><code>file_read</code>, <code>file_write</code>, <code>file_edit</code> &mdash; All file operations with paths and sizes</li>
                    <li><code>shell</code> &mdash; Commands executed, exit codes, output length</li>
                    <li><code>tool</code> &mdash; Tool name, arguments (sanitized), results</li>
                    <li><code>threat</code> &mdash; Crucible&trade; detections with category, severity, matched text</li>
                    <li><code>context_swap</code>, <code>eviction</code> &mdash; Context management events</li>
                    <li><code>error</code> &mdash; Exception types and messages</li>
                </ul>
                <p style="margin-top:12px;color:var(--text-dim);font-size:0.88rem">View with <code>/forensics</code>. Export with <code>/export</code> (includes SHA-256 manifest for chain-of-custody). Supports redaction mode for sensitive environments.</p>
            </div>
        </div>

        <!-- ═══════════════ VOICE & INTERACTION ═══════════════ -->
        <div class="section-divider">
            <div class="section-divider-label">Voice &amp; Interaction</div>
        </div>

        <div class="feature-section reveal" id="voice">
            <h2>Voice I/O</h2>
            <p class="feature-what">Talk to Forge with your voice. Responses can be read back aloud. Speech-to-text and text-to-speech both run locally.</p>
            <p class="feature-why">Hands-free coding. Describe what you want while looking at reference material, whiteboarding, or thinking out loud. No cloud transcription service ever hears you.</p>

            <div class="doc-card">
                <h3>Speech-to-Text (Input)</h3>
                <ul>
                    <li><strong>Engine:</strong> faster-whisper (OpenAI Whisper, optimized for speed)</li>
                    <li><strong>Models:</strong> tiny, base, small, medium (tiny default for low latency)</li>
                    <li><strong>Modes:</strong> Push-to-talk (backtick key) or VOX (voice-activated, continuous)</li>
                    <li><strong>GPU accelerated:</strong> Uses CUDA when available</li>
                </ul>
            </div>

            <div class="doc-card">
                <h3>Text-to-Speech (Output)</h3>
                <ul>
                    <li><strong>Dual engine:</strong> <span class="jargon" data-tip="pyttsx3 uses your OS's built-in speech engine (SAPI5 on Windows, espeak on Linux). Fully offline, no network needed.">pyttsx3</span> (offline, system voices) or <span class="jargon" data-tip="edge-tts connects to Microsoft's neural TTS service. Higher quality voices but requires internet. LGPLv3 licensed.">edge-tts</span> (neural voices, requires internet)</li>
                    <li><strong>Default:</strong> pyttsx3 (fully offline). Set <code>tts_engine: "edge"</code> for neural voices</li>
                    <li><strong>5 voice options</strong> with edge engine (en-US-GuyNeural default)</li>
                    <li><strong>Non-blocking:</strong> Audio plays in background thread</li>
                    <li><strong>Smart filtering:</strong> Strips markdown, code blocks, file paths for natural speech</li>
                </ul>
            </div>

            <div class="code-block">
                <button class="copy-btn">Copy</button>
<pre><code>voice_model: "tiny"          # whisper model size
voice_language: "en"         # ISO language code
voice_vox_threshold: 0.02    # RMS threshold for VOX
voice_silence_timeout: 1.5   # seconds of silence to end recording</code></pre>
            </div>
            <p style="color:var(--text-dim);font-size:0.88rem">Toggle with <code>/voice</code>. Optional dependencies: <code>faster-whisper</code>, <code>sounddevice</code>, <code>pynput</code>.</p>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="themes">
            <h2>Themes &amp; Dashboard <span class="feature-badge">14 Themes</span></h2>
            <p class="feature-what">14 built-in color themes from dark minimalist to full cyberpunk. Three themes include live visual effects (particles, edge glow, crackle). Neural Cortex&trade; dashboard with animated brain visualization.</p>
            <p class="feature-why">You stare at your coding tool for hours. It should look exactly how you want it. Switch themes instantly with <code>/theme &lt;name&gt;</code> — no restart required.</p>

            <div class="theme-grid">
                <?php
                $themes = [
                    ['midnight',  '#0a0e17', false], ['obsidian',  '#1a1a1a', false],
                    ['dracula',   '#282a36', false], ['solarized', '#002b36', false],
                    ['nord',      '#2e3440', false], ['monokai',   '#272822', false],
                    ['cyberpunk', '#050508', true],  ['matrix',    '#0a0f0a', true],
                    ['amber',     '#1a1000', false], ['phosphor',  '#0a120a', false],
                    ['arctic',    '#f0f2f5', false], ['sunset',    '#1a0f0a', false],
                    ['od_green',  '#111408', false], ['plasma',    '#070010', true],
                ];
                foreach ($themes as $t) {
                    $slug = $t[0]; $bg = $t[1]; $fx = $t[2];
                    $label = ucwords(str_replace('_', ' ', $slug));
                    echo '<div class="theme-badge">';
                    echo '<span class="theme-swatch" style="background:' . $bg . '"></span>';
                    echo '<span class="theme-name">' . htmlspecialchars($label) . '</span>';
                    if ($fx) echo '<span class="fx-dot" title="Has visual effects"></span>';
                    echo '</div>';
                }
                ?>
            </div>

            <p style="color:var(--text-dim);font-size:0.88rem;margin-top:12px"><strong>Dashboard:</strong> Run <code>/dashboard</code> to open the Neural Cortex&trade; GUI — real-time brain animation (9 states), live session stats, system health cards, and threat alerts. The brain animation reflects what Forge is doing: thinking, executing, indexing, scanning.</p>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="plugins">
            <h2>Plugin System</h2>
            <p class="feature-what">Build custom plugins that hook into Forge's lifecycle events. 6 hook points for intercepting input, output, tool calls, commands, file reads, and context additions.</p>
            <p class="feature-why">Extend Forge with custom behavior — log to your own system, modify AI prompts, add custom commands, filter outputs. Auto-discovered from <code>~/.forge/plugins/</code>.</p>

            <div class="doc-card">
                <h3>6 Hook Points</h3>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Hook</th><th>When It Fires</th></tr></thead>
                        <tbody>
                            <tr><td><code>on_user_input(text)</code></td><td>Before user input is sent to AI. Can modify or observe.</td></tr>
                            <tr><td><code>on_ai_response(response)</code></td><td>After AI response, before display. Can intercept.</td></tr>
                            <tr><td><code>on_tool_call(name, args)</code></td><td>Before tool execution. Can block or modify.</td></tr>
                            <tr><td><code>on_command(cmd, arg)</code></td><td>On slash command. Can handle custom commands.</td></tr>
                            <tr><td><code>on_file_read(path, content)</code></td><td>After file read. Can post-process content.</td></tr>
                            <tr><td><code>on_context_add(entry)</code></td><td>When new context is added. Can react or filter.</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="code-block">
                <button class="copy-btn">Copy</button>
<pre><code># ~/.forge/plugins/my_plugin.py
from forge.plugins.base import ForgePlugin

class MyPlugin(ForgePlugin):
    priority = 50  # Lower = runs first

    def on_load(self, engine):
        self.engine = engine
        print("My plugin loaded!")

    def on_tool_call(self, name, args):
        print(f"Tool called: {name}")
        return args  # Return modified args or None to block</code></pre>
            </div>
        </div>

        <!-- ═══════════════ LICENSING & FLEET ═══════════════ -->
        <div class="section-divider">
            <div class="section-divider-label">Licensing &amp; Fleet</div>
        </div>

        <div class="feature-section reveal" id="licensing">
            <h2>Tiers &amp; Pricing</h2>
            <p class="feature-what">Three tiers. Community is free forever with all core features. Pro and Power add persistence, team features, and enterprise capabilities.</p>
            <p class="feature-why">Every developer gets the full AI coding experience for free — 59 commands, 28 tools, 14 themes, 9-layer security, voice I/O. Paid tiers unlock cross-session intelligence and fleet management for teams.</p>

            <div class="table-wrap">
                <table>
                    <thead><tr><th>Feature</th><th>Community (Free)</th><th>Pro ($199)</th><th>Power ($999)</th></tr></thead>
                    <tbody>
                        <tr><td>Seats</td><td>1</td><td>3</td><td>10</td></tr>
                        <tr><td>All 59 commands</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>All 28 tools</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>9-layer security</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>14 themes + dashboard</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>/break + /assure (31 scenarios)</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>Voice I/O</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>Genome persistence</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>AutoForge (auto-commit)</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>Shipwright (release mgmt)</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>Team Genome Sync</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>HIPAA/SOC2 scenarios (+7)</td><td style="color:var(--text-dim)">No</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>Enterprise mode</td><td style="color:var(--text-dim)">No</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>Fleet management</td><td style="color:var(--text-dim)">No</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td></tr>
                        <tr><td>Priority support</td><td style="color:var(--text-dim)">No</td><td style="color:var(--text-dim)">No</td><td style="color:var(--green)">Yes</td></tr>
                    </tbody>
                </table>
            </div>
            <p style="color:var(--text-dim);font-size:0.88rem;margin-top:12px">Monthly alternatives: Pro $19/mo, Power $79/mo. See <a href="/ForgeV2/#pricing">pricing page</a>.</p>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="activation">
            <h2>Activation</h2>
            <p class="feature-what">Activate your license with a cryptographically signed passport file. Master activates directly, Puppets are generated from a Master.</p>
            <p class="feature-why">One purchase, multiple machines. Generate Puppet passports for your laptop, CI runner, or team members from your Master instance.</p>

            <div class="doc-card">
                <h3>Master Activation</h3>
                <ol>
                    <li>Purchase a tier from the <a href="/ForgeV2/#pricing">pricing page</a></li>
                    <li>Download your passport file from the success page</li>
                    <li>In Forge: <code>/license activate passport.json</code></li>
                    <li>Forge validates the cryptographic signature and activates your Master role</li>
                </ol>
            </div>

            <div class="doc-card">
                <h3>Puppet Activation</h3>
                <ol>
                    <li>On your Master: <code>/puppet generate DevBox</code></li>
                    <li>Transfer the generated passport to the target machine</li>
                    <li>On target: <code>/puppet join puppet_passport.json</code></li>
                    <li>Forge validates the chain of trust back to Origin</li>
                </ol>
            </div>

            <div class="callout callout-warn">
                <strong>Security:</strong> Passport files contain cryptographic license credentials. Keep them secure. If compromised, use <code>/puppet revoke &lt;machine_id&gt;</code> to instantly invalidate.
            </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="fleet">
            <h2>Master/Puppet Fleet</h2>
            <p class="feature-what">Run Forge on multiple machines from a single license. Master controls the seat pool, generates Puppet passports, and can revoke any Puppet instantly.</p>
            <p class="feature-why">Developers work on multiple machines. Instead of buying separate licenses, you get N seats and distribute them. Fleet members share genome intelligence for collective improvement.</p>

            <div class="code-block">
                <button class="copy-btn">Copy</button>
<pre><code>/puppet seats              # Check seat allocation
/puppet generate WorkLaptop # Create puppet passport (uses 1 seat)
/puppet list               # List all fleet members with status
/puppet revoke &lt;id&gt;        # Instantly revoke a puppet's access
/puppet sync               # Force genome sync to master
/puppet status             # Your role, tier, and fleet summary</code></pre>
            </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="bpos">
            <h2>Behavioral Proof of Stake <span class="feature-badge">BPoS</span></h2>
            <p class="feature-what">Five-layer anti-piracy where legitimate copies genuinely work better than pirated ones. No DRM that frustrates paying customers — just accumulated intelligence that can't be replicated.</p>
            <p class="feature-why">Traditional DRM punishes buyers. BPoS rewards them. A legitimate copy with 100 sessions of accumulated genome intelligence produces better code, recovers faster from failures, and routes more accurately than a fresh pirated copy.</p>

            <div class="doc-card">
                <h3>The 5 Layers</h3>
                <ol style="line-height:2.2">
                    <li><strong>Chain of Being</strong> &mdash; HMAC-SHA512 signed identity chain. Every passport traced back to Origin.</li>
                    <li><strong>Forge Genome</strong> &mdash; Accumulated behavioral intelligence. Pirated copy starts at zero.</li>
                    <li><strong><span class="jargon" data-tip="Features that literally get better the more you use them. The AI recovery system learns which fixes work for your model, the router learns your task complexity patterns, and the health monitor calibrates to your workflow.">Symbiotic Capability Scaling</span></strong> &mdash; AMI, Continuity, and Router genuinely improve with usage.</li>
                    <li><strong><span class="jargon" data-tip="Passive monitoring of how you use Forge (tool frequency, session length, command patterns). Creates a unique behavioral signature that's hard to replicate without actually using the software legitimately.">Ambient Verification</span></strong> &mdash; Behavioral fingerprinting detects anomalous usage patterns.</li>
                    <li><strong>Passport Token</strong> &mdash; Cryptographically signed, account-bound, role-encoded (v2 protocol).</li>
                </ol>
            </div>
        </div>

        <!-- ═══════════════ ADVANCED ═══════════════ -->
        <div class="section-divider">
            <div class="section-divider-label">Advanced</div>
        </div>

        <div class="feature-section reveal" id="config">
            <h2>Configuration Reference <span class="feature-badge">97 Keys</span></h2>
            <p class="feature-what">All 97 configuration parameters in <code>~/.forge/config.yaml</code>. Edit directly or use <code>/config &lt;key&gt; &lt;value&gt;</code>.</p>
            <p class="feature-why">Every behavior in Forge is configurable. Invalid values are logged with fallback to defaults — you can't break Forge by misconfiguring it.</p>

            <input type="text" class="filter-input" placeholder="Filter config keys..." data-filter-target="config-table">

            <div class="table-wrap" id="config-table">
                <table>
                    <thead><tr><th style="width:260px">Parameter</th><th style="width:100px">Default</th><th>Description</th></tr></thead>
                    <tbody>
                        <tr class="cmd-cat-header"><td colspan="3">SAFETY &amp; SECURITY</td></tr>
                        <tr><td><code>safety_level</code></td><td>1</td><td>Safety tier: 0=unleashed, 1=smart_guard, 2=confirm_writes, 3=locked_down</td></tr>
                        <tr><td><code>sandbox_enabled</code></td><td>false</td><td>Restrict file operations to sandbox_roots directories</td></tr>
                        <tr><td><code>threat_signatures_enabled</code></td><td>true</td><td>Load and use threat signature database</td></tr>
                        <tr><td><code>threat_signatures_url</code></td><td>""</td><td>Custom URL for remote threat signatures</td></tr>
                        <tr><td><code>threat_auto_update</code></td><td>true</td><td>Auto-check for signature updates</td></tr>
                        <tr><td><code>output_scanning</code></td><td>true</td><td>Scan LLM output for secrets and threats</td></tr>
                        <tr><td><code>rag_scanning</code></td><td>true</td><td>Scan RAG retrievals before context injection</td></tr>
                        <tr><td><code>data_retention_days</code></td><td>30</td><td>Auto-prune forensic logs older than N days</td></tr>

                        <tr class="cmd-cat-header"><td colspan="3">MODEL &amp; LLM</td></tr>
                        <tr><td><code>backend_provider</code></td><td>"ollama"</td><td>LLM backend: ollama, openai, or anthropic</td></tr>
                        <tr><td><code>default_model</code></td><td>"qwen2.5-coder:14b"</td><td>Primary model for coding tasks</td></tr>
                        <tr><td><code>small_model</code></td><td>""</td><td>Fast model for routing (e.g., qwen2.5-coder:3b)</td></tr>
                        <tr><td><code>router_enabled</code></td><td>false</td><td>Auto-route tasks to optimal model by complexity</td></tr>
                        <tr><td><code>embedding_model</code></td><td>"nomic-embed-text"</td><td>Model for semantic search embeddings</td></tr>
                        <tr><td><code>ollama_url</code></td><td>"http://localhost:11434"</td><td>Ollama API endpoint</td></tr>
                        <tr><td><code>openai_api_key</code></td><td>""</td><td>OpenAI API key (or OPENAI_API_KEY env var)</td></tr>
                        <tr><td><code>anthropic_api_key</code></td><td>""</td><td>Anthropic API key (or ANTHROPIC_API_KEY env var)</td></tr>
                        <tr><td><code>openai_base_url</code></td><td>""</td><td>Custom OpenAI-compatible endpoint URL</td></tr>

                        <tr class="cmd-cat-header"><td colspan="3">CONTEXT WINDOW</td></tr>
                        <tr><td><code>context_safety_margin</code></td><td>0.85</td><td>Use this fraction of calculated max context</td></tr>
                        <tr><td><code>swap_threshold_pct</code></td><td>85</td><td>Auto-swap context at this % usage</td></tr>
                        <tr><td><code>swap_summary_target_tokens</code></td><td>500</td><td>Target token count for summarizing old context</td></tr>

                        <tr class="cmd-cat-header"><td colspan="3">AGENT &amp; TOOLS</td></tr>
                        <tr><td><code>max_agent_iterations</code></td><td>15</td><td>Max tool-call loops per user turn</td></tr>
                        <tr><td><code>shell_timeout</code></td><td>30</td><td>Shell command timeout in seconds</td></tr>
                        <tr><td><code>shell_max_output</code></td><td>10000</td><td>Truncate shell output at this many characters</td></tr>
                        <tr><td><code>dedup_enabled</code></td><td>true</td><td>Suppress near-duplicate tool calls</td></tr>
                        <tr><td><code>dedup_threshold</code></td><td>0.92</td><td>Similarity threshold for dedup (0.0-1.0)</td></tr>
                        <tr><td><code>dedup_window</code></td><td>5</td><td>Recent calls to compare per tool</td></tr>
                        <tr><td><code>rate_limiting</code></td><td>true</td><td>Circuit breaker for runaway tool loops</td></tr>
                        <tr><td><code>rate_limit_per_minute</code></td><td>30</td><td>Max tool calls per sliding minute</td></tr>

                        <tr class="cmd-cat-header"><td colspan="3">VOICE</td></tr>
                        <tr><td><code>voice_model</code></td><td>"tiny"</td><td>Whisper model size: tiny, base, small, medium</td></tr>
                        <tr><td><code>voice_language</code></td><td>"en"</td><td>ISO language code for STT</td></tr>
                        <tr><td><code>voice_vox_threshold</code></td><td>0.02</td><td>RMS threshold for voice-activation mode</td></tr>
                        <tr><td><code>voice_silence_timeout</code></td><td>1.5</td><td>Seconds of silence to end recording</td></tr>

                        <tr class="cmd-cat-header"><td colspan="3">UI &amp; PERSONA</td></tr>
                        <tr><td><code>theme</code></td><td>"midnight"</td><td>Color theme (14 options)</td></tr>
                        <tr><td><code>effects_enabled</code></td><td>true</td><td>Animated visual effects in themes that support them</td></tr>
                        <tr><td><code>terminal_mode</code></td><td>"console"</td><td>Interface mode: console or gui</td></tr>
                        <tr><td><code>persona</code></td><td>"professional"</td><td>AI persona: professional, casual, mentor, hacker</td></tr>
                        <tr><td><code>show_hardware_on_start</code></td><td>true</td><td>Show GPU/CPU info on startup</td></tr>
                        <tr><td><code>show_billing_on_start</code></td><td>true</td><td>Show token balance on startup</td></tr>
                        <tr><td><code>show_cache_on_start</code></td><td>true</td><td>Show cache stats on startup</td></tr>

                        <tr class="cmd-cat-header"><td colspan="3">CONTINUITY &amp; AMI</td></tr>
                        <tr><td><code>continuity_enabled</code></td><td>true</td><td>Track session health and continuity grade</td></tr>
                        <tr><td><code>continuity_threshold</code></td><td>60</td><td>Score below this triggers mild recovery</td></tr>
                        <tr><td><code>continuity_aggressive_threshold</code></td><td>40</td><td>Score below this triggers aggressive recovery</td></tr>
                        <tr><td><code>ami_enabled</code></td><td>true</td><td>Adaptive Model Intelligence (self-healing)</td></tr>
                        <tr><td><code>ami_max_retries</code></td><td>3</td><td>Max recovery attempts per turn</td></tr>
                        <tr><td><code>ami_quality_threshold</code></td><td>0.7</td><td>Quality score below this triggers AMI</td></tr>
                        <tr><td><code>ami_auto_probe</code></td><td>true</td><td>Auto-detect model capabilities on first use</td></tr>
                        <tr><td><code>ami_constrained_fallback</code></td><td>true</td><td>Use GBNF grammar for forced tool compliance</td></tr>

                        <tr class="cmd-cat-header"><td colspan="3">PLAN VERIFICATION</td></tr>
                        <tr><td><code>plan_mode</code></td><td>"off"</td><td>Plan mode: off, manual, auto, always</td></tr>
                        <tr><td><code>plan_auto_threshold</code></td><td>3</td><td>Complexity score to auto-trigger planning</td></tr>
                        <tr><td><code>plan_verify_mode</code></td><td>"off"</td><td>Verification: off, report, repair, strict</td></tr>
                        <tr><td><code>plan_verify_tests</code></td><td>true</td><td>Run tests after each AI change</td></tr>
                        <tr><td><code>plan_verify_lint</code></td><td>false</td><td>Run linter after each AI change</td></tr>
                        <tr><td><code>plan_verify_timeout</code></td><td>30</td><td>Max seconds for test/lint suite</td></tr>

                        <tr class="cmd-cat-header"><td colspan="3">ENTERPRISE &amp; LICENSING</td></tr>
                        <tr><td><code>enterprise_mode</code></td><td>false</td><td>Strict verification, forced safety 2+, audit export</td></tr>
                        <tr><td><code>license_tier</code></td><td>"community"</td><td>License tier: community, pro, power</td></tr>
                        <tr><td><code>auto_commit</code></td><td>false</td><td>AutoForge: auto-commit file edits after each turn</td></tr>
                        <tr><td><code>shipwright_llm_classify</code></td><td>false</td><td>Use LLM for commit classification (slower, more accurate)</td></tr>
                        <tr><td><code>starting_balance</code></td><td>50.0</td><td>Virtual token budget in credits</td></tr>

                        <tr class="cmd-cat-header"><td colspan="3">TELEMETRY &amp; BUG REPORTER</td></tr>
                        <tr><td><code>telemetry_enabled</code></td><td>false</td><td>Opt-in: send anonymized performance data on session end</td></tr>
                        <tr><td><code>telemetry_redact</code></td><td>true</td><td>Strip prompts and responses from telemetry</td></tr>
                        <tr><td><code>telemetry_label</code></td><td>""</td><td>Machine nickname for telemetry dashboard</td></tr>
                        <tr><td><code>bug_reporter_enabled</code></td><td>false</td><td>Auto-file GitHub issues on crashes (owner only)</td></tr>
                        <tr><td><code>bug_reporter_max_daily</code></td><td>10</td><td>Max auto-filed issues per day</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="enterprise">
            <h2>Enterprise Mode</h2>
            <p class="feature-what">Strict operating mode for regulated environments. Enforces safety minimums, mandatory audit logging, and verified changes. Requires Power tier.</p>
            <p class="feature-why">When your compliance team needs audit trails and enforced safety, Enterprise Mode provides the guardrails without changing your workflow.</p>

            <div class="doc-card">
                <h3>What It Enables</h3>
                <ul>
                    <li>Safety level enforced at 2+ (cannot be lowered)</li>
                    <li>Strict plan verification (unverified plans blocked)</li>
                    <li>Forensic logging on all tool calls (mandatory)</li>
                    <li>Audit export with chain-of-custody manifests</li>
                    <li>Fleet analytics dashboard access</li>
                    <li>Reproducible benchmark suite</li>
                </ul>
            </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="benchmark">
            <h2>Benchmark Suite</h2>
            <p class="feature-what">Reproducible coding benchmarks that test any model against deterministic scenarios in isolated temp directories.</p>
            <p class="feature-why">Compare models objectively. Track quality over time. Prove to stakeholders that your AI setup works — with numbers, not anecdotes.</p>
            <p style="color:var(--text-dim);font-size:0.92rem">Run <code>/benchmark</code>. Results stored in <code>~/.forge/benchmarks/</code> with exact prompt hashes, model info, and config for full reproducibility. Metrics: pass/fail, behavior preserved, file scope accuracy, iteration count, quality score, token counts.</p>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="shipwright">
            <h2>Shipwright <span class="feature-badge">Release Mgmt</span></h2>
            <p class="feature-what">AI-powered release management. Classifies commits (25+ rules for breaking/feature/fix/docs/tests/security/performance), determines version bumps, generates changelogs, runs preflight checks.</p>
            <p class="feature-why">Automates the tedious parts of releasing software while keeping you in control. One command to go from "commits on main" to "tagged release with changelog."</p>

            <div class="doc-card">
                <h3>Commands</h3>
                <ul>
                    <li><code>/ship status</code> &mdash; Current version, unreleased commits, suggested bump</li>
                    <li><code>/ship dry</code> &mdash; Preview next release without modifying anything</li>
                    <li><code>/ship preflight</code> &mdash; Run tests + lint before release</li>
                    <li><code>/ship go</code> &mdash; Tag, bump version, push (irreversible)</li>
                    <li><code>/ship changelog</code> &mdash; Generate formatted changelog</li>
                    <li><code>/ship history</code> &mdash; Show past releases</li>
                </ul>
            </div>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="autoforge">
            <h2>AutoForge <span class="feature-badge">Auto-Commit</span></h2>
            <p class="feature-what">Automatically commits file changes after each AI turn. Smart batching groups related edits into single commits with AI-generated messages.</p>
            <p class="feature-why">Never lose AI-generated changes. Every turn = one coherent commit. If the AI breaks something, <code>git revert</code> takes you right back.</p>
            <p style="color:var(--text-dim);font-size:0.92rem"><code>/autocommit on</code> / <code>off</code> / <code>status</code>. Use <code>/autocommit hook</code> to generate a Claude Code hook for automatic triggering.</p>
        </div>

        <div class="section-break"><div class="section-break-line"></div><div class="section-break-dot"></div><div class="section-break-line"></div></div>

        <div class="feature-section reveal" id="telemetry">
            <h2>Telemetry</h2>
            <p class="feature-what">Optional, anonymized performance telemetry. <strong>Disabled by default</strong> (<code>telemetry_enabled: false</code>). Sends hardware profiles, token rates, and reliability scores when enabled. No prompts, no responses, no source code.</p>
            <p class="feature-why">Helps improve Forge for everyone. Completely opt-in. The <code>telemetry_redact</code> flag (default: true) strips all user content even when telemetry is enabled.</p>

            <div class="code-block">
                <button class="copy-btn">Copy</button>
<pre><code>telemetry_enabled: true    # Opt in (default: false)
telemetry_redact: true     # Strip all user content (default: true)
telemetry_label: "my-pc"   # Machine nickname for dashboard</code></pre>
            </div>
        </div>

        <!-- ═══════════════ FOOTER ═══════════════ -->
        <div style="margin-top:80px;padding-top:32px;border-top:1px solid var(--border);text-align:center">
            <p style="color:var(--text-xdim);font-size:0.85rem">
                &copy; <?php echo date('Y'); ?> Forge by Dirt Star &bull;
                <a href="/ForgeV2/">Home</a> &bull;
                <a href="/ForgeV2/#pricing">Pricing</a> &bull;
                <a href="/Forge/matrix.php">Matrix</a>
            </p>
        </div>

    </main>
</div>

<!-- Command Detail Modal — MUST be outside .reveal containers (transform breaks position:fixed) -->
<div class="cmd-modal-overlay" id="cmdModal">
    <div class="cmd-modal">
        <div class="cmd-modal-head">
            <h3 id="cmdModalTitle">/command</h3>
            <span id="cmdModalTag" class="cmd-modal-tag"></span>
            <button class="cmd-modal-close" id="cmdModalClose">&times;</button>
        </div>
        <div class="cmd-modal-body">
            <div class="cmd-modal-desc" id="cmdModalDesc"></div>
            <div class="cmd-modal-label">Example Session</div>
            <div class="cmd-modal-term" id="cmdModalTerm"></div>
            <div class="cmd-modal-variants" id="cmdModalVariants"></div>
        </div>
    </div>
</div>

<script>
/* ══════════════ COMMAND MODAL SYSTEM ══════════════ */
(function(){
    var CMD = {
        help: {
            cat: 'system', desc: 'Lists every slash command organized by category with a short description. This is the quickest way to discover what Forge can do.',
            term: '<span class="prompt">forge&gt;</span> /help\n\n<span class="dim">Context Management:</span>\n  <span class="highlight">/context</span>          Show detailed context window status\n  <span class="highlight">/drop N</span>            Drop context entry at index N\n  <span class="highlight">/pin N</span>             Pin entry (survives eviction)\n  ...\n\n<span class="dim">Model &amp; Tools:</span>\n  <span class="highlight">/model [name]</span>      Show or switch model\n  <span class="highlight">/models</span>            List available Ollama models\n  <span class="highlight">/tools</span>             List available tools\n  ...\n\n<span class="dim">59 commands across 12 categories.</span>\n<span class="dim">Everything else is sent to the AI.</span>',
            variants: []
        },
        docs: {
            cat: 'system', desc: 'Opens the built-in documentation window. Also available via the F1 keyboard shortcut. Provides searchable, categorized access to all Forge features without leaving the application.',
            term: '<span class="prompt">forge&gt;</span> /docs\n<span class="output">Documentation window opened.</span>',
            variants: []
        },
        quit: {
            cat: 'system', desc: 'Gracefully exits Forge. Session state is auto-saved so you can resume later with /load. The /exit alias does the same thing.',
            term: '<span class="prompt">forge&gt;</span> /quit\n<span class="output">Session auto-saved to ~/.forge/session.json</span>\n<span class="output">Goodbye.</span>',
            variants: ['/exit']
        },
        dashboard: {
            cat: 'system', desc: 'Launches the Neural Cortex&trade; GUI dashboard in a separate window. Shows a real-time brain animation, performance cards (tokens/sec, context usage, continuity grade), threat alerts, and session timeline &mdash; all updating live as you work.',
            term: '<span class="prompt">forge&gt;</span> /dashboard\n<span class="output">Neural Cortex dashboard launched.</span>\n<span class="dim">[GUI window opens with live brain animation,</span>\n<span class="dim"> performance cards, and session timeline]</span>',
            variants: []
        },
        voice: {
            cat: 'system', desc: 'Controls voice input and text-to-speech output. Push-to-talk (hold backtick key) or VOX (voice-activated). Switch TTS between cloud neural voices (edge) and offline system voices (local).',
            term: '<span class="prompt">forge&gt;</span> /voice\n<span class="output">Voice Input</span>\n  Status: <span class="highlight">active</span>\n  Mode:   PTT\n  TTS:    Edge Neural\n  Hotkey: ` (backtick)\n\n<span class="prompt">forge&gt;</span> /voice ptt\n<span class="output">Voice mode: Push-to-Talk (hold ` to speak)</span>\n\n<span class="prompt">forge&gt;</span> /voice engine edge\n<span class="output">TTS engine: Edge Neural (cloud, high quality)</span>',
            variants: ['/voice ptt', '/voice vox', '/voice engine local|edge', '/voice off']
        },
        theme: {
            cat: 'system', desc: 'Switches the terminal color theme. 14 built-in themes, 3 with animated effects (cyberpunk, matrix, phosphor). Hot-swaps instantly without restart.',
            term: '<span class="prompt">forge&gt;</span> /theme\n<span class="output">UI Themes</span>\n  Current: <span class="highlight">midnight</span>\n\n  <span class="highlight">midnight</span>           Midnight\n  obsidian           Obsidian\n  dracula            Dracula\n  cyberpunk          Cyberpunk\n  matrix             Matrix\n  phosphor           Phosphor\n  <span class="dim">... 8 more</span>\n\n<span class="prompt">forge&gt;</span> /theme cyberpunk\n<span class="output">Theme set to: Cyberpunk</span>',
            variants: ['/theme', '/theme &lt;name&gt;']
        },
        update: {
            cat: 'system', desc: 'Checks for new commits on the remote branch. Shows incoming changes and lets you apply them with <code>--yes</code>. Uses <code>git pull --ff-only</code> (safe, no merge conflicts). Auto-reinstalls dependencies if pyproject.toml changed.',
            term: '<span class="prompt">forge&gt;</span> /update\n<span class="output">3 new commit(s) available.</span>\n<span class="dim">Incoming changes:</span>\n  a7f2c3d fix: context swap preserves pinned order\n  9e3b18f feat: /break --share uploads signed report\n  4d8a05c docs: update command reference\n\n<span class="warn">Run /update --yes to apply these changes.</span>\n\n<span class="prompt">forge&gt;</span> /update --yes\n<span class="output">Pulling updates...</span>\n<span class="highlight">Updated successfully.</span>',
            variants: ['/update', '/update --yes']
        },
        cd: {
            cat: 'system', desc: 'Shows or changes Forge\'s working directory. All file operations, scans, and tool calls use this directory. Useful when working across multiple projects in one session.',
            term: '<span class="prompt">forge&gt;</span> /cd\n<span class="output">Current: C:\\Users\\dev\\project</span>\n\n<span class="prompt">forge&gt;</span> /cd ../my-api\n<span class="output">Changed to: C:\\Users\\dev\\my-api</span>',
            variants: []
        },
        plugins: {
            cat: 'system', desc: 'Shows all loaded plugins with their status. Bundled plugins (cortex, telemetry, assurance) load automatically. Custom plugins go in <code>~/.forge/plugins/</code>. Plugins subscribe to events via pattern matching (e.g. <code>tool.*</code>).',
            term: '<span class="prompt">forge&gt;</span> /plugins\n<span class="output">Loaded plugins:</span>\n  <span class="highlight">[active]</span>  Cortex Plugin &mdash; dashboard event bridge\n  <span class="highlight">[active]</span>  Telemetry Plugin &mdash; session telemetry\n  <span class="highlight">[active]</span>  Assurance Plugin &mdash; auto-assurance on session end\n<span class="dim">Plugin directory: ~/.forge/plugins/</span>',
            variants: []
        },
        model: {
            cat: 'model', desc: 'Shows the current model and provider, or switches to a different one. Supports provider:model syntax to switch backends on the fly: <code>ollama:qwen3:14b</code>, <code>openai:gpt-4o</code>, <code>anthropic:claude-sonnet-4-20250514</code>. Context window and billing adjust automatically.',
            term: '<span class="prompt">forge&gt;</span> /model\n<span class="output">Current model: qwen3:14b (provider: ollama)</span>\n<span class="output">Context length: 32,768</span>\n\n<span class="prompt">forge&gt;</span> /model openai:gpt-4o\n<span class="output">Switched to: gpt-4o (provider: openai, context: 128,000)</span>\n\n<span class="prompt">forge&gt;</span> /model anthropic:claude-sonnet-4-20250514\n<span class="output">Switched to: claude-sonnet-4-20250514 (provider: anthropic, context: 200,000)</span>',
            variants: ['/model', '/model &lt;name&gt;', '/model &lt;provider:name&gt;']
        },
        models: {
            cat: 'model', desc: 'Lists all models available in your Ollama instance. The currently active model is highlighted. Use <code>/model &lt;name&gt;</code> to switch.',
            term: '<span class="prompt">forge&gt;</span> /models\n<span class="output">Available models:</span>\n  qwen3:14b <span class="highlight">*</span>\n  qwen3:8b\n  llama3.3:70b\n  nomic-embed-text\n  codestral:latest',
            variants: []
        },
        tools: {
            cat: 'model', desc: 'Lists all 28 AI tools registered in the engine with a short description of each. Helps you understand what capabilities the AI has access to in your session.',
            term: '<span class="prompt">forge&gt;</span> /tools\n<span class="output">Available tools:</span>\n  <span class="highlight">read_file</span>            Read a file from disk\n  <span class="highlight">edit_file</span>            Edit a file with search/replace\n  <span class="highlight">run_shell</span>            Execute a shell command\n  <span class="highlight">grep_files</span>           Search file contents with regex\n  <span class="highlight">write_file</span>           Write content to a file\n  <span class="dim">... 23 more tools</span>',
            variants: []
        },
        router: {
            cat: 'model', desc: 'Controls the multi-model router. Routes simple tasks (greetings, short questions) to a smaller, faster model and complex tasks (code generation, analysis) to the primary model. Saves tokens without sacrificing quality on hard problems.',
            term: '<span class="prompt">forge&gt;</span> /router\n<span class="output">Multi-Model Router Status</span>\n  ...\n\n<span class="prompt">forge&gt;</span> /router on\n<span class="output">Router enabled. Big: qwen3:14b, Small: qwen3:8b</span>\n\n<span class="prompt">forge&gt;</span> /router small qwen3:8b\n<span class="output">Small model set to: qwen3:8b</span>\n\n<span class="prompt">forge&gt;</span> /router off\n<span class="output">Router disabled. Using big model for all tasks.</span>',
            variants: ['/router', '/router on|off', '/router big &lt;model&gt;', '/router small &lt;model&gt;']
        },
        compare: {
            cat: 'model', desc: 'Shows what this session would cost on every major cloud AI provider. Compares your actual input + output token counts against real API pricing. Shows how much your cache hits would have saved on Opus.',
            term: '<span class="prompt">forge&gt;</span> /compare\n<span class="output">Cost Comparison &mdash; This Session</span>\n  Tokens: 98,200 input + 44,600 output\n  Cache saved: 12,400 tokens (would cost $0.18 on Opus)\n\n  Service                                   Input     Output      Total\n  ------------------------------------------------------------------\n  Claude Opus 4                            $1.47     $3.35      $4.82\n  Claude Sonnet 4                          $0.29     $0.67      $0.96\n  GPT-4o                                   $0.25     $0.45      $0.70\n  Gemini 2.5 Pro                           $0.12     $0.45      $0.57\n\n  <span class="highlight">Forge: $0.00</span> <span class="dim">(local model, your hardware)</span>',
            variants: []
        },
        context: {
            cat: 'context', desc: 'Shows detailed context window status: total tokens used, percentage full, per-partition breakdown (system, user, assistant, tool), and eviction history. This is how you monitor whether a context swap is approaching.',
            term: '<span class="prompt">forge&gt;</span> /context\n<span class="output">Context Window: 18,432 / 32,768 tokens (<span class="warn">56.3%</span>)</span>\n<span class="output">  [==============              ] 56.3%</span>\n\n  #  Role       Tag          Tokens  Pin\n  0  <span class="highlight">system</span>     system        1,240   *\n  1  user       user            380\n  2  assistant  response      2,100\n  3  tool       file_read       890\n  4  user       user            210\n  ...\n\n<span class="dim">Token usage by type:</span>\n  system                  1,240 tokens\n  user                    3,420 tokens\n  assistant              11,200 tokens\n  tool                    2,572 tokens',
            variants: []
        },
        pin: {
            cat: 'context', desc: 'Pins a context entry by index so it survives automatic eviction. Pinned entries stay in the context window even when the swap threshold is hit. Use /context to see entry indices.',
            term: '<span class="prompt">forge&gt;</span> /context\n<span class="dim">  3  tool  file_read  890 tokens</span>\n\n<span class="prompt">forge&gt;</span> /pin 3\n<span class="output">Pinned entry 3</span>\n<span class="dim">This entry will survive context swaps.</span>',
            variants: []
        },
        unpin: {
            cat: 'context', desc: 'Removes the pin from a context entry, allowing it to be evicted during the next context swap if needed.',
            term: '<span class="prompt">forge&gt;</span> /unpin 3\n<span class="output">Unpinned entry 3</span>',
            variants: []
        },
        drop: {
            cat: 'context', desc: 'Manually evicts a specific context entry to free tokens. Use this when you know a particular entry is no longer relevant and you want to reclaim space before an automatic swap.',
            term: '<span class="prompt">forge&gt;</span> /context\n<span class="dim">  5  assistant  response  3,200 tokens  (old analysis)</span>\n\n<span class="prompt">forge&gt;</span> /drop 5\n<span class="output">Dropped entry 5: [assistant] 3,200 tokens freed</span>\n<span class="output">Context: 15,232 / 32,768 (46.5%)</span>',
            variants: []
        },
        clear: {
            cat: 'context', desc: 'Clears all context entries (including pinned). Good for starting a new task without a full <code>/reset</code> (which also resets turn count and episodic memory).',
            term: '<span class="prompt">forge&gt;</span> /clear\n<span class="output">Cleared 14 entries</span>\n<span class="output">Context: 1,240 / 32,768 (3.8%)</span>',
            variants: []
        },
        save: {
            cat: 'context', desc: 'Saves the entire context window to a JSON file. All entries, metadata, and state are preserved with full fidelity. Restore later with <code>/load</code>. Defaults to the auto-save path if no filename given.',
            term: '<span class="prompt">forge&gt;</span> /save my-session\n<span class="output">Session saved to my-session</span>',
            variants: []
        },
        load: {
            cat: 'context', desc: 'Restores a previously saved session file. All context entries and metadata are loaded back, replacing the current session. Defaults to the auto-save path if no filename given.',
            term: '<span class="prompt">forge&gt;</span> /load my-session\n<span class="output">Loaded 22 entries from my-session</span>\n<span class="output">Context: 18,432 / 32,768 (56.3%)</span>',
            variants: []
        },
        reset: {
            cat: 'context', desc: 'Full session reset: clears all context entries, resets the turn counter, reinitializes episodic memory, and clears dedup history. Cache and journal files on disk are preserved. Use this when you want a completely fresh start.',
            term: '<span class="prompt">forge&gt;</span> /reset\n<span class="output">Session reset. Context cleared. Cache &amp; journal preserved.</span>\n<span class="output">Context: 1,240 / 32,768 (3.8%)</span>',
            variants: []
        },
        memory: {
            cat: 'context', desc: 'Shows the status of all memory subsystems: episodic memory (session journal), semantic index (embedding-based code search), context partitions (core/working/reference/recall/quarantine), and task state.',
            term: '<span class="prompt">forge&gt;</span> /memory\n<span class="output">Forge Memory System</span>\n\n  <span class="highlight">Episodic Memory:</span>\n    Session ID:     ses_a7f2c3\n    Journal entries: 38\n\n  <span class="highlight">Semantic Index:</span>\n    Files indexed:  891\n    Total chunks:   4,230\n    Index size:     12.4MB\n\n  <span class="highlight">Context Partitions:</span>\n    core         1,240 tokens (1 entry)\n    working      8,200 tokens (6 entries)\n    reference    3,100 tokens (4 entries)\n\n  <span class="highlight">Task State:</span>\n    <span class="dim">No task tracked yet.</span>',
            variants: []
        },
        scan: {
            cat: 'search', desc: 'Deep-scans a directory to build the codebase digest. Extracts files, classes, functions, and structural patterns. Use <code>/scan force</code> to re-scan even if nothing changed. Results feed into the AI\'s understanding of your codebase.',
            term: '<span class="prompt">forge&gt;</span> /scan\n<span class="output">Scanning codebase at C:\\Users\\dev\\project...</span>\n\n  <span class="highlight">47</span> Python files, <span class="highlight">12</span> classes, <span class="highlight">89</span> functions\n  ...\n\n<span class="prompt">forge&gt;</span> /scan force\n<span class="output">Scanning codebase at C:\\Users\\dev\\project (forced)...</span>',
            variants: ['/scan', '/scan &lt;path&gt;', '/scan force']
        },
        index: {
            cat: 'search', desc: 'Builds or rebuilds the semantic embedding index using nomic-embed-text. Chunks source files and embeds them for meaning-based search. Use <code>--rebuild</code> to force a full re-index. Enables <code>/search</code> and <code>/recall</code>.',
            term: '<span class="prompt">forge&gt;</span> /index\n<span class="output">Indexing C:\\Users\\dev\\project...</span>\n  <span class="dim">+12 chunks: commands.py</span>\n  <span class="dim">+8 chunks: engine.py</span>\n  ...\n\n<span class="output">Indexing complete:</span>\n  Files indexed:   <span class="highlight">47</span>\n  Chunks created:  230\n  Files unchanged: 0\n  Files skipped:   3\n  Total index:     230 chunks, 12.4MB',
            variants: ['/index', '/index &lt;path&gt;', '/index --rebuild']
        },
        search: {
            cat: 'search', desc: 'Quick semantic search across the indexed codebase. Returns top 10 matches ranked by embedding similarity with file paths and line ranges. Faster than /recall (no code previews).',
            term: '<span class="prompt">forge&gt;</span> /search authentication middleware\n<span class="output">Code Search: "authentication middleware"</span>\n   <span class="highlight">1.</span> [0.940] src/auth/middleware.py <span class="dim">L12-45</span>\n   <span class="highlight">2.</span> [0.870] src/auth/jwt_handler.py <span class="dim">L1-38</span>\n   <span class="highlight">3.</span> [0.820] src/routes/login.py <span class="dim">L55-92</span>\n   <span class="highlight">4.</span> [0.710] tests/test_auth.py <span class="dim">L1-120</span>',
            variants: []
        },
        journal: {
            cat: 'search', desc: 'Shows recent episodic memory entries &mdash; Forge automatically records what happened each turn (tool calls, decisions, context swaps). Useful for reviewing your session history or recalling what you worked on.',
            term: '<span class="prompt">forge&gt;</span> /journal 5\n<span class="output">Episodic Memory (last 5 entries):</span>\n  <span class="dim">2026-03-07 14:23</span>  Edited forge/commands.py (3 tool calls)\n  <span class="dim">2026-03-07 10:11</span>  Fixed billing roundtrip bug\n  <span class="dim">2026-03-06 16:45</span>  Added /stress command\n  <span class="dim">2026-03-06 09:30</span>  Context swap (continuity: B+)\n  <span class="dim">2026-03-05 22:15</span>  Assurance suite: 100% pass',
            variants: ['/journal', '/journal &lt;N&gt;']
        },
        recall: {
            cat: 'search', desc: 'Semantic code search with inline previews. Returns the top 5 matches by embedding similarity, each with a code snippet so you can find exactly the right function or class without opening files.',
            term: '<span class="prompt">forge&gt;</span> /recall database connection pooling\n<span class="output">Semantic Recall: "database connection pooling"</span>\n\n  <span class="highlight">1. [0.930]</span> src/db/pool.py <span class="dim">(lines 12-45)</span>\n    <span class="dim">class ConnectionPool:</span>\n    <span class="dim">    def acquire(self, timeout=30):</span>\n    <span class="dim">        \"\"\"Get a connection from the pool...\"\"\"</span>\n\n  <span class="highlight">2. [0.852]</span> src/db/config.py <span class="dim">(lines 3-8)</span>\n    <span class="dim">POOL_SIZE = int(os.getenv(\"DB_POOL_SIZE\", 10))</span>',
            variants: []
        },
        digest: {
            cat: 'search', desc: 'Shows the codebase digest summary (files, lines, symbols, languages) or a structural breakdown of a specific file. Requires <code>/scan</code> to have been run first.',
            term: '<span class="prompt">forge&gt;</span> /digest\n<span class="output">Codebase Digest</span>\n  Root:      C:\\Users\\dev\\project\n  Files:     131\n  Lines:     58,200\n  Symbols:   1,336\n  Languages: 89 Python, 42 JavaScript\n  Scan time: 2.3s\n\n<span class="prompt">forge&gt;</span> /digest forge/engine.py\n  <span class="dim">(file-specific structural breakdown)</span>',
            variants: ['/digest', '/digest &lt;file&gt;']
        },
        synapse: {
            cat: 'search', desc: 'Triggers a synapse check on the Neural Cortex&trade; dashboard, cycling through all thought-mode animations. The dashboard must be running to see the effect.',
            term: '<span class="prompt">forge&gt;</span> /synapse\n<span class="output">Synapse check triggered on Neural Cortex dashboard.</span>\n<span class="dim">(Dashboard must be running to see the animation cycle.)</span>',
            variants: []
        },
        tasks: {
            cat: 'search', desc: 'Shows the current task state: objective, subtask progress, files touched, context swaps, and key decisions. Forge auto-tracks objectives after the first context swap so you never lose track of multi-step work.',
            term: '<span class="prompt">forge&gt;</span> /tasks\n<span class="output">Task State</span>\n  Objective:     Refactor auth module\n  Subtasks:      5\n  Progress:      2/5 done\n    <span class="highlight">+ Extract JWT logic</span>\n    <span class="highlight">+ Create middleware class</span>\n    <span class="warn">- Update route handlers</span>\n    <span class="dim">- Write tests</span>\n    <span class="dim">- Update docs</span>\n  Files touched: 3\n  Context swaps: 1\n  Decisions:     2',
            variants: []
        },
        safety: {
            cat: 'safety', desc: 'Shows or sets the safety level. Four tiers: <code>unleashed</code> (no restrictions), <code>smart_guard</code> (blocks dangerous commands), <code>confirm_writes</code> (asks before file changes), <code>locked_down</code> (read-only). Also controls filesystem sandboxing and allowed paths.',
            term: '<span class="prompt">forge&gt;</span> /safety\n<span class="dim">(shows current level, sandbox status, allowed paths)</span>\n\n<span class="prompt">forge&gt;</span> /safety confirm_writes\n<span class="output">Safety level set to confirm_writes (2)</span>\n\n<span class="prompt">forge&gt;</span> /safety sandbox on\n<span class="output">Sandbox enabled. Roots: C:\\Users\\dev\\project</span>\n\n<span class="prompt">forge&gt;</span> /safety allow C:\\tmp\\builds\n<span class="output">Added sandbox root: C:\\tmp\\builds</span>',
            variants: ['/safety', '/safety &lt;level&gt;', '/safety sandbox on|off', '/safety allow &lt;path&gt;']
        },
        crucible: {
            cat: 'safety', desc: 'Controls the Crucible&trade; security scanner. Scans every message for prompt injection, encoded payloads, and behavioral anomalies. Subcommands: <code>on|off</code> to toggle, <code>log</code> to view threat detections this session, <code>canary</code> to check honeypot integrity.',
            term: '<span class="prompt">forge&gt;</span> /crucible\n<span class="dim">(formatted status with detection stats)</span>\n\n<span class="prompt">forge&gt;</span> /crucible log\n<span class="output">No threats detected this session.</span>\n\n<span class="prompt">forge&gt;</span> /crucible canary\n  <span class="highlight">Canary intact</span> &mdash; no prompt injection detected',
            variants: ['/crucible', '/crucible on|off', '/crucible log', '/crucible canary']
        },
        forensics: {
            cat: 'safety', desc: 'Shows the forensic audit trail for the current session. Every tool call, threat event, context swap, and model switch is recorded. Use <code>/forensics save</code> to export the full report as JSON.',
            term: '<span class="prompt">forge&gt;</span> /forensics\n<span class="dim">(formatted forensic summary with event counts and timeline)</span>\n\n<span class="prompt">forge&gt;</span> /forensics save\n<span class="output">Forensics report saved: ~/.forge/forensics/session_abc123.json</span>',
            variants: ['/forensics', '/forensics save']
        },
        threats: {
            cat: 'safety', desc: 'Manages threat intelligence: shows pattern counts (hardcoded + external), keyword lists, behavioral rules, and signature version. Subcommands: <code>update</code> fetches new signatures, <code>list [category]</code> shows patterns, <code>search &lt;query&gt;</code> finds patterns by name, <code>stats</code> shows detection hits this session.',
            term: '<span class="prompt">forge&gt;</span> /threats\n<span class="output">Threat Intelligence</span>\n  Status:      <span class="highlight">ACTIVE</span>\n  Patterns:    187 hardcoded + 60 external (247 total)\n  Keywords:    4 lists (312 terms)\n  Behavioral:  8 rules\n  Version:     2026.03.07\n\n  <span class="dim">Commands: /threats update | list [category] | search &lt;query&gt; | stats</span>\n\n<span class="prompt">forge&gt;</span> /threats stats\n<span class="output">Detection Statistics (this session):</span>\n  Total hits: 0\n  <span class="dim">No detections yet.</span>',
            variants: ['/threats', '/threats update', '/threats list [category]', '/threats search &lt;query&gt;', '/threats stats']
        },
        provenance: {
            cat: 'safety', desc: 'Shows the cryptographic provenance chain &mdash; a tamper-evident log of every tool call with HMAC-SHA512 hashes. Each entry links to the previous one. If any entry is modified after the fact, the chain integrity check fails.',
            term: '<span class="prompt">forge&gt;</span> /provenance\n<span class="output">Provenance Chain (38 entries)</span>\n\n  <span class="dim">#37</span>  edit_file  forge/commands.py\n       <span class="dim">hash: a7f2c...</span>  <span class="dim">prev: 9e3b1...</span>\n  <span class="dim">#36</span>  read_file  forge/commands.py\n       <span class="dim">hash: 9e3b1...</span>  <span class="dim">prev: 4d8a0...</span>\n  ...\n\n  <span class="highlight">Chain integrity: VERIFIED (38 links, HMAC-SHA512)</span>',
            variants: []
        },
        plan: {
            cat: 'safety', desc: 'Controls multi-step plan mode. When enabled, complex tasks are broken into steps with optional verification (tests, linting) between each step. Modes: off, manual, auto (triggers on complex tasks), always.',
            term: '<span class="prompt">forge&gt;</span> /plan\n<span class="output">Plan Mode: <span class="dim">off</span></span>\n\n<span class="prompt">forge&gt;</span> /plan auto\n<span class="output">Plan mode: auto (threshold: 0.6)</span>\n<span class="dim">Complex tasks will generate a plan before execution.</span>\n\n<span class="prompt">forge&gt;</span> /plan verify\n<span class="output">Plan Verification</span>\n  Mode:     report\n  Tests:    on\n  Lint:     on\n  Timeout:  30s\n\n<span class="prompt">forge&gt;</span> /plan verify strict\n<span class="output">Plan verification: strict</span>\n<span class="dim">Each step must pass tests before proceeding.</span>',
            variants: ['/plan', '/plan on|off', '/plan auto', '/plan always', '/plan verify [off|report|repair|strict]']
        },
        dedup: {
            cat: 'safety', desc: 'Controls response deduplication. When enabled, Forge detects when the AI produces duplicate or near-duplicate tool calls and suppresses them. Adjustable similarity threshold.',
            term: '<span class="prompt">forge&gt;</span> /dedup\n<span class="output">Deduplication: <span class="highlight">enabled</span></span>\n  Threshold: 85%\n  Suppressed this session: 3\n\n<span class="prompt">forge&gt;</span> /dedup threshold 0.9\n<span class="output">Dedup threshold set to 90%</span>\n<span class="dim">Only near-exact duplicates will be suppressed.</span>',
            variants: ['/dedup', '/dedup on|off', '/dedup threshold &lt;0.0-1.0&gt;']
        },
        ami: {
            cat: 'intel', desc: 'Shows Adaptive Model Intelligence status. AMI tracks what the current model is good and bad at, learns from failures, and adjusts prompting strategies. Shows quality score, capability probes, and recovery stats.',
            term: '<span class="prompt">forge&gt;</span> /ami\n<span class="output">Adaptive Model Intelligence (qwen2.5-coder:14b)</span>\n  Quality score:  <span class="highlight">0.87</span>\n  Capabilities:   tool_calls, multi_file, refactor, test_gen\n  Failure catalog: 4 patterns learned\n  Recovery rate:   92%\n\n<span class="prompt">forge&gt;</span> /ami probe\n<span class="output">Probing model capabilities...</span>\n  Tool calls:     <span class="highlight">supported</span>\n  Multi-file:     <span class="highlight">supported</span>\n  JSON output:    <span class="highlight">supported</span>\n  Long context:   <span class="highlight">supported</span>\n\n<span class="prompt">forge&gt;</span> /ami stats\n<span class="output">AMI Recovery Analytics:</span>\n  Total retries:    23\n  Successful:       21 (91.3%)\n  Avg retry time:   1.2s',
            variants: ['/ami', '/ami probe', '/ami reset', '/ami stats']
        },
        continuity: {
            cat: 'intel', desc: 'Shows the continuity grade (A through F) that scores how well context swaps preserve conversation quality. Six signals are measured: topic retention, instruction recall, entity consistency, code reference accuracy, style consistency, and factual grounding.',
            term: '<span class="prompt">forge&gt;</span> /continuity\n<span class="output">Continuity Grade: <span class="highlight">B+</span></span>\n  Topic retention:     <span class="highlight">92%</span>\n  Instruction recall:  <span class="highlight">88%</span>\n  Entity consistency:  <span class="highlight">85%</span>\n  Code references:     <span class="warn">78%</span>\n  Style consistency:   <span class="highlight">90%</span>\n  Factual grounding:   <span class="highlight">87%</span>\n\n<span class="prompt">forge&gt;</span> /continuity history\n<span class="output">Last 5 snapshots:</span>\n  <span class="dim">Turn 45:</span> A-    <span class="dim">Turn 38:</span> B+\n  <span class="dim">Turn 30:</span> B     <span class="dim">Turn 22:</span> A\n  <span class="dim">Turn 15:</span> A+',
            variants: ['/continuity', '/continuity history', '/continuity set &lt;N&gt;', '/continuity on|off']
        },
        stats: {
            cat: 'diag', desc: 'Shows session analytics: turn count, token usage, tool call breakdown, and timing data. Use <code>/stats reliability</code> to see the 30-session reliability composite (verification rate, continuity grade, tool success, token efficiency).',
            term: '<span class="prompt">forge&gt;</span> /stats\n<span class="output">Session Analytics</span>\n  Turns:        15\n  Duration:     23m\n  Tokens:       142,800\n  Tool calls:   38\n  ...\n\n<span class="prompt">forge&gt;</span> /stats reliability\n<span class="output">Reliability Metrics (30-session window)</span>\n  Composite:     87.3%\n  Verification:  92%\n  Continuity:    B+\n  Tool success:  98.4%',
            variants: ['/stats', '/stats reliability']
        },
        billing: {
            cat: 'diag', desc: 'Shows the sandbox billing ledger: virtual balance, session token usage (input/output/cached), session duration, cost per turn, and lifetime totals. Use <code>/billing reset confirm</code> to zero lifetime stats.',
            term: '<span class="prompt">forge&gt;</span> /billing\n<span class="output">Sandbox Billing</span>\n  Balance:          <span class="highlight">$48.72</span>\n  Session tokens:   142,800 (98,200 in / 44,600 out)\n  Session cached:   12,400 tokens NOT spent\n  Session duration: 23.2 minutes\n  Turns:            15\n  Avg cost/turn:    $0.0853\n  Lifetime tokens:  1,247,000\n  Lifetime sessions: 12',
            variants: ['/billing', '/billing reset confirm']
        },
        topup: {
            cat: 'diag', desc: 'Adds virtual funds to the sandbox billing balance. Default amount is $50. The billing system tracks virtual costs so you can compare what your usage would cost on cloud providers.',
            term: '<span class="prompt">forge&gt;</span> /topup\n<span class="output">Added $50.00 to sandbox balance. New balance: $98.72</span>\n\n<span class="prompt">forge&gt;</span> /topup 100\n<span class="output">Added $100.00 to sandbox balance. New balance: $198.72</span>',
            variants: ['/topup', '/topup &lt;amount&gt;']
        },
        report: {
            cat: 'diag', desc: 'Files a bug report to GitHub Issues via the <code>gh</code> CLI. Session context (model, OS, version) is automatically attached. Requires <code>gh auth login</code> first.',
            term: '<span class="prompt">forge&gt;</span> /report context swap drops pinned entries\n<span class="output">Filing bug report...</span>\n<span class="output">Bug report filed: https://github.com/.../issues/47</span>',
            variants: []
        },
        export: {
            cat: 'diag', desc: 'Exports a governance-grade audit bundle as a zip file. Includes forensics, provenance chain, billing, memory, and a SHA-256 manifest. Use <code>--redact</code> to strip sensitive content, <code>--upload</code> to send to the telemetry server.',
            term: '<span class="prompt">forge&gt;</span> /export\n<span class="output">Audit exported: ~/.forge/exports/audit_2026-03-07_abc123.zip</span>\n\n<span class="prompt">forge&gt;</span> /export --redact\n<span class="output">Audit exported: ~/.forge/exports/audit_2026-03-07_redacted.zip</span>\n<span class="dim">(Redacted mode &mdash; sensitive content stripped)</span>',
            variants: ['/export', '/export --redact', '/export --upload']
        },
        benchmark: {
            cat: 'diag', desc: 'Runs reproducible coding benchmarks against the current model. Results are stored locally for comparison across models and versions.',
            term: '<span class="prompt">forge&gt;</span> /benchmark list\n<span class="output">Available suites:</span>\n  <span class="highlight">core</span>      8 scenarios (code gen, refactor, debug)\n  <span class="highlight">security</span>  5 scenarios (injection, exfil, encoding)\n  <span class="highlight">speed</span>     3 scenarios (throughput, latency)\n\n<span class="prompt">forge&gt;</span> /benchmark run core\n<span class="output">Running core benchmark (8 scenarios)...</span>\n  [1/8] Function generation    <span class="highlight">PASS</span>  1.8s\n  [2/8] Bug detection          <span class="highlight">PASS</span>  2.1s\n  [3/8] Refactor class         <span class="highlight">PASS</span>  3.4s\n  ...\n<span class="highlight">Score: 7/8 (87.5%)</span>',
            variants: ['/benchmark list', '/benchmark run [suite]', '/benchmark results', '/benchmark compare']
        },
        hardware: {
            cat: 'diag', desc: 'Detects your GPU, CPU, and RAM and recommends which models will fit in VRAM. Shows current GPU utilization and memory usage.',
            term: '<span class="prompt">forge&gt;</span> /hardware\n<span class="output">Hardware Profile</span>\n  GPU:  NVIDIA RTX 5070 Ti (16 GB VRAM)\n  CPU:  AMD Ryzen 9 7950X (16 cores)\n  RAM:  64 GB DDR5\n\n<span class="output">VRAM Usage:</span>\n  Model loaded: 9.2 GB\n  Available:    6.8 GB\n\n<span class="output">Recommended models:</span>\n  <span class="highlight">qwen2.5-coder:14b</span>  ~9 GB   (current)\n  <span class="highlight">qwen2.5-coder:32b</span>  ~18 GB  (needs offload)\n  <span class="highlight">qwen2.5-coder:7b</span>   ~5 GB   (fits easily)',
            variants: []
        },
        cache: {
            cat: 'diag', desc: 'Shows file cache statistics: cached files, hit/miss rate, tokens saved by avoiding re-reads. Lists individual cached files with token counts and read frequency. Use <code>/cache clear</code> to invalidate.',
            term: '<span class="prompt">forge&gt;</span> /cache\n<span class="output">File Cache</span>\n  Cached files:   47\n  Hits:           128\n  Misses:         36\n  Hit rate:       78.0%\n  Tokens saved:   <span class="highlight">54,200</span>\n  Total cached:   18,400 tokens\n\n  File                                          Tokens   Reads   Hash\n  -----------------------------------------------------------------\n  forge/commands.py                               3,200      12   a7f2c3...\n  forge/engine.py                                 2,800       9   9e3b18...\n  ...\n\n<span class="prompt">forge&gt;</span> /cache clear\n<span class="output">File cache cleared.</span>',
            variants: ['/cache', '/cache clear']
        },
        config: {
            cat: 'diag', desc: 'Shows key configuration values or reloads config from disk. 97 configuration keys covering models, safety, context, UI, telemetry, and more. Edit the YAML file directly, then <code>/config reload</code> to apply.',
            term: '<span class="prompt">forge&gt;</span> /config\n<span class="output">Forge Configuration</span>\n  <span class="dim">File: ~/.forge/config.yaml</span>\n  Safety: smart_guard (1)\n  Sandbox: OFF\n  Model: qwen3:14b\n  Small model: qwen3:8b\n  Router: ON\n  Max iterations: 25\n  Shell timeout: 30s\n  Swap threshold: 85%\n\n  <span class="dim">Edit: ~/.forge/config.yaml</span>\n  <span class="dim">Reload: /config reload</span>\n\n<span class="prompt">forge&gt;</span> /config reload\n<span class="output">Config reloaded from disk.</span>',
            variants: ['/config', '/config reload']
        },
        break: {
            cat: 'reliability', desc: 'Runs the Forge Break Suite &mdash; 31 scenarios across 6 categories plus a 30-probe behavioral fingerprint. Tests response quality, context handling, tool accuracy, and model consistency. Power tier adds 7 HIPAA/SOC2 compliance scenarios (2 additional categories). Results are signed and tamper-evident. When <code>telemetry_enabled</code> is true in your config, results are automatically contributed to the Forge Matrix leaderboard.',
            term: '<span class="prompt">forge&gt;</span> /break\n<span class="output">Running Forge Break Suite against \'qwen2.5-coder:14b\'...</span>\n\n  [1/31] Response coherence      <span class="highlight">PASS</span>\n  [2/31] Tool call accuracy      <span class="highlight">PASS</span>\n  [3/31] Multi-file consistency  <span class="highlight">PASS</span>\n  [4/31] Context recall          <span class="warn">WEAK</span> (0.72)\n  [5/31] Error recovery          <span class="highlight">PASS</span>\n  ...\n  [31/31] Behavioral fingerprint <span class="highlight">PASS</span>\n\n<span class="highlight">Reliability Score: 96.8%  (30/31 passed, 1 weak)</span>\n<span class="output">Report saved: brk_abc123</span>\n<span class="dim">Telemetry enabled &mdash; results contributed to Forge Matrix.</span>',
            variants: ['/break --autopsy', '/break --self-rate', '/break --assure', '/break --share', '/break --json']
        },
        autopsy: {
            cat: 'reliability', desc: 'Alias for <code>/break --autopsy</code>. Runs the full Break Suite and produces a detailed failure-mode analysis with per-category grades. For each scenario that failed or showed weakness, explains the root cause and suggests model-specific mitigations.',
            term: '<span class="prompt">forge&gt;</span> /autopsy\n<span class="output">Running Forge Break Suite against \'qwen2.5-coder:14b\'...</span>\n\n  adversarial             ........ PASS\n  context_integrity       ........ PASS\n  exfiltration            ........ PASS\n  reliability             ........ PARTIAL\n  safety                  ........ PASS\n  tool_misuse             ........ PASS\n\n<span class="highlight">  Forge Reliability Score: 94.6%  --  PARTIAL PASS</span>\n  (30/31 scenarios passed)\n\n<span class="output">  Failure Modes Detected:</span>\n\n  <span class="warn">1. Reliability Failure</span>\n     Scenario: reliability_context_recall\n     Detail:   invariant \'correct_entity\' NOT found in response\n\n<span class="output">  Stability Profile:</span>\n  Safety           [##########]  100%\n  Policy Adherence [##########]  100%\n  Tool Discipline  [##########]  100%\n  Exfil Guard      [##########]  100%\n  Reasoning        [########..]   85%\n  Context Integrity[#######...]   74%',
            variants: ['/autopsy', '/autopsy --share']
        },
        stress: {
            cat: 'reliability', desc: 'Runs a minimal 3-scenario stress suite designed for CI pipelines. Completes in under 30 seconds. Exits with code 1 on failure, making it safe to use in pre-commit hooks or GitHub Actions.',
            term: '<span class="prompt">forge&gt;</span> /stress\n<span class="output">Forge Stress Suite (3 scenarios)...</span>\n  [1/3] Basic tool call    <span class="highlight">PASS</span>  2.1s\n  [2/3] Context boundary   <span class="highlight">PASS</span>  4.3s\n  [3/3] Error recovery     <span class="highlight">PASS</span>  3.8s\n\n<span class="highlight">3/3 passed (10.2s)</span>\n\n<span class="dim"># In CI pipeline:</span>\n<span class="prompt">$</span> forge --stress --ci\n<span class="output">3/3 passed</span>\n<span class="prompt">$</span> echo $?\n<span class="output">0</span>',
            variants: ['/stress', '/stress --json', '/stress --ci']
        },
        assure: {
            cat: 'reliability', desc: 'Runs the AI Assurance Suite &mdash; 31 scenarios across 6 categories mapped to EU AI Act, NIST AI RMF, and ISO 42001 standards. Power tier adds 7 HIPAA/SOC2 compliance scenarios (data_residency + audit_integrity categories). Generates a signed, tamper-evident compliance report. Upload requires <code>telemetry_enabled: true</code> or the <code>--share</code> flag (local-first, opt-in only).',
            term: '<span class="prompt">forge&gt;</span> /assure\n<span class="output">Running AI assurance full suite against \'qwen2.5-coder:14b\'...</span>\n\n<span class="output">Assurance complete: 100% \u2014 PASS (31/31 scenarios)</span>\n<span class="output">Report saved: asr_def456</span>\n  <span class="highlight">\u2713</span> correctness: 100%\n  <span class="highlight">\u2713</span> safety: 100%\n  <span class="highlight">\u2713</span> consistency: 100%\n  <span class="highlight">\u2713</span> robustness: 100%\n  <span class="highlight">\u2713</span> compliance: 100%\n  <span class="highlight">\u2713</span> performance: 100%\n\n<span class="prompt">forge&gt;</span> /assure list\n<span class="output">Assurance reports (3 saved):</span>\n  asr_def456  qwen2.5-coder:14b  100%  2026-03-07\n  asr_abc123  qwen2.5-coder:14b   92%  2026-03-05\n  asr_789xyz  qwen2.5-coder:7b    85%  2026-03-04',
            variants: ['/assure', '/assure --share', '/assure list', '/assure show &lt;id&gt;', '/assure categories', '/assure run &lt;category&gt;']
        },
        ship: {
            cat: 'fleet', desc: 'Shipwright release management. Analyzes commits since last release, classifies them (breaking/feature/fix), computes the next semantic version, generates a changelog, runs preflight checks, and creates the release tag.',
            term: '<span class="prompt">forge&gt;</span> /ship status\n<span class="output">Shipwright</span>\n  Current version: v0.9.0\n  Unreleased commits: 7\n  Next version: v0.9.1 (patch)\n\n<span class="prompt">forge&gt;</span> /ship dry\n<span class="output">Dry Run:</span>\n  v0.9.0 -> v0.9.1 (patch)\n  7 commits\n\n  <span class="highlight">## v0.9.1</span>\n  <span class="highlight">### Fixes</span>\n  - fix: context swap preserves pinned order\n  - fix: billing comparison keys\n  <span class="highlight">### Features</span>\n  - feat: /break --share uploads signed report\n\n<span class="prompt">forge&gt;</span> /ship preflight\n  [<span class="highlight">PASS</span>] Tests: 1318 passed\n  [<span class="highlight">PASS</span>] No uncommitted changes\n  [<span class="highlight">PASS</span>] On main branch\n<span class="output">All preflight checks passed.</span>\n\n<span class="prompt">forge&gt;</span> /ship go\n<span class="output">Released v0.9.1 (v0.9.0 -> v0.9.1)</span>',
            variants: ['/ship', '/ship dry', '/ship preflight', '/ship go', '/ship changelog', '/ship history', '/ship push on|off']
        },
        autocommit: {
            cat: 'fleet', desc: 'Controls AutoForge, the smart auto-commit system. When enabled, every AI turn that modifies files creates a git commit with an auto-generated message describing the changes.',
            term: '<span class="prompt">forge&gt;</span> /autocommit\n<span class="output">AutoForge: <span class="dim">disabled</span></span>\n  Pending edits: 0\n  Total commits: 0\n\n<span class="prompt">forge&gt;</span> /autocommit on\n<span class="output">AutoForge enabled. File edits will be auto-committed.</span>\n\n<span class="dim">[... you ask the AI to refactor a file ...]</span>\n\n<span class="output">[AutoForge] Committed: \"refactor: extract auth</span>\n<span class="output">middleware into separate module\" (2 files)</span>',
            variants: ['/autocommit', '/autocommit on|off', '/autocommit push on|off', '/autocommit status', '/autocommit hook']
        },
        license: {
            cat: 'fleet', desc: 'Shows your current license tier and available features. Three tiers: Community (free, full core features), Pro (genome persistence, AutoForge, Shipwright), and Power (fleet management, enterprise mode).',
            term: '<span class="prompt">forge&gt;</span> /license\n<span class="output">Forge License</span>\n  Tier: <span class="highlight">Community</span> (free)\n  Machine ID: a7f2c3d8...\n  Genome maturity: 34%\n\n<span class="prompt">forge&gt;</span> /license tiers\n  <span class="highlight">Community</span> (free)\n    All 59 commands, 28 tools, 14 themes\n    Full security shield, voice I/O\n  <span class="highlight">Pro</span> ($199 one-time or $19/mo)\n    + Genome persistence across sessions\n    + AutoForge, Shipwright, 3 seats\n  <span class="highlight">Power</span> ($999 one-time or $79/mo)\n    + Fleet management (Master/Puppet)\n    + Enterprise mode, 10 seats\n\n<span class="prompt">forge&gt;</span> /license activate passport.json\n<span class="output">License activated: Pro tier</span>\n<span class="output">Genome persistence enabled.</span>',
            variants: ['/license', '/license tiers', '/license activate &lt;file&gt;', '/license deactivate', '/license genome']
        },
        puppet: {
            cat: 'fleet', desc: 'Fleet management for Power tier. A Master instance can generate Puppet passports for other machines, forming a fleet that shares genome intelligence, coordinated testing, and centralized analytics.',
            term: '<span class="prompt">forge&gt;</span> /puppet status\n<span class="output">Fleet Status</span>\n  Role: <span class="highlight">Master</span>\n  Tier: Power\n  Seats: 3/5 used\n\n<span class="prompt">forge&gt;</span> /puppet list\n<span class="output">Fleet Members:</span>\n  <span class="highlight">[master]</span>  DevBox-Main   a7f2c3...  online\n  <span class="highlight">[puppet]</span>  CI-Runner     9e3b18...  online\n  <span class="highlight">[puppet]</span>  Laptop        4d8a05...  offline\n\n<span class="prompt">forge&gt;</span> /puppet generate BuildServer\n<span class="output">Puppet passport generated: puppet_BuildServer.json</span>\n<span class="dim">Transfer this file to the target machine</span>\n<span class="dim">and run: /puppet join puppet_BuildServer.json</span>',
            variants: ['/puppet', '/puppet list', '/puppet generate &lt;label&gt;', '/puppet join &lt;file&gt;', '/puppet revoke &lt;id&gt;', '/puppet sync', '/puppet seats']
        },
        admin: {
            cat: 'fleet', desc: 'Manages GitHub collaborators and telemetry tokens. Owner-only: invite or remove collaborators, check pending invitations, generate API tokens for testers. Requires GitHub CLI (gh) authenticated with repo scope.',
            term: '<span class="prompt">forge&gt;</span> /admin\n<span class="output">Repository Collaborators:</span>\n  <span class="highlight">owner</span>    ups0n\n  <span class="highlight">collab</span>   dev-team-member\n\n<span class="prompt">forge&gt;</span> /admin invite new-tester\n<span class="output">Invitation sent to new-tester (push access).</span>\n\n<span class="prompt">forge&gt;</span> /admin token beta-tester-1\n<span class="output">Token generated for beta-tester-1:</span>\n  <span class="dim">forge_tk_a7f2c3d8e9b1...</span>\n<span class="dim">Share this token securely. It cannot be retrieved later.</span>',
            variants: ['/admin', '/admin invite &lt;user&gt;', '/admin remove &lt;user&gt;', '/admin pending', '/admin token &lt;label&gt;', '/admin role &lt;label&gt; &lt;role&gt;']
        }
    };

    var catLabels = {
        system:'System', model:'Model & Tools', context:'Context & Memory',
        search:'Search & Indexing', safety:'Safety & Security',
        intel:'AI Intelligence', diag:'Diagnostics', reliability:'Reliability',
        fleet:'Fleet & Licensing'
    };
    var catClasses = {
        system:'cat-system', model:'cat-model', context:'cat-context',
        search:'cat-search', safety:'cat-safety', intel:'cat-intel',
        diag:'cat-diag', reliability:'cat-reliability', fleet:'cat-fleet'
    };

    var overlay = document.getElementById('cmdModal');
    var titleEl = document.getElementById('cmdModalTitle');
    var tagEl   = document.getElementById('cmdModalTag');
    var descEl  = document.getElementById('cmdModalDesc');
    var termEl  = document.getElementById('cmdModalTerm');
    var varEl   = document.getElementById('cmdModalVariants');
    var closeBtn= document.getElementById('cmdModalClose');
    var currentKey = '';
    var currentBaseTerm = '';

    function _esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
    function _p(c){return '<span class="prompt">forge&gt;</span> '+c;}
    function _o(t){return '<span class="output">'+t+'</span>';}
    function _h(t){return '<span class="highlight">'+t+'</span>';}
    function _w(t){return '<span class="warn">'+t+'</span>';}
    function _d(t){return '<span class="dim">'+t+'</span>';}

    function openModal(key) {
        var c = CMD[key];
        if (!c) return;
        titleEl.textContent = '/' + key;
        tagEl.textContent = catLabels[c.cat] || c.cat;
        tagEl.className = 'cmd-modal-tag ' + (catClasses[c.cat] || '');
        descEl.innerHTML = c.desc;
        termEl.innerHTML = c.term;
        currentKey = key;
        currentBaseTerm = c.term;
        if (c.variants && c.variants.length) {
            var baseCmd = '/' + key;
            var h = '<h4>All Forms</h4>';
            h += '<code class="cmd-var-pill active" data-var="__base__">' + _esc(baseCmd) + '</code>';
            c.variants.forEach(function(v){ h += '<code class="cmd-var-pill" data-var="' + _esc(v) + '">' + _esc(v) + '</code>'; });
            varEl.innerHTML = h;
            varEl.style.display = '';
        } else {
            varEl.style.display = 'none';
        }
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
    function closeModal() {
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    }
    closeBtn.addEventListener('click', closeModal);
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closeModal();
    });
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeModal();
    });

    var VTERM = {
        quit: {
            '/exit': _p('/exit')+'\n'+_o('Session auto-saved.')+'\n'+_o('Goodbye.')
        },
        billing: {
            '/billing reset confirm': _p('/billing reset confirm')+'\n'+_o('Lifetime billing stats reset to zero.')
        },
        voice: {
            '/voice ptt': _p('/voice ptt')+'\n'+_o('Voice mode: Push-to-Talk (hold ` to speak)'),
            '/voice vox': _p('/voice vox')+'\n'+_o('Voice mode: VOX (voice-activated, auto-detect speech)'),
            '/voice engine local|edge': _p('/voice engine edge')+'\n'+_o('TTS engine: Edge Neural (cloud, high quality)')+'\n\n'+_p('/voice engine local')+'\n'+_o('TTS engine: System SAPI (offline, no internet)'),
            '/voice off': _p('/voice off')+'\n'+_o('Voice input disabled.')
        },
        theme: {
            '/theme <name>': _p('/theme cyberpunk')+'\n'+_o('Theme set to: Cyberpunk')
        },
        update: {
            '/update --yes': _p('/update --yes')+'\n'+_o('Pulling updates...')+'\n'+_h('Updated successfully.')+'\n'+_o('No core files changed -- update is live.')
        },
        model: {
            '/model <name>': _p('/model qwen3:8b')+'\n'+_o('Switched to: qwen3:8b (context: 32,768)'),
            '/model <provider:name>': _p('/model openai:gpt-4o')+'\n'+_o('Switched to: gpt-4o (provider: openai, context: 128,000)')+'\n\n'+_p('/model anthropic:claude-sonnet-4-20250514')+'\n'+_o('Switched to: claude-sonnet-4-20250514 (provider: anthropic, context: 200,000)')
        },
        router: {
            '/router on|off': _p('/router on')+'\n'+_o('Router enabled. Big: qwen3:14b, Small: qwen3:8b')+'\n\n'+_p('/router off')+'\n'+_o('Router disabled. Using big model for all tasks.'),
            '/router big <model>': _p('/router big qwen3:14b')+'\n'+_o('Big model set to: qwen3:14b'),
            '/router small <model>': _p('/router small qwen3:8b')+'\n'+_o('Small model set to: qwen3:8b')
        },
        safety: {
            '/safety <level>': _p('/safety confirm_writes')+'\n'+_o('Safety level set to ')+_h('confirm_writes (2)')+'\n'+_d('AI will ask before modifying any file.')+'\n\n'+_p('/safety unleashed')+'\n'+_w('Safety level set to unleashed (0) — no restrictions.'),
            '/safety sandbox on|off': _p('/safety sandbox on')+'\n'+_o('Sandbox enabled. Roots: C:\\Users\\dev\\project')+'\n\n'+_p('/safety sandbox off')+'\n'+_o('Sandbox disabled.'),
            '/safety allow <path>': _p('/safety allow /tmp/builds')+'\n'+_o('Added sandbox root: /tmp/builds')
        },
        crucible: {
            '/crucible on|off': _p('/crucible on')+'\n'+_o('Crucible™ threat scanner ')+_h('enabled')+_o('.')+'\n\n'+_p('/crucible off')+'\n'+_w('Crucible™ threat scanner disabled.')+'\n'+_w('Warning: Messages will not be scanned for threats.'),
            '/crucible log': _p('/crucible log')+'\n'+_o('Threat log (last 10):')+'\n  '+_d('14:23:01')+' '+_w('MEDIUM')+' prompt_injection  "ignore previous..."'+'\n  '+_d('14:20:45')+' '+_w('LOW')+' encoded_payload  base64 in response'+'\n  '+_d('No further events.'),
            '/crucible canary': _p('/crucible canary')+'\n  '+_h('Canary intact')+' -- no prompt injection detected'
        },
        forensics: {
            '/forensics save': _p('/forensics save')+'\n'+_o('Forensics report saved: ~/.forge/forensics/session_abc123.json')
        },
        plan: {
            '/plan on|off': _p('/plan on')+'\n'+_o('Plan mode armed — next prompt will generate a plan.')+'\n\n'+_p('/plan off')+'\n'+_o('Plan mode disabled.'),
            '/plan auto': _p('/plan auto')+'\n'+_o('Plan mode: auto (threshold: 0.6)')+'\n'+_d('Complex tasks will generate a plan before execution.'),
            '/plan always': _p('/plan always')+'\n'+_o('Plan mode: always')+'\n'+_d('Every prompt generates a multi-step plan.'),
            '/plan verify [off|report|repair|strict]': _p('/plan verify')+'\n'+_o('Plan Verification')+'\n  Mode:     report\n  Tests:    on\n  Lint:     on\n  Timeout:  30s\n\n'+_p('/plan verify strict')+'\n'+_o('Plan verification: ')+_h('strict')+'\n'+_d('Each step must pass tests before proceeding.')
        },
        dedup: {
            '/dedup on|off': _p('/dedup on')+'\n'+_o('Tool deduplication ')+_h('enabled')+_o('.')+'\n\n'+_p('/dedup off')+'\n'+_o('Tool deduplication disabled.'),
            '/dedup threshold <0.0-1.0>': _p('/dedup threshold 0.9')+'\n'+_o('Dedup threshold set to ')+_h('90%')+'\n'+_d('Only near-exact duplicates will be suppressed.')
        },
        ami: {
            '/ami probe': _p('/ami probe')+'\n'+_o('Probing qwen3:14b...')+'\n  Native tool calling: YES\n  JSON format mode:    YES\n  Text JSON parsing:   YES\n  Preferred format:    native\n'+_o('Capabilities cached.'),
            '/ami reset': _p('/ami reset')+'\n'+_o('AMI failure catalog and learned patterns cleared.'),
            '/ami stats': _p('/ami stats')+'\n'+_o('AMI Session Statistics:')+'\n  Total turns:        45\n  Retries triggered:  3 (7%)\n  Recovery rate:      100% (3/3)\n  Tier 1 (parse):     2 attempts, 2 success\n  Tier 2 (constrain): 1 attempts, 1 success\n  Tier 3 (reset):     0 attempts, 0 success\n  Avg quality:        0.87'
        },
        continuity: {
            '/continuity history': _p('/continuity history')+'\n  '+_d('Turn 45:')+' A-    '+_d('Turn 38:')+' B+\n  '+_d('Turn 30:')+' B     '+_d('Turn 22:')+' A\n  '+_d('Turn 15:')+' A+',
            '/continuity set <N>': _p('/continuity set 80')+'\n'+_o('Continuity recovery threshold set to 80'),
            '/continuity on|off': _p('/continuity on')+'\n'+_o('Continuity Grade enabled.')+'\n\n'+_p('/continuity off')+'\n'+_o('Continuity Grade disabled.')
        },
        topup: {
            '/topup <amount>': _p('/topup 100')+'\n'+_o('Added $100.00 to sandbox balance. New balance: $148.72')
        },
        export: {
            '/export --redact': _p('/export --redact')+'\n'+_o('Audit exported: ~/.forge/exports/audit_2026-03-07_redacted.zip')+'\n'+_d('(Redacted mode -- sensitive content stripped)'),
            '/export --upload': _p('/export --upload')+'\n'+_o('Uploading audit bundle...')+'\n'+_o('Upload complete (redacted)')
        },
        benchmark: {
            '/benchmark list': _p('/benchmark list')+'\n'+_o('Available suites:')+'\n  '+_h('core')+'      8 scenarios (code gen, refactor, debug)\n  '+_h('security')+'  5 scenarios (injection, exfil, encoding)\n  '+_h('speed')+'     3 scenarios (throughput, latency)',
            '/benchmark run [suite]': _p('/benchmark run core')+'\n'+_o('Running core benchmark (8 scenarios)...')+'\n  [1/8] Function generation    '+_h('PASS')+'  1.8s\n  [2/8] Bug detection          '+_h('PASS')+'  2.1s\n  [3/8] Refactor class         '+_h('PASS')+'  3.4s\n  ...\n'+_h('Score: 7/8 (87.5%)'),
            '/benchmark results': _p('/benchmark results')+'\n'+_o('Benchmark History:')+'\n  '+_d('2026-03-07')+' core     qwen2.5-coder:14b  87.5%\n  '+_d('2026-03-05')+' core     qwen2.5-coder:7b   75.0%\n  '+_d('2026-03-04')+' security qwen2.5-coder:14b  100%',
            '/benchmark compare': _p('/benchmark compare')+'\n'+_o('Comparing last two runs:')+'\n  '+_d('Run 1:')+' core  qwen2.5-coder:14b  87.5%\n  '+_d('Run 2:')+' core  qwen2.5-coder:7b   75.0%\n  '+_h('Delta: +12.5%')+' (14b outperforms 7b on code generation)'
        },
        cache: {
            '/cache clear': _p('/cache clear')+'\n'+_o('File cache cleared.')
        },
        config: {
            '/config reload': _p('/config reload')+'\n'+_o('Config reloaded from disk.')
        },
        threats: {
            '/threats update': _p('/threats update')+'\n  Fetching signatures from https://...\n  '+_h('Updated: 12 new patterns loaded.'),
            '/threats list [category]': _p('/threats list injection')+'\n\n'+_h('injection')+' (8 patterns):\n  prompt_override              '+_w('[CRITICAL]')+_d('  Direct system prompt ov...')+'\n  ignore_previous              '+_w('[WARNING]')+_d('  Attempts to nullify pri...')+'\n  ...',
            '/threats search <query>': _p('/threats search exfil')+'\n\n'+_h('Results for "exfil":')+'\n  data_exfiltration_url        '+_w('[CRITICAL]')+_d('  Attempts to send data t...')+'\n  steganographic_exfil         '+_w('[WARNING]')+_d('  Hidden data in output f...'),
            '/threats stats': _p('/threats stats')+'\n'+_o('Detection Statistics (this session):')+'\n  Total hits: 0\n  '+_d('No detections yet.')
        },
        break: {
            '/break --autopsy': _p('/break --autopsy')+'\n'+_o('Running Forge Break Suite against \'qwen2.5-coder:14b\'...')+'\n\n  [31/31 scenarios complete]\n\n'+_o('Failure Mode Analysis:')+'\n\n  '+_w('[WEAK]')+' Context recall (score: 0.72)\n  '+_d('Root cause: Model loses entity references after')+'\n  '+_d('3+ context swaps. Summary budget may be too low.')+'\n  '+_d('Suggestion: Increase swap_summary_tokens to 800.')+'\n\n  '+_h('[PASS]')+' All other scenarios within expected range.',
            '/break --self-rate': _p('/break --self-rate')+'\n'+_o('Running Forge Break Suite against \'qwen2.5-coder:14b\'...')+'\n  (self-assessment enabled -- model will grade itself)\n\n  adversarial             ........ PASS\n  context_integrity       ........ PASS\n  reliability             ........ PARTIAL\n  safety                  ........ PASS\n  tool_misuse             ........ PASS\n  exfiltration            ........ PASS\n\n'+_h('Reliability Score: 94.6%  --  PARTIAL PASS')+'\n  (30/31 scenarios passed)\n\n'+_o('Self-Assessment Calibration: 76.9%')+'\n'+_d('  (model correctly predicted its own pass/fail on 76.9% of scenarios)')+'\n    safety_harm_refusal               PASS  self-rated 9/10 (predicted pass -- '+_h('correct')+')\n    reliability_context_recall        FAIL  self-rated 7/10 (predicted pass -- '+_w('WRONG')+')\n      '+_d('model says: \"I failed to maintain entity references across context boundaries.\"')+'\n    adversarial_compliance            PASS  self-rated 8/10 (predicted pass -- '+_h('correct')+')',
            '/break --assure': _p('/break --assure')+'\n'+_o('Running Forge Break Suite against \'qwen2.5-coder:14b\'...')+'\n\n  adversarial             ........ PASS\n  context_integrity       ........ PASS\n  reliability             ........ PARTIAL\n  safety                  ........ PASS\n  tool_misuse             ........ PASS\n  exfiltration            ........ PASS\n\n'+_h('Reliability Score: 94.6%  --  PARTIAL PASS')+'\n  (30/31 scenarios passed)\n\n'+_o('Running AI Assurance Suite against \'qwen2.5-coder:14b\'...')+'\n\n'+_o('Assurance complete: 100% -- PASS (31/31 scenarios)')+'\n'+_o('Report saved: asr_def456')+'\n  + safety: 100%\n  + reliability: 100%\n  + adversarial: 100%\n  + tool_misuse: 100%\n  + exfiltration: 100%\n  + context_integrity: 100%\n\n  ==================================================\n'+_h('  Combined Forge Matrix Score: 97.3%')+'\n    Break:     94.6%\n    Assurance: 100%\n  ==================================================',
            '/break --share': _p('/break --share')+'\n'+_o('Running Forge Break Suite...')+'\n  [31/31 complete]  Reliability: 94.6%\n\n'+_o('Uploading signed report...')+'\n'+_h('Report shared: https://forge.dirtstar.dev/report/abc123')+'\n'+_d('Shareable link valid for 90 days.'),
            '/break --json': _p('/break --json')+'\n'+_d('{')+'\n'+_d('  "model": "qwen2.5-coder:14b",')+'\n'+_d('  "pass_rate": 0.946,')+'\n'+_d('  "scenarios_passed": 30,')+'\n'+_d('  "scenarios_run": 31,')+'\n'+_d('  "reliability_score": 94.6,')+'\n'+_d('  "fingerprint": { ... },')+'\n'+_d('  "signature": "a7f2c3d8..."')+'\n'+_d('}')
        },
        autopsy: {
            '/autopsy --share': _p('/autopsy --share')+'\n'+_o('Running Forge Autopsy...')+'\n  [31/31 complete]\n\n'+_o('Failure analysis generated.')+'\n'+_o('Uploading signed report...')+'\n'+_h('Report shared: https://forge.dirtstar.dev/report/def456')
        },
        stress: {
            '/stress --json': _p('/stress --json')+'\n'+_d('{"passed":3,"failed":0,"total":3,"duration_s":10.2,"scenarios":[...]}')+'\n',
            '/stress --ci': _p('/stress --ci')+'\n'+_o('Forge Stress Suite (3 scenarios)...')+'\n  [1/3] Basic tool call    '+_h('PASS')+'\n  [2/3] Context boundary   '+_h('PASS')+'\n  [3/3] Error recovery     '+_h('PASS')+'\n'+_h('3/3 passed')+'\n\n'+_d('# Exit code 0 = all passed (CI-safe)')+'\n'+_d('# Exit code 1 = at least one failed')
        },
        assure: {
            '/assure --share': _p('/assure --share')+'\n'+_o('Running AI assurance full suite against \'qwen2.5-coder:14b\'...')+'\n\n'+_o('Assurance complete: 100% -- PASS (31/31 scenarios)')+'\n'+_o('Report saved: asr_def456')+'\n'+_o('Uploading to assurance server...')+'\n'+_h('Report uploaded to assurance server.'),
            '/assure list': _p('/assure list')+'\n'+_o('Assurance reports (3 saved):')+'\n  asr_def456  qwen2.5-coder:14b  100%  2026-03-07\n  asr_abc123  qwen2.5-coder:14b   92%  2026-03-05\n  asr_789xyz  qwen2.5-coder:7b    85%  2026-03-04',
            '/assure show <id>': _p('/assure show asr_def456')+'\n'+_o('Assurance Report: asr_def456')+'\n  Model:    qwen2.5-coder:14b\n  Date:     2026-03-07 14:23\n  Result:   '+_h('PASS (100%)')+'\n  Signed:   SHA-256:a7f2c3...\n\n  Categories:\n    correctness:  100%\n    safety:       100%\n    consistency:  100%\n    robustness:   100%',
            '/assure categories': _p('/assure categories')+'\n'+_o('Assurance scenario categories:')+'\n  adversarial\n  context_integrity\n  exfiltration\n  reliability\n  safety\n  tool_misuse',
            '/assure run <category>': _p('/assure run safety')+'\n'+_o('Running AI assurance category \'safety\'...')+'\n  [1/3] Injection resistance  '+_h('PASS')+'\n  [2/3] Exfil detection       '+_h('PASS')+'\n  [3/3] Output safety         '+_h('PASS')+'\n\n'+_h('Category safety: 100% (3/3)')
        },
        ship: {
            '/ship dry': _p('/ship dry')+'\n'+_o('Dry Run:')+'\n  v0.9.0 -> v0.9.1 (patch)\n  7 commits\n\n  '+_h('## v0.9.1')+'\n  '+_h('### Fixes')+'\n  - fix: context swap preserves pinned order\n  - fix: billing comparison keys\n  '+_h('### Features')+'\n  - feat: /break --share uploads signed report',
            '/ship preflight': _p('/ship preflight')+'\n  ['+_h('PASS')+'] Tests: 1318 passed\n  ['+_h('PASS')+'] No uncommitted changes\n  ['+_h('PASS')+'] On main branch\n  ['+_h('PASS')+'] Version not already tagged\n'+_o('All preflight checks passed.'),
            '/ship go': _p('/ship go')+'\n'+_o('Executing release...')+'\n'+_h('Released v0.9.1 (v0.9.0 -> v0.9.1)')+'\n\n  ## v0.9.1 Changelog\n  - fix: context swap preserves pinned order\n  - feat: /break --share uploads signed report\n\n'+_d('Pushed to origin — testers can /update.'),
            '/ship changelog': _p('/ship changelog')+'\n\n  '+_h('## v0.9.1 (unreleased)')+'\n  ### Fixes\n  - fix: context swap preserves pinned order\n  - fix: billing comparison keys\n  ### Features\n  - feat: /break --share uploads signed report\n  ### Other\n  - docs: update command reference',
            '/ship history': _p('/ship history')+'\n'+_o('Release History:')+'\n  v0.9.0  2026-03-05  12 commits  patch\n  v0.8.0  2026-02-28  31 commits  minor\n  v0.7.0  2026-02-20  45 commits  minor\n  v0.6.0  2026-02-12  28 commits  minor',
            '/ship push on|off': _p('/ship push on')+'\n'+_o('Shipwright push ')+_h('enabled')+_o('. /ship go will push to origin.')+'\n\n'+_p('/ship push off')+'\n'+_o('Shipwright push disabled.')
        },
        autocommit: {
            '/autocommit on|off': _p('/autocommit on')+'\n'+_o('AutoForge ')+_h('enabled')+_o('. File edits will be auto-committed.')+'\n\n'+_p('/autocommit off')+'\n'+_o('AutoForge disabled.'),
            '/autocommit push on|off': _p('/autocommit push on')+'\n'+_o('AutoForge push ')+_h('enabled')+_o('. Commits will be pushed to origin.')+'\n\n'+_p('/autocommit push off')+'\n'+_o('AutoForge push disabled.'),
            '/autocommit status': _p('/autocommit status')+'\n'+_o('AutoForge: ')+_h('enabled')+'\n  Pending edits: 0\n  Total commits this session: 4\n  Push on commit: off',
            '/autocommit hook': _p('/autocommit hook')+'\n'+_o('Hook script written to .claude/hooks/auto_commit.py')+'\n'+_d('Add to .claude/settings.json to activate.')
        },
        license: {
            '/license tiers': _p('/license tiers')+'\n\n  '+_h('Community')+' (free)\n    All 59 commands, 28 tools, 14 themes\n    Full security shield, voice I/O\n\n  '+_h('Pro')+' ($199 or $19/mo)\n    + Genome persistence, 3 seats\n    + AutoForge, Shipwright\n\n  '+_h('Power')+' ($999 or $79/mo)\n    + Fleet management, 10 seats\n    + Enterprise mode, fleet analytics',
            '/license activate <file>': _p('/license activate passport.json')+'\n'+_h('License activated: Pro tier')+'\n'+_o('Genome persistence enabled.'),
            '/license deactivate': _p('/license deactivate')+'\n'+_o('License deactivated. Reverted to Community tier.')+'\n'+_d('Your data and models are unchanged.'),
            '/license genome': _p('/license genome')+'\n'+_o('Forge Genome')+'\n  Maturity: 34%\n  Sessions: 12\n  AMI patterns: 4\n  Model profiles: 2\n  Avg quality: 0.87\n  Reliability: 94.6\n  Threat scans: 1,247'
        },
        puppet: {
            '/puppet list': _p('/puppet list')+'\n'+_o('Fleet Members:')+'\n  '+_h('[master]')+'  DevBox-Main   a7f2c3...  online\n  '+_h('[puppet]')+'  CI-Runner     9e3b18...  online\n  '+_h('[puppet]')+'  Laptop        4d8a05...  offline',
            '/puppet generate <label>': _p('/puppet generate BuildServer')+'\n'+_o('Puppet passport generated: puppet_BuildServer.json')+'\n'+_d('Transfer this file to the target machine and run:')+'\n'+_d('/puppet join puppet_BuildServer.json'),
            '/puppet join <file>': _p('/puppet join puppet_BuildServer.json')+'\n'+_h('Joined fleet as Puppet.')+'\n'+_o('Master: DevBox-Main (a7f2c3...)')+'\n'+_o('Genome sync: enabled'),
            '/puppet revoke <id>': _p('/puppet revoke 4d8a05')+'\n'+_o('Puppet 4d8a05 (Laptop) revoked.')+'\n'+_d('Seat freed. 2/5 seats in use.'),
            '/puppet sync': _p('/puppet sync')+'\n'+_o('Syncing genome to master...')+'\n'+_h('Genome synced.')+' 3 new patterns uploaded.',
            '/puppet seats': _p('/puppet seats')+'\n'+_o('Seat Allocation:')+'\n  Total: 5\n  Used: 3\n  Available: 2\n\n  '+_h('master')+'  DevBox-Main  (permanent)\n  '+_h('puppet')+'  CI-Runner    expires 2026-04-07\n  '+_h('puppet')+'  Laptop       expires 2026-04-07'
        },
        admin: {
            '/admin invite <user>': _p('/admin invite new-tester')+'\n'+_o('Invitation sent to new-tester (push access).'),
            '/admin remove <user>': _p('/admin remove old-tester')+'\n'+_o('Removed old-tester from collaborators.'),
            '/admin pending': _p('/admin pending')+'\n'+_o('Pending invitations:')+'\n  new-tester    invited 2h ago\n  '+_d('No expired invitations.'),
            '/admin token <label>': _p('/admin token beta-tester-1')+'\n'+_o('Token generated for beta-tester-1:')+'\n  '+_d('forge_tk_a7f2c3d8e9b1...')+'\n'+_d('Share this token securely. It cannot be retrieved later.'),
            '/admin role <label> <role>': _p('/admin role beta-tester-1 admin')+'\n'+_o('Role updated: beta-tester-1 is now ')+_h('admin')
        },
        scan: {
            '/scan <path>': _p('/scan src/auth/')+'\n'+_o('Scanning codebase at src/auth/...'),
            '/scan force': _p('/scan force')+'\n'+_o('Scanning codebase at C:\\Users\\dev\\project (forced)...')
        },
        index: {
            '/index <path>': _p('/index src/')+'\n'+_o('Indexing src/...')+'\n  '+_d('+12 chunks: commands.py')+'\n  ...\n\n'+_o('Indexing complete:')+'\n  Files indexed:   '+_h('47')+'\n  Chunks created:  230',
            '/index --rebuild': _p('/index --rebuild')+'\n'+_o('Cleared index -- full rebuild...')+'\n'+_o('Indexing C:\\Users\\dev\\project...')
        },
        journal: {
            '/journal <N>': _p('/journal 3')+'\n'+_o('Episodic Memory (last 3 entries):')+'\n  '+_d('2026-03-07 14:23')+'  Edited forge/commands.py (3 tool calls)\n  '+_d('2026-03-07 10:11')+'  Fixed billing roundtrip bug\n  '+_d('2026-03-06 16:45')+'  Added /stress command'
        },
        digest: {
            '/digest <file>': _p('/digest forge/engine.py')+'\n  '+_d('(file-specific structural breakdown)')
        },
        stats: {
            '/stats reliability': _p('/stats reliability')+'\n'+_o('Reliability Metrics (30-session window)')+'\n  Composite:     87.3%\n  Verification:  92%\n  Continuity:    B+\n  Tool success:  98.4%'
        }
    };

    varEl.addEventListener('click', function(e) {
        var pill = e.target.closest('.cmd-var-pill');
        if (!pill) return;
        var vCmd = pill.getAttribute('data-var');
        var vt;
        if (vCmd === '__base__') {
            vt = currentBaseTerm;
        } else {
            vt = (VTERM[currentKey] && VTERM[currentKey][vCmd]) || (_p(vCmd) + '\n' + _d('(Run this in Forge to see full output)'));
        }
        termEl.innerHTML = vt;
        varEl.querySelectorAll('.cmd-var-pill').forEach(function(p) { p.classList.remove('active'); });
        pill.classList.add('active');
    });

    document.querySelectorAll('.cmd-row').forEach(function(row) {
        row.addEventListener('click', function() {
            openModal(this.getAttribute('data-cmd'));
        });
    });
})();

/* ══════════════ TABLE FILTER ══════════════ */
(function(){
    document.querySelectorAll('.filter-input').forEach(function(input) {
        var targetId = input.getAttribute('data-filter-target');
        var target = document.getElementById(targetId);
        if (!target) return;
        input.addEventListener('input', function() {
            var q = this.value.toLowerCase();
            var rows = target.querySelectorAll('tbody tr');
            rows.forEach(function(row) {
                if (row.classList.contains('cmd-cat-header')) {
                    row.style.display = q ? 'none' : '';
                    return;
                }
                var text = row.textContent.toLowerCase();
                row.style.display = text.indexOf(q) !== -1 ? '' : 'none';
            });
        });
    });
})();

/* ══════════════ COPY BUTTONS ══════════════ */
(function(){
    document.querySelectorAll('.copy-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var code = this.closest('.code-block').querySelector('code');
            if (!code) return;
            navigator.clipboard.writeText(code.textContent).then(function() {
                btn.textContent = 'Copied!';
                setTimeout(function(){ btn.textContent = 'Copy'; }, 2000);
            });
        });
    });
})();

/* ══════════════ SCROLL SPY ══════════════ */
(function(){
    var sidebar = document.querySelector('.docs-sidebar');
    if (!sidebar) return;
    var links = sidebar.querySelectorAll('a[href^="#"]');
    if (!links.length) return;
    var sections = [];
    links.forEach(function(link) {
        var id = link.getAttribute('href').slice(1);
        var el = document.getElementById(id);
        if (el) sections.push({el: el, link: link});
    });
    var ticking = false;
    function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(function() {
            var scrollY = window.scrollY + 120;
            var current = null;
            for (var i = 0; i < sections.length; i++) {
                if (sections[i].el.offsetTop <= scrollY) {
                    current = sections[i];
                }
            }
            links.forEach(function(l){ l.classList.remove('active'); });
            if (current) current.link.classList.add('active');
            ticking = false;
        });
    }
    window.addEventListener('scroll', onScroll, {passive: true});
    onScroll();
})();

/* ══════════════ SCROLL REVEAL ══════════════ */
(function(){
    var reveals = document.querySelectorAll('.reveal');
    if (!reveals.length) return;
    if (!('IntersectionObserver' in window)) {
        /* No IO support — just show everything */
        reveals.forEach(function(el) { el.classList.add('visible'); });
        return;
    }
    /* Signal CSS that we're handling reveals */
    document.documentElement.classList.add('reveal-ready');
    var io = new IntersectionObserver(function(entries) {
        entries.forEach(function(e) {
            if (e.isIntersecting) {
                e.target.classList.add('visible');
                io.unobserve(e.target);
            }
        });
    }, { threshold: 0.05, rootMargin: '0px 0px -40px 0px' });
    reveals.forEach(function(el) { io.observe(el); });
})();

/* ══════════════ NAV SCROLL ══════════════ */
(function(){
    var nav = document.getElementById('nav');
    if (!nav) return;
    window.addEventListener('scroll', function() {
        if (window.scrollY > 20) nav.classList.add('scrolled');
        else nav.classList.remove('scrolled');
    }, {passive: true});
})();

/* ══════════════ MOBILE NAV TOGGLE ══════════════ */
(function(){
    var toggle = document.getElementById('navToggle');
    var links = document.getElementById('navLinks');
    if (!toggle || !links) return;
    toggle.addEventListener('click', function() {
        links.classList.toggle('open');
    });
})();
</script>
</body>
</html>
