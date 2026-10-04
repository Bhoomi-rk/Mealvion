# Mealvion

> **Understand your food. Make a better next choice.**

Mealvion is an AI-powered nutrition companion built with Streamlit. You can describe what you ate or upload a photo of your meal, and Mealvion will give you an estimated nutrition breakdown along with practical suggestions for what you could eat next.

It also keeps a simple nutrition snapshot during your current session and lets you email the report to yourself.

## What can you do with Mealvion?

- **Analyze your meals** — Describe a meal in chat or upload a JPG/PNG photo to get an AI-generated estimate of calories, protein, carbohydrates, and fat.
- **Track your day** — Keep track of the meals you've analyzed during your current session.
- **Set your preferences** — Add your goal, dietary preference, activity level, and optional calorie or protein targets.
- **Get practical suggestions** — Ask for healthier meal swaps, ideas for your next meal, or a summary of your day.
- **Email your report** — Send yourself a report containing your meal details, daily totals, insights, and suggested swaps.

## Getting Started

### 1. Set up the project

Make sure you have **Python 3.9 or newer** installed.

```bash
git clone <your-repository-url>
cd Mealvion

python -m venv .venv
```

Activate the virtual environment:

**Windows PowerShell**
```bash
.venv\Scripts\Activate.ps1
```

**macOS / Linux**
```bash
source .venv/bin/activate
```

Then install the required packages:

```bash
pip install -r requirements.txt
```

### 2. Add your API credentials

Create a file named:

```text
.streamlit/secrets.toml
```

Add your credentials to it:

```toml
GEMINI_API_KEY = "your-gemini-api-key"
GMAIL_ADDRESS = "you@gmail.com"
GMAIL_APP_PASSWORD = "your-16-character-gmail-app-password"
MEALVION_APP_URL = "https://your-deployed-app-url"
```

You can get a Gemini API key from [Google AI Studio](https://aistudio.google.com/).

For Gmail, you'll need a **Google App Password**. Your Google account must have 2-Step Verification enabled before you can create one.

**Keep `secrets.toml` private. Never commit your real credentials to GitHub.**

`MEALVION_APP_URL` is optional. If you provide it, the emailed report can include a link back to your deployed Mealvion app.

### 3. Run the application

Start Mealvion with:

```bash
streamlit run app.py
```

Streamlit will give you a local URL, usually:

```text
http://localhost:8501
```

Open it in your browser and you're ready to go.

## Using Mealvion

Your first session is pretty straightforward:

1. Enter your name and email and choose the profile options that apply to you.
2. Describe a meal in the chat or upload a JPG/PNG image of it. You can also do both.
3. Review the estimated nutrition information and your current daily snapshot.
4. Use the quick actions to explore meal swaps, next-meal suggestions, or a summary of your day.
5. Select **Email My Report** if you want to send the report to yourself.

Mealvion currently stores your profile and meal information in **Streamlit session state**. This means your data is available during the current session but isn't stored as a permanent account history.

## Configuration

Mealvion uses the following Streamlit secrets:

| Secret | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Used for meal analysis and personalized suggestions |
| `GMAIL_ADDRESS` | Gmail account used to send reports |
| `GMAIL_APP_PASSWORD` | App Password used for Gmail SMTP authentication |
| `MEALVION_APP_URL` | Optional URL included in the report email |

For local development, keep these values in:

```text
.streamlit/secrets.toml
```

If you're deploying to **Streamlit Community Cloud**, add the same values under your app's **Settings → Secrets** section.

Never hard-code API keys, passwords, or other credentials into the source code.

## Built With

- [Streamlit](https://streamlit.io/) — Interactive web application
- [Google Gen AI SDK](https://googleapis.github.io/python-genai/) — Gemini-powered text and image analysis
- Python `smtplib` — Sending nutrition reports through Gmail

## A Quick Note About the Nutrition Estimates

Mealvion's nutrition information is **AI-generated and should be treated as an estimate**.

The actual nutritional value of a meal can vary depending on portion size, ingredients, cooking methods, and other factors. Estimates based on photos can be even less precise because the exact ingredients and quantities may not always be visible.

Mealvion is designed to provide general nutrition guidance and help you make more informed food choices. It is **not medical advice** and shouldn't be used as a replacement for advice from a qualified healthcare professional.

---

Built for anyone who wants to understand their meals a little better and make their next choice a little easier. 🥗
