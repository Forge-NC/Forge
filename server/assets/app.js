/* ═══════════════════════════════════════════════════════════════════
   Forge — Shared JavaScript
   ═══════════════════════════════════════════════════════════════════ */

(function() {
    'use strict';

    /* ── Nav scroll shadow ── */
    var nav = document.querySelector('.nav');
    if (nav) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 10) {
                nav.classList.add('scrolled');
            } else {
                nav.classList.remove('scrolled');
            }
        });
    }

    /* ── Mobile hamburger ── */
    var hamburger = document.querySelector('.nav-hamburger');
    var navLinks = document.querySelector('.nav-links');
    if (hamburger && navLinks) {
        hamburger.addEventListener('click', function() {
            navLinks.classList.toggle('mobile-open');
            hamburger.innerHTML = navLinks.classList.contains('mobile-open') ? '&#10005;' : '&#9776;';
        });
        // Close on link click
        navLinks.querySelectorAll('a').forEach(function(link) {
            link.addEventListener('click', function() {
                navLinks.classList.remove('mobile-open');
                hamburger.innerHTML = '&#9776;';
            });
        });
    }

    /* ── Smooth scroll for anchor links ── */
    document.querySelectorAll('a[href^="#"]').forEach(function(anchor) {
        anchor.addEventListener('click', function(e) {
            var targetId = this.getAttribute('href');
            if (targetId === '#') return;
            var target = document.querySelector(targetId);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                history.pushState(null, null, targetId);
            }
        });
    });

    /* ── FAQ Accordion ── */
    document.querySelectorAll('.faq-q').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var item = this.closest('.faq-item');
            var wasOpen = item.classList.contains('open');
            // Close all
            document.querySelectorAll('.faq-item.open').forEach(function(el) {
                el.classList.remove('open');
            });
            // Toggle clicked
            if (!wasOpen) {
                item.classList.add('open');
            }
        });
    });

    /* ── Animated Counters ── */
    function animateCounter(el) {
        var target = parseInt(el.getAttribute('data-count'), 10);
        if (isNaN(target)) return;
        var suffix = el.getAttribute('data-suffix') || '';
        var prefix = el.getAttribute('data-prefix') || '';
        var duration = 1500;
        var start = 0;
        var startTime = null;

        function step(timestamp) {
            if (!startTime) startTime = timestamp;
            var progress = Math.min((timestamp - startTime) / duration, 1);
            var ease = 1 - Math.pow(1 - progress, 3); // easeOutCubic
            var current = Math.floor(start + (target - start) * ease);
            el.textContent = prefix + current.toLocaleString() + suffix;
            if (progress < 1) {
                requestAnimationFrame(step);
            } else {
                el.textContent = prefix + target.toLocaleString() + suffix;
            }
        }
        requestAnimationFrame(step);
    }

    var counterObserver = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting && !entry.target.classList.contains('counted')) {
                entry.target.classList.add('counted');
                animateCounter(entry.target);
            }
        });
    }, { threshold: 0.3 });

    document.querySelectorAll('[data-count]').forEach(function(el) {
        counterObserver.observe(el);
    });

    /* ── Scroll-triggered animations ── */
    var scrollObserver = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

    document.querySelectorAll('.animate-on-scroll').forEach(function(el) {
        scrollObserver.observe(el);
    });

    /* ── Code block copy buttons ── */
    document.querySelectorAll('.code-block .copy-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var code = this.closest('.code-block').querySelector('code');
            if (!code) return;
            var text = code.textContent || code.innerText;
            navigator.clipboard.writeText(text).then(function() {
                btn.textContent = 'Copied!';
                btn.classList.add('copied');
                setTimeout(function() {
                    btn.textContent = 'Copy';
                    btn.classList.remove('copied');
                }, 2000);
            });
        });
    });

    /* ── Tab switcher ── */
    document.querySelectorAll('.tabs').forEach(function(tabBar) {
        var tabs = tabBar.querySelectorAll('.tab');
        tabs.forEach(function(tab) {
            tab.addEventListener('click', function() {
                var target = this.getAttribute('data-tab');
                var container = tabBar.parentElement;
                // Deactivate all
                tabs.forEach(function(t) { t.classList.remove('active'); });
                container.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
                // Activate clicked
                this.classList.add('active');
                var panel = container.querySelector('[data-panel="' + target + '"]');
                if (panel) panel.classList.add('active');
            });
        });
    });

    /* ── Modal ── */
    window.openModal = function(id) {
        var overlay = document.getElementById(id);
        if (overlay) {
            overlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    };
    window.closeModal = function(id) {
        var overlay = document.getElementById(id);
        if (overlay) {
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        }
    };
    // Close modal on overlay click
    document.querySelectorAll('.modal-overlay').forEach(function(overlay) {
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) {
                overlay.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    });
    // Close modal on Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.active').forEach(function(overlay) {
                overlay.classList.remove('active');
            });
            document.body.style.overflow = '';
        }
    });

    /* ── Dropdown ── */
    document.querySelectorAll('.dropdown-toggle').forEach(function(toggle) {
        toggle.addEventListener('click', function(e) {
            e.stopPropagation();
            var dropdown = this.closest('.dropdown');
            var wasActive = dropdown.classList.contains('active');
            // Close all dropdowns
            document.querySelectorAll('.dropdown.active').forEach(function(d) {
                d.classList.remove('active');
            });
            if (!wasActive) dropdown.classList.add('active');
        });
    });
    document.addEventListener('click', function() {
        document.querySelectorAll('.dropdown.active').forEach(function(d) {
            d.classList.remove('active');
        });
    });

    /* ── Toast Notifications ── */
    window.showToast = function(message, type) {
        type = type || 'info';
        var container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        var toast = document.createElement('div');
        toast.className = 'toast toast-' + type;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(function() {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            toast.style.transition = 'all 0.3s';
            setTimeout(function() { toast.remove(); }, 300);
        }, 4000);
    };

    /* ── Fetch wrapper for admin AJAX ── */
    window.forgeAPI = function(url, options) {
        options = options || {};
        var method = options.method || 'GET';
        var body = options.body || null;
        var headers = { 'Content-Type': 'application/json' };

        // Get auth key from URL or cookie
        var params = new URLSearchParams(window.location.search);
        var key = params.get('key');
        if (key) {
            headers['X-Forge-Token'] = key;
        }

        var fetchOpts = { method: method, headers: headers };
        if (body && method !== 'GET') {
            fetchOpts.body = typeof body === 'string' ? body : JSON.stringify(body);
        }

        return fetch(url, fetchOpts)
            .then(function(res) {
                return res.json().then(function(data) {
                    if (!res.ok) {
                        throw new Error(data.error || 'Request failed');
                    }
                    return data;
                });
            })
            .catch(function(err) {
                showToast(err.message || 'Network error', 'error');
                throw err;
            });
    };

    /* ── Docs scroll spy ── */
    var sidebarLinks = document.querySelectorAll('.sidebar a[href^="#"]');
    if (sidebarLinks.length > 0) {
        var sections = [];
        sidebarLinks.forEach(function(link) {
            var id = link.getAttribute('href').slice(1);
            var section = document.getElementById(id);
            if (section) sections.push({ el: section, link: link });
        });

        function updateScrollSpy() {
            var scrollPos = window.scrollY + 100;
            var current = null;
            for (var i = sections.length - 1; i >= 0; i--) {
                if (sections[i].el.offsetTop <= scrollPos) {
                    current = sections[i];
                    break;
                }
            }
            sidebarLinks.forEach(function(l) { l.classList.remove('active'); });
            if (current) current.link.classList.add('active');
        }

        window.addEventListener('scroll', updateScrollSpy);
        updateScrollSpy();
    }

    /* ── Terminal typing animation ── */
    var terminalBody = document.querySelector('.terminal-body[data-demo]');
    if (terminalBody) {
        var demos = JSON.parse(terminalBody.getAttribute('data-demo'));
        var demoIndex = 0;
        var cursor = document.createElement('span');
        cursor.className = 'terminal-cursor';

        function scrollToBottom() {
            terminalBody.scrollTop = terminalBody.scrollHeight;
        }

        function extractText(html) {
            var tmp = document.createElement('span');
            tmp.innerHTML = html;
            return tmp.textContent || tmp.innerText || '';
        }

        function typeChars(container, html, cb) {
            // Type out the visible text char by char inside the styled HTML
            var plainText = extractText(html);
            container.innerHTML = '';
            container.appendChild(cursor);
            var charIdx = 0;

            function nextChar() {
                if (charIdx >= plainText.length) {
                    // Done typing — replace with full styled HTML
                    container.innerHTML = html;
                    cb();
                    return;
                }
                // Show partial plain text + cursor
                container.textContent = plainText.substring(0, charIdx + 1);
                container.appendChild(cursor);
                scrollToBottom();
                charIdx++;
                // Variable speed: faster on spaces/punctuation
                var ch = plainText[charIdx - 1];
                var delay = (ch === ' ' || ch === '/' || ch === '.') ? 25 : 40 + Math.random() * 30;
                setTimeout(nextChar, delay);
            }
            nextChar();
        }

        function typeDemo() {
            if (!demos || demos.length === 0) return;
            var demo = demos[demoIndex % demos.length];
            terminalBody.innerHTML = '';
            var lines = demo.split('\n');
            var lineIdx = 0;

            function processLine() {
                if (lineIdx >= lines.length) {
                    // Remove cursor, pause, then cycle
                    if (cursor.parentNode) cursor.parentNode.removeChild(cursor);
                    setTimeout(function() {
                        demoIndex++;
                        // Fade out
                        terminalBody.style.opacity = '0';
                        setTimeout(function() {
                            terminalBody.style.opacity = '1';
                            typeDemo();
                        }, 500);
                    }, 3500);
                    return;
                }

                var lineHtml = lines[lineIdx];
                lineIdx++;

                // Skip empty lines (just add spacing)
                if (!lineHtml.trim()) {
                    var spacer = document.createElement('div');
                    spacer.className = 't-line';
                    spacer.innerHTML = '&nbsp;';
                    terminalBody.appendChild(spacer);
                    scrollToBottom();
                    setTimeout(processLine, 80);
                    return;
                }

                var div = document.createElement('div');
                div.className = 't-line';
                terminalBody.appendChild(div);

                var isCommand = lineHtml.indexOf('class="prompt"') >= 0;

                if (isCommand) {
                    // Character-by-character typing for commands
                    // Brief pause before typing starts (like thinking)
                    div.appendChild(cursor);
                    scrollToBottom();
                    setTimeout(function() {
                        typeChars(div, lineHtml, function() {
                            scrollToBottom();
                            // Pause after command as if processing
                            setTimeout(processLine, 600);
                        });
                    }, 400);
                } else {
                    // Output lines — rapid reveal with slight stagger
                    div.style.opacity = '0';
                    div.innerHTML = lineHtml;
                    setTimeout(function() {
                        div.style.transition = 'opacity 0.15s';
                        div.style.opacity = '1';
                        scrollToBottom();
                    }, 20);
                    setTimeout(processLine, 120 + Math.random() * 80);
                }
            }
            processLine();
        }

        // Start when terminal scrolls into view
        var termObserver = new IntersectionObserver(function(entries) {
            if (entries[0].isIntersecting) {
                termObserver.disconnect();
                terminalBody.style.transition = 'opacity 0.4s';
                typeDemo();
            }
        }, { threshold: 0.3 });
        termObserver.observe(terminalBody.closest('.terminal') || terminalBody);
    }

    /* ── Theme Switcher ── */
    var EFFECT_THEMES = { cyberpunk: true, matrix: true, plasma: true };

    window.setTheme = function(slug) {
        // Remove any existing theme class
        var cl = document.body.className.replace(/theme-\S+/g, '').trim();
        document.body.className = cl + ' theme-' + slug;
        localStorage.setItem('forge-theme', slug);
        // Update active badge states
        document.querySelectorAll('.theme-badge').forEach(function(b) {
            b.classList.toggle('active', b.getAttribute('data-theme') === slug);
        });
        // Update accent glow color for cortex canvas wraps
        var accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
        document.querySelectorAll('.cortex-canvas-wrap').forEach(function(w) {
            w.style.boxShadow = '0 0 60px ' + accent + '26, 0 0 120px ' + accent + '0d';
        });
    };

    // Restore saved theme on page load
    var savedTheme = localStorage.getItem('forge-theme');
    if (savedTheme) window.setTheme(savedTheme);

    // Badge click delegation
    document.addEventListener('click', function(e) {
        var badge = e.target.closest('.theme-badge[data-theme]');
        if (badge) {
            window.setTheme(badge.getAttribute('data-theme'));
        }
    });

    /* ── Search/filter for tables ── */
    document.querySelectorAll('[data-filter-target]').forEach(function(input) {
        var targetId = input.getAttribute('data-filter-target');
        var table = document.getElementById(targetId);
        if (!table) return;

        input.addEventListener('input', function() {
            var query = this.value.toLowerCase();
            var rows = table.querySelectorAll('tbody tr');
            rows.forEach(function(row) {
                var text = row.textContent.toLowerCase();
                row.style.display = text.indexOf(query) >= 0 ? '' : 'none';
            });
        });
    });

})();
