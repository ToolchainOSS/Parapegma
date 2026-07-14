/**
 * useSparkRemix — adaptive remix hook.
 *
 * State model
 * -----------
 *   card              The card currently shown to the user (null = not yet generated).
 *   adjustmentHistory Ordered list of all adjustments applied to the current card
 *                     (oldest → newest), capped at 20. On first generate it's [].
 *                     On each adjust, the new text is appended and the endpoint is
 *                     called with base_card=card + adjustment_history=fullHistory.
 *
 * Contract sent to /spark/generate
 * ---------------------------------
 *   First generate:  no base_card, adjustment_history = []
 *   Each adjust:     base_card = current card, adjustment_history = accumulated stack
 *
 * This is the "client-carried history → stateless endpoint" pattern — the backend
 * stays stateless, the frontend owns the remix chain.
 */
import { useCallback, useRef, useState } from "react";
import api from "../../api/client";
import type { SparkCard, SparkGenerateResponse } from "../../api/types";
import type { SparkCondition, SparkFrame } from "./sparkData";
import {
    createSparkClientId,
    type SparkIdentityProvider,
} from "./sparkResearchIdentity";

const MAX_HISTORY = 20;

export interface SparkRemixState {
    card: SparkCard | null;
    cards: SparkCard[];           // For condition D: the full ranked list
    adjustmentHistory: string[];
    lastAdjustment: string | null;
    loading: boolean;
    error: string | null;
}

export interface SparkRemixActions {
    /** First generate: call with context, optional frame & count. */
    generate: (opts: GenerateOpts) => Promise<void>;
    /** Remix: append text to history and re-request with base_card (fire-and-forget from state updater). */
    adjust: (text: string) => void;
    /** Switch only the frame preference and re-request (fire-and-forget from state updater). */
    switchFrame: (frame: SparkFrame) => void;
    /** Select a card from a ranked list (condition D) as the active card. */
    selectCard: (card: SparkCard) => void;
    /** Reset the whole session (used when starting a new condition flow). */
    reset: () => void;
}

interface GenerateOpts {
    condition: SparkCondition;
    frame?: SparkFrame | null;
    context?: string;
    count?: number;
}

interface SparkRemixResearchContext {
    flowId: string;
    getIdentity: SparkIdentityProvider;
}

function initialState(): SparkRemixState {
    return {
        card: null,
        cards: [],
        adjustmentHistory: [],
        lastAdjustment: null,
        loading: false,
        error: null,
    };
}

export function useSparkRemix(
    research: SparkRemixResearchContext,
): [SparkRemixState, SparkRemixActions] {
    const [state, setState] = useState<SparkRemixState>(initialState);
    const { flowId, getIdentity } = research;
    // Keep opts from the last generate call so adjust can re-use condition/frame/context
    const optsRef = useRef<GenerateOpts>({ condition: "A" });

    const callApi = useCallback(
        async (opts: GenerateOpts, baseCard: SparkCard | null, history: string[]) => {
            setState((s) => ({ ...s, loading: true, error: null }));
            try {
                const identity = await getIdentity();
                const { data, error: apiError } = await api.POST("/spark/generate", {
                    body: {
                        identity,
                        flow_id: flowId,
                        client_event_id: createSparkClientId(),
                        condition: opts.condition,
                        frame_preference: opts.frame ?? undefined,
                        context: opts.context ?? undefined,
                        base_card: baseCard ?? undefined,
                        adjustment_history: history,
                        count: opts.count ?? (opts.condition === "D" ? 4 : opts.condition === "A" || opts.condition === "C" ? 1 : 3),
                    },
                });
                if (apiError || !data) throw new Error("Spark generation failed");
                const result = data as SparkGenerateResponse;
                const cards = result.cards ?? [];
                setState((s) => ({
                    ...s,
                    card: cards[0] ?? s.card,
                    cards,
                    loading: false,
                    error: null,
                }));
            } catch (err) {
                setState((s) => ({
                    ...s,
                    loading: false,
                    error: err instanceof Error ? err.message : "Spark generation failed",
                }));
            }
        },
        [flowId, getIdentity],
    );

    const generate = useCallback(
        async (opts: GenerateOpts) => {
            optsRef.current = opts;
            setState((s) => ({ ...s, adjustmentHistory: [], lastAdjustment: null, card: null, cards: [] }));
            await callApi(opts, null, []);
        },
        [callApi],
    );

    const adjust = useCallback(
        (text: string): void => {
            setState((s) => {
                const newHistory = [...s.adjustmentHistory, text].slice(-MAX_HISTORY);
                // Kick off the call with updated history — we read state inside callApi via closure
                void callApi(optsRef.current, s.card, newHistory);
                return { ...s, adjustmentHistory: newHistory, lastAdjustment: text };
            });
        },
        [callApi],
    );

    const switchFrame = useCallback(
        (frame: SparkFrame): void => {
            optsRef.current = { ...optsRef.current, frame };
            const text = `switch to ${frame} vibe`;
            setState((s) => {
                const newHistory = [...s.adjustmentHistory, text].slice(-MAX_HISTORY);
                void callApi({ ...optsRef.current, frame }, s.card, newHistory);
                return { ...s, adjustmentHistory: newHistory, lastAdjustment: text };
            });
        },
        [callApi],
    );

    const selectCard = useCallback((card: SparkCard) => {
        setState((s) => ({ ...s, card, adjustmentHistory: [], lastAdjustment: null }));
    }, []);

    const reset = useCallback(() => {
        setState(initialState());
    }, []);

    return [state, { generate, adjust, switchFrame, selectCard, reset }];
}
