import os
import json
import csv
import sys
from datetime import datetime, timedelta
from urllib.parse import urljoin, quote

import requests
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BITBUCKET_CSV_PATH = os.getenv("BITBUCKET_CSV_PATH")
JENKINS_ROOT_URL = 'http://jenkins-cb.regeneron.regn.com'
JENKINS_USERNAME = os.getenv("JENKINS_USERNAME")
JENKINS_PASSWORD = os.getenv("JENKINS_PASSWORD")
COMMIT_DATE_COLUMN = "LATEST_COMMIT_DATE"
REPO_NAME_COLUMN = "REPO_NAME"
DATE_FORMAT = '%m/%d/%Y'
TIME_DELTA_YEARS = int(os.getenv("TIME_DELTA_YEARS", "1"))
CA_CERT_PATH = os.getenv("CA_CERT_PATH")
OUTPUT_FILE = os.getenv("OUTPUT_FILE")
EXCEL_OUTPUT_FILE = os.getenv("EXCEL_OUTPUT_FILE")

all_jobs = []
all_controllers = []

# Use a requests.Session to reuse HTTP connections
session = requests.Session()
session.auth = HTTPBasicAuth(JENKINS_USERNAME, JENKINS_PASSWORD)
session.verify = CA_CERT_PATH


def serialize_datetime(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def get_relevant_repositories(csv_path, date_column, repo_column, date_format, years):
    relevant_repos = []
    cutoff_date = datetime.now() - timedelta(days=years * 365)

    try:
        with open(csv_path, 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            if date_column not in reader.fieldnames or repo_column not in reader.fieldnames:
                print(f"Error: '{date_column}' or '{repo_column}' column not found in CSV.")
                return relevant_repos

            for row in reader:
                try:
                    commit_date_str = row[date_column].strip()
                    commit_date = datetime.strptime(commit_date_str, date_format)
                    if commit_date > cutoff_date:
                        relevant_repos.append(row[repo_column].strip())
                except ValueError:
                    print(f"Warning: Could not parse date '{commit_date_str}' in row: {row}")
                except KeyError:
                    print(f"Warning: Missing column in row: {row}")
    except FileNotFoundError:
        print(f"Error: CSV file not found at '{csv_path}'")

    return list(set(relevant_repos))


def fetch_controllers_data():
    try:
        response = session.get(f"{JENKINS_ROOT_URL}/cjoc/")
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        job_items = soup.select('.jenkins-jobs-list_item')

        for item in job_items:
            details_link = item.select_one('.jenkins-jobs-list_item_details')
            if details_link and 'href' in details_link.attrs:
                job_url_relative = details_link['href']
                job_name = job_url_relative.strip('/').split('/')[-1]
                if job_name:
                    all_controllers.append(job_name)

        return all_controllers

    except requests.exceptions.RequestException as e:
        print(f"CRITICAL ERROR: Failed to fetch Jenkins data from {JENKINS_ROOT_URL}. Reason: {e}")
        sys.exit(1)  # Terminate script on critical failure


def fetch_jenkins_data(url):
    try:
        response = session.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"CRITICAL ERROR: Failed to fetch Jenkins data from {url}. Reason: {e}")
        return None


def traverse_jobs(current_jenkins_url, controller):
    api_url = urljoin(current_jenkins_url + "/", "api/json?tree=jobs[name],views[name,jobs[name]]&pretty=true")
    data = fetch_jenkins_data(api_url)
    if not data:
        return

    jobs = data.get("jobs", [])
    for job in jobs:
        job_name = job.get("name")
        if not job_name:
            continue

        if job.get("_class") != "org.jenkinsci.plugins.workflow.job.WorkflowJob":
            # Recursively traverse nested jobs
            traverse_jobs(urljoin(current_jenkins_url + "/", f"job/{job_name}"), controller)
        else:
            encoded_tree = quote("name,builds[number],actions[remoteUrls,_class]")
            job_details_url = f"{current_jenkins_url}/job/{job_name}/api/json?tree={encoded_tree}"
            job_details = fetch_jenkins_data(job_details_url)

            if not job_details:
                continue

            job_info = {"name": job_details.get("name"), "controller": controller}

            builds = job_details.get("builds", [])
            if builds:
                latest_build_no = builds[0].get("number")
                if latest_build_no is not None:
                    try:
                        build_url = (
                            f"{current_jenkins_url}/job/{job_name}/{latest_build_no}/api/json?"
                            "tree=actions[remoteUrls,_class],timestamp,result,url&pretty=true"
                        )
                        response = session.get(build_url)
                        response.raise_for_status()
                        build_data = response.json()

                        remote_urls = []
                        for action in build_data.get('actions', []):
                            if action.get('_class') == 'hudson.plugins.git.util.BuildData' and 'remoteUrls' in action:
                                remote_urls.extend(action['remoteUrls'])

                        if remote_urls:
                            job_info["remoteUrls"] = remote_urls

                        job_info["pipelineUrl"] = build_data.get("url")

                        timestamp_ms = build_data.get("timestamp")
                        if timestamp_ms is not None:
                            job_info["timestamp"] = datetime.fromtimestamp(timestamp_ms / 1000)

                        job_info["result"] = build_data.get("result")

                    except requests.exceptions.RequestException as e:
                        print(f"ERROR: Failed to fetch build data for job '{job_name}' build '{latest_build_no}'. Reason: {e}")
                else:
                    print(f"WARNING: No latest build number found for job '{job_name}'. Skipping build details.")
            # Append job info even if build details are missing
            all_jobs.append(job_info)


def main():
    try:
        # Uncomment if repository filtering needed
        # relevant_repos = get_relevant_repositories(BITBUCKET_CSV_PATH, COMMIT_DATE_COLUMN, REPO_NAME_COLUMN, DATE_FORMAT, TIME_DELTA_YEARS)
        # if not relevant_repos:
        #     print("No relevant repositories found based on the commit date.")
        #     return

        controllers = fetch_controllers_data()
        if not controllers:
            print("No Controllers found.")
            return

        for controller_segment in all_controllers:
            if controller_segment.lower() == "datapipeline":
                continue

            initial_controller_url = urljoin(JENKINS_ROOT_URL + "/", f"{controller_segment}/")
            print(f"\nTraversing controller: {initial_controller_url}")

            traverse_jobs(initial_controller_url, controller_segment)

        # Write JSON output
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_jobs, f, indent=4, default=serialize_datetime)
        print(f"\nJob data saved to {OUTPUT_FILE}")

    except Exception as e:
        print(f"Error during processing: {e}")
        sys.exit(1)

    # Convert JSON data to Excel
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            jobs = json.load(f)

        # Normalize remoteUrls to comma-separated string for Excel
        for job in jobs:
            if "remoteUrls" in job and isinstance(job["remoteUrls"], list):
                job["remoteUrls"] = ", ".join(job["remoteUrls"])

        df = pd.DataFrame(jobs)

        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

        df.to_excel(EXCEL_OUTPUT_FILE, index=False)
        print(f"\nJob data successfully exported to {EXCEL_OUTPUT_FILE}")

    except FileNotFoundError:
        print(f"Error: The file '{OUTPUT_FILE}' was not found. Please ensure JSON data is saved to this file.")
    except Exception as e:
        print(f"An error occurred while exporting to Excel: {e}")


if __name__ == "__main__":
    main()
