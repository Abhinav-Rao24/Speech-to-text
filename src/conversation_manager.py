import os
import sys
from openai import OpenAI

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

class ConversationManager:
    def __init__(self):
        # Workflows: TRACKING, PICKUP, DELAY, GENERAL, NONE
        self.current_workflow = "NONE"
        # Steps: GREETING, COLLECTING, FINALIZED
        self.current_step = "GREETING"
        # History rolling window (cap at 6 messages)
        self.history = []
        self.max_history_length = 6

        self.client = OpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY
        )

    def add_to_history(self, role: str, content: str):
        """Add a message to the history window, enforcing the max length."""
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_history_length:
            self.history = self.history[-self.max_history_length:]

    def initiate_conversation(self) -> str:
        """Returns the standardized professional greeting."""
        greeting = "Hello! Welcome to Colaberry Logistics Support. How may I assist you today?"
        self.add_to_history("assistant", greeting)
        self.current_step = "COLLECTING"
        return greeting

    def parse_intent(self, user_input: str) -> str:
        """Categorize the user input into logistics intents."""
        self.add_to_history("user", user_input)
        
        system_prompt = (
            "You are an intent classifier for a logistics support assistant.\n"
            "Classify the user's input into exactly one of the following categories:\n"
            "- track_shipment\n"
            "- schedule_pickup\n"
            "- delivery_status\n"
            "- shipment_delay\n"
            "- general_inquiry\n"
            "- unknown\n\n"
            "Respond ONLY with the exact category name. Do not include any punctuation or other text."
        )

        messages = [{"role": "system", "content": system_prompt}] + self.history

        try:
            response = self.client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=messages,
                max_tokens=50,
                temperature=0.0
            )
            intent = response.choices[0].message.content.strip().lower()
            
            valid_intents = [
                "track_shipment", "schedule_pickup", "delivery_status",
                "shipment_delay", "general_inquiry", "unknown"
            ]
            
            if intent not in valid_intents:
                intent = "unknown"
                
            return intent
        except Exception as e:
            print(f"[ERROR] Intent parsing failed: {e}")
            return "unknown"
