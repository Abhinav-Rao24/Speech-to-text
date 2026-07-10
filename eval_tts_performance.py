import os
import sys
import time
import pygame

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config
from src.tts_engine import generate_voice_output

def main():
    # Exactly 20 testing strings categorized across distinct scaling lengths (Short, Medium, Long)
    test_strings = [
        # Short (7 strings)
        {"length": "Short", "text": "Order dispatched."},
        {"length": "Short", "text": "Cargo checked in."},
        {"length": "Short", "text": "Verify shipment ID."},
        {"length": "Short", "text": "Arrival delayed."},
        {"length": "Short", "text": "Gate number four."},
        {"length": "Short", "text": "Processing customs now."},
        {"length": "Short", "text": "Pallet loaded."},

        # Medium (6 strings)
        {"length": "Medium", "text": "The delivery courier is heading to the regional sorting facility now."},
        {"length": "Medium", "text": "A custom inspection clearance form must accompany this heavy cargo order."},
        {"length": "Medium", "text": "Please update the freight manifest tracking status immediately upon delivery completion."},
        {"length": "Medium", "text": "The temperature tracking logger recorded three degrees Celsius during distribution transit."},
        {"length": "Medium", "text": "Warehouse supervisors are currently checking inventory levels for this high-demand item."},
        {"length": "Medium", "text": "All dispatch vehicles must pass security screening before leaving the main gate."},

        # Long (7 strings)
        {"length": "Long", "text": "Please verify that the shipping manifest is absolutely correct and ensure all high-priority container pallets are safely loaded onto the delivery truck before dispatching the carrier from the loading dock."},
        {"length": "Long", "text": "The international consignment arrived at the regional distribution center after experiencing customs clearance delays at the border due to incorrect waybill documentation which has now been updated."},
        {"length": "Long", "text": "We need to coordinate with the local logistics team to guarantee that last-mile courier delivery is successfully completed before the end of the business day for all premium subscribers."},
        {"length": "Long", "text": "The temperature controlled logistics trailer reported a temperature fluctuation of five degrees Celsius which triggered an automated warning notification to the supply chain management system and operators."},
        {"length": "Long", "text": "A high-priority shipment containing medical supplies and critical spare parts has been cataloged at the main terminal and requires immediate unloading and prompt distribution to the warehouse."},
        {"length": "Long", "text": "The automated sorting conveyor belt system is operating at maximum capacity to ensure all outgoing orders are classified and packed before the overnight carrier arrives."},
        {"length": "Long", "text": "Return merchandise authorization documents must be printed and signed by the receiver before any refunds or replacement cargo items can be dispatched from our regional warehouse."}
    ]

    print("Initializing Pygame mixer...")
    try:
        pygame.mixer.init()
    except Exception as e:
        print(f"Failed to initialize pygame mixer: {e}. Audio playback measurements might fail.", file=sys.stderr)

    provider = getattr(config, "TTS_PROVIDER", "sarvam").lower()
    print(f"Starting performance profiling using active TTS provider: '{provider}'")
    print("-" * 80)

    # Dictionary to collect results by category
    results = {
        "Short": [],
        "Medium": [],
        "Long": []
    }

    for i, item in enumerate(test_strings, 1):
        category = item["length"]
        text = item["text"]
        print(f"[{i:02d}/20] ({category}) Text: \"{text}\"")

        # Milestone 1: Audio Generation Latency
        t0 = time.time()
        audio_path = generate_voice_output(text)
        t1 = time.time()
        
        gen_latency = t1 - t0
        playback_startup = 0.0
        cumulative_latency = 0.0
        success = False

        if audio_path and os.path.exists(audio_path):
            success = True
            t_start_load = time.time()
            try:
                # Milestone 2: Playback Startup Time
                pygame.mixer.music.load(audio_path)
                pygame.mixer.music.play()
                t_play_started = time.time()
                playback_startup = t_play_started - t_start_load

                # Measure full duration to playback finish
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
                
                t_ended = time.time()
                # Milestone 3: Cumulative Operational Latency (from API dispatch to playback finish)
                cumulative_latency = t_ended - t0
                pygame.mixer.music.unload()

                print(f"  - Gen Latency: {gen_latency:.3f}s")
                print(f"  - Playback Startup: {playback_startup:.3f}s")
                print(f"  - Cumulative Operational Latency: {cumulative_latency:.3f}s")
            except Exception as e:
                print(f"  - Playback Error: {e}")
                # Fallback to responsiveness time if full playback fails
                cumulative_latency = (t_play_started if 't_play_started' in locals() else time.time()) - t0
            finally:
                # Clean up local file immediately
                try:
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                except Exception as clean_err:
                    print(f"  - Error cleaning up file {audio_path}: {clean_err}")
        else:
            print("  - Generation Failed.")

        if success:
            results[category].append({
                "text_length": len(text),
                "gen_latency": gen_latency,
                "playback_startup": playback_startup,
                "cumulative_latency": cumulative_latency
            })
        print("-" * 60)

    # -------------------------------------------------------------------------
    # Aggregate results and print Markdown Table
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("                      PERFORMANCE PROFILING REPORT")
    print("=" * 80)

    categories = ["Short", "Medium", "Long"]
    
    # Header
    print("| Category | Samples | Avg Text Length (chars) | Avg Gen Latency (s) | Avg Playback Startup (s) | Avg Cumulative Latency (s) |")
    print("| --- | --- | --- | --- | --- | --- |")

    all_samples = []
    
    for cat in categories:
        samples = results[cat]
        if not samples:
            print(f"| {cat} | 0 | N/A | N/A | N/A | N/A |")
            continue
        
        all_samples.extend(samples)
        
        avg_len = sum(s["text_length"] for s in samples) / len(samples)
        avg_gen = sum(s["gen_latency"] for s in samples) / len(samples)
        avg_startup = sum(s["playback_startup"] for s in samples) / len(samples)
        avg_cum = sum(s["cumulative_latency"] for s in samples) / len(samples)
        
        print(f"| {cat} | {len(samples)} | {avg_len:.1f} | {avg_gen:.3f}s | {avg_startup:.3f}s | {avg_cum:.3f}s |")

    # Overall Average
    if all_samples:
        avg_len_all = sum(s["text_length"] for s in all_samples) / len(all_samples)
        avg_gen_all = sum(s["gen_latency"] for s in all_samples) / len(all_samples)
        avg_startup_all = sum(s["playback_startup"] for s in all_samples) / len(all_samples)
        avg_cum_all = sum(s["cumulative_latency"] for s in all_samples) / len(all_samples)
        
        print(f"| **Overall** | **{len(all_samples)}** | **{avg_len_all:.1f}** | **{avg_gen_all:.3f}s** | **{avg_startup_all:.3f}s** | **{avg_cum_all:.3f}s** |")
    else:
        print("| **Overall** | **0** | **N/A** | **N/A** | **N/A** | **N/A** |")
    
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
