import os
import re
from urllib.parse import quote_plus, unquote_plus, urlparse
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms.validators import DataRequired
from io import BytesIO
import json
from crewai import run_crewai_agent, run_crewai_search

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secret-key")

class ProfileForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    age = StringField("Age", validators=[DataRequired()])
    occupation = StringField("Occupation", validators=[DataRequired()])
    qualification = SelectField(
        "Qualification",
        choices=[
            ("High School", "High School"),
            ("Graduate", "Graduate"),
            ("Postgraduate", "Postgraduate"),
            ("Diploma", "Diploma"),
            ("Other", "Other"),
        ],
        validators=[DataRequired()],
    )
    annual_income = StringField("Annual Income (INR)", validators=[DataRequired()])
    category = SelectField(
        "Category",
        choices=[
            ("General", "General"),
            ("OBC", "OBC"),
            ("SC", "SC"),
            ("ST", "ST"),
        ],
        validators=[DataRequired()],
    )
    location = StringField("Location / State", validators=[DataRequired()])
    family_size = StringField("Family Size", validators=[DataRequired()])
    marital_status = SelectField(
        "Marital Status",
        choices=[
            ("Single", "Single"),
            ("Married", "Married"),
            ("Widowed", "Widowed"),
            ("Divorced", "Divorced"),
        ],
        validators=[DataRequired()],
    )
    disability_status = SelectField(
        "Disability Status",
        choices=[
            ("None", "None"),
            ("Yes", "Yes"),
        ],
        validators=[DataRequired()],
    )
    scheme_type = StringField("Preferred Scheme Type", validators=[DataRequired()])
    submit = SubmitField("Submit")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/profile", methods=["GET", "POST"])
def profile():
    form = ProfileForm()
    profile_data = session.get("profile", {})

    if request.method == "GET" and profile_data:
        form.name.data = profile_data.get("name")
        form.age.data = profile_data.get("age")
        form.occupation.data = profile_data.get("occupation")
        form.qualification.data = profile_data.get("qualification")
        form.annual_income.data = profile_data.get("annual_income")
        form.category.data = profile_data.get("category")
        form.location.data = profile_data.get("location")
        form.family_size.data = profile_data.get("family_size")
        form.marital_status.data = profile_data.get("marital_status")
        form.disability_status.data = profile_data.get("disability_status")
        form.scheme_type.data = profile_data.get("scheme_type")

    if form.validate_on_submit():
        profile_data = {
            "name": form.name.data,
            "age": form.age.data,
            "occupation": form.occupation.data,
            "qualification": form.qualification.data,
            "annual_income": form.annual_income.data,
            "category": form.category.data,
            "location": form.location.data,
            "family_size": form.family_size.data,
            "marital_status": form.marital_status.data,
            "disability_status": form.disability_status.data,
            "scheme_type": form.scheme_type.data,
        }
        session["profile"] = profile_data
        flash("Profile saved successfully.", "success")

    return render_template("profile.html", form=form, profile=profile_data, eligibility=None)

@app.route("/clear-profile", methods=["POST"])
def clear_profile():
    session.pop("profile", None)
    flash("Profile details cleared.", "info")
    return redirect(url_for("profile"))


@app.route("/download-report", methods=["GET", "POST"])
def download_report():
    if request.method == "GET":
        flash("Please select a scheme from search results before downloading a report.", "info")
        return redirect(url_for("search"))

    profile_data = session.get("profile", {})
    selected_scheme = request.form.get("selected_scheme")
    selected_details = request.form.get("selected_details", "")

    if not selected_scheme:
        flash("Please select a scheme before downloading the report.", "warning")
        return redirect(url_for("search"))

    content = render_template(
        "report.txt",
        profile=profile_data,
        scheme_name=selected_scheme,
        scheme_details=selected_details,
    )
    buffer = BytesIO()
    buffer.write(content.encode("utf-8"))
    buffer.seek(0)
    return send_file(buffer, download_name="scheme_report.txt", as_attachment=True)


@app.route("/download-documents", methods=["POST"])
def download_documents():
    scheme_name = request.form.get("scheme_name")
    application_link = request.form.get("application_link", "")
    required_documents = request.form.get("required_documents", "[]")
    try:
        required_documents = json.loads(required_documents)
    except Exception:
        required_documents = [required_documents] if required_documents else []

    content = render_template(
        "documents.txt",
        scheme_name=scheme_name,
        application_link=application_link,
        required_documents=required_documents,
    )
    buffer = BytesIO()
    buffer.write(content.encode("utf-8"))
    buffer.seek(0)
    return send_file(buffer, download_name=f"{scheme_name}_documents.txt", as_attachment=True)


def has_profile_content(profile):
    if not profile:
        return False
    required_keys = [
        "name",
        "age",
        "occupation",
        "qualification",
        "annual_income",
        "category",
        "location",
        "family_size",
        "marital_status",
        "disability_status",
    ]
    return all(profile.get(key) for key in required_keys)


def add_search_history(query):
    if not query:
        return
    history = session.get("search_history", [])
    if query in history:
        history.remove(query)
    history.insert(0, query)
    session["search_history"] = history[:10]


def get_search_cache():
    return session.get("search_cache", {})


def cache_search_result(query, result):
    cache = session.get("search_cache", {})
    if query in cache:
        cache.pop(query)
    if len(cache) >= 10:
        oldest = next(iter(cache))
        cache.pop(oldest, None)
    cache[query] = result
    session["search_cache"] = cache


def get_saved_schemes():
    return session.get("saved_schemes", [])


def calculate_eligibility_score(profile, scheme):
    score = 50
    profile_text = " ".join(
        v.lower() for k, v in profile.items() if isinstance(v, str)
    )
    scheme_text_parts = []
    if isinstance(scheme.get("description"), str):
        scheme_text_parts.append(scheme.get("description"))
    if isinstance(scheme.get("eligibility_reason"), str):
        scheme_text_parts.append(scheme.get("eligibility_reason"))
    if isinstance(scheme.get("application_procedure"), str):
        scheme_text_parts.append(scheme.get("application_procedure"))
    if isinstance(scheme.get("more_info"), str):
        scheme_text_parts.append(scheme.get("more_info"))
    if isinstance(scheme.get("eligibility_criteria"), list):
        scheme_text_parts.extend([str(item) for item in scheme.get("eligibility_criteria")])
    elif isinstance(scheme.get("eligibility_criteria"), str):
        scheme_text_parts.append(scheme.get("eligibility_criteria"))
    scheme_text = " ".join(scheme_text_parts).lower()

    if profile.get("category") and profile["category"].lower() in scheme_text:
        score += 15
    if profile.get("scheme_type") and profile["scheme_type"].lower() in scheme_text:
        score += 10
    if profile.get("disability_status", "").lower() == "yes" and "disability" in scheme_text:
        score += 15
    if profile.get("location") and profile["location"].lower() in scheme_text:
        score += 10
    if scheme.get("source") and any(domain in str(scheme.get("source")).lower() for domain in [".gov.in", ".nic.in", ".gov"]):
        score += 5
    link = scheme.get("application_link") or ""
    if isinstance(link, str) and any(domain in link.lower() for domain in [".gov.in", ".nic.in", ".gov"]):
        score += 5
    score = min(100, max(0, score))
    return score


@app.route("/search", methods=["GET", "POST"])
def search():
    profile_data = session.get("profile", {})
    result = None
    prompt = build_scheme_search_query(profile_data)

    if request.method == "POST":
        if not has_profile_content(profile_data):
            flash("Please enter your profile first before searching.", "warning")
        else:
            search_query = request.form.get("search_query", "").strip()
            scheme_type_override = request.form.get("scheme_type", "").strip()
            search_filters = {
                "scheme_type": scheme_type_override,
                "category": request.form.get("category", "").strip(),
                "location": request.form.get("location", "").strip(),
                "min_income": request.form.get("min_income", "").strip(),
                "max_income": request.form.get("max_income", "").strip(),
            }

            if scheme_type_override:
                profile_data = dict(profile_data) if profile_data else {}
                profile_data["scheme_type"] = scheme_type_override
                session["profile"] = profile_data
                prompt = build_scheme_search_query(profile_data)

            query = search_query if search_query else prompt
            history_key = f"{scheme_type_override}-{search_query}-{search_filters['category']}-{search_filters['location']}-{search_filters['min_income']}-{search_filters['max_income']}"
            add_search_history(history_key)

            cached = get_search_cache().get(history_key)
            if cached:
                result = cached
            else:
                result = run_agent_search(query, search_filters)
                cache_search_result(history_key, result)

    if result and result.get("schemes"):
        for scheme in result["schemes"]:
            if isinstance(scheme, dict):
                score = scheme.get("eligibility_score")
                if score is None:
                    scheme["eligibility_score"] = calculate_eligibility_score(profile_data, scheme)
                else:
                    try:
                        scheme["eligibility_score"] = int(re.sub(r"[^0-9]", "", str(score)))
                    except Exception:
                        scheme["eligibility_score"] = calculate_eligibility_score(profile_data, scheme)
                link = scheme.get("application_link") or ""
                if link:
                    scheme["gov_redirect_url"] = url_for("goto", url=link)
                else:
                    scheme["gov_redirect_url"] = ""

    return render_template(
        "search.html",
        result=result,
        prompt=prompt,
        profile=profile_data,
        search_history=session.get("search_history", []),
        saved_schemes=get_saved_schemes(),
    )


@app.route('/goto')
def goto():
    url = request.args.get('url', '')
    if not url:
        flash('No destination URL provided.', 'warning')
        return redirect(url_for('search'))
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme:
        url = 'https://' + url
    return redirect(url)


def build_scheme_search_query(profile):
    scheme_type = profile.get("scheme_type") if profile else None
    if not profile or (len(profile) == 1 and scheme_type):
        if scheme_type:
            return (
                f"Find Indian government schemes for the scheme type '{scheme_type}'. "
                "Provide 15 official government schemes if available, otherwise return as many as you can find, "
                "excluding blogs, news posts, social posts, forums, and unrelated articles. "
                "Prefer official government sources (gov.in, nic.in, state government portals). "
                "Provide eligibility_score as a number from 0 to 100, a detailed required_documents list with at least 8 specific documents for each scheme, and include items such as birth certificate, Aadhaar card, PAN card, income proof, domicile certificate, bank statement, passport photo, and any scheme-specific certificates. "
                "If the exact source does not list all documents, infer the most likely required documents for this type of scheme. "
                "Include last application date, official application link, and a short reason for eligibility. "
                "Return only valid JSON with keys: summary and schemes. "
                "Each scheme should include name, description, application_link, last_date, source, authoritative, eligibility_score, and required_documents. "
            )
        return "Search government schemes for citizens in India."

    prompt_parts = [
        f"Find Indian government schemes for a {profile.get('age', 'adult')} year old {profile.get('occupation', 'individual')}.",
    ]
    if profile.get("qualification"):
        prompt_parts.append(f"Qualification: {profile.get('qualification')}." )
    if profile.get("annual_income"):
        prompt_parts.append(f"Annual income: {profile.get('annual_income')} INR.")
    if profile.get("category"):
        prompt_parts.append(f"Category: {profile.get('category')}.")
    if scheme_type:
        prompt_parts.append(f"Preferred scheme type: {scheme_type}.")

    prompt_parts.append(
        "Use every provided profile attribute for analysis, including age, occupation, qualification, annual income, category, location, family size, marital status, disability status, and preferred scheme type. "
        "Generate only schemes that match all relevant profile attributes and explain why each scheme is suitable. "
        "Provide 15 official government schemes if available, otherwise return as many as you can find, excluding blogs, news posts, social posts, forums, and unrelated articles. "
        "Prefer official government sources (gov.in, nic.in, state government portals). "
        "Provide eligibility_score as a number from 0 to 100, a detailed required_documents list with at least 5-8 specific documents for each scheme, last application date, official application link, benefits, eligibility_criteria, and application_procedure. "
        "Return only valid JSON with keys: summary and schemes. "
        "Each scheme should include name, description, application_link, last_date, source, authoritative, eligibility_score, required_documents, benefits, eligibility_criteria, and application_procedure. "
    )

    return " ".join(prompt_parts)


def extract_profile(user_text):
    return run_crewai_agent("profile_extractor", user_text)


def check_eligibility(profile):
    if not profile:
        return None
    eligibility_profile = {k: v for k, v in profile.items() if k != "name"}
    return run_crewai_agent("eligibility_checker", json.dumps(eligibility_profile, indent=2))


def run_agent_search(query, search_filters=None):
    if search_filters:
        filter_descriptions = []
        if search_filters.get("category"):
            filter_descriptions.append(f"Category: {search_filters['category']}")
        if search_filters.get("location"):
            filter_descriptions.append(f"Location: {search_filters['location']}")
        if search_filters.get("scheme_type"):
            filter_descriptions.append(f"Scheme type: {search_filters['scheme_type']}")
        if search_filters.get("min_income"):
            filter_descriptions.append(f"Minimum income: {search_filters['min_income']} INR")
        if search_filters.get("max_income"):
            filter_descriptions.append(f"Maximum income: {search_filters['max_income']} INR")
        if filter_descriptions:
            query = f"{query} Filters: {', '.join(filter_descriptions)}."
    return run_crewai_search(query)


@app.route("/save-scheme", methods=["POST"])
def save_scheme():
    scheme_name = request.form.get("scheme_name")
    scheme_description = request.form.get("scheme_description", "")
    application_link = request.form.get("application_link", "")
    last_date = request.form.get("last_date", "")
    eligibility_score = request.form.get("eligibility_score", "")
    required_documents = request.form.get("required_documents", "[]")
    try:
        required_documents = json.loads(required_documents)
    except Exception:
        required_documents = [required_documents] if required_documents else []

    saved_schemes = get_saved_schemes()
    saved_schemes = [scheme for scheme in saved_schemes if scheme.get("name") != scheme_name]
    saved_schemes.insert(0, {
        "name": scheme_name,
        "description": scheme_description,
        "application_link": application_link,
        "last_date": last_date,
        "eligibility_score": eligibility_score,
        "required_documents": required_documents,
    })
    session["saved_schemes"] = saved_schemes[:10]
    flash(f"Scheme '{scheme_name}' saved to your bookmarks.", "success")
    return redirect(url_for("search"))


@app.route("/remove-saved-scheme", methods=["POST"])
def remove_saved_scheme():
    scheme_name = request.form.get("scheme_name")
    saved_schemes = get_saved_schemes()
    session["saved_schemes"] = [s for s in saved_schemes if s.get("name") != scheme_name]
    flash(f"Removed '{scheme_name}' from saved schemes.", "info")
    return redirect(url_for("search"))


@app.route("/saved-schemes")
def saved_schemes():
    return render_template("search.html", result=None, prompt="", profile=session.get("profile", {}), search_history=session.get("search_history", []), saved_schemes=get_saved_schemes())


if __name__ == "__main__":
    app.run(debug=True)
