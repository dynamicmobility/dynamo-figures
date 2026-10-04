#!/usr/bin/env python3
"""
    File: pic_from_video.py
    Description: A python script to extract a single frame from a video file.
    Extracts a single frame from a video file and saves it as an image.
    Supports various video formats and allows specification of frame number or time.
"""

import argparse
import cv2
import os
import sys
from pathlib import Path


class FrameExtractor:
    """Class for extracting frames from video files."""

    def __init__(self, video_path, frame_number=None, time_seconds=None):
        """
        Initialize FrameExtractor.
        
        Args:
            video_path: Path to the input video file
            frame_number: Frame number to extract (0-indexed)
            time_seconds: Time in seconds to extract frame from
        """
        self.video_path = video_path
        self.frame_number = frame_number
        self.time_seconds = time_seconds
        self.fps = None
        self.frame_count = None
        self.width = None
        self.height = None
        self.duration = None

    def _load_video_info(self, cap):
        """Load video properties from capture object."""
        self.fps = cap.get(cv2.CAP_PROP_FPS)
        self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.duration = self.frame_count / self.fps if self.fps > 0 else 0

    def get_video_info(self):
        """
        Get video information without extracting a frame.
        
        Returns:
            dict: Video information or None if video cannot be opened
        """
        if not os.path.exists(self.video_path):
            print(f"Error: Video file '{self.video_path}' not found.")
            return None

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video file '{self.video_path}'.")
            return None

        self._load_video_info(cap)
        cap.release()

        return {
            'path': self.video_path,
            'width': self.width,
            'height': self.height,
            'frame_count': self.frame_count,
            'fps': self.fps,
            'duration': self.duration
        }

    def extract_frame(self, output_path):
        """
        Extract a frame from the video and save it as an image.
        
        Args:
            output_path: Path where the extracted frame will be saved
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Check if video file exists
        if not os.path.exists(self.video_path):
            print(f"Error: Video file '{self.video_path}' not found.")
            return False

        # Open video capture
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video file '{self.video_path}'.")
            return False

        # Load video properties
        self._load_video_info(cap)

        print(f" -- Video info: {self.frame_count} frames, {self.fps:.2f} FPS, {self.duration:.2f}s duration")

        # Determine which frame to extract
        target_frame = 0

        if self.time_seconds is not None:
            # Convert time to frame number
            target_frame = int(self.time_seconds * self.fps)
            print(f" -- Extracting frame at {self.time_seconds}s (frame {target_frame})")
        elif self.frame_number is not None:
            target_frame = self.frame_number
            print(f" -- Extracting frame {self.frame_number}")
        else:
            # Default to middle frame
            target_frame = self.frame_count // 2
            print(f" -- No frame/time specified, extracting middle frame ({target_frame})")

        # Validate frame number
        if target_frame < 0 or target_frame >= self.frame_count:
            print(f"Error: Frame {target_frame} is out of range (0-{self.frame_count-1})")
            cap.release()
            return False

        # Set video position to target frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

        # Read the frame
        ret, frame = cap.read()

        if not ret:
            print(f"Error: Could not read frame {target_frame}")
            cap.release()
            return False

        # Create output directory if it doesn't exist
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save the frame
        success = cv2.imwrite(output_path, frame)

        if success:
            print(f" -- Frame saved to: {output_path}")
            print(f" -- Image dimensions: {frame.shape[1]}x{frame.shape[0]}")
        else:
            print(f"Error: Could not save frame to '{output_path}'")

        # Clean up
        cap.release()

        return success


def main():
    """Main function for command-line interface."""
    parser = argparse.ArgumentParser(
        prog='dynamo-pic-from-video',
        description='Extract a frame from a video file and save it as an image.',
        epilog='-'
    )
    parser.add_argument('--video_path', type=str, required=True,
                        help='path of input video file.')
    parser.add_argument('--output', type=str, default=None,
                        help='output file path (default: same directory as video with _frame.jpg extension)')
    parser.add_argument('--frame', type=int, default=None,
                        help='frame number to extract (0-indexed). Cannot be used with --time.')
    parser.add_argument('--time', type=float, default=None,
                        help='time in seconds to extract frame from. Cannot be used with --frame.')
    parser.add_argument('--info_only', action='store_true',
                        help='only display video information without extracting a frame')

    args = parser.parse_args()

    # Read command-line parameters
    path = args.video_path
    frame_number = args.frame
    time_seconds = args.time

    print(" -- Load Param: video path", path)
    print(" -- Load Param: frame", frame_number)
    print(" -- Load Param: time", time_seconds)

    # Check for mutually exclusive arguments
    if frame_number is not None and time_seconds is not None:
        print("Error: Cannot specify both --frame and --time arguments.")
        sys.exit(1)

    # Create frame extractor
    extractor = FrameExtractor(path, frame_number, time_seconds)

    # If info-only mode, just display video info
    if args.info_only:
        info = extractor.get_video_info()
        if info is None:
            sys.exit(1)

        print(f" -- Video: {info['path']}")
        print(f" -- Dimensions: {info['width']}x{info['height']}")
        print(f" -- Frames: {info['frame_count']}")
        print(f" -- FPS: {info['fps']:.2f}")
        print(f" -- Duration: {info['duration']:.2f} seconds")
        return

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        video_path = Path(path)
        output_path = str(video_path.parent / f'{video_path.stem}_frame.jpg')

    print(" -- Load Param: output", output_path)

    # Extract the frame
    success = extractor.extract_frame(output_path)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()