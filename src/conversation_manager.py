import os
import sys
import json
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

        # Slots tracking
        self.slots = {
            "tracking_id": None,
            "pickup_location": None,
            "pickup_date": None
        }

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

    def _extract_slots(self, user_input: str) -> bool:
        """Extract slots and validate input domain. Returns True if valid, False if out-of-domain/gibberish."""
        system_prompt = (
            "You are a slot extraction and conversation validation assistant for a logistics support system.\n"
            "Analyze the user's input and current active workflow, then extract values for:\n"
            "1. tracking_id (any alphanumeric ID or reference number, e.g., TX12345)\n"
            "2. pickup_location (the city, state, or location, e.g., Hyderabad, Delhi)\n"
            "3. pickup_date (a date or day, e.g., tomorrow, next Monday, 15th July)\n\n"
            "Also evaluate if the user's input is a valid request, general logistics question, or a response to our question.\n"
            "Identify if the input is completely off-topic (e.g., 'Tell me a joke', 'What is the capital of France?') or meaningless gibberish (e.g., 'asdfgh', 'xyz').\n\n"
            "Return a JSON object with the exact keys:\n"
            "- \"tracking_id\"\n"
            "- \"pickup_location\"\n"
            "- \"pickup_date\"\n"
            "- \"is_valid_input\": true if the input is relevant/valid; false if it is gibberish or an off-topic/out-of-domain request.\n\n"
            "If a slot is not present or not mentioned, set its value to null.\n"
            "Ensure that you do not overwrite existing slots with null if they are already provided in the active slots state.\n"
            "Respond ONLY with the JSON object. Do not include markdown code blocks (like ```json) or explanations."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Active Workflow: {self.current_workflow}\nUser Input: {user_input}\nActive Slots State: {json.dumps(self.slots)}"}
        ]

        try:
            response = self.client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=messages,
                max_tokens=150,
                temperature=0.0
            )
            response_text = response.choices[0].message.content.strip()
            
            # Safe JSON parsing: strip away potential markdown fences
            content = response_text
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines).strip()

            extracted = json.loads(content)
            is_valid_input = extracted.get("is_valid_input", True)
            
            if is_valid_input:
                for key in ["tracking_id", "pickup_location", "pickup_date"]:
                    val = extracted.get(key)
                    if val is not None and str(val).strip().lower() != "null" and str(val).strip() != "":
                        self.slots[key] = str(val).strip()
                return True
            else:
                return False
        except Exception as e:
            print(f"[Warning] Safe JSON parsing failed for slot extraction: {e}")
            return True

    def process_message(self, user_input: str) -> tuple[str, str]:
        """Process user message, classify intent, extract slots, and return (response, intent)."""
        self.add_to_history("user", user_input)

        # 1. Determine active workflow/intent
        intent = "unknown"
        original_workflow = self.current_workflow
        if self.current_workflow == "NONE":
            intent = self.parse_intent(user_input)
            if intent in ["track_shipment", "delivery_status", "shipment_delay"]:
                self.current_workflow = "TRACKING"
            elif intent == "schedule_pickup":
                self.current_workflow = "PICKUP"
            elif intent == "general_inquiry":
                self.current_workflow = "GENERAL"
            else:
                self.current_workflow = "NONE"

        # 2. Extract slots and validate input domain
        is_valid_input = self._extract_slots(user_input)

        # 3. Handle out-of-domain/gibberish during collecting step
        if not is_valid_input and original_workflow != "NONE":
            response = ""
            if self.current_workflow == "TRACKING":
                response = "I can help you with your logistics request, but first, please provide a valid shipment ID so we can proceed."
            elif self.current_workflow == "PICKUP":
                if self.slots["pickup_location"] is None:
                    response = "I can help you with your logistics request, but first, please provide a valid pickup location so we can proceed."
                else:
                    response = "I can help you with your logistics request, but first, please provide a valid pickup date so we can proceed."
            else:
                response = "I am not quite sure how to help with that. Could you please rephrase?"
            
            self.add_to_history("assistant", response)
            return response, "unknown"

        # 4. Handle conversation flow and state updates
        response = ""
        if self.current_workflow == "TRACKING":
            if self.slots["tracking_id"] is None:
                self.current_step = "COLLECTING"
                response = "Please provide your shipment ID."
            else:
                self.current_step = "FINALIZED"
                response = f"Confirmed: Retrieving status for shipment ID {self.slots['tracking_id']}."
        
        elif self.current_workflow == "PICKUP":
            if self.slots["pickup_location"] is None:
                self.current_step = "COLLECTING"
                response = "Please provide your pickup location."
            elif self.slots["pickup_date"] is None:
                self.current_step = "COLLECTING"
                response = "Please provide your pickup date."
            else:
                self.current_step = "FINALIZED"
                response = f"Confirmed: Booking pickup at {self.slots['pickup_location']} on {self.slots['pickup_date']}."
        
        elif self.current_workflow == "GENERAL":
            self.current_step = "FINALIZED"
            response = "Sure, I can answer your logistics questions. How can I help?"
        
        else:
            self.current_step = "COLLECTING"
            response = "I am not quite sure how to help with that. Could you please rephrase?"

        self.add_to_history("assistant", response)
        return response, intent
