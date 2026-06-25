import { useMemo, useState } from "react";
import { PageHeader } from "../components/ui/PageHeader";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Input } from "../components/Input";
import { Alert } from "../components/Alert";
import api from "../api/client";
import type { SparkGenerateResponse } from "../api/types";

type SparkCondition = "A" | "B" | "C" | "D";
type SparkFrame = "calm" | "zoomies" | "silly" | "challenge" | "science";

const FRAME_OPTIONS: SparkFrame[] = [
    "calm",
    "zoomies",
    "silly",
    "challenge",
    "science",
];

export function Spark() {
    const [condition, setCondition] = useState<SparkCondition>("A");
    const [frame, setFrame] = useState<SparkFrame | "">("");
    const [context, setContext] = useState("");
    const [adjustment, setAdjustment] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<SparkGenerateResponse | null>(null);

    const cardCount = useMemo(() => {
        if (condition === "D") return 4;
        if (condition === "A" || condition === "C") return 1;
        return 3;
    }, [condition]);

    const onGenerate = async () => {
        setLoading(true);
        setError(null);
        try {
            const { data, error: apiError } = await api.POST("/spark/generate", {
                body: {
                    condition,
                    frame_preference: frame || undefined,
                    context: context.trim() || undefined,
                    adjustment: adjustment.trim() || undefined,
                    count: cardCount,
                },
            });
            if (apiError || !data) {
                throw new Error("Spark generation failed");
            }
            setResult(data as SparkGenerateResponse);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Spark generation failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex flex-col flex-1 bg-bg">
            <PageHeader title="Spark Prototype" data-testid="spark-heading" />
            <div className="space-y-4 px-4 py-6 max-w-3xl mx-auto w-full" data-testid="spark-page">
                <Card>
                    <CardHeader>
                        <h2 className="text-lg font-semibold text-text">Stateless Spark Runner</h2>
                        <p className="text-sm text-text-muted">
                            This phase is frontend-state only. Cards are generated live through the Spark LLM proxy and are not persisted.
                        </p>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="grid gap-3 sm:grid-cols-2">
                            <label className="text-sm text-text">
                                Condition
                                <select
                                    className="mt-1 w-full rounded-md border border-divider bg-surface px-3 py-2 text-sm"
                                    value={condition}
                                    onChange={(e) => setCondition(e.target.value as SparkCondition)}
                                    data-testid="spark-condition"
                                >
                                    <option value="A">A</option>
                                    <option value="B">B</option>
                                    <option value="C">C</option>
                                    <option value="D">D</option>
                                </select>
                            </label>
                            <label className="text-sm text-text">
                                Frame Preference
                                <select
                                    className="mt-1 w-full rounded-md border border-divider bg-surface px-3 py-2 text-sm"
                                    value={frame}
                                    onChange={(e) => setFrame(e.target.value as SparkFrame | "")}
                                    data-testid="spark-frame"
                                >
                                    <option value="">No preference</option>
                                    {FRAME_OPTIONS.map((opt) => (
                                        <option key={opt} value={opt}>
                                            {opt}
                                        </option>
                                    ))}
                                </select>
                            </label>
                        </div>
                        <Input
                            label="Context (optional)"
                            placeholder="e.g. I am in office clothes before a meeting"
                            value={context}
                            onChange={(e) => setContext(e.target.value)}
                            data-testid="spark-context"
                        />
                        <Input
                            label="Adjustment (optional)"
                            placeholder="e.g. make it quieter and less awkward"
                            value={adjustment}
                            onChange={(e) => setAdjustment(e.target.value)}
                            data-testid="spark-adjustment"
                        />
                        <div className="text-xs text-text-muted">Expected cards: {cardCount}</div>
                        <Button onClick={() => void onGenerate()} disabled={loading} data-testid="spark-generate">
                            {loading ? "Generating..." : "Generate Spark"}
                        </Button>
                        {error && (
                            <Alert variant="error" data-testid="spark-error">
                                {error}
                            </Alert>
                        )}
                    </CardContent>
                </Card>

                {result && (
                    <Card>
                        <CardHeader>
                            <h3 className="text-base font-semibold text-text">
                                {result.cards.length} card{result.cards.length === 1 ? "" : "s"} for condition {result.condition}
                            </h3>
                            <p className="text-xs text-text-muted" data-testid="spark-model-meta">
                                Model {result.model} via {result.prompt_version.prompt_file}
                            </p>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            {result.cards.map((card, idx) => (
                                <div
                                    key={`${card.title}-${idx}`}
                                    className="rounded-lg border border-divider bg-surface-2 p-3"
                                    data-testid="spark-card"
                                >
                                    <div className="flex items-center justify-between gap-2">
                                        <h4 className="font-semibold text-text">{card.title}</h4>
                                        <span className="text-xs uppercase text-text-muted">{card.frame}</span>
                                    </div>
                                    <p className="mt-2 text-sm text-text">{card.action}</p>
                                    <p className="mt-2 text-sm text-text-muted">{card.reward}</p>
                                    <p className="mt-1 text-xs text-text-muted">Why: {card.why}</p>
                                    {typeof card.fit_score === "number" && (
                                        <p className="mt-1 text-xs text-text-muted">Fit score: {card.fit_score}</p>
                                    )}
                                </div>
                            ))}
                        </CardContent>
                    </Card>
                )}
            </div>
        </div>
    );
}
