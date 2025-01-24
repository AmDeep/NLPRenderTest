from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import json
import re
import spacy
import language_tool_python

# Initialize the Flask app
app = Flask(__name__)

# Load the English spaCy model
nlp = spacy.load("en_core_web_sm")

# Initialize LanguageTool for grammar corrections
tool = language_tool_python.LanguageTool('en-US')


# Load medical definitions from the provided JSON file
def load_medical_definitions(file_path):
    try:
        with open(file_path, "r") as file:
            data = json.load(file)
            return data.get("definitions", [])
    except Exception as e:
        raise RuntimeError(f"Error loading medical definitions: {e}")


# Simplify terms in a text using loaded definitions
def simplify_terms(text, definitions):
    for term in definitions:
        term_lower = term["term"].lower()
        definition = term["definition"]
        text = re.sub(rf"\b{term_lower}\b", definition, text, flags=re.IGNORECASE)
    return text


# Improve grammar and convert text to questions
def improve_question_grammar(text):
    if "individuals" in text.lower():
        text = re.sub(r"\bindividuals\b", "Do you", text, flags=re.IGNORECASE)
    if "diagnosis" in text.lower():
        text = re.sub(r"\bdiagnosis\b", "Have you been diagnosed with", text, flags=re.IGNORECASE)
    text = re.sub(r"have\s(current|severe)\s", "Do you currently have ", text)
    return text


# Correct grammar using LanguageTool
def correct_grammar(text):
    matches = tool.check(text)
    return language_tool_python.utils.correct(text, matches)


# Convert content to survey questions
def convert_to_survey_questions(content, definitions):
    lines = re.split(r'\d+\.\s*', content)
    survey_questions = []

    for idx, line in enumerate(lines, start=1):
        line = line.strip()
        if line:
            simplified_line = simplify_terms(line, definitions)
            improved_line = improve_question_grammar(simplified_line)
            corrected_line = correct_grammar(improved_line)
            question = f"Question {idx}: {corrected_line} (Yes/No)"
            survey_questions.append(question)

    return survey_questions


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        condition = request.form.get("condition", "").strip()
        definitions = load_medical_definitions("data.json")

        # Fetch the data from Unity Trials
        base_url = "https://unitytrials.org/trials/"
        search_url = f"{base_url}{condition.lower().replace(' ', '-')}"
        response = requests.get(search_url)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            script_tag = soup.find("script", {"id": "__NEXT_DATA__"})

            if script_tag:
                data = json.loads(script_tag.string)
                study_items = data.get("props", {}).get("pageProps", {}).get("getStudies", {}).get("items", [])
                if study_items:
                    first_study = study_items[0]
                    trial_path = first_study.get("path", "")
                    trial_url = f"https://unitytrials.org{trial_path}"
                    trial_response = requests.get(trial_url)

                    if trial_response.status_code == 200:
                        trial_soup = BeautifulSoup(trial_response.text, "html.parser")
                        participation_criteria_wrapper = trial_soup.find("div", class_="participation__criteria-wrapper")

                        if participation_criteria_wrapper:
                            content = participation_criteria_wrapper.get_text(strip=True, separator=" ")
                            survey_questions = convert_to_survey_questions(content, definitions)
                            return jsonify({"questions": survey_questions})

        return jsonify({"error": "Unable to fetch or process the trial data."})

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
