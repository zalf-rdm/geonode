// geonode/themes/ui_zalf/static/ui_zalf/js/main.js
(function () {
  // Debug visível no console
  console.log('[ui_zalf] main.js loaded');

  // Preferência de acessibilidade
  var prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function $(sel, root) { return (root || document).querySelector(sel); }

  function initAnimations() {
    if (!window.gsap) {
      console.warn('[ui_zalf] GSAP not found; skipping animations.');
      return;
    }
    gsap.registerPlugin(window.ScrollTrigger || {});

    var reduced = prefersReduced || document.documentElement.classList.contains('no-anim');

    // ---------- Base states ----------
    // Fade-up initial state
    if (!reduced) {
      gsap.set('.fade-up', { autoAlpha: 0, y: 24 });
    } else {
      $all('.fade-up').forEach(function (el) { el.style.opacity = 1; el.style.transform = 'none'; });
    }

    // ---------- Hero intro ----------
    if (!reduced) {
      var heroTl = gsap.timeline({ defaults: { ease: 'power2.out', duration: 0.7 } });
      heroTl
        .from('.hero-eyebrow', { y: 12, autoAlpha: 0 })
        .from('.zalf-hero-title', { y: 18, autoAlpha: 0 }, '-=0.4')
        .from('.zalf-hero-sub', { y: 16, autoAlpha: 0 }, '-=0.4')
        .from('.zalf-searchbar', { y: 16, autoAlpha: 0 }, '-=0.35')
        .from('.hero-cta .btn', { y: 12, autoAlpha: 0, stagger: 0.08 }, '-=0.35')
        .from('.hero-svg', { y: 20, autoAlpha: 0 }, '-=0.45');
    }

    // ---------- Floating particles ----------
    if (!reduced) {
      $all('.particle').forEach(function (p) {
        var dx = gsap.utils.random(-10, 10, 1, true);
        var dy = gsap.utils.random(-8, 8, 1, true);
        var d = gsap.utils.random(3, 6, 0.1, true);
        gsap.to(p, { x: dx, y: dy, duration: d, yoyo: true, repeat: -1, ease: 'sine.inOut' });
      });
    }

    // ---------- Scroll reveals ----------
    if (!reduced && window.ScrollTrigger) {
      gsap.utils.toArray('.fade-up').forEach(function (el) {
        gsap.to(el, {
          y: 0,
          autoAlpha: 1,
          duration: 0.6,
          ease: 'power2.out',
          scrollTrigger: {
            trigger: el,
            start: 'top 80%',
            toggleActions: 'play none none reverse'
          }
        });
      });
    }

    // ---------- Stats counters ----------
    var nums = $all('.stat .num[data-count]');
    if (!reduced && nums.length) {
      nums.forEach(function (node, i) {
        var target = parseFloat(node.getAttribute('data-count')) || 0;
        var obj = { val: 0 };
        // Formata números grandes
        var fmt = function (v) { return (v >= 1000) ? Math.round(v).toLocaleString() : Math.round(v); };
        var tween = gsap.to(obj, {
          val: target,
          duration: gsap.utils.clamp(0.8, 1.8, target / 500),
          ease: 'power1.out',
          onUpdate: function () { node.textContent = fmt(obj.val); }
        });
        if (window.ScrollTrigger) {
          window.ScrollTrigger.create({
            trigger: node,
            start: 'top 90%',
            onEnter: function () { tween.play(); },
            once: true
          });
        } else {
          tween.play();
        }
      });
    } else {
      // Sem animação: mostrar valores direto
      nums.forEach(function (node) { node.textContent = node.getAttribute('data-count'); });
    }

    // ---------- Logos marquee ----------
    (function marquee() {
      var wrap = $('.logos-wrap');
      var track = $('.logos', wrap);
      if (!wrap || !track) return;

      // mede largura do conteúdo
      var totalW = track.scrollWidth;
      // velocidade base (px/s)
      var speed = 40;
      if (reduced) return; // sem animação

      // anima de x:0 até -metade da largura (pois você já duplicou os items no HTML)
      gsap.set(track, { x: 0 });
      gsap.to(track, {
        x: -totalW / 2,
        duration: (totalW / 2) / speed,
        ease: 'none',
        repeat: -1,
        modifiers: {
          x: function (x) {
            var nx = parseFloat(x);
            if (Math.abs(nx) >= totalW / 2) {
              // reseta para loop perfeito
              nx = 0;
            }
            return nx + 'px';
          }
        }
      });
    })();

    // ---------- Skip animation toggle ----------
    var toggle = $('#toggle-anim');
    if (toggle) {
      toggle.addEventListener('click', function () {
        var active = !document.documentElement.classList.contains('no-anim');
        if (active) {
          document.documentElement.classList.add('no-anim');
          if (window.ScrollTrigger) ScrollTrigger.getAll().forEach(function (st) { st.kill(); });
          gsap.globalTimeline.clear();
          // Garante conteúdo visível
          $all('.fade-up').forEach(function (el) { el.style.opacity = 1; el.style.transform = 'none'; });
          toggle.setAttribute('aria-pressed', 'true');
          toggle.textContent = 'Enable Animation';
        } else {
          document.documentElement.classList.remove('no-anim');
          toggle.setAttribute('aria-pressed', 'false');
          toggle.textContent = 'Skip Animation'
