import html
import json
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st
from google import genai

try:
    from google.genai import types  # pyright: ignore[reportMissingImports]
except Exception:
    genai = None

    class _Part:
        def __init__(self, text=None, data=None, mime_type=None):
            self.text = text
            self.data = data
            self.mime_type = mime_type

        @classmethod
        def from_bytes(cls, data, mime_type):
            return cls(data=data, mime_type=mime_type)

    class _GenerateContentConfig:
        def __init__(self, *, system_instruction=None, **kwargs):
            self.system_instruction = system_instruction
            self.kwargs = kwargs

    class _TypesNamespace:
        Part = _Part
        GenerateContentConfig = _GenerateContentConfig

    types = _TypesNamespace()

from prompts import SUMMARY_REQUEST_PROMPT, SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE

MODEL_NAME = "gemini-3.5-flash"

st.set_page_config(
    page_title="Mealvion",
    page_icon="🥗",
    layout="wide",
)

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
GMAIL_ADDRESS = st.secrets["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = st.secrets["GMAIL_APP_PASSWORD"]
# Set this to the URL of your actual deployed Mealvion app.
# The email will not show a clickable website link if this is not configured.
MEALVION_APP_URL = str(st.secrets.get("MEALVION_APP_URL", "")).strip()


@st.cache_resource
def get_gemini_client():
    if genai is None:
        raise RuntimeError(
            "The Google GenAI SDK is not available. Install google-genai to continue."
        )
    return genai.Client(api_key=GEMINI_API_KEY)


gemini_client = get_gemini_client()


def profile_prompt():
    return SYSTEM_PROMPT.format(
        name=st.session_state.get("name", "User"),
        goal=st.session_state.get("goal", "Understand my eating"),
        diet=st.session_state.get("diet", "No preference specified"),
        activity=st.session_state.get("activity", "Not specified"),
        calorie_target=st.session_state.get("calorie_target") or "Not set",
        protein_target=st.session_state.get("protein_target") or "Not set",
    )


def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.markdown(message["content"])
        elif message["kind"] == "image":
            st.image(message["content"], use_container_width=True)


def add_message(role, kind, content):
    st.session_state.messages.append(
        {"role": role, "kind": kind, "content": content}
    )
    render_message(st.session_state.messages[-1])


def ask_gemini(parts):
    try:
        response = st.session_state.chat.send_message(parts)
        return response.text
    except Exception as error:
        return f"Sorry, something went wrong: {error}"


def parse_number(text, label):
    pattern = rf"{re.escape(label)}\s*:\s*(?:~\s*)?(\d+(?:\.\d+)?)"
    match = re.search(pattern, text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def parse_meal_from_answer(answer):
    meal_match = re.search(r"🍽️\s*Meal:\s*(.+)", answer)
    return {
        "name": meal_match.group(1).strip() if meal_match else "Logged meal",
        "calories": parse_number(answer, "🔥 Calories"),
        "protein": parse_number(answer, "🥩 Protein"),
        "carbs": parse_number(answer, "🍚 Carbohydrates"),
        "fat": parse_number(answer, "🥑 Fat"),
    }


def update_local_meal_log(answer):
    meal = parse_meal_from_answer(answer)

    if meal["calories"] is None:
        return

    st.session_state.meals.append(meal)


def totals_from_local_log():
    totals = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    for meal in st.session_state.get("meals", []):
        for key in totals:
            value = meal.get(key)
            if value is not None:
                totals[key] += value
    return totals


def progress_bar(value, target):
    if not target or target <= 0:
        return None
    return min(value / target, 1.0)


def render_dashboard():
    st.subheader("📊 Today's Nutrition Snapshot")

    totals = totals_from_local_log()
    meals_count = len(st.session_state.get("meals", []))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Calories", f"{totals['calories']:.0f} kcal")
    c2.metric("Protein", f"{totals['protein']:.0f} g")
    c3.metric("Carbs", f"{totals['carbs']:.0f} g")
    c4.metric("Fat", f"{totals['fat']:.0f} g")

    st.caption(
        f"{meals_count} meal{'s' if meals_count != 1 else ''} logged • "
        f"Goal: {st.session_state.get('goal', 'Understand my eating')}"
    )

    p1, p2 = st.columns(2)

    with p1:
        calorie_target = st.session_state.get("calorie_target")
        if calorie_target:
            st.write(
                f"**Calories:** {totals['calories']:.0f} / {calorie_target:.0f} kcal"
            )
            st.progress(progress_bar(totals["calories"], calorie_target))
        else:
            st.info(
                "Set an optional daily calorie target during onboarding to see progress.")

    with p2:
        protein_target = st.session_state.get("protein_target")
        if protein_target:
            st.write(
                f"**Protein:** {totals['protein']:.0f} / {protein_target:.0f} g"
            )
            st.progress(progress_bar(totals["protein"], protein_target))
        else:
            st.info("Set an optional daily protein target to track protein progress.")


def generate_report():
    try:
        response = st.session_state.chat.send_message([SUMMARY_REQUEST_PROMPT])
        raw = response.text.strip()

        # Gemini sometimes wraps JSON in code fences despite the instruction.
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        report = json.loads(raw)

        if not isinstance(report, dict):
            raise ValueError("Report was not a JSON object.")

        return report

    except Exception:
        totals = totals_from_local_log()
        meals = st.session_state.get("meals", [])

        return {
            "meals": [
                {
                    "name": meal["name"],
                    "calories": meal.get("calories") or 0,
                    "protein": meal.get("protein") or 0,
                    "carbs": meal.get("carbs") or 0,
                    "fat": meal.get("fat") or 0,
                    "confidence": "Medium",
                    "balance": "See the meal analysis in the chat for details.",
                }
                for meal in meals
            ],
            "totals": totals,
            "daily_insight": (
                "Your current snapshot is based on the meals successfully logged. "
                "Add more meals to make this insight more meaningful."
            ),
            "focus": "Choose your next meal based on your goal and current intake.",
            "next_meal": "Ask Mealvion for a next-meal suggestion.",
            "smart_swaps": [
                "Ask Mealvion to suggest a higher-protein or more balanced swap."
            ],
            "data_quality": "Medium",
        }


def safe_num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_email_html(report):
    """Build a mobile-first email using Gmail-compatible table layout.

    Wide multi-column meal tables are intentionally avoided because Gmail mobile
    can clip them instead of making them responsive. Each meal is a full-width
    card with a compact 2x2 nutrition grid.
    """
    totals = report.get("totals", {})
    meals = report.get("meals", [])

    meal_cards = ""
    for meal in meals:
        meal_name = html.escape(str(meal.get("name", "Meal")))
        confidence = html.escape(str(meal.get("confidence", "Medium")))
        balance = html.escape(str(meal.get("balance", "")))
        balance_row = ""
        if balance:
            balance_row = f"""
          <tr><td style="padding:0 16px 16px;">
            <div style="font-size:12px;line-height:1.5;color:#4b5563;word-break:break-word;">
              <strong>Meal balance:</strong> {balance}
            </div>
          </td></tr>
            """

        meal_cards += f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="width:100%;border-collapse:separate;border-spacing:0;margin:0 0 14px;
                      background:#f8fafc;border:1px solid #e5e7eb;border-radius:12px;">
          <tr>
            <td style="padding:16px;word-break:break-word;overflow-wrap:anywhere;">
              <div style="font-size:16px;line-height:1.35;font-weight:700;color:#111827;">
                {meal_name}
              </div>
              <div style="font-size:12px;line-height:1.4;color:#6b7280;margin-top:4px;">
                Confidence: {confidence}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:0 16px 16px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="width:100%;border-collapse:collapse;table-layout:fixed;">
                <tr>
                  <td width="50%" style="width:50%;padding:10px 8px 10px 0;border-top:1px solid #e5e7eb;">
                    <div style="font-size:11px;color:#6b7280;">Calories</div>
                    <div style="font-size:15px;font-weight:700;color:#111827;margin-top:2px;">
                      {safe_num(meal.get("calories")):.0f} kcal
                    </div>
                  </td>
                  <td width="50%" style="width:50%;padding:10px 0 10px 8px;border-top:1px solid #e5e7eb;">
                    <div style="font-size:11px;color:#6b7280;">Protein</div>
                    <div style="font-size:15px;font-weight:700;color:#111827;margin-top:2px;">
                      {safe_num(meal.get("protein")):.0f} g
                    </div>
                  </td>
                </tr>
                <tr>
                  <td width="50%" style="width:50%;padding:10px 8px 0 0;border-top:1px solid #e5e7eb;">
                    <div style="font-size:11px;color:#6b7280;">Carbohydrates</div>
                    <div style="font-size:15px;font-weight:700;color:#111827;margin-top:2px;">
                      {safe_num(meal.get("carbs")):.0f} g
                    </div>
                  </td>
                  <td width="50%" style="width:50%;padding:10px 0 0 8px;border-top:1px solid #e5e7eb;">
                    <div style="font-size:11px;color:#6b7280;">Fat</div>
                    <div style="font-size:15px;font-weight:700;color:#111827;margin-top:2px;">
                      {safe_num(meal.get("fat")):.0f} g
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          {balance_row}
        </table>
        """

    if not meal_cards:
        meal_cards = """
        <div style="font-size:14px;line-height:1.5;color:#6b7280;padding:14px 0;">
          No meals were logged for this snapshot.
        </div>
        """

    swaps = report.get("smart_swaps", [])
    swaps_html = "".join(
        f"<li style='margin:0 0 8px;line-height:1.5;word-break:break-word;'>{html.escape(str(item))}</li>"
        for item in swaps[:3]
    )

    calorie_target = st.session_state.get("calorie_target")
    protein_target = st.session_state.get("protein_target")

    progress_html = ""
    if calorie_target:
        calorie_pct = min(
            safe_num(totals.get("calories")) / float(calorie_target), 1
        ) * 100
        progress_html += f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="width:100%;margin:0 0 16px;background:#f8fafc;border-radius:12px;">
          <tr><td style="padding:14px 16px;">
            <div style="font-size:12px;color:#4b5563;">Calories</div>
            <div style="height:8px;background:#e5e7eb;border-radius:8px;margin-top:7px;overflow:hidden;">
              <div style="width:{calorie_pct:.0f}%;height:8px;background:#334155;border-radius:8px;"></div>
            </div>
            <div style="font-size:12px;color:#6b7280;margin-top:5px;">
              {safe_num(totals.get("calories")):.0f} / {float(calorie_target):.0f} kcal
            </div>
          </td></tr>
        </table>
        """

    if protein_target:
        protein_pct = min(
            safe_num(totals.get("protein")) / float(protein_target), 1
        ) * 100
        progress_html += f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="width:100%;margin:0 0 16px;background:#f8fafc;border-radius:12px;">
          <tr><td style="padding:14px 16px;">
            <div style="font-size:12px;color:#4b5563;">Protein</div>
            <div style="height:8px;background:#e5e7eb;border-radius:8px;margin-top:7px;overflow:hidden;">
              <div style="width:{protein_pct:.0f}%;height:8px;background:#334155;border-radius:8px;"></div>
            </div>
            <div style="font-size:12px;color:#6b7280;margin-top:5px;">
              {safe_num(totals.get("protein")):.0f} / {float(protein_target):.0f} g
            </div>
          </td></tr>
        </table>
        """

    name = html.escape(st.session_state.get("name", "there"))

    # Only link to the user's configured Mealvion deployment. Do not expose a
    # bare domain that a mail client could auto-link incorrectly.
    if MEALVION_APP_URL:
        safe_app_url = html.escape(MEALVION_APP_URL, quote=True)
        app_link = f'<a href="{safe_app_url}" style="color:#2563eb;text-decoration:none;font-weight:700;">Open Mealvion</a>'
    else:
        app_link = "Mealvion"

    return f"""<!doctype html>
<html>
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="x-apple-disable-message-reformatting">
  <title>Mealvion — Daily Nutrition Snapshot</title>
  <style>
    @media only screen and (max-width: 600px) {{
      .email-shell {{ width:100% !important; }}
      .email-pad {{ padding-left:18px !important; padding-right:18px !important; }}
      .email-title {{ font-size:26px !important; line-height:1.15 !important; }}
      .metric-cell {{ padding:8px 4px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;color:#1f2937;-webkit-text-size-adjust:100%;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#f3f4f6;">
    <tr>
      <td align="center" style="padding:16px 8px;">
        <table role="presentation" class="email-shell" width="680" cellpadding="0" cellspacing="0" border="0"
               style="width:100%;max-width:680px;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
          <tr>
            <td class="email-pad" style="padding:28px 32px 24px;border-bottom:1px solid #e5e7eb;">
              <div style="font-size:14px;font-weight:700;letter-spacing:.6px;color:#2563eb;">NUTRILENS</div>
              <div class="email-title" style="font-size:30px;line-height:1.2;font-weight:700;color:#111827;margin-top:8px;">
                Daily Nutrition Snapshot
              </div>
              <div style="font-size:13px;color:#6b7280;margin-top:7px;">
                {html.escape(str(st.session_state.get("report_date", "")))}
              </div>
            </td>
          </tr>

          <tr>
            <td class="email-pad" style="padding:24px 32px 28px;">
              <p style="margin:0 0 20px;font-size:16px;line-height:1.5;">Hi {name},</p>

              <div style="font-size:18px;font-weight:700;color:#111827;margin-bottom:10px;">Today's snapshot</div>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:collapse;">
                <tr>
                  <td class="metric-cell" width="50%" style="width:50%;padding:12px 6px 12px 0;vertical-align:top;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#f8fafc;border:1px solid #e5e7eb;border-radius:12px;">
                      <tr><td style="padding:14px;">
                        <div style="font-size:12px;color:#6b7280;">Calories</div>
                        <div style="font-size:22px;line-height:1.2;font-weight:700;color:#111827;margin-top:4px;">{safe_num(totals.get("calories")):.0f}</div>
                        <div style="font-size:12px;color:#6b7280;margin-top:2px;">kcal</div>
                      </td></tr>
                    </table>
                  </td>
                  <td class="metric-cell" width="50%" style="width:50%;padding:12px 0 12px 6px;vertical-align:top;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#f8fafc;border:1px solid #e5e7eb;border-radius:12px;">
                      <tr><td style="padding:14px;">
                        <div style="font-size:12px;color:#6b7280;">Protein</div>
                        <div style="font-size:22px;line-height:1.2;font-weight:700;color:#111827;margin-top:4px;">{safe_num(totals.get("protein")):.0f}</div>
                        <div style="font-size:12px;color:#6b7280;margin-top:2px;">g</div>
                      </td></tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td class="metric-cell" width="50%" style="width:50%;padding:12px 6px 12px 0;vertical-align:top;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#f8fafc;border:1px solid #e5e7eb;border-radius:12px;">
                      <tr><td style="padding:14px;">
                        <div style="font-size:12px;color:#6b7280;">Carbohydrates</div>
                        <div style="font-size:22px;line-height:1.2;font-weight:700;color:#111827;margin-top:4px;">{safe_num(totals.get("carbs")):.0f}</div>
                        <div style="font-size:12px;color:#6b7280;margin-top:2px;">g</div>
                      </td></tr>
                    </table>
                  </td>
                  <td class="metric-cell" width="50%" style="width:50%;padding:12px 0 12px 6px;vertical-align:top;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#f8fafc;border:1px solid #e5e7eb;border-radius:12px;">
                      <tr><td style="padding:14px;">
                        <div style="font-size:12px;color:#6b7280;">Fat</div>
                        <div style="font-size:22px;line-height:1.2;font-weight:700;color:#111827;margin-top:4px;">{safe_num(totals.get("fat")):.0f}</div>
                        <div style="font-size:12px;color:#6b7280;margin-top:2px;">g</div>
                      </td></tr>
                    </table>
                  </td>
                </tr>
              </table>

              {progress_html}

              <div style="font-size:18px;font-weight:700;color:#111827;margin:24px 0 12px;">Meals logged</div>
              {meal_cards}

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#f8fafc;border-radius:12px;margin-top:20px;">
                <tr><td style="padding:16px;">
                  <div style="font-size:12px;font-weight:700;letter-spacing:.4px;color:#475569;">NUTRILENS INSIGHT</div>
                  <div style="font-size:14px;line-height:1.55;color:#1f2937;margin-top:7px;word-break:break-word;">
                    {html.escape(str(report.get("daily_insight", "No additional insight available.")))}
                  </div>
                </td></tr>
              </table>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;background:#f8fafc;border-radius:12px;margin-top:12px;">
                <tr><td style="padding:16px;">
                  <div style="font-size:12px;font-weight:700;letter-spacing:.4px;color:#475569;">NEXT BEST ACTION</div>
                  <div style="font-size:14px;line-height:1.55;color:#1f2937;margin-top:7px;word-break:break-word;">
                    {html.escape(str(report.get("focus", "Choose your next meal mindfully.")))}
                  </div>
                </td></tr>
              </table>

              <div style="font-size:18px;font-weight:700;color:#111827;margin:24px 0 8px;">A useful next meal</div>
              <div style="font-size:14px;line-height:1.55;color:#374151;word-break:break-word;">
                {html.escape(str(report.get("next_meal", "Ask Mealvion for a personalized suggestion.")))}
              </div>

              <div style="font-size:18px;font-weight:700;color:#111827;margin:24px 0 8px;">Smart swaps</div>
              <ul style="margin:0;padding-left:20px;color:#374151;font-size:14px;line-height:1.5;word-break:break-word;">
                {swaps_html or "<li>No swaps suggested today.</li>"}
              </ul>

              <div style="margin-top:26px;padding-top:18px;border-top:1px solid #e5e7eb;font-size:12px;line-height:1.55;color:#6b7280;">
                Nutrition values are estimates based on meal images/descriptions and available portion information.
                Actual values can vary with ingredients, preparation, and serving size.
                Mealvion is intended for general nutrition guidance and is not medical advice.
              </div>

              <div style="margin-top:18px;font-size:13px;line-height:1.5;">
                {app_link}
              </div>
            </td>
          </tr>

          <tr>
            <td class="email-pad" style="padding:16px 32px;background:#f8fafc;border-top:1px solid #e5e7eb;font-size:12px;line-height:1.5;color:#6b7280;">
              Mealvion · Your nutrition companion
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def build_email_plain(report):
    totals = report.get("totals", {})
    lines = [
        "NUTRILENS.AI",
        "Daily Nutrition Snapshot",
        st.session_state.get("report_date", ""),
        "",
        f"Hi {st.session_state.get('name', 'there')},",
        "",
        "TODAY'S TOTALS",
        f"Calories: {safe_num(totals.get('calories')):.0f} kcal",
        f"Protein: {safe_num(totals.get('protein')):.0f} g",
        f"Carbohydrates: {safe_num(totals.get('carbs')):.0f} g",
        f"Fat: {safe_num(totals.get('fat')):.0f} g",
        "",
        "NUTRILENS INSIGHT",
        str(report.get("daily_insight", "")),
        "",
        "NEXT BEST ACTION",
        str(report.get("focus", "")),
        "",
        "NEXT MEAL",
        str(report.get("next_meal", "")),
        "",
        "SMART SWAPS",
    ]

    for item in report.get("smart_swaps", [])[:3]:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "Nutrition values are estimates and may vary with ingredients and portion size.",
            "Mealvion is intended for general nutrition guidance and is not medical advice.",
        ]
    )

    return "\n".join(lines)


def send_email(to_address, subject, html_body, plain_body):
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = GMAIL_ADDRESS
        message["To"] = to_address

        message.attach(MIMEText(plain_body, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(message)

        return True, "Email sent successfully."

    except Exception as error:
        return False, str(error)


# -------------------------
# Onboarding
# -------------------------

if "onboarded" not in st.session_state:
    st.title("🥗 Mealvion")
    st.caption("Understand your food. Improve your next choice.")

    with st.form("onboarding_form"):
        name = st.text_input("Your name")
        email_address = st.text_input(
            "Your email address",
            placeholder="you@example.com",
            help="Mealvion uses this address for your nutrition reports.",
        )

        st.markdown("### Personalize your Mealvion experience")

        goal = st.selectbox(
            "What would you like Mealvion to help with?",
            [
                "Understand my eating",
                "Lose weight",
                "Maintain my weight",
                "Build muscle",
                "Eat more balanced meals",
            ],
        )

        diet = st.selectbox(
            "Dietary preference",
            [
                "No preference",
                "Vegetarian",
                "Vegan",
                "Eggitarian",
                "High-protein",
            ],
        )

        activity = st.selectbox(
            "Activity level",
            ["Not specified", "Low", "Moderate", "High"],
        )

        st.caption(
            "Optional: enter targets you already use. Mealvion will not create "
            "medical or prescriptive targets for you."
        )

        calorie_target = st.number_input(
            "Daily calorie target (optional)",
            min_value=0,
            max_value=10000,
            value=0,
            step=50,
        )

        protein_target = st.number_input(
            "Daily protein target in grams (optional)",
            min_value=0,
            max_value=500,
            value=0,
            step=5,
        )

        submitted = st.form_submit_button("Start Mealvion 🚀")

    if submitted:
        if not name.strip() or not email_address.strip():
            st.warning("Please fill in both your name and email address.")
        elif "@" not in email_address or "." not in email_address:
            st.warning("Please enter a valid email address.")
        else:
            st.session_state.name = name.strip()
            st.session_state.email_address = email_address.strip()
            st.session_state.goal = goal
            st.session_state.diet = diet
            st.session_state.activity = activity
            st.session_state.calorie_target = calorie_target or None
            st.session_state.protein_target = protein_target or None
            st.session_state.messages = []
            st.session_state.meals = []
            st.session_state.latest_report = None

            st.session_state.chat = gemini_client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction=profile_prompt()
                ),
            )

            st.session_state.onboarded = True
            st.rerun()

    st.stop()


# -------------------------
# Main dashboard
# -------------------------

header_col, button_col = st.columns([5, 2], vertical_alignment="center")

with header_col:
    st.title("🥗 Mealvion")
    st.caption("Understand your food. Improve your next choice.")

with button_col:
    send_disabled = len(st.session_state.messages) <= 1

    if st.button(
        "📧 Email My Report",
        disabled=send_disabled,
        use_container_width=True,
    ):
        with st.spinner("Building your personalized nutrition report..."):
            report = generate_report()
            st.session_state.latest_report = report

            import datetime

            st.session_state.report_date = datetime.date.today().strftime(
                "%d %B %Y"
            )

            html_body = build_email_html(report)
            plain_body = build_email_plain(report)

        success, info = send_email(
            st.session_state.email_address,
            "Mealvion — Your Daily Nutrition Snapshot",
            html_body,
            plain_body,
        )

        if success:
            st.success("Your personalized report is on its way. 📧")
        else:
            st.error(f"Couldn't send the email: {info}")


with st.expander("👤 Your Mealvion profile", expanded=False):
    st.write(f"**Goal:** {st.session_state.goal}")
    st.write(f"**Diet:** {st.session_state.diet}")
    st.write(f"**Activity:** {st.session_state.activity}")

    if st.session_state.get("calorie_target"):
        st.write(
            f"**Calorie target:** {st.session_state.calorie_target:.0f} kcal")

    if st.session_state.get("protein_target"):
        st.write(
            f"**Protein target:** {st.session_state.protein_target:.0f} g")


render_dashboard()

# Quick actions make the experience feel like a nutrition companion rather
# than a generic chatbot.
st.markdown("### ⚡ Quick actions")

q1, q2, q3 = st.columns(3)

with q1:
    if st.button("🔄 Improve this meal", use_container_width=True):
        answer = ask_gemini(
            ["Review the most recently logged meal. Give me 2 realistic smart "
             "swaps or additions that better fit my goal. Keep it concise."]
        )
        add_message("assistant", "text", answer)

with q2:
    if st.button("🍽️ Suggest my next meal", use_container_width=True):
        answer = ask_gemini(
            ["Based on my goal, dietary preference, activity level, and meals "
             "logged so far, suggest 3 realistic options for my next meal. "
             "Explain briefly why each fits today's intake."]
        )
        add_message("assistant", "text", answer)

with q3:
    if st.button("🧠 Analyze my day", use_container_width=True):
        with st.spinner("Looking for useful patterns..."):
            report = generate_report()
            st.session_state.latest_report = report


if st.session_state.get("latest_report"):
    report = st.session_state.latest_report

    st.markdown("### 🧠 What Mealvion noticed")

    insight_col, action_col = st.columns(2)

    with insight_col:
        st.info(report.get("daily_insight", "No additional insight yet."))

    with action_col:
        st.success(
            f"**Next best action**\n\n"
            f"{report.get('focus', 'Choose your next meal based on your goal.')}"
        )

    st.markdown("#### 🍽️ A useful next meal")
    st.write(report.get("next_meal", "Ask Mealvion for a next-meal suggestion."))

    swaps = report.get("smart_swaps", [])
    if swaps:
        st.markdown("#### 🔄 Smart swaps")
        for swap in swaps[:3]:
            st.write(f"• {swap}")

    st.caption(
        f"Report data quality: {report.get('data_quality', 'Medium')}. "
        "Nutrition values are estimates."
    )


st.caption(
    f"Logged in as {st.session_state.name} • "
    f"reports go to {st.session_state.email_address}"
)

if not st.session_state.messages:
    add_message(
        "assistant",
        "text",
        WELCOME_MESSAGE_TEMPLATE.format(name=st.session_state.name),
    )
else:
    for message in st.session_state.messages:
        render_message(message)


user_input = st.chat_input(
    "Ask about this meal, upload a photo, or ask what to eat next",
    accept_file=True,
    file_type=["jpg", "jpeg", "png"],
)


if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text
    parts = []

    if photo is not None:
        photo_bytes = photo.getvalue()

        add_message("user", "image", photo_bytes)

        parts.append(
            types.Part.from_bytes(
                data=photo_bytes,
                mime_type=photo.type,
            )
        )

    if text:
        add_message("user", "text", text)
        parts.append(text)

    elif photo is not None:
        parts.append(
            "Analyze this meal using the Mealvion meal-analysis format. "
            "Estimate calories, protein, carbohydrates and fat, then provide "
            "confidence, one insight, one next best action, and one smart swap."
        )

    with st.spinner("Understanding your meal..."):
        answer = ask_gemini(parts)

    add_message("assistant", "text", answer)
    update_local_meal_log(answer)
