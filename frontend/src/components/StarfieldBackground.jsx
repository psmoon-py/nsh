import React, { useEffect, useRef } from 'react';

export default function StarfieldBackground({ density = 160, speed = 0.015 }) {
  const ref = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let raf = 0;
    let w = 1;
    let h = 1;
    const stars = [];

    function resize() {
      w = canvas.width = window.innerWidth * Math.min(window.devicePixelRatio || 1, 2);
      h = canvas.height = window.innerHeight * Math.min(window.devicePixelRatio || 1, 2);
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      stars.length = 0;
      const count = Math.round((window.innerWidth * window.innerHeight) / 9000) + density;
      for (let i = 0; i < count; i++) {
        stars.push({
          x: Math.random() * w,
          y: Math.random() * h,
          r: Math.random() * 1.4 + 0.25,
          a: Math.random() * 0.55 + 0.15,
          v: Math.random() * 0.25 + 0.05,
        });
      }
    }

    function draw() {
      ctx.clearRect(0, 0, w, h);
      const grad = ctx.createRadialGradient(w * 0.55, h * 0.5, 0, w * 0.55, h * 0.5, Math.max(w, h) * 0.7);
      grad.addColorStop(0, 'rgba(7,12,20,0.35)');
      grad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);

      for (const s of stars) {
        s.y += s.v * speed * 10;
        if (s.y > h) s.y = -2;
        ctx.globalAlpha = s.a;
        ctx.fillStyle = '#d9e8ff';
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(draw);
    }

    resize();
    draw();
    window.addEventListener('resize', resize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
    };
  }, [density, speed]);

  return <canvas ref={ref} className="impacts-starfield" aria-hidden="true" />;
}
