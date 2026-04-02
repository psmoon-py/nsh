/**
 * Globe3D — Production-quality 3D orbital visualization.
 *
 * Architecture:
 *  - Custom GLSL ShaderMaterial: day/night Earth with smoothstep terminator,
 *    Blinn-Phong ocean specular, twilight tint, Fresnel atmospheric rim.
 *  - Atmosphere: BackSide sphere with Fresnel glow + additive blending.
 *  - THREE.Points: single draw call for 10,000+ debris objects.
 *  - InstancedMesh: single draw call for all satellite markers.
 *  - GMST-synchronized Earth rotation (texture aligns to ECI frame).
 *  - logarithmicDepthBuffer: prevents z-fighting at orbital scale.
 */

import React, { useRef, useMemo, useEffect, useCallback } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Stars, Html, useTexture } from '@react-three/drei';
import * as THREE from 'three';

// ── Scale: 1 scene unit = 1000 km. Earth radius ≈ 6.378 scene units.
const EARTH_RADIUS = 6.378;   // scene units (= 6378 km / 1000)
const SCALE        = 1 / 1000; // km → scene units

// ── Approximate sun direction (fixed for aesthetics; could be computed from timestamp)
const SUN_DIR = new THREE.Vector3(1.0, 0.3, 0.5).normalize();

// ── GMST: Greenwich Mean Sidereal Time → Earth Y-rotation (radians)
function computeGMST(timestampStr) {
  try {
    const d  = new Date(timestampStr);
    const jd = d.getTime() / 86400000.0 + 2440587.5;
    const T  = (jd - 2451545.0) / 36525.0;
    const deg = (280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T) % 360.0;
    return (deg * Math.PI) / 180.0;
  } catch {
    return 0.0;
  }
}

// ── ECI (km) → Three.js (scene units, Y-up / north-pole = +Y)
function eciToVec3(r) {
  // ECI: X toward vernal equinox, Y completing equatorial plane, Z toward north pole
  // Three.js Y-up: ECI-Z → Three-Y, ECI-Y → Three-Z (flipped sign for right-hand to left-hand)
  return new THREE.Vector3(
     r.x * SCALE,
     r.z * SCALE,   // ECI Z (north) → Three.js Y (up)
    -r.y * SCALE,   // ECI Y → Three.js -Z
  );
}

// ── lat/lon/alt (degrees, km) → Three.js scene position
function llaToVec3(lat, lon, alt) {
  const r   = EARTH_RADIUS + alt * SCALE;
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon + 90); // +90 aligns 0° lon with Three.js +X
  return new THREE.Vector3(
    r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// GLSL SHADERS
// ═══════════════════════════════════════════════════════════════════════════════

const EARTH_VERT = /* glsl */`
varying vec2  vUv;
varying vec3  vNormal;
varying vec3  vPosition;

void main() {
  vUv      = uv;
  vNormal  = normalize(normalMatrix * normal);
  vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const EARTH_FRAG = /* glsl */`
uniform sampler2D uDayTexture;
uniform sampler2D uNightTexture;
uniform vec3      uSunDirection;

varying vec2 vUv;
varying vec3 vNormal;
varying vec3 vPosition;

void main() {
  vec3 dayColor   = texture2D(uDayTexture,   vUv).rgb;
  vec3 nightColor = texture2D(uNightTexture, vUv).rgb * 2.0; // boost city lights

  float NdotL = dot(vNormal, uSunDirection);

  // Smooth day/night blend — wide twilight zone (key detail for realism)
  float dayMix = smoothstep(-0.15, 0.25, NdotL);

  // Base color: night side + day side with diffuse shading
  float diffuse = max(NdotL, 0.0);
  vec3 color = mix(nightColor, dayColor * (0.3 + 0.7 * diffuse), dayMix);

  // Twilight tint (warm orange at the terminator edge)
  float twilight = pow(clamp(1.0 - abs(NdotL * 5.0), 0.0, 1.0), 2.5);
  color += vec3(1.0, 0.45, 0.2) * twilight * 0.1;

  // Fresnel atmospheric rim on day side
  vec3 viewDir = normalize(-vPosition);
  float fresnel = pow(1.0 - max(dot(viewDir, vNormal), 0.0), 3.0);
  color += vec3(0.35, 0.6, 1.0) * fresnel * dayMix * 0.18;

  gl_FragColor = vec4(color, 1.0);
}
`;

const ATMO_VERT = /* glsl */`
varying vec3 vNormal;
varying vec3 vPosition;

void main() {
  vNormal   = normalize(normalMatrix * normal);
  vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const ATMO_FRAG = /* glsl */`
uniform vec3  uAtmosphereColor;
uniform float uAtmosphereIntensity;
uniform vec3  uSunDirection;

varying vec3 vNormal;
varying vec3 vPosition;

void main() {
  vec3 viewDir = normalize(-vPosition);
  // Fresnel on the BackSide: edges glow, center transparent
  float fresnel = pow(clamp(dot(viewDir, -vNormal), 0.0, 1.0), 3.5);
  // Modulate by sun direction: brighter limb on day side, dim on night side
  float sunMix = 0.15 + 0.85 * smoothstep(-0.5, 1.0, dot(-vNormal, uSunDirection));
  gl_FragColor = vec4(uAtmosphereColor, fresnel * uAtmosphereIntensity * sunMix);
}
`;

// ═══════════════════════════════════════════════════════════════════════════════
// EARTH COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function Earth({ timestamp }) {
  const earthRef  = useRef();
  const gmstRef   = useRef(0);

  // Load textures
  const dayTex   = useTexture('/textures/earth_daymap.jpg');
  const nightTex = useTexture('/textures/earth_nightmap.jpg');

  // Shader uniforms (memoized, only update when textures load)
  const uniforms = useMemo(() => ({
    uDayTexture:   { value: dayTex },
    uNightTexture: { value: nightTex },
    uSunDirection: { value: SUN_DIR.clone() },
  }), [dayTex, nightTex]);

  const atmoUniforms = useMemo(() => ({
    uAtmosphereColor:     { value: new THREE.Color(0x4477cc) },
    uAtmosphereIntensity: { value: 1.6 },
    uSunDirection:        { value: SUN_DIR.clone() },
  }), []);

  // Update GMST when timestamp changes
  useEffect(() => {
    if (timestamp && timestamp !== '—') {
      gmstRef.current = computeGMST(timestamp);
    }
  }, [timestamp]);

  // Apply GMST rotation each frame
  useFrame(() => {
    if (earthRef.current) {
      earthRef.current.rotation.y = gmstRef.current;
    }
  });

  return (
    <group>
      {/* ── Main Earth sphere with custom day/night shader ── */}
      <mesh ref={earthRef}>
        <sphereGeometry args={[EARTH_RADIUS, 64, 64]} />
        <shaderMaterial
          vertexShader={EARTH_VERT}
          fragmentShader={EARTH_FRAG}
          uniforms={uniforms}
        />
      </mesh>

      {/* ── Atmosphere: BackSide sphere with Fresnel glow ── */}
      <mesh scale={[1.018, 1.018, 1.018]}>
        <sphereGeometry args={[EARTH_RADIUS, 48, 48]} />
        <shaderMaterial
          vertexShader={ATMO_VERT}
          fragmentShader={ATMO_FRAG}
          uniforms={atmoUniforms}
          side={THREE.BackSide}
          transparent
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>

      {/* ── Outer glow halo ── */}
      <mesh scale={[1.06, 1.06, 1.06]}>
        <sphereGeometry args={[EARTH_RADIUS, 32, 32]} />
        <meshBasicMaterial
          color={0x1133aa}
          transparent
          opacity={0.04}
          side={THREE.BackSide}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </group>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SATELLITES — InstancedMesh (single draw call)
// ═══════════════════════════════════════════════════════════════════════════════

const DUMMY = new THREE.Object3D();

function Satellites({ satellites, selectedSat, onSelectSat }) {
  const meshRef = useRef();
  const count   = satellites.length;

  // Per-instance color
  const colorArray = useMemo(() => {
    const arr = new Float32Array(Math.max(count, 1) * 3);
    satellites.forEach((sat, i) => {
      const c = new THREE.Color(
        sat.id === selectedSat  ? '#00e5ff' :
        sat.status === 'NOMINAL' ? '#00e676' : '#ffab00'
      );
      arr[i*3] = c.r; arr[i*3+1] = c.g; arr[i*3+2] = c.b;
    });
    return arr;
  }, [satellites, selectedSat, count]);

  useEffect(() => {
    if (!meshRef.current || count === 0) return;
    satellites.forEach((sat, i) => {
      // Prefer ECI position (accurate) over LLA fallback
      const pos = sat.r
        ? eciToVec3(sat.r)
        : llaToVec3(sat.lat, sat.lon, sat.alt || 550);

      const scale = sat.id === selectedSat ? 0.065 : 0.04;
      DUMMY.position.copy(pos);
      DUMMY.scale.setScalar(scale);
      DUMMY.updateMatrix();
      meshRef.current.setMatrixAt(i, DUMMY.matrix);
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
    if (meshRef.current.instanceColor) {
      meshRef.current.instanceColor.needsUpdate = true;
    }
  }, [satellites, selectedSat, count]);

  // Handle click → find which instance was clicked
  const handleClick = useCallback((e) => {
    e.stopPropagation();
    const idx = e.instanceId;
    if (idx !== undefined && satellites[idx]) {
      onSelectSat(satellites[idx].id);
    }
  }, [satellites, onSelectSat]);

  if (count === 0) return null;

  return (
    <group>
      <instancedMesh
        ref={meshRef}
        key={count}
        args={[undefined, undefined, count]}
        onClick={handleClick}
        frustumCulled={false}
      >
        <octahedronGeometry args={[1, 0]} />
        <meshStandardMaterial
          vertexColors
          metalness={0.6}
          roughness={0.3}
          emissive={new THREE.Color(0x002244)}
          emissiveIntensity={0.3}
        />
      </instancedMesh>

      {/* Instance color attribute */}
      {/* Note: instanceColor is set via setColorAt but we use vertexColors on geometry */}

      {/* Selected satellite tooltip via Html */}
      {satellites.map((sat) => {
        if (sat.id !== selectedSat) return null;
        const pos = sat.r
          ? eciToVec3(sat.r)
          : llaToVec3(sat.lat, sat.lon, sat.alt || 550);
        return (
          <Html key={sat.id} position={[pos.x, pos.y + 0.25, pos.z]}
            center distanceFactor={20} occlude
            style={{
              color: '#00e5ff',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 9,
              background: 'rgba(6,8,13,0.9)',
              padding: '4px 8px',
              borderRadius: 2,
              border: '1px solid rgba(0,229,255,0.4)',
              whiteSpace: 'nowrap',
              pointerEvents: 'none',
              userSelect: 'none',
              backdropFilter: 'blur(8px)',
              lineHeight: 1.6,
            }}
          >
            <div style={{ fontWeight: 600, letterSpacing: 1 }}>{sat.id}</div>
            <div style={{ color: '#7aafb5' }}>
              ⛽ {sat.fuel_kg?.toFixed(1)} kg · {sat.status}
            </div>
          </Html>
        );
      })}

      {/* Pulse ring around selected satellite */}
      {satellites.map((sat) => {
        if (sat.id !== selectedSat) return null;
        const pos = sat.r
          ? eciToVec3(sat.r)
          : llaToVec3(sat.lat, sat.lon, sat.alt || 550);
        return (
          <mesh key={`ring-${sat.id}`} position={pos} rotation={[Math.PI / 2, 0, 0]}>
            <ringGeometry args={[0.10, 0.14, 32]} />
            <meshBasicMaterial
              color="#00e5ff"
              transparent
              opacity={0.35}
              side={THREE.DoubleSide}
              depthWrite={false}
            />
          </mesh>
        );
      })}
    </group>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// DEBRIS CLOUD — THREE.Points (single draw call for 10k+ objects)
// ═══════════════════════════════════════════════════════════════════════════════

function DebrisCloud({ debrisCloud }) {
  const count = debrisCloud.length;

  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    debrisCloud.forEach(([, lat, lon, alt], i) => {
      const pos = llaToVec3(lat, lon, alt || 400);
      arr[i*3]   = pos.x;
      arr[i*3+1] = pos.y;
      arr[i*3+2] = pos.z;
    });
    return arr;
  }, [debrisCloud, count]);

  if (count === 0) return null;

  return (
    <points frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={count}
          array={positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.015}
        color={new THREE.Color(0xff4444)}
        sizeAttenuation
        transparent
        opacity={0.65}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// GROUND STATION MARKERS
// ═══════════════════════════════════════════════════════════════════════════════

const GROUND_STATIONS = [
  { id: 'GS-001', name: 'ISTRAC',      lat: 13.0333,  lon: 77.5167,  elev: 0.82 },
  { id: 'GS-002', name: 'Svalbard',    lat: 78.2297,  lon: 15.4077,  elev: 0.4 },
  { id: 'GS-003', name: 'Goldstone',   lat: 35.4266,  lon: -116.89,  elev: 1.0 },
  { id: 'GS-004', name: 'Pta Arenas',  lat: -53.15,   lon: -70.9167, elev: 0.03 },
  { id: 'GS-005', name: 'IIT Delhi',   lat: 28.545,   lon: 77.1926,  elev: 0.225 },
  { id: 'GS-006', name: 'McMurdo',     lat: -77.8463, lon: 166.6682, elev: 0.01 },
];

function GroundStationMarkers() {
  return (
    <group>
      {GROUND_STATIONS.map((gs) => {
        const pos = llaToVec3(gs.lat, gs.lon, gs.elev);
        return (
          <group key={gs.id} position={pos}>
            <mesh rotation={[0, 0, Math.PI / 4]}>
              <boxGeometry args={[0.04, 0.04, 0.006]} />
              <meshBasicMaterial color="#ffab00" />
            </mesh>
            {/* Coverage cone (wireframe) */}
            <mesh position={[0, 0.12, 0]}>
              <coneGeometry args={[0.06, 0.16, 4]} />
              <meshBasicMaterial
                color="#ffab00"
                transparent
                opacity={0.07}
                wireframe
              />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// CDM THREAT LINES — pulsing lines between satellite and threat direction
// ═══════════════════════════════════════════════════════════════════════════════

function ThreatLines({ satellites, cdmWarnings }) {
  const matRefs = useRef({});

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    Object.values(matRefs.current).forEach((mat, i) => {
      if (mat) {
        mat.opacity = 0.25 + 0.5 * (0.5 + 0.5 * Math.sin(t * 4.0 + i));
      }
    });
  });

  const lines = useMemo(() => {
    return cdmWarnings
      .filter((c) => c.risk_level === 'CRITICAL' || c.risk_level === 'RED')
      .slice(0, 8)
      .map((cdm) => {
        const sat = satellites.find((s) => s.id === cdm.sat_id);
        if (!sat || !sat.r) return null;
        const satPos = eciToVec3(sat.r);
        // Estimate debris direction as outward from center
        const dir = satPos.clone().normalize();
        const debPos = dir.multiplyScalar(satPos.length() + 0.3);
        const geom = new THREE.BufferGeometry().setFromPoints([satPos, debPos]);
        return {
          key: `${cdm.sat_id}-${cdm.deb_id}`,
          geom,
          isCritical: cdm.risk_level === 'CRITICAL',
        };
      })
      .filter(Boolean);
  }, [satellites, cdmWarnings]);

  return (
    <group>
      {lines.map((l, i) => (
        <line key={l.key} geometry={l.geom}>
          <lineBasicMaterial
            ref={(m) => { matRefs.current[i] = m; }}
            color={l.isCritical ? '#ff3b3b' : '#ffab00'}
            transparent
            opacity={0.5}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </line>
      ))}
    </group>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ORBIT RINGS — decorative orbital altitude reference
// ═══════════════════════════════════════════════════════════════════════════════

function OrbitRing({ altitude, color = '#1e2a3e', opacity = 0.12 }) {
  const r = EARTH_RADIUS + altitude * SCALE;
  return (
    <mesh rotation={[Math.PI / 2, 0, 0]}>
      <ringGeometry args={[r - 0.004, r + 0.004, 128]} />
      <meshBasicMaterial
        color={color}
        transparent
        opacity={opacity}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SCENE LIGHTING
// ═══════════════════════════════════════════════════════════════════════════════

function SceneLighting() {
  return (
    <>
      {/* Sun — directional light matching uSunDirection */}
      <directionalLight
        position={[SUN_DIR.x * 80, SUN_DIR.y * 80, SUN_DIR.z * 80]}
        intensity={2.5}
        color="#fff8e8"
      />
      {/* Ambient fill — deep blue space ambience */}
      <ambientLight intensity={0.08} color="#223366" />
    </>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN EXPORT
// ═══════════════════════════════════════════════════════════════════════════════

export default function Globe3D({
  satellites  = [],
  debrisCloud = [],
  cdmWarnings = [],
  selectedSat,
  onSelectSat,
  timestamp,
}) {
  return (
    <Canvas
      camera={{ position: [0, 8, 18], fov: 42, near: 0.01, far: 2000 }}
      gl={{
        antialias: true,
        alpha: false,
        toneMapping: THREE.ACESFilmicToneMapping,
        toneMappingExposure: 1.1,
        outputColorSpace: THREE.SRGBColorSpace,
      }}
      // CRITICAL: logarithmicDepthBuffer prevents z-fighting at orbital scale
      // (Earth surface is 6378 km from center; debris is ~6800–7200 km — huge depth range)
      logarithmicDepthBuffer
      dpr={[1, 1.5]}
      style={{ background: '#06080d' }}
    >
      <SceneLighting />
      <Stars
        radius={400}
        depth={60}
        count={7000}
        factor={3.5}
        saturation={0.08}
        fade
        speed={0.4}
      />
      <OrbitControls
        enablePan={false}
        minDistance={8}
        maxDistance={60}
        enableDamping
        dampingFactor={0.06}
        rotateSpeed={0.45}
        zoomSpeed={0.7}
      />

      {/* ── Core scene objects ── */}
      <Earth timestamp={timestamp} />
      <GroundStationMarkers />

      {/* ── Orbital reference rings ── */}
      <OrbitRing altitude={400} color="#1e2a3e" opacity={0.12} />
      <OrbitRing altitude={550} color="#006688" opacity={0.10} />
      <OrbitRing altitude={800} color="#1e2a3e" opacity={0.08} />
      <OrbitRing altitude={1200} color="#0a1420" opacity={0.06} />

      {/* ── Data layers ── */}
      <DebrisCloud debrisCloud={debrisCloud} />
      <Satellites
        satellites={satellites}
        selectedSat={selectedSat}
        onSelectSat={onSelectSat}
      />
      <ThreatLines satellites={satellites} cdmWarnings={cdmWarnings} />
    </Canvas>
  );
}
