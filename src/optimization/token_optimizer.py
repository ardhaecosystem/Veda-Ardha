"""
Veda Token Optimizer: Compresses context using LLMLingua-2.
Protects your budget and RAM.
"""
from llmlingua import PromptCompressor
import structlog

logger = structlog.get_logger()

class TokenOptimizer:
    def __init__(self):
        try:
            # We use the BERT-based model which is fast and runs on CPU
            self.compressor = PromptCompressor(
                model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
                use_llmlingua2=True,
                device_map="cpu"
            )
            logger.info("token_optimizer_initialized")
        except Exception as e:
            logger.error("token_optimizer_failed", error=str(e))
            self.compressor = None

    def compress_search_results(self, text: str, target_ratio: float = 0.5) -> str:
        """
        Compresses long search results (e.g., huge SAP Logs).
        """
        if not self.compressor or not text or len(text) < 500:
            return text
            
        try:
            # Protect SAP keywords from being deleted
            result = self.compressor.compress_prompt(
                text,
                rate=target_ratio,
                force_tokens=['\n', 'Error', 'Code', 'SAP', 'TCode', 'st22', 'sm21'] 
            )
            return result['compressed_prompt']
        except Exception as e:
            logger.warning("compression_failed", error=str(e))
            return text
