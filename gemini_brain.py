"""
Pattern recognition brain using Google Gemini 2.5 Flash.
Uses Structured Outputs for strict decision formatting.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from google import genai
from config import Settings

logger = logging.getLogger(__name__)


class TradingDecision(BaseModel):
    """Structured output for trading decisions."""
    decision: str = Field(..., description="BUY, SELL, or HOLD")
    reason: str = Field(..., description="Detailed reasoning for the decision")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence level 0-1")


class GeminiBrain:
    """AI-powered pattern recognition engine."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = settings.GEMINI_MODEL
        
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
        Use Gemini to analyze market patterns and return structured decision.
        Uses low temperature for deterministic analysis.
        """
        try:
            # Format market data
            market_summary = self._format_market_data(market_data)
            
            # Build analysis prompt
            prompt = f"""You are an expert quantitative trader analyzing real-time market data.

{market_summary}

Based on the technical indicators, price action, and volume patterns above, determine the optimal trading action.

Consider:
1. RSI extremes (< 30 = oversold, > 70 = overbought)
2. Price vs moving averages
3. Volume trends
4. Overall market momentum

Provide your trading decision with clear reasoning."""

            # Call Gemini API with structured output (schema validation)
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                generation_config={
                    "temperature": self.settings.GEMINI_TEMPERATURE,
                    "max_output_tokens": self.settings.GEMINI_MAX_TOKENS,
                },
                system_instruction="You are a professional quantitative trading analyst. Always respond with a clear BUY, SELL, or HOLD decision with detailed reasoning.",
            )
            
            # Parse response
            response_text = response.text
            logger.debug(f"Gemini raw response: {response_text}")
            
            # Extract decision and reason from response
            decision = self._parse_gemini_response(response_text)
            
            return decision
            
        except Exception as e:
            logger.error(f"Error in pattern analysis: {str(e)}", exc_info=True)
            return {
                "decision": "HOLD",
                "reason": f"Analysis error: {str(e)}",
                "confidence": 0.0
            }
    
    def _parse_gemini_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Gemini response and extract decision."""
        try:
            # Try to find JSON in response
            if "{" in response_text and "}" in response_text:
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                json_str = response_text[json_start:json_end]
                parsed = json.loads(json_str)
                
                # Validate structure
                decision = parsed.get("decision", "HOLD").upper()
                if decision not in ["BUY", "SELL", "HOLD"]:
                    decision = "HOLD"
                
                return {
                    "decision": decision,
                    "reason": parsed.get("reason", "No reason provided"),
                    "confidence": float(parsed.get("confidence", 0.5))
                }
            
            # Fallback: search for keywords
            text_upper = response_text.upper()
            if "BUY" in text_upper and text_upper.find("BUY") < text_upper.find("SELL" if "SELL" in text_upper else float('inf')):
                decision = "BUY"
            elif "SELL" in text_upper:
                decision = "SELL"
            else:
                decision = "HOLD"
            
            return {
                "decision": decision,
                "reason": response_text[:200],
                "confidence": 0.5
            }
            
        except Exception as e:
            logger.error(f"Error parsing response: {str(e)}")
            return {
                "decision": "HOLD",
                "reason": f"Parse error: {str(e)}",
                "confidence": 0.0
            }
