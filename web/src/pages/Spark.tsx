/**
 * Spark — One-Minute Micro-Coach  (full prototype port)
 *
 * Four conditions (A/B/C/D) are reachable from a home grid and switchable
 * at any time via the top condition tabs. Each condition runs its own
 * multi-step state machine. Adjustments remix cumulatively on the prior card
 * via useSparkRemix — the card *evolves*, it doesn't reset.
 *
 * Visual design: scoped `.spark-zone` exception; framing palette + timer/mic
 * animation live in spark/spark.css; global tokens untouched.
 */
import { useState } from "react";
import { PageHeader } from "../components/ui/PageHeader";
import { Alert } from "../components/Alert";
import { AdjustPanel } from "./spark/AdjustPanel";
import { CueStep } from "./spark/CueStep";
import { FeedbackStep, type FeedbackState } from "./spark/FeedbackStep";
import { IntakeStep } from "./spark/IntakeStep";
import { RankedList } from "./spark/RankedList";
import { ReflectStep, type RatingState } from "./spark/ReflectStep";
import { SparkCard } from "./spark/SparkCard";
import { SparkThinking } from "./spark/SparkThinking";
import { SparkTimer } from "./spark/SparkTimer";
import { VibeWheel } from "./spark/VibeWheel";
import { useSparkRemix } from "./spark/useSparkRemix";
import {
    createSparkClientId,
    getSparkResearchIdentity,
    type SparkIdentityProvider,
} from "./spark/sparkResearchIdentity";
import { useSparkEventTracker } from "./spark/sparkTelemetry";
import {
    CONDITIONS,
    FRAME_ORDER,
    FRAMINGS,
    buildContextFromProfile,
    conditionAccent,
    emptyProfile,
    type IntakeProfile,
    type SparkCondition,
    type SparkFrame,
} from "./spark/sparkData";
import "./spark/spark.css";

// ---------------------------------------------------------------------------
// Flow progress — back affordance (mid-flow only) + animated step bar
// ---------------------------------------------------------------------------
interface FlowProgressProps {
    step: number;
    total: number;
    accent: string;
    onBack: () => void;
}
function FlowProgress({ step, total, accent, onBack }: FlowProgressProps) {
    const pct = Math.round(((step + 1) / total) * 100);
    return (
        <div
            className="spark-flowbar"
            style={{ ["--seg-accent" as string]: accent }}
            aria-label={`Step ${step + 1} of ${total}`}
        >
            {step > 0 && (
                <button
                    type="button"
                    className="spark-back-btn"
                    onClick={onBack}
                    aria-label="Previous step"
                >
                    <svg
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                    >
                        <path d="m15 18-6-6 6-6" />
                    </svg>
                </button>
            )}
            <div className="spark-progress">
                <div className="spark-progress-meta">
                    <span>
                        Step {step + 1} of {total}
                    </span>
                    <span>{pct}%</span>
                </div>
                <div className="spark-progress-track">
                    <div className="spark-progress-fill" style={{ width: `${pct}%` }} />
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Continue button
// ---------------------------------------------------------------------------
function ContinueBtn({
    label = "Continue",
    onClick,
    disabled = false,
}: {
    label?: string;
    onClick: () => void;
    disabled?: boolean;
}) {
    return (
        <div className="mt-5">
            <button
                type="button"
                disabled={disabled}
                className={`w-full py-3.5 rounded-[var(--radius-lg)] font-bold text-base transition-opacity ${disabled ? "bg-text/40 text-bg cursor-not-allowed" : "bg-text text-bg hover:opacity-90"}`}
                onClick={onClick}
            >
                {label}
            </button>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Home grid
// ---------------------------------------------------------------------------
function SparkHome({ onStart }: { onStart: (c: SparkCondition) => void }) {
    return (
        <div className="space-y-6">
            <div>
                <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">
                    One-minute movement micro-coach · research prototype
                </p>
                <h1 className="text-4xl font-bold text-text mt-2 leading-tight">
                    Four ways to deliver a one-minute Spark.
                </h1>
                <p className="text-sm text-text-muted mt-2 max-w-prose">
                    Same one-minute action, four designs for <strong>choice</strong> and{" "}
                    <strong>personalization</strong>. Step through each, adjust the Spark by tapping
                    or by voice — adjustments remix cumulatively, not single-shot.
                    Switch conditions anytime from the top bar.
                </p>
            </div>

            <div className="spark-cond-grid">
                {CONDITIONS.map((c) => (
                    <button
                        key={c.id}
                        type="button"
                        data-testid={`spark-cond-${c.id}`}
                        className="spark-home-card text-left bg-surface border border-border rounded-[var(--radius-lg)] p-5 shadow-[var(--shadow-sm)] flex flex-col gap-2 min-h-[160px]"
                        style={{ ["--seg-accent" as string]: c.letterBg }}
                        onClick={() => onStart(c.id)}
                    >
                        <div
                            className="w-9 h-9 rounded-[10px] grid place-items-center text-white text-sm font-bold shadow-[var(--shadow-xs)]"
                            style={{ background: c.letterBg }}
                        >
                            {c.id}
                        </div>
                        <div className="font-bold text-lg text-text">{c.name}</div>
                        <div className="text-sm text-text-muted">{c.what}</div>
                        <div className="flex gap-1.5 flex-wrap mt-auto">
                            {c.tags.map((t) => (
                                <span key={t} className="text-xs font-semibold px-2 py-0.5 rounded-full border border-border text-text-muted bg-surface-2">
                                    {t}
                                </span>
                            ))}
                        </div>
                    </button>
                ))}
            </div>

            <p className="text-xs text-text-muted border border-dashed border-border rounded-xl p-4">
                Every condition shares: a <strong>Spark card</strong>, a <strong>1-minute timer</strong>,
                an <strong>adjust panel</strong> (tap or voice-to-text), <strong>feedback</strong>,
                a <strong>cue + reminder</strong>, and a short <strong>rating</strong>.
                What changes is <strong>who chooses</strong> and <strong>how much the system personalizes</strong>.
            </p>

            <p className="text-xs text-text-muted border border-dashed border-border rounded-xl p-4">
                <strong>Research privacy:</strong> Spark works without an account. To link repeat visits,
                it uses a random study identifier stored only in this browser plus a browser fingerprint.
                Flow stores keyed, non-reversible versions—not the raw values. Clearing site data starts a
                new study identity.
            </p>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Condition A — Random Spark
// steps: 0 landing | 1 card+adjust | 2 timer | 3 feedback | 4 cue | 5 reflect
// ---------------------------------------------------------------------------
function ConditionA({
    onExit,
    onGoto,
    getIdentity,
}: {
    onExit: () => void;
    onGoto: (c: SparkCondition) => void;
    getIdentity: SparkIdentityProvider;
}) {
    const [step, setStep] = useState(0);
    const [flowId] = useState(createSparkClientId);
    const track = useSparkEventTracker({ condition: "A", flowId, getIdentity });
    const [spark, actions] = useSparkRemix({ flowId, getIdentity });
    const [feedback, setFeedback] = useState<FeedbackState>({ tried: null, reason: null, tweak: "" });
    const [cue, setCue] = useState<string | null>(null);
    const [reminder, setReminder] = useState<string | null>(null);
    const [confidence, setConfidence] = useState<number | null>(null);
    const [rating, setRating] = useState<RatingState>({ fit: null, clarity: null, willing: null });

    function back() {
        if (step === 0) { onExit(); return; }
        setStep((s) => s - 1);
    }

    return (
        <div>
            <FlowProgress step={step} total={6} accent={conditionAccent("A")} onBack={back} />
            {step === 0 && (
                <div className="space-y-4">
                    <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">Condition A · Random Spark</p>
                    <h2 className="text-2xl font-bold text-text">A Spark, sent to you</h2>
                    <p className="text-sm text-text-muted">
                        No menu, no questions. Tap once and we'll send one Spark for you to act on.
                        Tests whether simply delivering a short action is enough.
                    </p>
                    {spark.error && <Alert variant="error" data-testid="spark-error">{spark.error}</Alert>}
                    {spark.loading ? (
                        <SparkThinking />
                    ) : (
                        <ContinueBtn
                            label="Get my Spark"
                            disabled={spark.loading}
                            onClick={() => {
                                void actions.generate({ condition: "A" }).then(() => setStep(1));
                            }}
                        />
                    )}
                </div>
            )}
            {step === 1 && spark.card && (
                <div className="space-y-2">
                    <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">Your Spark</p>
                    <SparkCard card={spark.card} data-testid="spark-card" />
                    {/* Control group: no adjust/remix — the Spark is delivered as-is. */}
                    {spark.error && <Alert variant="error">{spark.error}</Alert>}
                    <ContinueBtn label="Start 1-minute timer" onClick={() => setStep(2)} />
                </div>
            )}
            {step === 2 && spark.card && (
                <SparkTimer
                    frame={(spark.card.frame as SparkFrame) ?? "calm"}
                    onDone={(completion) => {
                        track({ event_type: "timer_finished", completion });
                        setStep(3);
                    }}
                />
            )}
            {step === 3 && (
                <>
                    <FeedbackStep state={feedback} onChange={setFeedback} />
                    <ContinueBtn
                        label="Next"
                        disabled={feedback.tried === null}
                        onClick={() => {
                            if (feedback.tried !== null) {
                                track({
                                    event_type: "feedback_submitted",
                                    tried: feedback.tried,
                                    reason: feedback.reason,
                                    tweak: feedback.tweak,
                                });
                            }
                            setStep(4);
                        }}
                    />
                </>
            )}
            {step === 4 && (
                <>
                    <CueStep
                        profile={emptyProfile()}
                        cue={cue}
                        reminder={reminder}
                        confidence={confidence}
                        onCue={setCue}
                        onReminder={setReminder}
                        onConfidence={setConfidence}
                    />
                    <ContinueBtn
                        label="Next"
                        disabled={!cue}
                        onClick={() => {
                            if (cue) {
                                track({
                                    event_type: "cue_selected",
                                    cue,
                                    reminder: reminder as "calendar" | "email" | "skip" | null,
                                    confidence,
                                });
                            }
                            setStep(5);
                        }}
                    />
                </>
            )}
            {step === 5 && (
                <ReflectStep
                    condition="A"
                    rating={rating}
                    onChange={setRating}
                    onFinish={() => {
                        if (rating.fit && rating.clarity && rating.willing) {
                            track({
                                event_type: "condition_completed",
                                fit: rating.fit,
                                clarity: rating.clarity,
                                willing: rating.willing,
                            });
                        }
                        onExit();
                    }}
                    onGoto={onGoto}
                />
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Condition B — Spark Wheel
// steps: 0 wheel | 1 pick spark (mini-menu) | 2 card+adjust | 3 timer | 4 feedback | 5 cue | 6 reflect
// ---------------------------------------------------------------------------
function ConditionB({
    onExit,
    onGoto,
    getIdentity,
}: {
    onExit: () => void;
    onGoto: (c: SparkCondition) => void;
    getIdentity: SparkIdentityProvider;
}) {
    const [step, setStep] = useState(0);
    const [chosenFrame, setChosenFrame] = useState<SparkFrame | null>(null);
    const [flowId] = useState(createSparkClientId);
    const track = useSparkEventTracker({ condition: "B", flowId, getIdentity });
    const [spark, actions] = useSparkRemix({ flowId, getIdentity });
    const [feedback, setFeedback] = useState<FeedbackState>({ tried: null, reason: null, tweak: "" });
    const [cue, setCue] = useState<string | null>(null);
    const [reminder, setReminder] = useState<string | null>(null);
    const [confidence, setConfidence] = useState<number | null>(null);
    const [rating, setRating] = useState<RatingState>({ fit: null, clarity: null, willing: null });

    function back() {
        if (step === 0) { onExit(); return; }
        setStep((s) => s - 1);
    }

    return (
        <div>
            <FlowProgress step={step} total={7} accent={conditionAccent("B")} onBack={back} />
            {step === 0 && (
                <VibeWheel
                    onPick={(f) => {
                        // Clear any options/card cached from a previous topic pick — otherwise
                        // re-entering the wheel and picking again (same or different vibe)
                        // would show stale cards from the prior frame.
                        actions.reset();
                        track({ event_type: "frame_selected", frame: f });
                        setChosenFrame(f);
                        setStep(1);
                    }}
                />
            )}
            {step === 1 && chosenFrame && (
                <div className="space-y-4">
                    <div>
                        <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">
                            {FRAMINGS[chosenFrame].emoji} {FRAMINGS[chosenFrame].label} · Choose a Spark
                        </p>
                        <h2 className="text-2xl font-bold text-text mt-1">Which one fits right now?</h2>
                    </div>
                    {spark.error && <Alert variant="error">{spark.error}</Alert>}
                    {/* Show 3 options from LLM */}
                    {spark.cards.length > 0 ? (
                        <div className="flex flex-col gap-3">
                            {spark.cards.slice(0, 3).map((card, i) => {
                                const f = FRAMINGS[chosenFrame];
                                return (
                                    <button
                                        key={i}
                                        type="button"
                                        className="text-left rounded-[var(--radius-lg)] border border-border bg-surface shadow-[var(--shadow-sm)] p-4 flex gap-3 transition-[transform,border-color] hover:-translate-y-0.5 hover:border-text-subtle"
                                        onClick={() => {
                                            track({ event_type: "card_selected", rank: i + 1 });
                                            actions.selectCard(card);
                                            setStep(2);
                                        }}
                                    >
                                        <div className="w-7 h-7 rounded-lg grid place-items-center flex-none text-lg" style={{ background: f.tintVar }} aria-hidden="true">
                                            {f.emoji}
                                        </div>
                                        <div>
                                            <div className="font-bold text-text">{card.title}</div>
                                            <p className="text-sm text-text-muted mt-0.5 line-clamp-2">{card.action}</p>
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    ) : (
                        spark.loading ? (
                            <SparkThinking frame={chosenFrame} />
                        ) : (
                            <ContinueBtn
                                label="Load options"
                                disabled={spark.loading}
                                onClick={() => {
                                    void actions.generate({ condition: "B", frame: chosenFrame, count: 3 });
                                }}
                            />
                        )
                    )}
                </div>
            )}
            {step === 2 && spark.card && (
                <div className="space-y-2">
                    <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">Your Spark</p>
                    <SparkCard card={spark.card} data-testid="spark-card" />
                    {/* Control group: choice happens at the menu; no post-pick remix. */}
                    {spark.error && <Alert variant="error">{spark.error}</Alert>}
                    <ContinueBtn label="Start 1-minute timer" onClick={() => setStep(3)} />
                </div>
            )}
            {step === 3 && spark.card && (
                <SparkTimer
                    frame={(spark.card.frame as SparkFrame) ?? "calm"}
                    onDone={(completion) => {
                        track({ event_type: "timer_finished", completion });
                        setStep(4);
                    }}
                />
            )}
            {step === 4 && (
                <>
                    <FeedbackStep state={feedback} onChange={setFeedback} />
                    <ContinueBtn
                        label="Next"
                        disabled={feedback.tried === null}
                        onClick={() => {
                            if (feedback.tried !== null) {
                                track({
                                    event_type: "feedback_submitted",
                                    tried: feedback.tried,
                                    reason: feedback.reason,
                                    tweak: feedback.tweak,
                                });
                            }
                            setStep(5);
                        }}
                    />
                </>
            )}
            {step === 5 && (
                <>
                    <CueStep
                        profile={emptyProfile()}
                        cue={cue}
                        reminder={reminder}
                        confidence={confidence}
                        onCue={setCue}
                        onReminder={setReminder}
                        onConfidence={setConfidence}
                    />
                    <ContinueBtn
                        label="Next"
                        disabled={!cue}
                        onClick={() => {
                            if (cue) {
                                track({
                                    event_type: "cue_selected",
                                    cue,
                                    reminder: reminder as "calendar" | "email" | "skip" | null,
                                    confidence,
                                });
                            }
                            setStep(6);
                        }}
                    />
                </>
            )}
            {step === 6 && (
                <ReflectStep
                    condition="B"
                    rating={rating}
                    onChange={setRating}
                    onFinish={() => {
                        if (rating.fit && rating.clarity && rating.willing) {
                            track({
                                event_type: "condition_completed",
                                fit: rating.fit,
                                clarity: rating.clarity,
                                willing: rating.willing,
                            });
                        }
                        onExit();
                    }}
                    onGoto={onGoto}
                />
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Conditions C & D — adaptive (intake → 1 card / ranked list)
// ---------------------------------------------------------------------------
function ConditionAdaptive({
    condition,
    onExit,
    onGoto,
    getIdentity,
}: {
    condition: "C" | "D";
    onExit: () => void;
    onGoto: (c: SparkCondition) => void;
    getIdentity: SparkIdentityProvider;
}) {
    // Steps: 0-3 intake | 4 generation/selection | 5 card+adjust (D only) | timer | feedback | cue | reflect
    const intakeSteps = 4;
    const hasSelection = condition === "D";
    const timerStep   = hasSelection ? 6 : 5;
    const fbStep      = timerStep + 1;
    const cueStep     = fbStep + 1;
    const reflectStep = cueStep + 1;
    const totalSteps  = reflectStep + 1;

    const [step, setStep] = useState(0);
    const [profile, setProfile] = useState<IntakeProfile>(emptyProfile());
    const [flowId] = useState(createSparkClientId);
    const track = useSparkEventTracker({ condition, flowId, getIdentity });
    const [spark, actions] = useSparkRemix({ flowId, getIdentity });
    const [feedback, setFeedback] = useState<FeedbackState>({ tried: null, reason: null, tweak: "" });
    const [cue, setCue] = useState<string | null>(null);
    const [reminder, setReminder] = useState<string | null>(null);
    const [confidence, setConfidence] = useState<number | null>(null);
    const [rating, setRating] = useState<RatingState>({ fit: null, clarity: null, willing: null });

    function back() {
        if (step === 0) { onExit(); return; }
        setStep((s) => s - 1);
    }

    function handleIntakeAnswer(field: keyof IntakeProfile, value: string) {
        track({
            event_type: "intake_answered",
            field,
            value,
        });
        const next = { ...profile, [field]: value };
        setProfile(next);
        if (step < intakeSteps - 1) {
            setStep(step + 1);
        } else {
            // Last intake question answered — advance to the generation step
            // immediately so the thinking/loading animation is visible while the
            // (up-to-5s) LLM call is in flight, then fire the request.
            setStep(intakeSteps);
            const ctx = buildContextFromProfile(next);
            void actions.generate({
                condition,
                frame: next.frame,
                context: ctx || undefined,
                count: condition === "D" ? 4 : 1,
            });
        }
    }

    const condLabel = condition === "C" ? "AI-Adapted Spark" : "AI-Ranked Choice";

    return (
        <div>
            <FlowProgress step={step} total={totalSteps} accent={conditionAccent(condition)} onBack={back} />

            {/* Intake steps 0–3 */}
            {step < intakeSteps && (
                <IntakeStep stepIndex={step} profile={profile} onAnswer={handleIntakeAnswer} />
            )}

            {/* Generation / selection step */}
            {step === intakeSteps && (
                <div className="space-y-4">
                    {/* Full-page loader only for the INITIAL generation (no card/list
                        yet). Remixes keep the card mounted and use the compact
                        in-AdjustPanel loader, matching condition D. */}
                    {spark.loading && !spark.card && spark.cards.length === 0 && (
                        <SparkThinking
                            frame={profile.frame ?? undefined}
                            phrases={
                                condition === "D"
                                    ? [
                                          "Lining up your best matches…",
                                          "Ranking a few contenders…",
                                          "Weighing what fits your day…",
                                          "Sorting Sparks by good-fit energy…",
                                          "Reading your intake like tea leaves…",
                                      ]
                                    : [
                                          "Tailoring a Spark just for you…",
                                          "Folding your intake into the mix…",
                                          "Tuning it to your vibe…",
                                          "Shaping the perfect one-minute move…",
                                          "Adding a personal touch…",
                                      ]
                            }
                        />
                    )}
                    {spark.error && <Alert variant="error">{spark.error}</Alert>}

                    {condition === "C" && spark.card && (
                        <div className="space-y-2">
                            <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">
                                Condition C · {condLabel}
                            </p>
                            <h2 className="text-2xl font-bold text-text">Here's your adapted Spark</h2>
                            <SparkCard card={spark.card} showWhy tuned data-testid="spark-card" />
                            <AdjustPanel
                                card={spark.card}
                                lastAdjustment={spark.lastAdjustment}
                                loading={spark.loading}
                                onAdjust={actions.adjust}
                                onFrameSwitch={actions.switchFrame}
                            />
                            <ContinueBtn label="Start 1-minute timer" onClick={() => setStep(timerStep)} />
                        </div>
                    )}

                    {!spark.loading && condition === "D" && spark.cards.length > 0 && (
                        <div className="space-y-2">
                            <RankedList
                                cards={spark.cards}
                                onPick={(card, rank) => {
                                    track({ event_type: "card_selected", rank });
                                    actions.selectCard(card);
                                    setStep(5); // card+adjust preview step
                                }}
                            />
                        </div>
                    )}
                </div>
            )}

            {/* D only: card+adjust preview after selection */}
            {hasSelection && step === 5 && spark.card && (
                <div className="space-y-2">
                    <p className="text-xs font-semibold text-text-muted uppercase tracking-wide">Your pick</p>
                    <SparkCard card={spark.card} showWhy tuned data-testid="spark-card" />
                    <AdjustPanel
                        card={spark.card}
                        lastAdjustment={spark.lastAdjustment}
                        loading={spark.loading}
                        onAdjust={actions.adjust}
                        onFrameSwitch={actions.switchFrame}
                    />
                    {spark.error && <Alert variant="error">{spark.error}</Alert>}
                    <ContinueBtn label="Start 1-minute timer" onClick={() => setStep(timerStep)} />
                </div>
            )}

            {step === timerStep && spark.card && (
                <SparkTimer
                    frame={(spark.card.frame as SparkFrame) ?? "calm"}
                    onDone={(completion) => {
                        track({ event_type: "timer_finished", completion });
                        setStep(fbStep);
                    }}
                />
            )}

            {step === fbStep && (
                <>
                    <FeedbackStep state={feedback} onChange={setFeedback} rich />
                    <div className="flex gap-3 mt-4 flex-wrap">
                        <button
                            type="button"
                            className="spark-chip"
                            onClick={() => {
                                if (feedback.tried !== null) {
                                    track({
                                        event_type: "feedback_submitted",
                                        tried: feedback.tried,
                                        reason: feedback.reason,
                                        tweak: feedback.tweak,
                                    });
                                }
                                // Remix from feedback
                                if (feedback.tweak) actions.adjust(feedback.tweak);
                                else actions.adjust(feedback.reason ?? "different");
                                setStep(intakeSteps);
                            }}
                        >
                            ↻ Adapt Spark from feedback
                        </button>
                        <button
                            type="button"
                            disabled={feedback.tried === null}
                            className={`spark-chip ${feedback.tried === null ? "opacity-40" : ""}`}
                            onClick={() => {
                                if (feedback.tried !== null) {
                                    track({
                                        event_type: "feedback_submitted",
                                        tried: feedback.tried,
                                        reason: feedback.reason,
                                        tweak: feedback.tweak,
                                    });
                                }
                                setStep(cueStep);
                            }}
                        >
                            Next
                        </button>
                    </div>
                </>
            )}

            {step === cueStep && (
                <>
                    <CueStep
                        profile={profile}
                        cue={cue}
                        reminder={reminder}
                        confidence={confidence}
                        onCue={setCue}
                        onReminder={setReminder}
                        onConfidence={setConfidence}
                    />
                    <ContinueBtn
                        label="Next"
                        disabled={!cue}
                        onClick={() => {
                            if (cue) {
                                track({
                                    event_type: "cue_selected",
                                    cue,
                                    reminder: reminder as "calendar" | "email" | "skip" | null,
                                    confidence,
                                });
                            }
                            setStep(reflectStep);
                        }}
                    />
                </>
            )}

            {step === reflectStep && (
                <ReflectStep
                    condition={condition}
                    rating={rating}
                    onChange={setRating}
                    onFinish={() => {
                        if (rating.fit && rating.clarity && rating.willing) {
                            track({
                                event_type: "condition_completed",
                                fit: rating.fit,
                                clarity: rating.clarity,
                                willing: rating.willing,
                            });
                        }
                        onExit();
                    }}
                    onGoto={onGoto}
                />
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Condition tabs
// ---------------------------------------------------------------------------
function ConditionTabs({
    active,
    onSelect,
}: {
    active: SparkCondition | null;
    onSelect: (c: SparkCondition | null) => void;
}) {
    return (
        <div className="flex justify-center mb-6">
            <div className="spark-segmented" role="tablist" aria-label="Spark conditions">
                <button
                    type="button"
                    role="tab"
                    aria-selected={active === null}
                    className="spark-seg"
                    data-active={active === null ? "true" : undefined}
                    style={{ ["--seg-accent" as string]: "var(--text)" }}
                    onClick={() => onSelect(null)}
                >
                    Home
                </button>
                {FRAME_ORDER.length > 0 &&
                    (["A", "B", "C", "D"] as SparkCondition[]).map((c) => (
                        <button
                            key={c}
                            type="button"
                            role="tab"
                            aria-selected={active === c}
                            className="spark-seg"
                            data-active={active === c ? "true" : undefined}
                            data-testid={`spark-tab-${c}`}
                            style={{ ["--seg-accent" as string]: conditionAccent(c) }}
                            onClick={() => onSelect(c)}
                        >
                            {c}
                        </button>
                    ))}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Root export
// ---------------------------------------------------------------------------
export function Spark() {
    const [condition, setCondition] = useState<SparkCondition | null>(null);
    const getIdentity = getSparkResearchIdentity;

    function goto(c: SparkCondition | null) {
        setCondition(c);
        window.scrollTo({ top: 0, behavior: "smooth" });
    }

    return (
        <div className="flex flex-col flex-1 bg-bg">
            <PageHeader title="Spark" data-testid="spark-heading" />
            <div
                className="spark-zone px-4 py-5 max-w-3xl mx-auto w-full"
                data-testid="spark-page"
            >
                <ConditionTabs active={condition} onSelect={goto} />

                {condition === null && <SparkHome onStart={(c) => goto(c)} />}
                {condition === "A" && (
                    <ConditionA
                        onExit={() => goto(null)}
                        onGoto={(c) => goto(c)}
                        getIdentity={getIdentity}
                    />
                )}
                {condition === "B" && (
                    <ConditionB
                        onExit={() => goto(null)}
                        onGoto={(c) => goto(c)}
                        getIdentity={getIdentity}
                    />
                )}
                {condition === "C" && (
                    <ConditionAdaptive
                        condition="C"
                        onExit={() => goto(null)}
                        onGoto={(c) => goto(c)}
                        getIdentity={getIdentity}
                    />
                )}
                {condition === "D" && (
                    <ConditionAdaptive
                        condition="D"
                        onExit={() => goto(null)}
                        onGoto={(c) => goto(c)}
                        getIdentity={getIdentity}
                    />
                )}
            </div>
        </div>
    );
}

