import { useState } from "react";
import { VoiceControl } from "./VoiceControl";

export interface FeedbackState {
    tried: number | null; // 0=Yes, 1=Partly, 2=Not now
    reason: string | null;
    tweak: string;
}

interface FeedbackStepProps {
    state: FeedbackState;
    onChange: (next: FeedbackState) => void;
    /** If true, shows richer explanation that feedback drives adaptation */
    rich?: boolean;
}

const YES_REASONS = ["Easy to start", "Felt good", "Fit the moment", "Liked the vibe"];
const NO_REASONS  = ["No time", "Felt awkward", "Wrong moment", "Didn't fit me"];

export function FeedbackStep({ state, onChange, rich = false }: FeedbackStepProps) {
    const [tweakSaved, setTweakSaved] = useState(false);

    return (
        <div className="space-y-4">
            <div>
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">
                    Quick feedback
                </p>
                <h2 className="text-2xl font-bold text-text mt-1">How did that go?</h2>
            </div>

            {/* Tried? */}
            <div className="rounded-[var(--radius-lg)] border border-border bg-surface p-4 space-y-3">
                <p className="text-sm font-semibold text-text">Did you get a chance to try it?</p>
                <div className="spark-chips">
                    {["Yes, did it", "Partly", "Not now"].map((lab, i) => (
                        <button
                            key={lab}
                            type="button"
                            className="spark-chip"
                            data-active={state.tried === i ? "true" : undefined}
                            onClick={() => onChange({ ...state, tried: i, reason: null })}
                        >
                            {lab}
                        </button>
                    ))}
                </div>
            </div>

            {/* Reason (follow-up) */}
            {state.tried !== null && (
                <div className="rounded-[var(--radius-lg)] border border-border bg-surface p-4 space-y-3">
                    <p className="text-sm font-semibold text-text">
                        {state.tried === 0 ? "What made it work?" : "What got in the way?"}
                    </p>
                    <div className="spark-chips">
                        {(state.tried === 0 ? YES_REASONS : NO_REASONS).map((lab) => (
                            <button
                                key={lab}
                                type="button"
                                className="spark-chip"
                                data-active={state.reason === lab ? "true" : undefined}
                                onClick={() => onChange({ ...state, reason: lab })}
                            >
                                {lab}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Tweak / voice */}
            <div className="rounded-[var(--radius-lg)] border border-border bg-surface p-4 space-y-2">
                <p className="text-sm font-semibold text-text">
                    {rich
                        ? "What should change so the next one fits better?"
                        : "Anything you'd change? (optional)"}
                </p>
                <VoiceControl
                    placeholder="Type or speak…"
                    hint="Type or tap the mic to say what to tweak, then Send — this is captured as feedback."
                    onText={(t) => {
                        onChange({ ...state, tweak: t });
                        setTweakSaved(true);
                    }}
                />
                {tweakSaved && (
                    <p className="text-xs font-semibold" style={{ color: "var(--sf-calm)" }}>
                        Feedback noted: "{state.tweak}"
                    </p>
                )}
                {rich && (
                    <p className="text-xs text-text-muted border border-dashed border-border rounded-xl p-2 mt-1">
                        In conditions C & D this feedback updates your profile, so the next Spark adapts.
                    </p>
                )}
            </div>
        </div>
    );
}
