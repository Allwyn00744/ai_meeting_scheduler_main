import * as React from "react";

export type RecorderState = "idle" | "recording" | "processing" | "error";

const MAX_VOICE_RECORDING_SECONDS = 60;

function detectVoiceRecordingSupport(): boolean {
  if (typeof navigator === "undefined" || typeof window === "undefined") return false;
  if (!navigator.mediaDevices?.getUserMedia) return false;
  if (!window.MediaRecorder) return false;
  return MediaRecorder.isTypeSupported("audio/webm;codecs=opus");
}

/**
 * Wraps the browser's MediaRecorder API for the voice-scheduling flow.
 * Records to a webm/opus blob - one of the mime types the backend's
 * /ai/schedule-voice endpoint accepts (see _ALLOWED_AUDIO_MIME_TYPES in
 * app/api/ai_routes.py). V1 only supports Chrome/Edge/Firefox;
 * isSupported reflects that up front so callers can show a fallback
 * instead of letting getUserMedia/MediaRecorder fail unpredictably.
 *
 * onStopped fires with the finished recording's Blob both when the
 * caller explicitly calls stop() and when the max-duration cap
 * auto-stops the recording - the two are treated identically. It does
 * NOT fire after discard().
 */
export function useVoiceRecorder(onStopped: (blob: Blob) => void) {
  const [state, setState] = React.useState<RecorderState>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = React.useState(0);

  const mediaRecorderRef = React.useRef<MediaRecorder | null>(null);
  const chunksRef = React.useRef<Blob[]>([]);
  const streamRef = React.useRef<MediaStream | null>(null);
  const timerRef = React.useRef<number | null>(null);
  const discardedRef = React.useRef(false);

  const isSupported = React.useMemo(detectVoiceRecordingSupport, []);

  const cleanupStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const stopRecording = () => {
    setState("processing");
    mediaRecorderRef.current?.stop();
  };

  const start = async () => {
    if (!isSupported) {
      setError(
        "Voice input isn't supported in this browser. Try Chrome, Edge, or Firefox, or type your request instead."
      );
      setState("error");
      return;
    }

    setError(null);
    setElapsedSeconds(0);
    discardedRef.current = false;
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        cleanupStream();
        if (!discardedRef.current) {
          onStopped(blob);
        }
      };

      recorder.start();
      setState("recording");
      timerRef.current = window.setInterval(() => {
        setElapsedSeconds((s) => {
          const next = s + 1;
          // Auto-stop behaves exactly like the user tapping "stop" -
          // same onstop handler, same onStopped callback.
          if (next >= MAX_VOICE_RECORDING_SECONDS) {
            stopRecording();
          }
          return next;
        });
      }, 1000);
    } catch {
      // Covers getUserMedia rejection AND MediaRecorder construction/
      // start() throwing (e.g. an unsupported mimeType) - both are
      // inside this same try, so both clean up the stream the same way.
      setError(
        "Couldn't access your microphone. Check your browser's microphone permissions and try again."
      );
      setState("error");
      cleanupStream();
    }
  };

  /** Tap-to-stop-and-schedule action. */
  const stop = () => {
    stopRecording();
  };

  /**
   * Discard the in-progress recording without scheduling anything.
   * Distinct from stop(): onStopped is never invoked for a discarded
   * recording.
   */
  const discard = () => {
    discardedRef.current = true;
    mediaRecorderRef.current?.stop();
    cleanupStream();
    setState("idle");
    setError(null);
    setElapsedSeconds(0);
  };

  const reset = () => {
    setState("idle");
    setError(null);
    setElapsedSeconds(0);
  };

  React.useEffect(() => cleanupStream, []);

  return {
    state,
    error,
    elapsedSeconds,
    isSupported,
    maxRecordingSeconds: MAX_VOICE_RECORDING_SECONDS,
    start,
    stop,
    discard,
    reset,
    setState,
  };
}
