eine sehr frühe demo version 

import React, { useState, useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ReferenceDot, ReferenceArea, ResponsiveContainer,
} from "recharts";
import {
  TrendingUp, TrendingDown, Target as TargetIcon,
  Activity, Zap, ChevronDown, ChevronRight, Bug, CheckCircle2, XCircle,
} from "lucide-react";

// ===========================================================================
// Synthetic data
// ===========================================================================
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function generatePriceData() {
  const rng = mulberry32(7);
  const prices = [2000];
  const seg = (to, n, noise = 1.5) => {
    const step = (to - prices[prices.length - 1]) / n;
    for (let i = 0; i < n; i++)
      prices.push(prices[prices.length - 1] + step + (rng() - 0.5) * noise * 2);
  };
  seg(2080, 20); seg(2030, 12); seg(2160, 25); seg(2110, 10); seg(2150, 8);

  return prices.map((p, i) => ({
    idx: i, close: p,
    high: p + rng() * 1.2 + 0.3,
    low: p - rng() * 1.2 - 0.3,
  }));
}

// ===========================================================================
// Core logic (mit Debug-Trace)
// ===========================================================================
function zigzagPivots(data, threshold, trace) {
  if (data.length < 3) return [];
  const pivots = [];
  let trend = null, extIdx = 0, extPrice = (data[0].high + data[0].low) / 2;
  const lastPrice = extPrice;

  for (let i = 1; i < data.length; i++) {
    if (trend === null) {
      if (data[i].high >= lastPrice * (1 + threshold)) {
        trend = "up";
        pivots.push({ idx: 0, price: data[0].low, kind: "low" });
        extIdx = i; extPrice = data[i].high;
        trace?.push({ idx: i, event: "trend-init-up", price: data[i].high });
      } else if (data[i].low <= lastPrice * (1 - threshold)) {
        trend = "down";
        pivots.push({ idx: 0, price: data[0].high, kind: "high" });
        extIdx = i; extPrice = data[i].low;
        trace?.push({ idx: i, event: "trend-init-down", price: data[i].low });
      }
      continue;
    }
    if (trend === "up") {
      if (data[i].high > extPrice) { extIdx = i; extPrice = data[i].high; }
      else if (data[i].low <= extPrice * (1 - threshold)) {
        pivots.push({ idx: extIdx, price: extPrice, kind: "high" });
        trace?.push({ idx: extIdx, event: "reversal-to-down", price: extPrice });
        trend = "down"; extIdx = i; extPrice = data[i].low;
      }
    } else {
      if (data[i].low < extPrice) { extIdx = i; extPrice = data[i].low; }
      else if (data[i].high >= extPrice * (1 + threshold)) {
        pivots.push({ idx: extIdx, price: extPrice, kind: "low" });
        trace?.push({ idx: extIdx, event: "reversal-to-up", price: extPrice });
        trend = "up"; extIdx = i; extPrice = data[i].high;
      }
    }
  }
  if (trend !== null) {
    pivots.push({ idx: extIdx, price: extPrice, kind: trend === "up" ? "high" : "low" });
    trace?.push({ idx: extIdx, event: "final-pivot", price: extPrice });
  }
  return pivots;
}

const FIB = {
  w2: [0.382, 0.5, 0.618, 0.786],
  w3: [1.272, 1.618, 2.0, 2.618],
  w4: [0.236, 0.382, 0.5],
  w5: [0.618, 1.0, 1.618],
  wB: [0.382, 0.5, 0.618, 0.786, 1.0, 1.382],
  wC: [0.618, 1.0, 1.272, 1.618],
};

function fibProximity(ratio, targets, tol = 0.15) {
  let best = 0, bestT = null;
  for (const t of targets) {
    const dist = Math.abs(ratio - t) / Math.max(t, 1e-6);
    const prox = Math.max(0, 1 - dist / tol);
    if (prox > best) { best = prox; bestT = t; }
  }
  return { score: best, nearestFib: bestT };
}

function alternating(pivots, dir) {
  let want = dir === "up" ? "low" : "high";
  for (const p of pivots) {
    if (p.kind !== want) return false;
    want = want === "low" ? "high" : "low";
  }
  return true;
}

function buildWave(s, e, label) {
  return {
    start: s, end: e, label,
    length: Math.abs(e.price - s.price),
    bars: e.idx - s.idx,
    direction: e.price > s.price ? "up" : "down",
  };
}

// ===========================================================================
// Hypothesis builders – return accepted or rejected with reasoning
// ===========================================================================
const rej = (name, reason) => ({ name, attempted: true, accepted: false, reason });
const acc = (name, prediction, breakdown) => ({
  name, attempted: true, accepted: true, prediction, scoreBreakdown: breakdown,
});

function hCompletedImpulse(pivots, price) {
  const name = "completed 5-wave impulse";
  if (pivots.length < 6) return rej(name, `need 6 pivots, have ${pivots.length}`);
  const seg = pivots.slice(-6);
  const dir = seg[5].price > seg[0].price ? "up" : "down";
  if (!alternating(seg, dir)) return rej(name, "pivots not alternating high/low");

  const w = []; for (let i = 0; i < 5; i++) w.push(buildWave(seg[i], seg[i + 1], String(i + 1)));
  if (w[1].length >= w[0].length) return rej(name, `w2 ≥ w1 (${(w[1].length/w[0].length).toFixed(2)})`);
  if (w[2].length < w[0].length && w[2].length < w[4].length) return rej(name, "w3 is shortest");
  if (dir === "up" && w[3].end.price <= w[0].end.price) return rej(name, `w4 overlaps w1 (${w[3].end.price.toFixed(2)} ≤ ${w[0].end.price.toFixed(2)})`);
  if (dir === "down" && w[3].end.price >= w[0].end.price) return rej(name, `w4 overlaps w1 (${w[3].end.price.toFixed(2)} ≥ ${w[0].end.price.toFixed(2)})`);

  const r = {
    "w2/w1": w[1].length / w[0].length, "w3/w1": w[2].length / w[0].length,
    "w4/w3": w[3].length / w[2].length, "w5/w1": w[4].length / w[0].length,
  };
  const f1 = fibProximity(r["w2/w1"], FIB.w2);
  const f2 = fibProximity(r["w3/w1"], FIB.w3);
  const f3 = fibProximity(r["w4/w3"], FIB.w4);
  const f4 = fibProximity(r["w5/w1"], FIB.w5);
  const altBonus = (r["w2/w1"] > 0.5) !== (r["w4/w3"] > 0.382) ? 0.15 : 0;

  const breakdown = [
    { component: "w2/w1", ratio: r["w2/w1"], weight: 0.20, nearest: f1.nearestFib, proximity: f1.score, contribution: f1.score * 0.20 },
    { component: "w3/w1", ratio: r["w3/w1"], weight: 0.30, nearest: f2.nearestFib, proximity: f2.score, contribution: f2.score * 0.30 },
    { component: "w4/w3", ratio: r["w4/w3"], weight: 0.20, nearest: f3.nearestFib, proximity: f3.score, contribution: f3.score * 0.20 },
    { component: "w5/w1", ratio: r["w5/w1"], weight: 0.15, nearest: f4.nearestFib, proximity: f4.score, contribution: f4.score * 0.15 },
    { component: "alternation", ratio: null, weight: 0.15, nearest: null, proximity: altBonus > 0 ? 1 : 0, contribution: altBonus },
  ];
  const score = Math.min(breakdown.reduce((s, b) => s + b.contribution, 0), 1) * 0.9;

  const nextDir = dir === "up" ? "down" : "up";
  const sgn = nextDir === "up" ? 1 : -1;
  const base = w[4].end.price;
  const total = Math.abs(w[4].end.price - w[0].start.price);
  const targets = [
    { factor: 0.382, prob: 0.20, src: "0.382 retrace" },
    { factor: 0.5,   prob: 0.25, src: "0.5 retrace" },
    { factor: 0.618, prob: 0.35, src: "0.618 retrace" },
    { factor: 0.786, prob: 0.20, src: "0.786 retrace" },
  ].map(t => ({
    level: base + sgn * total * t.factor,
    probability: t.prob, source: t.src,
    distancePct: (base + sgn * total * t.factor - price) / price * 100,
  }));

  return acc(name, {
    hypothesis: `completed ${dir} 5-wave impulse · correction starting`,
    nextWave: "A", nextDirection: nextDir, pattern: "impulse",
    currentPrice: price, targets,
    invalidation: w[4].end.price,
    invalidationReason: `price makes new ${dir === "up" ? "high" : "low"} beyond wave 5`,
    confidence: score, completedWaves: w, ratios: r,
    timeBars: [Math.floor((w[4].end.idx - w[0].start.idx) * 0.3),
               Math.floor((w[4].end.idx - w[0].start.idx) * 0.8)],
  }, breakdown);
}

function hInWave5(pivots, price) {
  const name = "in wave 5";
  if (pivots.length < 5) return rej(name, `need 5 pivots, have ${pivots.length}`);
  const seg = pivots.slice(-5);
  const dir = seg[1].price > seg[0].price ? "up" : "down";
  if (!alternating(seg, dir)) return rej(name, "pivots not alternating for this direction");

  const w = [];
  for (let i = 0; i < 4; i++) w.push(buildWave(seg[i], seg[i + 1], String(i + 1)));
  if (w[1].length >= w[0].length) return rej(name, `w2/w1 = ${(w[1].length/w[0].length).toFixed(2)} ≥ 1.0`);
  if (dir === "up" && w[3].end.price <= w[0].end.price) return rej(name, "w4 overlaps w1");
  if (dir === "down" && w[3].end.price >= w[0].end.price) return rej(name, "w4 overlaps w1");
  if (w[2].length < w[0].length * 0.5) return rej(name, `w3 too short (${(w[2].length/w[0].length).toFixed(2)} < 0.5·w1)`);

  const r = {
    "w2/w1": w[1].length / w[0].length,
    "w3/w1": w[2].length / w[0].length,
    "w4/w3": w[3].length / w[2].length,
  };
  const f1 = fibProximity(r["w2/w1"], FIB.w2);
  const f2 = fibProximity(r["w3/w1"], FIB.w3);
  const f3 = fibProximity(r["w4/w3"], FIB.w4);

  const breakdown = [
    { component: "w2/w1", ratio: r["w2/w1"], weight: 0.30, nearest: f1.nearestFib, proximity: f1.score, contribution: f1.score * 0.30 },
    { component: "w3/w1", ratio: r["w3/w1"], weight: 0.40, nearest: f2.nearestFib, proximity: f2.score, contribution: f2.score * 0.40 },
    { component: "w4/w3", ratio: r["w4/w3"], weight: 0.30, nearest: f3.nearestFib, proximity: f3.score, contribution: f3.score * 0.30 },
  ];
  const s = breakdown.reduce((sum, b) => sum + b.contribution, 0);

  const sgn = dir === "up" ? 1 : -1;
  const base = w[3].end.price;
  const w1len = w[0].length;
  const d03 = Math.abs(w[2].end.price - w[0].start.price);

  const targets = [
    { level: base + sgn * w1len * 0.618, probability: 0.20, source: "w5 = 0.618·w1" },
    { level: base + sgn * w1len * 1.0,   probability: 0.35, source: "w5 = w1 (equality)" },
    { level: base + sgn * w1len * 1.618, probability: 0.15, source: "w5 = 1.618·w1" },
    { level: base + sgn * d03 * 0.618,   probability: 0.30, source: "w5 = 0.618·(0→3)" },
  ].map(t => ({ ...t, distancePct: (t.level - price) / price * 100 }))
   .sort((a, b) => b.probability - a.probability);

  return acc(name, {
    hypothesis: `in wave 5 of ${dir} impulse`,
    nextWave: "5", nextDirection: dir, pattern: "impulse",
    currentPrice: price, targets,
    invalidation: w[3].end.price,
    invalidationReason: "price breaks below wave 4 end (structure invalid)",
    confidence: s, completedWaves: w, ratios: r,
    timeBars: [Math.floor(Math.min(w[0].bars, w[2].bars) * 0.618),
               Math.floor(Math.max(w[0].bars, w[2].bars) * 1.382)],
  }, breakdown);
}

function hInWave4(pivots, price) {
  const name = "in wave 4";
  if (pivots.length < 4) return rej(name, `need 4 pivots, have ${pivots.length}`);
  const seg = pivots.slice(-4);
  const dir = seg[1].price > seg[0].price ? "up" : "down";
  if (!alternating(seg, dir)) return rej(name, "pivots not alternating");

  const w1 = buildWave(seg[0], seg[1], "1");
  const w2 = buildWave(seg[1], seg[2], "2");
  const w3 = buildWave(seg[2], seg[3], "3");
  if (w2.length >= w1.length) return rej(name, "w2 ≥ w1");
  if (dir === "up" && w3.end.price <= w1.end.price) return rej(name, "w3 didn't exceed w1");
  if (dir === "down" && w3.end.price >= w1.end.price) return rej(name, "w3 didn't exceed w1");
  if (w3.length < w1.length * 0.8) return rej(name, `w3/w1 = ${(w3.length/w1.length).toFixed(2)} < 0.8`);

  const r = { "w2/w1": w2.length / w1.length, "w3/w1": w3.length / w1.length };
  const f1 = fibProximity(r["w2/w1"], FIB.w2);
  const f2 = fibProximity(r["w3/w1"], FIB.w3);
  const breakdown = [
    { component: "w2/w1", ratio: r["w2/w1"], weight: 0.4, nearest: f1.nearestFib, proximity: f1.score, contribution: f1.score * 0.4 },
    { component: "w3/w1", ratio: r["w3/w1"], weight: 0.6, nearest: f2.nearestFib, proximity: f2.score, contribution: f2.score * 0.6 },
  ];
  const s = breakdown.reduce((sum, b) => sum + b.contribution, 0);

  const nextDir = dir === "up" ? "down" : "up";
  const sgn = nextDir === "up" ? 1 : -1;
  const base = w3.end.price;

  const targets = [
    { factor: 0.236, prob: 0.20, src: "w4 = 0.236·w3 (shallow)" },
    { factor: 0.382, prob: 0.45, src: "w4 = 0.382·w3 (typical)" },
    { factor: 0.5,   prob: 0.25, src: "w4 = 0.5·w3" },
    { factor: 0.618, prob: 0.10, src: "w4 = 0.618·w3 (deep)" },
  ].map(t => {
    const level = base + sgn * w3.length * t.factor;
    return { level, probability: t.prob, source: t.src,
             distancePct: (level - price) / price * 100 };
  });

  return acc(name, {
    hypothesis: `in wave 4 of ${dir} impulse`,
    nextWave: "4", nextDirection: nextDir, pattern: "impulse",
    currentPrice: price, targets,
    invalidation: w1.end.price,
    invalidationReason: "price enters wave 1 territory (strict impulse breaks)",
    confidence: s, completedWaves: [w1, w2, w3], ratios: r,
    timeBars: [Math.floor(w3.bars * 0.3), Math.floor(w3.bars * 1.0)],
  }, breakdown);
}

function hInWave3(pivots, price) {
  const name = "in wave 3";
  if (pivots.length < 3) return rej(name, `need 3 pivots, have ${pivots.length}`);
  const seg = pivots.slice(-3);
  const dir = seg[1].price > seg[0].price ? "up" : "down";
  if (!alternating(seg, dir)) return rej(name, "pivots not alternating");

  const w1 = buildWave(seg[0], seg[1], "1");
  const w2 = buildWave(seg[1], seg[2], "2");
  if (w2.length >= w1.length) return rej(name, `w2/w1 = ${(w2.length/w1.length).toFixed(2)} ≥ 1.0`);

  const r = { "w2/w1": w2.length / w1.length };
  const f1 = fibProximity(r["w2/w1"], FIB.w2);
  const breakdown = [
    { component: "w2/w1", ratio: r["w2/w1"], weight: 0.75, nearest: f1.nearestFib, proximity: f1.score, contribution: f1.score * 0.75 },
  ];
  const s = breakdown.reduce((sum, b) => sum + b.contribution, 0);

  const sgn = dir === "up" ? 1 : -1;
  const base = w2.end.price;

  const targets = [
    { factor: 1.0,   prob: 0.10, src: "w3 = w1 (min)" },
    { factor: 1.272, prob: 0.20, src: "w3 = 1.272·w1" },
    { factor: 1.618, prob: 0.40, src: "w3 = 1.618·w1 (typical)" },
    { factor: 2.0,   prob: 0.20, src: "w3 = 2.0·w1" },
    { factor: 2.618, prob: 0.10, src: "w3 = 2.618·w1" },
  ].map(t => {
    const level = base + sgn * w1.length * t.factor;
    return { level, probability: t.prob, source: t.src,
             distancePct: (level - price) / price * 100 };
  });

  return acc(name, {
    hypothesis: `in wave 3 of ${dir} impulse`,
    nextWave: "3", nextDirection: dir, pattern: "impulse",
    currentPrice: price, targets,
    invalidation: seg[0].price,
    invalidationReason: "price exceeds wave 1 start (wave 2 > 100%)",
    confidence: s, completedWaves: [w1, w2], ratios: r,
    timeBars: [w1.bars, Math.floor(w1.bars * 2.618)],
  }, breakdown);
}

function hInWaveC(pivots, price) {
  const name = "in wave C";
  if (pivots.length < 3) return rej(name, `need 3 pivots, have ${pivots.length}`);
  const seg = pivots.slice(-3);
  const dirA = seg[1].price > seg[0].price ? "up" : "down";
  if (!alternating(seg, dirA)) return rej(name, "pivots not alternating");

  const wa = buildWave(seg[0], seg[1], "A");
  const wb = buildWave(seg[1], seg[2], "B");
  const rb = wa.length ? wb.length / wa.length : 0;
  if (rb < 0.3) return rej(name, `wB/wA = ${rb.toFixed(2)} < 0.3 (too shallow)`);
  if (rb > 1.4) return rej(name, `wB/wA = ${rb.toFixed(2)} > 1.4 (too deep)`);

  const r = { "wB/wA": rb };
  const f1 = fibProximity(rb, FIB.wB);
  const breakdown = [
    { component: "wB/wA", ratio: rb, weight: 0.55, nearest: f1.nearestFib, proximity: f1.score, contribution: f1.score * 0.55 },
  ];
  const s = breakdown.reduce((sum, b) => sum + b.contribution, 0);

  const sgn = dirA === "up" ? 1 : -1;
  const base = wb.end.price;

  const targets = [
    { factor: 0.618, prob: 0.20, src: "wC = 0.618·wA" },
    { factor: 1.0,   prob: 0.45, src: "wC = wA (equality)" },
    { factor: 1.272, prob: 0.20, src: "wC = 1.272·wA" },
    { factor: 1.618, prob: 0.15, src: "wC = 1.618·wA" },
  ].map(t => {
    const level = base + sgn * wa.length * t.factor;
    return { level, probability: t.prob, source: t.src,
             distancePct: (level - price) / price * 100 };
  });

  return acc(name, {
    hypothesis: `in wave C of ${dirA === "up" ? "bullish" : "bearish"} correction`,
    nextWave: "C", nextDirection: dirA, pattern: rb < 0.9 ? "zigzag" : "flat",
    currentPrice: price, targets,
    invalidation: base + sgn * wa.length * 2.618,
    invalidationReason: "wC exceeds 2.618·wA",
    confidence: s, completedWaves: [wa, wb], ratios: r,
    timeBars: [Math.floor(wa.bars * 0.618), Math.floor(wa.bars * 1.618)],
  }, breakdown);
}

function analyze(pivots, currentPrice, minConf) {
  const builders = [hCompletedImpulse, hInWave5, hInWave4, hInWave3, hInWaveC];
  const allAttempts = [];
  const seen = new Set();

  for (const cutoff of [0, 1]) {
    const working = cutoff ? pivots.slice(0, -cutoff) : pivots;
    for (const b of builders) {
      let result;
      if (working.length < 2) {
        result = { name: b.name, attempted: false, accepted: false, reason: "no pivots" };
      } else {
        result = b(working, currentPrice);
      }
      result.cutoff = cutoff;
      if (result.accepted) {
        const id = `${result.prediction.hypothesis}|${result.prediction.nextWave}`;
        if (seen.has(id)) {
          result.accepted = false; result.reason = "duplicate of earlier match"; result.filtered = true;
        } else {
          seen.add(id);
          if (cutoff) result.prediction.confidence *= 0.85;
          if (result.prediction.confidence < minConf) result.filteredByConfidence = true;
        }
      }
      allAttempts.push(result);
    }
  }

  const accepted = allAttempts
    .filter(a => a.accepted && !a.filteredByConfidence)
    .map(a => a.prediction)
    .sort((a, b) => b.confidence - a.confidence);

  return { accepted, attempts: allAttempts };
}

// ===========================================================================
// Dashboard
// ===========================================================================
export default function ElliottWaveDashboard() {
  const [priceData] = useState(() => generatePriceData());
  const [zigzag, setZigzag] = useState(0.018);
  const [minConf, setMinConf] = useState(0.18);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [hoveredTarget, setHoveredTarget] = useState(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugSection, setDebugSection] = useState("attempts");

  const { pivots, zigzagTrace } = useMemo(() => {
    const trace = [];
    const piv = zigzagPivots(priceData, zigzag, trace);
    return { pivots: piv, zigzagTrace: trace };
  }, [priceData, zigzag]);

  const currentPrice = priceData[priceData.length - 1].close;
  const { accepted: predictions, attempts } = useMemo(
    () => analyze(pivots, currentPrice, minConf),
    [pivots, currentPrice, minConf]
  );

  const selected = predictions[selectedIdx] || null;
  const projectionBars = 50;

  const chartData = useMemo(() => {
    const base = priceData.map(d => ({ idx: d.idx, close: d.close }));
    const lastIdx = priceData[priceData.length - 1].idx;
    for (let i = 1; i <= projectionBars; i++) base.push({ idx: lastIdx + i, close: null });
    return base;
  }, [priceData]);

  const priceMin = Math.min(...priceData.map(d => d.low)) * 0.99;
  const priceMax = Math.max(...priceData.map(d => d.high)) * 1.06;

  const projectedPaths = useMemo(() => {
    if (!selected) return [];
    const lastIdx = priceData[priceData.length - 1].idx;
    const avgBars = selected.timeBars
      ? (selected.timeBars[0] + selected.timeBars[1]) / 2 : 20;
    return selected.targets.map((t, i) => ({
      ...t, idx: i,
      data: [
        { idx: lastIdx, y: currentPrice },
        { idx: Math.min(lastIdx + Math.floor(avgBars), lastIdx + projectionBars), y: t.level },
      ],
    }));
  }, [selected, currentPrice, priceData]);

  const stats = {
    accepted: attempts.filter(a => a.accepted && !a.filteredByConfidence).length,
    belowMin: attempts.filter(a => a.filteredByConfidence).length,
    rejected: attempts.filter(a => a.attempted && !a.accepted && !a.filtered).length,
    duplicate: attempts.filter(a => a.filtered).length,
  };

  return (
    <div className="min-h-screen bg-stone-950 text-stone-100 p-4 md:p-6"
         style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,600&family=JetBrains+Mono:wght@300;400;500;600&display=swap');
        .font-display { font-family: 'Fraunces', ui-serif, Georgia, serif; font-feature-settings: "ss01"; }
        .grain { background-image: radial-gradient(rgba(200,169,106,0.04) 1px, transparent 1px); background-size: 4px 4px; }
      `}</style>

      <div className="max-w-[1600px] mx-auto">
        <header className="border-b border-stone-800 pb-4 mb-5 flex items-end justify-between flex-wrap gap-4">
          <div>
            <div className="text-[10px] tracking-[0.3em] text-amber-500/70 uppercase mb-1.5">
              Predictor · Interactive Analysis
            </div>
            <h1 className="font-display text-3xl md:text-4xl font-light tracking-tight">
              Elliott Wave <span className="italic text-amber-500/90">Forecast</span>
            </h1>
          </div>
          <div className="text-xs text-stone-500 text-right">
            <div className="text-amber-500/80 text-sm">{currentPrice.toFixed(2)}</div>
            <div>XAU/USD · {priceData.length} bars · {pivots.length} pivots</div>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-8 space-y-4">
            <div className="bg-stone-900/50 border border-stone-800 p-4 grain">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Activity size={14} className="text-amber-500/80" />
                  <span className="text-xs uppercase tracking-wider text-stone-400">
                    Price Structure & Projected Targets
                  </span>
                </div>
                {selected && (
                  <div className="text-[10px] text-stone-500 uppercase">
                    {selected.hypothesis}
                  </div>
                )}
              </div>

              <div style={{ width: "100%", height: 440 }}>
                <ResponsiveContainer>
                  <LineChart data={chartData} margin={{ top: 10, right: 80, bottom: 20, left: 10 }}>
                    <CartesianGrid stroke="#292524" strokeDasharray="1 4" />
                    <XAxis dataKey="idx" stroke="#57534e"
                      tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
                    <YAxis domain={[priceMin, priceMax]} stroke="#57534e"
                      tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }}
                      tickFormatter={v => v.toFixed(0)} />
                    <Tooltip contentStyle={{
                      background: "#0c0a09", border: "1px solid #44403c",
                      fontFamily: "JetBrains Mono", fontSize: 11,
                    }} labelStyle={{ color: "#a8a29e" }}
                      formatter={v => v != null ? v.toFixed(2) : ""} />
                    <ReferenceArea x1={priceData.length - 1}
                      x2={priceData.length - 1 + projectionBars}
                      fill="#0c0a09" fillOpacity={0.5} />
                    <Line type="monotone" dataKey="close" stroke="#78716c"
                      strokeWidth={1} dot={false} isAnimationActive={false}
                      connectNulls={false} />

                    {selected && selected.completedWaves.map((w, i) => (
                      <ReferenceLine key={`wv-${i}`}
                        segment={[
                          { x: w.start.idx, y: w.start.price },
                          { x: w.end.idx, y: w.end.price },
                        ]}
                        stroke="#c8a96a" strokeWidth={1.5} strokeOpacity={0.9}
                        ifOverflow="extendDomain" />
                    ))}

                    {selected && (() => {
                      const ws = selected.completedWaves;
                      const pts = [
                        { idx: ws[0].start.idx, price: ws[0].start.price, label: "0" },
                        ...ws.map(w => ({ idx: w.end.idx, price: w.end.price, label: w.label })),
                      ];
                      return pts.map((pt, i) => (
                        <ReferenceDot key={`pd-${i}`} x={pt.idx} y={pt.price}
                          r={4} fill="#c8a96a" stroke="#1c1917" strokeWidth={2}
                          label={{
                            value: pt.label, position: "top",
                            fill: "#c8a96a", fontSize: 13,
                            fontFamily: "Fraunces", fontWeight: 600,
                          }} />
                      ));
                    })()}

                    <ReferenceDot x={priceData.length - 1} y={currentPrice}
                      r={5} fill="#fbbf24" stroke="#1c1917" strokeWidth={2}
                      ifOverflow="extendDomain" />

                    {selected && (
                      <ReferenceLine y={selected.invalidation}
                        stroke="#f43f5e" strokeWidth={1.2} strokeDasharray="6 3"
                        label={{
                          value: `✗ invalid ${selected.invalidation.toFixed(2)}`,
                          position: "right", fill: "#f43f5e", fontSize: 10,
                          fontFamily: "JetBrains Mono",
                        }} />
                    )}

                    {selected && projectedPaths.map((path, i) => {
                      const isHovered = hoveredTarget === i;
                      const opacity = hoveredTarget !== null
                        ? (isHovered ? 1 : 0.15) : 0.4 + path.probability * 0.6;
                      const color = selected.nextDirection === "up" ? "#10b981" : "#f43f5e";
                      return (
                        <ReferenceLine key={`pth-${i}`}
                          segment={path.data.map(p => ({ x: p.idx, y: p.y }))}
                          stroke={color}
                          strokeWidth={isHovered ? 2.5 : 1.2 + path.probability * 1.5}
                          strokeOpacity={opacity}
                          strokeDasharray={isHovered ? "0" : "3 3"}
                          ifOverflow="extendDomain"
                          label={{
                            value: `${path.level.toFixed(0)} · ${(path.probability * 100).toFixed(0)}%`,
                            position: "right", fill: color, fontSize: 10,
                            fontFamily: "JetBrains Mono", fillOpacity: opacity,
                          }} />
                      );
                    })}

                    {selected && projectedPaths.map((path, i) => {
                      const isHovered = hoveredTarget === i;
                      const color = selected.nextDirection === "up" ? "#10b981" : "#f43f5e";
                      return (
                        <ReferenceDot key={`td-${i}`}
                          x={path.data[1].idx} y={path.level}
                          r={isHovered ? 6 : 3 + path.probability * 3}
                          fill={color} fillOpacity={isHovered ? 1 : 0.7}
                          stroke="#0c0a09" strokeWidth={1.5}
                          ifOverflow="extendDomain" />
                      );
                    })}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="bg-stone-900/50 border border-stone-800 p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              <Slider label="ZigZag Threshold" value={zigzag}
                display={`${(zigzag * 100).toFixed(2)}%`}
                min={0.005} max={0.05} step={0.0025} onChange={setZigzag} />
              <Slider label="Min Confidence" value={minConf}
                display={minConf.toFixed(2)}
                min={0} max={0.6} step={0.02} onChange={setMinConf} />
            </div>
          </div>

          <div className="lg:col-span-4 space-y-4">
            <div className="bg-stone-900/50 border border-stone-800 p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="text-xs uppercase tracking-wider text-stone-400 flex items-center gap-2">
                  <Zap size={12} className="text-amber-500/80" />
                  Scenarios
                </div>
                <div className="text-[10px] text-stone-600">
                  {predictions.length} · click to explore
                </div>
              </div>

              {predictions.length === 0 ? (
                <div className="text-stone-500 text-xs py-4 text-center">
                  no scenarios — loosen parameters
                </div>
              ) : (
                <div className="space-y-1.5 max-h-[280px] overflow-y-auto pr-1">
                  {predictions.map((p, i) => {
                    const active = i === selectedIdx;
                    const topTarget = p.targets.reduce((a, b) => a.probability > b.probability ? a : b);
                    return (
                      <button key={i}
                        onClick={() => { setSelectedIdx(i); setHoveredTarget(null); }}
                        className={`w-full text-left px-3 py-2.5 border transition-all ${
                          active ? "border-amber-500/70 bg-amber-500/5"
                                 : "border-stone-800 hover:border-stone-700 hover:bg-stone-900/40"
                        }`}>
                        <div className="flex items-start justify-between gap-2 mb-1.5">
                          <div className="text-xs text-stone-200 flex items-center gap-1.5 leading-tight">
                            {p.nextDirection === "up"
                              ? <TrendingUp size={12} className="text-emerald-400 flex-shrink-0" />
                              : <TrendingDown size={12} className="text-rose-400 flex-shrink-0" />}
                            <span>{p.hypothesis}</span>
                          </div>
                          <span className="text-[10px] text-stone-500 flex-shrink-0">
                            {(p.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="h-1 bg-stone-800 overflow-hidden">
                          <div className="h-full bg-amber-500/80"
                            style={{ width: `${p.confidence * 100}%` }} />
                        </div>
                        <div className="flex items-center justify-between text-[10px] text-stone-500 mt-1">
                          <span>→ {topTarget.level.toFixed(0)} ({topTarget.distancePct >= 0 ? "+" : ""}{topTarget.distancePct.toFixed(1)}%)</span>
                          <span>wave {p.nextWave}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {selected && (
              <div className="bg-stone-900/50 border border-stone-800 p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="text-xs uppercase tracking-wider text-stone-400 flex items-center gap-2">
                    <TargetIcon size={12} className="text-amber-500/80" />
                    Targets
                  </div>
                  <div className="text-[10px] text-stone-600">hover to focus</div>
                </div>
                <div className="space-y-1.5 mb-4">
                  {selected.targets.map((t, i) => {
                    const isHovered = hoveredTarget === i;
                    const cl = selected.nextDirection === "up" ? "emerald" : "rose";
                    return (
                      <div key={i}
                        onMouseEnter={() => setHoveredTarget(i)}
                        onMouseLeave={() => setHoveredTarget(null)}
                        className={`px-2.5 py-2 border transition-all cursor-pointer ${
                          isHovered ? `border-${cl}-500/60 bg-${cl}-500/5`
                                    : "border-stone-800 hover:border-stone-700"
                        }`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[11px] text-stone-300">{t.source}</span>
                          <span className="text-[10px] text-amber-500/80">
                            {(t.probability * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[10px] font-mono">
                          <span className="text-stone-200">{t.level.toFixed(2)}</span>
                          <span className={t.distancePct >= 0 ? "text-emerald-400" : "text-rose-400"}>
                            {t.distancePct >= 0 ? "+" : ""}{t.distancePct.toFixed(2)}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="border-t border-stone-800 pt-3 space-y-1.5 text-[11px] font-mono">
                  <DetailRow label="Invalidation" value={selected.invalidation.toFixed(2)} color="rose" />
                  <DetailRow label="Reason" value={selected.invalidationReason}
                    valueClass="text-[10px] text-stone-400 text-right max-w-[65%]" />
                  <DetailRow label="R:R (best)" value={((() => {
                    const t = selected.targets.reduce((a, b) => a.probability > b.probability ? a : b);
                    const r = Math.abs(t.level - currentPrice);
                    const risk = Math.abs(currentPrice - selected.invalidation);
                    return risk > 0 ? (r / risk).toFixed(2) : "∞";
                  })())} />
                  {selected.timeBars && (
                    <DetailRow label="ETA" value={`${selected.timeBars[0]}–${selected.timeBars[1]} bars`} />
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ============================= DEBUG PANEL ============================= */}
        <div className="mt-5 bg-stone-900/50 border border-stone-800">
          <button
            onClick={() => setDebugOpen(!debugOpen)}
            className="w-full px-4 py-3 flex items-center justify-between hover:bg-stone-900/80 transition-colors"
          >
            <div className="flex items-center gap-3">
              <Bug size={14} className="text-amber-500/80" />
              <span className="text-xs uppercase tracking-wider text-stone-300">
                Debug Panel
              </span>
              <div className="flex items-center gap-2 text-[10px] text-stone-500">
                <StatChip color="emerald" label="accepted" value={stats.accepted} />
                <StatChip color="amber" label="below min" value={stats.belowMin} />
                <StatChip color="rose" label="rejected" value={stats.rejected} />
                <StatChip color="stone" label="duplicate" value={stats.duplicate} />
              </div>
            </div>
            {debugOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {debugOpen && (
            <div className="border-t border-stone-800">
              <div className="flex border-b border-stone-800 overflow-x-auto">
                {[
                  { k: "attempts",  l: "Hypothesis Trace" },
                  { k: "breakdown", l: "Score Breakdown" },
                  { k: "pivots",    l: "Pivots" },
                  { k: "zigzag",    l: "ZigZag Events" },
                  { k: "params",    l: "Params & State" },
                ].map(tab => (
                  <button key={tab.k}
                    onClick={() => setDebugSection(tab.k)}
                    className={`px-4 py-2 text-[11px] uppercase tracking-wider transition-colors whitespace-nowrap ${
                      debugSection === tab.k
                        ? "text-amber-500 border-b-2 border-amber-500/70 bg-amber-500/5"
                        : "text-stone-500 hover:text-stone-300"
                    }`}>
                    {tab.l}
                  </button>
                ))}
              </div>

              <div className="p-4 max-h-[420px] overflow-y-auto">
                {debugSection === "attempts" && <AttemptsPanel attempts={attempts} />}
                {debugSection === "breakdown" && <BreakdownPanel selected={selected} attempts={attempts} />}
                {debugSection === "pivots" && <PivotsPanel pivots={pivots} />}
                {debugSection === "zigzag" && <ZigZagPanel trace={zigzagTrace} />}
                {debugSection === "params" && (
                  <ParamsPanel priceData={priceData} zigzag={zigzag} minConf={minConf}
                    currentPrice={currentPrice} stats={stats} />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ===========================================================================
// Debug Sub-Panels
// ===========================================================================
function StatChip({ color, label, value }) {
  const bg = { emerald: "bg-emerald-500/10 text-emerald-400",
               amber: "bg-amber-500/10 text-amber-400",
               rose: "bg-rose-500/10 text-rose-400",
               stone: "bg-stone-700/30 text-stone-400" }[color];
  return (
    <div className={`px-1.5 py-0.5 ${bg}`}>
      {value} {label}
    </div>
  );
}

function AttemptsPanel({ attempts }) {
  return (
    <div className="space-y-1.5">
      <div className="text-[10px] text-stone-500 mb-2 leading-relaxed">
        Every hypothesis builder runs against 2 pivot variants — cutoff=0 treats the last pivot as a completed wave end,
        cutoff=1 treats it as ongoing (price still moving).
      </div>
      {attempts.map((a, i) => {
        const status = a.accepted && !a.filteredByConfidence ? "accepted"
                     : a.filteredByConfidence ? "below-min"
                     : a.filtered ? "duplicate" : "rejected";
        const colors = {
          "accepted":  { border: "border-emerald-500/30", bg: "bg-emerald-500/5", text: "text-emerald-400", icon: <CheckCircle2 size={11} /> },
          "below-min": { border: "border-amber-500/30",   bg: "bg-amber-500/5",   text: "text-amber-400",   icon: <XCircle size={11} /> },
          "duplicate": { border: "border-stone-700",      bg: "bg-stone-900/40",  text: "text-stone-500",   icon: <XCircle size={11} /> },
          "rejected":  { border: "border-rose-500/20",    bg: "bg-rose-500/[0.03]", text: "text-rose-400/80", icon: <XCircle size={11} /> },
        }[status];
        return (
          <div key={i} className={`px-3 py-1.5 border ${colors.border} ${colors.bg} text-[11px]`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={colors.text}>{colors.icon}</span>
                <span className="text-stone-200">{a.name}</span>
                <span className="text-[9px] text-stone-600 uppercase">cutoff {a.cutoff}</span>
              </div>
              <span className={`text-[10px] uppercase ${colors.text}`}>
                {status}
                {a.accepted && !a.filteredByConfidence && a.prediction && ` · ${(a.prediction.confidence * 100).toFixed(0)}%`}
                {a.filteredByConfidence && a.prediction && ` · ${(a.prediction.confidence * 100).toFixed(0)}%`}
              </span>
            </div>
            {(a.reason || a.filteredByConfidence) && (
              <div className="text-[10px] text-stone-500 ml-5 mt-0.5">
                {a.filteredByConfidence ? "confidence below threshold" : a.reason}
              </div>
            )}
            {a.accepted && !a.filteredByConfidence && a.prediction && (
              <div className="text-[10px] text-stone-400 ml-5 mt-0.5">
                → next wave {a.prediction.nextWave} ({a.prediction.nextDirection}) ·
                {" "}top target @ {a.prediction.targets.reduce((x, y) => x.probability > y.probability ? x : y).level.toFixed(2)}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function BreakdownPanel({ selected, attempts }) {
  if (!selected) {
    return <div className="text-stone-500 text-xs text-center py-4">select a scenario to see its score breakdown</div>;
  }
  const attempt = attempts.find(a => a.accepted && a.prediction === selected);
  if (!attempt || !attempt.scoreBreakdown) {
    return <div className="text-stone-500 text-xs text-center py-4">no breakdown available</div>;
  }
  const totalRaw = attempt.scoreBreakdown.reduce((s, b) => s + b.contribution, 0);

  return (
    <div>
      <div className="text-[10px] text-stone-500 mb-3 leading-relaxed">
        Score = Σ (weight × fib-proximity). Each row: measured ratio vs. nearest Fibonacci level, how close (proximity), and the contribution to the final score.
      </div>
      <div className="space-y-2">
        {attempt.scoreBreakdown.map((b, i) => {
          const pct = b.contribution / Math.max(totalRaw, 0.001) * 100;
          return (
            <div key={i} className="border border-stone-800 px-3 py-2">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[11px] text-stone-200">{b.component}</span>
                <span className="text-[10px] text-stone-500">
                  weight {(b.weight * 100).toFixed(0)}%
                </span>
              </div>
              <div className="grid grid-cols-4 gap-2 text-[10px] font-mono mb-1.5">
                <MetricCell label="measured" value={b.ratio !== null ? b.ratio.toFixed(3) : "—"} />
                <MetricCell label="nearest fib" value={b.nearest !== null ? b.nearest.toFixed(3) : "—"} />
                <MetricCell label="proximity" value={`${(b.proximity * 100).toFixed(0)}%`} />
                <MetricCell label="contribution" value={`+${(b.contribution * 100).toFixed(1)}`} highlight />
              </div>
              <div className="h-1 bg-stone-800 overflow-hidden">
                <div className="h-full bg-amber-500/70" style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
        <div className="border-t border-stone-700 pt-2 mt-2 flex items-center justify-between text-[11px]">
          <span className="text-stone-400">total confidence</span>
          <span className="text-amber-500 font-mono">{(selected.confidence * 100).toFixed(1)}%</span>
        </div>
      </div>
    </div>
  );
}

function MetricCell({ label, value, highlight }) {
  return (
    <div>
      <div className="text-stone-600">{label}</div>
      <div className={highlight ? "text-amber-500/90" : "text-stone-200"}>{value}</div>
    </div>
  );
}

function PivotsPanel({ pivots }) {
  return (
    <div>
      <div className="text-[10px] text-stone-500 mb-2">
        {pivots.length} pivots · alternating high/low by construction
      </div>
      {pivots.length === 0 ? (
        <div className="text-stone-500 text-xs text-center py-3">no pivots at this threshold</div>
      ) : (
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr className="text-stone-600 border-b border-stone-800">
              <th className="text-left py-1.5 pr-3 font-normal">#</th>
              <th className="text-left py-1.5 pr-3 font-normal">idx</th>
              <th className="text-left py-1.5 pr-3 font-normal">price</th>
              <th className="text-left py-1.5 pr-3 font-normal">kind</th>
              <th className="text-left py-1.5 pr-3 font-normal">Δ prev</th>
              <th className="text-left py-1.5 font-normal">bars</th>
            </tr>
          </thead>
          <tbody>
            {pivots.map((p, i) => {
              const prev = pivots[i - 1];
              const delta = prev ? (p.price - prev.price) / prev.price * 100 : 0;
              const bars = prev ? p.idx - prev.idx : 0;
              return (
                <tr key={i} className="border-b border-stone-900 hover:bg-stone-900/60">
                  <td className="py-1 pr-3 text-stone-600">{i.toString().padStart(2, "0")}</td>
                  <td className="py-1 pr-3 text-stone-300">{p.idx}</td>
                  <td className="py-1 pr-3 text-stone-200">{p.price.toFixed(2)}</td>
                  <td className={`py-1 pr-3 ${p.kind === "high" ? "text-rose-400/80" : "text-emerald-400/80"}`}>
                    {p.kind}
                  </td>
                  <td className={`py-1 pr-3 ${delta > 0 ? "text-emerald-400/60" : "text-rose-400/60"}`}>
                    {prev ? `${delta >= 0 ? "+" : ""}${delta.toFixed(2)}%` : "—"}
                  </td>
                  <td className="py-1 text-stone-500">{prev ? bars : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ZigZagPanel({ trace }) {
  return (
    <div>
      <div className="text-[10px] text-stone-500 mb-2 leading-relaxed">
        Raw events from the ZigZag scanner. Reversals happen when price moves against the current trend by ≥ threshold.
        The final pivot is tentative — price may still continue and invalidate it.
      </div>
      {trace.length === 0 ? (
        <div className="text-stone-500 text-xs text-center py-3">no trend established (threshold never breached)</div>
      ) : (
        <div className="space-y-1">
          {trace.map((ev, i) => {
            const col = ev.event.includes("up") ? "#10b981"
                      : ev.event.includes("down") ? "#f43f5e"
                      : "#f59e0b";
            return (
              <div key={i} className="flex items-center gap-3 text-[11px] font-mono px-2 py-1 border-l-2"
                   style={{ borderColor: col }}>
                <span className="text-stone-600 w-10">#{i.toString().padStart(2, "0")}</span>
                <span className="text-stone-400 w-14">idx {ev.idx}</span>
                <span className="w-36" style={{ color: col }}>{ev.event}</span>
                <span className="text-stone-300">@ {ev.price.toFixed(2)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ParamsPanel({ priceData, zigzag, minConf, currentPrice, stats }) {
  const prices = priceData.map(d => d.close);
  const returns = prices.slice(1).map((p, i) => (p - prices[i]) / prices[i]);
  const vol = Math.sqrt(returns.reduce((s, r) => s + r * r, 0) / returns.length);
  const priceMin = Math.min(...priceData.map(d => d.low));
  const priceMax = Math.max(...priceData.map(d => d.high));

  return (
    <div className="space-y-4 text-[11px] font-mono">
      <div>
        <div className="text-[10px] uppercase tracking-wider text-stone-500 mb-2">Runtime Parameters</div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1">
          <KVRow k="zigzag threshold" v={`${(zigzag * 100).toFixed(3)}%`} />
          <KVRow k="min confidence" v={minConf.toFixed(3)} />
          <KVRow k="cutoff variants" v="[0, 1]" />
          <KVRow k="fib tolerance" v="15%" />
        </div>
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-wider text-stone-500 mb-2">Data Properties</div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1">
          <KVRow k="bars" v={priceData.length} />
          <KVRow k="current price" v={currentPrice.toFixed(2)} />
          <KVRow k="min price" v={priceMin.toFixed(2)} />
          <KVRow k="max price" v={priceMax.toFixed(2)} />
          <KVRow k="range" v={`${((priceMax - priceMin) / priceMin * 100).toFixed(2)}%`} />
          <KVRow k="bar volatility σ" v={`${(vol * 100).toFixed(3)}%`} />
        </div>
        <div className="text-[10px] text-stone-500 mt-2 leading-relaxed">
          Tip: ZigZag threshold should be roughly 2–3σ of bar-to-bar volatility to catch meaningful swings
          without noise. Current bar σ suggests ~{(vol * 100 * 2.5).toFixed(2)}% as a reasonable start.
        </div>
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-wider text-stone-500 mb-2">Analysis Stats</div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1">
          <KVRow k="total hypothesis attempts" v={5 * 2} />
          <KVRow k="accepted" v={stats.accepted} />
          <KVRow k="below min confidence" v={stats.belowMin} />
          <KVRow k="rejected (rule fail)" v={stats.rejected} />
          <KVRow k="duplicate (filtered)" v={stats.duplicate} />
        </div>
      </div>
    </div>
  );
}

function KVRow({ k, v }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-stone-500">{k}</span>
      <span className="text-stone-200">{v}</span>
    </div>
  );
}

function Slider({ label, value, display, min, max, step, onChange }) {
  return (
    <div>
      <div className="flex justify-between items-baseline mb-1.5">
        <span className="text-xs text-stone-300">{label}</span>
        <span className="text-xs text-amber-500/80">{display}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="w-full h-1 bg-stone-800 rounded-full appearance-none cursor-pointer
                   [&::-webkit-slider-thumb]:appearance-none
                   [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3
                   [&::-webkit-slider-thumb]:bg-amber-500
                   [&::-webkit-slider-thumb]:rounded-full
                   [&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:h-3
                   [&::-moz-range-thumb]:bg-amber-500
                   [&::-moz-range-thumb]:rounded-full
                   [&::-moz-range-thumb]:border-0" />
    </div>
  );
}

function DetailRow({ label, value, color = "stone", valueClass = "text-stone-200" }) {
  return (
    <div className="flex items-center justify-between">
      <span className={color === "rose" ? "text-rose-400" : "text-stone-500"}>{label}</span>
      <span className={valueClass}>{value}</span>
    </div>
  );
}