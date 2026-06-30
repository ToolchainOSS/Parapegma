/**
 * VoiceControl — Web Speech API wrapper with typed textarea fallback.
 *
 * Renders a textarea + microphone button. When the user taps the mic:
 *   - If SpeechRecognition is available: start listening; call onText on result.
 *   - If not: focus the textarea for typed input.
 * Ctrl/Cmd+Enter in the textarea also submits.
 *
 * Does NOT persist state — parent owns the value if needed.
 */
import { useRef, useState } from "react";

interface VoiceControlProps {
    placeholder?: string;
    hint?: string;
    onText: (text: string) => void;
    /** Extra class on the outer wrapper */
    className?: string;
}

// ---------------------------------------------------------------------------
// Minimal Web Speech API typings (constructor is not in lib.dom.d.ts globals)
// ---------------------------------------------------------------------------
interface SRResult {
    readonly isFinal: boolean;
    readonly [index: number]: { readonly transcript: string } | undefined;
}
interface SRResultList {
    readonly length: number;
    readonly [index: number]: SRResult | undefined;
}
interface SREvent {
    readonly resultIndex: number;
    readonly results: SRResultList;
}
interface SRErrorEvent {
    readonly error: string;
}
interface SRInstance {
    lang: string;
    interimResults: boolean;
    continuous: boolean;
    onresult: ((e: SREvent) => void) | null;
    onerror: ((e: SRErrorEvent) => void) | null;
    onend: (() => void) | null;
    start(): void;
    stop(): void;
}
type SRCtor = new () => SRInstance;

/** Vendor-safe SpeechRecognition constructor. Returns null when unavailable. */
function getSR(): SRCtor | null {
    const w = window as unknown as Record<string, unknown>;
    // eslint-disable-next-line @typescript-eslint/dot-notation
    const ctor = w["SpeechRecognition"] ?? w["webkitSpeechRecognition"];
    return typeof ctor === "function" ? (ctor as SRCtor) : null;
}

export function VoiceControl({ placeholder = "Type or speak a change…", hint, onText, className = "" }: VoiceControlProps) {
    const taRef = useRef<HTMLTextAreaElement>(null);
    const recRef = useRef<SRInstance | null>(null);
    const [recording, setRecording] = useState(false);

    function submit() {
        const v = taRef.current?.value.trim();
        if (v) onText(v);
    }

    function stopRecording() {
        setRecording(false);
        try {
            recRef.current?.stop();
        } catch {
            // ignore
        }
    }

    function toggleMic() {
        if (recording) {
            stopRecording();
            submit();
            return;
        }

        const SR = getSR();
        if (!SR) {
            if (taRef.current) taRef.current.focus();
            return;
        }

        const rec = new SR();
        rec.lang = "en-US";
        rec.interimResults = true;
        rec.continuous = false;
        recRef.current = rec;

        let finalText = "";
        rec.onresult = (e: SREvent) => {
            let interim = "";
            for (let i = e.resultIndex; i < e.results.length; i++) {
                const result = e.results[i];
                if (!result) continue;
                const tr = result[0]?.transcript ?? "";
                if (result.isFinal) finalText += tr;
                else interim += tr;
            }
            if (taRef.current) taRef.current.value = (finalText + " " + interim).trim();
        };

        rec.onerror = () => {
            stopRecording();
            if (taRef.current) taRef.current.focus();
        };

        rec.onend = () => {
            if (recording) {
                setRecording(false);
                submit();
            }
        };

        setRecording(true);
        if (taRef.current) taRef.current.value = "";
        try {
            rec.start();
        } catch {
            setRecording(false);
        }
    }

    return (
        <div className={`space-y-1.5 ${className}`}>
            <div className="spark-voice-row">
                <textarea
                    ref={taRef}
                    className="spark-voice-input"
                    placeholder={placeholder}
                    rows={2}
                    onKeyDown={(e) => {
                        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                            e.preventDefault();
                            submit();
                        }
                    }}
                />
                <button
                    type="button"
                    className={`spark-mic-btn${recording ? " spark-mic-recording" : ""}`}
                    data-recording={recording ? "true" : "false"}
                    aria-label={recording ? "Stop recording" : "Speak your change"}
                    onClick={toggleMic}
                >
                    <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke={recording ? "#fff" : "currentColor"}
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        width="20"
                        height="20"
                    >
                        <rect x="9" y="2" width="6" height="12" rx="3" />
                        <path d="M5 10a7 7 0 0 0 14 0" />
                        <line x1="12" y1="19" x2="12" y2="22" />
                    </svg>
                </button>
            </div>
            {hint && <p className="text-xs text-text-muted">{hint}</p>}
        </div>
    );
}

