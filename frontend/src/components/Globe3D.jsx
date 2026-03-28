import React, { useRef, useMemo, useCallback, useEffect } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Stars, Html } from '@react-three/drei';
import * as THREE from 'three';

const EARTH_RADIUS = 6.378; // Scaled: 1 unit = 1000 km
const SCALE = 1 / 1000;     // Convert km to scene units

/**
 * Convert lat/lon/alt to 3D Cartesian for the scene.
 */
function llaToVec3(lat, lon, alt) {
  const r = EARTH_RADIUS + alt * SCALE;
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon);
  return new THREE.Vector3(
    r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta)
  );
}

function eciToVec3(r) {
  return new THREE.Vector3(r.x * SCALE, r.z * SCALE, -r.y * SCALE);
}

/* ================ EARTH ================ */
function Earth() {
  const meshRef = useRef();
  const cloudsRef = useRef();

  const textures = useMemo(() => {
    const loader = new THREE.TextureLoader();
    return {
      map: loader.load('/textures/earth_daymap.jpg'),
      night: loader.load('/textures/earth_nightmap.jpg'),
    };
  }, []);

  useFrame((_, delta) => {
    if (meshRef.current) meshRef.current.rotation.y += delta * 0.01;
  });

  return (
    <group>
      <mesh ref={meshRef}>
        <sphereGeometry args={[EARTH_RADIUS, 64, 64]} />
        <meshPhongMaterial
          map={textures.map}
          emissiveMap={textures.night}
          emissive={new THREE.Color(0x222222)}
          emissiveIntensity={1.5}
          specular={new THREE.Color(0x222244)}
          shininess={15}
        />
      </mesh>

      {/* Atmosphere glow */}
      <mesh>
        <sphereGeometry args={[EARTH_RADIUS * 1.015, 64, 64]} />
        <meshBasicMaterial color={0x4488ff} transparent opacity={0.06} side={THREE.BackSide} />
      </mesh>
      <mesh>
        <sphereGeometry args={[EARTH_RADIUS * 1.04, 32, 32]} />
        <meshBasicMaterial color={0x00aaff} transparent opacity={0.025} side={THREE.BackSide} />
      </mesh>
    </group>
  );
}

/* ================ SATELLITES ================ */
function Satellites({ satellites, selectedSat, onSelectSat }) {
  return (
    <group>
      {satellites.map((sat) => {
        const pos = sat.r
          ? eciToVec3(sat.r)
          : llaToVec3(sat.lat, sat.lon, sat.alt || 550);

        const isSelected = sat.id === selectedSat;
        const isNominal = sat.status === 'NOMINAL';
        const color = isSelected ? '#00e5ff' : isNominal ? '#00e676' : '#ffab00';

        return (
          <group key={sat.id} position={pos}>
            <mesh onClick={() => onSelectSat(sat.id)}>
              <sphereGeometry args={[isSelected ? 0.04 : 0.025, 8, 8]} />
              <meshBasicMaterial color={color} />
            </mesh>

            {isSelected && (
              <mesh>
                <ringGeometry args={[0.06, 0.1, 32]} />
                <meshBasicMaterial color="#00e5ff" transparent opacity={0.4} side={THREE.DoubleSide} />
              </mesh>
            )}

            {isSelected && (
              <Html
                distanceFactor={15}
                style={{
                  color: '#00e5ff', fontSize: 10,
                  fontFamily: "'IBM Plex Mono', monospace",
                  background: 'rgba(6,8,13,0.85)', padding: '2px 6px',
                  borderRadius: 3, border: '1px solid rgba(0,229,255,0.3)',
                  whiteSpace: 'nowrap', pointerEvents: 'none', userSelect: 'none',
                }}
              >
                {sat.id} — {sat.fuel_kg?.toFixed(1)} kg
              </Html>
            )}
          </group>
        );
      })}
    </group>
  );
}

/* ================ DEBRIS CLOUD (InstancedMesh) ================ */
function DebrisCloud({ debrisCloud }) {
  const meshRef = useRef();
  const count = debrisCloud.length;
  const dummy = useMemo(() => new THREE.Object3D(), []);

  // FIX: useEffect instead of useMemo — refs aren't available during render phase
  useEffect(() => {
    if (!meshRef.current || count === 0) return;

    for (let i = 0; i < count; i++) {
      const [, lat, lon, alt] = debrisCloud[i];
      const pos = llaToVec3(lat, lon, alt);
      dummy.position.copy(pos);
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
    }
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, [debrisCloud, count, dummy]);

  if (count === 0) return null;

  return (
    // FIX: key={count} forces remount when debris count changes
    // (InstancedMesh can't resize its buffer dynamically)
    <instancedMesh ref={meshRef} key={count} args={[null, null, Math.max(count, 1)]} frustumCulled={false}>
      <sphereGeometry args={[0.008, 4, 4]} />
      <meshBasicMaterial color="#ff3d4a" transparent opacity={0.35} />
    </instancedMesh>
  );
}

/* ================ GROUND STATIONS ================ */
const GROUND_STATIONS = [
  { id: 'GS-001', name: 'ISTRAC Bengaluru', lat: 13.0333, lon: 77.5167, elev: 0.82 },
  { id: 'GS-002', name: 'Svalbard', lat: 78.2297, lon: 15.4077, elev: 0.4 },
  { id: 'GS-003', name: 'Goldstone', lat: 35.4266, lon: -116.89, elev: 1.0 },
  { id: 'GS-004', name: 'Punta Arenas', lat: -53.15, lon: -70.9167, elev: 0.03 },
  { id: 'GS-005', name: 'IIT Delhi', lat: 28.545, lon: 77.1926, elev: 0.225 },
  { id: 'GS-006', name: 'McMurdo', lat: -77.8463, lon: 166.6682, elev: 0.01 },
];

function GroundStationMarkers() {
  return (
    <group>
      {GROUND_STATIONS.map((gs) => {
        const pos = llaToVec3(gs.lat, gs.lon, gs.elev);
        return (
          <group key={gs.id} position={pos}>
            <mesh rotation={[0, 0, Math.PI / 4]}>
              <boxGeometry args={[0.03, 0.03, 0.005]} />
              <meshBasicMaterial color="#ffab00" />
            </mesh>
            <mesh position={[0, 0.08, 0]}>
              <coneGeometry args={[0.04, 0.12, 4]} />
              <meshBasicMaterial color="#ffab00" transparent opacity={0.08} wireframe />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}

/* ================ CDM THREAT LINES ================ */
function ThreatLines({ satellites, cdmWarnings }) {
  const lines = useMemo(() => {
    return cdmWarnings
      .filter((c) => c.risk_level === 'CRITICAL' || c.risk_level === 'RED')
      .slice(0, 10)
      .map((cdm) => {
        const sat = satellites.find((s) => s.id === cdm.sat_id);
        if (!sat || !sat.r) return null;
        const satPos = eciToVec3(sat.r);
        const dir = satPos.clone().normalize();
        const debPos = dir.multiplyScalar(satPos.length() + 0.2);
        return { key: `${cdm.sat_id}-${cdm.deb_id}`, points: [satPos, debPos], risk: cdm.risk_level };
      })
      .filter(Boolean);
  }, [satellites, cdmWarnings]);

  return (
    <group>
      {lines.map((l) => {
        const geom = new THREE.BufferGeometry().setFromPoints(l.points);
        return (
          <line key={l.key} geometry={geom}>
            <lineBasicMaterial
              color={l.risk === 'CRITICAL' ? '#ff3d4a' : '#ffab00'}
              transparent opacity={0.5} linewidth={1}
            />
          </line>
        );
      })}
    </group>
  );
}

/* ================ ORBIT RING ================ */
function OrbitRing({ altitude, color = '#1e2a3e', opacity = 0.15 }) {
  const r = EARTH_RADIUS + altitude * SCALE;
  return (
    <mesh rotation={[Math.PI / 2, 0, 0]}>
      <ringGeometry args={[r - 0.005, r + 0.005, 128]} />
      <meshBasicMaterial color={color} transparent opacity={opacity} side={THREE.DoubleSide} />
    </mesh>
  );
}

/* ================ SCENE SETUP ================ */
function SceneSetup() {
  return (
    <>
      <directionalLight position={[50, 20, 30]} intensity={2.0} color="#fff5e0" />
      <ambientLight intensity={0.15} color="#4466aa" />
      <Stars radius={300} depth={100} count={6000} factor={3} saturation={0.1} fade speed={0.5} />
      <OrbitControls
        enablePan={false} minDistance={8} maxDistance={40}
        enableDamping dampingFactor={0.05} rotateSpeed={0.5} zoomSpeed={0.8}
      />
    </>
  );
}

/* ================ MAIN COMPONENT ================ */
export default function Globe3D({
  satellites = [], debrisCloud = [], cdmWarnings = [],
  selectedSat, onSelectSat,
}) {
  return (
    <Canvas
      camera={{ position: [0, 8, 16], fov: 45, near: 0.1, far: 1000 }}
      style={{ background: '#06080d' }}
      gl={{ antialias: true, alpha: false }}
      dpr={[1, 2]}
    >
      <SceneSetup />
      <Earth />
      <GroundStationMarkers />
      <OrbitRing altitude={400} />
      <OrbitRing altitude={550} color="#00809a" opacity={0.08} />
      <OrbitRing altitude={800} />
      <DebrisCloud debrisCloud={debrisCloud} />
      <Satellites satellites={satellites} selectedSat={selectedSat} onSelectSat={onSelectSat} />
      <ThreatLines satellites={satellites} cdmWarnings={cdmWarnings} />
    </Canvas>
  );
}
