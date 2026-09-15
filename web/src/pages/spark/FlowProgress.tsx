/** Flow progress — back affordance plus an animated step bar. */
import { IconButton } from "../../components/ui";

interface FlowProgressProps {
    step: number;
    total: number;
    /** Tailwind background class for the fill, from `conditionAccent`. */
    accent: string;
    onBack: () => void;
}

export function FlowProgress({ step, total, accent, onBack }: FlowProgressProps) {
    const pct = Math.round(((step + 1) / total) * 100);
    return (
        <div className="flex items-center gap-3 mb-6" aria-label={`Step ${step + 1} of ${total}`}>
            {/* Always present: at step 0 this is the only way back out. */}
            <IconButton
                label={step > 0 ? "Previous step" : "Back to the start"}
                onClick={onBack}
                className="shrink-0 border border-border"
            >
                <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                >
                    <path d="m15 18-6-6 6-6" />
                </svg>
            </IconButton>
            <div className="flex-1">
                <div className="flex justify-between text-xs text-text-subtle mb-1.5">
                    <span>
                        Step {step + 1} of {total}
                    </span>
                    <span>{pct}%</span>
                </div>
                <div className="h-1 rounded-pill bg-surface-3 overflow-hidden">
                    <div
                        className={`h-full rounded-pill transition-[width] duration-500 ease-[var(--ease-out)] ${accent}`}
                        style={{ width: `${pct}%` }}
                    />
                </div>
            </div>
        </div>
    );
}
