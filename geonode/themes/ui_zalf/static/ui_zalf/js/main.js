(function () {
  'use strict';
  // --------------------------------------------------
  // ui_zalf main.js — GSAP-driven animation system
  // --------------------------------------------------
  // Dependencies: GSAP 3.x, ScrollTrigger (optional), Bootstrap 3 (for modals events)
  // No jQuery required. ES5 only.

  // Utilities
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function on(el, ev, fn, opts) { if (el) el.addEventListener(ev, fn, opts || false); }
  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  function debounce(fn, wait) {
    var t;
    return function () {
      var ctx = this, args = arguments;
      clearTimeout(t);
      t = setTimeout(function(){ fn.apply(ctx, args); }, wait);
    };
  }

  // Motion preferences
  var prefersReduced = false;
  try {
    prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) {}

  // Simple feature flags
  var hasGSAP = typeof window.gsap !== 'undefined';
  var hasST = hasGSAP && typeof window.ScrollTrigger !== 'undefined';

  // Public API (exposed on window for integration points)
  var UI = window.UI_ZALF = window.UI_ZALF || {};

  // -------------------------------
  // Core bootstrap
  // -------------------------------
  ready(function () {
    var body = document.body;
    var reduced = prefersReduced || body.classList.contains('reduce-motion') || body.classList.contains('no-anim');

    if (!hasGSAP) {
      console.warn('[ui_zalf] GSAP not found; animations disabled.');
      // Minimal fallbacks for visibility
      $$('.fade-up').forEach(function (el) {
        el.style.opacity = 1;
        el.style.transform = 'none';
      });
      // Counters: render immediate
      $$('.stat .num[data-count]').forEach(function (n) {
        var target = parseFloat(n.getAttribute('data-count')) || 0;
        n.textContent = Math.round(target).toLocaleString();
      });
      // Alerts: simple auto-dismiss
      autoDismissAlerts(true);
      // Dark toggle init
      initDarkMode();
      return;
    }

    // Register ScrollTrigger if present
    if (hasST) {
      window.gsap.registerPlugin(window.ScrollTrigger);
    }

    // INITIAL STATES (JS-only to avoid CLS)
    if (!reduced) {
      window.gsap.set('.fade-up', { autoAlpha: 0, y: 24 });
      window.gsap.set('.stagger-children > *', { autoAlpha: 0, y: 12 });
    } else {
      $$('.fade-up, .stagger-children > *').forEach(function (el) {
        el.style.opacity = 1;
        el.style.transform = 'none';
      });
    }

    // Init modules
    heroIntro(reduced);
    svgParallax(reduced);
    particlesFloat(reduced);
    revealOnScroll(reduced);
    counters(reduced);
    logoMarquee(reduced);
    cardHoverTilt(reduced);
    buttonRipple(reduced);
    tablesReveal(reduced);
    modalsAnimate(reduced);
    autoDismissAlerts(reduced);
    paginationPulse(reduced);
    formFocusStates();
    skeletonStopHelper();
    initDarkMode();

    // Expose manual API
    UI.refresh = function () {
      if (hasST) window.ScrollTrigger.refresh();
    };
  });

  // -------------------------------
  // Module: Hero intro timeline
  // -------------------------------
  function heroIntro(reduced) {
    if (reduced) return;
    var tl = window.gsap.timeline({ defaults: { ease: 'power2.out', duration: 0.7 } });
    if ($('.hero-eyebrow')) tl.from('.hero-eyebrow', { y: 12, autoAlpha: 0 });
    if ($('.zalf-hero-title')) tl.from('.zalf-hero-title', { y: 18, autoAlpha: 0 }, '-=0.4');
    if ($('.zalf-hero-sub')) tl.from('.zalf-hero-sub', { y: 16, autoAlpha: 0 }, '-=0.4');
    if ($('.zalf-searchbar')) tl.from('.zalf-searchbar', { y: 16, autoAlpha: 0 }, '-=0.35');
    if ($$('.hero-cta .btn').length) tl.from('.hero-cta .btn', { y: 12, autoAlpha: 0, stagger: 0.08 }, '-=0.35');
    if ($('.hero-svg')) tl.from('.hero-svg', { y: 20, autoAlpha: 0 }, '-=0.45');
  }

  // -------------------------------
  // Module: SVG parallax (subtle)
  // -------------------------------
  function svgParallax(reduced) {
    if (reduced || !hasST || !$('.hero-svg')) return;
    try {
      window.gsap.to('#ridge1', {
        yPercent: -6,
        ease: 'none',
        scrollTrigger: {
          trigger: '.hero',
          start: 'top top',
          end: 'bottom top',
          scrub: true
        }
      });
      window.gsap.to('#ridge2', {
        yPercent: -12,
        ease: 'none',
        scrollTrigger: {
          trigger: '.hero',
          start: 'top top',
          end: 'bottom top',
          scrub: true
        }
      });
    } catch (e) {
      // No-op if IDs are absent
    }

    // Centering helper on resize (kept simple)
    function centerHeroSvg() {
      var svg = $('.hero-svg');
      if (!svg) return;
      // Clear transforms possibly set from layout shifts
      window.gsap.set(svg, { clearProps: 'transform' });
    }
    centerHeroSvg();
    on(window, 'resize', debounce(centerHeroSvg, 250));
  }

  // -------------------------------
  // Module: Floating particles
  // -------------------------------
  function particlesFloat(reduced) {
    if (reduced) return;
    $$('.particle').forEach(function (p) {
      var dx = window.gsap.utils.random(-10, 10, 1, true);
      var dy = window.gsap.utils.random(-8, 8, 1, true);
      var d = window.gsap.utils.random(3, 6, 0.1, true);
      window.gsap.to(p, { x: dx, y: dy, duration: d, yoyo: true, repeat: -1, ease: 'sine.inOut' });
    });
  }

  // -------------------------------
  // Module: Reveal on scroll
  // -------------------------------
  function revealOnScroll(reduced) {
    if (reduced) return;
    if (hasST) {
      window.gsap.utils.toArray('.fade-up').forEach(function (el) {
        window.gsap.to(el, {
          y: 0,
          autoAlpha: 1,
          duration: 0.6,
          ease: 'power2.out',
          scrollTrigger: { trigger: el, start: 'top 80%', toggleActions: 'play none none reverse' }
        });
      });
      window.gsap.utils.toArray('.stagger-children').forEach(function (wrap) {
        window.gsap.to(wrap.children, {
          autoAlpha: 1,
          y: 0,
          stagger: 0.08,
          duration: 0.55,
          ease: 'power2.out',
          scrollTrigger: { trigger: wrap, start: 'top 85%', once: true }
        });
      });
    } else {
      // Fallback: immediate show
      $$('.fade-up, .stagger-children > *').forEach(function (el) {
        el.style.opacity = 1; el.style.transform = 'none';
      });
    }
  }

  // -------------------------------
  // Module: Animated counters
  // -------------------------------
  function counters(reduced) {
    var nodes = $$('.stat .num[data-count]');
    if (!nodes.length) return;
    if (reduced) {
      nodes.forEach(function (n) {
        var target = parseFloat(n.getAttribute('data-count')) || 0;
        n.textContent = Math.round(target).toLocaleString();
      });
      return;
    }
    nodes.forEach(function (n, index) {
      var target = parseFloat(n.getAttribute('data-count')) || 0;
      var obj = { v: 0 };
      var duration = window.gsap.utils.clamp(1.2, 3.0, target / 300);
      var tween = window.gsap.to(obj, {
        v: target, duration: duration, ease: 'expo.out', paused: true,
        onUpdate: function () { n.textContent = Math.round(obj.v).toLocaleString(); }
      });
      if (hasST) {
        window.ScrollTrigger.create({
          trigger: n, start: 'top 90%', once: true,
          onEnter: function () { window.gsap.delayedCall(index * 0.1, function(){ tween.play(); }); }
        });
      } else {
        window.gsap.delayedCall(index * 0.1, function(){ tween.play(); });
      }
    });
  }

  // -------------------------------
  // Module: Logo marquee
  // -------------------------------
  function logoMarquee(reduced) {
    if (reduced) return;
    var wrap = $('.logos-wrap');
    var track = wrap ? $('.logos', wrap) : null;
    if (!wrap || !track) return;

    // Duplicate children if not already duplicated
    if (!track.getAttribute('data-duplicated')) {
      var html = track.innerHTML;
      track.innerHTML = html + html;
      track.setAttribute('data-duplicated', '1');
    }

    var tl;
    function build() {
      if (tl) tl.kill();
      window.gsap.set(track, { x: 0 });
      var totalW = track.scrollWidth;
      var speed = 40; // px/s
      tl = window.gsap.to(track, { x: -totalW / 2, duration: (totalW / 2) / speed, ease: 'none', repeat: -1 });
    }
    build();
    on(window, 'resize', debounce(build, 200));
  }

  // -------------------------------
  // Module: Card hover tilt / lift
  // -------------------------------
  function cardHoverTilt(reduced) {
    var cards = $$('.gn-card, .dataset-card, .map-card, .document-card, .panel, .thumbnail');
    if (!cards.length) return;

    if (reduced) {
      cards.forEach(function (c) {
        on(c, 'mouseenter', function(){ c.style.transform = 'translateY(-2px)'; });
        on(c, 'mouseleave', function(){ c.style.transform = 'none'; });
      });
      return;
    }

    // Use quickSetter for performance
    cards.forEach(function (card) {
      var setTransform = window.gsap.quickSetter(card, 'transform');
      var bounds;
      function enter() {
        bounds = card.getBoundingClientRect();
        window.gsap.to(card, { duration: 0.25, boxShadow: '0 12px 30px rgba(0,0,0,.12)', y: -2 });
      }
      function move(e) {
        if (!bounds) bounds = card.getBoundingClientRect();
        var x = e.clientX - bounds.left;
        var y = e.clientY - bounds.top;
        var rx = ((y / bounds.height) - 0.5) * -6; // tilt X
        var ry = ((x / bounds.width) - 0.5) * 6;   // tilt Y
        setTransform('perspective(600px) rotateX(' + rx + 'deg) rotateY(' + ry + 'deg) translateY(-2px)');
      }
      function leave() {
        bounds = null;
        window.gsap.to(card, { duration: 0.3, rotateX: 0, rotateY: 0, y: 0, transform: 'perspective(600px)', boxShadow: 'var(--gn-shadow)' });
      }
      on(card, 'mouseenter', enter);
      on(card, 'mousemove', move);
      on(card, 'mouseleave', leave);
      on(card, 'touchstart', enter);
      on(card, 'touchend', leave);
    });
  }

  // -------------------------------
  // Module: Button ripple micro-interaction
  // -------------------------------
  function buttonRipple(reduced) {
    if (reduced) return;
    function addRipple(e) {
      var btn = e.currentTarget;
      var rect = btn.getBoundingClientRect();
      var size = Math.max(rect.width, rect.height);
      var x = (e.clientX || (e.touches && e.touches[0] && e.touches[0].clientX) || (rect.left + rect.width/2)) - rect.left - size / 2;
      var y = (e.clientY || (e.touches && e.touches[0] && e.touches[0].clientY) || (rect.top + rect.height/2)) - rect.top - size / 2;

      var ripple = document.createElement('span');
      ripple.className = 'btn-ripple';
      ripple.style.position = 'absolute';
      ripple.style.left = x + 'px';
      ripple.style.top = y + 'px';
      ripple.style.width = size + 'px';
      ripple.style.height = size + 'px';
      ripple.style.borderRadius = '50%';
      ripple.style.pointerEvents = 'none';
      ripple.style.background = 'rgba(255,255,255,.35)';
      ripple.style.transform = 'scale(0)';
      ripple.style.opacity = '0.9';
      ripple.style.mixBlendMode = 'overlay';
      ripple.style.willChange = 'transform, opacity';
      ripple.style.backfaceVisibility = 'hidden';
      ripple.style.webkitBackfaceVisibility = 'hidden';

      btn.style.position = btn.style.position || 'relative';
      btn.style.overflow = 'hidden';
      btn.appendChild(ripple);

      window.gsap.to(ripple, { duration: 0.45, scale: 1, ease: 'power2.out' });
      window.gsap.to(ripple, {
        duration: 0.45, opacity: 0, ease: 'power2.out', delay: 0.15,
        onComplete: function () { if (ripple && ripple.parentNode) ripple.parentNode.removeChild(ripple); }
      });
    }
    $$('.btn').forEach(function (b) {
      on(b, 'click', addRipple);
      on(b, 'touchstart', addRipple);
    });
  }

  // -------------------------------
  // Module: Tables reveal (stagger rows)
  // -------------------------------
  function tablesReveal(reduced) {
    if (reduced || !hasST) return;
    window.gsap.utils.toArray('table.table').forEach(function (tbl) {
      var rows = $$('tbody tr', tbl);
      if (!rows.length) return;
      window.gsap.from(rows, {
        y: 10, autoAlpha: 0, stagger: 0.04, duration: 0.35, ease: 'power1.out',
        scrollTrigger: { trigger: tbl, start: 'top 85%', once: true }
      });
    });
  }

  // -------------------------------
  // Module: Modals open/close animations
  // -------------------------------
  function modalsAnimate(reduced) {
    if (reduced) return;
    // Bootstrap 3 events: show.bs.modal / hidden.bs.modal
    $$('.modal').forEach(function (modal) {
      on(modal, 'show.bs.modal', function () {
        var dlg = $('.modal-dialog', modal);
        if (!dlg) return;
        window.gsap.set(dlg, { y: 16, autoAlpha: 0 });
        window.gsap.to(dlg, { duration: 0.35, y: 0, autoAlpha: 1, ease: 'power2.out' });
      });
      on(modal, 'hidden.bs.modal', function () {
        // Clean transforms
        var dlg = $('.modal-dialog', modal);
        if (dlg) window.gsap.set(dlg, { clearProps: 'all' });
      });
    });
  }

  // -------------------------------
  // Module: Alerts auto-dismiss (fade out)
  // -------------------------------
  function autoDismissAlerts(noAnim) {
    var alerts = $$('.alert.auto-dismiss, .alert[data-autohide="true"], .alert[data-timeout]');
    alerts.forEach(function (al) {
      var t = parseInt(al.getAttribute('data-timeout'), 10);
      if (isNaN(t)) t = 5000;
      setTimeout(function () {
        if (noAnim || !hasGSAP) {
          al.parentNode && al.parentNode.removeChild(al);
        } else {
          window.gsap.to(al, {
            duration: 0.35, y: -10, autoAlpha: 0, ease: 'power1.out',
            onComplete: function () { al.parentNode && al.parentNode.removeChild(al); }
          });
        }
      }, t);
    });
  }

  // -------------------------------
  // Module: Pagination pulse
  // -------------------------------
  function paginationPulse(reduced) {
    var active = $('.pagination li.active a, .pagination li.active span');
    if (!active) return;
    if (reduced) return;
    window.gsap.fromTo(active, { scale: 0.96 }, { duration: 0.35, scale: 1, ease: 'back.out(2)' });
  }

  // -------------------------------
  // Module: Form focus (floating label support)
  // -------------------------------
  function formFocusStates() {
    $$('.form-group .form-control').forEach(function (el) {
      var group = el.closest ? el.closest('.form-group') : null;
      if (!group) return;
      on(el, 'focus', function(){ group.classList.add('is-focused'); });
      on(el, 'blur', function(){ group.classList.remove('is-focused'); });
      // Pre-filled state
      if (el.value) group.classList.add('is-filled');
      on(el, 'input', function(){ if (el.value) group.classList.add('is-filled'); else group.classList.remove('is-filled'); });
    });
  }

  // -------------------------------
  // Module: Skeleton stop helper
  // -------------------------------
  function skeletonStopHelper() {
    // Users can call UI_ZALF.stopSkeletons(container) after data load
    UI_ZALF.stopSkeletons = function (root) {
      var nodes = $$('.skeleton', root);
      nodes.forEach(function (n) { n.classList.remove('skeleton'); });
    };
  }

  // -------------------------------
  // Module: Dark mode toggle (optional)
  // -------------------------------
  function initDarkMode() {
    var storageKey = 'ui_zalf_theme';
    try {
      var saved = localStorage.getItem(storageKey);
      if (saved === 'dark') document.documentElement.classList.add('dark');
    } catch (e) {}
    var toggles = $$('.js-dark-toggle');
    toggles.forEach(function (btn) {
      on(btn, 'click', function () {
        var root = document.documentElement;
        var isDark = root.classList.toggle('dark');
        try { localStorage.setItem(storageKey, isDark ? 'dark' : 'light'); } catch (e) {}
      });
    });
  }

  // --------------------------------------------------
  // End of file
  // --------------------------------------------------
})();