from __future__ import annotations

from app.agent.vision.schemas import PortfolioImageExtractResponse


class VisionPortfolioExtractor:
    """LLM Vision-based portfolio extraction from screenshots.

    Currently a stub — returns vision_unavailable when no vision model is configured.
    """

    def __init__(self) -> None:
        self.available = self._check_vision_available()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_vision_available() -> bool:
        from app.config import settings

        return bool(settings.openai_api_key)  # gpt-4o supports vision

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        image_bytes: bytes,
        broker_hint: str | None = None,
    ) -> PortfolioImageExtractResponse:
        """Extract portfolio positions from a screenshot image.

        Parameters
        ----------
        image_bytes : bytes
            Raw image file bytes (PNG / JPG / WEBP).
        broker_hint : str | None
            Optional broker/platform name to improve parsing accuracy.

        Returns
        -------
        PortfolioImageExtractResponse
            Extraction result with parsed positions or error status.

        Rules
        -----
        - NEVER write image content to logs.
        - NEVER store images long-term.
        - NEVER auto-import positions — user must confirm.
        - NO traditional OCR (Tesseract, PaddleOCR, etc.).
        """
        if not self.available:
            return PortfolioImageExtractResponse(
                status="vision_unavailable",
                warnings=[
                    "当前未配置多模态图片识别模型，截图解析不可用。"
                    "请在环境变量中配置 OPENAI_API_KEY 或支持 Vision 的 LLM 接入。"
                ],
                needs_user_confirmation=True,
            )

        # PLACEHOLDER for actual LLM Vision call (to be implemented in a future MVP)
        return PortfolioImageExtractResponse(
            status="vision_unavailable",
            warnings=[
                "Vision 模型已配置，但 MVP 3.3 仅预留接口，尚未实现完整的截图解析流程。"
                "请在后续版本中完善。"
            ],
            needs_user_confirmation=True,
        )
