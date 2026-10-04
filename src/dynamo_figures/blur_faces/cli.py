"""
    File: cli.py
    Description: Command-line interface for the dynamo-blur-faces tool.
    Blurs, pixelates, or covers faces in a photo or video, fully locally.
"""

import argparse
import sys
from pathlib import Path

from dynamo_figures.blur_faces.core import FaceBlur

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.webm', '.wmv'}


def main():
    """Main function for command-line interface."""
    parser = argparse.ArgumentParser(
        prog='dynamo-blur-faces',
        description='Blur, pixelate, or cover faces in a photo or video. Runs fully locally.',
        epilog='-'
    )
    parser.add_argument('--input', type=str, required=True,
                        help='path of input image or video file.')
    parser.add_argument('--output', type=str, default=None,
                        help='output file path (default: same directory as input with _blurred suffix)')
    parser.add_argument('--style', default='blur', choices=FaceBlur.STYLES,
                        help='how to obscure faces (default: blur)')
    parser.add_argument('--shape', default='ellipse', choices=FaceBlur.SHAPES,
                        help='shape of the obscured region (default: ellipse)')
    parser.add_argument('--padding', type=float, default=0.25,
                        help='fraction to enlarge each face box on every side (default: 0.25)')
    parser.add_argument('--blur_strength', type=float, default=0.5,
                        help='blur kernel size as a fraction of face size, for --style blur (default: 0.5)')
    parser.add_argument('--pixel_blocks', type=int, default=10,
                        help='number of mosaic blocks across each face, for --style pixelate (default: 10)')
    parser.add_argument('--fill_color', type=str, default='black',
                        help='color name or hex code, for --style fill (default: black)')
    parser.add_argument('--score_threshold', type=float, default=0.6,
                        help='minimum detection confidence 0..1; lower catches more faces but more false positives (default: 0.6)')
    parser.add_argument('--nms_threshold', type=float, default=0.3,
                        help='overlap threshold for merging duplicate detections (default: 0.3)')
    parser.add_argument('--detect_max_dim', type=int, default=2048,
                        help='downscale so the longest side is at most this before detection; '
                             'raise for tiny faces, lower for speed, 0 = full resolution (default: 2048)')
    parser.add_argument('--device', default='auto', choices=FaceBlur.DEVICES,
                        help='detection device: gpu needs onnxruntime (CoreML) or onnxruntime-gpu (CUDA); '
                             'auto uses the GPU when available (default: auto)')
    parser.add_argument('--batch_size', type=int, default=8,
                        help='video only: frames detected per batch (default: 8)')
    parser.add_argument('--workers', type=int, default=None,
                        help='video only: CPU threads for detection/blurring (default: number of cores)')
    parser.add_argument('--hold_frames', type=int, default=5,
                        help='video only: keep obscuring a face for this many frames after it is lost (default: 5)')
    parser.add_argument('--smoothing', type=float, default=0.5,
                        help='video only: box smoothing between frames, 0..1 (0 = off; higher is steadier '
                             'but lags; the raw detection is always covered) (default: 0.5)')
    parser.add_argument('--start_t', type=float, default=None,
                        help='video only: trim the output to start this many seconds into the input '
                             '(default: start of video)')
    parser.add_argument('--end_t', type=float, default=None,
                        help='video only: trim the output to end this many seconds into the input '
                             '(default: end of video)')
    parser.add_argument('--no_audio', action='store_true',
                        help='video only: drop the audio track')
    parser.add_argument('--crf', type=int, default=18,
                        help='video only: H.264 quality, lower is better (default: 18)')
    parser.add_argument('--draw_boxes', action='store_true',
                        help='draw detection boxes and scores instead of obscuring (for tuning)')
    parser.add_argument('--disable_pbar', action='store_true',
                        help='disable progress bar when processing videos')

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found.")
        sys.exit(1)

    ext = input_path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        is_video = False
    elif ext in VIDEO_EXTENSIONS:
        is_video = True
    else:
        print(f"Error: Unsupported file type '{ext}'.")
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        out_ext = '.mp4' if is_video else ext
        output_path = str(input_path.parent / f'{input_path.stem}_blurred{out_ext}')

    print(" -- Load Param: input", input_path)
    print(" -- Load Param: output", output_path)
    print(" -- Load Param: style", args.style)
    print(" -- Load Param: shape", args.shape)
    print(" -- Load Param: score_threshold", args.score_threshold)
    print(" -- Load Param: device", args.device)

    if not 0 <= args.smoothing < 1:
        print("Error: --smoothing must be in [0, 1).")
        sys.exit(1)

    if not is_video and (args.start_t is not None or args.end_t is not None):
        print("Error: --start_t/--end_t only apply to videos.")
        sys.exit(1)

    if args.start_t is not None and args.start_t < 0:
        print("Error: --start_t must be >= 0.")
        sys.exit(1)

    if args.end_t is not None and args.end_t <= (args.start_t or 0.0):
        print("Error: --end_t must be greater than --start_t.")
        sys.exit(1)

    blurrer = FaceBlur(
        style=args.style,
        shape=args.shape,
        padding=args.padding,
        score_threshold=args.score_threshold,
        nms_threshold=args.nms_threshold,
        detect_max_dim=args.detect_max_dim,
        blur_strength=args.blur_strength,
        pixel_blocks=args.pixel_blocks,
        fill_color=args.fill_color,
        hold_frames=args.hold_frames,
        smoothing=args.smoothing,
        draw_boxes=args.draw_boxes,
        disable_pbar=args.disable_pbar,
        device=args.device,
        batch_size=args.batch_size,
        workers=args.workers,
    )

    if is_video:
        success = blurrer.process_video(str(input_path), output_path,
                                        keep_audio=not args.no_audio, crf=args.crf,
                                        start_t=args.start_t, end_t=args.end_t)
    else:
        success = blurrer.process_image(str(input_path), output_path)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
