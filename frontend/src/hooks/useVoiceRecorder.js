import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeAudio } from "../api/voice";

// Recording formats in order of preference; browsers support different ones.
const FORMATS = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
const MIN_BYTES = 1000;

export function voiceSupported() {
  return Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
}

function micErrorText(error) {
  if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
    return "Microphone access is blocked. Allow the microphone for this site (the icon in the address bar) and try again.";
  }

  if (error?.name === "NotFoundError" || error?.name === "OverconstrainedError") {
    return "No microphone was found. Plug one in and try again.";
  }

  if (error?.name === "NotReadableError") {
    return "The microphone is being used by another app. Close it and try again.";
  }

  return "The microphone could not be started. Please try again.";
}

// Click to start, click again to stop: the recording is turned into text and passed to
// onText. Stops by itself after maxSeconds.
export default function useVoiceRecorder({ onText, maxSeconds = 60 }) {
  const [state, setState] = useState("idle"); // idle | starting | recording | working
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");

  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(0);
  const aliveRef = useRef(true);
  const onTextRef = useRef(onText);

  useEffect(() => {
    onTextRef.current = onText;
  }, [onText]);

  const release = useCallback(() => {
    clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const stop = useCallback(() => {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
  }, []);

  const start = useCallback(async () => {
    setError("");

    if (!voiceSupported()) {
      setError("Voice input is not supported in this browser. Please use Chrome, Edge or Firefox.");
      return;
    }

    setState("starting");

    let stream;

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (err) {
      setState("idle");
      setError(micErrorText(err));
      return;
    }

    if (!aliveRef.current) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }

    const mimeType = FORMATS.find((type) => MediaRecorder.isTypeSupported?.(type));
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks = [];

    streamRef.current = stream;
    recorderRef.current = recorder;

    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
    };

    recorder.onstop = async () => {
      release();

      if (!aliveRef.current) return;

      const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" });

      if (blob.size < MIN_BYTES) {
        setState("idle");
        setError("That was too short. Click the mic, speak, then click it again.");
        return;
      }

      setState("working");

      try {
        const text = await transcribeAudio(blob);
        if (aliveRef.current) onTextRef.current(text);
      } catch (err) {
        if (aliveRef.current) setError(err.message || "Your voice could not be understood. Please try again.");
      } finally {
        if (aliveRef.current) setState("idle");
      }
    };

    recorder.start(250);
    setSeconds(0);
    setState("recording");

    const started = Date.now();
    timerRef.current = setInterval(() => {
      const elapsed = Math.floor((Date.now() - started) / 1000);
      setSeconds(elapsed);
      if (elapsed >= maxSeconds) stop();
    }, 250);
  }, [maxSeconds, release, stop]);

  // Leaving the page mid-recording turns the microphone off and drops the result.
  useEffect(() => {
    aliveRef.current = true;

    return () => {
      aliveRef.current = false;
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
      release();
    };
  }, [release]);

  const toggle = useCallback(() => {
    if (state === "recording") stop();
    else if (state === "idle") start();
  }, [state, start, stop]);

  return { state, seconds, error, toggle, clearError: () => setError("") };
}
