# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "boto3",
# ]
# ///

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

CDN_BASE_URL = os.environ.get("CDN_BASE_URL", "https://cdn.packtrans.download")
METADATA_KEY = "glossary/metadata.json"
INDEXES_PREFIX = "glossary/indexes"
KEEP_VERSIONS = int(os.environ.get("KEEP_VERSIONS", "3"))
ASSET_PATTERN = re.compile(r"^packtrans-glossary-index-(.+)-[0-9]{8}\.zip$")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def s3_client() -> object:
    return boto3.client(
        "s3",
        endpoint_url=require_env("S3_ENDPOINT"),
        aws_access_key_id=require_env("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=require_env("S3_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("S3_REGION", "auto"),
    )


def index_url(version_tag: str, lang: str) -> str:
    return (
        f"{CDN_BASE_URL}/glossary/indexes/{version_tag}/"
        f"packtrans-glossary-index-{lang}.zip"
    )


def upload_zip(client: object, bucket: str, version_tag: str, zip_path: Path, lang: str) -> None:
    dest_key = f"{INDEXES_PREFIX}/{version_tag}/packtrans-glossary-index-{lang}.zip"
    print(f"Uploading {zip_path.name} -> s3://{bucket}/{dest_key}")
    client.upload_file(
        str(zip_path),
        bucket,
        dest_key,
        ExtraArgs={
            "ContentType": "application/zip",
            "CacheControl": "public, max-age=3600",
        },
    )


def load_metadata(client: object, bucket: str) -> dict:
    try:
        response = client.get_object(Bucket=bucket, Key=METADATA_KEY)
        print("Loaded existing metadata.json")
        return json.loads(response["Body"].read())
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"404", "NoSuchKey"}:
            return {"indexes": []}
        raise


def build_metadata(existing: dict, version_tag: str, languages: list[str]) -> dict:
    new_entry = {
        "version": version_tag,
        "indexesLanguages": languages,
        "indexesFiles": {lang: index_url(version_tag, lang) for lang in languages},
    }

    indexes = [new_entry] + [
        entry
        for entry in existing.get("indexes", [])
        if entry.get("version") != version_tag
    ]
    indexes.sort(key=lambda entry: entry["version"], reverse=True)
    indexes = indexes[:KEEP_VERSIONS]

    return {
        "lastUpdatedAt": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "latestIndexesVersion": indexes[0]["version"],
        "indexes": indexes,
    }


def upload_metadata(client: object, bucket: str, metadata: dict) -> None:
    body = json.dumps(metadata, indent=2, ensure_ascii=False).encode()
    print(f"Uploading metadata.json -> s3://{bucket}/{METADATA_KEY}")
    client.put_object(
        Bucket=bucket,
        Key=METADATA_KEY,
        Body=body,
        ContentType="application/json",
        CacheControl="public, max-age=300",
    )


def list_index_versions(client: object, bucket: str) -> list[str]:
    versions: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{INDEXES_PREFIX}/", Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            version = prefix["Prefix"].removeprefix(f"{INDEXES_PREFIX}/").strip("/")
            if version:
                versions.append(version)
    return versions


def delete_old_versions(client: object, bucket: str, kept_versions: set[str]) -> None:
    for version in list_index_versions(client, bucket):
        if version in kept_versions:
            continue
        prefix = f"{INDEXES_PREFIX}/{version}/"
        print(f"Deleting old version from S3: {prefix}")
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                client.delete_objects(Bucket=bucket, Delete={"Objects": objects})


def collect_languages(assets_dir: Path, version_tag: str, client: object, bucket: str) -> list[str]:
    languages: list[str] = []

    for zip_path in sorted(assets_dir.glob("*.zip")):
        match = ASSET_PATTERN.match(zip_path.name)
        if not match:
            print(f"Skipping unrecognized asset: {zip_path.name}", flush=True)
            continue

        lang = match.group(1)
        languages.append(lang)
        upload_zip(client, bucket, version_tag, zip_path, lang)

    if not languages:
        raise SystemExit(f"No glossary index zip assets found in {assets_dir}")

    return sorted(set(languages))


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish glossary index assets and metadata to S3")
    parser.add_argument("version_tag", help="Release tag, e.g. index-20260601")
    parser.add_argument("assets_dir", type=Path, help="Directory containing release zip assets")
    args = parser.parse_args()

    if not re.fullmatch(r"index-[0-9]{8}", args.version_tag):
        raise SystemExit(f"Unsupported release tag: {args.version_tag} (expected index-YYYYMMDD)")

    if not args.assets_dir.is_dir():
        raise SystemExit(f"Assets directory not found: {args.assets_dir}")

    bucket = require_env("S3_BUCKET")
    client = s3_client()

    languages = collect_languages(args.assets_dir, args.version_tag, client, bucket)
    metadata = build_metadata(load_metadata(client, bucket), args.version_tag, languages)
    upload_metadata(client, bucket, metadata)

    kept_versions = {entry["version"] for entry in metadata["indexes"]}
    print("Keeping versions:")
    for version in metadata["indexes"]:
        print(version["version"])

    delete_old_versions(client, bucket, kept_versions)
    print("Publish complete.")


if __name__ == "__main__":
    main()
