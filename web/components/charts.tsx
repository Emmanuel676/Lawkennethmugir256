"use client";

import type { ReactNode } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import type { BandKey, LenderRow, StatusShare } from "@/lib/api";
import { int, pct } from "@/lib/format";

// Colours are CSS variables (globals.css), validated with the dataviz palette checker for both themes.
const BAND_COLOR: Record<BandKey, string> = {
  high: "var(--band-high)", medium: "var(--band-medium)", low: "var(--band-low)",
};
const AXIS = { stroke: "var(--line)", tick: { fill: "var(--muted)", fontSize: 12 } };
const AXIS_LABEL = { fill: "var(--muted)", fontSize: 12 };
const TOOLTIP_STYLE = {
  contentStyle: { background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, color: "var(--ink)" },
  labelStyle: { color: "var(--ink)", fontWeight: 600 },
  itemStyle: { color: "var(--ink-2)" },
  cursor: { fill: "var(--surface-2)" },
};

/** Every chart: a figure with an accessible description (alt text) and a visible caption. */
export function ChartFigure({ alt, caption, height, children }: {
  alt: string; caption?: ReactNode; height: number; children: ReactNode;
}) {
  return (
    <figure className="m-0 min-w-0">
      <div role="img" aria-label={alt} style={{ height }} className="w-full min-w-0">
        {children}
      </div>
      {caption && <figcaption className="mt-2 text-xs leading-relaxed text-muted">{caption}</figcaption>}
    </figure>
  );
}

export function BandChart({ bands }: { bands: { key: BandKey; label: string; borrowers: number; share: number }[] }) {
  const alt = `Bar chart of borrowers per risk band: ${bands
    .map((b) => `${b.label} ${int(b.borrowers)} (${pct(b.share)})`).join(", ")}.`;
  return (
    <ChartFigure alt={alt} height={280}
                 caption="Each bar is labelled with its band name and count, so the chart never relies on colour alone.">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={bands} margin={{ top: 24, right: 8, bottom: 24, left: 8 }} barCategoryGap="28%">
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey="label" {...AXIS} tickLine={false}
                 label={{ value: "Risk band", position: "insideBottom", offset: -14, ...AXIS_LABEL }} />
          <YAxis {...AXIS} tickLine={false} axisLine={false} tickFormatter={(v: number) => int(v)} width={56}
                 label={{ value: "Borrowers", angle: -90, position: "insideLeft", offset: 4, ...AXIS_LABEL,
                          style: { textAnchor: "middle" } }} />
          <Tooltip {...TOOLTIP_STYLE}
                   formatter={(value, _name, item) => [`${int(Number(value))} (${pct(item.payload.share)})`, "Borrowers"]} />
          <Bar dataKey="borrowers" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {bands.map((b) => <Cell key={b.key} fill={BAND_COLOR[b.key]} />)}
            <LabelList dataKey="borrowers" position="top" formatter={(v) => int(Number(v))}
                       style={{ fill: "var(--ink)", fontSize: 12, fontWeight: 600 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFigure>
  );
}

export function AgeingChart({ buckets }: { buckets: { bucket: string; loans: number; owed: { exact: string } }[] }) {
  const alt = `Bar chart of unpaid loans by days past due: ${buckets.map((b) => `${b.bucket} ${int(b.loans)}`).join(", ")}.`;
  return (
    <ChartFigure alt={alt} height={280} caption="'Current' means not yet due. The table below gives the amounts owed.">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={buckets} margin={{ top: 24, right: 8, bottom: 12, left: 8 }} barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey="bucket" {...AXIS} tickLine={false} interval={0} fontSize={11} angle={-28} textAnchor="end"
                 height={64} label={{ value: "Days past due", position: "insideBottom", offset: -6, ...AXIS_LABEL }} />
          <YAxis {...AXIS} tickLine={false} axisLine={false} tickFormatter={(v: number) => int(v)} width={56}
                 label={{ value: "Unpaid loans", angle: -90, position: "insideLeft", offset: 4, ...AXIS_LABEL,
                          style: { textAnchor: "middle" } }} />
          <Tooltip {...TOOLTIP_STYLE}
                   formatter={(value, _name, item) => [`${int(Number(value))} loans · ${item.payload.owed.exact}`, "Unpaid"]} />
          <Bar dataKey="loans" fill="var(--series)" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            <LabelList dataKey="loans" position="top" formatter={(v) => int(Number(v))}
                       style={{ fill: "var(--ink)", fontSize: 12, fontWeight: 600 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFigure>
  );
}

export function StatusChart({ statuses }: { statuses: StatusShare[] }) {
  const data = statuses.map((s) => ({ ...s, percent: Math.round(s.share * 1000) / 10 }));
  const alt = `Horizontal bar chart of loans by repayment status: ${statuses
    .map((s) => `${s.label} ${pct(s.share)}`).join(", ")}.`;
  return (
    <ChartFigure alt={alt} height={Math.max(240, data.length * 34 + 50)}
                 caption={<><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-amber align-middle" aria-hidden="true" />
                   Amber bars are the statuses in the follow-up list (not paying, overdue but paying). Teal bars are all the
                   others. Every bar carries its status name and share.</>}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 48, bottom: 22, left: 4 }} barCategoryGap="22%">
          <CartesianGrid horizontal={false} stroke="var(--grid)" />
          <XAxis type="number" {...AXIS} tickLine={false} unit="%" domain={[0, "auto"]}
                 label={{ value: "Share of all loans", position: "insideBottom", offset: -14, ...AXIS_LABEL }} />
          <YAxis type="category" dataKey="label" {...AXIS} tickLine={false} width={150} fontSize={12} />
          <Tooltip {...TOOLTIP_STYLE}
                   formatter={(value, _name, item) => [`${Number(value).toFixed(1)}% · ${int(item.payload.loans)} loans`, "Share"]} />
          <Bar dataKey="percent" radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {data.map((s) => <Cell key={s.key} fill={s.follow_up ? "var(--band-medium)" : "var(--series)"} />)}
            <LabelList dataKey="percent" position="right" formatter={(v) => `${Number(v).toFixed(1)}%`}
                       style={{ fill: "var(--ink)", fontSize: 12, fontWeight: 600 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFigure>
  );
}

interface IntervalBarProps {
  x?: number; y?: number; width?: number; height?: number;
  payload?: { share: number; low: number; high: number };
}

/** The share as a bar, with its confidence interval drawn as a thin line with end caps on top of it. */
function IntervalBar({ x = 0, y = 0, width = 0, height = 0, payload }: IntervalBarProps) {
  if (!payload || payload.share <= 0) return <g />;
  const perPoint = width / payload.share; // pixels per percentage point
  const lowX = x + payload.low * 100 * perPoint;
  const highX = x + payload.high * 100 * perPoint;
  const mid = y + height / 2;
  const r = Math.min(4, width / 2);
  return (
    <g>
      <path d={`M${x},${y} h${width - r} a${r},${r} 0 0 1 ${r},${r} v${height - 2 * r} a${r},${r} 0 0 1 -${r},${r} h-${width - r} Z`}
            fill="var(--series)" />
      <line x1={lowX} x2={highX} y1={mid} y2={mid} stroke="var(--interval)" strokeWidth={2} />
      <line x1={lowX} x2={lowX} y1={mid - 5} y2={mid + 5} stroke="var(--interval)" strokeWidth={2} />
      <line x1={highX} x2={highX} y1={mid - 5} y2={mid + 5} stroke="var(--interval)" strokeWidth={2} />
    </g>
  );
}

export function LenderIntervalChart({ lenders, confidence }: { lenders: LenderRow[]; confidence: number }) {
  const data = lenders.map((l) => ({
    name: l.name.replace(/ \(Demo\)$/, ""),
    share: Math.round(l.abusive_share * 1000) / 10,
    low: l.interval_low, high: l.interval_high, rank: l.rank,
  }));
  const level = `${Math.round(confidence * 100)}%`;
  const axisMax = Math.max(5, Math.ceil((Math.max(...lenders.map((l) => l.interval_high)) * 100) / 5) * 5);
  const alt = `Horizontal bar chart of the share of each ranked lender's messages labelled abusive, with ${level} confidence intervals. ${lenders
    .map((l) => `${l.rank}. ${l.name}: ${pct(l.abusive_share)} (${pct(l.interval_low, 0)} to ${pct(l.interval_high, 0)})`).join("; ")}.`;
  return (
    <ChartFigure alt={alt} height={Math.max(260, data.length * 32 + 50)}
                 caption={`The bar is the share; the thin line is its ${level} confidence interval. Lenders are ranked by the lower end of that line, so a small lender cannot top the list by luck.`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 22, left: 4 }} barCategoryGap="26%">
          <CartesianGrid horizontal={false} stroke="var(--grid)" />
          <XAxis type="number" {...AXIS} tickLine={false} unit="%" domain={[0, axisMax]}
                 label={{ value: "Share of messages labelled abusive", position: "insideBottom", offset: -14, ...AXIS_LABEL }} />
          <YAxis type="category" dataKey="name" {...AXIS} tickLine={false} width={140} fontSize={12} />
          <Tooltip {...TOOLTIP_STYLE}
                   formatter={(value, _name, item) => [
                     `${Number(value).toFixed(1)}% (interval ${pct(item.payload.low, 0)} to ${pct(item.payload.high, 0)})`,
                     "Labelled abusive"]} />
          <Bar dataKey="share" fill="var(--series)" isAnimationActive={false} shape={IntervalBar} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFigure>
  );
}

export function PointsChart({ points }: { points: { signal: string; points: number; max_points: number }[] }) {
  const data = points.map((p) => ({
    ...p, rest: Math.max(0, p.max_points - p.points), name: `${p.signal}: ${p.points.toFixed(1)} of ${p.max_points}`,
  }));
  const alt = `Score breakdown: ${points.map((p) => `${p.signal} ${p.points.toFixed(1)} of ${p.max_points} points`).join(", ")}.`;
  return (
    <ChartFigure alt={alt} height={Math.max(200, data.length * 36 + 40)}
                 caption="The filled part is the points scored; the pale part is the most that signal can add.">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 22, left: 4 }} barCategoryGap="28%">
          <XAxis type="number" {...AXIS} tickLine={false} domain={[0, "dataMax"]}
                 label={{ value: "Points", position: "insideBottom", offset: -14, ...AXIS_LABEL }} />
          <YAxis type="category" dataKey="name" {...AXIS} tickLine={false} width={210} fontSize={12} />
          <Tooltip {...TOOLTIP_STYLE}
                   formatter={(value, name, item) => name === "points"
                     ? [`${Number(value).toFixed(1)} of ${item.payload.max_points}`, "Points"] : [null, null]} />
          <Bar dataKey="points" stackId="p" fill="var(--series)" isAnimationActive={false} />
          <Bar dataKey="rest" stackId="p" fill="var(--grid)" radius={[0, 4, 4, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFigure>
  );
}
