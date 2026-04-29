import { Suspense, useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import * as THREE from "three";

interface GoldDustProps {
  count: number;
  spread: number;
}

function GoldDust({ count, spread }: GoldDustProps) {
  const pointsRef = useRef<THREE.Points>(null);

  const { positions, sizes, phases } = useMemo(() => {
    const positions = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    const phases = new Float32Array(count);
    for (let i = 0; i < count; i += 1) {
      positions[i * 3 + 0] = (Math.random() - 0.5) * spread;
      positions[i * 3 + 1] = (Math.random() - 0.5) * spread;
      positions[i * 3 + 2] = (Math.random() - 0.5) * spread * 0.6;
      sizes[i] = 0.6 + Math.random() * 1.6;
      phases[i] = Math.random() * Math.PI * 2;
    }
    return { positions, sizes, phases };
  }, [count, spread]);

  useFrame(({ clock, pointer }) => {
    const points = pointsRef.current;
    if (!points) return;
    const t = clock.getElapsedTime();
    const positionAttr = points.geometry.attributes.position as THREE.BufferAttribute;
    const arr = positionAttr.array as Float32Array;
    for (let i = 0; i < count; i += 1) {
      const phase = phases[i];
      arr[i * 3 + 1] += Math.sin(t * 0.4 + phase) * 0.0035;
      arr[i * 3 + 0] += Math.cos(t * 0.3 + phase) * 0.0028;
    }
    positionAttr.needsUpdate = true;
    points.rotation.y = pointer.x * 0.08 + t * 0.005;
    points.rotation.x = pointer.y * 0.06;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
          count={count}
        />
        <bufferAttribute
          attach="attributes-size"
          args={[sizes, 1]}
          count={count}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.06}
        color={new THREE.Color("#f5cc5b")}
        transparent
        opacity={0.85}
        depthWrite={false}
        sizeAttenuation
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

function Nebula() {
  const meshRef = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    const m = meshRef.current;
    if (!m) return;
    m.rotation.z = clock.getElapsedTime() * 0.02;
  });
  return (
    <mesh ref={meshRef} position={[0, 0, -8]}>
      <planeGeometry args={[40, 40, 1, 1]} />
      <meshBasicMaterial
        color={new THREE.Color("#1a1230")}
        transparent
        opacity={0.45}
        depthWrite={false}
      />
    </mesh>
  );
}

interface BackgroundSceneProps {
  enabled?: boolean;
  intensity?: number;
}

export function BackgroundScene({
  enabled = true,
  intensity = 0.7,
}: BackgroundSceneProps) {
  if (!enabled) return null;

  const dustCount = Math.round(700 * Math.max(0.2, Math.min(1.4, intensity)));

  return (
    <div
      className="singularity-bg"
      aria-hidden="true"
      data-testid="singularity-bg"
    >
      <Canvas
        camera={{ position: [0, 0, 6], fov: 60 }}
        dpr={[1, 1.5]}
        gl={{ antialias: false, alpha: true, powerPreference: "high-performance" }}
        style={{ width: "100%", height: "100%" }}
      >
        <color attach="background" args={["#03040a"]} />
        <fog attach="fog" args={["#03040a", 6, 22]} />
        <ambientLight intensity={0.3} />
        <pointLight position={[6, 4, 6]} intensity={1.4} color="#f5cc5b" />
        <pointLight position={[-8, -6, -4]} intensity={0.6} color="#65d6ff" />
        <Suspense fallback={null}>
          <Nebula />
          <GoldDust count={dustCount} spread={18} />
        </Suspense>
        <EffectComposer multisampling={0} enableNormalPass={false}>
          <Bloom
            intensity={0.9 * intensity}
            luminanceThreshold={0.1}
            luminanceSmoothing={0.4}
            mipmapBlur
          />
        </EffectComposer>
      </Canvas>
    </div>
  );
}

export default BackgroundScene;
