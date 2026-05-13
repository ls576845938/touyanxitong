from __future__ import annotations

import json
import base64
from loguru import logger

from app.agent.vision.schemas import PortfolioImageExtractResponse, ExtractedPosition

VISION_UNAVAILABLE_MSG = (
    "当前未配置多模态图片识别模型，截图解析不可用。"
    "请在环境变量中配置 OPENAI_API_KEY 或支持 Vision 的 LLM 接入。"
)

# ── System Prompt (Chinese) ──────────────────────────────────────────

SYSTEM_PROMPT = """你是一个专业的证券持仓信息提取助手。你的任务是从用户上传的券商/证券APP截图或网页截图中，精确提取持仓信息并输出为结构化的JSON数据。

## 支持的截图类型（常见的中文券商APP及网页）
- 同花顺 (THS)
- 东方财富 / 东方财富证券
- 华泰证券 (涨乐财富通)
- 中信证券 (信e投)
- 国泰君安 (国泰君安君弘)
- 招商证券 (智远一户通)
- 广发证券 (广发易淘金)
- 海通证券 (e海通财)
- 银河证券 (中国银河证券)
- 平安证券 (平安证券APP)
- 其他常见券商APP、港股美股券商APP（如富途、老虎等）的持仓页面

## 需要提取的信息

提取截图中的以下信息：

1. **券商/平台名称**（broker_name）：截图来自哪个券商或平台，不确定时设为 null
2. **账户总资产/总市值**（account_equity）：账户总资产或总市值
3. **可用资金/现金**（cash）：账户中的可用现金
4. **持仓列表**（positions）：每只持仓证券的详细信息

## 每只持仓字段说明

每个持仓对象包含以下字段：

- **symbol**（股票代码/基金代码）：如 "000858" "600519" "AAPL" "00700"。从截图中提取代码，不确定则设为 null
- **name**（证券名称）：如 "五粮液" "贵州茅台" "Apple Inc." "腾讯控股"
- **quantity**（持仓数量）：股数或份额，不含单位
- **market_value**（持仓市值）：该持仓的当前市值，单位为人民币元（A股/港股）或美元（美股）
- **cost**（成本价/持仓均价）：每单位的平均成本价格
- **weight_pct**（持仓占比）：该持仓占账户总资产的比例，百分比数值（如 15.0 表示 15%）
- **unrealized_pnl**（浮动盈亏）：该持仓的浮动盈亏金额
- **confidence**（信心分数）：0.0-1.0 之间的数值，表示你对这个持仓提取结果的把握程度
  - 信息清晰完整 → 0.95 以上
  - 信息存在但部分模糊 → 0.6-0.9
  - 信息难以辨认或不确定 → 0.3-0.5
  - 几乎全靠猜测 → 0.1-0.3
- **raw_text**（原始文本）：你从截图中提取该持仓的具体原始文字片段，方便人工核对

## 输出格式要求

你必须输出**纯JSON**，不要包含任何markdown代码块标记（如 ```json），不要有任何额外说明文字。

输出的JSON结构如下：
{
  "status": "success",
  "broker_name": "券商名称或 null",
  "account_equity": 账户总资产数值或 null,
  "cash": 可用现金数值或 null,
  "positions": [
    {
      "symbol": "股票代码",
      "name": "证券名称",
      "quantity": 持仓数量,
      "market_value": 持仓市值,
      "cost": 成本价,
      "weight_pct": 持仓占比百分比,
      "unrealized_pnl": 浮动盈亏,
      "confidence": 0.95,
      "raw_text": "截图中的原始文字片段"
    }
  ],
  "warnings": ["需要注意的问题列表"],
  "unmapped_rows": ["无法解析的行或字段说明"]
}

## 重要规则

1. **不确定的字段设为 null，不要编造数据**。宁可设为 null，也不要猜测不存在的值。
2. **所有数字字段不要包含货币符号或单位**（不要 "￥"、"$"、"元"、"股"、" shares" 等），只输出纯数字。
3. **confidence 字段至关重要**，请如实反映你对每个持仓提取结果的把握程度。
4. **unmapped_rows**：如果截图中存在你无法解析的行或数据（如表格标题、合计行、无法辨认的字段），请将这些行的原始文字片段添加到 unmapped_rows 数组中，不要强行解析。
5. **warnings**：如果截图质量不佳、信息不全或存在其他需要注意的情况，请在 warnings 中添加说明。
6. 如果截图中完全没有持仓信息，status 设为 "parse_failed"，并在 warnings 中说明原因。
7. 输出必须是**纯 JSON**，不要包含 markdown 代码块标记。"""


class VisionPortfolioExtractor:
    """LLM Vision-based portfolio extraction from screenshots.

    Uses multimodal LLM (e.g. GPT-4o) to parse Chinese brokerage screenshots
    and extract structured portfolio positions.
    """

    def __init__(self, api_key: str | None = None, provider: str = "openai") -> None:
        self.provider = provider
        if api_key is not None:
            # Caller-supplied key (e.g. from X-LLM-API-Key header)
            self.api_key = api_key
            self.base_url = None
            self.hermes_config = {}
        else:
            # Fall back to server-side config
            self.api_key, self.base_url, self.hermes_config = self._load_config()
        self.available = bool(self.api_key)

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_config() -> tuple[str | None, str | None, dict]:
        from app.config import settings

        api_key = settings.openai_api_key
        base_url = None
        hermes_config: dict = {}

        # If Hermes is enabled and has an endpoint, try it first
        if settings.hermes_enabled and settings.hermes_endpoint:
            hermes_config = {
                "enabled": True,
                "endpoint": settings.hermes_endpoint.rstrip("/") + "/v1",
            }

        return api_key, base_url, hermes_config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        image_bytes: bytes,
        broker_hint: str | None = None,
        market_hint: str | None = None,
        user_hint: str | None = None,
    ) -> PortfolioImageExtractResponse:
        """Extract portfolio positions from a screenshot image.

        Parameters
        ----------
        image_bytes : bytes
            Raw image file bytes (PNG / JPG / WEBP).
        broker_hint : str | None
            Optional broker/platform name to improve parsing accuracy.
        market_hint : str | None
            Optional market hint (A / HK / US).
        user_hint : str | None
            Optional user-provided instruction or context.

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
                warnings=[VISION_UNAVAILABLE_MSG],
                needs_user_confirmation=True,
            )

        # DeepSeek is text-only — no vision support
        if self.provider == "deepseek":
            return PortfolioImageExtractResponse(
                status="vision_unavailable",
                warnings=[
                    "DeepSeek 模型不支持图片识别（纯文本模型）。"
                    "请切换到 OpenAI 或 Gemini 以使用截图解析功能。"
                ],
                needs_user_confirmation=True,
            )

        # Build a tailored prompt with hints
        user_prompt = self._build_user_prompt(broker_hint, market_hint, user_hint)

        try:
            response_text = self._call_vision_api(image_bytes, user_prompt)
        except Exception as exc:
            logger.error(f"Vision API call failed: {exc}")
            return PortfolioImageExtractResponse(
                status="parse_failed",
                warnings=[f"调用多模态模型时发生错误: {exc}"],
                needs_user_confirmation=True,
            )

        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning("Vision model returned non-JSON output")
            # Attempt to strip markdown code fences and retry
            cleaned = self._strip_markdown_fence(response_text)
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                return PortfolioImageExtractResponse(
                    status="parse_failed",
                    warnings=[
                        "多模态模型返回了非JSON格式的输出，无法解析。",
                        f"原始输出(前200字): {response_text[:200]}",
                    ],
                    unmapped_rows=[response_text],
                    needs_user_confirmation=True,
                )

        return self._normalize_response(parsed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_user_prompt(
        self,
        broker_hint: str | None,
        market_hint: str | None,
        user_hint: str | None,
    ) -> str:
        parts = ["请提取下面截图中的持仓信息。"]

        if broker_hint:
            parts.append(f"提示：该截图来自「{broker_hint}」。")
        if market_hint:
            hint_map = {"A": "A股", "HK": "港股", "US": "美股"}
            display = hint_map.get(market_hint.upper(), market_hint)
            parts.append(f"提示：该截图为{display}市场。")
        if user_hint:
            parts.append(f"用户备注：{user_hint}")

        parts.append("请严格按照系统指令中的JSON格式输出。")
        return "\n".join(parts)

    def _call_vision_api(self, image_bytes: bytes, user_prompt: str) -> str:
        """Call a multimodal LLM with the image.

        Supports:
        - ``gemini`` via google-generativeai SDK (Gemini 2.5 Flash)
        - ``openai`` via OpenAI SDK (GPT-4o)
        - Hermes sidecar via OpenAI-compatible endpoint
        """
        if self.provider == "gemini":
            return self._call_gemini_vision(image_bytes, user_prompt)

        # OpenAI-compatible path (OpenAI native or Hermes sidecar)
        from openai import OpenAI

        if self.hermes_config.get("enabled"):
            base_url = self.hermes_config["endpoint"]
            model = "hermes"
        else:
            base_url = self.base_url
            model = "gpt-4o"

        client = OpenAI(api_key=self.api_key, base_url=base_url)

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:image/png;base64,{image_b64}"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": SYSTEM_PROMPT},
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_uri},
                        },
                    ],
                }
            ],
            max_tokens=2000,
            temperature=0.1,
        )

        return response.choices[0].message.content or ""

    def _call_gemini_vision(self, image_bytes: bytes, user_prompt: str) -> str:
        """Call Gemini with image via google-generativeai SDK."""
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        image_data = base64.b64encode(image_bytes).decode("utf-8")
        image_part = {"mime_type": "image/png", "data": image_data}

        response = model.generate_content(
            [SYSTEM_PROMPT, user_prompt, image_part]
        )
        return response.text

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        """Strip markdown code block fences (`` ```json `` / `` ``` ``).

        Returns the content *inside* the first fenced block, or the original
        text if no fence markers are found.
        """
        lines = text.strip().split("\n")
        cleaned = []
        in_fence = False
        fence_found = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                fence_found = True
                continue
            if in_fence:
                cleaned.append(line)
        if fence_found:
            return "\n".join(cleaned).strip()
        # No fence markers — return the original text as-is
        return text.strip()

    @staticmethod
    def _normalize_response(raw: dict) -> PortfolioImageExtractResponse:
        """Validate and normalize the vision model output into a response."""
        status = raw.get("status", "parse_failed")
        if status not in ("success", "parse_failed", "vision_unavailable"):
            status = "parse_failed"

        raw_positions = raw.get("positions", [])
        if not isinstance(raw_positions, list):
            raw_positions = []

        positions = []
        for item in raw_positions:
            if not isinstance(item, dict):
                continue
            positions.append(
                ExtractedPosition(
                    symbol=item.get("symbol"),
                    name=item.get("name"),
                    quantity=_safe_float(item.get("quantity")),
                    market_value=_safe_float(item.get("market_value")),
                    cost=_safe_float(item.get("cost")),
                    weight_pct=_safe_float(item.get("weight_pct")),
                    unrealized_pnl=_safe_float(item.get("unrealized_pnl")),
                    confidence=_safe_float(item.get("confidence"), default=0.0),
                    raw_text=str(item["raw_text"]) if item.get("raw_text") else None,
                )
            )

        raw_unmapped = raw.get("unmapped_rows", [])
        if not isinstance(raw_unmapped, list):
            raw_unmapped = []

        raw_warnings = raw.get("warnings", [])
        if not isinstance(raw_warnings, list):
            raw_warnings = []

        return PortfolioImageExtractResponse(
            status=status,
            broker_name=str(raw["broker_name"]) if raw.get("broker_name") else None,
            account_equity=_safe_float(raw.get("account_equity")),
            cash=_safe_float(raw.get("cash")),
            positions=positions,
            warnings=raw_warnings,
            unmapped_rows=raw_unmapped,
            needs_user_confirmation=True,
        )


def _safe_float(value, default: float | None = None) -> float | None:
    """Convert a value to float, returning *default* on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
