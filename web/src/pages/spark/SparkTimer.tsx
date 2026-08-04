/**
 * SparkTimer — 60-second SVG ring countdown.
 * Calls onDone ~1 s after the ring hits zero.
 */
import { useEffect, useRef, useState } from "react";
import { Chip } from "../../components/ui";
import { framingOf } from "./FramingChip";
import type { SparkFrame } from "./sparkData";

const TOTAL = 60;
const R = 88;
const CIRC = 2 * Math.PI * R;

interface SparkTimerProps {
    frame: SparkFrame;
    onDone: (completion: "completed" | "skipped") => void;
}

export function SparkTimer({ frame, onDone }: SparkTimerProps) {
    const [left, setLeft] = useState(TOTAL);
    const [completion, setCompletion] = useState<"completed" | "skipped" | null>(null);
    const onDoneRef = useRef(onDone);

    useEffect(() => {
        onDoneRef.current = onDone;
    });

    useEffect(() => {
        if (completion) {
            const t = setTimeout(() => onDoneRef.current(completion), 1100);
            return () => clearTimeout(t);
        }
    }, [completion]);

    useEffect(() => {
        const iv = setInterval(() => {
            setLeft((prev) => {
                if (prev <= 1) {
                    clearInterval(iv);
                    setCompletion("completed");
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);
        return () => clearInterval(iv);
    }, []);

    const f = framingOf(frame);
    const offset = CIRC * (1 - left / TOTAL);
    const done = completion !== null;
    const skipped = completion === "skipped";

    return (
        <div className="text-center py-8">
            {!done ? (
                <>
                    <svg
                        className="block mx-auto"
                        width="200"
                        height="200"
                        viewBox="0 0 200 200"
                        role="img"
                        aria-label={`${left} seconds remaining`}
                    >
                        <circle
                            cx="100"
                            cy="100"
                            r={R}
                            fill="none"
                            stroke="var(--color-divider)"
                            strokeWidth="14"
                        />
                        <circle
                            cx="100"
                            cy="100"
                            r={R}
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="14"
                            strokeLinecap="round"
                            transform="rotate(-90 100 100)"
                            strokeDasharray={CIRC}
                            strokeDashoffset={offset}
                            className={`spark-ring-progress ${f.accentText}`}
                        />
                        <text
                            x="100"
                            y="112"
                            textAnchor="middle"
                            className="font-display tabular-nums"
                            fill="var(--color-text)"
                            fontSize="48"
                        >
                            {left}
                        </text>
                    </svg>
                    <p className="text-sm text-text-muted mt-2">Move until the timer ends.</p>
                    <div className="flex justify-center mt-3">
                        <Chip
                            tone="quiet"
                            onClick={() => {
                                setLeft(0);
                                setCompletion("skipped");
                            }}
                        >
                            Skip to end
                        </Chip>
                    </div>
                </>
            ) : (
                <div className="text-center">
                    <div
                        className={`w-[72px] h-[72px] rounded-full grid place-items-center mx-auto ${f.accentBg}`}
                        aria-hidden="true"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" width="38" height="38">
                            <path d="M20 6 9 17l-5-5" />
                        </svg>
                    </div>
                    <h3 className="display-sm text-text mt-4">
                        {skipped ? "Skipped — good call." : "Done — that's your minute."}
                    </h3>
                    <p className="text-text-muted mt-1">Nice. Notice how your body feels right now.</p>
                </div>
            )}
        </div>
    );
}
