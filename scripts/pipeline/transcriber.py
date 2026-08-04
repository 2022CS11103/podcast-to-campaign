import json
import sys
import time
from pathlib import Path
from faster_whisper import WhisperModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from utils.cost_tracker import log_whisper_time

model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8"
)


def transcribe(audio_path):

    segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        word_timestamps=True
    )

    output = []

    full_text = ""

    for segment in segments:

        words = []

        if segment.words:

            for word in segment.words:

                words.append({

                    "word": word.word,

                    "start": round(word.start, 2),

                    "end": round(word.end, 2)

                })

        output.append({

            "start": round(segment.start,2),

            "end": round(segment.end,2),

            "text": segment.text.strip(),

            "words": words

        })

        full_text += segment.text.strip()+" "

    return {

        "language": info.language,

        "duration": info.duration,

        "transcript": full_text,

        "segments": output

    }


def main():

    audio = PROJECT_ROOT/"output"/"audio.wav"

    start_time = time.time()
    result = transcribe(audio)
    elapsed = time.time() - start_time
    log_whisper_time(elapsed)

    out = PROJECT_ROOT/"output"/"transcript.json"

    with open(out,"w",encoding="utf-8") as f:

        json.dump(result,f,indent=4,ensure_ascii=False)

    print(out)


if __name__=="__main__":
    main()