import type { SparkCard as SparkCardData } from "../../api/types";
import { FRAME_ORDER, FRAMINGS, type SparkFrame } from "./sparkData";
import { VoiceControl } from "./VoiceControl";

interface AdjustPanelProps {
    card: SparkCardData;
    /** Most recent resolved adjustment label (for "saved" visual), or null */
    lastAdjustment?: string | null;
    loading?: boolean;
    onAdjust: (text: string) => void;
    /** Switch the framing without changing the action */
    onFrameSwitch: (frame: SparkFrame) => void;
    onSave?: () => void;
    saved?: boolean;
}

const QUICK_CHIPS = [
    { label: "Make it easier", text: "make it easier" },
    { label: "More energetic", text: "more energetic" },
    { label: "Less awkward", text: "less awkward, something more subtle" },
    { label: "Give me another", text: "give me a different one" },
];

export function AdjustPanel({
    card,
    lastAdjustment,
    loading = false,
    onAdjust,
    onFrameSwitch,
    onSave,
    saved = false,
}: AdjustPanelProps) {
    const currentFrame = card.frame as SparkFrame;

    return (
        <div className="mt-4 border-t border-divider pt-4 space-y-4">
            {/* Quick chips */}
            <div>
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">
                    Adjust this Spark
                </p>
                <div className="spark-chips">
                    {QUICK_CHIPS.map((c) => (
                        <button
                            key={c.label}
                            type="button"
                            className="spark-chip"
                            disabled={loading}
                            onClick={() => onAdjust(c.text)}
                        >
                            {c.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Frame toggle */}
            <div>
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">
                    Switch the vibe (same action)
                </p>
                <div className="spark-chips">
                    {FRAME_ORDER.map((k) => {
                        const f = FRAMINGS[k];
                        return (
                            <button
                                key={k}
                                type="button"
                                className="spark-chip"
                                data-active={currentFrame === k ? "true" : undefined}
                                data-ghost={currentFrame !== k ? "true" : undefined}
                                disabled={loading}
                                onClick={() => onFrameSwitch(k)}
                            >
                                {f.emoji} {f.short}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Voice / type */}
            <div>
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">
                    Or tell it what to change
                </p>
                <VoiceControl
                    placeholder="Type or speak a change…"
                    hint={`Tap the mic or type — e.g. "make it easier", "I'm at a desk", "less awkward".`}
                    onText={onAdjust}
                />
                {lastAdjustment && (
                    <p className="mt-1.5 text-xs font-semibold" style={{ color: "var(--sf-calm)" }}>
                        Spark updated: "{lastAdjustment}"
                    </p>
                )}
            </div>

            {/* Save */}
            {onSave && (
                <button
                    type="button"
                    className="spark-chip text-sm"
                    data-active={saved ? "true" : undefined}
                    onClick={onSave}
                    aria-pressed={saved}
                >
                    {saved ? "★ Saved" : "☆ Save this Spark"}
                </button>
            )}
        </div>
    );
}
