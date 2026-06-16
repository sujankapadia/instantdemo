import asyncio, time
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv("/Users/user/dev/personal/instantdemo/.env")
from instantdemo.agent_backend import PydanticAIBackend

class Ans(BaseModel):
    answer: str
    items: list[str]

class Ctx:  # minimal duck-typed context
    event_emitter = None

PROMPT = ("List three primary colors and a one-sentence note about color theory. "
          "Return the note as 'answer' and the colors as 'items'.")

async def one(label, settings):
    be = PydanticAIBackend(default_model="openrouter:deepseek/deepseek-chat-v3.1",
                           allowed_roots=[Path("/tmp")], cwd=Path("/tmp"),
                           model_settings=settings)
    t0 = time.monotonic()
    r = await be.run_structured(Ctx(), PROMPT, "phase2-probe", output_type=Ans)
    dt = time.monotonic()-t0
    print(f"{label:28s} {dt:6.1f}s  out={r.output.items}")

async def main():
    await one("default (reasoning as-is)", None)
    await one("reasoning OFF", {"extra_body": {"reasoning": {"enabled": False}}})
    await one("default again (warm)", None)

asyncio.run(main())
