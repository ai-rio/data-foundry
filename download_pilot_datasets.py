#!/usr/bin/env python3
"""
Download pilot test datasets from public sources.
No Kaggle authentication needed for this approach.
"""

import os
import urllib.request
import urllib.error
import zipfile
import shutil
from pathlib import Path

# Dataset download URLs (direct links where available)
DATASETS = {
    "fintech": {
        "name": "USA Banking Transactions Dataset",
        "urls": [
            # Fallback: Kaggle datasets page (requires manual download via browser)
            "https://www.kaggle.com/api/v1/datasets/download/pradeepkumar2424/usa-banking-transactions-dataset-2023-2024",
        ],
        "description": "5,000 categorized banking transactions",
        "path": "data/pilot_test_datasets/fintech"
    },
    "ecommerce": {
        "name": "E-Commerce Products Dataset",
        "urls": [
            "https://www.kaggle.com/api/v1/datasets/download/athulxavier/e-commerce-products-dataset",
        ],
        "description": "10,000+ products with categories",
        "path": "data/pilot_test_datasets/ecommerce"
    },
    "healthcare": {
        "name": "Healthcare Dataset (Synthetic)",
        "urls": [
            "https://www.kaggle.com/api/v1/datasets/download/prasad22/healthcare-dataset",
        ],
        "description": "10,000+ synthetic patient records",
        "path": "data/pilot_test_datasets/healthcare"
    },
    "legal": {
        "name": "CUAD Contract Dataset",
        "urls": [
            # Direct Zenodo link (doesn't require Kaggle auth)
            "https://zenodo.org/records/4595826/files/CUAD_v1.zip",
        ],
        "description": "510 contracts with 13,000+ labeled clauses",
        "path": "data/pilot_test_datasets/legal"
    },
}

def ensure_directory(path):
    """Ensure directory exists."""
    Path(path).mkdir(parents=True, exist_ok=True)
    print(f"✓ Directory ready: {path}")

def download_file(url, destination, max_retries=3):
    """Download file with retry logic."""
    for attempt in range(max_retries):
        try:
            print(f"  Downloading from: {url}")
            urllib.request.urlretrieve(url, destination)
            print(f"  ✓ Downloaded successfully")
            return True
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"  ✗ Authentication required for this URL")
                print(f"    You may need to download manually from Kaggle")
                return False
            elif attempt < max_retries - 1:
                print(f"  ⚠ Attempt {attempt + 1} failed, retrying...")
            else:
                print(f"  ✗ Download failed after {max_retries} attempts")
                return False
        except Exception as e:
            print(f"  ✗ Error: {str(e)}")
            return False
    return False

def unzip_file(zip_path, extract_path):
    """Unzip downloaded file."""
    try:
        print(f"  Extracting: {os.path.basename(zip_path)}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
        print(f"  ✓ Extracted successfully")
        # Remove zip after extraction
        os.remove(zip_path)
        return True
    except Exception as e:
        print(f"  ✗ Extraction failed: {str(e)}")
        return False

def main():
    """Main download routine."""
    print("\n" + "="*70)
    print("PILOT TEST DATASETS DOWNLOADER")
    print("="*70)

    results = {}

    for vertical, config in DATASETS.items():
        print(f"\n[{vertical.upper()}] {config['name']}")
        print(f"  Description: {config['description']}")

        # Ensure directory
        ensure_directory(config['path'])

        # Try to download
        success = False
        for url in config['urls']:
            zip_filename = f"{config['path']}/{vertical}_dataset.zip"

            if download_file(url, zip_filename):
                if unzip_file(zip_filename, config['path']):
                    success = True
                    break

            # If this URL failed, try the next one
            if not success and url != config['urls'][-1]:
                print("  Trying alternative URL...\n")

        results[vertical] = "✓ Downloaded" if success else "⚠ Requires manual download"

        if not success:
            print(f"\n  MANUAL DOWNLOAD REQUIRED:")
            print(f"  → Go to: https://www.kaggle.com/datasets/{vertical}")
            print(f"  → Download the dataset ZIP")
            print(f"  → Extract to: {os.path.abspath(config['path'])}")

    # Summary
    print("\n" + "="*70)
    print("DOWNLOAD SUMMARY")
    print("="*70)
    for vertical, status in results.items():
        print(f"  {vertical.upper():12} {status}")

    # List what was downloaded
    print("\n" + "="*70)
    print("DATASET CONTENTS")
    print("="*70)
    for vertical, config in DATASETS.items():
        path = config['path']
        if os.path.exists(path):
            files = os.listdir(path)
            if files:
                print(f"\n  {vertical.upper()}:")
                for file in files:
                    file_path = os.path.join(path, file)
                    if os.path.isfile(file_path):
                        size_mb = os.path.getsize(file_path) / (1024 * 1024)
                        print(f"    - {file} ({size_mb:.1f} MB)")
                    else:
                        print(f"    - {file}/ (directory)")
            else:
                print(f"\n  {vertical.upper()}: (empty - requires download)")

if __name__ == "__main__":
    main()
