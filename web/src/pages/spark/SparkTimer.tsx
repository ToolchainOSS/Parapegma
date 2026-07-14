/**
 * SparkTimer — 60-second SVG ring countdown.
 * Calls onDone ~1 s after the ring hits zero.
 */
import { useEffect, useRef, useState } from "react";
import { FRAMINGS, type SparkFrame } from "./sparkData";

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

    const f = FRAMINGS[frame] ?? FRAMINGS.calm;
    const offset = CIRC * (1 - left / TOTAL);
    const done = completion !== null;
    const skipped = completion === "skipped";

    return (
        <div className="spark-timer-wrap">
            {!done ? (
                <>
                    <svg
                        className="spark-timer-ring"
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
                            stroke="var(--divider)"
                            strokeWidth="14"
                        />
                        <circle
                            cx="100"
                            cy="100"
                            r={R}
                            fill="none"
                            stroke={f.colorVar}
                            strokeWidth="14"
                            strokeLinecap="round"
                            transform="rotate(-90 100 100)"
                            strokeDasharray={CIRC}
                            strokeDashoffset={offset}
                            className="spark-ring-progress"
                        />
                        <text
                            x="100"
                            y="112"
                            textAnchor="middle"
                            className="spark-timer-number"
                            fill="var(--text)"
                            fontSize="48"
                        >
                            {left}
                        </text>
                    </svg>
                    <p className="text-sm text-text-muted mt-2">Move until the timer ends.</p>
                    <div className="flex justify-center mt-3">
                        <button
                            type="button"
                            className="spark-chip"
                            onClick={() => {
                                setLeft(0);
                                setCompletion("skipped");
                            }}
                        >
                            Skip to end
                        </button>
                    </div>
                </>
            ) : (
                <div className="text-center">
                    <div
                        className="spark-check-circle"
                        style={{ background: f.colorVar }}
                        aria-hidden="true"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" width="38" height="38">
                            <path d="M20 6 9 17l-5-5" />
                        </svg>
                    </div>
                    <h3 className="text-2xl font-bold mt-3 text-text">
                        {skipped ? "Skipped — good call." : "Done — that's your minute."}
                    </h3>
                    <p className="text-text-muted mt-1">Nice. Notice how your body feels right now.</p>
                </div>
            )}
        </div>
    );
}
