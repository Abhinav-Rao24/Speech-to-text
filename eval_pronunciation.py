import os
import shutil
import sys

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config
from src.tts_engine import generate_voice_output

def main():
    # Exactly 20 domain-specific logistics sentences
    sentences = [
        "Shipment ID SH12345 has been processed.",
        "Consignment arrived at the Hyderabad Distribution Center.",
        "Package is currently held at the regional delivery hub.",
        "Dispatch confirmed from warehouse.",
        "The carrier is dispatched for container pick-up.",
        "Delivery exception occurred due to incorrect address.",
        "Customs clearance is in progress for the international order.",
        "Estimated time of arrival is scheduled for tomorrow noon.",
        "Goods transit document has been uploaded successfully.",
        "Waybill number WB9876543 has been generated.",
        "Inventory levels for SKU forty-five are critical.",
        "Order sorting completed at the automated sorting facility.",
        "Cold chain temperature logged at four degrees Celsius.",
        "Last-mile courier is out for delivery.",
        "Pallet classification updated to heavy cargo.",
        "Freight charges are billed to the receiver.",
        "The shipping manifest has been verified by the supervisor.",
        "A high-priority shipment requires immediate dock unloading.",
        "The cargo drone is loaded and ready for takeoff.",
        "Return merchandise authorization has been approved."
    ]

    output_dir = os.path.join(ROOT_DIR, "evaluation_outputs")
    os.makedirs(output_dir, exist_ok=True)
    
    provider = getattr(config, "TTS_PROVIDER", "sarvam").lower()
    print(f"Starting pronunciation evaluation using active TTS provider: '{provider}'")
    print(f"Target directory for output files: '{output_dir}'")
    print("-" * 60)

    for i, sentence in enumerate(sentences, 1):
        print(f"[{i:02d}/20] Generating voice output for: \"{sentence}\"")
        audio_path = generate_voice_output(sentence)
        
        if not audio_path or not os.path.exists(audio_path):
            print(f"  Error: Audio generation failed for sentence {i:02d}.")
            continue
        
        # Get extension of the generated file
        ext = os.path.splitext(audio_path)[1]
        dest_filename = f"eval_pronunciation_{provider}_{i:02d}{ext}"
        dest_path = os.path.join(output_dir, dest_filename)
        
        try:
            # Move the file to evaluation_outputs/
            shutil.move(audio_path, dest_path)
            print(f"  Saved to: {dest_path}")
        except Exception as e:
            print(f"  Error moving file: {e}")

    print("-" * 60)
    print("Pronunciation evaluation script execution complete.")

if __name__ == "__main__":
    main()
