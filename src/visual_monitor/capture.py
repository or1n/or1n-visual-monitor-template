import cv2
import numpy as np


def best_template_match(current_frame, templates):
    if current_frame is None or not templates:
        return 0.0

    current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    current_edges = cv2.Canny(current_gray, 50, 150)
    best_score = 0.0

    orb = cv2.ORB_create(nfeatures=2000)
    current_kp, current_des = orb.detectAndCompute(current_gray, None)

    for template in templates:
        if template is None:
            continue

        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        template_h, template_w = template_gray.shape[:2]
        if template_h <= 0 or template_w <= 0:
            continue

        template_edges = cv2.Canny(template_gray, 50, 150)
        template_kp, template_des = orb.detectAndCompute(template_gray, None)

        feature_score = 0.0
        if template_des is not None and current_des is not None and len(template_des) > 8 and len(current_des) > 8:
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
            matches = matcher.knnMatch(template_des, current_des, k=2)
            good_matches = 0
            for match_a, match_b in matches:
                if match_a is None or match_b is None:
                    continue
                if match_a.distance < 0.75 * match_b.distance:
                    good_matches += 1
            feature_score = min(1.0, good_matches / 12.0)

        for scale in (0.75, 0.9, 1.0, 1.15, 1.3):
            scaled_w = max(12, int(template_w * scale))
            scaled_h = max(12, int(template_h * scale))
            scaled_template = cv2.resize(template_gray, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
            scaled_edges = cv2.resize(template_edges, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)

            result = cv2.matchTemplate(current_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
            _, template_max_val, _, _ = cv2.minMaxLoc(result)

            edge_result = cv2.matchTemplate(current_edges, scaled_edges, cv2.TM_CCOEFF_NORMED)
            _, edge_max_val, _, _ = cv2.minMaxLoc(edge_result)

            combined_score = max(float(template_max_val), float(edge_max_val))
            if feature_score > 0.15:
                combined_score = max(combined_score, 0.7 * float(template_max_val) + 0.3 * feature_score)

            if combined_score > best_score:
                best_score = float(combined_score)

    return best_score
