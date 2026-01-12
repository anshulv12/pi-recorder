#!/usr/bin/env python3
"""
OAK-D Continuous Recorder for Raspberry Pi

Runs continuously when Pi boots, saving recordings to sessions.
Each session is saved to recordings/session_YYYYMMDD_HHMMSS/

Designed for headless operation - no preview window.
"""

import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

# Add hand_tracker to path
sys.path.insert(0, str(Path(__file__).parent / "hand_tracker"))
from HandTrackerEdge import HandTracker

HAND_LANDMARK_NAMES = [
    "WRIST",
    "THUMB_CMC", "THUMB_MCP", "THUMB_IP", "THUMB_TIP",
    "INDEX_FINGER_MCP", "INDEX_FINGER_PIP", "INDEX_FINGER_DIP", "INDEX_FINGER_TIP",
    "MIDDLE_FINGER_MCP", "MIDDLE_FINGER_PIP", "MIDDLE_FINGER_DIP", "MIDDLE_FINGER_TIP",
    "RING_FINGER_MCP", "RING_FINGER_PIP", "RING_FINGER_DIP", "RING_FINGER_TIP",
    "PINKY_MCP", "PINKY_PIP", "PINKY_DIP", "PINKY_TIP",
]

BODY_KEYPOINT_NAMES = [
    "NOSE",
    "LEFT_EYE", "RIGHT_EYE",
    "LEFT_EAR", "RIGHT_EAR",
    "LEFT_SHOULDER", "RIGHT_SHOULDER",
    "LEFT_ELBOW", "RIGHT_ELBOW",
    "LEFT_WRIST", "RIGHT_WRIST",
    "LEFT_HIP", "RIGHT_HIP",
    "LEFT_KNEE", "RIGHT_KNEE",
    "LEFT_ANKLE", "RIGHT_ANKLE",
]

# Global flag for graceful shutdown
running = True


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    global running
    print("\nShutdown signal received, finishing current session...")
    running = False


def get_disk_usage_percent(path: Path) -> float:
    """Get disk usage percentage for the given path."""
    import shutil
    total, used, free = shutil.disk_usage(path)
    return (used / total) * 100


def record_session(
    output_dir: Path,
    max_duration: float = 3600.0,  # 1 hour max per session
    max_disk_usage: float = 90.0,  # Stop if disk > 90% full
) -> bool:
    """
    Record a single session.

    Returns True if should continue recording, False if should stop.
    """
    global running

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Initializing tracker...")

    # Initialize hand tracker BEFORE creating folder
    try:
        tracker = HandTracker(
            input_src="rgb",
            use_world_landmarks=True,
            xyz=True,
            solo=False,
            resolution="full",  # 1920x1080
            lm_model="lite",
            stats=False,
            trace=0,
        )
    except Exception as e:
        print(f"Error initializing tracker: {e}")
        print("Waiting 5 seconds and retrying...")
        time.sleep(5)
        return running  # Continue trying - DON'T create folder

    # Try to get first frame to verify camera is working
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Testing camera...")
    try:
        first_frame, _, _ = tracker.next_frame()
        if first_frame is None:
            print("Camera not returning frames - check hardware connection")
            print("Waiting 5 seconds and retrying...")
            try:
                tracker.exit()
            except:
                pass
            time.sleep(5)
            return running  # DON'T create folder
    except Exception as e:
        print(f"Error getting first frame: {e}")
        print("Waiting 5 seconds and retrying...")
        try:
            tracker.exit()
        except:
            pass
        time.sleep(5)
        return running  # DON'T create folder

    # Only create session folder AFTER we verify camera works
    output_dir.mkdir(parents=True, exist_ok=True)
    rgb_dir = output_dir / "rgb_frames"
    rgb_dir.mkdir(exist_ok=True)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Started session: {output_dir.name}")

    # Get camera intrinsics
    intrinsics = {
        "fx": tracker.resolution[0] * 0.8,
        "fy": tracker.resolution[0] * 0.8,
        "cx": tracker.resolution[0] / 2,
        "cy": tracker.resolution[1] / 2,
        "width": tracker.resolution[0],
        "height": tracker.resolution[1],
    }

    try:
        import depthai as dai
        calib = tracker.device.readCalibration()
        intrinsic_matrix = calib.getCameraIntrinsics(dai.CameraBoardSocket.CAM_A, 1920, 1080)
        intrinsics = {
            "fx": intrinsic_matrix[0][0],
            "fy": intrinsic_matrix[1][1],
            "cx": intrinsic_matrix[0][2],
            "cy": intrinsic_matrix[1][2],
            "width": 1920,
            "height": 1080,
        }
    except Exception as e:
        print(f"Could not get calibration: {e}")

    with open(output_dir / "camera_info.json", "w") as f:
        json.dump({"intrinsics": intrinsics}, f, indent=2)

    # Write header info to poses file (will append frames as JSONL)
    poses_file = output_dir / "hand_poses.jsonl"
    with open(poses_file, "w") as f:
        # First line is header with metadata
        header = {
            "_type": "header",
            "intrinsics": intrinsics,
            "landmark_names": HAND_LANDMARK_NAMES,
            "body_keypoint_names": BODY_KEYPOINT_NAMES,
        }
        f.write(json.dumps(header) + "\n")

    frame_count = 0
    timestamps = []
    start_time = time.time()
    last_status_time = start_time

    while running:
        elapsed = time.time() - start_time

        # Check max duration
        if elapsed > max_duration:
            print(f"Session duration limit reached ({max_duration}s)")
            break

        # Check disk space every 30 seconds
        if time.time() - last_status_time > 30:
            disk_usage = get_disk_usage_percent(output_dir)
            if disk_usage > max_disk_usage:
                print(f"Disk usage too high ({disk_usage:.1f}%), stopping")
                running = False
                break
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Frame {frame_count}, Disk: {disk_usage:.1f}%")
            last_status_time = time.time()

        # Get next frame
        try:
            frame, hands, bag = tracker.next_frame()
        except Exception as e:
            print(f"Error getting frame: {e}")
            break

        if frame is None:
            print("No frame received, ending session")
            break

        timestamp_ms = int(elapsed * 1000)

        # Process hands
        hands_data = []
        for hand in hands:
            hand_data = {
                "handedness": hand.label.capitalize(),
                "confidence": float(hand.lm_score),
            }

            if hasattr(hand, 'landmarks') and hand.landmarks is not None:
                hand_data["landmarks_2d"] = hand.landmarks.tolist()
            else:
                hand_data["landmarks_2d"] = []

            if hasattr(hand, 'world_landmarks') and hand.world_landmarks is not None:
                hand_data["landmarks_3d"] = hand.world_landmarks.tolist()
            else:
                hand_data["landmarks_3d"] = []

            if hasattr(hand, 'xyz') and hand.xyz is not None:
                xyz = hand.xyz
                hand_data["palm_xyz"] = xyz.tolist() if hasattr(xyz, 'tolist') else list(xyz)

            hands_data.append(hand_data)

        # Process body
        body_data = None
        body = bag.get("body", None) if bag else None
        if body is not None and hasattr(body, 'keypoints'):
            body_data = {
                "keypoints_2d": body.keypoints.tolist(),
                "scores": body.scores.tolist() if hasattr(body, 'scores') else [],
            }

        # Save frame (use JPEG for smaller files on Pi)
        frame_name = f"frame_{frame_count:06d}"
        cv2.imwrite(str(rgb_dir / f"{frame_name}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        # Write pose immediately to JSONL (power-loss safe)
        frame_pose = {
            "_type": "frame",
            "frame_idx": frame_count,
            "timestamp_ms": timestamp_ms,
            "hands": hands_data,
            "body": body_data,
        }
        with open(poses_file, "a") as f:
            f.write(json.dumps(frame_pose) + "\n")

        timestamps.append(timestamp_ms)
        frame_count += 1

    # Cleanup tracker
    try:
        tracker.exit()
    except:
        pass

    # Save final metadata (poses already saved incrementally to JSONL)
    if frame_count > 0:
        actual_duration = timestamps[-1] / 1000.0 if timestamps else 0

        with open(output_dir / "metadata.json", "w") as f:
            json.dump({
                "recording_date": datetime.now().isoformat(),
                "duration_seconds": actual_duration,
                "frame_count": frame_count,
                "fps": frame_count / actual_duration if actual_duration > 0 else 0,
            }, f, indent=2)

        print(f"Session complete: {frame_count} frames, {actual_duration:.1f}s")
    else:
        print("No frames recorded in this session")

    return running


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OAK-D Continuous Recorder")
    parser.add_argument("--recordings-dir", "-o", type=str, default="recordings",
                        help="Directory to save recordings")
    parser.add_argument("--session-duration", type=float, default=3600.0,
                        help="Max duration per session in seconds (default: 1 hour)")
    parser.add_argument("--max-disk-usage", type=float, default=90.0,
                        help="Stop recording if disk usage exceeds this percent")
    args = parser.parse_args()

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    recordings_dir = Path(args.recordings_dir)
    recordings_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("OAK-D Continuous Recorder")
    print("=" * 60)
    print(f"Recordings directory: {recordings_dir.absolute()}")
    print(f"Session duration: {args.session_duration}s")
    print(f"Max disk usage: {args.max_disk_usage}%")
    print("Press Ctrl+C to stop")
    print("=" * 60)

    # Main recording loop
    while running:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = recordings_dir / f"session_{timestamp}"

        should_continue = record_session(
            session_dir,
            max_duration=args.session_duration,
            max_disk_usage=args.max_disk_usage,
        )

        if not should_continue:
            break

        # Brief pause between sessions
        print("Starting new session in 2 seconds...")
        time.sleep(2)

    print("\nRecorder stopped.")


if __name__ == "__main__":
    main()
