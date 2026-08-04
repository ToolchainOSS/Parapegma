/** Condition B — five concrete Sparks, one per vibe.
 *
 *  Replaces the old vibe wheel. The wheel asked participants to name a vibe
 *  before they had seen a single Spark, which is a choice most people cannot
 *  make — the labels alone ("Challenge me") do not say what you would actually
 *  be doing. Here every vibe is represented by one randomly drawn Spark from the
 *  curated library, so the choice is made over the intervention itself and the
 *  vibe is whatever the chosen card happens to be.
 */
import type { SparkCard as SparkCardData } from "../../api/types";
import { FRAMINGS, type SparkFrame } from "./sparkData";

interface SparkSamplerProps {
    cards: readonly SparkCardData[];
    /** 1-based position within the sampler, for telemetry. */
    onPick: (card: SparkCardData, rank: number) => void;
}

export function SparkSampler({ cards, onPick }: SparkSamplerProps) {
    return (
        <div className="space-y-4">
            <div>
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-1">
                    Condition B · Spark Wheel
                </p>
                <h2 className="text-2xl font-bold text-text">Which one would you actually do?</h2>
                <p className="text-sm text-text-muted mt-1">
                    Choice without an intake. One Spark from each of the five vibes, drawn at
                    random — no questions, and nothing to guess at before you have seen them.
                </p>
            </div>

            <div className="flex flex-col gap-3">
                {cards.map((card, i) => {
                    const f = FRAMINGS[card.frame as SparkFrame] ?? FRAMINGS.calm;
                    return (
                        <button
                            key={`${card.frame}-${card.title}`}
                            type="button"
                            data-testid={`spark-sample-${card.frame}`}
                            className="text-left rounded-[var(--radius-lg)] border border-border bg-surface shadow-[var(--shadow-sm)] overflow-hidden transition-[transform,border-color] hover:-translate-y-0.5 hover:border-text-subtle"
                            onClick={() => onPick(card, i + 1)}
                        >
                            <div className="h-1.5 w-full" style={{ background: f.colorVar }} aria-hidden="true" />
                            <div className="p-4">
                                <span
                                    className="spark-framechip text-xs font-semibold rounded-full px-3 py-1 inline-flex items-center gap-1.5"
                                    style={{ background: f.tintVar, color: f.colorVar }}
                                >
                                    <span aria-hidden="true">{f.emoji}</span> {f.label}
                                </span>
                                <div className="font-bold text-text mt-2">{card.title}</div>
                                <p className="text-sm text-text-muted mt-1">{card.action}</p>
                                <p className="text-xs text-text-muted mt-2 italic">{card.reward}</p>
                            </div>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
