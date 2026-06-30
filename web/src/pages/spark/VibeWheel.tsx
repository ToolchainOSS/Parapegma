/** Condition B — vibe picker wheel */
import { FRAME_ORDER, FRAMINGS, type SparkFrame } from "./sparkData";

interface VibeWheelProps {
    onPick: (frame: SparkFrame) => void;
}

export function VibeWheel({ onPick }: VibeWheelProps) {
    return (
        <div className="space-y-4">
            <div>
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-1">
                    Condition B · Spark Wheel
                </p>
                <h2 className="text-2xl font-bold text-text">Pick a vibe</h2>
                <p className="text-sm text-text-muted mt-1">
                    Choice without an intake. Pick how you want to feel, then choose a Spark from a short menu.
                </p>
            </div>
            <div className="spark-wheel">
                {FRAME_ORDER.map((k) => {
                    const f = FRAMINGS[k];
                    return (
                        <button
                            key={k}
                            type="button"
                            className="fam text-left rounded-[var(--radius-lg)] p-4 border border-border shadow-[var(--shadow-sm)] transition-transform hover:-translate-y-0.5"
                            style={{ background: f.tintVar }}
                            onClick={() => onPick(k)}
                        >
                            <span className="text-2xl" aria-hidden="true">{f.emoji}</span>
                            <div className="font-bold text-lg mt-1.5" style={{ color: f.colorVar }}>
                                {f.label}
                            </div>
                            <div className="text-sm mt-0.5 text-text-muted">{f.desc}</div>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
