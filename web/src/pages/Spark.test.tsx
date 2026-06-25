import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { Spark } from "./Spark";

const mockPost = vi.fn();

vi.mock("../api/client", () => ({
    default: {
        POST: (...args: unknown[]) => mockPost(...args),
    },
}));

describe("Spark page", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("renders the Spark page", () => {
        render(<Spark />);
        expect(screen.getByTestId("spark-page")).toBeInTheDocument();
        expect(screen.getByTestId("spark-heading")).toBeInTheDocument();
    });

    it("calls Spark generate endpoint and renders cards", async () => {
        mockPost.mockResolvedValue({
            data: {
                condition: "A",
                cards: [
                    {
                        title: "Desk Reset",
                        frame: "calm",
                        action: "Roll your shoulders and breathe.",
                        reward: "You feel less tension.",
                        why: "Desk-friendly and quick.",
                        fit_score: 80,
                    },
                ],
                model: "gpt-test-model",
                prompt_version: {
                    prompt_file: "spark_proxy_system",
                    prompt_sha256: "abc",
                },
            },
            error: undefined,
        });

        render(<Spark />);

        fireEvent.click(screen.getByTestId("spark-generate"));

        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledWith("/spark/generate", {
                body: {
                    condition: "A",
                    frame_preference: undefined,
                    context: undefined,
                    adjustment: undefined,
                    count: 1,
                },
            });
        });

        expect(await screen.findByText("Desk Reset")).toBeInTheDocument();
        expect(screen.getByTestId("spark-model-meta")).toHaveTextContent(
            "gpt-test-model",
        );
    });
});
