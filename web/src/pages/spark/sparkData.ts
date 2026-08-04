/** Constants ported from the HTML prototype — single source of truth for the
 *  Spark React implementation. No business logic here, just typed data.
 */

export type SparkFrame = "calm" | "zoomies" | "silly" | "challenge" | "science";

export interface FramingDef {
    key: SparkFrame;
    label: string;
    short: string;
    emoji: string;
    /** CSS custom-property name resolving to the accent color, e.g. "var(--sf-calm)" */
    colorVar: string;
    tintVar: string;
    desc: string;
    reward: string;
}

export const FRAMINGS: Record<SparkFrame, FramingDef> = {
    calm: {
        key: "calm",
        label: "Calm me",
        short: "Calm",
        emoji: "🌿",
        colorVar: "var(--sf-calm)",
        tintVar: "var(--sf-calm-tint)",
        desc: "Slow it down and release tension.",
        reward: "A slower reset — notice your shoulders drop and your breath even out.",
    },
    zoomies: {
        key: "zoomies",
        label: "Give me zoomies",
        short: "Zoomies",
        emoji: "⚡",
        colorVar: "var(--sf-zoomies)",
        tintVar: "var(--sf-zoomies-tint)",
        desc: "A quick jolt of energy.",
        reward: "A quick jolt — get the blood moving and shake off the sluggish feeling.",
    },
    silly: {
        key: "silly",
        label: "Make it silly",
        short: "Silly",
        emoji: "🤪",
        colorVar: "var(--sf-silly)",
        tintVar: "var(--sf-silly-tint)",
        desc: "Permission to look a little ridiculous.",
        reward: "Permission to look a little ridiculous. A grin counts as a rep.",
    },
    challenge: {
        key: "challenge",
        label: "Challenge me",
        short: "Challenge",
        emoji: "🔥",
        colorVar: "var(--sf-challenge)",
        tintVar: "var(--sf-challenge-tint)",
        desc: "Push the pace and make it count.",
        reward: "Make it count — keep it crisp and see if you hold the pace all 60 seconds.",
    },
    science: {
        key: "science",
        label: "Give me the science",
        short: "Science",
        emoji: "🔬",
        colorVar: "var(--sf-science)",
        tintVar: "var(--sf-science-tint)",
        desc: "The why behind the move.",
        reward: "Short movement bursts boost circulation and help refocus attention.",
    },
};

export const FRAME_ORDER: SparkFrame[] = [
    "calm",
    "zoomies",
    "silly",
    "challenge",
    "science",
];

export interface AnchorDef {
    k: string;
    label: string;
    cue: string;
}

export const ANCHORS: AnchorDef[] = [
    { k: "coffee", label: "Make coffee or tea", cue: "right after your coffee or tea" },
    { k: "water", label: "Fill a water bottle or cup", cue: "each time you refill your water" },
    { k: "bathroom", label: "Take a bathroom break", cue: "after a bathroom break" },
    { k: "food", label: "Walk to get a meal", cue: "on the way to grab a meal" },
    { k: "work", label: "Start work or class", cue: "as you start work or class" },
    { k: "break", label: "Have a break between meetings", cue: "in the gap between meetings" },
    { k: "email", label: "Check email / Slack / Teams", cue: "before opening your inbox" },
];

export const TIMES = ["Morning", "Afternoon", "Evening", "A specific time"] as const;

/** The four study conditions */
export type SparkCondition = "A" | "B" | "C" | "D";

export interface ConditionDef {
    id: SparkCondition;
    name: string;
    what: string;
    tags: string[];
    letterBg: string; // inline bg color for the letter badge
}

export const CONDITIONS: ConditionDef[] = [
    {
        id: "A",
        name: "Random Spark",
        what: "You receive one randomly chosen Spark and act on it.",
        tags: ["No choice", "No intake"],
        letterBg: "#8A8F84",
    },
    {
        id: "B",
        name: "Spark Wheel",
        what: "You see one Spark from each of the five vibes and pick the one you like.",
        tags: ["Choice", "No intake"],
        letterBg: "var(--sf-challenge)",
    },
    {
        id: "C",
        name: "AI-Adapted Spark",
        what: "A short intake, then one Spark adapted to you.",
        tags: ["Intake", "AI adapts"],
        letterBg: "var(--sf-calm)",
    },
    {
        id: "D",
        name: "AI-Ranked Choice",
        what: "A short intake, then one Spark per vibe, ranked by predicted fit.",
        tags: ["Intake", "AI ranks", "Choice"],
        letterBg: "var(--sf-science)",
    },
];

/** Accent color for a condition (used by progress bar, home cards, badges). */
export function conditionAccent(id: SparkCondition): string {
    return CONDITIONS.find((c) => c.id === id)?.letterBg ?? "var(--text)";
}

/** Intake question definitions for conditions C & D.
 *
 *  The intake deliberately asks only about *circumstances* — when, what kind of
 *  move, what daily habit to attach it to. It never asks which vibe the
 *  participant wants: nobody can name that before seeing a Spark, and asking
 *  turned a guess into a hard constraint on everything they were then shown.
 *  Vibe is now revealed by which card they pick (`SparkCard.frame`).
 */
export interface IntakeQuestion {
    field: keyof IntakeProfile;
    question: string;
    sub: string;
    options: readonly { label: string; value: string }[];
}

/** Fixed question list — a constant, not a per-render rebuild. */
export const INTAKE_QUESTIONS: readonly IntakeQuestion[] = [
    {
        field: "anchor",
        question: "Which of these do you do every day?",
        sub: "We attach the move to something you already do, so it sticks.",
        options: ANCHORS.map((a) => ({ label: a.label, value: a.k })),
    },
    {
        field: "action",
        question: "Pick a move you'd actually try.",
        sub: "No wrong answer — we can tweak it later.",
        options: [
            { label: "Reach & Roll", value: "reach" },
            { label: "Quick March", value: "march" },
            { label: "Desk Unwind", value: "neck" },
            { label: "Steady Tree", value: "tree" },
            { label: "Calf Lifts", value: "calf" },
            { label: "Shake It Out", value: "shake" },
            { label: "Surprise me", value: "any" },
        ],
    },
    {
        field: "time",
        question: "When should we remind you?",
        sub: "Just a rough window is fine.",
        options: TIMES.map((t) => ({ label: t, value: t })),
    },
];

/** Build a context string from the intake profile to send to the LLM */
export function buildContextFromProfile(profile: IntakeProfile): string {
    const parts: string[] = [];
    if (profile.anchor) {
        const anchor = ANCHORS.find((a) => a.k === profile.anchor);
        if (anchor) parts.push(`anchor: ${anchor.cue}`);
    }
    if (profile.action && profile.action !== "any") parts.push(`preferred move: ${profile.action}`);
    if (profile.time) parts.push(`time: ${profile.time}`);
    return parts.join("; ");
}

/** Answers to {@link INTAKE_QUESTIONS}. No `frame`: the intake cannot state a
 *  vibe, so "profile claims a vibe the participant never saw" is unrepresentable. */
export interface IntakeProfile {
    anchor: string | null;
    action: string | null;
    time: string | null;
}

export function emptyProfile(): IntakeProfile {
    return { anchor: null, action: null, time: null };
}

/** Condition D's catalog: one adapted Spark per vibe, ranked against each other.
 *  This is the count requested; the server de-duplicates vibes and serves a
 *  shorter catalog rather than failing when the model returns fewer. */
export const D_CATALOG_SIZE = FRAME_ORDER.length;
