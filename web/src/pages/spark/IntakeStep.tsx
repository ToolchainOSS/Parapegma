/** Intake step — one question at a time for conditions C & D */
import type { IntakeProfile } from "./sparkData";
import { buildIntakeQuestions } from "./sparkData";

interface IntakeStepProps {
    stepIndex: number; // 0–3
    profile: IntakeProfile;
    onAnswer: (field: keyof IntakeProfile, value: string) => void;
}

export function IntakeStep({ stepIndex, profile, onAnswer }: IntakeStepProps) {
    const questions = buildIntakeQuestions();
    const q = questions[stepIndex];
    if (!q) return null;

    return (
        <div className="space-y-4">
            <p className="text-xs font-semibold text-text-muted">
                Intake · {stepIndex + 1} of {questions.length}
            </p>

            <div className="rounded-[var(--radius-lg)] border border-border bg-surface shadow-[var(--shadow-sm)] p-5">
                {/* AI avatar row on first question */}
                {stepIndex === 0 && (
                    <div className="flex gap-3 mb-4">
                        <div
                            className="flex-none w-9 h-9 rounded-[10px] grid place-items-center text-white text-sm font-bold"
                            style={{ background: "conic-gradient(from 0deg, var(--sf-calm), var(--sf-science), var(--sf-calm))" }}
                            aria-hidden="true"
                        >
                            AI
                        </div>
                        <p className="text-sm text-text-muted self-center">
                            I'm your micro-coach. Let's find a tiny way to move that fits your day.
                        </p>
                    </div>
                )}

                <p className="font-semibold text-base text-text">{q.question}</p>
                <p className="text-sm text-text-muted mt-1 mb-3">{q.sub}</p>

                <div className="flex flex-col gap-2">
                    {q.options.map((opt) => {
                        const selected = profile[q.field] === opt.value;
                        return (
                            <button
                                key={opt.value}
                                type="button"
                                className="text-left border border-border rounded-xl px-4 py-3 text-sm font-medium transition-colors hover:border-text-subtle"
                                style={selected ? { background: "var(--text)", color: "var(--bg)", borderColor: "var(--text)" } : {}}
                                onClick={() => onAnswer(q.field, opt.value)}
                            >
                                {opt.label}
                            </button>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
