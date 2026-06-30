import type { SparkCondition } from "./sparkData";

export interface RatingState {
    fit: number | null;
    clarity: number | null;
    willing: number | null;
}

interface ReflectStepProps {
    condition: SparkCondition;
    rating: RatingState;
    onChange: (next: RatingState) => void;
    onFinish: () => void;
    onGoto: (cond: SparkCondition) => void;
}

const ITEMS: { key: keyof RatingState; label: string; sub: string }[] = [
    { key: "fit",     label: "Perceived fit",    sub: "How well did this Spark fit you?" },
    { key: "clarity", label: "Action clarity",   sub: "How clear was what to do?" },
    { key: "willing", label: "Willingness to try", sub: "How willing are you to actually do it?" },
];

export function ReflectStep({ condition, rating, onChange, onFinish, onGoto }: ReflectStepProps) {
    const allRated = ITEMS.every((it) => rating[it.key] !== null);

    return (
        <div className="space-y-4">
            <div>
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">
                    Rate this experience
                </p>
                <h2 className="text-2xl font-bold text-text mt-1">
                    Before you go — Condition {condition}
                </h2>
            </div>

            {ITEMS.map(({ key, label, sub }) => (
                <div key={key} className="rounded-[var(--radius-lg)] border border-border bg-surface p-4 space-y-2">
                    <p className="text-sm font-semibold text-text">{label}</p>
                    <p className="text-xs text-text-muted">{sub}</p>
                    <div className="spark-scale">
                        {[1, 2, 3, 4, 5].map((n) => (
                            <button
                                key={n}
                                type="button"
                                className="spark-scale-btn"
                                data-selected={rating[key] === n ? "true" : undefined}
                                onClick={() => onChange({ ...rating, [key]: n })}
                            >
                                {n}
                            </button>
                        ))}
                    </div>
                    <div className="flex justify-between text-xs text-text-muted">
                        <span>Low</span>
                        <span>High</span>
                    </div>
                </div>
            ))}

            <button
                type="button"
                className={`w-full py-3 rounded-[var(--radius-lg)] font-bold text-base transition-opacity ${allRated ? "bg-text text-bg" : "bg-text/40 text-bg cursor-not-allowed"}`}
                disabled={!allRated}
                onClick={onFinish}
            >
                Finish Condition {condition}
            </button>

            {/* Quick jump to other conditions */}
            <div className="flex gap-2 flex-wrap">
                {(["A", "B", "C", "D"] as SparkCondition[])
                    .filter((c) => c !== condition)
                    .map((c) => (
                        <button
                            key={c}
                            type="button"
                            className="spark-chip"
                            onClick={() => onGoto(c)}
                        >
                            Go to {c}
                        </button>
                    ))}
            </div>
        </div>
    );
}
