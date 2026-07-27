import os
import cv2
import numpy as np
from PIL import Image

class DocumentPreprocessor:
    @staticmethod
    def preprocess_image(input_path: str, output_path: str = None) -> str:
        """
        Enhances document images (phone photos, receipts) by performing:
        1. Grayscale conversion
        2. Denoising
        3. Automatic deskewing / orientation correction
        4. Adaptive thresholding / contrast normalization
        """
        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_preprocessed.png"

        try:
            # Read image using OpenCV
            image = cv2.imread(input_path)
            if image is None:
                # Fallback to PIL if OpenCV cannot read directly
                pil_img = Image.open(input_path)
                image = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

            # Convert to Grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Deskewing calculation via minimum area rect on non-zero threshold
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) > 0:
                angle = cv2.minAreaRect(coords)[-1]
                if angle < -45:
                    angle = -(90 + angle)
                elif angle > 45:
                    angle = 90 - angle
                
                # Perform rotation if skew angle is significant (> 0.5 deg and < 45 deg)
                if abs(angle) > 0.5 and abs(angle) < 45:
                    (h, w) = image.shape[:2]
                    center = (w // 2, h // 2)
                    M = cv2.getRotationMatrix2D(center, angle, 1.0)
                    gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

            # Denoise
            denoised = cv2.fastNlMeansDenoising(gray, h=10)

            # Contrast enhancement (CLAHE - Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(denoised)

            # Save result
            cv2.imwrite(output_path, enhanced)
            return output_path

        except Exception as e:
            print(f"[Preprocessor Warning] Preprocessing failed: {e}. Returning original image.")
            return input_path

    @staticmethod
    def get_image_bytes(file_path: str) -> bytes:
        """Reads file as bytes for API payload transmission."""
        with open(file_path, "rb") as f:
            return f.read()
