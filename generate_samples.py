"""
generate_samples.py - Creates clean, stylized sample face portraits
for instant 1-click testing of BioScan AI without requiring a physical webcam.
"""

import os
from PIL import Image, ImageDraw

def create_sample_portraits():
    samples_dir = os.path.join(os.path.dirname(__file__), "static", "samples")
    os.makedirs(samples_dir, exist_ok=True)
    
    samples_config = [
        {
            "filename": "sample_1_elena.jpg",
            "name": "Elena Vance",
            "bg_color": (32, 42, 58),
            "skin_color": (235, 192, 165),
            "hair_color": (45, 30, 20),
            "eye_color": (50, 110, 80),
            "hair_type": "long_curls",
            "gender": "female"
        },
        {
            "filename": "sample_2_marcus.jpg",
            "name": "Marcus Chen",
            "bg_color": (28, 36, 44),
            "skin_color": (240, 205, 175),
            "hair_color": (20, 20, 25),
            "eye_color": (55, 40, 30),
            "hair_type": "neat_crop",
            "gender": "male"
        },
        {
            "filename": "sample_3_amari.jpg",
            "name": "Amari Diallo",
            "bg_color": (40, 32, 48),
            "skin_color": (115, 75, 52),
            "hair_color": (15, 15, 18),
            "eye_color": (60, 42, 30),
            "hair_type": "buzz_fade",
            "gender": "male"
        },
        {
            "filename": "sample_4_astrid.jpg",
            "name": "Astrid Lindqvist",
            "bg_color": (25, 45, 52),
            "skin_color": (250, 222, 200),
            "hair_color": (210, 180, 110),
            "eye_color": (70, 130, 180),
            "hair_type": "straight_bob",
            "gender": "female"
        }
    ]
    
    W, H = 400, 480
    
    for s in samples_config:
        img = Image.new("RGB", (W, H), s["bg_color"])
        draw = ImageDraw.Draw(img)
        
        # Subdued gradient / vignette background
        for r in range(0, 240, 12):
            alpha = max(0, 255 - r)
            draw.ellipse([W//2 - r*2, H//2 - r*2, W//2 + r*2, H//2 + r*2], outline=(s["bg_color"][0]+10, s["bg_color"][1]+10, s["bg_color"][2]+15))
        
        # Shoulders / Torso
        shoulder_color = (max(0, s["bg_color"][0] - 10), max(0, s["bg_color"][1] - 10), max(0, s["bg_color"][2] - 5))
        draw.ellipse([50, 340, 350, 600], fill=shoulder_color)
        
        # Neck
        neck_color = (int(s["skin_color"][0]*0.9), int(s["skin_color"][1]*0.9), int(s["skin_color"][2]*0.9))
        draw.rectangle([170, 260, 230, 360], fill=neck_color)
        
        # Head / Jaw oval
        head_box = [120, 100, 280, 310]
        draw.ellipse(head_box, fill=s["skin_color"])
        
        # Hair base (behind or on top)
        if s["hair_type"] == "long_curls":
            draw.ellipse([90, 70, 310, 330], fill=s["hair_color"])
            draw.ellipse(head_box, fill=s["skin_color"]) # redraw face over back hair
            # Bangs / Front hair
            draw.chord([110, 70, 290, 200], 180, 360, fill=s["hair_color"])
            draw.polygon([(110, 130), (130, 260), (100, 320), (85, 200)], fill=s["hair_color"])
            draw.polygon([(290, 130), (270, 260), (300, 320), (315, 200)], fill=s["hair_color"])
        elif s["hair_type"] == "neat_crop":
            draw.chord([115, 80, 285, 200], 180, 360, fill=s["hair_color"])
            draw.rectangle([115, 120, 130, 200], fill=s["hair_color"])
            draw.rectangle([270, 120, 285, 200], fill=s["hair_color"])
        elif s["hair_type"] == "buzz_fade":
            draw.chord([118, 90, 282, 190], 180, 360, fill=s["hair_color"])
        elif s["hair_type"] == "straight_bob":
            draw.ellipse([105, 80, 295, 260], fill=s["hair_color"])
            draw.ellipse(head_box, fill=s["skin_color"])
            draw.chord([115, 80, 285, 185], 180, 360, fill=s["hair_color"])
            draw.rectangle([105, 130, 128, 270], fill=s["hair_color"])
            draw.rectangle([272, 130, 295, 270], fill=s["hair_color"])
            
        # Eyebrows
        brow_color = (int(s["hair_color"][0]*0.8), int(s["hair_color"][1]*0.8), int(s["hair_color"][2]*0.8))
        draw.line([(145, 175), (180, 172)], fill=brow_color, width=4)
        draw.line([(220, 172), (255, 175)], fill=brow_color, width=4)
        
        # Eyes
        # Sclera
        draw.ellipse([145, 185, 180, 205], fill=(245, 245, 250))
        draw.ellipse([220, 185, 255, 205], fill=(245, 245, 250))
        # Iris
        draw.ellipse([155, 187, 172, 203], fill=s["eye_color"])
        draw.ellipse([228, 187, 245, 203], fill=s["eye_color"])
        # Pupil
        draw.ellipse([160, 191, 167, 199], fill=(10, 10, 15))
        draw.ellipse([233, 191, 240, 199], fill=(10, 10, 15))
        # Eye highlight
        draw.ellipse([162, 192, 165, 195], fill=(255, 255, 255))
        draw.ellipse([235, 192, 238, 195], fill=(255, 255, 255))
        
        # Nose
        nose_color = (int(s["skin_color"][0]*0.82), int(s["skin_color"][1]*0.82), int(s["skin_color"][2]*0.82))
        draw.line([(200, 185), (196, 225)], fill=nose_color, width=2)
        draw.arc([192, 220, 208, 232], 0, 180, fill=nose_color, width=2)
        
        # Mouth / Lips
        lip_color = (int(s["skin_color"][0]*0.9 + 40), int(s["skin_color"][1]*0.7), int(s["skin_color"][2]*0.7))
        draw.ellipse([175, 250, 225, 268], fill=lip_color)
        draw.line([(175, 259), (225, 259)], fill=(int(lip_color[0]*0.8), int(lip_color[1]*0.7), int(lip_color[2]*0.7)), width=2)
        
        # Subtle cheek tone
        cheek_color = (int(min(255, s["skin_color"][0] + 15)), int(max(0, s["skin_color"][1] - 8)), int(max(0, s["skin_color"][2] - 8)))
        draw.ellipse([135, 215, 165, 235], fill=cheek_color)
        draw.ellipse([235, 215, 265, 235], fill=cheek_color)

        filepath = os.path.join(samples_dir, s["filename"])
        img.save(filepath, "JPEG", quality=92)
        print(f"Generated sample: {filepath}")

if __name__ == "__main__":
    create_sample_portraits()
