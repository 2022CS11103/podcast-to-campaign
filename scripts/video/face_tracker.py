import json
from pathlib import Path

import cv2
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Load YOLO model once
model = YOLO("yolov8n.pt")


def detect_main_person(frame):
    """
    Detect the largest person in the frame.
    Returns None if no person is found.
    """

    results = model.predict(
        frame,
        classes=[0],      # Only person class
        conf=0.35,
        verbose=False
    )

    boxes = results[0].boxes

    if len(boxes) == 0:
        return None

    best_box = None
    best_area = 0

    for box in boxes:

        x1, y1, x2, y2 = box.xyxy[0].tolist()

        area = (x2 - x1) * (y2 - y1)

        if area > best_area:
            best_area = area
            best_box = box

    x1, y1, x2, y2 = best_box.xyxy[0].tolist()

    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2

    return {
        "bbox": {
            "x1": round(x1, 2),
            "y1": round(y1, 2),
            "x2": round(x2, 2),
            "y2": round(y2, 2),
        },
        "center": {
            "x": round(cx, 2),
            "y": round(cy, 2),
        },
        "confidence": round(float(best_box.conf[0]), 3)
    }


def process_video(video_path):

    cap = cv2.VideoCapture(str(video_path))

    fps = cap.get(cv2.CAP_PROP_FPS)

    frame_number = 0

    detections = []

    # YOLO on every frame of a 30s clip is the slowest/costliest local step.
    # Every 5th frame (~6 fps at 30fps) is enough to follow a talking head.
    STRIDE = 5

    while True:

        success, frame = cap.read()

        if not success:
            break

        if frame_number % STRIDE != 0:
            frame_number += 1
            continue

        person = detect_main_person(frame)

        if person:

            detections.append({

                "frame": frame_number,

                "time": round(frame_number / fps, 2),

                **person

            })

        frame_number += 1

    cap.release()

    return detections


def main():

    shorts_dir = PROJECT_ROOT / "output" / "shorts"

    tracking_dir = PROJECT_ROOT / "output" / "tracking"
    tracking_dir.mkdir(exist_ok=True)

    videos = sorted(shorts_dir.glob("*.mp4"))

    if not videos:
        print("No shorts found.")
        return

    for video in videos:

        print(f"Tracking speaker in {video.name}")

        detections = process_video(video)

        output_file = tracking_dir / f"{video.stem}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(
                detections,
                f,
                indent=4
            )

        print(f"Saved -> {output_file}")

    print("\n✅ Face tracking completed.")


if __name__ == "__main__":
    main()