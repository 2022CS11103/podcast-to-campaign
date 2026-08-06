import json

import sys

from pathlib import Path



PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent



if str(PROJECT_ROOT) not in sys.path:

    sys.path.append(str(PROJECT_ROOT))



from utils.gemini_clients import get_client

from utils.cost_tracker import log_gemini_call



PROMPT = """You are a marketing strategist. Based on the brand context below, write a short strategy brief (max 120 words) explaining:

1. Why this content mix (reels/shorts/linkedin/twitter) fits this goal and audience

2. What angle the content should take to achieve the stated goal

3. One risk or thing to watch out for



Be specific and concise, not generic. Return plain text, no markdown headers.



Brand context:

"""





def main():

    brand_file = PROJECT_ROOT / "brand_context.json"

    plan_file = PROJECT_ROOT / "content_plan.json"



    brand = {}

    if brand_file.exists():

        with open(brand_file, "r", encoding="utf-8") as f:

            brand = json.load(f)



    plan = {}

    if plan_file.exists():

        with open(plan_file, "r", encoding="utf-8") as f:

            plan = json.load(f)



    context_text = json.dumps({"brand": brand, "content_plan": plan}, indent=2)



    client = get_client()

    response = client.models.generate_content(

        model="gemini-3.1-flash-lite",

        contents=PROMPT + context_text,

    )

    log_gemini_call("strategy_brief", response)



    output_file = PROJECT_ROOT / "output" / "strategy_brief.txt"

    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:

        f.write(response.text)



    print(f"✅ Strategy brief saved to {output_file}")

    print(response.text)





if __name__ == "__main__":

    main()