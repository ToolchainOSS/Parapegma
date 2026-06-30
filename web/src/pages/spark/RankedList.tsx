/** Condition D — ranked card menu */
import type { SparkCard as SparkCardData } from "../../api/types";
import { FRAMINGS, type SparkFrame } from "./sparkData";

interface RankedListProps {
    cards: SparkCardData[];
    onPick: (card: SparkCardData) => void;
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
                    Built from your intake and ordered by predicted fit. Pick the one you like — you stay in control.
                </p>
            </div>

            <div className="flex flex-col gap-3">
                {cards.map((card, idx) => {
                    const f = FRAMINGS[card.frame as SparkFrame] ?? FRAMINGS.calm;
                    const fit = card.fit_score ?? 0;
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
                                {/* fit bar */}
                                <div className="spark-fitbar mt-2">
                                    <div
                                        className="spark-fitbar-fill"
                                        style={{ width: `${fit}%`, background: f.colorVar }}
                                    />
                                </div>
                                <p className="text-xs text-text-muted mt-1 font-semibold">
                                    Predicted fit {fit}% · {card.why}
                                </p>
                            </div>
                        </button>
                    );
                })}
            </div>

            <p className="text-xs text-text-muted border border-dashed border-border rounded-xl p-3">
                Ranking is transparent on purpose: each card shows a predicted-fit score and a reason.
            </p>
        </div>
    );
}
