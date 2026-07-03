"""
Pattern recognition brain using Groq (fast Llama inference).
Uses Groq's OpenAI-compatible chat completions endpoint with a
JSON-structured response format for strict decision formatting.
"""

import json
import logging
from typing import Dict, Any

import requests
from config import Settings

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqBrain:
    """AI-powered pattern recognition engine backed by Groq."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.GROQ_API_KEY
        self.model_name = settings.GROQ_MODEL

    def get_model_info(self) -> str:
        """Retrieve and log model information."""
        return self.model_name

    def _format_market_data(self, market_data: Dict[str, Any]) -> str:
        """Format market data into a string for analysis."""
        formatted = "MARKET DATA SUMMARY:\n"
        formatted += "-" * 50 + "\n"

        for symbol, data in market_data.items():
            if isinstance(data, dict):
                ohlcv = data.get('ohlcv', {})
                formatted += f"{symbol}:\n"
                formatted += f"  Open: ${ohlcv.get('open', 'N/A')}\n"
                formatted += f"  High: ${ohlcv.get('high', 'N/A')}\n"
                formatted += f"  Low: ${ohlcv.get('low', 'N/A')}\n"
                formatted += f"  Close: ${ohlcv.get('close', 'N/A')}\n"
                formatted += f"  Volume: {ohlcv.get('volume', 'N/A')}\n"
                formatted += f"  RSI: {data.get('rsi', 'N/A')}\n"
                formatted += f"  MA20: ${data.get('ma20', 'N/A')}\n"
                formatted += f"  Change: {data.get('change_pct', 'N/A')}%\n"
                formatted += "\n"

        return formatted

    def analyze_patterns(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use a Groq-hosted model to analyze market patterns and return a
        structured decision with custom quantity sizing.
        """
        try:
            market_summary = self._format_market_data(market_data)

            prompt = f"""You are an expert quantitative trader analyzing real-time market data.

{market_summary}

Based on the technical indicators, price action, and volume patterns above, determine the optimal trading action and position sizing.

Consider:
1. RSI extremes (< 30 = oversold, > 70 = overbought)
2. Price vs moving averages
3. Volume trends
4. Overall market momentum

Respond with a valid JSON object in this exact schema format. Choose a quantity between 1 and 10 shares depending on the strength and confidence of the chart setup:
{{
  "decision": "BUY|SELL|HOLD", 
  "quantity": 5,
  "reason": "detailed reasoning text here", 
  "confidence": 0.85
}}"""

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a professional quantitative trading analyst. "
                            "You always output structured data in JSON format matching the schema requested. "
                            "Do not include any conversational text or markdown blocks."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": self.settings.GROQ_TEMPERATURE,
                "max_tokens": self.settings.GROQ_MAX_TOKENS,
                "response_format": {"type": "json_object"},
            }

            response = requests.post(
                GROQ_URL, headers=headers, json=payload, timeout=30
            )
            
            if response.status_code == 400:
                logger.error(f"Groq 400 Bad Request Diagnostic Details: {response.text}")
                
            response.raise_for_status()
            data = response.json()

            response_text = data["choices"][0]["message"]["content"]
            logger.debug(f"Groq raw response: {response_text}")

            decision = self._parse_response(response_text)
            return decision

        except Exception as e:
            logger.error(f"Error in pattern analysis: {str(e)}", exc_info=True)
            return {
                "decision": "HOLD",
                "quantity": 0,
                "reason": f"Analysis error: {str(e)}",
                "confidence": 0.0,
            }

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse model response and extract decision and chosen quantity."""
        try:
            if "{" in response_text and "}" in response_text:
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                json_str = response_text[json_start:json_end]
                parsed = json.loads(json_str)

                decision = str(parsed.get("decision", "HOLD")).upper()
                if decision not in ["BUY", "SELL", "HOLD"]:
                    decision = "HOLD"

                return {
                    "decision": decision,
                    "quantity": int(parsed.get("quantity", 1)),
                    "reason": parsed.get("reason", "No reason provided"),
                    "confidence": float(parsed.get("confidence", 0.5)),
                }

            text_upper = response_text.upper()
            if "BUY" in text_upper and text_upper.find("BUY") < text_upper.find(
                "SELL" if "SELL" in text_upper else "\uffff"
            ):
                decision = "BUY"
            elif "SELL" in text_upper:
                decision = "SELL"
            else:
                decision = "HOLD"

            return {
                "decision": decision,
                "quantity": 1,
                "reason": response_text[:200],
                "confidence": 0.5,
            }

        except Exception as e:
            logger.error(f"Error parsing response: {str(e)}")
            return {
                "decision": "HOLD",
                "quantity": 0,
                "reason": f"Parse error: {str(e)}",
                "confidence": 0.0,
            }
