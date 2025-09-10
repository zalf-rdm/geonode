// geonode/themes/ui_zalf/static/ui_zalf/js/main.js
(function () {
  'use strict';
  console.log('[ui_zalf] main.js loaded');

  var prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }

  ready(function () {
    var gsap = window.gsap;
    var ST = window.ScrollTrigger;

    if (!gsap) {
      console.warn('[ui_zalf] GSAP not found; skipping animations.');
      return;
    }
    if (ST) gsap.registerPlugin(ST);

    var reduced = prefersReduced || document.documentElement.classList.contains('no-anim');

    // ---------- ESTADOS INICIAIS (sem CSS)
    if (!reduced) {
      gsap.set('.fade-up', { autoAlpha: 0, y: 24 });
    } else {
      $$('.fade-up').forEach(function (el) { el.style.opacity = 1; el.style.transform = 'none'; });
    }

    // ---------- HERO INTRO
    if (!reduced) {
      var tl = gsap.timeline({ defaults: { ease: 'power2.out', duration: 0.7 } });
      tl.from('.hero-eyebrow', { y: 12, autoAlpha: 0 })
        .from('.zalf-hero-title', { y: 18, autoAlpha: 0 }, '-=0.4')
        .from('.zalf-hero-sub', { y: 16, autoAlpha: 0 }, '-=0.4')
        .from('.zalf-searchbar', { y: 16, autoAlpha: 0 }, '-=0.35')
        .from('.hero-cta .btn', { y: 12, autoAlpha: 0, stagger: 0.08 }, '-=0.35')
        .from('.hero-svg', { y: 20, autoAlpha: 0 }, '-=0.45');
    }

    // ---------- PARALLAX SUAVE DAS CRISTAS DO SVG AO ROLAR
    if (!reduced && ST && $('.hero-svg')) {
      gsap.to('#ridge1', {
        yPercent: -6,
        ease: 'none',
        scrollTrigger: {
          trigger: '.hero',
          start: 'top top',
          end: 'bottom top',
          scrub: true
        }
      });
      gsap.to('#ridge2', {
        yPercent: -12,
        ease: 'none',
        scrollTrigger: {
          trigger: '.hero',
          start: 'top top',
          end: 'bottom top',
          scrub: true
        }
      });
    }

    // ---------- PARTÍCULAS FLUTUANDO
    if (!reduced) {
      $$('.particle').forEach(function (p) {
        var dx = gsap.utils.random(-10, 10, 1, true);
        var dy = gsap.utils.random(-8, 8, 1, true);
        var d = gsap.utils.random(3, 6, 0.1, true);
        gsap.to(p, { x: dx, y: dy, duration: d, yoyo: true, repeat: -1, ease: 'sine.inOut' });
      });
    }

    // ---------- REVEAL ON SCROLL
    if (!reduced && ST) {
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

    // ---------- CONTADORES DAS STATS
    (function statsCounters() {
  // Select all counter elements
  var nodes = $$('.stat .num[data-count]');
  if (!nodes.length) return;

  // Fallback for reduced motion preference
  if (reduced) {
    nodes.forEach(function (n) {
      n.textContent = (+n.getAttribute('data-count') || 0).toLocaleString();
    });
    return;
  }

  // Animate each counter with smooth interpolation
  nodes.forEach(function (n, index) {
    // Parse target number from data attribute
    var target = parseFloat(n.getAttribute('data-count')) || 0;

    // Animation object — keep value as float for smooth interpolation
    var obj = { v: 0 };

    // Format function: round ONLY for display, never during animation
    var fmt = function (x) {
      var rounded = Math.round(x);
      return rounded.toLocaleString(); // Add commas for thousands
    };

    // Dynamic duration: longer for larger numbers (min 1.2s, max 3.0s)
    var duration = gsap.utils.clamp(1.2, 3.0, target / 300);

    // Use 'expo.out' for natural easing — starts fast, ends smooth (perfect for counters)
    var ease = 'expo.out';

    // Create GSAP tween
    var tween = gsap.to(obj, {
      v: target,
      duration: duration,
      ease: ease,
      paused: true,
      onUpdate: function () {
        // Update DOM text — format only here to preserve animation smoothness
        n.textContent = fmt(obj.v);
      }
    });

    // Trigger animation on scroll (if ScrollTrigger is available)
    if (ST) {
      ST.create({
        trigger: n,
        start: 'top 90%',
        onEnter: function () {
          // Optional: staggered delay for sequential animation (0.1s per item)
          gsap.delayedCall(index * 0.1, function () {
            tween.play();
          });
        },
        once: true // Animate only once
      });
    } else {
      // Fallback: animate immediately with staggered delay
      gsap.delayedCall(index * 0.1, function () {
        tween.play();
      });
    }
  });
})();

    // ---------- MARQUEE DOS LOGOS
    (function marquee() {
      var wrap = $('.logos-wrap');
      var track = $('.logos', wrap);
      if (!wrap || !track) return;
      if (reduced) return;

      var tl;
      function build() {
        if (tl) tl.kill();
        gsap.set(track, { x: 0 });
        // largura total do conteúdo
        var totalW = track.scrollWidth;
        var speed = 40; // px/s
        // anima de 0 até -metade (HTML já tem itens duplicados)
        tl = gsap.to(track, {
          x: -totalW / 2,
          duration: (totalW / 2) / speed,
          ease: 'linear',
          repeat: -1
        });
      }

      build();
      // Recalcula em resize debounced
      var to;
      window.addEventListener('resize', function () {
        clearTimeout(to);
        to = setTimeout(build, 200);
      });
    })();

    
  });

  let resizeTimer;

function centerHeroSvg() {
    const svg = document.querySelector('.hero-svg');
    if (!svg) return;

    const vw = window.innerWidth;

    gsap.set(svg, { clearProps: "transform" }); 
}

// Executa ao carregar
centerHeroSvg();

// Executa ao redimensionar
window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        centerHeroSvg();
    }, 250);
});
})();


