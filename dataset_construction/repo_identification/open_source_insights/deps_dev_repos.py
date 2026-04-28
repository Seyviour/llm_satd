import os
import pandas as pd
import requests
import json
from urllib.parse import quote
from urllib.parse import urlparse


BASE_URL = "https://api.deps.dev/v3alpha"
SYSTEM = "PYPI"

def get_version_data(package_name, version):
    url = f"{BASE_URL}/systems/{SYSTEM}/packages/{quote(package_name)}/versions/{quote(version)}"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def get_package_versions(package_name):
    url = f"{BASE_URL}/systems/{SYSTEM}/packages/{quote(package_name)}"
    r = requests.get(url)
    r.raise_for_status()
    return r.json().get("versions", [])

def is_valid_repo_url(url):
    """
    Validates if the URL is a proper GitHub, Bitbucket, or GitLab repo URL.
    """
    # Normalize and parse URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url  # ensure scheme exists

    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path_parts = [p for p in parsed.path.strip('/').split('/') if p]

    # Check domain
    valid_domains = {'github.com', 'bitbucket.org', 'gitlab.com'}
    if netloc not in valid_domains:
        return False

    # Must have exactly two path parts: /user/repo
    return len(path_parts) >= 2

def get_related_projects_for_latest(package_name):
    try:
        versions = get_package_versions(package_name)
        if not versions:
            return []

        default = next((v for v in versions if v.get("isDefault")), versions[0])
        version_info = get_version_data(package_name, default["versionKey"]["version"])

        valid_projects = []
        for proj in version_info.get("relatedProjects", []):
            project_id = proj["projectKey"]["id"]
            if is_valid_repo_url(project_id):
                valid_projects.append(project_id)
            else:
                print(f"Invalid project ID: {project_id}")
        return valid_projects
    except Exception as e:
        return []
    
    