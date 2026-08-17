import os

# Must be set before CTranslate2/MKL loads. int8 + MKL on Windows
# was crashing with: mkl_malloc: failed to allocate memory
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("MKL_DISABLE_FAST_MM", "1")
os.environ.setdefault("CT2_USE_EXPERIMENTAL_PACKED_GEMM", "0")
os.environ.setdefault("CT2_FORCE_CPU_ISA", "GENERIC")
os.environ.setdefault("ONNXRUNTIME_INTRA_OP_NUM_THREADS", "1")
os.environ.setdefault("ONNXRUNTIME_INTER_OP_NUM_THREADS", "1")

import gc
import json
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from utils.cost_tracker import log_whisper_time

# float32 first: int8/int8_float32 hits mkl_malloc on this Windows CPU.
MODEL_CANDIDATES = ("tiny.en", "tiny")
COMPUTE_CANDIDATES = ("float32", "int8_float32")


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


def transcribe_wav(model, audio_path):
    """
    Transcribe one short wav. Consume the generator immediately so
    MKL encode errors surface here, not later during iteration.
    """
    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=1,
        vad_filter=False,
        word_timestamps=False,
        condition_on_previous_text=False,
        without_timestamps=False,
    )
    return list(segments_iter), info


class WhisperSession:
    """Allows reloading the model after an MKL allocator crash."""

    def __init__(self):
        self.model, self.size = get_model()

    def reload(self):
        print("Reloading Whisper after a memory allocator crash...")
        try:
            del self.model
        except Exception:
            pass
        self.model = None
        gc.collect()
        self.model, self.size = get_model()


def transcribe(audio_path):
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    model, model_size = get_model()
    segments, info = transcribe_wav(model, audio_path)

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
