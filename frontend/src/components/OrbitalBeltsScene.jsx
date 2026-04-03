import React, { useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Stars, useTexture } from '@react-three/drei';
import * as THREE from 'three';

const EARTH_R = 1.0;

function toVec(lat, lon, altKm = 550) {
  const r = EARTH_R + altKm / 7000;
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon + 180);
  return new THREE.Vector3(
    r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta)
  );
}

function ShellRing({ radius, color }) {
  const pts = useMemo(() => {
    const arr = [];
    for (let i = 0; i <= 200; i++) {
      const t = (i / 200) * Math.PI * 2;
      arr.push(new THREE.Vector3(Math.cos(t) * radius, 0, Math.sin(t) * radius));
    }
    return arr;
  }, [radius]);
  const geom = useMemo(() => new THREE.BufferGeometry().setFromPoints(pts), [pts]);
  return <line geometry={geom}><lineBasicMaterial color={color} transparent opacity={0.25} /></line>;
}

function Cloud({ points = [], color = '#7db8ff', size = 0.012 }) {
  const positions = useMemo(() => {
    const out = new Float32Array(points.length * 3);
    points.forEach((p, i) => {
      out[i * 3] = p.x;
      out[i * 3 + 1] = p.y;
      out[i * 3 + 2] = p.z;
    });
    return out;
  }, [points]);

  return (
    <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={points.length} array={positions} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial color={color} size={size} sizeAttenuation depthWrite={false} transparent opacity={0.9} />
    </points>
  );
}

function Scene({ satellites = [], debrisCloud = [], selectedBand = 'LEO' }) {
  const dayTex = useTexture('/textures/earth_daymap.jpg');
  const satPts = useMemo(() => satellites.slice(0, 250).map((s) => toVec(s.lat ?? 0, s.lon ?? 0, s.alt ?? 550)), [satellites]);
  const debPts = useMemo(() => debrisCloud.slice(0, 4000).map((d) => toVec(d[1] ?? 0, d[2] ?? 0, d[3] ?? 550)), [debrisCloud]);

  const leo = debPts.filter((p) => p.length() < 1.18);
  const meo = debPts.filter((p) => p.length() >= 1.18 && p.length() < 1.45);
  const high = debPts.filter((p) => p.length() >= 1.45);

  const shellInfo = {
    LEO: { title: 'Low Earth Orbit', note: 'Primary constellation and debris activity', color: '#7db8ff' },
    MEO: { title: 'Medium Earth Orbit', note: 'Navigation and transfer regimes', color: '#8fffc1' },
    HIGH: { title: 'High Altitude / GEO transfer', note: 'Sparse but persistent long-duration objects', color: '#ff7ea7' },
  }[selectedBand] || { title: 'Low Earth Orbit', note: '', color: '#7db8ff' };

  return (
    <>
      <color attach="background" args={['#020608']} />
      <ambientLight intensity={0.55} />
      <directionalLight position={[5, 3, 5]} intensity={1.6} color="#dce8ff" />
      <Stars radius={120} depth={40} count={3500} factor={3} saturation={0} fade speed={0.4} />

      <mesh>
        <sphereGeometry args={[EARTH_R, 64, 64]} />
        <meshStandardMaterial map={dayTex} roughness={1} metalness={0} />
      </mesh>
      <mesh scale={1.02}>
        <sphereGeometry args={[EARTH_R, 48, 48]} />
        <meshBasicMaterial color="#294d87" transparent opacity={0.06} side={THREE.BackSide} />
      </mesh>

      <ShellRing radius={1.08} color="#7db8ff" />
      <ShellRing radius={1.28} color="#8fffc1" />
      <ShellRing radius={1.62} color="#ff7ea7" />

      <Cloud points={leo} color="#7db8ff" size={0.012} />
      <Cloud points={meo} color="#8fffc1" size={0.013} />
      <Cloud points={high} color="#ff7ea7" size={0.013} />
      <Cloud points={satPts} color="#f5c96d" size={0.024} />

      <OrbitControls enablePan={false} minDistance={1.8} maxDistance={5.5} autoRotate autoRotateSpeed={0.3} />
    </>
  );
}

export default function OrbitalBeltsScene(props) {
  return (
    <Canvas camera={{ position: [2.8, 1.9, 2.8], fov: 42 }} gl={{ antialias: true }}>
      <Scene {...props} />
    </Canvas>
  );
}
