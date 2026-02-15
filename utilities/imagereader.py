# it converts images here to base64 and return them as a list of dicts with keys 'name' and 'data'
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from fastmcp.server.context import Context
from mcp.types import ImageContent, SamplingMessage, TextContent


class ImageReader:
    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path

    def read_base64(self) -> dict[str, str]:
        if self.file_path is None:
            raise ValueError("file_path is required to read image data")
        return self.image_file_to_base64(self.file_path)

    @staticmethod
    def image_file_to_base64(file_path: Path) -> dict[str, str]:
        data = file_path.read_bytes()
        return {
            "name": file_path.name,
            "mime_type": ImageReader._guess_mime_type(file_path),
            "data": base64.b64encode(data).decode(),
        }

    @staticmethod
    def _guess_mime_type(file_path: Path) -> str:
        ext = file_path.suffix.lower()
        return {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
        }.get(ext, "image/png")

    async def describe_base64(
        self,
        image_b64: str,
        ctx: Context,
        mime_type: str = "image/png",
    ) -> dict[str, Any]:
        if ctx is None:
            raise ValueError("ctx is required for sampling")

        prompt = (
            "You are given an image. Return ONLY raw JSON(No markdown/code fences with) with keys : "
            "description (short summary), text (all visible text), and notes "
            "(useful details like tables, diagrams, or labels)."
        )

        messages = [
            SamplingMessage(
                role="user",
                content=[
                    TextContent(type="text", text=prompt),
                    ImageContent(type="image", data=image_b64, mimeType=mime_type),
                ],
            )
        ]

        result = await ctx.sample(messages, max_tokens=512, temperature=0.2)
        raw_text = result.text or ""

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            return {
                "description": raw_text.strip()
            }

    async def describe_from_docx_image(self, image_object: dict[str, Any], ctx: Context) -> dict[str, Any]:
        data = image_object.get("data", {})
        image_b64 = data.get("bytes_b64", "")
        mime_type = data.get("content_type", "image/png")
        if not image_b64:
            raise ValueError("bytes_b64 is required in image_object.data")
        return await self.describe_base64(image_b64=image_b64, ctx=ctx, mime_type=mime_type)

