# Models

`face_detection_yunet_2023mar.onnx` is OpenCV's YuNet face detector from
[opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
(MIT license). It has been edited so the batch, height, and width inputs are
symbolic, and stale intermediate shapes have been removed. This lets ONNX Runtime
(CoreML/CUDA) run it at any resolution. OpenCV's `FaceDetectorYN` loads it
unchanged.
