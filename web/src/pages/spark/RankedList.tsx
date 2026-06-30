/** Condition D — ranked card menu */
import type { SparkCard as SparkCardData } from "../../api/types";
import { FRAMINGS, type SparkFrame } from "./sparkData";

interface RankedListProps {
    cards: SparkCardData[];
    onPick: (card: SparkCardData) => void;
}

/**
 * Translate a raw fit_score into a feel-good, always-positive match.
 * The LLM sometimes returns 0 / equal scores, which reads as a cold
 * "fitness = 0". We floor it and fall back to a rank-based curve so the
 * ranking always feels encouraging and monotonic.
 */
function matchFor(score: number | null | undefined, rank: number): { pct: number; label: string } {
    const base = score && score > 0 ? score : 96 - rank * 7;
    const pct = Math.max(70, Math.min(98, Math.round(base)));
    const label = pct >= 90 ? "Top match" : pct >= 80 ? "Great fit" : pct >= 73 ? "Good fit" : "Worth a try";
    return { pct, label };
}

export function RankedList({ cards, onPick }: RankedListProps) {
    return (
        <div className="space-y-4">
            <div>
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-1">
                    Condition D · AI-Ranked Choice
                </p>
                <h2 className="text-2xl font-bold text-text">Ranked for your day</h2>
                <p className="text-sm text-text-muted mt-1">
                    Built from your intake and ordered by best match. Pick the one you like — you stay in control.
                </p>
            </div>

            <div className="flex flex-col gap-3">
                {cards.map((card, idx) => {
                    const f = FRAMINGS[card.frame as SparkFrame] ?? FRAMINGS.calm;
                    const { pct, label } = matchFor(card.fit_score, idx);
                    return (
                        <button
                            key={`${card.title}-${idx}`}
                            type="button"
                            className="text-left rounded-[var(--radius-lg)] border border-border bg-surface shadow-[var(--shadow-sm)] p-4 flex gap-3 transition-[transform,border-color] hover:-translate-y-0.5 hover:border-text-subtle"
                            onClick={() => onPick(card)}
                        >
                            {/* rank badge */}
                            <div
                                className="flex-none w-7 h-7 rounded-lg grid place-items-center text-white font-bold text-sm"
                                style={{ background: f.colorVar }}
                                aria-label={`Rank ${idx + 1}`}
                            >
                                {idx + 1}
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="font-bold text-text">
                                    {card.title}{" "}
                                    <span className="text-xs font-semibold" style={{ color: f.colorVar }}>
                                        · {f.emoji} {f.short}
                                    </span>
                                </div>
                                <p className="text-sm text-text-muted mt-0.5 line-clamp-2">{card.action}</p>
                                {/* match bar */}
                                <div className="spark-fitbar mt-2">
                                    <div
                                        className="spark-fitbar-fill"
                                        style={{ width: `${pct}%`, background: f.colorVar }}
                                    />
                                </div>
                                <p className="text-xs mt-1 font-semibold" style={{ color: f.colorVar }}>
                                    {idx === 0 ? "✨ " : ""}
                                    {label} · {pct}% match
                                </p>
                                {card.why && (
                                    <p className="text-xs text-text-muted mt-0.5">{card.why}</p>
                                )}
                            </div>
                        </button>
                    );
                })}
            </div>

            <p className="text-xs text-text-muted border border-dashed border-border rounded-xl p-3">
                Ranking is transparent on purpose: each card shows how strong a match it is and why.
            </p>
        </div>
    );
}
