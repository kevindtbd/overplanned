"""
Import pipeline package.

Handles external data source imports and converts them into
ImportPreferenceSignal rows linked to ImportJob records.

Exports:
  process_chatgpt_import  — ZIP-based ChatGPT export ingestion
"""

from services.api.import_pipeline.chatgpt_import import process_chatgpt_import

__all__ = ["process_chatgpt_import"]
