import os
import json
import time
from typing import List, Dict, Any
from dotenv import load_dotenv
from groq import Groq, APIConnectionError, RateLimitError
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class AILeadParser:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                f"GROQ_API_KEY not found. Expected .env at: {os.path.join(BASE_DIR, '.env')}"
            )

        self.client = Groq(api_key=api_key)
        self.model = "openai/gpt-oss-120b"

    def parse_text_with_llm(self, text: str, max_retries: int = 3, delay: int = 3) -> List[Dict[str, Any]]:
        system_prompt = """
        You are an expert lead parser AI.
        Extract leads from the provided text into a strict JSON object with a single key "leads".
        "leads" must be a list of objects.

        Each object must have exactly these keys:
        - "name": string or null
        - "job_title": string or null
        - "company": string or null
        - "email": string or null
        - "phone": string or null

        Output ONLY valid JSON. No markdown code blocks, no explanation.
        """

        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Extract all leads from this text:\n\n{text}"}
                    ],
                    model=self.model,
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )

                content = response.choices[0].message.content
                data = json.loads(content)

                if isinstance(data, dict):
                    for key in ["leads", "data", "contacts"]:
                        if key in data and isinstance(data[key], list):
                            return data[key]
                    return [data]
                return data

            except (APIConnectionError, RateLimitError) as e:
                print(f"[!] Groq network issue (Attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    raise e
                time.sleep(delay)
            except Exception as e:
                raise e

        return []

    def save_to_json(self, leads: List[Dict[str, Any]], output_file: str = "leads_output.json"):
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(leads, f, indent=4, ensure_ascii=False)
        print(f"[+] Output saved successfully to {output_file}")

    def export_to_google_sheets(self, leads: List[Dict[str, Any]], max_retries: int = 3, delay: int = 3):
        webhook_url = os.getenv("GOOGLE_SHEETS_WEBHOOK")
        if not webhook_url:
            print("[!] GOOGLE_SHEETS_WEBHOOK not set. Skipping Sheets export.")
            return

        print("[*] Sending data to Google Sheets...")
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(webhook_url, json=leads, timeout=30, allow_redirects=True)
                if response.status_code == 200:
                    print("[+] Successfully exported to Google Sheets!")
                    return
                else:
                    print(f"[!] Export failed with status {response.status_code}. Retrying...")
            except requests.exceptions.RequestException as e:
                print(f"[!] Webhook error (Attempt {attempt}/{max_retries}): {e}")

            if attempt < max_retries:
                time.sleep(delay)

        print("[!] Could not send data to Google Sheets after retries.")


if __name__ == "__main__":
    input_path = os.path.join(BASE_DIR, "leads_raw.txt")
    output_path = os.path.join(BASE_DIR, "leads_output.json")

    if not os.path.exists(input_path):
        print(f"[!] Error: File '{input_path}' not found.")
    else:
        with open(input_path, "r", encoding="utf-8") as f:
            raw_data = f.read()

        print("[*] Sending data to LLM...")
        parser = AILeadParser()
        extracted_leads = parser.parse_text_with_llm(raw_data)

        parser.save_to_json(extracted_leads, output_path)
        parser.export_to_google_sheets(extracted_leads)
