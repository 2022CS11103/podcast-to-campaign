"""
Isolated Whisper process. Import nothing else first — MKL crashes when
faster-whisper shares a process with FastAPI/numpy/Gemini.
"""
import os
import sys
import json

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MKL_DISABLE_FAST_MM", "1")
os.environ.setdefault("CT2_USE_EXPERIMENTAL_PACKED_GEMM", "0")
os.environ.setdefault("CT2_FORCE_CPU_ISA", "GENERIC")

from faster_whisper import WhisperModel


def main():
    if len(sys.argv) < 2:
        print("usage: whisper_worker.py <audio.wav>", file=sys.stderr)
        sys.exit(2)

    wav = sys.argv[1]
    model = WhisperModel(
        "tiny.en",
        device="cpu",
        compute_type="float32",
        cpu_threads=1,
        num_workers=1,
    )
    segments_iter, _info = model.transcribe(
        wav,
        beam_size=1,
        vad_filter=False,
        word_timestamps=False,
        condition_on_previous_text=False,
    )
    out = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        out.append({
            "start": round(float(seg.start), 2),
            "end": round(float(seg.end), 2),
            "text": text,
        })
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
