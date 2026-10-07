import type { UndoRecord } from "./types";

interface UndoStackTimelineProps {
  undoStack?: UndoRecord[];
  outcome?: string;
}

export function UndoStackTimeline({ undoStack, outcome }: UndoStackTimelineProps) {
  if (!undoStack || undoStack.length === 0) return null;

  // If outcome is ESCALATED or UNRECOVERABLE, it means the verification failed
  // and the system rolled back. If it's RESOLVED or MITIGATED, it stayed intact.
  const isRolledBack = outcome === "ESCALATED" || outcome === "UNRECOVERABLE";

  return (
    <div className="bg-k-surface p-5 rounded border border-k-hairline shadow-sm flex flex-col gap-4">
      <div className="flex items-center gap-2 text-k-ink border-b border-k-hairline pb-2">
        <h3 className="font-semibold text-[11px] uppercase tracking-wider text-k-muted">Undo Stack</h3>
      </div>
      
      <p className="text-xs text-k-muted">
        Records the inverse of every action taken. If verification fails, Kavach pops this stack to unwind.
      </p>

      <div className="flex flex-col mt-2">
        {undoStack.map((record, index) => {
          const isLast = index === undoStack.length - 1;
          
          return (
            <div key={index} className="flex gap-4">
              {/* Timeline spine */}
              <div className="flex flex-col items-center">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center border text-[10px] ${isRolledBack ? "bg-red-50 border-red-200 text-red-500" : "bg-green-50 border-green-200 text-green-500"}`}>
                  {isRolledBack ? "✕" : "✓"}
                </div>
                {!isLast && <div className="w-px h-full bg-k-hairline-strong my-1" />}
              </div>
              
              {/* Content */}
              <div className="flex flex-col pb-6 pt-0.5">
                <div className="text-sm font-medium text-k-ink">
                  {record.original_action.name}
                </div>
                <div className="text-xs text-k-muted mt-1 flex items-center gap-1.5">
                  <span className="font-mono bg-k-canvas px-1.5 py-0.5 rounded border border-k-hairline">
                    inverse: {record.inverse_action.name}
                  </span>
                </div>
                
                {isRolledBack && (
                  <div className="mt-2 text-xs text-red-600 bg-red-50 px-2 py-1 rounded border border-red-100 flex items-center gap-1 w-fit">
                    <span>↺ Unwound</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
        
        {isRolledBack && (
          <div className="flex gap-4 mt-2">
             <div className="flex flex-col items-center">
                <div className="w-5 h-5 rounded-full flex items-center justify-center bg-k-canvas border border-k-hairline text-k-muted text-[10px]">
                  ↓
                </div>
              </div>
              <div className="text-xs font-medium text-k-muted pt-0.5">
                System restored to initial state
              </div>
          </div>
        )}
      </div>
    </div>
  );
}
