import React from "react";

export function LoopTimeline({ currentStage }: { currentStage?: string }) {
  const stages = [
    { id: "detect", label: "detect" },
    { id: "diagnose", label: "diagnose" },
    { id: "plan", label: "plan" },
    { id: "gate", label: "gate" },
    { id: "execute", label: "execute" },
    { id: "verify", label: "verify" },
    { id: "outcome", label: "done" },
  ];

  const getStageColor = (stage: string) => {
    const map: Record<string, string> = {
      detect: "var(--color-k-stage-detect)",
      diagnose: "var(--color-k-stage-diagnose)",
      plan: "var(--color-k-stage-detect)", // No specific plan color, fallback to detect or surface
      gate: "var(--color-k-stage-evidence)",
      execute: "var(--color-k-stage-execute)",
      verify: "var(--color-k-stage-verify)",
      outcome: "var(--color-k-stage-done)",
    };
    return map[stage] || "var(--color-k-surface-strong)";
  };

  return (
    <div className="flex gap-2 text-[10px] font-bold uppercase tracking-wider overflow-hidden">
      {stages.map((stage) => {
        const isActiveOrPast = true; // For now everything is colored, later we can highlight current
        const isDone = stage.id === "outcome";
        const bgColor = isActiveOrPast
          ? getStageColor(stage.id)
          : "var(--color-k-surface-strong)";
        const textColor = isDone
          ? "var(--color-k-on-primary)"
          : "var(--color-k-ink)";

        return (
          <div
            key={stage.id}
            style={{ backgroundColor: bgColor, color: textColor }}
            className={`px-3 py-1.5 rounded-full ${
              currentStage === stage.id ? "ring-2 ring-offset-2 ring-k-ink" : ""
            }`}
          >
            {stage.label}
          </div>
        );
      })}
    </div>
  );
}
