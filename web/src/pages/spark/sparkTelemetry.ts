import { useCallback, useEffect } from "react";
import api from "../../api/client";
import type { SparkCondition, SparkFrame } from "./sparkData";
import { createSparkClientId, type SparkIdentityProvider } from "./sparkResearchIdentity";

export type SparkTelemetryEvent =
    | { event_type: "flow_started" }
    | {
          event_type: "intake_answered";
          /** No "frame" — the intake never asks a participant to name a vibe. */
          field: "anchor" | "action" | "time";
          value: string;
      }
    /** Revealed vibe: the frame of the card the participant actually chose. */
    | { event_type: "frame_selected"; frame: SparkFrame }
    /** `rank` is 1-5 within the list picked from (B's sampler, or one vibe
     *  column in D) — never an index into D's full 25-card catalog. */
    | { event_type: "card_selected"; rank: number }
    | { event_type: "timer_finished"; completion: "completed" | "skipped" }
    | {
          event_type: "feedback_submitted";
          tried: number;
          reason: string | null;
          tweak: string;
      }
    | {
          event_type: "cue_selected";
          cue: string;
          reminder: "calendar" | "email" | "skip" | null;
          confidence: number | null;
      }
    | { event_type: "condition_completed"; fit: number; clarity: number; willing: number };

interface SparkEventTrackerOptions {
    condition: SparkCondition;
    flowId: string;
    getIdentity: SparkIdentityProvider;
}

/** Send a typed event without ever exposing the pseudonymous identifiers in logs. */
export function useSparkEventTracker({
    condition,
    flowId,
    getIdentity,
}: SparkEventTrackerOptions): (event: SparkTelemetryEvent) => void {
    const track = useCallback(
        (event: SparkTelemetryEvent): void => {
            void (async () => {
                try {
                    const identity = await getIdentity();
                    const { error } = await api.POST("/spark/events", {
                        body: {
                            identity,
                            flow_id: flowId,
                            client_event_id: createSparkClientId(),
                            condition,
                            event,
                        },
                    });
                    if (error) {
                        console.warn("Spark interaction telemetry was not recorded.");
                    }
                } catch {
                    console.warn("Spark interaction telemetry was not recorded.");
                }
            })();
        },
        [condition, flowId, getIdentity],
    );

    useEffect(() => {
        track({ event_type: "flow_started" });
    }, [track]);

    return track;
}
