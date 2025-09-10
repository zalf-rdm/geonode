// geonode/themes/ui_zalf/static/ui_zalf/js/main.js
(function () {
  console.log('[ui_zalf] main.js loaded');
  var docEl = document.documentElement;

  // Se esqueceram de setar 'has-anim' no HTML e também não está em 'no-anim', força 'has-anim' (FOUC mínimo)
  if (!docEl.classList.contains('has-anim') && !docEl.classList.contains('no-anim')) {
    docEl.classList.add('has-anim');
  }

  var prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function $(sel, root) { return (root || document).querySelector(sel); }

  function revealFallback() {
    // Mostra tudo e desativa animações
    docEl.classList.remove('has-anim');
    docEl.classList.add('no-anim');
    $all('.fade-up').forEach(function (el) {
      el.style.opacity = 1;
      el.style.transform = 'none';
    });
  }

  function initAnimations() {
    var reduced = prefersReduced || docEl.classList.contains('no-anim');

    if (reduced) {
      revealFallback();
      bindToggle(); // ainda habilita o botão para reativar
      return;
    }

    if (!window.gsap) {
      console.warn('[ui_zalf] GSAP not found; fallback.');
      revealFallback();
      bindToggle();
      return;
    }

    // ---------- Setup GSAP ----------
    gsap.registerPlugin(window.ScrollTrigger || {});

    // Estado inicial dos elementos que revelam no scroll
    if (docEl.classList.contains('has-anim')) {
      gsap.set('.fade-up', { autoAlpha: 0, y: 24 });
    } else {
      // visível se por acaso não estiver com has-anim
      $all('.fade-up').forEach(function (el) { el.style.opacity = 1; el.style.transform = 'none'; });
    }

    // ---------- Hero intro ----------
    var heroTl = gsap.timeline({ defaults: { ease: 'power2.out', duration: 0.7 } });
    heroTl
      .from('.hero-eyebrow', { y: 12, autoAlpha: 0 })
      .from('.zalf-hero-title', { y: 18, autoAlpha: 0 }, '-=0.4')
      .from('.zalf-hero-sub', { y: 16, autoAlpha: 0 }, '-=0.4')
      .from('.zalf-searchbar', { y: 16, autoAlpha: 0 }, '-=0.35')
      .from('.hero-cta .btn', { y: 12, autoAlpha: 0, stagger: 0.08 }, '-=0.35')
      .from('.hero-svg', { y: 20, autoAlpha: 0 }, '-=0.45');

    // ---------- Floating particles ----------
    $all('.particle').forEach(function (p) {
      var dx = gsap.utils.random(-10, 10, 1, true);
      var dy = gsap.utils.random(-8, 8, 1, true);
      var d = gsap.utils.random(3, 6, 0.1, true);
      gsap.to(p, { x: dx, y: dy, duration: d, yoyo: true, repeat: -1, ease: 'sine.inOut' });
    });

    // ---------- Scroll reveals ----------
    if (window.ScrollTrigger) {
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
    } else {
      // Sem ScrollTrigger, revela direto
      $all('.fade-up').forEach(function (el) {
        gsap.to(el, { y: 0, autoAlpha: 1, duration: 0.6, ease: 'power2.out' });
      });
    }

    // ---------- Stats counters ----------
    var nums = $all('.stat .num[data-count]');
    if (nums.length) {
      nums.forEach(function (node) {
        var target = parseFloat(node.getAttribute('data-count')) || 0;
        var obj = { val: 0 };
        var fmt = function (v) { return (v >= 1000) ? Math.round(v).toLocaleString() : Math.round(v); };
        var counterTween = gsap.to(obj, {
          val: target,
          paused: true,
          duration: gsap.utils.clamp(0.8, 1.8, target / 500),
          ease: 'power1.out',
          onUpdate: function () { node.textContent = fmt(obj.val); }
        });

        if (window.ScrollTrigger) {
          ScrollTrigger.create({
            trigger: node,
            start: 'top 90%',
            once: true,
            onEnter: function () { counterTween.play(); }
          });
        } else {
          counterTween.play();
        }
      });
    }

    // ---------- Logos marquee ----------
    (function marquee() {
      var wrap = $('.logos-wrap');
      var track = $('.logos', wrap);
      if (!wrap || !track) return;

      var totalW = track.scrollWidth; // largura do conteúdo (já duplicado no HTML)
      var speed = 40; // px/s

      gsap.set(track, { x: 0 });
      gsap.to(track, {
        x: -totalW / 2,
        duration: (totalW / 2) / speed,
        ease: 'none',
        repeat: -1,
        modifiers: {
          x: function (x) {
            var nx = parseFloat(x);
            if (Math.abs(nx) >= totalW / 2) nx = 0;
            return nx + 'px';
          }
        }
      });
    })();

    bindToggle();
  }

  function bindToggle() {
    var toggle = $('#toggle-anim');
    if (!toggle || toggle.__bound) return;
    toggle.__bound = true;

    toggle.addEventListener('click', function () {
      var disabled = docEl.classList.contains('no-anim');

      if (disabled) {
        // Re-ativar animações
        docEl.classList.remove('no-anim');
        docEl.classList.add('has-anim');
        toggle.setAttribute('aria-pressed', 'false');
        toggle.textContent = 'Skip Animation';
        // reinicializa animações
        initAnimations();
      } else {
        // Desligar animações
        if (window.ScrollTrigger) ScrollTrigger.getAll().forEach(function (st) { st.kill(); });
        if (window.gsap) gsap.globalTimeline.clear();
        revealFallback();
        toggle.setAttribute('aria-pressed', 'true');
        toggle.textContent = 'Enable Animation';
      }
    });
  }

  // Inicialização
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAnimations);
  } else {
    initAnimations();
  }

  // Segurança: se GSAP não carregar em até 2s e estamos com has-anim, faz fallback
  setTimeout(function () {
    if (docEl.classList.contains('has-anim') && typeof window.gsap === 'undefined') {
      console.warn('[ui_zalf] GSAP did not load. Falling back.');
      revealFallback();
    }
  }, 2000);
})();
