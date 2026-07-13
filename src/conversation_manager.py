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
        # Steps: GREETING, COLLECTING, OFFER_HELP, FINALIZED
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

    def _is_negative_response(self, user_input: str) -> bool:
        """Use LLM to classify if user responds negatively to 'anything else' question."""
        system_prompt = (
            "You are a conversation flow assistant.\n"
            "The user was asked 'Is there anything else I can help you with?'\n"
            "Analyze the user's input and determine if it is a negative/decline response (e.g., 'no', 'that is all', 'no thanks', 'nothing else', 'nope').\n\n"
            "Respond ONLY with 'NO' if they decline further assistance.\n"
            "Otherwise, respond with 'YES' (e.g., they ask another question, say yes, or request a new task).\n"
            "Do not include punctuation or other text."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]

        try:
            response = self.client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=messages,
                max_tokens=10,
                temperature=0.0
            )
            res = response.choices[0].message.content.strip().upper()
            return "NO" in res
        except Exception as e:
            print(f"[Warning] Failed to classify negative response: {e}")
            lower_input = user_input.lower().strip()
            negative_words = ["no", "nothing", "that's all", "that is all", "nope", "no thanks", "no, thank you"]
            return any(word in lower_input for word in negative_words)

    def reset_session(self):
        """Reset the conversation state and clear all slot variables."""
        self.current_workflow = "NONE"
        self.current_step = "GREETING"
        self.slots = {
            "tracking_id": None,
            "pickup_location": None,
            "pickup_date": None
        }

    def process_message(self, user_input: str) -> tuple[str, str]:
        """Process user message, classify intent, extract slots, and handle workflow steps."""
        self.add_to_history("user", user_input)

        # Case 1: Active OFFER_HELP check
        if self.current_step == "OFFER_HELP":
            if self._is_negative_response(user_input):
                response = "Thank you for contacting Colaberry Logistics Support. Have a great day!"
                self.reset_session()
                self.add_to_history("assistant", response)
                return response, "unknown"
            else:
                # Wipe previous slots/state to process the new request afresh
                self.reset_session()

        # Case 2: Determine active workflow/intent
        intent = "unknown"
        original_workflow = self.current_workflow
        if self.current_workflow == "NONE":
            intent = self.parse_intent(user_input)
            if intent in ["track_shipment", "delivery_status"]:
                self.current_workflow = "TRACKING"
            elif intent == "shipment_delay":
                self.current_workflow = "DELAY"
            elif intent == "schedule_pickup":
                self.current_workflow = "PICKUP"
            elif intent == "general_inquiry":
                self.current_workflow = "GENERAL"
            else:
                self.current_workflow = "NONE"

        # Case 3: Extract slots and validate input domain
        is_valid_input = self._extract_slots(user_input)

        # Case 4: Handle out-of-domain/gibberish during collecting step
        if not is_valid_input and original_workflow != "NONE":
            response = ""
            if self.current_workflow == "TRACKING":
                response = "I can help you with your logistics request, but first, please provide a valid shipment ID so we can proceed."
            elif self.current_workflow == "DELAY":
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

        # Case 5: Handle active workflow execution and response generation
        response = ""
        if self.current_workflow == "TRACKING":
            if self.slots["tracking_id"] is None:
                self.current_step = "COLLECTING"
                response = "Please provide your shipment ID."
            else:
                self.current_step = "OFFER_HELP"
                response = f"Your shipment {self.slots['tracking_id']} is currently at the Hyderabad Distribution Hub. Is there anything else I can help you with?"
        
        elif self.current_workflow == "DELAY":
            if self.slots["tracking_id"] is None:
                self.current_step = "COLLECTING"
                response = "Please provide your shipment ID."
            else:
                self.current_step = "OFFER_HELP"
                response = f"Your shipment {self.slots['tracking_id']} is delayed due to: Customs Hold at Hyderabad Distribution Hub. We recommend contacting central support or choosing to reroute. Is there anything else I can help you with?"

        elif self.current_workflow == "PICKUP":
            if self.slots["pickup_location"] is None:
                self.current_step = "COLLECTING"
                response = "Please provide your pickup location."
            elif self.slots["pickup_date"] is None:
                self.current_step = "COLLECTING"
                response = "Please provide your pickup date."
            else:
                self.current_step = "OFFER_HELP"
                response = f"Confirmed: Booking pickup at {self.slots['pickup_location']} on {self.slots['pickup_date']}. Is there anything else I can help you with?"
        
        elif self.current_workflow == "GENERAL":
            self.current_step = "COLLECTING"
            response = "I can help with general questions. What details can I provide for you today?"
            self.current_workflow = "NONE"
        
        else:
            self.current_step = "COLLECTING"
            response = "I am not quite sure how to help with that. Could you please rephrase?"

        self.add_to_history("assistant", response)
        return response, intent
