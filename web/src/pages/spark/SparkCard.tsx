import type { SparkCard as SparkCardData } from "../../api/types";
import { FRAMINGS, type SparkFrame } from "./sparkData";

interface SparkCardProps {
    card: SparkCardData;
    showWhy?: boolean;
    /** Show a warm "tuned to you" badge (conditions C & D). */
    tuned?: boolean;
    /** Extra className for the outer wrapper */
    className?: string;
    "data-testid"?: string;
}

export function SparkCard({
    card,
    showWhy = true,
    tuned = false,
    className = "",
    ...rest
}: SparkCardProps) {
    const frame = card.frame as SparkFrame;
    const f = FRAMINGS[frame] ?? FRAMINGS.calm;

    return (
        <div
            className={`rounded-[var(--sf-radius,20px)] overflow-hidden border border-border shadow-[var(--shadow-sm)] bg-surface ${className}`}
            {...rest}
        >
            {/* colored band */}
            <div
                className="h-2 w-full"
                style={{ background: f.colorVar }}
                aria-hidden="true"
            />
            <div className="p-5">
                {/* frame chip + tuned badge */}
                <div className="flex flex-wrap items-center gap-2 mb-3">
                    <span
                        className="spark-framechip text-xs font-semibold rounded-full px-3 py-1 inline-flex items-center gap-1.5"
                        style={{ background: f.tintVar, color: f.colorVar }}
                    >
                        <span aria-hidden="true">{f.emoji}</span> {f.label}
                    </span>
                    {tuned && (
                        <span
                            className="spark-match"
                            style={{ background: f.tintVar, color: f.colorVar }}
                        >
                            <span aria-hidden="true">✨</span> Tuned to your vibe
                        </span>
                    )}
                </div>

                <h3 className="text-xl font-bold text-text leading-tight mt-1">{card.title}</h3>
                <p className="mt-3 text-base text-text leading-relaxed">{card.action}</p>

                {/* meta pills */}
                <div className="flex flex-wrap gap-2 mt-3">
                    <span className="text-xs text-text-muted border border-border rounded-lg px-2.5 py-1">
                        ⏱ 1 minute
                    </span>
                    <span className="text-xs text-text-muted border border-border rounded-lg px-2.5 py-1">
                        ✓ Done when timer hits 0
                    </span>
                </div>

                {/* reward */}
                <div
                    className="mt-3 text-sm text-text pl-3 border-l-4 py-2 rounded-r-lg bg-surface-2"
                    style={{ borderColor: f.colorVar }}
                >
                    {card.reward}
                </div>

                {/* why (expandable) */}
                {showWhy && card.why && (
                    <details className="mt-3 group">
                        <summary
                            className="text-sm font-semibold cursor-pointer list-none"
                            style={{ color: f.colorVar }}
                        >
                            Why this Spark?
                        </summary>
                        <p className="mt-2 text-sm text-text-muted">{card.why}</p>
                    </details>
                )}
            </div>
        </div>
    );
}
