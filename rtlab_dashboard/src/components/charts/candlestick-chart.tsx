"use client";

import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type Time,
} from "lightweight-charts";

interface CandlePoint {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface MarkerPoint {
  time: string;
  text: string;
  position: "aboveBar" | "belowBar";
  color: string;
}

export function CandlestickChart({
  candles,
  markers = [],
}: {
  candles: CandlePoint[];
  markers?: MarkerPoint[];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      height: 320,
      layout: {
        background: { type: ColorType.Solid, color: "#020617" },
        textColor: "#94a3b8",
      },
      rightPriceScale: {
        borderColor: "#1e293b",
      },
      timeScale: {
        borderColor: "#1e293b",
        timeVisible: true,
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      crosshair: {
        vertLine: { color: "#22d3ee33" },
        horzLine: { color: "#22d3ee33" },
      },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderUpColor: "#10b981",
      borderDownColor: "#ef4444",
      wickUpColor: "#34d399",
      wickDownColor: "#f87171",
    });

    series.setData(
      candles.map((x) => ({
        time: x.time as Time,
        open: x.open,
        high: x.high,
        low: x.low,
        close: x.close,
      })),
    );

    if (markers.length) {
      createSeriesMarkers(
        series,
        markers.map((marker) => ({
          time: marker.time as Time,
          text: marker.text,
          position: marker.position,
          color: marker.color,
          shape: marker.position === "aboveBar" ? "arrowDown" : "arrowUp",
        })),
      );
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect?.width;
      if (width && chartRef.current) {
        chartRef.current.applyOptions({ width });
      }
    });

    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, markers]);

  return <div ref={containerRef} className="w-full overflow-hidden rounded-xl border border-slate-800" />;
}
