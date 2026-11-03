import useVoiceRecorder, { voiceSupported } from "../hooks/useVoiceRecorder";

const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

// A mic button: click, speak, click again. What was said is passed to onText.
export default function VoiceButton({ onText, disabled = false, label = "Speak instead of typing" }) {
  const { state, seconds, error, toggle } = useVoiceRecorder({ onText });

  if (!voiceSupported()) return null;

  const recording = state === "recording";
  const busy = state === "starting" || state === "working";

  return (
    <div className="dx-voice">
      <button
        type="button"
        onClick={toggle}
        disabled={(disabled && !recording) || busy}
        className={`dx-mic ${recording ? "on" : ""} ${busy ? "busy" : ""}`}
        aria-label={recording ? "Stop recording" : label}
        aria-pressed={recording}
        title={recording ? "Stop recording" : label}
      >
        {busy ? (
          <span className="dx-step-spin" aria-hidden="true" />
        ) : (
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            {recording ? (
              <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" />
            ) : (
              <>
                <rect x="9" y="3" width="6" height="11" rx="3" />
                <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
              </>
            )}
          </svg>
        )}
      </button>

      <p className="dx-voice-status" role="status" aria-live="polite">
        {recording && <>Listening… {clock(seconds)} · click again when you finish</>}
        {state === "starting" && "Starting the microphone…"}
        {state === "working" && "Understanding what you said…"}
      </p>

      {error && (
        <p className="dx-assist-status bad dx-voice-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
