"""
Gemini Vision Client with multi-model fallback retry logic for image-based profile extraction.
"""

import os
import json
import base64
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

GEMINI_API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class GeminiError(Exception):
    """Exception raised when Gemini API call fails."""
    pass


class GeminiClient:
    """Client for interacting with Google Gemini API for vision tasks."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize Gemini client.

        Args:
            api_key: Gemini API Key (defaults to GEMINI_API_KEY environment variable)
            model: Gemini model name (default: gemini-3.6-flash or GEMINI_MODEL env var)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        mime_type: str = "image/jpeg",
        schema: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze a single image byte payload using Gemini Vision API."""
        return self.analyze_images([image_bytes], prompt, mime_type, schema, api_key)

    def analyze_images(
        self,
        images_bytes_list: List[bytes],
        prompt: str,
        mime_type: str = "image/jpeg",
        schema: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze multiple in-memory image byte payloads in a single Gemini Vision API call.
        """
        effective_key = api_key or self.api_key or os.getenv("GEMINI_API_KEY")
        if not effective_key:
            raise GeminiError(
                "Gemini API key is required. Set GEMINI_API_KEY in .env file or pass geminiApiKey in query parameter."
            )

        if not images_bytes_list:
            raise GeminiError("No image bytes provided for analysis.")

        # Attempt to use google-genai SDK if available
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=effective_key)
            contents = [
                types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
                for img_bytes in images_bytes_list
            ]
            contents.append(prompt)

            config_args = {"response_mime_type": "application/json"}
            if schema:
                config_args["response_schema"] = schema

            config = types.GenerateContentConfig(**config_args)
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            response_text = response.text or ""
            return self._parse_json_response(response_text)

        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"google-genai SDK call failed, falling back to HTTP endpoint: {e}")

        # Fallback to REST API with multi-model retry logic
        return self._call_rest_api_multi(images_bytes_list, prompt, mime_type, effective_key)

    def _call_rest_api_multi(
        self,
        images_bytes_list: List[bytes],
        prompt: str,
        mime_type: str,
        api_key: str,
    ) -> Dict[str, Any]:
        """Execute REST HTTP POST to Gemini API with multiple inline images and automatic model fallback on 503."""
        import requests

        fallback_models = [
            self.model,
            "gemini-3.6-flash",
            "gemini-flash-latest",
            "gemini-3.5-flash",
            "gemini-2.5-flash",
            "gemini-1.5-flash",
        ]
        fallback_models = list(dict.fromkeys([m for m in fallback_models if m]))

        parts = []
        for img_bytes in images_bytes_list:
            b64_data = base64.b64encode(img_bytes).decode("utf-8")
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": b64_data,
                }
            })
        parts.append({"text": prompt})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        }

        headers = {"Content-Type": "application/json"}
        last_error = None

        for model_name in fallback_models:
            url = f"{GEMINI_API_URL_TEMPLATE.format(model=model_name)}?key={api_key}"
            try:
                logger.info(f"Querying Gemini Vision model: {model_name}...")
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    res_json = response.json()
                    candidates = res_json.get("candidates", [])
                    if not candidates:
                        raise GeminiError(f"No response candidates from Gemini API: {res_json}")

                    text_parts = candidates[0].get("content", {}).get("parts", [])
                    if not text_parts:
                        raise GeminiError(f"Empty content parts from Gemini API response.")

                    response_text = text_parts[0].get("text", "")
                    return self._parse_json_response(response_text)

                elif response.status_code in (503, 429):
                    logger.warning(
                        f"Model {model_name} returned {response.status_code} (Busy/High Demand). Trying next fallback model..."
                    )
                    last_error = f"Gemini API HTTP Error {response.status_code}: {response.text}"
                    continue
                else:
                    raise GeminiError(
                        f"Gemini API HTTP Error {response.status_code}: {response.text}"
                    )

            except requests.RequestException as e:
                logger.warning(f"Network error with model {model_name}: {e}. Retrying with next fallback model...")
                last_error = str(e)
                continue

        raise GeminiError(last_error or "All Gemini Vision models failed or returned busy status.")

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Clean markdown codeblocks if any and parse JSON."""
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise GeminiError(f"Failed to decode Gemini JSON response: {e}\nRaw output: {text}")
