import { Card, CardContent, SectionHeader } from "../../components";
import { Chip, ScaleControl } from "../../components/ui";
import { ANCHORS, type IntakeProfile } from "./sparkData";

interface CueStepProps {
    profile: IntakeProfile;
    cue: string | null;
    reminder: string | null;
    confidence: number | null;
    onCue: (c: string) => void;
    onReminder: (r: string) => void;
    onConfidence: (v: number) => void;
}

const DEFAULT_CUES = [
    "After my next coffee",
    "Before a meeting",
    "Right after lunch",
    "When I feel stiff",
    "Mid-afternoon slump",
];

const REMINDERS = [
    { label: "📅 Add to calendar", k: "calendar" },
    { label: "✉️ Email me", k: "email" },
    { label: "Skip", k: "skip" },
];

export function CueStep({ profile, cue, reminder, confidence, onCue, onReminder, onConfidence }: CueStepProps) {
    const anchorDef = profile.anchor ? ANCHORS.find((a) => a.k === profile.anchor) : null;
    const cues = anchorDef
        ? [`When I ${anchorDef.label.toLowerCase()}`, ...DEFAULT_CUES].slice(0, 5)
        : DEFAULT_CUES;

    return (
        <div className="space-y-4">
            <SectionHeader
                size="lg"
                eyebrow="Make it stick"
                title="When would you do this again?"
            />

            <Card>
                <CardContent className="space-y-3">
                    <p className="text-sm font-medium text-text">Pick a cue to repeat it</p>
                    <div className="flex flex-wrap gap-2">
                        {cues.map((c) => (
                            <Chip key={c} selected={cue === c} onClick={() => onCue(c)}>
                                {c}
                            </Chip>
                        ))}
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardContent className="space-y-3">
                    <p className="text-sm font-medium text-text">Send yourself a reminder?</p>
                    <div className="flex flex-wrap gap-2">
                        {REMINDERS.map(({ label, k }) => (
                            <Chip key={k} selected={reminder === k} onClick={() => onReminder(k)}>
                                {label}
                            </Chip>
                        ))}
                    </div>
                </CardContent>
            </Card>

            {/* Confidence (shown once cue picked) */}
            {cue && (
                <Card>
                    <CardContent className="space-y-3">
                        <p className="text-sm font-medium text-text">
                            How confident are you this fits your day?
                        </p>
                        <ScaleControl
                            value={confidence}
                            onPick={onConfidence}
                            lo="Not at all"
                            hi="Very"
                            label="Confidence this fits your day"
                        />
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
