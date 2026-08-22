"""
Isolated Whisper process. Import nothing else first — MKL crashes when
faster-whisper shares a process with FastAPI/numpy/Gemini.

One-shot:  python whisper_worker.py audio.wav
Server:    python whisper_worker.py --serve
           stdin  = JSON line {"wav": "path"}
           stdout = JSON line [segments]
"""
import os
import sys
import json

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

from faster_whisper import WhisperModel


def _cpu_threads():
    count = os.cpu_count() or 4
    return max(2, min(8, count))


def load_model():
    threads = _cpu_threads()
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["MKL_NUM_THREADS"] = str(threads)
    # Isolated worker: int8 + SIMD is safe here. GENERIC+float32 was ~2x slower
    # than the audio itself on a 8-minute scan.
    try:
        return WhisperModel(
            "tiny.en",
            device="cpu",
            compute_type="int8",
            cpu_threads=threads,
            num_workers=1,
        )
    except Exception:
        return WhisperModel(
            "tiny.en",
            device="cpu",
            compute_type="float32",
            cpu_threads=threads,
            num_workers=1,
        )


def transcribe_wav(model, wav, word_timestamps=False):
    segments_iter, _info = model.transcribe(
        wav,
        beam_size=1,
        vad_filter=True,
        word_timestamps=bool(word_timestamps),
        condition_on_previous_text=False,
    )
    out = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        words = []
        for word in getattr(seg, "words", None) or []:
            token = (getattr(word, "word", "") or "").strip()
            if not token:
                continue
            words.append({
                "word": token,
                "start": round(float(word.start), 2),
                "end": round(float(word.end), 2),
            })
        out.append({
            "start": round(float(seg.start), 2),
            "end": round(float(seg.end), 2),
            "text": text,
            "words": words,
        })
    return out


def serve(model):
    for raw in sys.stdin:
        line = (raw or "").strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps({"error": "bad json"}), flush=True)
            continue
        if payload.get("stop"):
            break
        wav = payload.get("wav")
        if not wav:
            print(json.dumps({"error": "missing wav"}), flush=True)
            continue
        try:
            print(
                json.dumps(transcribe_wav(model, wav, payload.get("words"))),
                flush=True,
            )
        except Exception as exc:
            print(json.dumps({"error": str(exc)[-500:]}), flush=True)


def main():
    if len(sys.argv) < 2:
        print("usage: whisper_worker.py <audio.wav|--serve>", file=sys.stderr)
        sys.exit(2)

    model = load_model()
    if sys.argv[1] == "--serve":
        serve(model)
        return

    json.dump(transcribe_wav(model, sys.argv[1]), sys.stdout)


if __name__ == "__main__":
    main()
