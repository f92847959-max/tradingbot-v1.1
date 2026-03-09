import { forwardRef, useImperativeHandle, useState, type CSSProperties } from "react";

export type ParticleDirection = "radial" | "up" | "down" | "away";

export type ParticleBurstConfig = {
  x: number;
  y: number;
  count: number;
  spreadRadius: number;
  velocity: number;
  rotationRange: number;
  color: string;
  durationMs: number;
  delayMs?: number;
  direction?: ParticleDirection;
};

export type ParticleFieldHandle = {
  burst: (config: ParticleBurstConfig) => void;
};

type ParticleModel = {
  id: string;
  x: number;
  y: number;
  dx: number;
  dy: number;
  rotation: number;
  size: number;
  color: string;
  durationMs: number;
  delayMs: number;
};

const TAU = Math.PI * 2;

function randomRange(min: number, max: number): number {
  return Math.random() * (max - min) + min;
}

export const ParticleField = forwardRef<ParticleFieldHandle, { disabled?: boolean }>(
  function ParticleField({ disabled = false }, ref) {
    const [particles, setParticles] = useState<ParticleModel[]>([]);

    useImperativeHandle(ref, () => ({
      burst(config: ParticleBurstConfig) {
        if (disabled || config.count <= 0) return;

        const now = Date.now();
        const next: ParticleModel[] = [];
        const direction = config.direction ?? "radial";

        for (let index = 0; index < config.count; index += 1) {
          const angle = randomRange(0, TAU);
          const radialDistance = randomRange(config.spreadRadius * 0.2, config.spreadRadius);
          const velocity = randomRange(config.velocity * 0.75, config.velocity * 1.15);
          const baseDx = Math.cos(angle) * velocity;
          const baseDy = Math.sin(angle) * velocity;

          let dx = baseDx;
          let dy = baseDy;
          if (direction === "up") {
            dy = -Math.abs(baseDy) - radialDistance * 0.6;
          } else if (direction === "down") {
            dy = Math.abs(baseDy) + radialDistance * 0.6;
          } else if (direction === "away") {
            dx *= 1.45;
            dy *= 1.45;
          }

          next.push({
            id: `${now}-${index}-${Math.random().toString(16).slice(2)}`,
            x: config.x,
            y: config.y,
            dx,
            dy,
            rotation: randomRange(-config.rotationRange, config.rotationRange),
            size: randomRange(3, 9),
            color: config.color,
            durationMs: config.durationMs,
            delayMs: Math.max(0, config.delayMs ?? 0) + index * 16,
          });
        }

        setParticles((current) => [...current, ...next]);

        const cleanupDelay = config.durationMs + (config.delayMs ?? 0) + 240;
        window.setTimeout(() => {
          const ids = new Set(next.map((item) => item.id));
          setParticles((current) => current.filter((item) => !ids.has(item.id)));
        }, cleanupDelay);
      },
    }), [disabled]);

    return (
      <div className="particle-layer" aria-hidden>
        {particles.map((particle) => (
          <span
            key={particle.id}
            className="particle-bit"
            style={
              {
                left: particle.x,
                top: particle.y,
                width: particle.size,
                height: particle.size,
                background: particle.color,
                ["--particle-dx" as string]: `${particle.dx}px`,
                ["--particle-dy" as string]: `${particle.dy}px`,
                ["--particle-rot" as string]: `${particle.rotation}deg`,
                ["--particle-life" as string]: `${particle.durationMs}ms`,
                ["--particle-delay" as string]: `${particle.delayMs}ms`,
              } as CSSProperties
            }
          />
        ))}
      </div>
    );
  },
);
