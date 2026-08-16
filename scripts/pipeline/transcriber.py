import os

# Must be set before CTranslate2/MKL loads. int8 + MKL on Windows
# was crashing with: mkl_malloc: failed to allocate memory
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("CT2_USE_EXPERIMENTAL_PACKED_GEMM", "0")

import json
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from utils.cost_tracker import log_whisper_time

# Prefer tiny.en (fast). Fall back if MKL/int8 cannot allocate.
MODEL_CANDIDATES = ("tiny.en", "tiny")
COMPUTE_CANDIDATES = ("int8_float32", "float32")


def get_model():
    last_error = None
    for model_size in MODEL_CANDIDATES:
        for compute in COMPUTE_CANDIDATES:
            try:
                print(f"Loading Whisper {model_size} ({compute})...")
                model = WhisperModel(
                    model_size,
                    device="cpu",
                    compute_type=compute,
                    cpu_threads=1,
                    num_workers=1,
                )
                print(f"Loaded Whisper {model_size} ({compute})")
                return model, model_size
            except Exception as exc:
                last_error = exc
                print(f"Failed {model_size}/{compute}: {exc}")
    raise RuntimeError(f"Could not load Whisper: {last_error}") from last_error


def transcribe(audio_path):
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    model, model_size = get_model()
    segments, info = model.transcribe(
        str(audio_path),
        beam_size=1,
        vad_filter=True,
        word_timestamps=False,
        condition_on_previous_text=False,
    )

    output = []
    full_text = ""

    for segment in segments:
        text = (segment.text or "").strip()
        if not text:
            continue
        output.append({
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": text,
            "words": [],
        })
        full_text += text + " "

    return {
        "language": info.language,
        "duration": info.duration,
        "transcript": full_text,
        "segments": output,
        "whisper_model": model_size,
    }


def main():
    audio = PROJECT_ROOT / "output" / "audio.wav"
    start_time = time.time()
    result = transcribe(audio)
    elapsed = time.time() - start_time
    log_whisper_time(elapsed)

    out = PROJECT_ROOT / "output" / "transcript.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print(f"Whisper {result['whisper_model']} finished in {elapsed:.1f}s -> {out}")


if __name__ == "__main__":
    main()
