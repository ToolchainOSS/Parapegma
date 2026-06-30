import { ANCHORS, type IntakeProfile } from "./sparkData";

interface CueStepProps {
    profile: IntakeProfile;
    cue: string | null;
    reminder: string | null;
    confidence: number | null;
    onCue: (c: string) => void;
    onReminder: (r: string) => void;
    onConfidence: (v: number) => void;
}

const DEFAULT_CUES = [
    "After my next coffee",
    "Before a meeting",
    "Right after lunch",
    "When I feel stiff",
    "Mid-afternoon slump",
];

export function CueStep({ profile, cue, reminder, confidence, onCue, onReminder, onConfidence }: CueStepProps) {
    const anchorDef = profile.anchor ? ANCHORS.find((a) => a.k === profile.anchor) : null;
    const cues = anchorDef
        ? [`When I ${anchorDef.label.toLowerCase()}`, ...DEFAULT_CUES].slice(0, 5)
        : DEFAULT_CUES;

    return (
        <div className="space-y-4">
            <div>
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">
                    Make it stick
                </p>
                <h2 className="text-2xl font-bold text-text mt-1">When would you do this again?</h2>
            </div>

            {/* Cue selection */}
            <div className="rounded-[var(--radius-lg)] border border-border bg-surface p-4 space-y-2">
                <p className="text-sm font-semibold text-text">Pick a cue to repeat it</p>
                <div className="spark-chips">
                    {cues.map((c) => (
                        <button
                            key={c}
                            type="button"
                            className="spark-chip"
                            data-active={cue === c ? "true" : undefined}
                            onClick={() => onCue(c)}
                        >
                            {c}
                        </button>
                    ))}
                </div>
            </div>

            {/* Reminder */}
            <div className="rounded-[var(--radius-lg)] border border-border bg-surface p-4 space-y-2">
                <p className="text-sm font-semibold text-text">Send yourself a reminder?</p>
                <div className="spark-chips">
                    {[
                        { label: "📅 Add to calendar", k: "calendar" },
                        { label: "✉️ Email me", k: "email" },
                        { label: "Skip", k: "skip" },
                    ].map(({ label, k }) => (
                        <button
                            key={k}
                            type="button"
                            className="spark-chip"
                            data-active={reminder === k ? "true" : undefined}
                            onClick={() => onReminder(k)}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Confidence (shown once cue picked) */}
            {cue && (
                <div className="rounded-[var(--radius-lg)] border border-border bg-surface p-4 space-y-2">
                    <p className="text-sm font-semibold text-text">
                        How confident are you this fits your day?
                    </p>
                    <ScaleControl value={confidence} onPick={onConfidence} lo="Not at all" hi="Very" />
                </div>
            )}
        </div>
    );
}

function ScaleControl({
    value,
    onPick,
    lo,
    hi,
}: {
    value: number | null;
    onPick: (v: number) => void;
    lo: string;
    hi: string;
}) {
    return (
        <div>
            <div className="spark-scale">
                {[1, 2, 3, 4, 5].map((n) => (
                    <button
                        key={n}
                        type="button"
                        className="spark-scale-btn"
                        data-selected={value === n ? "true" : undefined}
                        onClick={() => onPick(n)}
                    >
                        {n}
                    </button>
                ))}
            </div>
            <div className="flex justify-between text-xs text-text-muted mt-1">
                <span>{lo}</span>
                <span>{hi}</span>
            </div>
        </div>
    );
}
