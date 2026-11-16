"use client";

// The chart library (Recharts) is loaded only by pages that draw a chart, after the page itself has rendered
// (Phase 14), so the landing page and first visits stay light. Each chart shows a skeleton of its own size meanwhile.
import dynamic from "next/dynamic";

function placeholder(height: number) {
  return function ChartLoading() {
    return <div style={{ height }} className="skeleton w-full" aria-hidden="true" />;
  };
}

export const BandChart = dynamic(() => import("./charts").then((m) => m.BandChart), { ssr: false, loading: placeholder(280) });
export const AgeingChart = dynamic(() => import("./charts").then((m) => m.AgeingChart), { ssr: false, loading: placeholder(280) });
export const StatusChart = dynamic(() => import("./charts").then((m) => m.StatusChart), { ssr: false, loading: placeholder(320) });
export const LenderIntervalChart = dynamic(() => import("./charts").then((m) => m.LenderIntervalChart), { ssr: false, loading: placeholder(420) });
export const PointsChart = dynamic(() => import("./charts").then((m) => m.PointsChart), { ssr: false, loading: placeholder(220) });
