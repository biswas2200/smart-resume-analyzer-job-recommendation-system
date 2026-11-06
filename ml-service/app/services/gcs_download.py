"""Copies a folder of a Google Cloud Storage bucket to disk, for fetching the
trained NER model at start-up (see local_ner_parser.ensure_local_model).

Authenticates with Application Default Credentials, like the Gemini path:
`gcloud auth application-default login` on a laptop, the attached service
account on GCP. No key file or API key. Uses the Cloud Storage JSON API
through google-auth, which is already installed for Gemini, so no extra
client library is needed.
"""

import logging
import shutil
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger(__name__)

_OBJECTS_URL = "https://storage.googleapis.com/storage/v1/b/{bucket}/o"
_READ_ONLY_SCOPE = "https://www.googleapis.com/auth/devstorage.read_only"


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    """`gs://bucket/some/folder` -> ("bucket", "some/folder/")."""
    if not uri.startswith("gs://"):
        raise ValueError(f"{uri!r} is not a gs:// URI.")
    bucket, _, prefix = uri[len("gs://"):].partition("/")
    if not bucket:
        raise ValueError(f"{uri!r} names no bucket.")
    prefix = prefix.strip("/")
    return bucket, f"{prefix}/" if prefix else ""


def download_folder(uri: str, dest: Path, session=None) -> int:
    """Downloads every file directly inside the `uri` folder into `dest`
    (replacing whatever is there) and returns how many were copied.
    Subfolders are skipped: a saved model is a flat folder. `session` is an
    authorised requests session; tests pass a fake one.
    """
    bucket, prefix = parse_gcs_uri(uri)
    if session is None:
        session = _adc_session()

    names = [name for name in _list_objects(session, bucket, prefix) if _is_direct_file(name, prefix)]
    if not names:
        raise FileNotFoundError(f"No files found under {uri}.")

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in names:
        response = session.get(
            f"{_OBJECTS_URL.format(bucket=bucket)}/{quote(name, safe='')}",
            params={"alt": "media"},
            stream=True,
        )
        response.raise_for_status()
        with open(dest / name[len(prefix):], "wb") as out:
            for block in response.iter_content(chunk_size=1 << 20):
                out.write(block)
    return len(names)


def _adc_session():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=[_READ_ONLY_SCOPE])
    return AuthorizedSession(credentials)


def _list_objects(session, bucket: str, prefix: str) -> list[str]:
    names, page_token = [], None
    while True:
        params = {"prefix": prefix, "fields": "items(name),nextPageToken"}
        if page_token:
            params["pageToken"] = page_token
        response = session.get(_OBJECTS_URL.format(bucket=bucket), params=params)
        response.raise_for_status()
        body = response.json()
        names.extend(item["name"] for item in body.get("items", []))
        page_token = body.get("nextPageToken")
        if not page_token:
            return names


def _is_direct_file(name: str, prefix: str) -> bool:
    """A file in the folder itself: no subfolder, no folder placeholder, and
    nothing that could write outside `dest`."""
    relative = name[len(prefix):]
    return bool(relative) and "/" not in relative and relative not in (".", "..")
