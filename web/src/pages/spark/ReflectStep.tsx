import { Button, Card, CardContent, SectionHeader } from "../../components";
import { Chip, ScaleControl } from "../../components/ui";
import type { SparkCondition } from "./sparkData";

export interface RatingState {
    fit: number | null;
    clarity: number | null;
    willing: number | null;
}

interface ReflectStepProps {
    condition: SparkCondition;
    rating: RatingState;
    onChange: (next: RatingState) => void;
    onFinish: () => void;
    onGoto: (cond: SparkCondition) => void;
}

const ITEMS: { key: keyof RatingState; label: string; sub: string }[] = [
    { key: "fit",     label: "Perceived fit",    sub: "How well did this Spark fit you?" },
    { key: "clarity", label: "Action clarity",   sub: "How clear was what to do?" },
    { key: "willing", label: "Willingness to try", sub: "How willing are you to actually do it?" },
];

export function ReflectStep({ condition, rating, onChange, onFinish, onGoto }: ReflectStepProps) {
    const allRated = ITEMS.every((it) => rating[it.key] !== null);

    return (
        <div className="space-y-4">
            <SectionHeader
                size="lg"
                eyebrow="Rate this experience"
                title={`Before you go — Condition ${condition}`}
            />

            {ITEMS.map(({ key, label, sub }) => (
                <Card key={key}>
                    <CardContent className="space-y-3">
                        <div>
                            <p className="text-sm font-medium text-text">{label}</p>
                            <p className="text-xs text-text-subtle mt-0.5">{sub}</p>
                        </div>
                        <ScaleControl
                            value={rating[key]}
                            onPick={(n) => onChange({ ...rating, [key]: n })}
                            lo="Low"
                            hi="High"
                            label={label}
                        />
                    </CardContent>
                </Card>
            ))}

            <Button variant="primary" size="lg" className="w-full" disabled={!allRated} onClick={onFinish}>
                Finish Condition {condition}
            </Button>

            {/* Quick jump to other conditions */}
            <div className="flex gap-2 flex-wrap">
                {(["A", "B", "C", "D"] as SparkCondition[])
                    .filter((c) => c !== condition)
                    .map((c) => (
                        <Chip key={c} tone="quiet" onClick={() => onGoto(c)}>
                            Go to {c}
                        </Chip>
                    ))}
            </div>
        </div>
    );
}
