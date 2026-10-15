/**
 * three-bg.js — Eva 3D Arka Plan (Faz 9)
 * =========================================
 * Three.js kullanarak GPU'da render edilen parçacık ağı.
 * CPU animasyonları gibi sayfayı yavaşlatmaz — tamamen GPU'da çalışır.
 *
 * Özellikler:
 *  - 3000 parçacık, birbirine çizgilerle bağlı (particle network)
 *  - Mouse hareketi → hafif parallax (derinlik hissi)
 *  - evaThink() / evaTalk() → parçacıklar hızlanır / parlar
 */

(function () {
  'use strict';

  // Three.js yüklenene kadar bekle
  function waitForThree(cb) {
    if (typeof THREE !== 'undefined') { cb(); return; }
    const t = setInterval(() => {
      if (typeof THREE !== 'undefined') { clearInterval(t); cb(); }
    }, 100);
  }

  waitForThree(() => {
    // ── Sahne kurulumu ────────────────────────────────────────────
    const scene    = new THREE.Scene();
    const camera   = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.1, 1000);
    camera.position.z = 80;

    const renderer = new THREE.WebGLRenderer({ canvas: document.getElementById('three-canvas'), alpha: true, antialias: false });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); // Mobilde pil tasarrufu
    renderer.setSize(innerWidth, innerHeight);
    renderer.setClearColor(0x000000, 0); // Şeffaf arka plan

    // ── Parçacık geometrisi ───────────────────────────────────────
    const PARTICLE_COUNT = 2000;
    const positions = new Float32Array(PARTICLE_COUNT * 3);
    const velocities = [];

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      positions[i * 3]     = (Math.random() - 0.5) * 200;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 120;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 60;
      velocities.push({
        x: (Math.random() - 0.5) * 0.04,
        y: (Math.random() - 0.5) * 0.04,
        z: (Math.random() - 0.5) * 0.02,
      });
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const material = new THREE.PointsMaterial({
      color: 0x0ea5e9,  // Eva'nın turkuaz rengi
      size: 0.35,
      transparent: true,
      opacity: 0.7,
      sizeAttenuation: true,
    });

    const particles = new THREE.Points(geometry, material);
    scene.add(particles);

    // ── Bağlantı çizgileri (Lines) ────────────────────────────────
    // Yakın parçacıkları birbirine bağlar — WebGL Lines ile GPU'da
    const lineGeo  = new THREE.BufferGeometry();
    const maxLines = 6000;
    const linePos  = new Float32Array(maxLines * 6); // her çizgi 2 nokta
    lineGeo.setAttribute('position', new THREE.BufferAttribute(linePos, 3));
    lineGeo.setDrawRange(0, 0);

    const lineMat = new THREE.LineSegments(lineGeo, new THREE.LineBasicMaterial({
      color: 0x0284c7,
      transparent: true,
      opacity: 0.18,
    }));
    scene.add(lineMat);

    // ── Mouse parallax ────────────────────────────────────────────
    let mouseX = 0, mouseY = 0;
    let targetX = 0, targetY = 0;

    document.addEventListener('mousemove', (e) => {
      mouseX = (e.clientX / innerWidth - 0.5) * 2;
      mouseY = (e.clientY / innerHeight - 0.5) * 2;
    });

    // ── Durum değişkenleri (Eva konuşurken hızlan) ─────────────
    let energyMultiplier = 1.0;  // 1 = normal, 3 = Eva düşünüyor, 5 = konuşuyor
    let targetEnergy     = 1.0;

    window.evaThink  = () => { targetEnergy = 3.0; };  // Eva düşünüyor
    window.evaTalk   = () => { targetEnergy = 5.0; };  // Eva konuşuyor
    window.evaIdle   = () => { targetEnergy = 1.0; };  // Bekleme

    // ── Resize handler ─────────────────────────────────────────
    window.addEventListener('resize', () => {
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
    });

    // ── Animasyon döngüsü ─────────────────────────────────────
    const clock = new THREE.Clock();

    function animate() {
      requestAnimationFrame(animate);
      const t = clock.getElapsedTime();

      // Enerji yumuşak geçiş
      energyMultiplier += (targetEnergy - energyMultiplier) * 0.03;

      // Mouse parallax
      targetX += (mouseX * 8 - targetX) * 0.05;
      targetY += (mouseY * 4 - targetY) * 0.05;
      scene.rotation.y = targetX * 0.015;
      scene.rotation.x = targetY * 0.01;

      // Parçacıkları hareket ettir
      const pos = geometry.attributes.position.array;
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        const v = velocities[i];
        pos[i * 3]     += v.x * energyMultiplier;
        pos[i * 3 + 1] += v.y * energyMultiplier;
        pos[i * 3 + 2] += v.z * energyMultiplier;

        // Sınır kontrolü — çıkarsa karşı taraftan gir
        if (Math.abs(pos[i * 3])     > 100) pos[i * 3]     *= -0.95;
        if (Math.abs(pos[i * 3 + 1]) >  60) pos[i * 3 + 1] *= -0.95;
        if (Math.abs(pos[i * 3 + 2]) >  30) pos[i * 3 + 2] *= -0.95;
      }
      geometry.attributes.position.needsUpdate = true;

      // Çizgi güncellemesi (her 2 karede bir — performans optimizasyonu)
      if (Math.floor(t * 30) % 2 === 0) {
        updateLines(pos);
      }

      // Renk pulse — Eva konuşurken parlar
      const pulse = 0.5 + 0.5 * Math.sin(t * (2 + energyMultiplier));
      material.opacity = 0.5 + 0.25 * pulse * (energyMultiplier / 5);
      material.color.setHSL(0.55, 0.9, 0.45 + 0.1 * (energyMultiplier - 1) / 4);

      renderer.render(scene, camera);
    }

    // Çizgileri güncelle — yakın parçacıkları bağla
    function updateLines(pos) {
      const lp   = lineGeo.attributes.position.array;
      const DIST = 18 + energyMultiplier * 2;
      let   idx  = 0;
      const maxL = maxLines;

      outer: for (let i = 0; i < PARTICLE_COUNT; i += 3) {
        const ax = pos[i * 3], ay = pos[i * 3 + 1], az = pos[i * 3 + 2];
        for (let j = i + 3; j < PARTICLE_COUNT; j += 3) {
          const dx = ax - pos[j * 3];
          const dy = ay - pos[j * 3 + 1];
          const dz = az - pos[j * 3 + 2];
          if (dx * dx + dy * dy + dz * dz < DIST * DIST) {
            lp[idx++] = ax; lp[idx++] = ay; lp[idx++] = az;
            lp[idx++] = pos[j * 3]; lp[idx++] = pos[j * 3 + 1]; lp[idx++] = pos[j * 3 + 2];
            if (idx / 6 >= maxL) break outer;
          }
        }
      }
      lineGeo.setDrawRange(0, idx / 3);
      lineGeo.attributes.position.needsUpdate = true;
    }

    animate();
    console.log('[Eva 3D] Particle network başlatıldı ✓');
  });
})();
