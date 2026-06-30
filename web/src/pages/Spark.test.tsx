import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { Spark } from "./Spark";

const mockPost = vi.fn();

vi.mock("../api/client", () => ({
    default: {
        POST: (...args: unknown[]) => mockPost(...args),
    },
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

    it("condition A: first generate sends no base_card and empty history", async () => {
        mockPost.mockResolvedValue(SUCCESS_RESPONSE);

        render(<Spark />);

        // Enter condition A from home grid
        fireEvent.click(screen.getByTestId("spark-cond-A"));

        // Click "Get my Spark"
        fireEvent.click(screen.getByText("Get my Spark"));

        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledWith("/spark/generate", {
                body: expect.objectContaining({
                    condition: "A",
                    adjustment_history: [],
                    count: 1,
                }),
            });
        });

        // base_card should NOT be present (or undefined) on first generate
        const callBody = mockPost.mock.calls[0][1].body;
        expect(callBody.base_card).toBeUndefined();

        // Spark card title visible after generation
        expect(await screen.findByText("Desk Reset")).toBeInTheDocument();
    });

    it("adjust sends base_card + accumulated adjustment_history", async () => {
        // First call succeeds with a card
        mockPost.mockResolvedValueOnce(SUCCESS_RESPONSE);
        // Second call (remix) also succeeds
        mockPost.mockResolvedValueOnce({
            data: {
                condition: "A",
                cards: [{ ...CARD, title: "Desk Reset (Remix)" }],
                model: "gpt-test-model",
                prompt_version: { prompt_file: "spark_proxy_system", prompt_sha256: "abc" },
            },
            error: undefined,
        });

        render(<Spark />);

        fireEvent.click(screen.getByTestId("spark-cond-A"));
        fireEvent.click(screen.getByText("Get my Spark"));

        // Wait for card to appear
        await screen.findByText("Desk Reset");

        // Click "Make it easier" quick chip
        fireEvent.click(await screen.findByText("Make it easier"));

        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledTimes(2);
        });

        const remixCall = mockPost.mock.calls[1][1].body;
        // base_card should be the prior card
        expect(remixCall.base_card).toMatchObject({ title: "Desk Reset" });
        // history carries the adjustment
        expect(remixCall.adjustment_history).toEqual(["make it easier"]);
    });

    it("condition tabs switch between conditions and home", () => {
        render(<Spark />);
        // Navigate to condition B
        fireEvent.click(screen.getByTestId("spark-tab-B"));
        // Vibe wheel heading should appear
        expect(screen.getByText("Pick a vibe")).toBeInTheDocument();

        // Navigate back home
        fireEvent.click(screen.getByText("Home"));
        expect(screen.getByTestId("spark-cond-A")).toBeInTheDocument();
    });
});

