# Jenkins Job and Repository Analyzer

This Python script extracts Jenkins job details and filters Bitbucket repositories based on recent commit activity. It connects to a Jenkins instance, gathers job metadata, and outputs the results to a JSON and Excel file.

## 🧰 Features

- Reads a Bitbucket CSV file to filter repositories by last commit date.
- Fetches Jenkins job and controller information using the Jenkins REST API.
- Gathers latest build metadata for relevant Jenkins jobs.
- Exports the job data in both `.json` and `.xlsx` formats for reporting or analysis.
- Securely uses credentials and configuration from environment variables.

---

## 📌 Use Case

This script is primarily used to:

- **Audit Jenkins jobs and CI/CD pipelines**.
- **Track last activity on repositories** and match them with Jenkins jobs.
- **Generate compliance or activity reports** by exporting relevant job metadata.

---

## 🧾 Prerequisites

- Python 3.7 or higher
- Access to the target Jenkins instance (with credentials)
- Access to Bitbucket repo CSV with `REPO_NAME` and `LATEST_COMMIT_DATE` columns
- CA certificate (if Jenkins is hosted with SSL verification)
- Valid Jenkins username and password/API token

---

## 🧪 Dependencies

Install Python dependencies via:

```bash
pip install -r requirements.txt
```

## 🗃️ CSV Format

Your CSV file must include the following columns:

- REPO_NAME: The name of the repository.
- LATEST_COMMIT_DATE: The most recent commit date (in MM/DD/YYYY format).

## 🚀 Running the Script
```bash
python jenkins_repo_audit.py
````