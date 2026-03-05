/**
 * Forge Site Analytics — Lightweight Client Tracker
 * No cookies. No fingerprinting. localStorage visitor ID only.
 * ~80 lines. Sends events via sendBeacon to track.php.
 */
(function() {
    'use strict';

    var ENDPOINT = '/Forge/track.php';
    var vid = null;

    // ── Visitor ID (random, localStorage only) ──
    try {
        vid = localStorage.getItem('forge_vid');
        if (!vid) {
            vid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                var r = Math.random() * 16 | 0;
                return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
            });
            localStorage.setItem('forge_vid', vid);
        }
    } catch(e) { vid = 'anon'; }

    // ── Send event ──
    function send(data) {
        data.vid = vid;
        data.url = location.pathname + location.search;
        data.ref = document.referrer || null;
        data.vw = window.innerWidth;
        data.sw = screen.width;
        data.sh = screen.height;
        var json = JSON.stringify(data);
        if (navigator.sendBeacon) {
            navigator.sendBeacon(ENDPOINT, new Blob([json], {type: 'application/json'}));
        } else {
            var x = new XMLHttpRequest();
            x.open('POST', ENDPOINT, true);
            x.setRequestHeader('Content-Type', 'application/json');
            x.send(json);
        }
    }

    // ── UTM extraction ──
    function getUTM() {
        var params = {};
        try {
            var sp = new URLSearchParams(location.search);
            ['utm_source','utm_medium','utm_campaign','utm_content','utm_term'].forEach(function(k) {
                var v = sp.get(k);
                if (v) params[k] = v;
            });
        } catch(e) {}
        return params;
    }

    // ── Pageview ──
    var pvData = {event: 'pageview'};
    var utm = getUTM();
    for (var k in utm) pvData[k] = utm[k];
    send(pvData);

    // ── CTA click tracking ──
    document.addEventListener('click', function(e) {
        var el = e.target.closest('a, button');
        if (!el) return;

        var href = el.getAttribute('href') || '';
        var text = (el.textContent || '').trim().substring(0, 200);

        // Match checkout links, pricing anchors, doc install links, CTA buttons
        var isCheckout = href.indexOf('checkout') !== -1;
        var isPricing = href.indexOf('#pricing') !== -1;
        var isDocs = href.indexOf('docs.php') !== -1 && href.indexOf('#install') !== -1;
        var isCTA = el.classList.contains('btn-primary') || el.classList.contains('btn-secondary');
        var inCTAZone = !!el.closest('.hero-buttons, .persona-cta, .price-card, .cta-banner, .cta-section');

        if (isCheckout || isPricing || isDocs || (isCTA && inCTAZone)) {
            var data = {event: 'cta_click', btn_text: text, btn_href: href};

            // Extract tier from href
            var tierMatch = href.match(/[?&]tier=([^&]+)/);
            if (tierMatch) data.tier = tierMatch[1];

            // Extract billing from href
            var billMatch = href.match(/[?&]billing=([^&]+)/);
            if (billMatch) data.billing = billMatch[1];

            // Section context
            var section = el.closest('section, [id]');
            if (section && section.id) data.section = section.id;
            else if (section && section.className) data.section = section.className.split(' ')[0];

            send(data);
        }
    }, true);

    // ── Waitlist form tracking ──
    document.addEventListener('submit', function(e) {
        var form = e.target;
        if (form.classList.contains('waitlist-form') || form.querySelector('[name="waitlist_email"]')) {
            var data = {event: 'waitlist'};
            var tierInput = form.querySelector('[name="tier"]');
            if (tierInput && tierInput.value) data.tier = tierInput.value;
            send(data);
        }
    }, true);

    // ── Scroll depth + time on page ──
    var maxScroll = 0;
    var pageStart = Date.now();

    function updateScroll() {
        var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        var docHeight = Math.max(
            document.body.scrollHeight, document.documentElement.scrollHeight,
            document.body.offsetHeight, document.documentElement.offsetHeight
        );
        var winHeight = window.innerHeight;
        var pct = docHeight > winHeight ? Math.round((scrollTop + winHeight) / docHeight * 100) : 100;
        if (pct > maxScroll) maxScroll = pct;
    }

    window.addEventListener('scroll', updateScroll, {passive: true});
    updateScroll();

    // Send scroll depth on page unload
    function sendScrollDepth() {
        var elapsed = Math.round((Date.now() - pageStart) / 1000);
        send({event: 'scroll_depth', max_scroll: Math.min(maxScroll, 100), time_on_page: elapsed});
    }

    // Use pagehide (preferred) or beforeunload as fallback
    window.addEventListener('pagehide', sendScrollDepth);
    window.addEventListener('beforeunload', sendScrollDepth);
})();
