import path from "node:path";
import { readFile } from "node:fs/promises";

export const runtime = "nodejs";

export async function GET() {
  try {
    const formatsPath = path.join(process.cwd(), "..", "prompts", "formats.json");
    const raw = await readFile(formatsPath, "utf8");
    const formats = JSON.parse(raw);

    return Response.json(formats, {
      headers: {
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    return Response.json(
      {
        error:
          err instanceof Error
            ? err.message
            : "Failed to load prompts/formats.json",
      },
      { status: 500 }
    );
  }
}

