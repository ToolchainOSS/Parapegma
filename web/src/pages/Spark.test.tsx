import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { Spark } from "./Spark";

const mockPost = vi.fn();

vi.mock("../api/client", () => ({
    default: {
        POST: (...args: unknown[]) => mockPost(...args),
    },
}));

vi.mock("./spark/sparkResearchIdentity", () => ({
    createSparkClientId: () => "00000000-0000-4000-8000-000000000001",
    getSparkResearchIdentity: async () => ({
        installation_id: "00000000-0000-4000-8000-000000000002",
        fingerprint: "test-thumbmark",
        fingerprint_version: "1.10.0",
        timezone: "America/Toronto",
        locale: "en-CA",
    }),
}));

vi.mock("./spark/sparkTelemetry", () => ({
    useSparkEventTracker: () => vi.fn(),
}));

// Minimal card fixture
const CARD = {
    title: "Desk Reset",
    frame: "calm",
    action: "Roll your shoulders and breathe.",
    reward: "You feel less tension.",
    why: "Desk-friendly and quick.",
    fit_score: 80,
};

const SUCCESS_RESPONSE = {
    data: {
        condition: "A",
        cards: [CARD],
        model: "gpt-test-model",
        prompt_version: { prompt_file: "spark_proxy_system", prompt_sha256: "abc" },
    },
    error: undefined,
};

/** One card per vibe — the shape condition B's sampler is served. */
const SAMPLER_CARDS = ["calm", "zoomies", "silly", "challenge", "science"].map((frame) => ({
    ...CARD,
    frame,
    title: `${frame} sample`,
}));

function respondWith(condition: string, cards: unknown[]) {
    return {
        data: {
            condition,
            cards,
            model: "static-library",
            prompt_version: { prompt_file: "x", prompt_sha256: "y" },
        },
        error: undefined,
    };
}

/** Answer the intake — it asks about circumstances only, never about a vibe. */
async function answerIntake() {
    fireEvent.click(await screen.findByText("Make coffee or tea"));
    fireEvent.click(await screen.findByText("Reach & Roll"));
    fireEvent.click(await screen.findByText("Morning"));
}

describe("Spark page", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("renders the Spark page and home grid", () => {
        render(<Spark />);
        expect(screen.getByTestId("spark-page")).toBeInTheDocument();
        expect(screen.getByTestId("spark-heading")).toBeInTheDocument();
        // All four condition cards are present on home
        expect(screen.getByTestId("spark-cond-A")).toBeInTheDocument();
        expect(screen.getByTestId("spark-cond-D")).toBeInTheDocument();
    });

    it("condition A: fetches on entry, with no base_card and empty history", async () => {
        mockPost.mockResolvedValue(SUCCESS_RESPONSE);

        render(<Spark />);

        // Entering the condition IS the request — no second tap to confirm it,
        // which is also what keeps A in step with B's sampler.
        fireEvent.click(screen.getByTestId("spark-cond-A"));

        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledWith("/spark/generate", {
                body: expect.objectContaining({
                    identity: expect.objectContaining({
                        installation_id: "00000000-0000-4000-8000-000000000002",
                        fingerprint: "test-thumbmark",
                    }),
                    condition: "A",
                    adjustment_history: [],
                    count: 1,
                }),
            });
        });

        // base_card should NOT be present (or undefined) on first generate
        const firstCall = mockPost.mock.calls[0];
        const callBody = (firstCall?.[1] as { body: Record<string, unknown> } | undefined)?.body;
        expect(callBody?.base_card).toBeUndefined();

        // Spark card title visible after generation
        expect(await screen.findByText("Desk Reset")).toBeInTheDocument();
    });

    it("auto-fetching conditions request exactly once on entry", async () => {
        // The once-only guard lives in useSparkRemix, so a re-render (or
        // StrictMode's double effect) must not fire a second generate — which
        // would also double-count the participant's flow in the telemetry.
        mockPost.mockResolvedValue(respondWith("B", SAMPLER_CARDS));

        const { rerender } = render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));
        await screen.findByTestId("spark-sample-calm");

        rerender(<Spark />);
        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledTimes(1);
        });
    });

    it("adjust (conditions C/D only) sends base_card + accumulated adjustment_history", async () => {
        // Intake → generate (C) succeeds with a card
        mockPost.mockResolvedValueOnce({
            data: {
                condition: "C",
                cards: [CARD],
                model: "gpt-test-model",
                prompt_version: { prompt_file: "spark_proxy_system", prompt_sha256: "abc" },
            },
            error: undefined,
        });
        // Second call (remix) also succeeds
        mockPost.mockResolvedValueOnce({
            data: {
                condition: "C",
                cards: [{ ...CARD, title: "Desk Reset (Remix)" }],
                model: "gpt-test-model",
                prompt_version: { prompt_file: "spark_proxy_system", prompt_sha256: "abc" },
            },
            error: undefined,
        });

        render(<Spark />);

        // Enter condition C (adaptive) and answer the intake questions
        fireEvent.click(screen.getByTestId("spark-cond-C"));
        await answerIntake();

        // First (intake) generate fires with no base_card + empty history
        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledTimes(1);
        });
        const firstBody = (mockPost.mock.calls[0]?.[1] as { body: Record<string, unknown> } | undefined)?.body;
        expect(firstBody?.condition).toBe("C");
        expect(firstBody?.base_card).toBeUndefined();
        expect(firstBody?.adjustment_history).toEqual([]);
        // The intake states no vibe — the model picks one.
        expect(firstBody?.frame_preference).toBeUndefined();

        // Adapted card appears, with the adjust panel (C/D keep remix)
        await screen.findByText("Desk Reset");

        // Click "Make it easier" quick chip
        fireEvent.click(await screen.findByText("Make it easier"));

        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledTimes(2);
        });

        const remixCall = (mockPost.mock.calls[1]?.[1] as { body: Record<string, unknown> } | undefined)?.body;
        // base_card should be the prior card
        expect(remixCall?.base_card).toMatchObject({ title: "Desk Reset" });
        // history carries the adjustment
        expect(remixCall?.adjustment_history).toEqual(["make it easier"]);
    });

    it("condition B: shows one real Spark per vibe on entry instead of asking for a vibe", async () => {
        mockPost.mockResolvedValue(respondWith("B", SAMPLER_CARDS));

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));

        // The sampler loads itself — no vibe question stands between the
        // participant and the intervention.
        await screen.findByTestId("spark-sample-calm");
        expect(mockPost).toHaveBeenCalledTimes(1);
        const body = (mockPost.mock.calls[0]?.[1] as { body: Record<string, unknown> }).body;
        expect(body.condition).toBe("B");
        expect(body.frame_preference).toBeUndefined();

        // Every vibe is represented by a concrete Spark.
        for (const frame of ["calm", "zoomies", "silly", "challenge", "science"]) {
            expect(screen.getByTestId(`spark-sample-${frame}`)).toBeInTheDocument();
        }

        // Picking one carries that card straight through — no extra fetch.
        fireEvent.click(screen.getByTestId("spark-sample-silly"));
        expect(await screen.findByTestId("spark-card")).toBeInTheDocument();
        expect(screen.getByText("silly sample")).toBeInTheDocument();
        expect(mockPost).toHaveBeenCalledTimes(1);
    });

    it("condition D: browses a ranked catalog holding one Spark per vibe", async () => {
        const catalog = ["calm", "zoomies", "silly", "challenge", "science"].map(
            (frame, i) => ({ ...CARD, frame, fit_score: 95 - i * 5, title: `${frame} pick` }),
        );
        mockPost.mockResolvedValue(respondWith("D", catalog));

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-D"));
        await answerIntake();

        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledTimes(1);
        });
        const body = (mockPost.mock.calls[0]?.[1] as { body: Record<string, unknown> }).body;
        // One request for the whole catalog — one card per vibe, no vibe asked for.
        expect(body).toMatchObject({ condition: "D", count: 5 });
        expect(body.frame_preference).toBeUndefined();

        // Same choice set as condition B's sampler: every vibe, exactly once.
        for (const frame of ["calm", "zoomies", "silly", "challenge", "science"]) {
            expect(screen.getByTestId(`spark-ranked-${frame}`)).toBeInTheDocument();
        }

        // Picking lands on the preview step, whose index is derived from the
        // intake length — not a hardcoded one that drifts when questions change.
        fireEvent.click(screen.getByTestId("spark-ranked-challenge"));
        expect(await screen.findByTestId("spark-card")).toBeInTheDocument();
        expect(screen.getByText("Your pick")).toBeInTheDocument();
    });

    it("shows the API's own reason for a failure, not a blanket message", async () => {
        // A missing key (503), a bad model payload (502) and a timeout (504) all
        // used to render identically, which made the UI useless for diagnosis.
        mockPost.mockResolvedValue({
            data: undefined,
            error: { detail: "OpenAI API key not configured" },
        });

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));

        expect(await screen.findByTestId("spark-error")).toHaveTextContent(
            "OpenAI API key not configured",
        );
    });

    it("falls back to a generic message when the API gives no usable detail", async () => {
        mockPost.mockResolvedValue({ data: undefined, error: { detail: [] } });

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));

        expect(await screen.findByTestId("spark-error")).toHaveTextContent(
            "Spark generation failed",
        );
    });

    it("leaves a condition through the back affordance on its first step", async () => {
        mockPost.mockResolvedValue(respondWith("B", SAMPLER_CARDS));

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));
        expect(await screen.findByText("Which one would you actually do?")).toBeInTheDocument();

        // With no condition switcher above the flow, back on step 0 is the only
        // way out — it must exit to home rather than be hidden.
        fireEvent.click(screen.getByLabelText("Back to all conditions"));
        expect(screen.getByTestId("spark-cond-A")).toBeInTheDocument();
    });
});
